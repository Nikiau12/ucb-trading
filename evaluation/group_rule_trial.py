"""Offline-only trial of the three frozen group-card entry patterns.

This module never imports the live scanner, exchange client or credentials.
Candidates use completed 1D/4H candles only. Current passports and contract
ticks are NOT point-in-time historical admission evidence.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

from evaluation import sector_entries as base
from evaluation.group_frequency_lab import load_development_inputs, summarize_frequency
from evaluation.sector_data import FOUR_HOURS, digest


CARD_PATH = Path(__file__).with_name("group_rule_cards.v1.json")
TEMPLATES = {"trend_flag", "breakout_confirmation", "structure_range"}
BTC_POLICIES = {"none", "hard_same", "hard_not_opposite", "context_only"}
VERSION = "group-rule-trial-v1-2026-11-08"


def load_cards(config=None):
    config = config or base.load_entries()[0]
    cards = json.loads(CARD_PATH.read_text())
    if (cards["mode"] != "design_only_not_scanner_configuration"
            or cards["live_eligible"] is not False
            or cards["automatic_promotion"] is not False
            or cards["timeframes"] != ["1d", "4h"]
            or cards["base_entry_version"] != config["version"]
            or set(cards["templates"]) != TEMPLATES
            or set(cards["groups"]) != set(config["groups"])):
        raise ValueError("Group cards changed or are not research-only")
    for group, rules in cards["groups"].items():
        if rules["btc_policy"] not in BTC_POLICIES:
            raise ValueError("Unknown BTC context policy: " + group)
        for side in ("long", "short"):
            templates = rules[side]
            if not templates or len(templates) != len(set(templates)) or not set(templates) <= TEMPLATES:
                raise ValueError("Invalid group template binding: " + group)
    return cards


def _levels(entry, stop, side, tick, *, tp1=None, tp2=None):
    sign = 1 if side == "long" else -1
    entry = base.round_price(entry, tick, sign == 1)
    stop = base.round_price(stop, tick, sign == -1)
    risk = sign * (entry - stop)
    if min(entry, stop) <= 0 or risk <= 0:
        return None
    tp1 = entry + sign * 1.5 * risk if tp1 is None else tp1
    tp2 = entry + sign * 3 * risk if tp2 is None else tp2
    tp1 = base.round_price(tp1, tick, sign == -1)
    tp2 = base.round_price(tp2, tick, sign == -1)
    if min(tp1, tp2) <= 0 or not (sign * (tp1 - entry) > 0 and sign * (tp2 - tp1) > 0):
        return None
    return {"entry": entry, "stop": stop, "tp1": tp1, "tp2": tp2, "risk_price": risk}


def plan_geometry(feature, side, template, tick, rv_min=0):
    """One deterministic 4H setup, with no current/future candle in inputs."""
    if side not in ("long", "short") or template not in TEMPLATES:
        raise ValueError("Unknown side/template")
    if not math.isfinite(tick) or tick <= 0:
        raise ValueError("Positive tick required")
    bars, h = feature["bars"], feature["h"]
    if len(bars) < 61:
        return None
    t, i, sign = bars[-1], len(bars)-1, 1 if side == "long" else -1
    atr = h["atr"][-1]
    if atr is None or not math.isfinite(atr) or atr <= 0:
        return None
    lower = upper = breakout_time = None
    if template == "trend_flag":
        e20, e50, adx = (h[key][-1] for key in ("ema20", "ema50", "adx"))
        if (any(v is None or not math.isfinite(v) for v in (e20, e50, adx))
                or adx < 25 or sign * (e20-e50) <= 0 or sign * (t.c-e20) <= 0
                or sign * (t.c-t.o) <= 0 or t.h-t.l > 2.5*atr
                or base.relative_volume(bars, i) < rv_min):
            return None
        # Longest valid pause wins. This priority is fixed before seeing PnL.
        for count in range(8, 3, -1):
            pause = bars[-count-1:-1]
            low, high = min(b.l for b in pause), max(b.h for b in pause)
            if (high-low <= 3*atr and .1*atr <= sign*(t.c-(high if sign == 1 else low))
                    and (t.l >= low-.25*atr if sign == 1 else t.h <= high+.25*atr)):
                lower, upper = low, high
                break
        if lower is None:
            return None
        entry = t.h+tick if sign == 1 else t.l-tick
        stop = lower-.25*atr if sign == 1 else upper+.25*atr
    elif template == "breakout_confirmation":
        first = bars[-2]
        first_atr = h["atr"][-2]
        if first_atr is None or not math.isfinite(first_atr) or first_atr <= 0:
            return None
        prior = bars[-22:-2]
        level = max(b.h for b in prior) if sign == 1 else min(b.l for b in prior)
        distance = sign * (first.c-level)
        if (not .1*first_atr <= distance <= first_atr
                or first.h-first.l > 2.5*first_atr
                or base.relative_volume(bars, i-1) < max(1.5, rv_min)
                or sign*(t.c-level) <= 0 or sign*(t.c-t.o) <= 0
                or (t.l < level if sign == 1 else t.h > level)
                or t.h-t.l > 2.5*atr):
            return None
        breakout_time = first.ts+FOUR_HOURS
        entry = t.h+tick if sign == 1 else t.l-tick
        stop = min(level, t.l)-.25*atr if sign == 1 else max(level, t.h)+.25*atr
    else:
        prior = bars[-49:-1]
        lower, upper = min(b.l for b in prior), max(b.h for b in prior)
        if (not 4*atr <= upper-lower <= 10*atr
                or any(len(base.spaced_touches(prior, level, .25*atr, high)) < 2
                       for level, high in ((lower, False), (upper, True)))):
            return None
        boundary, extreme = (lower, t.l) if sign == 1 else (upper, t.h)
        if (abs(extreme-boundary) > .25*atr or sign*(t.c-boundary) <= .25*atr
                or sign*(t.c-t.o) <= 0):
            return None
        entry = t.h+tick if sign == 1 else t.l-tick
        stop = lower-.25*atr if sign == 1 else upper+.25*atr
    tp1 = (lower+upper)/2 if template == "structure_range" else None
    tp2 = (upper-.25*atr if sign == 1 else lower+.25*atr) if template == "structure_range" else None
    levels = _levels(entry, stop, side, tick, tp1=tp1, tp2=tp2)
    if levels is None:
        return None
    risk = levels["risk_price"]
    if (template == "structure_range" and
            (sign*(levels["tp1"]-levels["entry"]) < risk
             or sign*(levels["tp2"]-levels["entry"]) < 2*risk)):
        return None
    if template != "structure_range" and not .75*atr <= risk <= 2.5*atr:
        return None
    return {"family": template, "side": side, **levels, "atr4h": atr,
            "breakout_time": breakout_time, "range_lower": lower, "range_upper": upper,
            "entry_type": "stop", "trigger_price_type": "contract_last",
            "signal_time": t.ts+FOUR_HOURS, "entry_expiry_seconds": 2*FOUR_HOURS}


def candidate(symbol, side, markets, *, as_of, tick, passport=None, feature_cache=None,
              config=None, mapping=None, cards=None):
    """Research-only group candidate. No admission or order placement."""
    if type(as_of) is not int or as_of % FOUR_HOURS:
        raise ValueError("Only completed UTC 4H decision times are allowed")
    if config is None or mapping is None:
        config, mapping = base.load_entries()
    cards = cards or load_cards(config)
    if symbol not in mapping or side not in ("long", "short"):
        raise ValueError("No fallback for unknown symbol/side")
    group, policy = mapping[symbol], cards["groups"][mapping[symbol]]
    p = config["groups"][group]
    if passport is not None and (passport.get("symbol") != symbol or passport.get("group") != group):
        raise ValueError("Passport identity mismatch")

    def get(sym):
        key = (sym, as_of)
        if feature_cache is not None and key in feature_cache:
            return feature_cache[key]
        value = base.features(markets[sym], as_of)
        if feature_cache is not None:
            feature_cache[key] = value
        return value

    try:
        f = get(symbol)
        btc = get("BTC_USDT") if policy["btc_policy"] != "none" else None
    except (KeyError, ValueError) as exc:
        return {"status": "blocked_data", "reason": str(exc), "live_eligible": False}
    sign = 1 if side == "long" else -1
    desired = "up" if sign == 1 else "down"
    opposite = "down" if sign == 1 else "up"
    btc_regime = btc["regime"] if btc is not None else None
    role = policy["btc_policy"]
    if role == "hard_same" and btc_regime != desired:
        return {"status": "no_setup", "reason": "btc_direction", "live_eligible": False}
    if role == "hard_not_opposite" and (btc_regime not in ("up", "down", "neutral", "transition")
                                        or btc_regime == opposite):
        return {"status": "no_setup", "reason": "btc_direction", "live_eligible": False}
    if (p["rs"] and role != "context_only" and btc is not None
            and f["regime"] != "neutral" and sign*(f["return20"]-btc["return20"]) <= 0):
        return {"status": "no_setup", "reason": "relative_strength_btc", "live_eligible": False}
    extra = (passport or {}).get("additional_benchmark")
    if extra and group in ("scaling", "defi"):
        try:
            other = get(extra)
        except (KeyError, ValueError):
            return {"status": "blocked_data", "reason": "additional_benchmark_missing", "live_eligible": False}
        if sign*(f["return20"]-other["return20"]) <= 0:
            return {"status": "no_setup", "reason": "relative_strength_subtype", "live_eligible": False}
    if "trend_age" in p and not p["trend_age"][0] <= f["age"] <= p["trend_age"][1]:
        return {"status": "no_setup", "reason": "daily_trend_age", "live_eligible": False}
    if side == "long" and p["volatility_long"] and not f["volatility_ok"]:
        return {"status": "no_setup", "reason": "daily_volatility", "live_eligible": False}
    for template in policy[side]:
        if f["regime"] != ("neutral" if template == "structure_range" else desired):
            continue
        if (template == "trend_flag" and
                sign*(f["daily"][-1].c-f["d"]["ema20"][-1]) > 2*f["d"]["atr"][-1]):
            continue
        plan = plan_geometry(f, side, template, tick, p["rv_"+side])
        if plan is None:
            continue
        if plan["signal_time"] != as_of:
            return {"status": "blocked_data", "reason": "stale_or_future_feature_cache",
                    "live_eligible": False}
        plan.update(symbol=symbol, group=group, profile_version=cards["version"],
                    profile_sha256=digest(cards),
                    implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    passport_sha256=digest(passport) if passport else None,
                    max_holding_seconds=min(p["max_hours"], 72 if template == "structure_range" else 96)*3600,
                    daily_regime=f["regime"], btc_regime=btc_regime,
                    btc_policy=role, btc_divergent=btc_regime == opposite,
                    daily_trend_age=f["age"], status="technical_candidate_not_admitted",
                    live_eligible=False, historical_validation_eligible=False,
                    evidence_pending=policy["to_verify"])
        plan["decision_key"] = digest({key: plan[key] for key in (
            "symbol", "side", "signal_time", "profile_sha256", "passport_sha256",
            "implementation_sha256", "family")})
        return plan
    return {"status": "no_setup", "reason": "group_price_confirmation_or_own_regime",
            "live_eligible": False}


def scan_development(root, shortlist, *, return_details=False):
    (preflight, selected, decisions, baseline, config, mapping, passports,
     markets, ticks, hashes) = load_development_inputs(root, shortlist)
    cards = load_cards(config)
    original_ids = {(p["symbol"], p["side"], p["signal_time"]) for p in baseline}
    added, reasons, examined = [], Counter(), Counter()
    cache = {}
    for row in decisions:
        symbol, side, as_of = (row[key] for key in ("symbol", "side", "time"))
        group = mapping[symbol]
        if (row["status"] != "no_setup"
                or (row.get("reason") != "price_confirmation"
                    and not (group == "privacy" and row.get("reason") in
                             ("daily_regime", "relative_strength_btc")))):
            continue
        examined[group+":"+side] += 1
        result = candidate(symbol, side, markets, as_of=as_of, tick=ticks[symbol],
                           passport=passports[symbol], feature_cache=cache,
                           config=config, mapping=mapping, cards=cards)
        if result["status"] == "technical_candidate_not_admitted":
            identity = (symbol, side, as_of)
            if identity in original_ids:
                raise ValueError("Trial duplicates an original candidate")
            added.append(result)
        else:
            reasons[result.get("reason", "unknown")] += 1
        # One decision at a time; caching other times would retain huge arrays.
        cache.clear()
    if len(added) + sum(reasons.values()) != sum(examined.values()):
        raise ValueError("Incomplete trial decision accounting")
    start, end = preflight["scan_start"], preflight["scan_end"]
    report = {
        "version": VERSION, "mode": "offline_development_technical_screen",
        "live_eligible": False, "historical_validation_eligible": False,
        "profitability_established": False, "economic_admitted": 0,
        "period": {"start": start, "end": end, "symbols": len(selected["selected"])},
        "examined_by_group_side": dict(sorted(examined.items())),
        "rejection_reasons": dict(sorted(reasons.items())),
        "new_candidates_by_template": dict(sorted(Counter(p["family"] for p in added).items())),
        "new_candidates_by_group_template": dict(sorted(Counter(
            p["group"]+":"+p["family"] for p in added).items())),
        "baseline": summarize_frequency(baseline, start, end),
        "new_patterns": summarize_frequency(added, start, end),
        "combined_technical_only": summarize_frequency(baseline+added, start, end),
        "privacy_btc_divergent_candidates": sum(
            p["btc_divergent"] for p in added if p["group"] == "privacy"),
        "source": {"base_rules_sha256": digest(config), "cards_sha256": digest(cards),
                   "old_candidates_sha256": digest(baseline), "four_hour_sha256": hashes,
                   "trial_implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
        "limitations": [
            "27 preselected symbols and already inspected development dates, not an independent test",
            "Current passport, contract tick and liquidity are not point-in-time historical evidence",
            "Technical ideas are neither admitted nor delivered, entered or profitable trades",
            "No minute-level execution or verified historical fees, funding and order-book slippage",
            "The privacy BTC exception is a hypothesis, not proof of independence",
        ],
    }
    return (report, baseline, added, markets) if return_details else report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--shortlist", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(scan_development(args.root, args.shortlist), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
