#!/usr/bin/env python3
"""Select a BTC profile by stability across four chronological windows."""
from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional

from trading.backtest import BacktestConfig, HOUR_SECONDS

from .run_symbol_optimization import (
    INTERNAL_CONFIRMATION_START,
    SYMBOL_PROFILES,
    build_plan_cache,
    confirmation_passes,
    evaluate_profile,
)
from .run_walk_forward import (
    LOCKED_TEST_END,
    LOCKED_TRAIN_END,
    LOCKED_VALIDATION_END,
    fetch_bars,
    fetch_contract,
    iso,
)


ROLLING_BOUNDARIES = (
    int(datetime(2023, 7, 1, 11, tzinfo=timezone.utc).timestamp()),
    int(datetime(2024, 3, 1, 11, tzinfo=timezone.utc).timestamp()),
    int(datetime(2024, 11, 1, 11, tzinfo=timezone.utc).timestamp()),
    INTERNAL_CONFIRMATION_START,
)


def stability_metrics(windows: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    summaries = tuple(windows)
    returns = [float(item["return_pct"]) for item in summaries]
    return {
        "windows": len(summaries),
        "positive_windows": sum(value > 0 for value in returns),
        "total_trades": sum(int(item["trades"]) for item in summaries),
        "mean_return_pct": statistics.fmean(returns),
        "median_return_pct": statistics.median(returns),
        "worst_return_pct": min(returns),
        "max_window_drawdown_pct": max(float(item["max_drawdown_pct"]) for item in summaries),
    }


def stability_eligible(metrics: Mapping[str, Any]) -> bool:
    return (
        metrics["positive_windows"] >= 3
        and metrics["total_trades"] >= 20
        and metrics["mean_return_pct"] > 0
    )


def stability_score(metrics: Mapping[str, Any]) -> float:
    return (
        float(metrics["mean_return_pct"])
        + 0.25 * float(metrics["worst_return_pct"])
        - 0.5 * float(metrics["max_window_drawdown_pct"])
    )


def run(count: int, cache_dir: Path, data_end_close: int) -> Dict[str, Any]:
    symbol = "BTC_USDT"
    bars = fetch_bars(symbol, count, cache_dir, end_close=data_end_close)
    contract = fetch_contract(symbol, cache_dir)
    config = BacktestConfig(
        initial_deposit=1_000,
        risk_pct=1,
        leverage=10,
        fee_bps=4,
        slippage_bps=2,
    )
    first = bars[0].ts + config.warmup_hours * HOUR_SECONDS
    boundaries = (first, *ROLLING_BOUNDARIES)
    plans = build_plan_cache(
        bars, symbol, contract, first, LOCKED_VALIDATION_END, config
    )

    profiles = []
    for profile in SYMBOL_PROFILES:
        windows = [
            evaluate_profile(
                bars, symbol, contract, plans, profile,
                start, end, config,
            )
            for start, end in zip(boundaries, boundaries[1:])
        ]
        profiles.append({
            "profile": profile,
            "windows": windows,
            "stability": stability_metrics(item["summary"] for item in windows),
        })

    eligible = [
        item for item in profiles
        if item["profile"].name != "baseline_060" and stability_eligible(item["stability"])
    ]
    selected = max(eligible, key=lambda item: stability_score(item["stability"])) if eligible else None
    report: Dict[str, Any] = {
        "protocol": {
            "symbol": symbol,
            "rolling_windows": [
                {"start": iso(start), "end": iso(end)}
                for start, end in zip(boundaries, boundaries[1:])
            ],
            "confirmation": {"start": iso(INTERNAL_CONFIRMATION_START), "end": iso(LOCKED_TRAIN_END)},
            "validation": {"start": iso(LOCKED_TRAIN_END), "end": iso(LOCKED_VALIDATION_END)},
            "test": {"start": iso(LOCKED_VALIDATION_END), "end": iso(LOCKED_TEST_END)},
            "selection_gate": ">=3/4 positive windows, >=20 total trades, mean return>0",
            "score": "mean return + 0.25*worst return - 0.5*max window drawdown",
        },
        "profiles": [
            {
                "profile": item["profile"].name,
                "windows": item["windows"],
                "stability": item["stability"],
            }
            for item in profiles
        ],
        "selected": selected["profile"].name if selected else None,
        "confirmation": None,
        "confirmation_passed": False,
        "validation": None,
        "validation_passed": False,
        "test_opened": False,
    }
    if selected is None:
        return report

    chosen = selected["profile"]
    baseline = SYMBOL_PROFILES[0]
    confirmation_baseline = evaluate_profile(
        bars, symbol, contract, plans, baseline,
        INTERNAL_CONFIRMATION_START, LOCKED_TRAIN_END, config,
    )
    confirmation_candidate = evaluate_profile(
        bars, symbol, contract, plans, chosen,
        INTERNAL_CONFIRMATION_START, LOCKED_TRAIN_END, config,
    )
    report["confirmation"] = {
        "baseline": confirmation_baseline,
        "candidate": confirmation_candidate,
    }
    report["confirmation_passed"] = confirmation_passes(
        confirmation_candidate["summary"], confirmation_baseline["summary"]
    )
    if not report["confirmation_passed"]:
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
    report["validation_passed"] = confirmation_passes(
        validation_candidate["summary"], validation_baseline["summary"]
    )
    return report


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="BTC rolling stability research")
    parser.add_argument("--candles", type=int, default=35_000)
    parser.add_argument("--cache-dir", type=Path, default=Path("/tmp/ucb-walk-forward-data"))
    parser.add_argument("--data-end", default="2026-08-07T11:00:00Z")
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
