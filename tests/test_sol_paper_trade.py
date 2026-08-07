from evaluation.sol_paper_trade import advance_candle, new_state
from trading.analytics.structure import Bar


HOUR = 60 * 60


def pending(side="long"):
    return {
        "signal_time": HOUR,
        "expires_at": 13 * HOUR,
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
    state = new_state(HOUR)
    state["pending"] = pending()
    candle = Bar(ts=HOUR, o=100, h=121, l=89, c=105, v=1)

    advance_candle(state, candle)

    assert state["position"] is None
    assert state["trades"][0]["exit_reason"] == "stop"
    assert state["equity"] < 990


def test_paper_trade_scales_out_at_both_targets():
    state = new_state(HOUR)
    state["pending"] = pending()
    advance_candle(state, Bar(ts=HOUR, o=100, h=101, l=99, c=100, v=1))
    advance_candle(state, Bar(ts=2 * HOUR, o=100, h=121, l=99, c=120, v=1))

    assert state["position"] is None
    assert state["trades"][0]["exit_reason"] == "tp2"
    assert state["trades"][0]["net_pnl"] > 14
    assert state["equity"] > 1_014


def test_expired_paper_order_is_removed_without_trade():
    state = new_state(HOUR)
    state["pending"] = pending()
    advance_candle(state, Bar(ts=13 * HOUR, o=120, h=121, l=119, c=120, v=1))

    assert state["pending"] is None
    assert state["position"] is None
    assert state["trades"] == []
