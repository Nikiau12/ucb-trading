"""Per-user payment invoices and the single transaction that grants access."""

from __future__ import annotations

import json
import logging
from decimal import Decimal

from psycopg.types.json import Json

try:
    from .invoice_amount import format_usdt, quantize_usdt, unique_invoice_amount
except ImportError:
    from invoice_amount import format_usdt, quantize_usdt, unique_invoice_amount

logger = logging.getLogger("ucb.billing")


class PaymentRejected(Exception):
    """A settle attempt that must roll back and must not look like success."""

    def __init__(self, result: dict):
        super().__init__(result.get("reason", "rejected"))
        self.result = result


def ensure_open_invoice(connection, user_id: int, base_amount) -> dict | None:
    """Return the user's open invoice, creating one with a unique amount."""
    for _attempt in range(5):
        try:
            with connection.transaction():
                existing = connection.execute(
                    """
                    SELECT id, expected_amount::text
                    FROM payment_invoices
                    WHERE telegram_user_id = %s AND status = 'open'
                    FOR UPDATE
                    """,
                    (int(user_id),),
                ).fetchone()
                if existing:
                    return {
                        "id": existing[0],
                        "expected_amount": format_usdt(existing[1]),
                    }
                used = connection.execute(
                    """
                    SELECT expected_amount::text
                    FROM payment_invoices
                    WHERE status = 'open'
                       OR created_at > NOW() - INTERVAL '72 hours'
                    """
                ).fetchall()
                amount = unique_invoice_amount(
                    base_amount,
                    int(user_id),
                    {Decimal(row[0]) for row in used},
                )
                created = connection.execute(
                    """
                    INSERT INTO payment_invoices (
                        telegram_user_id, expected_amount, base_amount, status
                    )
                    VALUES (%s, %s, %s, 'open')
                    RETURNING id, expected_amount::text
                    """,
                    (int(user_id), amount, quantize_usdt(base_amount)),
                ).fetchone()
                return {"id": created[0], "expected_amount": format_usdt(created[1])}
        except Exception as exc:
            if exc.__class__.__name__ != "UniqueViolation":
                logger.warning("invoice create failed: %s", type(exc).__name__)
                return None
    return None


def settle_payment_transaction(
    connection,
    *,
    user_id: int,
    tx_hash: str,
    paid_amount,
    expected_amount,
    duration_seconds: int,
    details: dict | None = None,
) -> dict:
    """Reserve the hash and extend paid_until. Caller commits only on success.

    Any failure raises or returns ok=False before commit. A returned failure
    must be rolled back by the caller so the hash is not burned.
    """
    expected = quantize_usdt(expected_amount)
    paid = quantize_usdt(paid_amount)
    if paid != expected:
        return {
            "ok": False,
            "reason": "amount_mismatch",
            "paid_amount": format_usdt(paid),
            "required_amount": format_usdt(expected),
        }

    invoice = connection.execute(
        """
        SELECT id, expected_amount::text
        FROM payment_invoices
        WHERE telegram_user_id = %s AND status = 'open'
        FOR UPDATE
        """,
        (int(user_id),),
    ).fetchone()
    if not invoice:
        return {"ok": False, "reason": "no_invoice"}
    invoice_amount = quantize_usdt(invoice[1])
    if invoice_amount != expected:
        return {
            "ok": False,
            "reason": "amount_mismatch",
            "paid_amount": format_usdt(paid),
            "required_amount": format_usdt(invoice_amount),
        }

    normalized = str(tx_hash).strip().lower()
    claimed = connection.execute(
        """
        INSERT INTO payment_claims (tx_hash, telegram_user_id, status, details)
        VALUES (%s, %s, 'approved', %s)
        ON CONFLICT (tx_hash) DO NOTHING
        RETURNING tx_hash
        """,
        (normalized, int(user_id), Json(details or {})),
    ).fetchone()
    if claimed is None:
        return {"ok": False, "reason": "tx_used"}

    granted = connection.execute(
        """
        INSERT INTO subscriptions (
            telegram_user_id, paid_until, payment_status, paywall_sent
        )
        VALUES (
            %s,
            NOW() + (%s * INTERVAL '1 second'),
            'approved',
            FALSE
        )
        ON CONFLICT (telegram_user_id) DO UPDATE SET
            paid_until = GREATEST(COALESCE(subscriptions.paid_until, NOW()), NOW())
                + (%s * INTERVAL '1 second'),
            payment_status = 'approved',
            paywall_sent = FALSE,
            updated_at = NOW()
        RETURNING EXTRACT(EPOCH FROM paid_until)
        """,
        (int(user_id), int(duration_seconds), int(duration_seconds)),
    ).fetchone()
    if not granted or granted[0] is None:
        raise RuntimeError("subscription update did not return paid_until")

    invoice_update = connection.execute(
        """
        UPDATE payment_invoices
        SET status = 'paid', tx_hash = %s, paid_at = NOW()
        WHERE id = %s AND status = 'open'
        """,
        (normalized, invoice[0]),
    )
    if invoice_update.rowcount != 1:
        raise RuntimeError("invoice was not marked paid")
    return {"ok": True, "paid_until": int(float(granted[0])), "tx_hash": normalized}


def payment_details_json(details: dict | None) -> str:
    return json.dumps(details or {})
