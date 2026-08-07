#!/usr/bin/env python3
"""Pre-registered train/validation/test research for the production strategy.

The test period is evaluated only when the training-selected candidate passes
the validation gate. Market data is cached outside the repository by default.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import time
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

import requests

from trading.analytics.structure import Bar
from trading.backtest import BacktestConfig, HOUR_SECONDS, run_backtest


MEXC_API = "https://contract.mexc.com/api/v1/contract"
LOCKED_TRAIN_END = int(datetime(2025, 12, 24, 11, tzinfo=timezone.utc).timestamp())
LOCKED_VALIDATION_END = int(datetime(2026, 4, 16, 11, tzinfo=timezone.utc).timestamp())
LOCKED_TEST_END = int(datetime(2026, 8, 7, 11, tzinfo=timezone.utc).timestamp())


@dataclass(frozen=True)
class Candidate:
    name: str
    min_confidence: float
    require_trend_alignment: bool = False
    allowed_regimes: tuple[str, ...] = ("trend", "range")
    min_adx: Optional[float] = None
    max_adx: Optional[float] = None
    require_rsi_momentum: bool = False
    require_1h_confirmation: bool = False
    min_entry_distance_atr: Optional[float] = None
    max_entry_distance_atr: Optional[float] = None
    allowed_sides: tuple[str, ...] = ("long", "short")


# Intentionally small and declared in source before validation/test is opened.
INITIAL_CANDIDATES = (
    Candidate("baseline_060", 0.60),
    Candidate("confidence_065", 0.65),
    Candidate("confidence_070", 0.70),
    Candidate("aligned_060", 0.60, require_trend_alignment=True),
)

# Iteration 2 was frozen after the initial training-only diagnostic showed that
# range entries were the weakest setup class. Validation remained unopened.
SETUP_V2_CANDIDATES = (
    Candidate("baseline_060", 0.60),
    Candidate("trend_adx22", 0.60, allowed_regimes=("trend",), min_adx=22),
    Candidate("trend_adx25", 0.60, allowed_regimes=("trend",), min_adx=25),
    Candidate("trend_adx30", 0.60, allowed_regimes=("trend",), min_adx=30),
    Candidate(
        "trend_adx25_rsi_momentum",
        0.60,
        allowed_regimes=("trend",),
        min_adx=25,
        require_rsi_momentum=True,
    ),
)

# Iteration 3 was frozen after training-only diagnostics found that planned
# entries 0.10-0.50 ATR from market were the only stable positive distance band.
SETUP_V3_CANDIDATES = (
    Candidate("baseline_060", 0.60),
    Candidate(
        "trend_near_entry",
        0.60,
        allowed_regimes=("trend",),
        min_entry_distance_atr=0.10,
        max_entry_distance_atr=0.50,
    ),
    Candidate(
        "trend_near_entry_adx_cap",
        0.60,
        allowed_regimes=("trend",),
        max_adx=40,
        min_entry_distance_atr=0.10,
        max_entry_distance_atr=0.50,
    ),
    Candidate(
        "trend_near_entry_rsi",
        0.60,
        allowed_regimes=("trend",),
        require_rsi_momentum=True,
        min_entry_distance_atr=0.10,
        max_entry_distance_atr=0.50,
    ),
    Candidate(
        "trend_near_entry_adx_cap_rsi",
        0.60,
        allowed_regimes=("trend",),
        max_adx=40,
        require_rsi_momentum=True,
        min_entry_distance_atr=0.10,
        max_entry_distance_atr=0.50,
    ),
)

# Iteration 4 tests a closed-candle bounce confirmation instead of blindly
# leaving a limit at the 4h EMA. It was frozen before validation was opened.
SETUP_V4_CANDIDATES = (
    Candidate("baseline_060", 0.60),
    Candidate(
        "trend_1h_confirmation",
        0.60,
        allowed_regimes=("trend",),
        require_1h_confirmation=True,
    ),
    Candidate(
        "trend_1h_confirmation_near",
        0.60,
        allowed_regimes=("trend",),
        require_1h_confirmation=True,
        min_entry_distance_atr=0.10,
        max_entry_distance_atr=0.50,
    ),
    Candidate(
        "trend_1h_confirmation_rsi",
        0.60,
        allowed_regimes=("trend",),
        require_rsi_momentum=True,
        require_1h_confirmation=True,
    ),
    Candidate(
        "trend_1h_confirmation_near_rsi",
        0.60,
        allowed_regimes=("trend",),
        require_rsi_momentum=True,
        require_1h_confirmation=True,
        min_entry_distance_atr=0.10,
        max_entry_distance_atr=0.50,
    ),
)

CANDIDATE_SETS = {
    "initial": INITIAL_CANDIDATES,
    "setup_v2": SETUP_V2_CANDIDATES,
    "setup_v3": SETUP_V3_CANDIDATES,
    "setup_v4": SETUP_V4_CANDIDATES,
}


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


def fetch_bars(
    symbol: str,
    count: int,
    cache_dir: Path,
    end_close: Optional[int] = None,
) -> List[Bar]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"-{end_close}" if end_close is not None else ""
    cache_path = cache_dir / f"{symbol.lower()}-{count}-1h{suffix}.json"
    if cache_path.exists():
        rows = json.loads(cache_path.read_text())
        return [Bar(**row) for row in rows]

    now = int(time.time()) // HOUR_SECONDS * HOUR_SECONDS
    end = (end_close or now) - HOUR_SECONDS
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
    side = str((plan.get("primary") or {}).get("side") or plan.get("side") or "").lower()
    expected = "up" if side == "long" else "down" if side == "short" else ""
    if side not in candidate.allowed_sides:
        return False
    trend = plan.get("trend") or {}
    if trend.get("regime") not in candidate.allowed_regimes:
        return False
    if candidate.require_trend_alignment and not (
        expected and trend.get("1d") == expected and trend.get("4h") == expected
    ):
        return False

    reasons = list((plan.get("primary") or {}).get("reasons") or [])
    if candidate.min_adx is not None:
        adx = _reason_number(reasons, "adx4h≈")
        if adx is None or adx < candidate.min_adx:
            return False
    if candidate.max_adx is not None:
        adx = _reason_number(reasons, "adx4h≈")
        if adx is None or adx >= candidate.max_adx:
            return False
    if candidate.require_rsi_momentum:
        rsi = _reason_number(reasons, "rsi1h≈")
        if rsi is None or (side == "long" and rsi < 50) or (side == "short" and rsi > 50):
            return False
    if candidate.require_1h_confirmation:
        momentum = next(
            (reason.removeprefix("momentum1h=") for reason in reasons if reason.startswith("momentum1h=")),
            "neutral",
        )
        if momentum != expected:
            return False
    entry_distance = _reason_number(reasons, "entry_dist_ATR4h=")
    if candidate.min_entry_distance_atr is not None and (
        entry_distance is None or entry_distance < candidate.min_entry_distance_atr
    ):
        return False
    if candidate.max_entry_distance_atr is not None and (
        entry_distance is None or entry_distance > candidate.max_entry_distance_atr
    ):
        return False
    return True


def _reason_number(reasons: Iterable[str], prefix: str) -> Optional[float]:
    for reason in reasons:
        if reason.startswith(prefix):
            try:
                return float(reason[len(prefix):])
            except ValueError:
                return None
    return None


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


def _evaluate_task(args: tuple[Any, ...]) -> Dict[str, Any]:
    return evaluate(*args)


def evaluate_candidates(
    bars_by_symbol: Mapping[str, List[Bar]],
    contracts: Mapping[str, Dict[str, Any]],
    candidates: Iterable[Candidate],
    start: int,
    end: int,
    config: BacktestConfig,
    workers: int,
) -> List[Dict[str, Any]]:
    candidates = tuple(candidates)
    tasks = [(bars_by_symbol, contracts, candidate, start, end, config) for candidate in candidates]
    if workers <= 1:
        return [_evaluate_task(task) for task in tasks]
    with concurrent.futures.ProcessPoolExecutor(max_workers=min(workers, len(tasks))) as executor:
        return list(executor.map(_evaluate_task, tasks))


def training_eligible(summary: Mapping[str, Any]) -> bool:
    required_positive = math.ceil(2 * summary["symbols_total"] / 3)
    required_trades = max(40, 10 * summary["symbols_total"])
    return (
        summary["trades"] >= required_trades
        and summary["net_pnl"] > 0
        and summary["symbols_positive"] >= required_positive
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


def run(
    symbols: Iterable[str],
    count: int,
    cache_dir: Path,
    *,
    candidate_set: str = "setup_v2",
    workers: int = 1,
    data_end_close: Optional[int] = None,
) -> Dict[str, Any]:
    symbols = tuple(symbols)
    bars_by_symbol = {
        symbol: fetch_bars(symbol, count, cache_dir, end_close=data_end_close)
        for symbol in symbols
    }
    contracts = {symbol: fetch_contract(symbol, cache_dir) for symbol in symbols}
    config = BacktestConfig(initial_deposit=1_000, risk_pct=1, leverage=10, fee_bps=4, slippage_bps=2)

    first = max(bars[0].ts for bars in bars_by_symbol.values()) + config.warmup_hours * HOUR_SECONDS
    end = min(bars[-1].ts for bars in bars_by_symbol.values()) + HOUR_SECONDS
    if candidate_set in {"setup_v3", "setup_v4"}:
        train_end = LOCKED_TRAIN_END
        validation_end = LOCKED_VALIDATION_END
        end = min(end, LOCKED_TEST_END)
        if not first < train_end < validation_end < end:
            raise ValueError("Data does not cover the locked research windows")
    else:
        usable_hours = (end - first) // HOUR_SECONDS
        train_end = first + int(usable_hours * 0.60) * HOUR_SECONDS
        validation_end = first + int(usable_hours * 0.80) * HOUR_SECONDS
    windows = {
        "training": (first, train_end),
        "validation": (train_end, validation_end),
        "test": (validation_end, end),
    }

    candidates = CANDIDATE_SETS[candidate_set]
    training = evaluate_candidates(
        bars_by_symbol, contracts, candidates, *windows["training"], config, workers
    )
    eligible = [item for item in training if training_eligible(item["summary"])]
    selected = max(eligible, key=lambda item: training_score(item["summary"])) if eligible else None

    report: Dict[str, Any] = {
        "protocol": {
            "symbols": symbols,
            "candidate_set": candidate_set,
            "candles_per_symbol": count,
            "split": (
                "locked chronological windows with expanded training"
                if candidate_set in {"setup_v3", "setup_v4"}
                else "60/20/20 chronological after warmup"
            ),
            "windows": {name: {"start": iso(value[0]), "end": iso(value[1])} for name, value in windows.items()},
            "training_gate": "trades>=max(40,10*symbols), net_pnl>0, >=2/3 positive symbols",
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

    baseline_candidate = candidates[0]
    chosen = next(candidate for candidate in candidates if candidate.name == selected["candidate"]["name"])
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
    parser.add_argument("--candidate-set", choices=tuple(CANDIDATE_SETS), default="setup_v2")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument(
        "--data-end",
        help="Fixed ISO-8601 close time for the last candle (recommended for reproducibility)",
    )
    parser.add_argument("--cache-dir", type=Path, default=Path("/tmp/ucb-walk-forward-data"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    data_end_close = None
    if args.data_end:
        data_end_close = int(
            datetime.fromisoformat(args.data_end.replace("Z", "+00:00")).timestamp()
        )
    report = run(
        args.symbols,
        args.candles,
        args.cache_dir,
        candidate_set=args.candidate_set,
        workers=max(1, args.workers),
        data_end_close=data_end_close,
    )
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(payload + "\n")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
