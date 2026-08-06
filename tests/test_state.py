from trading import state


def _duplicate_target_plan():
    return {
        "symbol": "XPL_USDT",
        "primary": {
            "side": "short",
            "entry": 0.0754,
            "stop": 0.07842,
            "tps": [{"price": 0.07325}, {"price": 0.07325}],
        },
    }


def test_invalid_plan_cannot_be_alerted_or_saved(monkeypatch):
    monkeypatch.setattr(state, "DATABASE_URL", "")
    plan = _duplicate_target_plan()

    assert state.should_send_alert("XPL_USDT", "short", 0.83, plan) is False
    assert state.save_signal(plan, "XPL_USDT", "short", 0.83) is None
