"""Runtime strategy bindings; no exchange, Telegram or real orders."""
from types import SimpleNamespace

import pytest

from evaluation import sector_entries as base
from evaluation.sector_data import FOUR_HOURS
from trading import group_candidates, group_live_rules, group_plan
from trading.group_catalog import registry
from test_group_rule_trial import fixture_feature


GROUP_SYMBOLS = {group: next(symbol for symbol, owner in registry()["baseline"].items()
                             if owner == group)
                 for group in base.load_entries()[0]["groups"]}


def test_all_16_groups_have_explicit_live_rules_and_only_rwa_withholds_new_pattern():
    rules = group_live_rules.load_rules()
    assert rules["version"] == group_plan.VERSION
    assert set(rules["groups"]) == set(GROUP_SYMBOLS)
    for group, policy in rules["groups"].items():
        for side in ("long", "short"):
            assert policy[side] or group == "rwa"
    assert rules["groups"]["privacy"]["btc_policy"] == "context_only"
    assert rules["profitability_validated"] is False


@pytest.mark.parametrize("group", sorted(GROUP_SYMBOLS))
@pytest.mark.parametrize("side", ["long", "short"])
def test_each_group_uses_its_own_fallback_pattern_after_original_declines(monkeypatch, group, side):
    symbol = GROUP_SYMBOLS[group]
    instrument, bitcoin = object(), object()
    rules = group_live_rules.load_rules()["groups"][group]
    sign = 1 if side == "long" else -1
    desired = "up" if side == "long" else "down"
    own_regime = "neutral" if rules[side] == ["structure_range"] else desired
    def features(series, _as_of):
        is_btc = series is bitcoin
        return {"regime": desired if is_btc else own_regime,
                "age": 5, "return20": 0 if is_btc else sign * .1,
                "volatility_ok": True, "daily": [SimpleNamespace(c=100)],
                "d": {"ema20": [100], "atr": [2]}, "bars": [1]}
    seen = []
    def geometry(_feature, selected_side, template, _tick, rv_min):
        seen.append((selected_side, template, rv_min))
        return {"family": template, "side": selected_side,
                "entry": 100, "stop": 95 if sign == 1 else 105,
                "tp1": 108 if sign == 1 else 92, "tp2": 112 if sign == 1 else 88,
                "risk_price": 5, "signal_time": 14400,
                "entry_expiry_seconds": 28800}
    monkeypatch.setattr(base, "candidate", lambda *_a, **_kw:
                        {"status": "no_setup", "reason": "price_confirmation"})
    monkeypatch.setattr(base, "features", features)
    monkeypatch.setattr(group_live_rules, "plan_geometry", geometry)
    market = {symbol: instrument, "BTC_USDT": bitcoin}
    result = group_candidates.candidate(symbol, side, market, as_of=14400, tick=.01)
    if group == "rwa":
        assert result == {"status": "no_setup", "reason": "price_confirmation"}
        assert not seen
    else:
        assert result["status"] == "technical_candidate_not_admitted"
        assert result["group"] == group and result["family"] == rules[side][0]
        assert result["profile_version"] == group_plan.VERSION
        assert result["decision_key"] and seen[0][1] == rules[side][0]


def test_original_accepted_setup_is_untouched(monkeypatch):
    original = {"status": "technical_candidate_not_admitted", "decision_key": "frozen"}
    monkeypatch.setattr(base, "candidate", lambda *_a, **_kw: original)
    monkeypatch.setattr(group_candidates, "additional_candidate", lambda *_a, **_kw:
                        pytest.fail("Fallback ran over accepted original"))
    assert group_candidates.candidate("BTC_USDT", "long", {}, as_of=14400, tick=.01) is original


def test_fallback_fails_closed_on_missing_benchmark_and_invalid_passport():
    symbol = GROUP_SYMBOLS["scaling"]
    result = group_live_rules.additional_candidate(symbol, "long", {symbol: []}, as_of=14400, tick=.01)
    assert result["status"] == "blocked_data"
    with pytest.raises(ValueError, match="Passport identity mismatch"):
        group_live_rules.additional_candidate(symbol, "long", {}, as_of=14400, tick=.01,
                                              passport={"symbol": "OTHER_USDT", "group": "scaling"})


def test_privacy_btc_is_context_not_directional_veto(monkeypatch):
    symbol = GROUP_SYMBOLS["privacy"]
    instrument, bitcoin = object(), object()
    def features(series, _as_of):
        return {"regime": "down" if series is bitcoin else "up", "return20": 0,
                "age": 5, "volatility_ok": True, "daily": [SimpleNamespace(c=100)],
                "d": {"ema20": [100], "atr": [2]}, "bars": [1]}
    monkeypatch.setattr(base, "features", features)
    monkeypatch.setattr(group_live_rules, "plan_geometry", lambda *_a, **_kw:
                        {"family": "breakout_confirmation", "side": "long", "entry": 100,
                         "stop": 95, "tp1": 108, "tp2": 112, "risk_price": 5,
                         "signal_time": 14400, "entry_expiry_seconds": 28800})
    result = group_live_rules.additional_candidate(symbol, "long",
        {symbol: instrument, "BTC_USDT": bitcoin}, as_of=14400, tick=.01)
    assert result["status"] == "technical_candidate_not_admitted"
    assert result["btc_policy"] == "context_only" and result["btc_regime"] == "down"


@pytest.mark.parametrize("group,template,regime", [
    ("core_btc", "trend_flag", "up"),
    ("scaling", "breakout_confirmation", "up"),
    ("payments", "structure_range", "neutral"),
])
def test_live_route_uses_real_closed_candle_geometry(monkeypatch, group, template, regime):
    symbol = GROUP_SYMBOLS[group]
    as_of = 61 * FOUR_HOURS
    own = {**fixture_feature(template), "regime": regime, "age": 5,
           "return20": .1, "volatility_ok": True,
           "daily": [SimpleNamespace(c=100)], "d": {"ema20": [100], "atr": [2]}}
    btc = {**own, "regime": "up" if group == "scaling" else "neutral",
           "return20": 0}
    cache = {(symbol, as_of): own, ("BTC_USDT", as_of): btc}
    if group == "core_btc":
        cache[(symbol, as_of)] = own
    monkeypatch.setattr(base, "candidate", lambda *_a, **_kw:
                        {"status": "no_setup", "reason": "price_confirmation"})
    result = group_candidates.candidate(symbol, "long", {}, as_of=as_of,
                                        tick=.01, _feature_cache=cache)
    assert result["status"] == "technical_candidate_not_admitted"
    assert result["family"] == template and result["signal_time"] == as_of
    assert result["entry"] < result["tp1"] < result["tp2"]
