#!/usr/bin/env python3
"""Research a frozen mean-reversion profile for ETH range regimes."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from trading.backtest import BacktestConfig, HOUR_SECONDS

from .run_symbol_optimization import (
    INTERNAL_CONFIRMATION_START,
    build_plan_cache,
    confirmation_passes,
    evaluate_profile,
    profile_score,
    selection_eligible,
)
from .run_walk_forward import (
    Candidate,
    LOCKED_TEST_END,
    LOCKED_TRAIN_END,
    LOCKED_VALIDATION_END,
    fetch_bars,
    fetch_contract,
    iso,
)


PRODUCTION_BASELINE = Candidate("production_baseline", 0.60)
ETH_RANGE_PROFILES = (
    Candidate("eth_range", 0.60, allowed_regimes=("range",)),
    Candidate(
        "eth_range_near",
        0.60,
        allowed_regimes=("range",),
        max_entry_distance_atr=0.50,
    ),
    Candidate(
        "eth_range_reversal",
        0.60,
        allowed_regimes=("range",),
        require_candle_direction=True,
    ),
    Candidate(
        "eth_range_reversal_near",
        0.60,
        allowed_regimes=("range",),
        require_candle_direction=True,
        max_entry_distance_atr=0.50,
    ),
    Candidate(
        "eth_range_reversal_rsi",
        0.60,
        allowed_regimes=("range",),
        require_candle_direction=True,
        long_rsi_max=45,
        short_rsi_min=55,
    ),
    Candidate(
        "eth_range_reversal_rsi_near",
        0.60,
        allowed_regimes=("range",),
        require_candle_direction=True,
        long_rsi_max=45,
        short_rsi_min=55,
        max_entry_distance_atr=0.50,
    ),
    Candidate("eth_range_long", 0.60, allowed_regimes=("range",), allowed_sides=("long",)),
    Candidate("eth_range_short", 0.60, allowed_regimes=("range",), allowed_sides=("short",)),
)


def run(count: int, cache_dir: Path, data_end_close: int) -> Dict[str, Any]:
    symbol = "ETH_USDT"
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
    plans = build_plan_cache(
        bars, symbol, contract, first, LOCKED_VALIDATION_END, config
    )
    selection = [
        evaluate_profile(
            bars, symbol, contract, plans, profile,
            first, INTERNAL_CONFIRMATION_START, config,
        )
        for profile in ETH_RANGE_PROFILES
    ]
    eligible = [item for item in selection if selection_eligible(item["summary"])]
    selected = max(eligible, key=lambda item: profile_score(item["summary"])) if eligible else None
    report: Dict[str, Any] = {
        "protocol": {
            "symbol": symbol,
            "profiles": [asdict(profile) for profile in ETH_RANGE_PROFILES],
            "windows": {
                "selection": {"start": iso(first), "end": iso(INTERNAL_CONFIRMATION_START)},
                "confirmation": {"start": iso(INTERNAL_CONFIRMATION_START), "end": iso(LOCKED_TRAIN_END)},
                "validation": {"start": iso(LOCKED_TRAIN_END), "end": iso(LOCKED_VALIDATION_END)},
                "test": {"start": iso(LOCKED_VALIDATION_END), "end": iso(LOCKED_TEST_END)},
            },
            "selection_gate": "trades>=15, return>0, PF>1",
            "confirmation_validation_gate": "trades>=5, return>0, PF>1, DD<=production baseline, return>production baseline",
        },
        "selection": selection,
        "selected": selected["profile"] if selected else None,
        "confirmation": None,
        "confirmation_passed": False,
        "validation": None,
        "validation_passed": False,
        "test_opened": False,
    }
    if selected is None:
        return report

    chosen = next(profile for profile in ETH_RANGE_PROFILES if profile.name == selected["profile"]["name"])
    confirmation_baseline = evaluate_profile(
        bars, symbol, contract, plans, PRODUCTION_BASELINE,
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
        bars, symbol, contract, plans, PRODUCTION_BASELINE,
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
    parser = argparse.ArgumentParser(description="ETH range-profile research")
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
