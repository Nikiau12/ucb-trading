"""Lower-threshold 1D/4H market ideas for a trader's decision journal.

These are *not* estimated win probabilities or execution instructions.  Each
idea still needs a completed 4H candle, a real contract and publication-time
market/trigger checks.  The existing, stricter group candidate takes priority.
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path

from evaluation import sector_entries as base
from evaluation.sector_data import FOUR_HOURS, digest
from trading.group_catalog import registry
from trading.group_live_rules import load_rules


VERSION = "group-journal-v1-2026-11-08"


def _finite(*values):
    return all(value is not None and math.isfinite(value) for value in values)


def _geometry(feature, side, template, tick):
    bars, h = feature["bars"], feature["h"]
    if len(bars) < 30:
        return None
    bar, previous = bars[-1], bars[-2]
    atr, ema20, ema50 = (h[key][-1] for key in ("atr", "ema20", "ema50"))
    if not _finite(atr, ema20, ema50) or atr <= 0 or bar.h - bar.l > 3 * atr:
        return None
    sign = 1 if side == "long" else -1
    # A real directional close is required; a flat/doji candle is not an idea.
    if sign * (bar.c - bar.o) < .12 * atr:
        return None
    if template == "trend_flag":
        if (sign * (ema20 - ema50) <= 0 or sign * (bar.c - ema20) <= 0
                or sign * (bar.c - previous.c) <= 0):
            return None
        support = min(b.l for b in bars[-4:]) if sign == 1 else max(b.h for b in bars[-4:])
        stop_raw = support - .2 * atr if sign == 1 else support + .2 * atr
    elif template == "breakout_confirmation":
        prior = bars[-13:-1]
        boundary = max(b.h for b in prior) if sign == 1 else min(b.l for b in prior)
        if not .03 * atr <= sign * (bar.c - boundary) <= 1.5 * atr:
            return None
        stop_raw = min(boundary, bar.l) - .25 * atr if sign == 1 else max(boundary, bar.h) + .25 * atr
    elif template == "structure_range":
        prior = bars[-25:-1]
        low, high = min(b.l for b in prior), max(b.h for b in prior)
        width = high - low
        if not 2 * atr <= width <= 12 * atr:
            return None
        boundary = low if sign == 1 else high
        extreme = bar.l if sign == 1 else bar.h
        if abs(extreme - boundary) > .55 * atr or sign * (bar.c - boundary) < .2 * atr:
            return None
        stop_raw = boundary - .3 * atr if sign == 1 else boundary + .3 * atr
    else:
        raise ValueError("Unknown journal geometry")
    entry = base.round_price(bar.h + tick if sign == 1 else bar.l - tick, tick, sign == 1)
    stop = base.round_price(stop_raw, tick, sign == -1)
    risk = sign * (entry - stop)
    if min(entry, stop) <= 0 or not .5 * atr <= risk <= 3 * atr:
        return None
    tp1 = base.round_price(entry + sign * 1.25 * risk, tick, sign == -1)
    tp2 = base.round_price(entry + sign * 2.25 * risk, tick, sign == -1)
    if min(tp1, tp2) <= 0 or sign * (tp1 - entry) < risk or sign * (tp2 - entry) < 1.8 * risk:
        return None
    return {"family": "journal_" + template, "side": side, "entry": entry, "stop": stop,
            "tp1": tp1, "tp2": tp2, "risk_price": risk, "atr4h": atr,
            "entry_type": "stop", "trigger_price_type": "contract_last",
            "signal_time": bar.ts + FOUR_HOURS, "entry_expiry_seconds": 2 * FOUR_HOURS}


def candidate(symbol, side, markets, *, as_of, tick, passport=None, _feature_cache=None):
    """Return one group-specific journal idea, or an explicit no-setup reason."""
    if type(as_of) is not int or as_of % FOUR_HOURS or side not in ("long", "short"):
        raise ValueError("Only closed 4H decisions and known directions are allowed")
    definitions, _ = base.load_entries()
    group = registry()["mapping"].get(symbol)
    if group not in definitions["groups"]:
        raise ValueError("Unclassified journal symbol")
    if passport is not None and (passport.get("symbol") != symbol or passport.get("group") != group):
        raise ValueError("Passport identity mismatch")
    policy = load_rules()["groups"][group]
    def get(sym):
        key = sym, as_of
        if _feature_cache is not None and key in _feature_cache:
            return _feature_cache[key]
        value = base.features(markets[sym], as_of)
        if _feature_cache is not None:
            _feature_cache[key] = value
        return value
    try:
        feature = get(symbol)
        btc = get("BTC_USDT") if policy["btc_policy"] != "none" else None
    except (KeyError, ValueError) as exc:
        return {"status": "blocked_data", "reason": str(exc)}
    if (not isinstance(feature.get("h"), dict)
            or any(not (feature.get("d") or {}).get(key) for key in ("ema20", "ema50"))
            or (btc is not None and not (btc.get("d") or {}).get("ema20"))):
        return {"status": "no_setup", "reason": "journal_4h_geometry"}
    sign = 1 if side == "long" else -1
    # Keep the group's entry family. RWA uses its existing trend family; gold
    # reference data are deliberately NOT represented as verified here.
    templates = policy[side] or ["trend_flag"]
    for template in templates:
        plan = _geometry(feature, side, template, tick)
        if plan is None:
            continue
        daily, d = feature["daily"][-1], feature["d"]
        daily_e20, daily_e50 = d["ema20"][-1], d["ema50"][-1]
        if not _finite(daily_e20, daily_e50):
            return {"status": "blocked_data", "reason": "daily_context_unavailable"}
        matches = {
            "daily_close": sign * (daily.c - daily_e20) > 0,
            "daily_ema": sign * (daily_e20 - daily_e50) > 0,
            "btc_context": btc is None or sign * (btc["daily"][-1].c - btc["d"]["ema20"][-1]) > 0,
            "four_hour_ema": sign * (feature["bars"][-1].c - feature["h"]["ema20"][-1]) > 0,
            "four_hour_volume": base.relative_volume(feature["bars"], len(feature["bars"]) - 1) >= 1,
        }
        score = round(.6 + .05 * sum(matches.values()), 2)
        implementation = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        plan.update(symbol=symbol, group=group, profile_version=VERSION,
                    profile_sha256=digest(load_rules()), implementation_sha256=implementation,
                    passport_sha256=digest(passport) if passport else None,
                    max_holding_seconds=min(definitions["groups"][group]["max_hours"], 96) * 3600,
                    daily_regime=feature["regime"], btc_regime=btc["regime"] if btc else None,
                    btc_policy=policy["btc_policy"], criteria=matches, criteria_score=score,
                    status="technical_candidate_not_admitted", live_eligible=False,
                    historical_validation_eligible=False)
        plan["decision_key"] = digest({key: plan[key] for key in (
            "symbol", "side", "signal_time", "profile_sha256", "passport_sha256",
            "implementation_sha256", "family")})
        return plan
    return {"status": "no_setup", "reason": "journal_4h_geometry"}
