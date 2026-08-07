from evaluation.sol_paper_trade import (
    FOUR_HOURS,
    advance_candle,
    migrate_empty_hourly_state,
    new_state,
)
from trading.analytics.structure import Bar


HOUR = 60 * 60


def pending(side="long"):
    return {
        "signal_time": FOUR_HOURS,
        "expires_at": 3 * FOUR_HOURS,
        "side": side,
        "confidence": 0.8,
        "entry": 100,
        "stop": 90 if side == "long" else 110,
        "tp1": 110 if side == "long" else 90,
        "tp2": 120 if side == "long" else 80,
        "qty": 1,
        "risk_usdt": 10,
    }


def test_paper_trade_uses_stop_first_on_fill_candle():
    state = new_state(FOUR_HOURS)
    state["pending"] = pending()
    candle = Bar(ts=FOUR_HOURS, o=100, h=121, l=89, c=105, v=1)

    advance_candle(state, candle)

    assert state["position"] is None
    assert state["trades"][0]["exit_reason"] == "stop"
    assert state["equity"] < 990


def test_paper_trade_scales_out_at_both_targets():
    state = new_state(FOUR_HOURS)
    state["pending"] = pending()
    advance_candle(state, Bar(ts=FOUR_HOURS, o=100, h=101, l=99, c=100, v=1))
    advance_candle(state, Bar(ts=2 * FOUR_HOURS, o=100, h=121, l=99, c=120, v=1))

    assert state["position"] is None
    assert state["trades"][0]["exit_reason"] == "tp2"
    assert state["trades"][0]["net_pnl"] > 14
    assert state["equity"] > 1_014


def test_expired_paper_order_is_removed_without_trade():
    state = new_state(FOUR_HOURS)
    state["pending"] = pending()
    advance_candle(state, Bar(ts=3 * FOUR_HOURS, o=120, h=121, l=119, c=120, v=1))

    assert state["pending"] is None
    assert state["position"] is None
    assert state["trades"] == []


def test_empty_hourly_state_migrates_without_hourly_signals():
    old = {
        "version": 1,
        "symbol": "SOL_USDT",
        "profile": "sol_trend_1h_confirmation",
        "started_at": HOUR,
        "last_candle_close": 2 * HOUR,
        "equity": 1_000.0,
        "pending": None,
        "position": None,
        "trades": [],
        "signals_rejected": 2,
    }

    migrated = migrate_empty_hourly_state(old, 10 * FOUR_HOURS)

    assert migrated["version"] == 2
    assert migrated["last_candle_close"] == 10 * FOUR_HOURS
    assert migrated["signal_timeframes"] == ["4h", "1d"]
    assert migrated["signals_rejected"] == 0
