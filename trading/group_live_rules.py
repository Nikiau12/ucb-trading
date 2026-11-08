"""Approved runtime bindings for the 16 group entry strategies.

The frozen research cards are not imported as a scanner configuration. Their
three pure, closed-candle geometries are reused after the existing group rule
has declined a setup. This module neither places orders nor changes saved
signals. Market admission remains the responsibility of group_plan.
"""
from __future__ import annotations

from functools import lru_cache
import hashlib
import json
from pathlib import Path

from evaluation import sector_entries as base
from evaluation.group_rule_trial import plan_geometry
from evaluation.sector_data import FOUR_HOURS, digest


_PATH = Path(__file__).with_name("group_live_rules.v2.json")
_TEMPLATES = {"trend_flag", "breakout_confirmation", "structure_range"}
_POLICIES = {"none", "hard_same", "hard_not_opposite", "context_only"}


@lru_cache(maxsize=1)
def load_rules():
    rules = json.loads(_PATH.read_text())
    definitions, _ = base.load_entries()
    if (rules["mode"] != "public_candidate_rules"
            or rules["base_entry_version"] != definitions["version"]
            or rules["timeframes"] != ["1d", "4h"]
            or rules["selection"] != "existing_rule_first_then_group_pattern"
            or rules["profitability_validated"] is not False
            or set(rules["groups"]) != set(definitions["groups"])):
        raise ValueError("Invalid live group strategy registry")
    for group, policy in rules["groups"].items():
        expected_btc = {"none": "none", "same": "hard_same",
                        "not_opposite": "hard_not_opposite"}[definitions["groups"][group]["btc"]]
        if (policy["btc_policy"] not in _POLICIES
                or policy["btc_policy"] != ("context_only" if group == "privacy" else expected_btc)):
            raise ValueError("Unexpected group benchmark policy: " + group)
        for side in ("long", "short"):
            names = policy[side]
            if (not isinstance(names, list) or len(names) != len(set(names))
                    or not set(names) <= _TEMPLATES
                    or (not names and group != "rwa")):
                raise ValueError("Invalid group entry pattern: " + group)
    # New XAUT/PAXG pattern remains withheld until the underlying-asset
    # reference can be verified. The existing RWA trend rule still runs.
    if rules["groups"]["rwa"]["long"] or rules["groups"]["rwa"]["short"]:
        raise ValueError("RWA alternative needs independent reference")
    return rules


def additional_candidate(symbol, side, markets, *, as_of, tick, passport=None,
                         _feature_cache=None):
    """Return a group-specific alternative, or an explicit fail-closed reason."""
    if type(as_of) is not int or as_of % FOUR_HOURS:
        raise ValueError("Only completed UTC 4H decisions are allowed")
    definitions, _ = base.load_entries()
    from trading.group_catalog import registry
    group = registry()["mapping"].get(symbol)
    if group is None or side not in ("long", "short"):
        raise ValueError("No group strategy for instrument or direction")
    if passport is not None and (passport.get("symbol") != symbol or
                                passport.get("group") != group):
        raise ValueError("Passport identity mismatch")
    policy = load_rules()["groups"][group]
    if not policy[side]:
        return {"status": "no_setup", "reason": "no_additional_group_pattern"}
    profile = definitions["groups"][group]

    def get(sym):
        key = sym, as_of
        if _feature_cache is not None and key in _feature_cache:
            return _feature_cache[key]
        result = base.features(markets[sym], as_of)
        if _feature_cache is not None:
            _feature_cache[key] = result
        return result

    try:
        feature = get(symbol)
        btc = get("BTC_USDT") if policy["btc_policy"] != "none" else None
    except (KeyError, ValueError) as exc:
        return {"status": "blocked_data", "reason": str(exc)}
    sign = 1 if side == "long" else -1
    desired = "up" if sign == 1 else "down"
    opposite = "down" if sign == 1 else "up"
    role = policy["btc_policy"]
    btc_regime = btc["regime"] if btc is not None else None
    if role == "hard_same" and btc_regime != desired:
        return {"status": "no_setup", "reason": "daily_regime"}
    if (role == "hard_not_opposite" and
            (btc_regime not in ("up", "down", "neutral", "transition") or
             btc_regime == opposite)):
        return {"status": "no_setup", "reason": "daily_regime"}
    if (role == "context_only" and
            btc_regime not in ("up", "down", "neutral", "transition")):
        return {"status": "blocked_data", "reason": "btc_context_missing"}
    if (profile["rs"] and role != "context_only" and btc is not None and
            feature["regime"] != "neutral" and
            sign * (feature["return20"] - btc["return20"]) <= 0):
        return {"status": "no_setup", "reason": "relative_strength_btc"}
    extra = (passport or {}).get("additional_benchmark")
    if extra and group in ("scaling", "defi"):
        try:
            other = get(extra)
        except (KeyError, ValueError):
            return {"status": "blocked_data", "reason": "additional_benchmark_missing"}
        if sign * (feature["return20"] - other["return20"]) <= 0:
            return {"status": "no_setup", "reason": "relative_strength_subtype"}
    if ("trend_age" in profile and
            not profile["trend_age"][0] <= feature["age"] <= profile["trend_age"][1]):
        return {"status": "no_setup", "reason": "daily_trend_age"}
    if side == "long" and profile["volatility_long"] and not feature["volatility_ok"]:
        return {"status": "no_setup", "reason": "daily_volatility"}

    for template in policy[side]:
        if feature["regime"] != ("neutral" if template == "structure_range" else desired):
            continue
        if (template == "trend_flag" and
                sign * (feature["daily"][-1].c - feature["d"]["ema20"][-1]) >
                2 * feature["d"]["atr"][-1]):
            continue
        plan = plan_geometry(feature, side, template, tick, profile["rv_" + side])
        if plan is None:
            continue
        if plan["signal_time"] != as_of:
            return {"status": "blocked_data", "reason": "stale_or_future_feature_cache"}
        implementation = hashlib.sha256(
            Path(__file__).read_bytes() + Path(plan_geometry.__code__.co_filename).read_bytes()
        ).hexdigest()
        plan.update(symbol=symbol, group=group, profile_version=load_rules()["version"],
                    profile_sha256=digest(load_rules()), implementation_sha256=implementation,
                    passport_sha256=digest(passport) if passport else None,
                    max_holding_seconds=min(profile["max_hours"],
                                           72 if template == "structure_range" else 96) * 3600,
                    daily_regime=feature["regime"], daily_trend_age=feature["age"],
                    btc_regime=btc_regime, btc_policy=role,
                    status="technical_candidate_not_admitted", live_eligible=False,
                    historical_validation_eligible=False)
        plan["decision_key"] = digest({key: plan[key] for key in (
            "symbol", "side", "signal_time", "profile_sha256", "passport_sha256",
            "implementation_sha256", "family")})
        return plan
    return {"status": "no_setup", "reason": "price_confirmation"}
