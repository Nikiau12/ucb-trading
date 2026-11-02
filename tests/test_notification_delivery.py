import asyncio
from datetime import datetime, timezone

from trading.notification_delivery import deliver_pending_signal_updates


def _update(user_id, event_type="tp1_reached"):
    return {
        "id": 1842,
        "telegram_user_id": user_id,
        "event_type": event_type,
        "attempts": 0,
        "symbol": "ASTER_USDT",
        "side": "LONG",
        "entry": 1.082,
        "stop": 1.041,
        "tp1": 1.13,
        "created_at": datetime(2026, 10, 29, 12, tzinfo=timezone.utc),
        "price_unit": 0.001,
        "tp1_hit_at": None,
    }


class _DeliveryState:
    def __init__(self, deliveries):
        self.deliveries = deliveries
        self.marked = []

    def load_pending_signal_updates(self):
        return [item.copy() for item in self.deliveries if not item.get("sent")]

    def mark_signal_update_delivery(
        self, signal_id, user_id, event_type, *, sent, error, retry_seconds,
    ):
        self.marked.append((signal_id, user_id, event_type, sent, error, retry_seconds))
        item = next(
            row for row in self.deliveries
            if row["id"] == signal_id
            and row["telegram_user_id"] == user_id
            and row["event_type"] == event_type
        )
        item["attempts"] += 1
        item["sent"] = sent


class _Notifier:
    def __init__(self, outcomes):
        self.outcomes = outcomes
        self.calls = []

    async def send_message_to_user(self, chat_id, text, **kwargs):
        self.calls.append((chat_id, text, kwargs))
        outcome = self.outcomes[chat_id].pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_failed_or_raised_send_does_not_block_other_users_and_retries_once():
    state = _DeliveryState([_update(1), _update(2), _update(3)])
    notifier = _Notifier({
        "1": [False, True],
        "2": [RuntimeError("telegram unavailable"), True],
        "3": [True],
    })

    async def run_twice():
        loop = asyncio.get_running_loop()
        args = {
            "state": state,
            "notifier": notifier,
            "language_for_user": lambda _user_id: "ru",
            "open_setup_keyboard": lambda signal_id, _lang: f"open:{signal_id}",
        }
        first = await deliver_pending_signal_updates(loop, **args)
        second = await deliver_pending_signal_updates(loop, **args)
        third = await deliver_pending_signal_updates(loop, **args)
        return first, second, third

    assert asyncio.run(run_twice()) == ((3, 1), (2, 2), (0, 0))
    assert [item[1] for item in state.marked] == [1, 2, 3, 1, 2]
    assert [item[5] for item in state.marked] == [30, 30, 30, 60, 60]
    assert all(item["sent"] for item in state.deliveries)
    assert all(call[2]["gated"] is False for call in notifier.calls)
    assert all(call[2]["reply_markup"] == "open:1842" for call in notifier.calls)


def test_delivery_uses_specific_text_for_stop_and_cancelled_setups():
    state = _DeliveryState([
        _update(1, "stop_reached"),
        _update(2, "cancelled_before_entry"),
    ])
    notifier = _Notifier({"1": [True], "2": [True]})

    async def run():
        return await deliver_pending_signal_updates(
            asyncio.get_running_loop(),
            state=state,
            notifier=notifier,
            language_for_user=lambda _user_id: "ru",
            open_setup_keyboard=lambda *_args: None,
        )

    assert asyncio.run(run()) == (2, 2)
    assert "Stop сработал" in notifier.calls[0][1]
    assert "Сигнал аннулирован до входа" in notifier.calls[1][1]
