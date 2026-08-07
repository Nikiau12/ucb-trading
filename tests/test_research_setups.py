from trading.analytics.structure import Bar
from trading.research_setups import (
    BTCSetup,
    ETHSetup,
    btc_plan_builder,
    eth_plan_builder,
)


def _snapshot(symbol):
    return {
        "symbol": symbol,
        "ticker": {"data": {"lastPrice": 100}},
        "stale": False,
    }


def test_btc_breakout_builder_creates_a_closed_candle_plan(monkeypatch):
    bars = [Bar(index, 99, 101, 98, 100, 10) for index in range(25)]
    bars[-1] = Bar(24, 100, 106, 99, 105, 20)
    features = {
        "bars_1h": bars,
        "atr_1h": 2.0,
        "atr_percentile": 50.0,
        "volume_ratio": 2.0,
        "ema_slope_atr": 0.2,
        "ema20_4h": 110.0,
        "ema50_4h": 100.0,
        "ema20_1h": 101.0,
        "ema20_1h_series": [100.0] * 25,
    }
    monkeypatch.setattr(
        "trading.research_setups.closed_market_features", lambda _snapshot: features
    )
    builder = btc_plan_builder(
        BTCSetup("test_breakout", "breakout", 20, ("long",), 1.0, 0.0, 100.0)
    )

    plan = builder(
        _snapshot("BTC_USDT"), deposit=1_000, risk_pct=1, lev=10, margin="cross"
    )

    assert plan["primary"]["side"] == "long"
    assert plan["primary"]["entry"] == 105
    assert plan["primary"]["stop"] < 105 < plan["primary"]["tps"][0]["price"]


def test_eth_range_builder_rejects_bad_reward(monkeypatch):
    bars = [Bar(index, 100, 101, 99, 100, 10) for index in range(25)]
    bars[-1] = Bar(24, 99, 100, 90, 99.5, 10)
    features = {
        "bars_1h": bars,
        "closes_1h": [bar.c for bar in bars],
        "atr_1h": 2.0,
        "atr_percentile": 50.0,
        "adx_4h": 15.0,
    }
    monkeypatch.setattr(
        "trading.research_setups.closed_market_features", lambda _snapshot: features
    )
    monkeypatch.setattr(
        "trading.research_setups._bands", lambda *_args: (102.0, 99.0, 105.0)
    )
    builder = eth_plan_builder(ETHSetup("test_range", 20, 1.5, ("long",)))

    plan = builder(
        _snapshot("ETH_USDT"), deposit=1_000, risk_pct=1, lev=10, margin="cross"
    )

    assert plan["side"] == "skip"
    assert "eth_range_reward_too_small" in plan["reasons"]


def test_eth_range_builder_creates_plan_when_reclaim_has_enough_reward(monkeypatch):
    bars = [Bar(index, 102, 103, 101, 102, 10) for index in range(25)]
    bars[-1] = Bar(24, 99.0, 100.2, 98.8, 100.0, 10)
    closes = [102.0] * 10 + [101.0, 103.0] * 7 + [100.0]
    features = {
        "bars_1h": bars,
        "closes_1h": closes,
        "atr_1h": 1.0,
        "atr_percentile": 50.0,
        "adx_4h": 15.0,
    }
    monkeypatch.setattr(
        "trading.research_setups.closed_market_features", lambda _snapshot: features
    )
    monkeypatch.setattr(
        "trading.research_setups._bands", lambda *_args: (102.0, 99.0, 105.0)
    )
    builder = eth_plan_builder(ETHSetup("test_range", 20, 1.5, ("long",)))

    plan = builder(
        _snapshot("ETH_USDT"), deposit=1_000, risk_pct=1, lev=10, margin="cross"
    )

    assert plan.get("primary", {}).get("side") == "long"
    assert plan["primary"]["tps"][1]["price"] > plan["primary"]["tps"][0]["price"]
