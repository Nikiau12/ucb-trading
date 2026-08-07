#!/usr/bin/env python3
"""Diagnose rejected native-4H BTC/SOL profiles without opening final data.

The already observed confirmation window is used only to explain why the
frozen profiles failed. It must not be reused as independent evidence for a
replacement profile.
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence

from trading.analytics.indicators import OHLC, atr, ema
from trading.backtest import BacktestConfig, HOUR_SECONDS, build_snapshot
from trading.higher_timeframe_setups import (
    BTC_4H_DIAGNOSTIC_CANDIDATES,
    BTC_4H_1D_SETUPS,
    SOL_4H_DIAGNOSTIC_CANDIDATES,
    SOL_4H_1D_SETUPS,
    htf_features,
    htf_plan_builder,
)
from trading.trade_plan import parse_bars

from .run_higher_timeframe_research import (
    CONFIRMATION_END,
    FOUR_HOURS,
    SELECTION_BOUNDARIES,
    build_plan_cache,
    evaluate,
    to_closed_4h,
)
from .run_walk_forward import fetch_bars, fetch_contract, iso
from .run_btc_stability import stability_metrics


PROFILE_NAMES = {
    "BTC_USDT": "btc_4h_pullback_long",
    "SOL_USDT": "sol_4h_pullback_both",
}


def _signed(value: float, side: str) -> float:
    return value if side == "long" else -value


def _trend_age(closes: Sequence[float], fast_period: int = 20, slow_period: int = 50) -> int:
    _, fast = ema(closes, fast_period, return_series=True)
    _, slow = ema(closes, slow_period, return_series=True)
    if not fast or not slow or fast[-1] is None or slow[-1] is None:
        return 0
    current_up = fast[-1] > slow[-1]
    age = 0
    for fast_value, slow_value in zip(reversed(fast), reversed(slow)):
        if fast_value is None or slow_value is None or (fast_value > slow_value) != current_up:
            break
        age += 1
    return age


def trade_features(
    bars_4h: Sequence[Any],
    symbol: str,
    contract: Mapping[str, Any],
    trade: Mapping[str, Any],
) -> Dict[str, Any]:
    signal_time = int(trade["signal_time"])
    snapshot = build_snapshot(
        symbol,
        bars_4h,
        signal_time,
        dict(contract),
        source_interval_hours=4,
    )
    features = htf_features(snapshot)
    if features is None:
        raise ValueError(f"Missing 4H/1D features at {signal_time}")
    bars_1d = parse_bars(snapshot, "kline_1d")[-120:]
    latest_4h = features["bars_4h"][-1]
    closes_1d = [bar.c for bar in bars_1d]
    ema20_1d, _ = ema(closes_1d, 20, return_series=False)
    atr_1d, _ = atr(
        [OHLC(bar.o, bar.h, bar.l, bar.c) for bar in bars_1d],
        14,
        return_series=False,
    )
    if ema20_1d is None or atr_1d is None:
        raise ValueError(f"Missing daily indicators at {signal_time}")

    side = str(trade["side"])
    candle_range = max(latest_4h.h - latest_4h.l, 1e-12)
    body = abs(latest_4h.c - latest_4h.o)
    atr_4h = float(features["atr_4h"])
    # Compare the closed 4H decision price with indicators built exclusively
    # from completed daily candles. This matches the candidate filter exactly.
    signed_daily_extension = _signed((latest_4h.c - ema20_1d) / atr_1d, side)
    signed_4h_extension = _signed(
        (latest_4h.c - float(features["ema20_4h"])) / atr_4h,
        side,
    )
    pullback_depth = (
        (float(features["ema20_4h"]) - latest_4h.l) / atr_4h
        if side == "long"
        else (latest_4h.h - float(features["ema20_4h"])) / atr_4h
    )
    return {
        **dict(trade),
        "signal_time_iso": iso(signal_time),
        "entry_time_iso": iso(int(trade["entry_time"])),
        "exit_time_iso": iso(int(trade["exit_time"])),
        "adx_4h": round(float(features["adx_4h"]), 4),
        "atr_4h_pct": round(100 * atr_4h / latest_4h.c, 4),
        "daily_trend_age_bars": _trend_age(closes_1d),
        "daily_extension_atr": round(signed_daily_extension, 4),
        "close_4h_extension_atr": round(signed_4h_extension, 4),
        "pullback_depth_atr": round(pullback_depth, 4),
        "trigger_body_ratio": round(body / candle_range, 4),
        "volume_ratio": features["volume_ratio"],
    }


def _mean(rows: Sequence[Mapping[str, Any]], key: str) -> Optional[float]:
    values = [float(row[key]) for row in rows if row.get(key) is not None]
    return round(statistics.mean(values), 4) if values else None


def diagnostic_summary(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    winners = [row for row in rows if float(row["net_pnl"]) > 0]
    losers = [row for row in rows if float(row["net_pnl"]) <= 0]

    def cohort(items: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
        return {
            "trades": len(items),
            "mean_r": _mean(items, "r_multiple"),
            "mean_holding_4h_bars": _mean(items, "holding_bars"),
            "mean_adx_4h": _mean(items, "adx_4h"),
            "mean_atr_4h_pct": _mean(items, "atr_4h_pct"),
            "mean_daily_trend_age_bars": _mean(items, "daily_trend_age_bars"),
            "mean_daily_extension_atr": _mean(items, "daily_extension_atr"),
            "mean_close_4h_extension_atr": _mean(items, "close_4h_extension_atr"),
            "mean_pullback_depth_atr": _mean(items, "pullback_depth_atr"),
            "mean_trigger_body_ratio": _mean(items, "trigger_body_ratio"),
        }

    return {
        "all": cohort(rows),
        "winners": cohort(winners),
        "losers": cohort(losers),
        "by_side": dict(Counter(str(row["side"]) for row in rows)),
        "exit_reasons": dict(Counter(str(row["exit_reason"]) for row in rows)),
    }


def diagnose_asset(
    symbol: str,
    bars_4h: Sequence[Any],
    contract: Dict[str, Any],
    setup: Any,
    config: BacktestConfig,
) -> Dict[str, Any]:
    first = bars_4h[0].ts + config.warmup_hours * HOUR_SECONDS
    plans = build_plan_cache(
        bars_4h,
        symbol,
        contract,
        htf_plan_builder(setup),
        first,
        CONFIRMATION_END,
        config,
    )
    selection = evaluate(
        bars_4h,
        symbol,
        contract,
        plans,
        first,
        SELECTION_BOUNDARIES[-1],
        config,
    )
    confirmation = evaluate(
        bars_4h,
        symbol,
        contract,
        plans,
        SELECTION_BOUNDARIES[-1],
        CONFIRMATION_END,
        config,
    )
    selection_rows = [
        trade_features(bars_4h, symbol, contract, trade) for trade in selection["trades"]
    ]
    confirmation_rows = [
        trade_features(bars_4h, symbol, contract, trade) for trade in confirmation["trades"]
    ]
    return {
        "symbol": symbol,
        "profile": setup.name,
        "selection": {
            "window": {"start": iso(first), "end": iso(SELECTION_BOUNDARIES[-1])},
            "backtest": selection["summary"],
            "diagnostics": diagnostic_summary(selection_rows),
            "trades": selection_rows,
        },
        "confirmation": {
            "window": {
                "start": iso(SELECTION_BOUNDARIES[-1]),
                "end": iso(CONFIRMATION_END),
            },
            "status": "rejection_diagnosis_only_not_reusable_as_proof",
            "backtest": confirmation["summary"],
            "diagnostics": diagnostic_summary(confirmation_rows),
            "trades": confirmation_rows,
        },
    }


def explore_candidates(
    symbol: str,
    bars_4h: Sequence[Any],
    contract: Dict[str, Any],
    setups: Sequence[Any],
    config: BacktestConfig,
) -> list[Dict[str, Any]]:
    """Evaluate pre-registered candidates on selection data only."""
    first = bars_4h[0].ts + config.warmup_hours * HOUR_SECONDS
    boundaries = (first, *SELECTION_BOUNDARIES)
    results = []
    for setup in setups:
        plans = build_plan_cache(
            bars_4h,
            symbol,
            contract,
            htf_plan_builder(setup),
            first,
            SELECTION_BOUNDARIES[-1],
            config,
        )
        windows = [
            evaluate(bars_4h, symbol, contract, plans, start, end, config)["summary"]
            for start, end in zip(boundaries, boundaries[1:])
        ]
        aggregate = evaluate(
            bars_4h,
            symbol,
            contract,
            plans,
            first,
            SELECTION_BOUNDARIES[-1],
            config,
        )["summary"]
        results.append({
            "setup": setup.name,
            "status": "exploratory_selection_only_requires_new_forward_confirmation",
            "windows": windows,
            "stability": stability_metrics(windows),
            "aggregate": aggregate,
        })
    return results


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
        "SOL_USDT": SOL_4H_1D_SETUPS,
    }
    candidates = {
        "BTC_USDT": BTC_4H_DIAGNOSTIC_CANDIDATES,
        "SOL_USDT": SOL_4H_DIAGNOSTIC_CANDIDATES,
    }
    assets = {}
    for symbol, setups in libraries.items():
        profile_name = PROFILE_NAMES[symbol]
        setup = next(item for item in setups if item.name == profile_name)
        bars_1h = fetch_bars(symbol, count, cache_dir, end_close=data_end_close)
        bars_4h = to_closed_4h(bars_1h, data_end_close)
        contract = fetch_contract(symbol, cache_dir)
        assets[symbol] = diagnose_asset(symbol, bars_4h, contract, setup, config)
        assets[symbol]["replacement_candidates"] = explore_candidates(
            symbol, bars_4h, contract, candidates[symbol], config
        )
    return {
        "protocol": {
            "signal_timeframes": ["4h", "1d"],
            "final_test_opened": False,
            "confirmation_use": "diagnosis_of_rejected_profiles_only",
            "warning": "Any replacement profile requires a new independent forward window.",
        },
        "assets": assets,
    }


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Diagnose rejected 4H + 1D profiles")
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
