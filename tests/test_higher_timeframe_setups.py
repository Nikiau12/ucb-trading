from trading.analytics.structure import Bar
from trading.higher_timeframe_setups import (
    BTC_4H_DIAGNOSTIC_CANDIDATES,
    BTC_4H_1D_SETUPS,
    htf_plan_builder,
)


def snapshot(with_1h=False):
    return {
        "symbol": "BTC_USDT",
        "ticker": {"data": {"lastPrice": 105}},
        "kline_1h": {"data": [[0, 100, 101, 99, 100, 1]] if with_1h else []},
        "kline_4h": {"data": []},
        "kline_1d": {"data": []},
        "stale": False,
    }


def test_htf_builder_rejects_hourly_signal_input(monkeypatch):
    monkeypatch.setattr(
        "trading.higher_timeframe_setups.htf_features",
        lambda _snapshot: (_ for _ in ()).throw(AssertionError("must not read features")),
    )

    plan = htf_plan_builder(BTC_4H_1D_SETUPS[0])(
        snapshot(with_1h=True),
        deposit=1_000,
        risk_pct=1,
        lev=10,
        margin="cross",
    )

    assert plan["side"] == "skip"
    assert plan["reasons"] == ["unexpected_1h_signal_data"]


def test_diagnostic_candidates_are_small_and_explicit():
    assert len(BTC_4H_DIAGNOSTIC_CANDIDATES) == 3
    assert all(setup.allowed_sides == ("long",) for setup in BTC_4H_DIAGNOSTIC_CANDIDATES)


def test_htf_pullback_uses_daily_direction_and_closed_4h_reclaim(monkeypatch):
    bars = [Bar(index, 100, 103, 99, 102, 10) for index in range(80)]
    bars[-1] = Bar(79, 101, 106, 99, 105, 20)
    features = {
        "bars_4h": bars,
        "bars_1d": [],
        "atr_4h": 2.0,
        "adx_4h": 30.0,
        "ema20_4h": 100.0,
        "ema20_4h_series": [100.0] * 80,
        "trend_4h": "up",
        "trend_1d": "up",
        "volume_ratio": 2.0,
        "swing_highs": [],
        "swing_lows": [],
    }
    monkeypatch.setattr(
        "trading.higher_timeframe_setups.htf_features", lambda _snapshot: features
    )

    plan = htf_plan_builder(BTC_4H_1D_SETUPS[0])(
        snapshot(), deposit=1_000, risk_pct=1, lev=10, margin="cross"
    )

    assert plan["primary"]["side"] == "long"
    assert plan["primary"]["entry"] == 100
    assert "signal_timeframes=4h+1d" in plan["primary"]["reasons"]
    assert all("1h" not in reason for reason in plan["primary"]["reasons"])
