from evaluation.run_higher_timeframe_research import FOUR_HOURS, gate, to_closed_4h
from trading.analytics.structure import Bar


HOUR = 60 * 60


def test_hourly_source_is_collapsed_into_complete_4h_bars():
    bars = [
        Bar(index * HOUR, 100 + index, 102 + index, 99 + index, 101 + index, 10)
        for index in range(9)
    ]

    result = to_closed_4h(bars, 9 * HOUR)

    assert len(result) == 2
    assert result[0].ts == 0
    assert result[1].ts == FOUR_HOURS
    assert result[0].o == 100
    assert result[0].c == 104
    assert result[0].v == 40


def test_htf_gate_requires_positive_quality_and_controlled_drawdown():
    good = {
        "trades": 10,
        "return_pct": 2,
        "profit_factor": 1.2,
        "max_drawdown_pct": 5,
    }
    assert gate(good, 10)
    assert not gate({**good, "trades": 9}, 10)
    assert not gate({**good, "return_pct": -1}, 10)
    assert not gate({**good, "max_drawdown_pct": 13}, 10)
