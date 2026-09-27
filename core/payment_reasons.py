"""Map TronGrid and invoice failures to distinct user-facing copy keys."""

PAYMENT_REASON_KEYS = {
    "invalid_hash": "payment_invalid_hash",
    "amount_too_low": "payment_amount_low",
    "amount_mismatch": "payment_amount_low",
    "wallet_not_configured": "payment_wallet_missing",
    "transaction_expired": "payment_expired",
    "wrong_recipient": "payment_wrong_recipient",
    "wrong_token": "payment_wrong_token",
    "not_confirmed": "payment_unconfirmed",
    "invalid_amount": "payment_invalid_amount",
    "not_found": "payment_not_found",
    "no_invoice": "payment_no_invoice",
    "tx_used": "payment_tx_used",
    "save_failed": "payment_save_failed",
}


def payment_reason_key(reason: str | None) -> str:
    return PAYMENT_REASON_KEYS.get(str(reason or ""), "payment_not_found")
