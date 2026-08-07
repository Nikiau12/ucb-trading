#!/usr/bin/env python3
"""Fresh 1D-context + native-4H-setup research for BTC, ETH and SOL."""
from __future__ import annotations

import argparse
import copy
import json
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Sequence

from trading.backtest import BacktestConfig, HOUR_SECONDS, resample_completed, run_backtest
from trading.higher_timeframe_setups import (
    BTC_4H_1D_SETUPS,
    ETH_4H_1D_SETUPS,
    SOL_4H_1D_SETUPS,
    htf_plan_builder,
)
from trading.trade_plan import normalize_for_contract

from .run_btc_stability import stability_eligible, stability_metrics, stability_score
from .run_walk_forward import fetch_bars, fetch_contract, iso


FOUR_HOURS = 4 * HOUR_SECONDS
SELECTION_BOUNDARIES = tuple(
    int(value.timestamp())
    for value in (
        datetime(2023, 7, 1, 8, tzinfo=timezone.utc),
        datetime(2024, 3, 1, 8, tzinfo=timezone.utc),
        datetime(2024, 11, 1, 8, tzinfo=timezone.utc),
        datetime(2025, 6, 1, 8, tzinfo=timezone.utc),
    )
)
CONFIRMATION_END = int(datetime(2025, 12, 24, 8, tzinfo=timezone.utc).timestamp())
VALIDATION_END = int(datetime(2026, 4, 16, 8, tzinfo=timezone.utc).timestamp())
TEST_END = int(datetime(2026, 8, 7, 8, tzinfo=timezone.utc).timestamp())


PlanBuilder = Callable[..., Dict[str, Any]]


def to_closed_4h(bars_1h: Sequence[Any], end_close: int) -> list[Any]:
    return resample_completed(
        bars_1h,
        FOUR_HOURS,
        end_close,
        HOUR_SECONDS,
    )


def build_plan_cache(
    bars_4h: Sequence[Any],
    symbol: str,
    contract: Dict[str, Any],
    builder: PlanBuilder,
    start: int,
    end: int,
    config: BacktestConfig,
) -> Dict[int, Dict[str, Any]]:
    plans: Dict[int, Dict[str, Any]] = {}

    def capture(snapshot: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
        decision_time = int(snapshot["kline_4h"]["data"][-1][0]) + FOUR_HOURS
        plans[decision_time] = builder(snapshot, **kwargs)
        return {"side": "skip", "confidence": 0, "reasons": ["4h_cache_capture"]}

    run_backtest(
        bars_4h,
        symbol=symbol,
        config=config,
        contract_rules=contract,
        plan_builder=capture,
        evaluation_start=start,
        evaluation_end=end,
    )
    return plans


def cached_builder(plans: Mapping[int, Dict[str, Any]]) -> PlanBuilder:
    def build(
        snapshot: Dict[str, Any],
        *,
        deposit: float,
        risk_pct: float,
        lev: float,
        margin: str,
    ) -> Dict[str, Any]:
        del margin
        decision_time = int(snapshot["kline_4h"]["data"][-1][0]) + FOUR_HOURS
        plan = copy.deepcopy(plans[decision_time])
        primary = plan.get("primary") or {}
        targets = primary.get("tps") or []
        if plan.get("side") == "skip" or len(targets) < 2:
            return plan
        normalized = normalize_for_contract(
            snapshot,
            str(primary["side"]),
            float(primary["entry"]),
            float(primary["stop"]),
            float(targets[0]["price"]),
            float(targets[1]["price"]),
            deposit,
            risk_pct,
            lev,
        )
        primary.update({
            "entry": normalized["entry"],
            "stop": normalized["stop"],
            "qty": normalized["qty"],
            "risk_usdt": normalized["risk_usdt"],
        })
        targets[0]["price"] = normalized["tp1"]
        targets[1]["price"] = normalized["tp2"]
        return plan

    return build


def evaluate(
    bars_4h: Sequence[Any],
    symbol: str,
    contract: Dict[str, Any],
    plans: Mapping[int, Dict[str, Any]],
    start: int,
    end: int,
    config: BacktestConfig,
) -> Dict[str, Any]:
    return run_backtest(
        bars_4h,
        symbol=symbol,
        config=config,
        contract_rules=contract,
        plan_builder=cached_builder(plans),
        evaluation_start=start,
        evaluation_end=end,
    )


def gate(summary: Mapping[str, Any], minimum_trades: int) -> bool:
    return (
        summary["trades"] >= minimum_trades
        and summary["return_pct"] > 0
        and (summary["profit_factor"] or 0) > 1
        and summary["max_drawdown_pct"] <= 12
    )


def research_asset(
    symbol: str,
    bars_4h: Sequence[Any],
    contract: Dict[str, Any],
    setups: Sequence[Any],
    config: BacktestConfig,
) -> Dict[str, Any]:
    first = bars_4h[0].ts + config.warmup_hours * HOUR_SECONDS
    boundaries = (first, *SELECTION_BOUNDARIES)
    profiles = []
    caches: Dict[str, Dict[int, Dict[str, Any]]] = {}
    for setup in setups:
        plans = build_plan_cache(
            bars_4h,
            symbol,
            contract,
            htf_plan_builder(setup),
            first,
            VALIDATION_END,
            config,
        )
        caches[setup.name] = plans
        windows = [
            evaluate(bars_4h, symbol, contract, plans, start, end, config)
            for start, end in zip(boundaries, boundaries[1:])
        ]
        summaries = [dict(result["summary"]) for result in windows]
        profiles.append({
            "setup": asdict(setup),
            "windows": summaries,
            "stability": stability_metrics(summaries),
        })

    eligible = [item for item in profiles if stability_eligible(item["stability"])]
    selected = max(eligible, key=lambda item: stability_score(item["stability"])) if eligible else None
    report: Dict[str, Any] = {
        "symbol": symbol,
        "profiles": profiles,
        "selected": selected["setup"] if selected else None,
        "selection_stress": None,
        "selection_stress_passed": False,
        "confirmation": None,
        "confirmation_passed": False,
        "validation": None,
        "validation_passed": False,
        "test_opened": False,
    }
    if selected is None:
        return report

    plans = caches[selected["setup"]["name"]]
    high_cost_config = replace(config, fee_bps=8, slippage_bps=4)
    delayed_config = replace(config, entry_delay_bars=2)
    high_cost = evaluate(
        bars_4h, symbol, contract, plans, first, SELECTION_BOUNDARIES[-1], high_cost_config
    )
    delayed = evaluate(
        bars_4h, symbol, contract, plans, first, SELECTION_BOUNDARIES[-1], delayed_config
    )
    report["selection_stress"] = {
        "higher_friction": dict(high_cost["summary"]),
        "one_extra_4h_bar_delay": dict(delayed["summary"]),
    }
    report["selection_stress_passed"] = gate(high_cost["summary"], 10) and gate(
        delayed["summary"], 10
    )
    if not report["selection_stress_passed"]:
        return report

    confirmation = evaluate(
        bars_4h,
        symbol,
        contract,
        plans,
        SELECTION_BOUNDARIES[-1],
        CONFIRMATION_END,
        config,
    )
    confirmation_high_cost = evaluate(
        bars_4h,
        symbol,
        contract,
        plans,
        SELECTION_BOUNDARIES[-1],
        CONFIRMATION_END,
        high_cost_config,
    )
    confirmation_delayed = evaluate(
        bars_4h,
        symbol,
        contract,
        plans,
        SELECTION_BOUNDARIES[-1],
        CONFIRMATION_END,
        delayed_config,
    )
    report["confirmation"] = {
        "candidate": dict(confirmation["summary"]),
        "higher_friction": dict(confirmation_high_cost["summary"]),
        "one_extra_4h_bar_delay": dict(confirmation_delayed["summary"]),
    }
    report["confirmation_passed"] = (
        gate(confirmation["summary"], 5)
        and gate(confirmation_high_cost["summary"], 3)
        and gate(confirmation_delayed["summary"], 3)
    )
    if not report["confirmation_passed"]:
        return report

    validation = evaluate(
        bars_4h, symbol, contract, plans, CONFIRMATION_END, VALIDATION_END, config
    )
    report["validation"] = dict(validation["summary"])
    report["validation_passed"] = gate(validation["summary"], 5)
    return report


def run(count: int, cache_dir: Path, data_end_close: int) -> Dict[str, Any]:
    config = BacktestConfig(
        initial_deposit=1_000,
        risk_pct=1,
        leverage=10,
        fee_bps=4,
        slippage_bps=2,
        entry_expiry_bars=3,
        max_holding_bars=84,
        warmup_hours=24 * 120,
        decision_interval_hours=4,
        bar_interval_hours=4,
    )
    libraries = {
        "BTC_USDT": BTC_4H_1D_SETUPS,
        "ETH_USDT": ETH_4H_1D_SETUPS,
        "SOL_USDT": SOL_4H_1D_SETUPS,
    }
    assets = {}
    starts = []
    for symbol, setups in libraries.items():
        bars_1h = fetch_bars(symbol, count, cache_dir, end_close=data_end_close)
        bars_4h = to_closed_4h(bars_1h, data_end_close)
        contract = fetch_contract(symbol, cache_dir)
        starts.append(bars_4h[0].ts + config.warmup_hours * HOUR_SECONDS)
        assets[symbol] = research_asset(symbol, bars_4h, contract, setups, config)
    first = max(starts)
    return {
        "protocol": {
            "signal_timeframes": ["4h", "1d"],
            "hourly_signal_features": False,
            "hourly_source_use": "resampling into complete 4h candles only",
            "execution_bar": "4h",
            "windows": {
                "selection": [
                    {"start": iso(start), "end": iso(end)}
                    for start, end in zip((first, *SELECTION_BOUNDARIES), SELECTION_BOUNDARIES)
                ],
                "confirmation": {"start": iso(SELECTION_BOUNDARIES[-1]), "end": iso(CONFIRMATION_END)},
                "validation": {"start": iso(CONFIRMATION_END), "end": iso(VALIDATION_END)},
                "test": {"start": iso(VALIDATION_END), "end": iso(TEST_END), "opened": False},
            },
            "stress": "8/4 bps friction and one additional 4h entry-delay bar",
        },
        "assets": assets,
        "production_change_recommended": False,
    }


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Native 4H + 1D strategy research")
    parser.add_argument("--candles", type=int, default=35_000)
    parser.add_argument("--cache-dir", type=Path, default=Path("/tmp/ucb-walk-forward-data"))
    parser.add_argument("--data-end", default="2026-08-07T08:00:00Z")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    data_end_close = int(
        datetime.fromisoformat(args.data_end.replace("Z", "+00:00")).timestamp()
    )
    report = run(args.candles, args.cache_dir, data_end_close)
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(payload + "\n")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
