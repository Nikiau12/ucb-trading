"""Runtime extension of frozen sector rules, without editing research artifacts.

The original 89 instruments still call the original candidate function (including
its decision hash). New reviewed instruments use the same rule sequence below.
Parity tests guard the mirrored sequence; indicators and price geometry are shared.
"""
import hashlib
from pathlib import Path

from evaluation import sector_entries as research
from evaluation.sector_data import FOUR_HOURS, digest
from trading.group_catalog import registry
from trading.group_live_rules import additional_candidate
from trading.group_journal_ideas import candidate as journal_candidate


def candidate(symbol, side, markets, **kwargs):
    catalog = registry()
    if symbol in catalog["baseline"]:
        original = research.candidate(symbol, side, markets, **kwargs)
    else:
        original = extended_candidate(symbol, side, markets, **kwargs)
    # Keep an accepted original setup and its decision identity unchanged.
    # Only a declined setup may try the predeclared pattern for its own group.
    if original["status"] != "no_setup":
        return original
    alternative = additional_candidate(symbol, side, markets, **kwargs)
    if alternative["status"] == "blocked_data":
        return alternative
    if alternative["status"] == "technical_candidate_not_admitted":
        return alternative
    journal = journal_candidate(symbol, side, markets, **kwargs)
    return journal if journal["status"] != "no_setup" else original


def extended_candidate(symbol, side, markets, *, as_of, tick, passport=None, _feature_cache=None):
    config, _ = research.load_entries()
    mapping = registry()["mapping"]
    if symbol not in mapping or side not in ("long", "short"):
        raise ValueError("No fallback for unknown instrument or direction")
    group = mapping[symbol]
    p = config["groups"][group]
    if passport is not None and (passport.get("symbol") != symbol or passport.get("group") != group):
        raise ValueError("Passport belongs to a different instrument/group")

    def get(s):
        key = (s, as_of)
        if _feature_cache is not None and key in _feature_cache:
            return _feature_cache[key]
        value = research.features(markets[s], as_of)
        if _feature_cache is not None:
            _feature_cache[key] = value
        return value

    try:
        f = get(symbol)
        btc = get("BTC_USDT") if p["btc"] != "none" else None
    except (ValueError, KeyError) as exc:
        return {"status": "blocked_data", "reason": str(exc), "live_eligible": False}
    family = p[side]
    if family == "TR":
        family = "R" if f["regime"] == "neutral" else "T"
    if not research.regime_allowed(f, btc, p, side, family):
        return {"status": "no_setup", "reason": "daily_regime", "live_eligible": False}
    sign = 1 if side == "long" else -1
    if p["rs"] and family != "R" and sign * (f["return20"] - btc["return20"]) <= 0:
        return {"status": "no_setup", "reason": "relative_strength_btc", "live_eligible": False}
    extra = (passport or {}).get("additional_benchmark")
    if extra and group in ("scaling", "defi"):
        try:
            other = get(extra)
        except (ValueError, KeyError):
            return {"status": "blocked_data", "reason": "additional_benchmark_missing", "live_eligible": False}
        if sign * (f["return20"] - other["return20"]) <= 0:
            return {"status": "no_setup", "reason": "relative_strength_subtype", "live_eligible": False}
    if "trend_age" in p and not p["trend_age"][0] <= f["age"] <= p["trend_age"][1]:
        return {"status": "no_setup", "reason": "daily_trend_age", "live_eligible": False}
    if family == "T" and sign * (f["daily"][-1].c - f["d"]["ema20"][-1]) > 2 * f["d"]["atr"][-1]:
        return {"status": "no_setup", "reason": "late_trend_extension", "live_eligible": False}
    if side == "long" and p["volatility_long"] and not f["volatility_ok"]:
        return {"status": "no_setup", "reason": "daily_volatility", "live_eligible": False}
    plan = research.form_plan(f["bars"], f["h"]["atr"], side, family, tick,
                             ema20=f["h"]["ema20"][-1], ema50=f["h"]["ema50"][-1],
                             adx=f["h"]["adx"][-1], rv_min=p["rv_" + side])
    if plan is None:
        return {"status": "no_setup", "reason": "price_confirmation", "live_eligible": False}
    if family == "B":
        for boundary in range(plan["breakout_time"], as_of + 1, FOUR_HOURS):
            try:
                before = get(symbol) if boundary == as_of else research.features(markets[symbol], boundary)
                ref = btc if boundary == as_of else (research.features(markets["BTC_USDT"], boundary) if p["btc"] != "none" else None)
                if not research.regime_allowed(before, ref, p, side, family):
                    return {"status": "no_setup", "reason": "regime_changed_during_retest", "live_eligible": False}
            except (KeyError, ValueError):
                return {"status": "blocked_data", "reason": "retest_context_missing", "live_eligible": False}
    implementation = hashlib.sha256(Path(__file__).read_bytes() + Path(research.__file__).read_bytes()).hexdigest()
    plan.update(symbol=symbol, group=group, profile_version=config["version"], profile_sha256=digest(config),
                implementation_sha256=implementation, passport_sha256=digest(passport) if passport else None,
                max_holding_seconds=min(p["max_hours"], 72 if family == "R" else 96) * 3600,
                daily_regime=f["regime"], daily_trend_age=f["age"], status="technical_candidate_not_admitted",
                live_eligible=False, historical_validation_eligible=False)
    plan["decision_key"] = digest({k: plan[k] for k in ("symbol", "side", "signal_time", "profile_sha256", "passport_sha256", "implementation_sha256", "family")})
    return plan
