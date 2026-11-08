from dataclasses import replace

import pytest

from evaluation.group_rule_trial import candidate, load_cards, plan_geometry
from evaluation.group_trial_replay import replay_one
from evaluation.sector_data import FOUR_HOURS
from trading.analytics.structure import Bar
from evaluation.sector_entries import load_entries


def mirror(bars):
    return [Bar(b.ts, 200-b.o, 200-b.l, 200-b.h, 200-b.c, b.v) for b in bars]


def fixture_feature(template, side="long"):
    bars = [Bar(i*FOUR_HOURS, 100, 101, 99, 100, 100) for i in range(61)]
    if template == "trend_flag":
        bars[-1] = Bar(60*FOUR_HOURS, 100.8, 102.4, 100.8, 101.8, 150)
    elif template == "breakout_confirmation":
        bars[-2] = Bar(59*FOUR_HOURS, 100.8, 102, 100.5, 101.6, 200)
        bars[-1] = Bar(60*FOUR_HOURS, 101.4, 102.2, 101.1, 101.9, 150)
    else:
        bars = [Bar(i*FOUR_HOURS, 104, 108, 102, 106, 100) for i in range(61)]
        for i in (20, 36):
            bars[i] = replace(bars[i], l=100)
        for i in (16, 32):
            bars[i] = replace(bars[i], h=110)
        bars[-1] = Bar(60*FOUR_HOURS, 100.4, 101.2, 100.1, 101, 100)
    if side == "short":
        bars = mirror(bars)
    return {"bars": bars, "h": {"atr": [2]*len(bars),
                                  "ema20": [100]*len(bars),
                                  "ema50": [99 if side == "long" else 101]*len(bars),
                                  "adx": [30]*len(bars)}}


@pytest.mark.parametrize("template", ["trend_flag", "breakout_confirmation", "structure_range"])
@pytest.mark.parametrize("side", ["long", "short"])
def test_three_templates_have_ordered_tick_rounded_levels(template, side):
    feature = fixture_feature(template, side)
    plan = plan_geometry(feature, side, template, .01, rv_min=1.2)
    assert plan and plan["signal_time"] == feature["bars"][-1].ts+FOUR_HOURS
    sign = 1 if side == "long" else -1
    assert sign*(plan["entry"]-plan["stop"]) > 0
    assert sign*(plan["tp1"]-plan["entry"]) > 0
    assert sign*(plan["tp2"]-plan["tp1"]) > 0
    assert plan["entry_expiry_seconds"] == 8*3600
    for key in ("entry", "stop", "tp1", "tp2"):
        assert plan[key]*100 == pytest.approx(round(plan[key]*100))


def test_breakout_requires_separate_confirming_candle_and_no_reentry():
    feature = fixture_feature("breakout_confirmation")
    first_only = {**feature, "bars": feature["bars"][:-1],
                  "h": {key: values[:-1] for key, values in feature["h"].items()}}
    assert plan_geometry(first_only, "long", "breakout_confirmation", .01) is None
    bad = fixture_feature("breakout_confirmation")
    bad["bars"][-1] = replace(bad["bars"][-1], l=100.9)
    assert plan_geometry(bad, "long", "breakout_confirmation", .01) is None


def test_range_needs_two_spaced_tests_each_side():
    feature = fixture_feature("structure_range")
    feature["bars"][36] = replace(feature["bars"][36], l=102)
    assert plan_geometry(feature, "long", "structure_range", .01) is None


def test_privacy_btc_is_context_only_but_own_daily_trend_still_required():
    config, mapping = load_entries()
    cards = load_cards(config)
    assert cards["groups"]["privacy"]["btc_policy"] == "context_only"
    assert cards["groups"]["l1"]["btc_policy"] == "hard_same"
    as_of = 61*FOUR_HOURS
    def feature(regime, template="breakout_confirmation"):
        f = fixture_feature(template)
        return {**f, "regime": regime, "return20": 0,
                "age": 4, "volatility_ok": True,
                "daily": [Bar(0, 100, 101, 99, 100, 1)],
                "d": {"ema20": [100], "atr": [2]}}
    cache = {("ZEC_USDT", as_of): feature("up"),
             ("BTC_USDT", as_of): feature("down")}
    out = candidate("ZEC_USDT", "long", {}, as_of=as_of, tick=.01,
                    feature_cache=cache, config=config, mapping=mapping, cards=cards)
    assert out["status"] == "technical_candidate_not_admitted"
    assert out["btc_divergent"] and not out["live_eligible"]
    cache[("ZEC_USDT", as_of)] = feature("transition")
    assert candidate("ZEC_USDT", "long", {}, as_of=as_of, tick=.01,
                     feature_cache=cache, config=config, mapping=mapping, cards=cards)["status"] == "no_setup"
    cache[("SUI_USDT", as_of)] = feature("up")
    assert candidate("SUI_USDT", "long", {}, as_of=as_of, tick=.01,
                     feature_cache=cache, config=config, mapping=mapping, cards=cards)["reason"] == "btc_direction"


def test_none_template_cannot_become_trading_signal():
    feature = fixture_feature("trend_flag")
    feature["h"]["adx"][-1] = 10
    assert plan_geometry(feature, "long", "trend_flag", .01) is None
    with pytest.raises(ValueError):
        plan_geometry(feature, "long", "unknown", .01)


def replay_plan():
    return {"side": "long", "entry": 100., "stop": 95., "tp1": 107.5,
            "tp2": 115., "risk_price": 5., "signal_time": 0,
            "entry_expiry_seconds": 2*FOUR_HOURS,
            "max_holding_seconds": 4*FOUR_HOURS}


def test_four_hour_replay_deducts_fee_and_slippage_only_on_ordered_path():
    bars = [Bar(0, 99, 101, 98, 100, 1),
            Bar(FOUR_HOURS, 103, 108, 102, 107, 1),
            Bar(2*FOUR_HOURS, 109, 116, 108, 115, 1),
            Bar(3*FOUR_HOURS, 115, 116, 114, 115, 1),
            Bar(4*FOUR_HOURS, 115, 116, 114, 115, 1)]
    result = replay_one(replay_plan(), bars)
    assert result["status"] == "tp2" and result["entered"] is True
    assert result["fee_r"] > 0
    assert 2.0 < result["fee_slippage_net_r"] < 2.25
    assert "excludes_funding" in result["cost_scope"]


def test_four_hour_replay_never_guesses_intrabar_order_or_missing_future():
    plan = replay_plan()
    entry_and_stop = [Bar(0, 99, 101, 94, 100, 1),
                      Bar(FOUR_HOURS, 100, 101, 98, 100, 1)]
    assert replay_one(plan, entry_and_stop)["status"] == "ambiguous_entry_bar"
    stop_before_entry = [Bar(0, 98, 99, 94, 98, 1),
                         Bar(FOUR_HOURS, 98, 99, 96, 98, 1)]
    assert replay_one(plan, stop_before_entry)["status"] == "cancelled_before_entry"
    assert replay_one(plan, [Bar(0, 99, 101, 98, 100, 1)])["status"] == "censored_data"
