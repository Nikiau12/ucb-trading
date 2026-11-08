from dataclasses import replace

import pytest

from evaluation.group_inside_bar_trial import inside_bar_plan
from evaluation.sector_data import FOUR_HOURS
from trading.analytics.structure import Bar


def feature():
    bars = [Bar(i * FOUR_HOURS, 100, 101, 99, 100, 100) for i in range(60)]
    bars.append(Bar(60 * FOUR_HOURS, 100, 102, 99, 101, 120))
    bars.append(Bar(61 * FOUR_HOURS, 100.5, 101.7, 100.3, 101.5, 80))
    return {"bars": bars, "h": {
        "atr": [2] * len(bars), "ema20": [100] * len(bars),
        "ema50": [99] * len(bars), "adx": [30] * len(bars)}}


def mirror(original):
    bars = [Bar(b.ts, 200 - b.o, 200 - b.l, 200 - b.h, 200 - b.c, b.v)
            for b in original["bars"]]
    return {"bars": bars, "h": {**original["h"], "ema50": [101] * len(bars)}}


def test_inside_bar_trend_entry_is_directional_and_tick_rounded():
    for side, data in (("long", feature()), ("short", mirror(feature()))):
        plan = inside_bar_plan(data, side, .01, 1.2)
        assert plan is not None
        sign = 1 if side == "long" else -1
        assert sign * (plan["entry"] - plan["stop"]) > 0
        assert sign * (plan["tp1"] - plan["entry"]) > 0
        assert sign * (plan["tp2"] - plan["tp1"]) > 0
        assert plan["signal_time"] == 62 * FOUR_HOURS
        assert plan["entry_expiry_seconds"] == 2 * FOUR_HOURS
        for key in ("entry", "stop", "tp1", "tp2"):
            assert plan[key] * 100 == pytest.approx(round(plan[key] * 100))


def test_inside_bar_rejects_uncontained_or_high_volume_signal():
    data = feature()
    data["bars"][-1] = replace(data["bars"][-1], h=102.1)
    assert inside_bar_plan(data, "long", .01, 0) is None
    data = feature()
    data["bars"][-1] = replace(data["bars"][-1], v=121)
    assert inside_bar_plan(data, "long", .01, 0) is None


def test_inside_bar_preserves_trend_and_mother_volume_gates():
    data = feature()
    data["h"]["adx"][-1] = 24
    assert inside_bar_plan(data, "long", .01, 0) is None
    data = feature()
    assert inside_bar_plan(data, "long", .01, 1.21) is None
