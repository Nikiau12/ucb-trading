import math

import pytest

from evaluation.group_daily_gate_trial import (
    btc_neutral_variant_allowed, directed_day, rejection_cause, unconfirmed_flags,
)
from evaluation.sector_entries import features, regime_allowed
from evaluation.sector_data import DAY, FOUR_HOURS
from trading.analytics.structure import Bar


def fixture_feature(regime="up", direction="up"):
    daily = [Bar(i*DAY, 100, 102, 98, 101, 1) for i in range(60)]
    d = {"atr": [2]*60, "ema20": [100]*60,
         "ema50": [99]*60, "adx": [25]*60}
    if direction == "down":
        daily[-1] = Bar(59*DAY, 100, 102, 98, 98, 1)
        d["ema20"][-1], d["ema50"][-1] = 99, 100
        d["ema20"][-4] = 100
    elif direction == "other":
        d["adx"][-1] = 10
    else:
        d["ema20"][-4] = 99
    return {"regime": regime, "daily": daily, "d": d}


def test_daily_rejection_separates_asset_confirmation_from_btc_context():
    p = {"long": "T", "short": "B", "btc": "same"}
    up = fixture_feature("up")
    neutral = fixture_feature("neutral", "other")
    assert rejection_cause(up, neutral, p, "long") == "btc_neutral"
    assert rejection_cause(fixture_feature("transition"), neutral, p, "long") == "asset_waiting_second_day"
    assert rejection_cause(fixture_feature("neutral", "other"), neutral, p, "long") == "asset_neutral_not_up"
    assert rejection_cause(fixture_feature("down", "down"), neutral, p, "long") == "asset_down_not_up"
    assert directed_day(up, -1) == "up"
    assert directed_day(fixture_feature("transition", "other"), -1) == "other"
    assert "trend_adx_below_20" in unconfirmed_flags(
        fixture_feature("transition", "other"), p, "long")
    range_profile = {"long": "R", "short": "R", "btc": "not_opposite"}
    assert "range_adx_not_below_20" not in unconfirmed_flags(
        fixture_feature("transition", "other"), range_profile, "long")


@pytest.mark.parametrize("btc_regime,expected", [("neutral", True), ("down", False),
                                                  ("transition", False), ("up", True)])
def test_only_neutral_btc_gets_exception_for_same_direction_groups(btc_regime, expected):
    asset = {"regime": "up"}
    btc = {"regime": btc_regime}
    p = {"btc": "same"}
    allowed = btc_neutral_variant_allowed(asset, btc, p, "long", "T",
                                          baseline=regime_allowed)
    assert allowed is expected
    assert not btc_neutral_variant_allowed(asset, btc, p, "long", "R",
                                           baseline=regime_allowed)
    assert not btc_neutral_variant_allowed(asset, btc, {"btc": "none"}, "short", "T",
                                           baseline=regime_allowed)


def test_daily_context_is_same_throughout_unfinished_utc_day():
    bars = []
    for i in range(780):
        close = 100+i*.03+math.sin(i/10)
        bars.append(Bar(i*FOUR_HOURS, close-.1, close+1, close-1, close, 100))
    midnight = 768*FOUR_HOURS
    at_midnight = features(bars, midnight)
    after_two_bars = features(bars, midnight+2*FOUR_HOURS)
    assert at_midnight["regime"] == after_two_bars["regime"]
    assert at_midnight["return20"] == after_two_bars["return20"]
    assert at_midnight["daily"] == after_two_bars["daily"]
