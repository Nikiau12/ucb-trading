import math

import pytest

from trading.analytics.indicators import OHLC, atr, ema, rsi, volatility_regime
from trading.analytics.levels import cluster_levels, midrange_ratio, nearest_levels
from trading.analytics.structure import Swing, bos_choch, last_structure_bias


def test_ema_returns_expected_last_value_and_series():
    last, series = ema([10.0, 12.0, 14.0], 3, return_series=True)

    assert last == pytest.approx(12.5)
    assert series == pytest.approx([10.0, 11.0, 12.5])


def test_rsi_is_100_for_strictly_rising_prices():
    last, series = rsi([float(value) for value in range(1, 20)], length=5, return_series=True)

    assert last == 100.0
    assert len(series) == 19
    assert math.isnan(series[0])


def test_atr_uses_true_range():
    candles = [
        OHLC(10, 11, 9, 10),
        OHLC(10, 12, 9, 11),
        OHLC(11, 13, 10, 12),
        OHLC(12, 14, 11, 13),
        OHLC(13, 15, 12, 14),
    ]

    last, _ = atr(candles, length=2)

    assert last == pytest.approx(3.0)


@pytest.mark.parametrize(
    ("atr_value", "price", "expected"),
    [
        (1.0, 1000.0, "quiet"),
        (8.0, 1000.0, "normal"),
        (20.0, 1000.0, "wild"),
        (1.0, 0.0, "unknown"),
    ],
)
def test_volatility_regime(atr_value, price, expected):
    assert volatility_regime(atr_value, price) == expected


def test_price_levels_are_clustered_and_ranked_around_market_price():
    levels = cluster_levels([99.9, 100.0, 100.1, 104.9, 105.0], tol=0.2)
    support, resistance = nearest_levels(levels, 102.0)

    assert levels == pytest.approx([100.0, 104.95])
    assert support == pytest.approx(100.0)
    assert resistance == pytest.approx(104.95)
    assert midrange_ratio(support, resistance, 102.0) == pytest.approx(2.0 / 2.95)


def test_structure_bias_and_break_of_structure():
    highs = [Swing(1, 100.0, "H"), Swing(3, 105.0, "H")]
    lows = [Swing(2, 90.0, "L"), Swing(4, 95.0, "L")]

    assert last_structure_bias(highs, lows) == "up"
    assert bos_choch(highs, lows, 106.0) == "BOS_up"
    assert bos_choch(highs, lows, 94.0) == "CHOCH_down"

