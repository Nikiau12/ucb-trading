#!/usr/bin/env python3
"""Run a reproducible product-quality evaluation against live MEXC data.

This evaluates data availability, plan invariants, latency, symbol
normalization, and personalized risk calculations. It does not evaluate or
claim trading profitability.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence


ROOT = Path(__file__).resolve().parents[1]
TRADING_DIR = ROOT / "trading"
sys.path.insert(0, str(TRADING_DIR))
sys.path.insert(0, str(ROOT))

import mexc_snapshot  # noqa: E402
import trade_plan  # noqa: E402
from miniapp.app import normalize_usdt_symbol  # noqa: E402


SYMBOLS = [
    "BTC_USDT",
    "ETH_USDT",
    "SOL_USDT",
    "XRP_USDT",
    "DOGE_USDT",
    "ADA_USDT",
    "BNB_USDT",
    "LTC_USDT",
    "LINK_USDT",
    "AVAX_USDT",
    "DOT_USDT",
    "TRX_USDT",
    "BCH_USDT",
    "SUI_USDT",
    "PEPE_USDT",
    "HYPE_USDT",
    "TAO_USDT",
    "ZEC_USDT",
    "NEAR_USDT",
    "APT_USDT",
]

DEFAULT_PROFILE = {
    "deposit": 3_000.0,
    "risk_pct": 1.0,
    "lev": 20.0,
    "margin": "cross",
}


def percentile(values: Sequence[float], percentile_value: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = (len(ordered) - 1) * percentile_value
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)


def finite_positive(value: Any) -> bool:
    try:
        return math.isfinite(float(value)) and float(value) > 0
    except (TypeError, ValueError):
        return False


def scenario_violations(scenario: Dict[str, Any], profile: Dict[str, float]) -> List[str]:
    issues: List[str] = []
    side = scenario.get("side")
    entry = scenario.get("entry")
    stop = scenario.get("stop")
    targets = scenario.get("tps") or []

    for field in ("entry", "stop", "qty", "risk_usdt", "margin_need"):
        if not finite_positive(scenario.get(field)):
            issues.append(f"{field}_not_positive")

    if len(targets) != 2 or not all(finite_positive(item.get("price")) for item in targets):
        issues.append("targets_invalid")
        return issues

    tp1 = float(targets[0]["price"])
    tp2 = float(targets[1]["price"])
    if side == "long" and not (float(stop) < float(entry) < tp1 <= tp2):
        issues.append("long_price_order_invalid")
    if side == "short" and not (float(stop) > float(entry) > tp1 >= tp2):
        issues.append("short_price_order_invalid")

    expected_risk = profile["deposit"] * profile["risk_pct"] / 100.0
    if not math.isclose(float(scenario["risk_usdt"]), expected_risk, rel_tol=1e-9):
        issues.append("risk_amount_mismatch")

    implied_risk = float(scenario["qty"]) * abs(float(entry) - float(stop))
    if not math.isclose(implied_risk, expected_risk, rel_tol=1e-8):
        issues.append("position_size_mismatch")

    expected_margin = float(scenario["qty"]) * float(entry) / profile["lev"]
    if not math.isclose(float(scenario["margin_need"]), expected_margin, rel_tol=1e-8):
        issues.append("margin_mismatch")

    allocation = sum(float(item.get("pct", 0)) for item in targets)
    if not math.isclose(allocation, 1.0, rel_tol=1e-9):
        issues.append("target_allocation_mismatch")
    return issues


def evaluate_symbol(symbol: str) -> Dict[str, Any]:
    total_started = time.perf_counter()
    snapshot_started = time.perf_counter()
    snapshot = mexc_snapshot.build_snapshot_with_fallback(symbol)
    snapshot_ms = (time.perf_counter() - snapshot_started) * 1_000

    plan_started = time.perf_counter()
    plan = trade_plan.make_plan(snapshot, **DEFAULT_PROFILE)
    plan_ms = (time.perf_counter() - plan_started) * 1_000

    result: Dict[str, Any] = {
        "symbol": symbol,
        "status": "skip" if plan.get("side") == "skip" else "plan",
        "used_cache": bool(plan.get("used_cache")),
        "snapshot_ms": round(snapshot_ms, 2),
        "plan_compute_ms": round(plan_ms, 2),
        "total_ms": round((time.perf_counter() - total_started) * 1_000, 2),
        "violations": [],
    }
    if result["status"] == "plan":
        primary = plan["primary"]
        result["side"] = primary["side"]
        result["confidence"] = round(float(primary["confidence"]), 4)
        result["violations"] = scenario_violations(primary, DEFAULT_PROFILE)
    else:
        result["confidence"] = round(float(plan.get("confidence", 0)), 4)
        result["skip_reason"] = (plan.get("reasons") or ["unknown"])[0]
    return result


def evaluate_symbols(symbols: Iterable[str], workers: int) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(evaluate_symbol, symbol): symbol for symbol in symbols}
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                output.append(future.result())
            except Exception as exc:
                output.append(
                    {
                        "symbol": symbol,
                        "status": "error",
                        "used_cache": False,
                        "violations": ["evaluation_error"],
                        "error_type": type(exc).__name__,
                    }
                )
    return sorted(output, key=lambda item: symbols.index(item["symbol"]))


def evaluate_normalization(symbols: Sequence[str]) -> Dict[str, Any]:
    valid_cases = []
    for symbol in symbols:
        base = symbol.removesuffix("_USDT")
        valid_cases.extend(
            [
                (symbol, symbol),
                (f"{base}/usdt", symbol),
                (f"{base.lower()}-usdt:usdt", symbol),
            ]
        )
    invalid_cases = ["BTC_EUR", "ETH/USD", "", "USDT", "BTCGBP"]
    failures = [
        {"input": value, "expected": expected, "actual": normalize_usdt_symbol(value)}
        for value, expected in valid_cases
        if normalize_usdt_symbol(value) != expected
    ]
    invalid_failures = [
        {"input": value, "actual": normalize_usdt_symbol(value)}
        for value in invalid_cases
        if normalize_usdt_symbol(value) is not None
    ]
    total = len(valid_cases) + len(invalid_cases)
    passed = total - len(failures) - len(invalid_failures)
    return {
        "cases": total,
        "passed": passed,
        "pass_rate_pct": round(100 * passed / total, 2),
        "failures": failures + invalid_failures,
    }


def evaluate_risk_matrix(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    scenarios = []
    failures = []
    for deposit in (100.0, 1_000.0, 10_000.0):
        for risk_pct in (0.5, 1.0, 2.0):
            for leverage in (1.0, 10.0, 20.0, 50.0):
                profile = {
                    "deposit": deposit,
                    "risk_pct": risk_pct,
                    "lev": leverage,
                    "margin": "cross",
                }
                plan = trade_plan.make_plan(snapshot, **profile)
                if plan.get("side") == "skip":
                    failures.append(
                        {
                            "deposit": deposit,
                            "risk_pct": risk_pct,
                            "leverage": leverage,
                            "reason": "reference_symbol_skipped",
                        }
                    )
                    continue
                issues = scenario_violations(plan["primary"], profile)
                scenarios.append(profile)
                if issues:
                    failures.append({**profile, "violations": issues})
    total = 3 * 3 * 4
    return {
        "reference_symbol": snapshot["symbol"],
        "cases": total,
        "passed": total - len(failures),
        "pass_rate_pct": round(100 * (total - len(failures)) / total, 2),
        "failures": failures,
    }


def make_summary(
    symbol_results: Sequence[Dict[str, Any]],
    normalization: Dict[str, Any],
    risk_matrix: Dict[str, Any],
) -> Dict[str, Any]:
    completed = [item for item in symbol_results if item["status"] != "error"]
    plans = [item for item in symbol_results if item["status"] == "plan"]
    valid_plans = [item for item in plans if not item["violations"]]
    errors = [item for item in symbol_results if item["status"] == "error"]
    total_latencies = [item["total_ms"] for item in completed]
    compute_latencies = [item["plan_compute_ms"] for item in completed]
    return {
        "symbols_requested": len(symbol_results),
        "symbols_completed": len(completed),
        "symbols_error": len(errors),
        "plans_generated": len(plans),
        "safe_skips": len(completed) - len(plans),
        "valid_plans": len(valid_plans),
        "plan_validity_pct": round(100 * len(valid_plans) / len(plans), 2) if plans else 0.0,
        "fresh_data_pct": round(
            100 * sum(not item["used_cache"] for item in completed) / len(completed),
            2,
        )
        if completed
        else 0.0,
        "latency_ms": {
            "median_total": round(statistics.median(total_latencies), 2) if total_latencies else 0.0,
            "p90_total": round(percentile(total_latencies, 0.90), 2),
            "median_compute": round(statistics.median(compute_latencies), 2) if compute_latencies else 0.0,
            "p90_compute": round(percentile(compute_latencies, 0.90), 2),
        },
        "normalization_pass_rate_pct": normalization["pass_rate_pct"],
        "risk_matrix_pass_rate_pct": risk_matrix["pass_rate_pct"],
    }


def write_markdown(payload: Dict[str, Any], output_path: Path) -> None:
    summary = payload["summary"]
    rows = "\n".join(
        "| {symbol} | {status} | {confidence} | {total} | {cache} | {result} |".format(
            symbol=item["symbol"],
            status=item["status"],
            confidence=item.get("confidence", "—"),
            total=item.get("total_ms", "—"),
            cache="yes" if item.get("used_cache") else "no",
            result="pass" if not item.get("violations") and item["status"] != "error" else "fail",
        )
        for item in payload["symbol_results"]
    )
    text = f"""# UCB Trading — Evaluation Report

Run: `{payload["run_id"]}`  
Generated: {payload["generated_at"]}  
Market source: live MEXC Futures API

## Scope

This evaluation measures product correctness, robustness, and latency. It does
not measure or claim signal profitability.

## Results

| Metric | Result |
|---|---:|
| Symbols completed | {summary["symbols_completed"]}/{summary["symbols_requested"]} |
| Plans generated | {summary["plans_generated"]} |
| Safe skips | {summary["safe_skips"]} |
| Valid generated plans | {summary["valid_plans"]}/{summary["plans_generated"]} ({summary["plan_validity_pct"]}%) |
| Fresh live data | {summary["fresh_data_pct"]}% |
| Full analysis latency, median | {summary["latency_ms"]["median_total"]} ms |
| Full analysis latency, p90 | {summary["latency_ms"]["p90_total"]} ms |
| Local plan computation, median | {summary["latency_ms"]["median_compute"]} ms |
| Symbol normalization | {summary["normalization_pass_rate_pct"]}% |
| Risk matrix | {summary["risk_matrix_pass_rate_pct"]}% |

## Test set

| Symbol | Output | Confidence | Total ms | Cache | Invariants |
|---|---|---:|---:|---|---|
{rows}

## Correctness checks

A generated plan passes only when:

- entry, stop, targets, quantity, risk amount, and required margin are finite
  and positive;
- price ordering is valid for the selected long or short direction;
- quantity × stop distance equals the configured risk amount;
- required margin matches quantity × entry ÷ leverage;
- TP1 and TP2 allocations sum to 100%.

The risk matrix covers 36 combinations: three deposits, three risk percentages,
and four leverage values. Symbol normalization covers 65 valid and invalid
input formats.

## Reproduce

```bash
python -m pip install -r requirements-dev.txt
python evaluation/run_evaluation.py
```

Raw machine-readable output: `docs/evaluation-results.json`.

## Limitations

- Results are a point-in-time measurement and live-market latency will vary.
- A safe `skip` is accepted when filters reject a setup; it is not counted as a
  generated plan.
- The evaluation does not backtest returns or estimate trading profitability.
- Telegram production delivery latency is outside this local evaluation.
"""
    output_path.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--json-output", default="docs/evaluation-results.json")
    parser.add_argument("--report-output", default="docs/EVALUATION_REPORT.md")
    args = parser.parse_args()

    run_started = time.perf_counter()
    symbol_results = evaluate_symbols(SYMBOLS, max(1, args.workers))

    reference_symbol = next(
        (item["symbol"] for item in symbol_results if item["status"] == "plan"),
        None,
    )
    if reference_symbol:
        reference_snapshot = mexc_snapshot.build_snapshot_with_fallback(reference_symbol)
        risk_matrix = evaluate_risk_matrix(reference_snapshot)
    else:
        risk_matrix = {
            "reference_symbol": None,
            "cases": 36,
            "passed": 0,
            "pass_rate_pct": 0.0,
            "failures": [{"reason": "no_reference_plan"}],
        }

    normalization = evaluate_normalization(SYMBOLS)
    summary = make_summary(symbol_results, normalization, risk_matrix)
    generated_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "run_id": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "generated_at": generated_at,
        "duration_seconds": round(time.perf_counter() - run_started, 2),
        "methodology": {
            "symbols": SYMBOLS,
            "workers": max(1, args.workers),
            "profile": DEFAULT_PROFILE,
            "profitability_evaluated": False,
        },
        "summary": summary,
        "normalization": normalization,
        "risk_matrix": risk_matrix,
        "symbol_results": symbol_results,
    }

    json_path = ROOT / args.json_output
    report_path = ROOT / args.report_output
    json_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_markdown(payload, report_path)
    print(json.dumps(summary, indent=2))
    return 1 if summary["symbols_error"] or summary["plan_validity_pct"] < 100 else 0


if __name__ == "__main__":
    raise SystemExit(main())
