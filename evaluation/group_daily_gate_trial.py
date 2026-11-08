"""Explain 1D rejections and test one frozen BTC-neutral exception offline.

This module reads only the already captured development window. It never uses
the unfinished independent period, credentials, Telegram, Railway or orders.
The variant is a technical-frequency hypothesis, not a production strategy.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from evaluation import sector_entries as research
from evaluation.group_frequency_lab import load_development_inputs, summarize_frequency
from evaluation.sector_data import DAY, digest


VERSION = "group-daily-gate-trial-v1-2026-11-08"
VARIANT_ID = "same_btc_group_allows_confirmed_asset_trend_when_btc_neutral"


def directed_day(feature, index):
    """Mirror the existing 1D direction formula; no unfinished candle."""
    daily, d = feature["daily"], feature["d"]
    if not -len(daily) <= index < len(daily):
        return "unknown"
    i = index if index >= 0 else len(daily)+index
    if i < 52:
        return "unknown"
    atr, e20, e50, adx = (d[key][i] for key in ("atr", "ema20", "ema50", "adx"))
    if any(value is None for value in (atr, e20, e50, adx)) or atr <= 0:
        return "unknown"
    if daily[i].c > e20 > e50 and e20 > d["ema20"][i-3] and adx >= 20:
        return "up"
    if daily[i].c < e20 < e50 and e20 < d["ema20"][i-3] and adx >= 20:
        return "down"
    return "other"


def rejection_cause(asset, btc, profile, side):
    """Classify the first failing daily gate, not speculate about trade PnL."""
    if side not in ("long", "short"):
        raise ValueError("Unknown direction")
    desired, opposite = (("up", "down") if side == "long" else ("down", "up"))
    family = profile[side]
    if family == "TR":
        family = "R" if asset["regime"] == "neutral" else "T"
    required = "neutral" if family == "R" else desired
    own = asset["regime"]
    if own != required:
        if own == "transition" and directed_day(asset, -1) == desired:
            return "asset_waiting_second_day"
        if own == "transition":
            return "asset_not_confirmed"
        return "asset_"+own+"_not_"+required
    if profile["btc"] == "none":
        return "daily_gate_passed"
    if btc is None or btc["regime"] not in ("up", "down", "neutral", "transition"):
        return "btc_context_missing"
    observed = btc["regime"]
    if profile["btc"] == "same" and observed != desired:
        return "btc_"+observed
    if profile["btc"] == "not_opposite" and observed == opposite:
        return "btc_opposite"
    return "daily_gate_passed"


def unconfirmed_flags(asset, profile, side):
    """Non-exclusive reasons for an unconfirmed own daily state."""
    d, daily = asset["d"], asset["daily"]
    atr, e20, e50, adx = (d[key][-1] for key in ("atr", "ema20", "ema50", "adx"))
    if any(value is None for value in (atr, e20, e50, adx)) or atr <= 0:
        return ["missing_daily_indicators"]
    family = profile[side]
    if family == "R":
        flags = []
        if adx >= 20:
            flags.append("range_adx_not_below_20")
        if abs(e20-e50) > .5*atr:
            flags.append("range_ema_spread_too_wide")
        return flags or ["range_other_confirmation"]
    sign = 1 if side == "long" else -1
    flags = []
    if sign*(daily[-1].c-e20) <= 0:
        flags.append("trend_price_wrong_side_of_ema20")
    if sign*(e20-e50) <= 0:
        flags.append("trend_ema_order_missing")
    if sign*(e20-d["ema20"][-4]) <= 0:
        flags.append("trend_ema20_slope_missing")
    if adx < 20:
        flags.append("trend_adx_below_20")
    return flags or ["trend_other_confirmation"]


def btc_neutral_variant_allowed(asset, btc, profile, side, family, *, baseline):
    """One predeclared exception; never permit an opposite/transition BTC."""
    if (profile["btc"] == "same" and btc is not None
            and btc["regime"] == "neutral"
            and asset["regime"] == ("up" if side == "long" else "down")
            and family != "R"):
        return True
    return baseline(asset, btc, profile, side, family)


def analyze(root: Path, shortlist: Path):
    (preflight, selected, decisions, baseline, config, mapping, passports,
     markets, ticks, hashes) = load_development_inputs(root, shortlist)
    daily_cache = {}

    def daily_feature(symbol, as_of):
        day_start = as_of//DAY*DAY
        key = symbol, day_start
        if key not in daily_cache:
            full = research.features(markets[symbol], day_start)
            daily_cache[key] = {name: full[name] for name in ("regime", "daily", "d")}
        return daily_cache[key]

    causes, group_causes, detail_flags, opportunities = Counter(), defaultdict(Counter), Counter(), []
    unique_days = defaultdict(set)
    for row in decisions:
        if row["status"] != "no_setup" or row.get("reason") != "daily_regime":
            continue
        symbol, side, as_of = (row[key] for key in ("symbol", "side", "time"))
        group = mapping[symbol]
        profile = config["groups"][group]
        asset = daily_feature(symbol, as_of)
        btc = daily_feature("BTC_USDT", as_of) if profile["btc"] != "none" else None
        cause = rejection_cause(asset, btc, profile, side)
        if cause == "daily_gate_passed":
            raise ValueError("Daily rejection provenance disagrees with current rules")
        causes[cause] += 1
        group_causes[group+":"+side][cause] += 1
        unique_days[cause].add((symbol, side, as_of//DAY))
        if cause == "asset_not_confirmed":
            detail_flags.update(unconfirmed_flags(asset, profile, side))
        if cause == "btc_neutral" and profile["btc"] == "same":
            opportunities.append(row)
    if sum(causes.values()) != sum(row.get("reason") == "daily_regime" for row in decisions):
        raise ValueError("Daily rejection grid incomplete")

    original_regime_allowed = research.regime_allowed
    def variant_regime_allowed(asset, btc, profile, side, family):
        return btc_neutral_variant_allowed(asset, btc, profile, side, family,
                                           baseline=original_regime_allowed)

    # The patch is confined to this single-threaded offline scan and restored.
    variant, variant_reasons = [], Counter()
    with patch.object(research, "regime_allowed", variant_regime_allowed):
        for row in opportunities:
            symbol, side, as_of = (row[key] for key in ("symbol", "side", "time"))
            result = research.candidate(symbol, side, markets, as_of=as_of,
                                        tick=ticks[symbol], passport=passports[symbol])
            if result["status"] == "technical_candidate_not_admitted":
                variant.append(result)
            elif result["status"] == "no_setup":
                variant_reasons[result["reason"]] += 1
            else:
                raise ValueError("Variant encountered blocked market data")
    if len(variant)+sum(variant_reasons.values()) != len(opportunities):
        raise ValueError("Variant accounting incomplete")
    baseline_ids = {(p["symbol"], p["side"], p["signal_time"]) for p in baseline}
    variant_ids = {(p["symbol"], p["side"], p["signal_time"]) for p in variant}
    if baseline_ids & variant_ids or len(variant_ids) != len(variant):
        raise ValueError("New daily-gate candidate duplicated an old one")
    start, end = preflight["scan_start"], preflight["scan_end"]
    return {
        "version": VERSION, "mode": "offline_daily_gate_diagnostic_and_frequency_only",
        "variant_id": VARIANT_ID, "live_eligible": False,
        "independent_validation": False, "profitability_established": False,
        "period": {"start": start, "end": end,
                   "symbols": len(selected["selected"]),
                   "day_context_count": len(daily_cache)},
        "daily_rejections": sum(causes.values()),
        "daily_rejection_causes": dict(sorted(causes.items())),
        "daily_rejection_unique_symbol_side_days": {
            key: len(value) for key, value in sorted(unique_days.items())},
        "asset_not_confirmed_nonexclusive_flags": dict(sorted(detail_flags.items())),
        "daily_rejection_by_group_side": {
            key: dict(sorted(value.items())) for key, value in sorted(group_causes.items())},
        "variant_decisions_examined": len(opportunities),
        "variant_rejection_reasons": dict(sorted(variant_reasons.items())),
        "baseline": summarize_frequency(baseline, start, end),
        "variant_additional": summarize_frequency(variant, start, end),
        "combined_technical_only": summarize_frequency(baseline+variant, start, end),
        "source": {"base_rules_sha256": digest(config),
                   "original_candidates_sha256": digest(baseline),
                   "four_hour_sha256": hashes,
                   "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
        "limitations": [
            "Old development window was already inspected; no PnL or strategy selection here",
            "Current passports and contract ticks are not point-in-time historical evidence",
            "Technical candidates are not admitted, filled or user-delivered signals",
            "Conservative distinct count reserves the full pending plus holding horizon",
            "The frozen independent period is not read or analyzed",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--shortlist", type=Path, required=True)
    parser.add_argument("--brief", action="store_true")
    args = parser.parse_args()
    full_report = analyze(args.root, args.shortlist)
    report = full_report
    if args.brief:
        report = {key: full_report[key] for key in (
            "version", "mode", "period", "daily_rejections", "daily_rejection_causes",
            "daily_rejection_unique_symbol_side_days",
            "asset_not_confirmed_nonexclusive_flags", "variant_decisions_examined",
            "variant_rejection_reasons", "limitations")}
        report["frequency"] = {
            key: {name: full_report[key][name] for name in (
                "technical_candidates", "conservative_distinct_candidates",
                "by_group_side_raw", "full_weeks_with_20_conservative_distinct")}
            for key in ("baseline", "variant_additional", "combined_technical_only")}
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
