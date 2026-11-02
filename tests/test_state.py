import time

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

    def fetchone(self):
        return (9,)


class _ScannerConnection(_RuntimeConnection):
    def __init__(self, existing_rows):
        super().__init__()
        self.existing_rows = existing_rows

    def fetchall(self):
        return self.existing_rows


def _scanner_plan(symbol="LTC_USDT"):
    return {
        "symbol": symbol,
        "price": 55.9,
        "primary": {
            "side": "short", "entry": 55.99, "stop": 57.58,
            "tps": [{"price": 54.39}, {"price": 52.79}],
        },
    }


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


def test_alert_dedup_does_not_reset_identical_setup_after_four_hours():
    now = time.time()
    levels = {"entry": 55.99, "stop": 57.58, "tp1": 54.39, "tp2": 52.79}
    previous = {"side": "SHORT", **levels, "ts": now - 5 * 3600}

    assert not state._alert_is_allowed(previous, "SHORT", levels, now)
    assert state._alert_is_allowed(
        previous, "SHORT", {"entry": 53, "stop": 55, "tp1": 50, "tp2": 48}, now
    )
    assert state._alert_is_allowed(
        {**previous, "ts": now - state.SIGNAL_SETUP_REUSE_SECS - 1},
        "SHORT", levels, now,
    )


def test_scanner_rejects_any_open_trade_for_same_coin():
    now = time.time()
    levels = state._plan_levels(_scanner_plan())
    for symbol in ("BTC_USDT", "ETH_USDT", "SOL_USDT", "LTC_USDT"):
        for status in state.OPEN_SIGNAL_STATUSES:
            connection = _ScannerConnection([
                ("SHORT", 55.99, 57.58, 54.39, 52.79, now - 5 * 3600, status)
            ])
            assert not state._scanner_signal_is_allowed(connection, symbol, "LONG", levels, now)
            assert connection.calls[0][1][0] == symbol


def test_scanner_rejects_recycled_levels_after_terminal_trade():
    now = time.time()
    connection = _ScannerConnection([
        ("SHORT", 55.99, 57.58, 54.39, 52.79, now - 5 * 3600, "cancelled_before_entry")
    ])
    same_levels = state._plan_levels(_scanner_plan())
    assert not state._scanner_signal_is_allowed(connection, "LTC_USDT", "SHORT", same_levels, now)
    assert state._scanner_signal_is_allowed(
        connection, "LTC_USDT", "SHORT",
        {"entry": 53, "stop": 55, "tp1": 50, "tp2": 48}, now,
    )


def test_scanner_save_rechecks_under_transaction_lock(monkeypatch):
    now = time.time()
    connection = _ScannerConnection([
        ("SHORT", 55.99, 57.58, 54.39, 52.79, now - 5 * 3600, "active")
    ])
    monkeypatch.setattr(state, "DATABASE_URL", "postgresql://test")
    monkeypatch.setattr(state.psycopg, "connect", lambda _url: connection)

    assert state.save_signal(_scanner_plan(), "LTC_USDT", "SHORT", 0.83) is None
    assert "pg_advisory_xact_lock" in connection.calls[0][0]
    assert not any("INSERT INTO signals" in query for query, _ in connection.calls)


def test_scanner_can_save_distinct_setup_after_terminal_trade(monkeypatch):
    now = time.time()
    connection = _ScannerConnection([
        ("SHORT", 51, 53, 49, 47, now - 5 * 3600, "stopped")
    ])
    monkeypatch.setattr(state, "DATABASE_URL", "postgresql://test")
    monkeypatch.setattr(state.psycopg, "connect", lambda _url: connection)

    assert state.save_signal(_scanner_plan(), "LTC_USDT", "SHORT", 0.83) == 9
    assert any("INSERT INTO signals" in query for query, _ in connection.calls)


def test_signal_contract_rules_are_extracted_for_history():
    plan = {
        "primary": {
            "price_unit": 0.1,
            "contract_size": 0.001,
            "vol_unit": 1,
            "min_vol": 1,
            "max_vol": 1000,
            "max_leverage": 50,
            "min_notional": 2,
        }
    }

    assert state._signal_contract_rules(plan) == {
        "price_unit": 0.1,
        "contract_size": 0.001,
        "vol_unit": 1,
        "min_vol": 1,
        "max_vol": 1000,
        "max_leverage": 50,
        "min_notional": 2,
    }


def test_personal_alerts_are_not_published_to_the_scanner_feed(monkeypatch):
    connection = _RuntimeConnection()
    monkeypatch.setattr(state, "DATABASE_URL", "postgresql://test")
    monkeypatch.setattr(state.psycopg, "connect", lambda _url: connection)

    assert state.save_alert_signal("BTC_USDT", "LONG", 0.78, source="scanner") is None
    assert state.save_alert_signal("BTC_USDT", "LONG", 0.78, source="manual") is None
    assert connection.calls == []

    saved = state.save_alert_signal(
        "BTC/USDT",
        "SHORT",
        1.4,
        source="spike",
        price=10,
        entry=10,
    )
    assert saved == 9
    params = connection.calls[0][1]
    assert params[0] == "BTC_USDT"
    assert params[1] == "SHORT"
    assert params[2] == 1.0
    assert params[-1] == "spike"

    monkeypatch.setattr(state, "plan_payload_errors", lambda _plan: [])
    state.save_signal({"primary": {}}, "ETH_USDT", "LONG", 0.78, source="manual")
    assert connection.calls[1][1][-1] == "manual"


def test_signal_context_stores_reason_regime_and_timeframe():
    reason, regime, timeframe = state.signal_context({
        "trend": {"1d": "up", "4h": "down", "regime": "trend"},
        "primary": {"reasons": ["trend_1d=up", "entry_dist_ATR4h=1.2", "regime=trend"]},
    })
    assert "trend_1d=up" in reason
    assert "entry" not in reason
    assert "midrange" not in reason
    assert "deposit" not in reason
    assert regime == "1d=up;4h=down;regime=trend"
    assert timeframe == "4h"


def test_save_signal_persists_setup_context(monkeypatch):
    connection = _RuntimeConnection()
    monkeypatch.setattr(state, "DATABASE_URL", "postgresql://test")
    monkeypatch.setattr(state.psycopg, "connect", lambda _url: connection)
    monkeypatch.setattr(state, "plan_payload_errors", lambda _plan: [])
    state.save_signal(
        {
            "price": 100,
            "trend": {"1d": "up", "4h": "down", "regime": "trend"},
            "primary": {
                "entry": 99,
                "stop": 90,
                "tps": [],
                "reasons": ["trend_1d=up", "entry_dist_ATR4h=0.4"],
            },
        },
        "ETH_USDT",
        "LONG",
        0.78,
        source="manual",
    )
    params = connection.calls[0][1]
    assert params[-1] == "manual"
    assert params[-2] == "4h"
    assert params[-3] == "1d=up;4h=down;regime=trend"
    assert "trend_1d=up" in params[-4]
    assert "entry" not in params[-4]


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
