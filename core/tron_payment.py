from __future__ import annotations

import re
import time
from decimal import Decimal, InvalidOperation

import requests


USDT_TRC20_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
TX_HASH_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def _display_usdt(amount: Decimal) -> str:
    text = format(amount.quantize(Decimal("0.000001")), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


class TronPaymentVerifier:
    def __init__(self, wallet: str, amount, api_key: str = "", timeout: int = 15, max_age_hours: int = 72):
        self.wallet = str(wallet).strip()
        self.amount = Decimal(str(amount))
        self.api_key = str(api_key).strip()
        self.timeout = timeout
        self.max_age_seconds = max_age_hours * 60 * 60

    def verify(self, tx_hash: str, expected_amount=None) -> dict:
        tx_hash = str(tx_hash).strip().lower()
        if not TX_HASH_RE.fullmatch(tx_hash):
            return {"ok": False, "reason": "invalid_hash"}
        if not self.wallet:
            return {"ok": False, "reason": "wallet_not_configured"}
        exact_amount = None if expected_amount is None else Decimal(str(expected_amount))

        headers = {"accept": "application/json"}
        if self.api_key:
            headers["TRON-PRO-API-KEY"] = self.api_key
        url = f"https://api.trongrid.io/v1/accounts/{self.wallet}/transactions/trc20"
        response = requests.get(
            url,
            params={
                "only_confirmed": "true",
                "only_to": "true",
                "contract_address": USDT_TRC20_CONTRACT,
                "limit": 200,
            },
            headers=headers,
            timeout=self.timeout,
        )
        response.raise_for_status()

        for item in response.json().get("data", []):
            if str(item.get("transaction_id", "")).lower() != tx_hash:
                continue
            token = item.get("token_info") or {}
            if str(item.get("to", "")) != self.wallet:
                return {"ok": False, "reason": "wrong_recipient"}
            if str(token.get("address", "")) != USDT_TRC20_CONTRACT:
                return {"ok": False, "reason": "wrong_token"}
            if item.get("confirmed") is False:
                return {"ok": False, "reason": "not_confirmed"}
            block_timestamp = int(item.get("block_timestamp", 0) or 0)
            transaction_age = time.time() - block_timestamp / 1000
            if block_timestamp <= 0 or transaction_age < -300 or transaction_age > self.max_age_seconds:
                return {"ok": False, "reason": "transaction_expired"}
            try:
                decimals = int(token.get("decimals", 6))
                paid = Decimal(str(item.get("value", "0"))) / (Decimal(10) ** decimals)
            except (InvalidOperation, TypeError, ValueError):
                return {"ok": False, "reason": "invalid_amount"}
            paid = paid.quantize(Decimal("0.000001"))
            if exact_amount is not None:
                required = exact_amount.quantize(Decimal("0.000001"))
                if paid != required:
                    return {
                        "ok": False,
                        "reason": "amount_mismatch",
                    "paid_amount": _display_usdt(paid),
                    "required_amount": _display_usdt(required),
                }
            elif paid < self.amount:
                return {
                    "ok": False,
                    "reason": "amount_too_low",
                    "paid_amount": _display_usdt(paid),
                    "required_amount": str(self.amount),
                }
            return {
                "ok": True,
                "tx_hash": tx_hash,
                "paid_amount": _display_usdt(paid),
                "from_address": str(item.get("from", "")),
                "block_timestamp": block_timestamp,
            }
        return {"ok": False, "reason": "not_found"}
