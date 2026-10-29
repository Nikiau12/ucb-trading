#!/usr/bin/env python3
"""Shadow-score frozen 4H/1D profiles on new BingX candles.

The forward window starts after the last research timestamp.  This module uses
public market data only and never places an order or reads private API keys.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence

from trading.analytics.structure import Bar
from trading.backtest import BacktestConfig, HOUR_SECONDS, run_backtest
from trading.bingx_snapshot import (
    futures_contract_detail,
    http_get,
    to_bingx_symbol,
)
from trading.higher_timeframe_setups import (
    BTC_4H_DIAGNOSTIC_CANDIDATES,
    ETH_4H_1D_SETUPS,
    SOL_4H_DIAGNOSTIC_CANDIDATES,
    htf_plan_builder,
)


FOUR_HOURS = 4 * HOUR_SECONDS
FORWARD_START = int(datetime(2026, 8, 7, 8, tzinfo=timezone.utc).timestamp())
WARMUP_START = int(datetime(2026, 3, 1, 0, tzinfo=timezone.utc).timestamp())
MINIMUM_FORWARD_TRADES = 20


FROZEN_PROFILES = {
    "BTC_USDT": BTC_4H_DIAGNOSTIC_CANDIDATES,
    # All six profiles were declared before the forward window.  None may be
    # added, relaxed or renamed after forward results are observed.
    "ETH_USDT": ETH_4H_1D_SETUPS,
    "SOL_USDT": SOL_4H_DIAGNOSTIC_CANDIDATES,
}


def utc_iso(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat().replace("+00:00", "Z")


def last_completed_4h(now: Optional[int] = None) -> int:
    current = int(time.time()) if now is None else int(now)
    return current // FOUR_HOURS * FOUR_HOURS


def normalize_rows(rows: Sequence[Any]) -> list[Bar]:
    normalized: Dict[int, Bar] = {}
    for item in rows:
        if isinstance(item, dict):
            timestamp = int(item["time"])
            values = (
                item["open"], item["high"], item["low"], item["close"], item.get("volume", 0)
            )
        elif isinstance(item, list) and len(item) >= 6:
            timestamp = int(item[0])
            values = (item[1], item[2], item[3], item[4], item[5])
        else:
            continue
        if timestamp > 10_000_000_000:
            timestamp //= 1_000
        normalized[timestamp] = Bar(
            ts=timestamp,
            o=float(values[0]),
            h=float(values[1]),
            l=float(values[2]),
            c=float(values[3]),
            v=float(values[4]),
        )
    return sorted(normalized.values(), key=lambda bar: bar.ts)


def validate_continuity(bars: Sequence[Bar], start: int, end: int) -> None:
    filtered = [bar for bar in bars if start <= bar.ts and bar.ts + FOUR_HOURS <= end]
    if not filtered:
        raise RuntimeError("BingX returned no completed 4H candles")
    missing = [
        left.ts + FOUR_HOURS
        for left, right in zip(filtered, filtered[1:])
        if right.ts - left.ts != FOUR_HOURS
    ]
    if missing:
        sample = ", ".join(utc_iso(value) for value in missing[:3])
        raise RuntimeError(f"BingX 4H history contains gaps, first missing candles: {sample}")


def _cache_path(cache_dir: Path, symbol: str, start: int, end: int) -> Path:
    return cache_dir / f"{symbol.lower()}-4h-{start}-{end}.json"


def fetch_bingx_4h(
    symbol: str,
    start: int,
    end: int,
    cache_dir: Path,
) -> list[Bar]:
    """Fetch native 4H candles backwards in API-sized pages."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _cache_path(cache_dir, symbol, start, end)
    if path.exists():
        bars = [Bar(**item) for item in json.loads(path.read_text())]
        validate_continuity(bars, start, end)
        return [bar for bar in bars if start <= bar.ts and bar.ts + FOUR_HOURS <= end]

    collected: Dict[int, Bar] = {}
    cursor_end = end
    while cursor_end > start:
        payload = http_get(
            "/openApi/swap/v3/quote/klines",
            {
                "symbol": to_bingx_symbol(symbol),
                "interval": "4h",
                "startTime": start * 1_000,
                "endTime": cursor_end * 1_000,
                "limit": 1_440,
            },
            timeout=30,
        )
        page = normalize_rows(payload.get("data", []))
        page = [bar for bar in page if start <= bar.ts and bar.ts + FOUR_HOURS <= end]
        if not page:
            break
        for bar in page:
            collected[bar.ts] = bar
        earliest = page[0].ts
        if earliest <= start:
            break
        if earliest >= cursor_end:
            raise RuntimeError("BingX pagination did not move backwards")
        cursor_end = earliest

    bars = sorted(collected.values(), key=lambda bar: bar.ts)
    validate_continuity(bars, start, end)
    path.write_text(json.dumps([asdict(bar) for bar in bars], separators=(",", ":")))
    return bars


def source_digest(bars: Sequence[Bar]) -> str:
    payload = json.dumps([asdict(bar) for bar in bars], separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def fee_bps(contract: Mapping[str, Any]) -> float:
    raw = contract.get("raw") or {}
    rate = float(raw.get("takerFeeRate") or 0.0005)
    return rate * 10_000


def profile_status(summary: Mapping[str, Any]) -> str:
    if int(summary["trades"]) < MINIMUM_FORWARD_TRADES:
        return "insufficient_sample"
    if float(summary["return_pct"]) <= 0 or float(summary.get("average_r") or 0) <= 0:
        return "rejected"
    if (summary.get("profit_factor") or 0) <= 1:
        return "rejected"
    return "forward_gate_passed"


def evaluate_symbol(
    symbol: str,
    bars: Sequence[Bar],
    contract: Dict[str, Any],
    evaluation_end: int,
) -> Dict[str, Any]:
    config = BacktestConfig(
        initial_deposit=1_000,
        risk_pct=1,
        leverage=10,
        fee_bps=fee_bps(contract),
        slippage_bps=2,
        entry_delay_bars=1,
        entry_expiry_bars=3,
        max_holding_bars=84,
        warmup_hours=24 * 120,
        decision_interval_hours=4,
        bar_interval_hours=4,
    )
    profiles = []
    for setup in FROZEN_PROFILES[symbol]:
        result = run_backtest(
            bars,
            symbol=symbol,
            config=config,
            contract_rules=contract,
            plan_builder=htf_plan_builder(setup),
            evaluation_start=FORWARD_START,
            evaluation_end=evaluation_end,
        )
        summary = dict(result["summary"])
        profiles.append({
            "profile": setup.name,
            "status": profile_status(summary),
            "summary": summary,
            "unfilled_orders": result["unfilled_orders"],
            "trades": result["trades"],
        })
    return {
        "symbol": symbol,
        "source_candles": len(bars),
        "source_first_open": utc_iso(bars[0].ts),
        "source_last_close": utc_iso(bars[-1].ts + FOUR_HOURS),
        "source_sha256": source_digest(bars),
        "taker_fee_bps_per_fill": config.fee_bps,
        "profiles": profiles,
    }


def run(cache_dir: Path, evaluation_end: int) -> Dict[str, Any]:
    if evaluation_end <= FORWARD_START:
        raise ValueError("evaluation_end must be after the frozen forward start")
    assets = {}
    for symbol in FROZEN_PROFILES:
        bars = fetch_bingx_4h(symbol, WARMUP_START, evaluation_end, cache_dir)
        contract = futures_contract_detail(symbol)
        assets[symbol] = evaluate_symbol(symbol, bars, contract, evaluation_end)
    return {
        "protocol": {
            "exchange": "BingX USDT-M perpetual futures",
            "mode": "offline shadow validation; no orders",
            "signal_timeframes": ["4h", "1d"],
            "hourly_signal_features": False,
            "forward_start": utc_iso(FORWARD_START),
            "forward_end": utc_iso(evaluation_end),
            "daily_context": "completed 1D candles only",
            "first_entry": "next 4H candle after signal",
            "ambiguous_intrabar_policy": "stop_first",
            "slippage_bps_per_fill": 2,
            "minimum_forward_trades": MINIMUM_FORWARD_TRADES,
            "profile_mutation_allowed": False,
        },
        "assets": assets,
        "production_change_recommended": False,
    }


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="BingX native 4H/1D forward validation")
    parser.add_argument("--cache-dir", type=Path, default=Path("/tmp/ucb-bingx-4h-data"))
    parser.add_argument("--end", help="exclusive UTC close, defaults to latest completed 4H")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    evaluation_end = (
        int(datetime.fromisoformat(args.end.replace("Z", "+00:00")).timestamp())
        if args.end
        else last_completed_4h()
    )
    report = run(args.cache_dir, evaluation_end)
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(payload + "\n")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
