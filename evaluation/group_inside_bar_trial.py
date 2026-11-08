"""Research-only inside-bar trend entry on previously rejected 4H decisions.

This is one predeclared entry hypothesis for trend-bound group sides, not a
replacement for the frozen profile or proof of trade quality. It uses only
already closed 1D/4H bars, preserves every upstream baseline gate, and does
not score outcomes, collect data, send messages or place orders.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

from evaluation import sector_entries as research
from evaluation.group_frequency_lab import load_development_inputs, summarize_frequency
from evaluation.sector_data import FOUR_HOURS, digest, write_json


VERSION = "group-inside-bar-trial-v1-2026-11-08"


def inside_bar_plan(feature: dict, side: str, tick: float, rv_min: float) -> dict | None:
    """A compact 4H pause followed by stop-entry beyond its mother bar."""
    bars, indicators = feature["bars"], feature["h"]
    if len(bars) < 61 or side not in ("long", "short") or not math.isfinite(tick) or tick <= 0:
        return None
    mother, signal, before_mother = bars[-2], bars[-1], bars[-3]
    atr = indicators["atr"][-1]
    ema20, ema50, adx = (indicators[key][-1] for key in ("ema20", "ema50", "adx"))
    if any(value is None or not math.isfinite(value) for value in (atr, ema20, ema50, adx)) or atr <= 0:
        return None
    sign = 1 if side == "long" else -1
    width = mother.h - mother.l
    if (not .8 * atr <= width <= 2 * atr
            or (mother.h <= before_mother.h and mother.l >= before_mother.l)
            or signal.h > mother.h or signal.l < mother.l
            or signal.h - signal.l > .75 * width
            or signal.v > mother.v
            or adx < 25 or sign * (ema20 - ema50) <= 0
            or sign * (signal.c - ema20) <= 0
            or sign * (signal.c - signal.o) <= 0
            or research.relative_volume(bars, len(bars) - 2) < rv_min):
        return None
    close_location = (signal.c - mother.l) / width
    if (side == "long" and close_location < .7) or (side == "short" and close_location > .3):
        return None
    entry = mother.h + tick if sign == 1 else mother.l - tick
    stop = mother.l - .25 * atr if sign == 1 else mother.h + .25 * atr
    entry = research.round_price(entry, tick, sign == 1)
    stop = research.round_price(stop, tick, sign == -1)
    risk = sign * (entry - stop)
    if min(entry, stop) <= 0 or not .75 * atr <= risk <= 2.5 * atr:
        return None
    tp1 = research.round_price(entry + sign * 1.5 * risk, tick, sign == -1)
    tp2 = research.round_price(entry + sign * 3 * risk, tick, sign == -1)
    if min(tp1, tp2) <= 0 or not (sign * (tp1 - entry) > 0 and sign * (tp2 - tp1) > 0):
        return None
    prior = bars[-61:-1]
    obstacle = max(b.h for b in prior) if sign == 1 else min(b.l for b in prior)
    if (len(research.spaced_touches(prior, obstacle, .25 * atr, sign == 1)) >= 3
            and 0 < sign * (obstacle - entry) < sign * (tp1 - entry)):
        return None
    return {
        "family": "I", "side": side, "entry": entry, "stop": stop,
        "tp1": tp1, "tp2": tp2, "risk_price": risk, "atr4h": atr,
        "entry_type": "stop", "trigger_price_type": "contract_last",
        "signal_time": signal.ts + FOUR_HOURS,
        "entry_expiry_seconds": 2 * FOUR_HOURS,
        "mother_bar_time": mother.ts,
    }


def run(root: Path, shortlist: Path) -> dict:
    (preflight, _shortlist, decisions, baseline, config, mapping, passports,
     markets, ticks, hashes) = load_development_inputs(root, shortlist)
    groups = config["groups"]
    implementation_sha256 = hashlib.sha256(
        Path(research.__file__).read_bytes() + Path(__file__).read_bytes()).hexdigest()
    profile_sha256 = digest({"version": VERSION, "base_profile_sha256": digest(config)})
    added, checked = [], Counter()
    for decision in decisions:
        if decision["status"] != "no_setup" or decision.get("reason") != "price_confirmation":
            continue
        symbol, side, as_of = (decision[key] for key in ("symbol", "side", "time"))
        group = mapping[symbol]
        profile = groups[group]
        feature = research.features(markets[symbol], as_of)
        family = profile[side]
        if family == "TR":
            family = "R" if feature["regime"] == "neutral" else "T"
        if family != "T":
            continue
        checked[group + ":" + side] += 1
        plan = inside_bar_plan(feature, side, ticks[symbol], profile["rv_" + side])
        if plan is None:
            continue
        plan.update(symbol=symbol, group=group, profile_version=VERSION,
                    profile_sha256=profile_sha256, implementation_sha256=implementation_sha256,
                    passport_sha256=digest(passports[symbol]),
                    max_holding_seconds=profile["max_hours"] * 3600,
                    daily_regime=feature["regime"], daily_trend_age=feature["age"],
                    status="technical_candidate_not_admitted", live_eligible=False,
                    historical_validation_eligible=False)
        plan["decision_key"] = digest({key: plan[key] for key in (
            "symbol", "side", "signal_time", "profile_sha256",
            "passport_sha256", "implementation_sha256", "family")})
        added.append(plan)
    start, end = preflight["scan_start"], preflight["scan_end"]
    original_ids = {(p["symbol"], p["side"], p["signal_time"]) for p in baseline}
    added_ids = {(p["symbol"], p["side"], p["signal_time"]) for p in added}
    if original_ids & added_ids or len(added_ids) != len(added):
        raise ValueError("Research variant duplicated an original candidate")
    return {
        "version": VERSION, "mode": "offline_entry_hypothesis_frequency_only",
        "live_eligible": False, "independent_validation": False,
        "profitability_established": False, "economic_admitted": 0,
        "candidate_refill_after_rejection": False,
        "tested_groups_sides": dict(sorted(checked.items())),
        "baseline": summarize_frequency(baseline, start, end),
        "new_inside_bar_only": summarize_frequency(added, start, end),
        "combined_technical_only": summarize_frequency(baseline + added, start, end),
        "source": {"baseline_sha256": digest(baseline), "four_hour_sha256": hashes,
                   "base_rules_sha256": digest(config),
                   "trial_implementation_sha256": implementation_sha256},
        "limitations": [
            "Only original 27 passported representatives on already inspected development dates",
            "The new trigger has no minute execution, funding, fees or slippage replay",
            "Technical candidates are not delivered signals or filled trades",
            "No independent evidence of win rate, drawdown or profitability",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--shortlist", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.root, args.shortlist)
    write_json(args.output, result)
    print(json.dumps({"baseline": result["baseline"]["technical_candidates"],
                      "new_inside_bar": result["new_inside_bar_only"]["technical_candidates"],
                      "combined": result["combined_technical_only"]["technical_candidates"]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
