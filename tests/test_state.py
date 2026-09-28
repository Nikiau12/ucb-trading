from trading import state


class _RuntimeConnection:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, query, params=None):
        self.calls.append((query, params))
        return self

    def commit(self):
        return None


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


def test_runtime_health_records_scanner_metrics(monkeypatch):
    connection = _RuntimeConnection()
    monkeypatch.setattr(state, "DATABASE_URL", "postgresql://test")
    monkeypatch.setattr(state.psycopg, "connect", lambda _url: connection)

    state.record_runtime_health(
        "plan_scanner",
        success=True,
        duration_seconds=12.5,
        details={"completed": 71, "failed": 0},
    )

    upsert = next(call for call in connection.calls if "INSERT INTO runtime_health" in call[0])
    assert upsert[1][0] == "plan_scanner"
    assert upsert[1][1] == "ok"
    assert '"completed": 71' in upsert[1][6]
