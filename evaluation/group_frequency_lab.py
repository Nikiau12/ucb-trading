"""Offline 1D/4H signal-frequency comparison on an already exposed dataset.

This is a technical-candidate diagnostic, not an execution backtest, a strategy
approval, or a weekly signal guarantee. It reads verified historical captures
and never connects to an exchange, database, bot, or production service.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
from unittest.mock import patch

from evaluation import sector_entries as research
from evaluation.sector_data import CandleCapture, DAY, FOUR_HOURS, digest


VERSION = "group-frequency-lab-v1-2026-11-08"
WEEK = 7 * DAY


def one_day_trend(feature: dict) -> str:
    """Test one *closed* directional day instead of two; leave neutral unchanged.

    The existing EMA order, three-day EMA slope and ADX>=20 still apply. This
    changes exactly the consecutive-day confirmation gate, not 4H geometry.
    """
    daily, indicators = feature["daily"], feature["d"]
    if len(daily) < 4:
        return feature["regime"]
    close = daily[-1].c
    ema20, ema50, adx, atr = (indicators[key][-1] for key in ("ema20", "ema50", "adx", "atr"))
    previous_ema20 = indicators["ema20"][-4]
    if any(value is None or not math.isfinite(value) for value in (ema20, ema50, adx, atr, previous_ema20)):
        return feature["regime"]
    if atr > 0 and adx >= 20:
        if close > ema20 > ema50 and ema20 > previous_ema20:
            return "up"
        if close < ema20 < ema50 and ema20 < previous_ema20:
            return "down"
    return feature["regime"] if feature["regime"] == "neutral" else "transition"


def week_start(timestamp: int) -> str:
    instant = datetime.fromtimestamp(timestamp, timezone.utc)
    monday = (instant - timedelta(days=instant.weekday())).date()
    return monday.isoformat()


def full_weeks(start: int, end: int) -> list[str]:
    """Weeks with every 4H decision boundary from Monday through Sunday."""
    if start > end or start % FOUR_HOURS or end % FOUR_HOURS:
        raise ValueError("Unaligned or reversed scan window")
    first = datetime.fromtimestamp(start, timezone.utc)
    last = datetime.fromtimestamp(end, timezone.utc)
    monday = (first + timedelta(days=7 - first.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    if first.weekday() == 0 and first.hour == 0:
        monday = first
    result = []
    while monday + timedelta(days=7) - timedelta(seconds=FOUR_HOURS) <= last:
        result.append(monday.date().isoformat())
        monday += timedelta(days=7)
    return result


def summarize_frequency(plans: list[dict], start: int, end: int) -> dict:
    """Report raw and conservative distinct ideas, never predicted deliveries."""
    weeks = full_weeks(start, end)
    candidates = sorted(plans, key=lambda p: (p["signal_time"], p["symbol"], p["side"]))
    if any(p["signal_time"] < start or p["signal_time"] > end
           or p["signal_time"] % FOUR_HOURS for p in candidates):
        raise ValueError("Candidate outside aligned scan window")
    identity = [(p["symbol"], p["side"], p["signal_time"]) for p in candidates]
    if len(identity) != len(set(identity)):
        raise ValueError("Duplicate symbol/side/time candidate")
    by_market_time = Counter((p["symbol"], p["signal_time"]) for p in candidates)
    uncontested = [p for p in candidates if by_market_time[p["symbol"], p["signal_time"]] == 1]
    # This deliberately reserves the full pending plus maximum holding horizon.
    # It undercounts possible deliveries when a model trade would close sooner.
    blocked_until = defaultdict(int)
    distinct = []
    for plan in uncontested:
        symbol, signal_time = plan["symbol"], plan["signal_time"]
        if signal_time < blocked_until[symbol]:
            continue
        expiry = int(plan["entry_expiry_seconds"])
        holding = int(plan["max_holding_seconds"])
        if not 0 < expiry <= 8 * 3600 or not 0 < holding <= 96 * 3600:
            raise ValueError("Invalid candidate lifetime")
        distinct.append(plan)
        blocked_until[symbol] = signal_time + expiry + holding
    def counts(rows):
        weekly = Counter(week_start(p["signal_time"]) for p in rows)
        return {week: weekly[week] for week in weeks}
    raw_weekly, distinct_weekly = counts(candidates), counts(distinct)
    return {
        "technical_candidates": len(candidates),
        "same_time_conflict_candidates": len(candidates) - len(uncontested),
        "conservative_distinct_candidates": len(distinct),
        "full_week_count": len(weeks),
        "raw_per_full_week": raw_weekly,
        "conservative_distinct_per_full_week": distinct_weekly,
        "full_weeks_with_20_raw": sum(value >= 20 for value in raw_weekly.values()),
        "full_weeks_with_20_conservative_distinct": sum(value >= 20 for value in distinct_weekly.values()),
        "by_group_side_raw": dict(sorted(Counter(p["group"] + ":" + p["side"] for p in candidates).items())),
        "by_group_side_conservative_distinct": dict(sorted(Counter(
            p["group"] + ":" + p["side"] for p in distinct).items())),
        "by_symbol_raw": dict(sorted(Counter(p["symbol"] for p in candidates).items())),
    }


def load_development_inputs(root: Path, shortlist_path: Path):
    root, shortlist_path = Path(root), Path(shortlist_path)
    preflight = json.loads((root / "expanded-preflight.json").read_text())
    shortlist = json.loads(shortlist_path.read_text())
    decisions = json.loads((root / "entry-decisions.json").read_text())
    baseline = json.loads((root / "entry-candidates.json").read_text())
    config, mapping = research.load_entries()
    passports = research.load_passports()
    first_chunk = preflight["chunks"][0]
    source_hash = hashlib.sha256(Path(research.__file__).read_bytes()).hexdigest()
    first_assets = {row["symbol"]: row for row in first_chunk["assets"]}
    if (preflight.get("technical_candidates") != len(baseline)
            or preflight.get("decisions") != len(decisions)
            or first_chunk["implementation_sha256"]["sector_entries.py"] != source_hash
            or first_chunk["profile_sha256"] != digest(config)
            or first_chunk["shortlist_sha256"] != digest(shortlist)):
        raise ValueError("Frozen development baseline or implementation changed")
    previous_end = None
    for chunk in preflight["chunks"]:
        if (chunk["implementation_sha256"]["sector_entries.py"] != source_hash
                or chunk["profile_sha256"] != first_chunk["profile_sha256"]
                or chunk["shortlist_sha256"] != first_chunk["shortlist_sha256"]
                or {row["symbol"]: row for row in chunk["assets"]} != first_assets
                or (previous_end is not None and chunk["scan_start"] != previous_end + FOUR_HOURS)):
            raise ValueError("Development chunk provenance or continuity changed")
        previous_end = chunk["scan_end"]
    if (preflight["chunks"][0]["scan_start"] != preflight["scan_start"]
            or previous_end != preflight["scan_end"]
            or sum(chunk["decisions"] for chunk in preflight["chunks"]) != len(decisions)
            or sum(chunk["technical_candidates"] for chunk in preflight["chunks"]) != len(baseline)):
        raise ValueError("Development chunk totals changed")
    symbols = [row["symbol"] for row in shortlist["selected"]]
    if (len(symbols) != len(set(symbols)) or len(symbols) > 32
            or any(mapping.get(row["symbol"]) != row["group"] for row in shortlist["selected"])):
        raise ValueError("Shortlist identity mismatch")
    if any(row["status"] not in ("no_setup", "technical_candidate_not_admitted") for row in decisions):
        raise ValueError("Incomplete baseline market data")
    scan_start, scan_end = preflight["scan_start"], preflight["scan_end"]
    if (scan_start > scan_end or (scan_end - scan_start) % FOUR_HOURS
            or len(decisions) != len(symbols) * 2 * ((scan_end - scan_start) // FOUR_HOURS + 1)):
        raise ValueError("Baseline decision grid incomplete")
    decision_ids = {(row["symbol"], row["side"], row["time"]) for row in decisions}
    baseline_ids = {(row["symbol"], row["side"], row["signal_time"]) for row in baseline}
    if (len(decision_ids) != len(decisions) or len(baseline_ids) != len(baseline)
            or any((row["symbol"], row["side"], row["time"]) not in baseline_ids
                   for row in decisions if row["status"] == "technical_candidate_not_admitted")
            or sum(row["status"] == "technical_candidate_not_admitted" for row in decisions) != len(baseline)):
        raise ValueError("Baseline candidate identities inconsistent")
    tick_rows = first_assets
    markets, ticks, hashes = {}, {}, {}
    client = CandleCapture(root / "candles", collect=False)
    for symbol in symbols:
        bars, sha = client.load(symbol, preflight["data_start"], preflight["data_end"])
        if (sha != tick_rows[symbol]["candles_sha256"]
                or tick_rows[symbol].get("market_error")
                or any(b.ts - a.ts != FOUR_HOURS for a, b in zip(bars, bars[1:]))):
            raise ValueError("Incomplete or changed 4H capture: " + symbol)
        tick = float(tick_rows[symbol]["tick"])
        if not math.isfinite(tick) or tick <= 0:
            raise ValueError("Invalid diagnostic tick: " + symbol)
        markets[symbol], ticks[symbol], hashes[symbol] = bars, tick, sha
    return preflight, shortlist, decisions, baseline, config, mapping, passports, markets, ticks, hashes


def scan_one_day_trend(preflight, symbols, config, mapping, passports, markets, ticks):
    original_features = research.features
    def variant_features(bars, as_of):
        feature = original_features(bars, as_of)
        return {**feature, "regime": one_day_trend(feature)}
    plans, reasons = [], Counter()
    # Single-threaded patch is confined to this offline scan and restored on exit.
    with patch.object(research, "features", variant_features), patch.object(research, "load_entries", return_value=(config, mapping)):
        for as_of in range(preflight["scan_start"], preflight["scan_end"] + 1, FOUR_HOURS):
            cache = {}
            for symbol in symbols:
                for side in ("long", "short"):
                    result = research.candidate(symbol, side, markets, as_of=as_of,
                                                tick=ticks[symbol], passport=passports[symbol],
                                                _feature_cache=cache)
                    if result["status"] == "technical_candidate_not_admitted":
                        plans.append(result)
                    elif result["status"] == "no_setup":
                        reasons[result.get("reason", "unknown")] += 1
                    else:
                        raise ValueError("Variant scan has blocked or unexpected market data")
    return plans, dict(sorted(reasons.items()))


def compare(root: Path, shortlist_path: Path) -> dict:
    (preflight, shortlist, decisions, baseline, config, mapping, passports,
     markets, ticks, hashes) = load_development_inputs(root, shortlist_path)
    symbols = [row["symbol"] for row in shortlist["selected"]]
    variant, reasons = scan_one_day_trend(preflight, symbols, config, mapping, passports, markets, ticks)
    if len(variant) + sum(reasons.values()) != len(decisions):
        raise ValueError("Variant decision grid incomplete")
    start, end = preflight["scan_start"], preflight["scan_end"]
    baseline_ids = {(p["symbol"], p["side"], p["signal_time"]) for p in baseline}
    variant_ids = {(p["symbol"], p["side"], p["signal_time"]) for p in variant}
    return {
        "version": VERSION, "mode": "offline_frequency_diagnostic",
        "live_eligible": False, "independent_validation": False,
        "performance_or_profitability_established": False,
        "target_unique_signals_per_week": 20,
        "period": {"start": start, "end": end, "symbols": len(symbols),
                   "historical_universe_point_in_time_verified": False},
        "baseline": summarize_frequency(baseline, start, end),
        "one_day_trend": summarize_frequency(variant, start, end),
        "candidate_identity": {"shared": len(baseline_ids & variant_ids),
                               "added": len(variant_ids - baseline_ids),
                               "lost": len(baseline_ids - variant_ids)},
        "baseline_rejection_reasons": dict(sorted(Counter(
            row.get("reason", "unknown") for row in decisions if row["status"] == "no_setup").items())),
        "one_day_rejection_reasons": reasons,
        "provenance": {"baseline_decisions": len(decisions),
                       "source_4h_sha256": hashes,
                       "baseline_sha256": digest(baseline),
                       "rules_sha256": digest(config),
                       "diagnostic_implementation_sha256": hashlib.sha256(
                           Path(__file__).read_bytes()).hexdigest()},
        "limitations": [
            "27 previously selected representatives, not all 111 reviewed instruments",
            "Current contract tick and selected universe are not point-in-time historical evidence",
            "Technical candidates are not admitted, delivered or entered trades",
            "Conservative distinct count reserves the entire maximum holding horizon, not actual exits",
            "No historical order books, complete historical costs or independent validation",
            "The development period was already inspected; no profitability inference is permitted",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--shortlist", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = compare(args.root, args.shortlist)
    content = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content)
    else:
        print(content, end="")


if __name__ == "__main__":
    main()
