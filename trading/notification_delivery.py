"""Deliver queued trade lifecycle updates independently of market decisions."""

import logging

from trading.signal_updates import (
    render_cancelled_before_entry_update,
    render_stop_update,
    render_tp1_update,
)


logger = logging.getLogger("ucb.notification_delivery")


async def deliver_pending_signal_updates(
    loop, *, state, notifier, language_for_user, open_setup_keyboard,
) -> tuple[int, int]:
    """Attempt each queued update; one Telegram failure must not block the rest.

    The database owns retry timing and the unique delivery key. Telegram does
    not provide an idempotency key, so a crash after send but before DB ack can
    still cause a duplicate; this queue intentionally favours eventual delivery.
    """
    deliveries = await loop.run_in_executor(None, state.load_pending_signal_updates)
    delivered = 0
    for update in deliveries:
        user_id = int(update["telegram_user_id"])
        lang = language_for_user(user_id)
        event_type = update["event_type"]
        if event_type == "stop_reached":
            message = render_stop_update(update, lang=lang)
        elif event_type == "cancelled_before_entry":
            message = render_cancelled_before_entry_update(update, lang=lang)
        else:
            message = render_tp1_update(update, lang=lang)

        try:
            sent = await notifier.send_message_to_user(
                str(user_id), message, gated=False,
                reply_markup=open_setup_keyboard(update["id"], lang),
            )
        except Exception as exc:
            logger.warning(
                "signal update send failed signal_id=%s event=%s error=%s",
                update["id"], event_type, type(exc).__name__,
            )
            sent = False

        retry_seconds = min(900, 30 * (2 ** int(update.get("attempts") or 0)))
        await loop.run_in_executor(
            None,
            lambda item=update, ok=sent, delay=retry_seconds: state.mark_signal_update_delivery(
                item["id"], item["telegram_user_id"], item["event_type"],
                sent=ok,
                error="telegram_delivery_failed" if not ok else "",
                retry_seconds=delay,
            ),
        )
        delivered += int(bool(sent))
    return len(deliveries), delivered
