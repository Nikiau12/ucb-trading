#!/usr/bin/env python3
"""Select a separate frozen strategy profile for BTC, ETH and SOL.

Each symbol chooses one profile on the selection window. That single winner is
then checked on an internal confirmation window before outer validation can be
opened. The final test stays closed unless every requested symbol passes.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import copy
import json
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional

from trading.backtest import BacktestConfig, HOUR_SECONDS, run_backtest
from trading.trade_plan import make_plan, normalize_for_contract

from .run_walk_forward import (
    Candidate,
    LOCKED_TEST_END,
    LOCKED_TRAIN_END,
    LOCKED_VALIDATION_END,
    accepts_candidate,
    fetch_bars,
    fetch_contract,
    iso,
)


INTERNAL_CONFIRMATION_START = int(
    datetime(2025, 6, 1, 11, tzinfo=timezone.utc).timestamp()
)


# The same bounded library is offered to every symbol. Only the selected
# profile may differ; thresholds are not optimized continuously per coin.
SYMBOL_PROFILES = (
    Candidate("baseline_060", 0.60),
    Candidate("trend_only", 0.60, allowed_regimes=("trend",)),
    Candidate(
        "trend_1h_confirmation",
        0.60,
        allowed_regimes=("trend",),
        require_1h_confirmation=True,
    ),
    Candidate(
        "trend_1h_confirmation_rsi",
        0.60,
        allowed_regimes=("trend",),
        require_rsi_momentum=True,
        require_1h_confirmation=True,
    ),
    Candidate(
        "trend_1h_confirmation_rsi_long",
        0.60,
        allowed_regimes=("trend",),
        require_rsi_momentum=True,
        require_1h_confirmation=True,
        allowed_sides=("long",),
    ),
    Candidate(
        "trend_1h_confirmation_rsi_short",
        0.60,
        allowed_regimes=("trend",),
        require_rsi_momentum=True,
        require_1h_confirmation=True,
        allowed_sides=("short",),
    ),
    Candidate(
        "trend_near_entry_rsi",
        0.60,
        allowed_regimes=("trend",),
        require_rsi_momentum=True,
        min_entry_distance_atr=0.10,
        max_entry_distance_atr=0.50,
    ),
    Candidate("range_only", 0.60, allowed_regimes=("range",)),
)


def selection_eligible(summary: Mapping[str, Any]) -> bool:
    return (
        summary["trades"] >= 15
        and summary["return_pct"] > 0
        and (summary["profit_factor"] or 0) > 1
    )


def profile_score(summary: Mapping[str, Any]) -> float:
    return float(summary["return_pct"]) - 0.5 * float(summary["max_drawdown_pct"])


def confirmation_passes(candidate: Mapping[str, Any], baseline: Mapping[str, Any]) -> bool:
    return (
        candidate["trades"] >= 5
        and candidate["return_pct"] > 0
        and (candidate["profit_factor"] or 0) > 1
        and candidate["max_drawdown_pct"] <= baseline["max_drawdown_pct"]
        and candidate["return_pct"] > baseline["return_pct"]
    )


def outer_validation_passes(candidate: Mapping[str, Any], baseline: Mapping[str, Any]) -> bool:
    return confirmation_passes(candidate, baseline)


def build_plan_cache(
    bars: list[Any],
    symbol: str,
    contract: Dict[str, Any],
    start: int,
    end: int,
    config: BacktestConfig,
) -> Dict[int, Dict[str, Any]]:
    plans: Dict[int, Dict[str, Any]] = {}

    def capture(snapshot: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
        decision_time = int(snapshot["kline_1h"]["data"][-1][0]) + HOUR_SECONDS
        plans[decision_time] = make_plan(snapshot, **kwargs)
        return {"side": "skip", "confidence": 0, "reasons": ["cache_capture"]}

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


def cached_builder(plans: Mapping[int, Dict[str, Any]]):
    def build(
        snapshot: Dict[str, Any],
        *,
        deposit: float,
        risk_pct: float,
        lev: float,
        margin: str,
    ) -> Dict[str, Any]:
        del margin
        decision_time = int(snapshot["kline_1h"]["data"][-1][0]) + HOUR_SECONDS
        plan = copy.deepcopy(plans[decision_time])
        primary = plan.get("primary") or {}
        if plan.get("side") == "skip" or not primary:
            return plan
        targets = primary.get("tps") or []
        if len(targets) < 2:
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
            "contract_vol": normalized["contract_vol"],
            "contract_size": normalized["contract_size"],
            "vol_unit": normalized["vol_unit"],
            "min_vol": normalized["min_vol"],
            "max_vol": normalized["max_vol"],
            "max_leverage": normalized["max_leverage"],
            "effective_leverage": normalized["effective_leverage"],
            "price_unit": normalized.get("price_unit"),
            "risk_usdt": normalized["risk_usdt"],
            "margin_need": normalized["margin_usdt"],
        })
        primary["tps"][0]["price"] = normalized["tp1"]
        primary["tps"][1]["price"] = normalized["tp2"]
        return plan

    return build


def evaluate_profile(
    bars: list[Any],
    symbol: str,
    contract: Dict[str, Any],
    plans: Mapping[int, Dict[str, Any]],
    profile: Candidate,
    start: int,
    end: int,
    config: BacktestConfig,
) -> Dict[str, Any]:
    result = run_backtest(
        bars,
        symbol=symbol,
        config=replace(config, min_confidence=profile.min_confidence),
        contract_rules=contract,
        plan_builder=cached_builder(plans),
        plan_filter=lambda plan: accepts_candidate(plan, profile),
        evaluation_start=start,
        evaluation_end=end,
    )
    return {"profile": asdict(profile), "summary": result["summary"]}


def optimize_symbol(args: tuple[Any, ...]) -> Dict[str, Any]:
    symbol, bars, contract, config, first = args
    plans = build_plan_cache(
        bars, symbol, contract, first, LOCKED_VALIDATION_END, config
    )
    selection = [
        evaluate_profile(
            bars,
            symbol,
            contract,
            plans,
            profile,
            first,
            INTERNAL_CONFIRMATION_START,
            config,
        )
        for profile in SYMBOL_PROFILES
    ]
    eligible = [item for item in selection if selection_eligible(item["summary"])]
    selected = max(eligible, key=lambda item: profile_score(item["summary"])) if eligible else None
    report: Dict[str, Any] = {
        "symbol": symbol,
        "selection": selection,
        "selected": selected["profile"] if selected else None,
        "confirmation": None,
        "confirmation_passed": False,
        "validation": None,
        "validation_passed": False,
    }
    if selected is None:
        return report

    chosen = next(profile for profile in SYMBOL_PROFILES if profile.name == selected["profile"]["name"])
    baseline = SYMBOL_PROFILES[0]
    confirmation_baseline = evaluate_profile(
        bars, symbol, contract, plans, baseline,
        INTERNAL_CONFIRMATION_START, LOCKED_TRAIN_END, config,
    )
    confirmation_candidate = evaluate_profile(
        bars, symbol, contract, plans, chosen,
        INTERNAL_CONFIRMATION_START, LOCKED_TRAIN_END, config,
    )
    confirmed = confirmation_passes(
        confirmation_candidate["summary"], confirmation_baseline["summary"]
    )
    report["confirmation"] = {
        "baseline": confirmation_baseline,
        "candidate": confirmation_candidate,
    }
    report["confirmation_passed"] = confirmed
    if not confirmed:
        return report

    validation_baseline = evaluate_profile(
        bars, symbol, contract, plans, baseline,
        LOCKED_TRAIN_END, LOCKED_VALIDATION_END, config,
    )
    validation_candidate = evaluate_profile(
        bars, symbol, contract, plans, chosen,
        LOCKED_TRAIN_END, LOCKED_VALIDATION_END, config,
    )
    report["validation"] = {
        "baseline": validation_baseline,
        "candidate": validation_candidate,
    }
    report["validation_passed"] = outer_validation_passes(
        validation_candidate["summary"], validation_baseline["summary"]
    )
    return report


def run(
    symbols: Iterable[str],
    count: int,
    cache_dir: Path,
    workers: int,
    data_end_close: int,
) -> Dict[str, Any]:
    symbols = tuple(symbols)
    bars_by_symbol = {
        symbol: fetch_bars(symbol, count, cache_dir, end_close=data_end_close)
        for symbol in symbols
    }
    contracts = {symbol: fetch_contract(symbol, cache_dir) for symbol in symbols}
    config = BacktestConfig(
        initial_deposit=1_000,
        risk_pct=1,
        leverage=10,
        fee_bps=4,
        slippage_bps=2,
    )
    first = max(bars[0].ts for bars in bars_by_symbol.values()) + config.warmup_hours * HOUR_SECONDS
    tasks = [
        (symbol, bars_by_symbol[symbol], contracts[symbol], config, first)
        for symbol in symbols
    ]
    if workers <= 1:
        symbol_reports = [optimize_symbol(task) for task in tasks]
    else:
        with concurrent.futures.ProcessPoolExecutor(max_workers=min(workers, len(tasks))) as executor:
            symbol_reports = list(executor.map(optimize_symbol, tasks))

    all_validated = all(item["validation_passed"] for item in symbol_reports)
    validation_trades = sum(
        item["validation"]["candidate"]["summary"]["trades"]
        for item in symbol_reports
        if item["validation"] is not None
    )
    # The test is intentionally not implemented in this optimizer yet: it can
    # be opened only after all profiles pass and total validation has 20 trades.
    test_gate_ready = all_validated and validation_trades >= 20
    return {
        "protocol": {
            "symbols": symbols,
            "profiles": [asdict(profile) for profile in SYMBOL_PROFILES],
            "windows": {
                "selection": {"start": iso(first), "end": iso(INTERNAL_CONFIRMATION_START)},
                "confirmation": {"start": iso(INTERNAL_CONFIRMATION_START), "end": iso(LOCKED_TRAIN_END)},
                "validation": {"start": iso(LOCKED_TRAIN_END), "end": iso(LOCKED_VALIDATION_END)},
                "test": {"start": iso(LOCKED_VALIDATION_END), "end": iso(LOCKED_TEST_END)},
            },
            "selection_gate": "trades>=15, return>0, PF>1",
            "score": "return_pct - 0.5 * max_drawdown_pct",
            "confirmation_and_validation_gate": "trades>=5, return>0, PF>1, DD<=baseline, return>baseline",
            "portfolio_test_gate": "every symbol passes validation and combined validation trades>=20",
        },
        "symbols": {item["symbol"]: item for item in symbol_reports},
        "test_gate_ready": test_gate_ready,
        "test_opened": False,
    }


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Per-symbol UCB profile optimization")
    parser.add_argument("--symbols", nargs="+", default=["BTC_USDT", "ETH_USDT", "SOL_USDT"])
    parser.add_argument("--candles", type=int, default=25_000)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--cache-dir", type=Path, default=Path("/tmp/ucb-walk-forward-data"))
    parser.add_argument("--data-end", default="2026-08-07T11:00:00Z")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    data_end_close = int(
        datetime.fromisoformat(args.data_end.replace("Z", "+00:00")).timestamp()
    )
    report = run(
        args.symbols,
        args.candles,
        args.cache_dir,
        max(1, args.workers),
        data_end_close,
    )
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(payload + "\n")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
