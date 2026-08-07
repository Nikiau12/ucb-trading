#!/usr/bin/env python3
"""Strict BTC breakout and ETH range-reversion research protocol.

Candidate libraries are fixed in source. A winner must survive rolling
selection, higher-friction and delayed-entry stress tests, and an independent
confirmation window before outer validation can be opened. The final test is
never opened by this runner.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Sequence

from trading.backtest import BacktestConfig, HOUR_SECONDS, run_backtest
from trading.research_setups import (
    BTC_SETUPS,
    BTC_V1_SETUPS,
    ETH_SETUPS,
    ETH_V1_SETUPS,
    btc_plan_builder,
    eth_plan_builder,
)
from trading.trade_plan import make_plan

from .run_btc_stability import (
    ROLLING_BOUNDARIES,
    stability_eligible,
    stability_metrics,
    stability_score,
)
from .run_symbol_optimization import (
    INTERNAL_CONFIRMATION_START,
    cached_builder,
)
from .run_walk_forward import (
    LOCKED_TEST_END,
    LOCKED_TRAIN_END,
    LOCKED_VALIDATION_END,
    fetch_bars,
    fetch_contract,
    iso,
)


PlanBuilder = Callable[..., Dict[str, Any]]


def build_research_cache(
    bars: Sequence[Any],
    symbol: str,
    contract: Dict[str, Any],
    builder: PlanBuilder,
    start: int,
    end: int,
    config: BacktestConfig,
) -> Dict[int, Dict[str, Any]]:
    plans: Dict[int, Dict[str, Any]] = {}

    def capture(snapshot: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
        decision_time = int(snapshot["kline_1h"]["data"][-1][0]) + HOUR_SECONDS
        plans[decision_time] = builder(snapshot, **kwargs)
        return {"side": "skip", "confidence": 0, "reasons": ["research_cache_capture"]}

    run_backtest(
        bars,
        symbol=symbol,
        config=config,
        contract_rules=contract,
        plan_builder=capture,
        evaluation_start=start,
        evaluation_end=end,
    )
    return plans


def evaluate_cached(
    bars: Sequence[Any],
    symbol: str,
    contract: Dict[str, Any],
    plans: Mapping[int, Dict[str, Any]],
    start: int,
    end: int,
    config: BacktestConfig,
) -> Dict[str, Any]:
    return run_backtest(
        bars,
        symbol=symbol,
        config=config,
        contract_rules=contract,
        plan_builder=cached_builder(plans),
        evaluation_start=start,
        evaluation_end=end,
    )


def stress_passes(summary: Mapping[str, Any], minimum_trades: int) -> bool:
    return (
        summary["trades"] >= minimum_trades
        and summary["return_pct"] > 0
        and (summary["profit_factor"] or 0) > 1
    )


def confirmation_passes_v2(
    candidate: Mapping[str, Any],
    baseline: Mapping[str, Any],
    high_cost: Mapping[str, Any],
    delayed: Mapping[str, Any],
) -> bool:
    return (
        candidate["trades"] >= 5
        and candidate["return_pct"] > 0
        and candidate["return_pct"] > baseline["return_pct"]
        and (candidate["profit_factor"] or 0) > 1
        and candidate["max_drawdown_pct"] <= max(baseline["max_drawdown_pct"], 5.0)
        and stress_passes(high_cost, 3)
        and stress_passes(delayed, 3)
    )


def _summary(result: Mapping[str, Any]) -> Dict[str, Any]:
    return dict(result["summary"])


def research_symbol(
    symbol: str,
    bars: Sequence[Any],
    contract: Dict[str, Any],
    setups: Sequence[Any],
    builder_factory: Callable[[Any], PlanBuilder],
    config: BacktestConfig,
) -> Dict[str, Any]:
    first = bars[0].ts + config.warmup_hours * HOUR_SECONDS
    boundaries = (first, *ROLLING_BOUNDARIES)
    profiles = []
    cache_by_name: Dict[str, Dict[int, Dict[str, Any]]] = {}
    for setup in setups:
        plans = build_research_cache(
            bars,
            symbol,
            contract,
            builder_factory(setup),
            first,
            LOCKED_VALIDATION_END,
            config,
        )
        cache_by_name[setup.name] = plans
        windows = [
            evaluate_cached(bars, symbol, contract, plans, start, end, config)
            for start, end in zip(boundaries, boundaries[1:])
        ]
        profiles.append({
            "setup": asdict(setup),
            "windows": [_summary(result) for result in windows],
            "stability": stability_metrics(_summary(result) for result in windows),
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

    selected_name = selected["setup"]["name"]
    plans = cache_by_name[selected_name]
    high_cost_config = replace(config, fee_bps=8, slippage_bps=4)
    delayed_config = replace(config, entry_delay_bars=2)
    high_cost_selection = evaluate_cached(
        bars, symbol, contract, plans, first, INTERNAL_CONFIRMATION_START, high_cost_config
    )
    delayed_selection = evaluate_cached(
        bars, symbol, contract, plans, first, INTERNAL_CONFIRMATION_START, delayed_config
    )
    report["selection_stress"] = {
        "high_cost": _summary(high_cost_selection),
        "delayed_entry": _summary(delayed_selection),
    }
    report["selection_stress_passed"] = (
        stress_passes(_summary(high_cost_selection), 10)
        and stress_passes(_summary(delayed_selection), 10)
    )
    if not report["selection_stress_passed"]:
        return report

    baseline = run_backtest(
        bars,
        symbol=symbol,
        config=config,
        contract_rules=contract,
        plan_builder=make_plan,
        evaluation_start=INTERNAL_CONFIRMATION_START,
        evaluation_end=LOCKED_TRAIN_END,
    )
    candidate = evaluate_cached(
        bars, symbol, contract, plans, INTERNAL_CONFIRMATION_START, LOCKED_TRAIN_END, config
    )
    high_cost = evaluate_cached(
        bars, symbol, contract, plans, INTERNAL_CONFIRMATION_START, LOCKED_TRAIN_END, high_cost_config
    )
    delayed = evaluate_cached(
        bars, symbol, contract, plans, INTERNAL_CONFIRMATION_START, LOCKED_TRAIN_END, delayed_config
    )
    report["confirmation"] = {
        "production_baseline": _summary(baseline),
        "candidate": _summary(candidate),
        "high_cost": _summary(high_cost),
        "delayed_entry": _summary(delayed),
    }
    report["confirmation_passed"] = confirmation_passes_v2(
        _summary(candidate), _summary(baseline), _summary(high_cost), _summary(delayed)
    )
    if not report["confirmation_passed"]:
        return report

    validation_baseline = run_backtest(
        bars,
        symbol=symbol,
        config=config,
        contract_rules=contract,
        plan_builder=make_plan,
        evaluation_start=LOCKED_TRAIN_END,
        evaluation_end=LOCKED_VALIDATION_END,
    )
    validation_candidate = evaluate_cached(
        bars, symbol, contract, plans, LOCKED_TRAIN_END, LOCKED_VALIDATION_END, config
    )
    validation_high_cost = evaluate_cached(
        bars, symbol, contract, plans, LOCKED_TRAIN_END, LOCKED_VALIDATION_END, high_cost_config
    )
    validation_delayed = evaluate_cached(
        bars, symbol, contract, plans, LOCKED_TRAIN_END, LOCKED_VALIDATION_END, delayed_config
    )
    report["validation"] = {
        "production_baseline": _summary(validation_baseline),
        "candidate": _summary(validation_candidate),
        "high_cost": _summary(validation_high_cost),
        "delayed_entry": _summary(validation_delayed),
    }
    report["validation_passed"] = confirmation_passes_v2(
        _summary(validation_candidate),
        _summary(validation_baseline),
        _summary(validation_high_cost),
        _summary(validation_delayed),
    )
    return report


def run(
    count: int,
    cache_dir: Path,
    data_end_close: int,
    iteration: str = "v2",
) -> Dict[str, Any]:
    config = BacktestConfig(
        initial_deposit=1_000,
        risk_pct=1,
        leverage=10,
        fee_bps=4,
        slippage_bps=2,
    )
    setup_library = {
        "v1": (BTC_V1_SETUPS, ETH_V1_SETUPS),
        "v2": (BTC_SETUPS, ETH_SETUPS),
    }
    btc_setups, eth_setups = setup_library[iteration]
    specifications = (
        ("BTC_USDT", btc_setups, btc_plan_builder),
        ("ETH_USDT", eth_setups, eth_plan_builder),
    )
    assets = {}
    for symbol, setups, builder_factory in specifications:
        bars = fetch_bars(symbol, count, cache_dir, end_close=data_end_close)
        contract = fetch_contract(symbol, cache_dir)
        assets[symbol] = research_symbol(
            symbol, bars, contract, setups, builder_factory, config
        )
    first = min(
        fetch_bars(symbol, count, cache_dir, end_close=data_end_close)[0].ts
        for symbol, _, _ in specifications
    ) + config.warmup_hours * HOUR_SECONDS
    return {
        "protocol": {
            "iteration": iteration,
            "candidate_policy": "8 pre-registered setups per asset; no continuous parameter search",
            "rolling_windows": [
                {"start": iso(start), "end": iso(end)}
                for start, end in zip((first, *ROLLING_BOUNDARIES), ROLLING_BOUNDARIES)
            ],
            "selection_gate": ">=3/4 positive windows, >=20 trades, positive mean return",
            "selection_stress_gate": ">=10 trades, return>0, PF>1 under both 8/4 bps friction and one-extra-bar delay",
            "confirmation_gate": ">=5 trades, PF>1, beats production baseline, controlled DD; stress cases >=3 trades and positive",
            "validation": {"start": iso(LOCKED_TRAIN_END), "end": iso(LOCKED_VALIDATION_END)},
            "test": {"start": iso(LOCKED_VALIDATION_END), "end": iso(LOCKED_TEST_END), "opened": False},
        },
        "assets": assets,
        "production_change_recommended": False,
    }


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="BTC/ETH regime strategy research")
    parser.add_argument("--candles", type=int, default=35_000)
    parser.add_argument("--cache-dir", type=Path, default=Path("/tmp/ucb-walk-forward-data"))
    parser.add_argument("--data-end", default="2026-08-07T11:00:00Z")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--iteration", choices=("v1", "v2"), default="v2")
    args = parser.parse_args(list(argv) if argv is not None else None)
    data_end_close = int(
        datetime.fromisoformat(args.data_end.replace("Z", "+00:00")).timestamp()
    )
    report = run(args.candles, args.cache_dir, data_end_close, args.iteration)
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(payload + "\n")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
