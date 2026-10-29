from datetime import datetime, timedelta, timezone

from trading import state
from trading.signal_updates import (
    advance_lifecycle,
    render_tp1_update,
    replay_lifecycle,
    signal_identity_footer,
)


NOW = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)


def _signal(**changes):
    value = {
        "id": 1842,
        "symbol": "ASTER_USDT",
        "side": "LONG",
        "entry": 1.082,
        "stop": 1.041,
        "tp1": 1.13,
        "tp2": 1.176,
        "price_unit": 0.001,
        "created_at": NOW - timedelta(hours=2),
        "status": "waiting_entry",
        "entry_expires_at": NOW + timedelta(hours=4),
        "holding_expires_at": None,
    }
    value.update(changes)
    return value


def test_long_lifecycle_waits_for_entry_then_reaches_tp1():
    waiting = advance_lifecycle(_signal(), 1.09, NOW)
    assert waiting == {"status": "waiting_entry", "events": []}

    entered = advance_lifecycle(_signal(), 1.082, NOW)
    assert entered["status"] == "active"
    assert entered["events"] == ["entry_reached"]

    tp1 = advance_lifecycle(_signal(status="active"), 1.13, NOW)
    assert tp1 == {"status": "tp1_reached", "events": ["tp1_reached"]}


def test_short_lifecycle_reverses_price_comparisons():
    short = _signal(
        side="SHORT", entry=10, stop=11, tp1=9, tp2=8,
        status="waiting_entry",
    )
    assert advance_lifecycle(short, 9.8, NOW)["status"] == "waiting_entry"
    assert advance_lifecycle(short, 10, NOW)["status"] == "active"
    assert advance_lifecycle({**short, "status": "active"}, 9, NOW)["status"] == "tp1_reached"


def test_direct_tp2_jump_does_not_end_in_break_even_state():
    outcome = advance_lifecycle(_signal(status="active"), 1.20, NOW)
    assert outcome["status"] == "tp2_reached"
    assert "tp2_reached" in outcome["events"]


def test_tp1_remainder_closes_at_break_even_before_tp2():
    outcome = advance_lifecycle(_signal(status="tp1_reached"), 1.081, NOW)
    assert outcome == {"status": "stopped", "events": ["stop_reached"]}


def test_pending_signal_expires_without_entry():
    outcome = advance_lifecycle(
        _signal(entry_expires_at=NOW - timedelta(seconds=1)),
        None,
        NOW,
    )
    assert outcome == {"status": "expired", "events": ["expired"]}


def _candle(hours_ago, *, high, low):
    moment = NOW - timedelta(hours=hours_ago)
    return {"time": int(moment.timestamp()), "high": high, "low": low}


def test_replay_restores_old_signal_that_is_waiting_after_tp1():
    old = _signal(
        created_at=NOW - timedelta(hours=10),
        entry_expires_at=NOW + timedelta(hours=2),
        max_holding_seconds=14 * 86400,
    )
    result = replay_lifecycle(old, [
        _candle(9, high=1.09, low=1.08),
        _candle(5, high=1.14, low=1.10),
    ], NOW)
    assert result["status"] == "tp1_reached"
    assert result["entry_hit_at"] == NOW - timedelta(hours=9)
    assert result["tp1_hit_at"] == NOW - timedelta(hours=5)


def test_replay_does_not_resurrect_signal_that_later_hit_stop():
    old = _signal(
        created_at=NOW - timedelta(hours=10),
        entry_expires_at=NOW + timedelta(hours=2),
        max_holding_seconds=14 * 86400,
    )
    result = replay_lifecycle(old, [
        _candle(9, high=1.09, low=1.08),
        _candle(5, high=1.14, low=1.10),
        _candle(2, high=1.12, low=1.03),
    ], NOW)
    assert result["status"] == "stopped"
    assert result["tp1_hit_at"] == NOW - timedelta(hours=5)
    assert result["stop_hit_at"] == NOW - timedelta(hours=2)


def test_replay_uses_entry_as_break_even_after_tp1():
    old = _signal(
        created_at=NOW - timedelta(hours=10),
        entry_expires_at=NOW + timedelta(hours=2),
        max_holding_seconds=14 * 86400,
    )
    result = replay_lifecycle(old, [
        _candle(9, high=1.09, low=1.08),
        _candle(5, high=1.14, low=1.10),
        _candle(2, high=1.11, low=1.08),
    ], NOW)
    assert result["status"] == "stopped"
    assert result["stop_hit_at"] == NOW - timedelta(hours=2)


def test_replay_expires_old_signal_that_never_entered():
    old = _signal(
        created_at=NOW - timedelta(hours=20),
        entry_expires_at=NOW - timedelta(hours=8),
        max_holding_seconds=14 * 86400,
    )
    result = replay_lifecycle(old, [_candle(15, high=1.20, low=1.10)], NOW)
    assert result["status"] == "expired"
    assert result["entry_hit_at"] is None


def test_replay_ignores_current_unclosed_hour():
    old = _signal(
        created_at=NOW - timedelta(hours=3),
        entry_expires_at=NOW + timedelta(hours=9),
        max_holding_seconds=14 * 86400,
    )
    current_hour = {
        "time": int((NOW - timedelta(minutes=20)).timestamp()),
        "high": 1.20,
        "low": 1.00,
    }
    result = replay_lifecycle(old, [current_hour], NOW)
    assert result["status"] == "waiting_entry"


def test_trade_reference_and_tp1_message_are_unambiguous():
    footer = signal_identity_footer(
        1842, "ASTER_USDT", "LONG", lang="ru", created_at=NOW,
    )
    assert "Сделка #1842" in footer
    assert "ASTER_USDT · LONG" in footer
    assert "29.10.2026 12:00 UTC" in footer

    message = render_tp1_update(_signal(), lang="ru")
    assert "TP1 достигнут" in message
    assert "Зафиксируйте 50%" in message
    assert "безубыток" in message
    assert "1.082" in message


def test_lifecycle_duration_uses_4h_plan_bars():
    assert state._signal_lifecycle_durations({
        "primary": {"entry_expiry_bars": 2, "max_holding_bars": 42}
    }) == (8 * 3600, 168 * 3600)


class _LifecycleConnection:
    def __init__(self, row):
        self.row = row
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, query, params=None):
        self.calls.append((query, params))
        return self

    def fetchone(self):
        return self.row

    def commit(self):
        return None


def test_tp1_transition_atomically_enqueues_original_recipients(monkeypatch):
    row = (
        1842, "ASTER_USDT", "LONG", 1.082, 1.041, 1.13, 1.176,
        NOW - timedelta(hours=2), 0.001, "active",
        NOW + timedelta(hours=2), NOW + timedelta(days=7), 7 * 86400,
        NOW - timedelta(hours=1), None, None, None, None,
    )
    connection = _LifecycleConnection(row)
    monkeypatch.setattr(state, "DATABASE_URL", "postgresql://test")
    monkeypatch.setattr(state.psycopg, "connect", lambda _url: connection)

    result = state.update_signal_lifecycle(1842, 1.13, checked_at=NOW)

    assert result["status"] == "tp1_reached"
    assert any("UPDATE signal_lifecycle" in query for query, _ in connection.calls)
    assert any("INSERT INTO signal_update_deliveries" in query for query, _ in connection.calls)
