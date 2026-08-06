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


def test_signal_contract_rules_are_extracted_for_history():
    plan = {
        "primary": {
            "price_unit": 0.1,
            "contract_size": 0.001,
            "vol_unit": 1,
            "min_vol": 1,
            "max_vol": 1000,
            "max_leverage": 50,
        }
    }

    assert state._signal_contract_rules(plan) == {
        "price_unit": 0.1,
        "contract_size": 0.001,
        "vol_unit": 1,
        "min_vol": 1,
        "max_vol": 1000,
        "max_leverage": 50,
    }
