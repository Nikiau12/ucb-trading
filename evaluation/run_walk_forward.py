#!/usr/bin/env python3
"""Pre-registered train/validation/test research for the production strategy.

The test period is evaluated only when the training-selected candidate passes
the validation gate. Market data is cached outside the repository by default.
"""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

import requests

from trading.analytics.structure import Bar
from trading.backtest import BacktestConfig, HOUR_SECONDS, run_backtest


MEXC_API = "https://contract.mexc.com/api/v1/contract"


@dataclass(frozen=True)
class Candidate:
    name: str
    min_confidence: float
    require_trend_alignment: bool = False


# Intentionally small and declared in source before validation/test is opened.
CANDIDATES = (
    Candidate("baseline_060", 0.60),
    Candidate("confidence_065", 0.65),
    Candidate("confidence_070", 0.70),
    Candidate("aligned_060", 0.60, require_trend_alignment=True),
)


def _request_json(url: str, *, attempts: int = 4) -> Dict[str, Any]:
    for attempt in range(attempts):
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            payload = response.json()
            if not payload.get("success"):
                raise RuntimeError(f"MEXC error: {payload.get('code')} {payload.get('message')}")
            return payload
        except (requests.RequestException, ValueError, RuntimeError):
            if attempt + 1 == attempts:
                raise
            time.sleep(2 ** attempt)
    raise AssertionError("unreachable")


def fetch_bars(symbol: str, count: int, cache_dir: Path) -> List[Bar]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{symbol.lower()}-{count}-1h.json"
    if cache_path.exists():
        rows = json.loads(cache_path.read_text())
        return [Bar(**row) for row in rows]

    now = int(time.time()) // HOUR_SECONDS * HOUR_SECONDS
    end = now - HOUR_SECONDS
    collected: Dict[int, Bar] = {}
    while len(collected) < count:
        remaining = count - len(collected)
        chunk_size = min(1_900, remaining)
        start = end - (chunk_size - 1) * HOUR_SECONDS
        url = (
            f"{MEXC_API}/kline/{symbol}?interval=Min60"
            f"&start={start}&end={end}"
        )
        data = _request_json(url)["data"]
        for index, timestamp in enumerate(data.get("time") or []):
            collected[int(timestamp)] = Bar(
                ts=int(timestamp),
                o=float(data["open"][index]),
                h=float(data["high"][index]),
                l=float(data["low"][index]),
                c=float(data["close"][index]),
                v=float(data["vol"][index]),
            )
        if not data.get("time"):
            raise RuntimeError(f"MEXC returned no candles for {symbol} at {start}-{end}")
        end = start - HOUR_SECONDS
        time.sleep(0.35)

    bars = sorted(collected.values(), key=lambda bar: bar.ts)[-count:]
    cache_path.write_text(json.dumps([asdict(bar) for bar in bars]))
    return bars


def fetch_contract(symbol: str, cache_dir: Path) -> Dict[str, Any]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{symbol.lower()}-contract.json"
    if not cache_path.exists():
        payload = _request_json(f"{MEXC_API}/detail?symbol={symbol}")["data"]
        cache_path.write_text(json.dumps(payload, indent=2))
    return json.loads(cache_path.read_text())


def accepts_candidate(plan: Mapping[str, Any], candidate: Candidate) -> bool:
    if not candidate.require_trend_alignment:
        return True
    side = str((plan.get("primary") or {}).get("side") or plan.get("side") or "").lower()
    expected = "up" if side == "long" else "down" if side == "short" else ""
    trend = plan.get("trend") or {}
    return bool(expected) and trend.get("1d") == expected and trend.get("4h") == expected


def aggregate(results: Mapping[str, Dict[str, Any]], initial_deposit: float) -> Dict[str, Any]:
    trades = []
    for symbol, result in results.items():
        trades.extend({**trade, "symbol": symbol} for trade in result["trades"])
    trades.sort(key=lambda trade: (trade["exit_time"], trade["symbol"]))
    starting_equity = initial_deposit * len(results)
    equity = peak = starting_equity
    max_drawdown = gross_profit = gross_loss = 0.0
    for trade in trades:
        pnl = float(trade["net_pnl"])
        equity += pnl
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, (peak - equity) / peak if peak else 0.0)
        if pnl > 0:
            gross_profit += pnl
        elif pnl < 0:
            gross_loss += abs(pnl)
    wins = sum(float(trade["net_pnl"]) > 0 for trade in trades)
    return {
        "trades": len(trades),
        "wins": wins,
        "win_rate_pct": 100 * wins / len(trades) if trades else 0.0,
        "net_pnl": equity - starting_equity,
        "return_pct": 100 * (equity / starting_equity - 1),
        "max_drawdown_pct": 100 * max_drawdown,
        "profit_factor": gross_profit / gross_loss if gross_loss else None,
        "fees_paid": sum(float(trade["fees"]) for trade in trades),
        "symbols_positive": sum(result["summary"]["net_pnl"] > 0 for result in results.values()),
        "symbols_total": len(results),
    }


def evaluate(
    bars_by_symbol: Mapping[str, List[Bar]],
    contracts: Mapping[str, Dict[str, Any]],
    candidate: Candidate,
    start: int,
    end: int,
    base_config: BacktestConfig,
) -> Dict[str, Any]:
    config = replace(base_config, min_confidence=candidate.min_confidence)
    results = {}
    for symbol, bars in bars_by_symbol.items():
        results[symbol] = run_backtest(
            bars,
            symbol=symbol,
            config=config,
            contract_rules=contracts[symbol],
            plan_filter=lambda plan, c=candidate: accepts_candidate(plan, c),
            evaluation_start=start,
            evaluation_end=end,
        )
    return {
        "candidate": asdict(candidate),
        "summary": aggregate(results, base_config.initial_deposit),
        "symbols": {symbol: result["summary"] for symbol, result in results.items()},
    }


def training_eligible(summary: Mapping[str, Any]) -> bool:
    return (
        summary["trades"] >= 40
        and summary["net_pnl"] > 0
        and summary["symbols_positive"] >= 2
    )


def training_score(summary: Mapping[str, Any]) -> float:
    return float(summary["return_pct"]) - 0.5 * float(summary["max_drawdown_pct"])


def validation_passes(candidate: Mapping[str, Any], baseline: Mapping[str, Any]) -> bool:
    return (
        candidate["trades"] >= 20
        and candidate["return_pct"] > 0
        and (candidate["profit_factor"] or 0) > 1
        and candidate["max_drawdown_pct"] <= baseline["max_drawdown_pct"]
        and candidate["return_pct"] >= baseline["return_pct"] + 0.25
    )


def final_gate_passes(candidate: Mapping[str, Any], baseline: Mapping[str, Any]) -> bool:
    return (
        candidate["trades"] >= 20
        and candidate["return_pct"] > 0
        and (candidate["profit_factor"] or 0) > 1
        and candidate["max_drawdown_pct"] <= baseline["max_drawdown_pct"]
        and candidate["return_pct"] > baseline["return_pct"]
    )


def iso(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


def run(symbols: Iterable[str], count: int, cache_dir: Path) -> Dict[str, Any]:
    symbols = tuple(symbols)
    bars_by_symbol = {symbol: fetch_bars(symbol, count, cache_dir) for symbol in symbols}
    contracts = {symbol: fetch_contract(symbol, cache_dir) for symbol in symbols}
    config = BacktestConfig(initial_deposit=1_000, risk_pct=1, leverage=10, fee_bps=4, slippage_bps=2)

    first = max(bars[0].ts for bars in bars_by_symbol.values()) + config.warmup_hours * HOUR_SECONDS
    end = min(bars[-1].ts for bars in bars_by_symbol.values()) + HOUR_SECONDS
    usable_hours = (end - first) // HOUR_SECONDS
    train_end = first + int(usable_hours * 0.60) * HOUR_SECONDS
    validation_end = first + int(usable_hours * 0.80) * HOUR_SECONDS
    windows = {
        "training": (first, train_end),
        "validation": (train_end, validation_end),
        "test": (validation_end, end),
    }

    training = [
        evaluate(bars_by_symbol, contracts, candidate, *windows["training"], config)
        for candidate in CANDIDATES
    ]
    eligible = [item for item in training if training_eligible(item["summary"])]
    selected = max(eligible, key=lambda item: training_score(item["summary"])) if eligible else None

    report: Dict[str, Any] = {
        "protocol": {
            "symbols": symbols,
            "candles_per_symbol": count,
            "split": "60/20/20 chronological after warmup",
            "windows": {name: {"start": iso(value[0]), "end": iso(value[1])} for name, value in windows.items()},
            "training_gate": "trades>=40, net_pnl>0, >=2/3 positive symbols",
            "selection_score": "return_pct - 0.5 * max_drawdown_pct",
            "validation_gate": "trades>=20, return>0, PF>1, DD<=baseline, return>=baseline+0.25pp",
            "test_gate": "trades>=20, return>0, PF>1, DD<=baseline, return>baseline",
            "friction": {"fee_bps_per_fill": 4, "slippage_bps_per_fill": 2},
        },
        "training": training,
        "selected": selected["candidate"] if selected else None,
        "validation": None,
        "validation_passed": False,
        "test_opened": False,
        "test": None,
        "production_change_recommended": False,
    }
    if selected is None or selected["candidate"]["name"] == "baseline_060":
        return report

    baseline_candidate = CANDIDATES[0]
    chosen = next(candidate for candidate in CANDIDATES if candidate.name == selected["candidate"]["name"])
    validation_baseline = evaluate(bars_by_symbol, contracts, baseline_candidate, *windows["validation"], config)
    validation_candidate = evaluate(bars_by_symbol, contracts, chosen, *windows["validation"], config)
    passed = validation_passes(validation_candidate["summary"], validation_baseline["summary"])
    report["validation"] = {"baseline": validation_baseline, "candidate": validation_candidate}
    report["validation_passed"] = passed
    if not passed:
        return report

    # This is the only branch allowed to inspect the untouched test window.
    report["test_opened"] = True
    test_baseline = evaluate(bars_by_symbol, contracts, baseline_candidate, *windows["test"], config)
    test_candidate = evaluate(bars_by_symbol, contracts, chosen, *windows["test"], config)
    report["test"] = {"baseline": test_baseline, "candidate": test_candidate}
    report["production_change_recommended"] = final_gate_passes(
        test_candidate["summary"], test_baseline["summary"]
    )
    return report


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Strict UCB train/validation/test research")
    parser.add_argument("--symbols", nargs="+", default=["BTC_USDT", "ETH_USDT", "SOL_USDT"])
    parser.add_argument("--candles", type=int, default=15_000)
    parser.add_argument("--cache-dir", type=Path, default=Path("/tmp/ucb-walk-forward-data"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = run(args.symbols, args.candles, args.cache_dir)
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(payload + "\n")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
