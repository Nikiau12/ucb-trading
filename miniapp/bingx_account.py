"""Per-user, read-only BingX futures access. Never log signed URLs or credentials."""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import time
from urllib.parse import urlencode

import requests
from cryptography.fernet import Fernet, InvalidToken


class AccountUnavailable(RuntimeError):
    pass


def _cipher():
    try:
        return Fernet(os.environ["BINGX_CREDENTIALS_KEY"].encode())
    except (KeyError, ValueError, TypeError):
        raise AccountUnavailable("account_encryption_not_configured") from None


def encrypt_credentials(user_id, api_key, secret):
    return _cipher().encrypt(json.dumps({"user_id": int(user_id), "key": api_key, "secret": secret}).encode()).decode()


def decrypt_credentials(user_id, encrypted):
    try:
        value = json.loads(_cipher().decrypt(encrypted.encode()))
        if value["user_id"] != int(user_id):
            raise ValueError("owner mismatch")
        return value["key"], value["secret"]
    except (InvalidToken, ValueError, KeyError, TypeError):
        raise AccountUnavailable("account_credentials_unavailable") from None


class BingxAccountClient:
    # Fixed host and allowlist: a user's secrets cannot reach arbitrary URLs.
    PATHS = frozenset({"/openApi/swap/v3/user/balance", "/openApi/swap/v2/user/positions",
                       "/openApi/swap/v2/trade/openOrders", "/openApi/swap/v2/trade/order"})

    def __init__(self, api_key, secret, request_get=None, clock=time.time):
        self._api_key = api_key
        self._secret = secret
        self._get = request_get or requests.get
        self._clock = clock
        self._last_request_at = 0.0

    def get(self, path, **params):
        if path not in self.PATHS:
            raise ValueError("unsupported_read_operation")
        delay = 0.25 - (time.monotonic() - self._last_request_at)
        if delay > 0:
            time.sleep(delay)
        self._last_request_at = time.monotonic()
        params.update(timestamp=int(self._clock() * 1000), recvWindow=5000)
        query = urlencode(sorted(params.items()))
        signature = hmac.new(self._secret.encode(), query.encode(), hashlib.sha256).hexdigest()
        try:
            response = self._get("https://open-api.bingx.com" + path + "?" + query + "&signature=" + signature,
                                 headers={"X-BX-APIKEY": self._api_key}, timeout=10, allow_redirects=False)
            if response.status_code != 200:
                raise ValueError("http_error")
            payload = response.json()
            if int(payload.get("code", -1)) != 0:
                raise ValueError("api_error")
            return payload["data"]
        except (requests.RequestException, ValueError, KeyError, TypeError):
            raise AccountUnavailable("bingx_account_unavailable") from None

    def balance(self):
        rows = self.get("/openApi/swap/v3/user/balance")
        try:
            row = next(row for row in rows if row.get("asset") == "USDT")
            balance = float(row["balance"])
            if not math.isfinite(balance) or balance < 0:
                raise ValueError()
            return balance
        except (StopIteration, ValueError, KeyError, TypeError, AttributeError):
            raise AccountUnavailable("bingx_balance_unavailable") from None

    def positions(self, symbol):
        data = self.get("/openApi/swap/v2/user/positions", symbol=symbol.replace("_", "-"))
        if not isinstance(data, list):
            raise AccountUnavailable("bingx_positions_unavailable")
        return data

    def open_orders(self, symbol):
        data = self.get("/openApi/swap/v2/trade/openOrders", symbol=symbol.replace("_", "-"))
        rows = data.get("orders") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            raise AccountUnavailable("bingx_orders_unavailable")
        return rows

    def order(self, symbol, order_id):
        data = self.get("/openApi/swap/v2/trade/order", symbol=symbol.replace("_", "-"), orderId=order_id)
        row = data.get("order", data) if isinstance(data, dict) else None
        if not isinstance(row, dict):
            raise AccountUnavailable("bingx_order_unavailable")
        return row


def account_client(connection, user_id):
    row = connection.execute("SELECT credentials FROM bingx_accounts WHERE telegram_user_id=%s FOR UPDATE", (user_id,)).fetchone()
    return BingxAccountClient(*decrypt_credentials(user_id, row[0])) if row else None


def refresh_balance(connection, user_id):
    client = account_client(connection, user_id)
    if client is None:
        return None
    value = client.balance()
    connection.execute("UPDATE bingx_accounts SET balance=%s, balance_checked_at=NOW() WHERE telegram_user_id=%s", (value, user_id))
    connection.execute("UPDATE user_profiles SET deposit=%s, updated_at=NOW() WHERE telegram_user_id=%s", (value, user_id))
    return value


def connect_account(connection, user_id, api_key, secret):
    encrypted = encrypt_credentials(user_id, api_key, secret)
    client = BingxAccountClient(api_key, secret)
    balance = client.balance()
    # Verify the two permissions needed for execution tracking, without sending orders.
    client.positions("BTC_USDT")
    client.open_orders("BTC_USDT")
    connection.execute("INSERT INTO user_profiles (telegram_user_id) VALUES (%s) ON CONFLICT DO NOTHING", (user_id,))
    connection.execute("""INSERT INTO bingx_accounts (telegram_user_id, credentials, key_hint, balance, balance_checked_at)
        VALUES (%s,%s,%s,%s,NOW()) ON CONFLICT (telegram_user_id) DO UPDATE SET
        credentials=EXCLUDED.credentials, key_hint=EXCLUDED.key_hint, balance=EXCLUDED.balance,
        balance_checked_at=NOW(), updated_at=NOW()""", (user_id, encrypted, api_key[-4:], balance))
    connection.execute("UPDATE user_profiles SET deposit=%s, updated_at=NOW() WHERE telegram_user_id=%s", (balance,user_id))
    # Reconnecting may select a different exchange account. Old bindings must not be reused.
    connection.execute("UPDATE user_trade_tracking SET position_id=NULL,tp1_order_id=NULL,execution_state='unverified' WHERE telegram_user_id=%s AND status='active'", (user_id,))
    connection.execute("UPDATE signal_update_deliveries SET status='sent',last_error='account_reconnected' WHERE telegram_user_id=%s AND event_type='tp1_filled' AND status IN ('pending','failed')", (user_id,))
    return balance


def account_status(connection, user_id):
    row = connection.execute("SELECT key_hint,balance,balance_checked_at FROM bingx_accounts WHERE telegram_user_id=%s", (user_id,)).fetchone()
    return {"connected": bool(row), "key_hint": row[0] if row else None,
            "balance": float(row[1]) if row and row[1] is not None else None,
            "checked_at": row[2].isoformat() if row and row[2] else None}
