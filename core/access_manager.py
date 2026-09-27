import logging
import threading
import time
from typing import Dict, Tuple

try:
    import psycopg
except ImportError:
    psycopg = None


logger = logging.getLogger("ucb.access")


def trial_wait_seconds(user: Dict, *, now: int, free_signals: int, cooldown_seconds: int) -> int:
    used = int(user.get("trial_used") or 0)
    if used <= 0 or used >= free_signals:
        return 0
    last = int(user.get("last_trial_signal_at") or 0)
    if last <= 0:
        return 0
    return max(0, last + cooldown_seconds - now)


def decide_consume(user: Dict, *, now: int, free_signals: int, cooldown_seconds: int):
    """Decide a trial debit without writing.

    Returns (allowed, mode, updated_user_or_None). updated_user is the row to
    persist when a trial credit is actually spent.
    """
    if int(user.get("paid_until") or 0) > now:
        return True, "paid", None
    wait = trial_wait_seconds(
        user, now=now, free_signals=free_signals, cooldown_seconds=cooldown_seconds
    )
    if wait > 0:
        return False, "cooldown", None
    used = int(user.get("trial_used") or 0)
    if used < free_signals:
        return True, "trial", {
            "trial_used": used + 1,
            "last_trial_signal_at": now,
            "paywall_sent": False,
            "previous_trial_used": used,
        }
    return False, "paywall", None


class AccessManager:
    def __init__(
        self,
        state_file: str,
        free_trial_signals: int,
        paid_access_hours: int,
        payment_address: str,
        payment_amount: str,
        payment_network: str,
    ):
        self.state_file = state_file
        self.free_trial_signals = free_trial_signals
        self.paid_access_seconds = paid_access_hours * 60 * 60
        self.payment_address = payment_address
        self.payment_amount = payment_amount
        self.payment_network = payment_network
        import os

        self.database_url = os.getenv("DATABASE_URL", "")
        self.trial_cooldown_seconds = int(os.getenv("FREE_TRIAL_COOLDOWN_MINUTES", "30")) * 60
        self._file_lock = threading.Lock()

    def ensure_user(self, chat_id: str):
        user_id = self._user_id(chat_id)
        if user_id is None:
            return
        if self._use_db():
            try:
                with psycopg.connect(self.database_url) as connection:
                    self._lock_subscription(connection, user_id)
            except Exception as exc:
                logger.warning("ensure user failed: %s", type(exc).__name__)
            return
        with self._file_lock:
            state = self._load_file()
            user = self._user(state, chat_id)
            user.setdefault("trial_used", 0)
            user.setdefault("paid_until", 0)
            user.setdefault("paywall_sent", False)
            user.setdefault("last_trial_signal_at", 0)
            self._save_file(state)

    def can_receive(self, chat_id: str) -> bool:
        allowed, _mode = self.check_access(chat_id)
        return allowed

    def check_access(self, chat_id: str) -> Tuple[bool, str]:
        user = self._read_user(chat_id)
        allowed, mode, _updated = decide_consume(
            user,
            now=int(time.time()),
            free_signals=self.free_trial_signals,
            cooldown_seconds=self.trial_cooldown_seconds,
        )
        if mode == "trial":
            return True, "trial"
        return allowed, mode

    def consume_signal(self, chat_id: str) -> Tuple[bool, str]:
        """Spend one trial credit under a row lock. Call this after delivery."""
        now = int(time.time())
        user_id = self._user_id(chat_id)
        if self._use_db() and user_id is not None:
            try:
                with psycopg.connect(self.database_url) as connection:
                    user = self._lock_subscription(connection, user_id)
                    allowed, mode, updated = decide_consume(
                        user,
                        now=now,
                        free_signals=self.free_trial_signals,
                        cooldown_seconds=self.trial_cooldown_seconds,
                    )
                    if updated:
                        cursor = connection.execute(
                            """
                            UPDATE subscriptions
                            SET trial_used = %s,
                                last_trial_signal_at = TO_TIMESTAMP(%s),
                                paywall_sent = FALSE,
                                updated_at = NOW()
                            WHERE telegram_user_id = %s
                              AND trial_used = %s
                            """,
                            (
                                updated["trial_used"],
                                updated["last_trial_signal_at"],
                                user_id,
                                updated["previous_trial_used"],
                            ),
                        )
                        if cursor.rowcount != 1:
                            raise RuntimeError("trial update lost the row lock race")
                    return allowed, mode
            except Exception as exc:
                logger.warning("consume signal failed: %s", type(exc).__name__)
                return False, "conflict"
        with self._file_lock:
            state = self._load_file()
            user = self._user(state, str(chat_id))
            allowed, mode, updated = decide_consume(
                user,
                now=now,
                free_signals=self.free_trial_signals,
                cooldown_seconds=self.trial_cooldown_seconds,
            )
            if updated:
                user["trial_used"] = updated["trial_used"]
                user["last_trial_signal_at"] = updated["last_trial_signal_at"]
                user["paywall_sent"] = False
                if not self._save_file(state):
                    return False, "conflict"
                return allowed, mode
            return allowed, mode

    def should_send_paywall(self, chat_id: str) -> bool:
        user_id = self._user_id(chat_id)
        if self._use_db() and user_id is not None:
            try:
                with psycopg.connect(self.database_url) as connection:
                    user = self._lock_subscription(connection, user_id)
                    if user.get("paywall_sent"):
                        return False
                    connection.execute(
                        """
                        UPDATE subscriptions
                        SET paywall_sent = TRUE, updated_at = NOW()
                        WHERE telegram_user_id = %s AND paywall_sent = FALSE
                        """,
                        (user_id,),
                    )
                    return True
            except Exception as exc:
                logger.warning("paywall flag failed: %s", type(exc).__name__)
                return False
        with self._file_lock:
            state = self._load_file()
            user = self._user(state, str(chat_id))
            if user.get("paywall_sent"):
                self._save_file(state)
                return False
            user["paywall_sent"] = True
            self._save_file(state)
            return True

    def find_payment_by_tx_hash(self, tx_hash: str, exclude_chat_id: str = None):
        normalized = str(tx_hash).strip().lower()
        if self._use_db():
            try:
                with psycopg.connect(self.database_url) as connection:
                    row = connection.execute(
                        "SELECT telegram_user_id, status FROM payment_claims WHERE tx_hash = %s",
                        (normalized,),
                    ).fetchone()
                if row and str(row[0]) != str(exclude_chat_id):
                    return {"chat_id": str(row[0]), "tx_hash": normalized, "status": row[1]}
                if row:
                    return {"chat_id": str(row[0]), "tx_hash": normalized, "status": row[1]}
            except Exception as exc:
                logger.warning("payment claim lookup failed: %s", type(exc).__name__)
                return {"chat_id": "", "tx_hash": normalized, "status": "unknown"}
        return None

    def ensure_open_invoice(self, chat_id: str) -> dict | None:
        user_id = self._user_id(chat_id)
        if not self._use_db() or user_id is None:
            return None
        try:
            from miniapp.billing import ensure_open_invoice

            with psycopg.connect(self.database_url) as connection:
                return ensure_open_invoice(connection, user_id, self.payment_amount)
        except Exception as exc:
            logger.warning("open invoice failed: %s", type(exc).__name__)
            return None

    def settle_payment(
        self,
        chat_id: str,
        tx_hash: str,
        *,
        paid_amount,
        expected_amount,
        hours: int = None,
        details: dict | None = None,
    ) -> dict:
        """Reserve the hash and extend access in one transaction.

        On any failure the transaction is rolled back, so the hash is not burned
        and the caller must not tell the user the payment succeeded.
        """
        user_id = self._user_id(chat_id)
        if not self._use_db() or user_id is None:
            return {"ok": False, "reason": "save_failed"}
        try:
            from miniapp.billing import PaymentRejected, settle_payment_transaction

            duration = (hours * 60 * 60) if hours else self.paid_access_seconds
            with psycopg.connect(self.database_url) as connection:
                result = settle_payment_transaction(
                    connection,
                    user_id=user_id,
                    tx_hash=tx_hash,
                    paid_amount=paid_amount,
                    expected_amount=expected_amount,
                    duration_seconds=duration,
                    details=details,
                )
                if not result.get("ok"):
                    raise PaymentRejected(result)
                return result
        except Exception as exc:
            result = getattr(exc, "result", None)
            if isinstance(result, dict):
                return result
            logger.warning("payment settle failed: %s", type(exc).__name__)
            return {"ok": False, "reason": "save_failed"}

    def grant_access(self, chat_id: str, hours: int = None):
        """Return the new paid_until unix time, or None if the row did not commit."""
        duration = (hours * 60 * 60) if hours else self.paid_access_seconds
        user_id = self._user_id(chat_id)
        if self._use_db() and user_id is not None:
            try:
                with psycopg.connect(self.database_url) as connection:
                    row = connection.execute(
                        """
                        INSERT INTO subscriptions (telegram_user_id, paid_until, paywall_sent)
                        VALUES (%s, NOW() + (%s * INTERVAL '1 second'), FALSE)
                        ON CONFLICT (telegram_user_id) DO UPDATE SET
                            paid_until = GREATEST(COALESCE(subscriptions.paid_until, NOW()), NOW())
                                + (%s * INTERVAL '1 second'),
                            paywall_sent = FALSE,
                            updated_at = NOW()
                        RETURNING EXTRACT(EPOCH FROM paid_until)
                        """,
                        (user_id, int(duration), int(duration)),
                    ).fetchone()
                    if not row or row[0] is None:
                        raise RuntimeError("grant did not return paid_until")
                    return int(float(row[0]))
            except Exception as exc:
                logger.warning("grant access failed: %s", type(exc).__name__)
                return None
        with self._file_lock:
            state = self._load_file()
            user = self._user(state, str(chat_id))
            paid_until = int(max(time.time(), user.get("paid_until", 0)) + duration)
            user["paid_until"] = paid_until
            user["paywall_sent"] = False
            if not self._save_file(state):
                return None
            return paid_until

    def revoke_access(self, chat_id: str) -> bool:
        user_id = self._user_id(chat_id)
        if self._use_db() and user_id is not None:
            try:
                with psycopg.connect(self.database_url) as connection:
                    connection.execute(
                        """
                        INSERT INTO subscriptions (telegram_user_id, paid_until)
                        VALUES (%s, NULL)
                        ON CONFLICT (telegram_user_id) DO UPDATE SET
                            paid_until = NULL,
                            updated_at = NOW()
                        """,
                        (user_id,),
                    )
                return True
            except Exception as exc:
                logger.warning("revoke access failed: %s", type(exc).__name__)
                return False
        with self._file_lock:
            state = self._load_file()
            user = self._user(state, str(chat_id))
            user["paid_until"] = 0
            return self._save_file(state)

    def status(self, chat_id: str) -> dict:
        user = self._read_user(chat_id)
        paid_until = int(user.get("paid_until") or 0)
        claim = None
        user_id = self._user_id(chat_id)
        if self._use_db() and user_id is not None:
            try:
                with psycopg.connect(self.database_url) as connection:
                    row = connection.execute(
                        """
                        SELECT tx_hash, status
                        FROM payment_claims
                        WHERE telegram_user_id = %s
                        ORDER BY created_at DESC
                        LIMIT 1
                        """,
                        (user_id,),
                    ).fetchone()
                if row:
                    claim = {"tx_hash": row[0], "status": row[1]}
            except Exception as exc:
                logger.warning("status claim read failed: %s", type(exc).__name__)
        else:
            claim = user.get("last_payment_claim")
        return {
            "trial_used": int(user.get("trial_used") or 0),
            "trial_left": max(0, self.free_trial_signals - int(user.get("trial_used") or 0)),
            "paid_until": paid_until,
            "has_paid_access": paid_until > time.time(),
            "payment_claim": claim,
            "trial_available_at": int(user.get("last_trial_signal_at") or 0) + self.trial_cooldown_seconds,
            "trial_cooldown_left": trial_wait_seconds(
                user,
                now=int(time.time()),
                free_signals=self.free_trial_signals,
                cooldown_seconds=self.trial_cooldown_seconds,
            ),
        }

    def format_paywall(self) -> str:
        wallet = self.payment_address or "wallet is not configured"
        return (
            "🔒 <b>Free signals are used up</b>\n\n"
            f"You had {self.free_trial_signals} free signals. "
            f"Access for {self.paid_access_seconds // 86400} days costs "
            f"<b>{self.payment_amount} USDT</b>.\n\n"
            f"Network: <b>{self.payment_network}</b>\n"
            f"Wallet:\n<code>{wallet}</code>\n\n"
            "After payment send:\n"
            "<code>/paid TX_HASH</code>"
        )

    def _use_db(self) -> bool:
        return bool(self.database_url and psycopg)

    @staticmethod
    def _user_id(chat_id) -> int | None:
        text = str(chat_id).strip()
        if not text.lstrip("-").isdigit():
            return None
        return int(text)

    def _lock_subscription(self, connection, user_id: int) -> dict:
        connection.execute(
            "INSERT INTO subscriptions (telegram_user_id) VALUES (%s) ON CONFLICT DO NOTHING",
            (user_id,),
        )
        row = connection.execute(
            """
            SELECT trial_used,
                   EXTRACT(EPOCH FROM paid_until),
                   EXTRACT(EPOCH FROM last_trial_signal_at),
                   paywall_sent
            FROM subscriptions
            WHERE telegram_user_id = %s
            FOR UPDATE
            """,
            (user_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError("subscription row missing after insert")
        return {
            "trial_used": int(row[0] or 0),
            "paid_until": int(float(row[1])) if row[1] else 0,
            "last_trial_signal_at": int(float(row[2])) if row[2] else 0,
            "paywall_sent": bool(row[3]),
        }

    def _read_user(self, chat_id: str) -> dict:
        user_id = self._user_id(chat_id)
        if self._use_db() and user_id is not None:
            try:
                with psycopg.connect(self.database_url) as connection:
                    connection.execute(
                        "INSERT INTO subscriptions (telegram_user_id) VALUES (%s) ON CONFLICT DO NOTHING",
                        (user_id,),
                    )
                    row = connection.execute(
                        """
                        SELECT trial_used,
                               EXTRACT(EPOCH FROM paid_until),
                               EXTRACT(EPOCH FROM last_trial_signal_at),
                               paywall_sent
                        FROM subscriptions
                        WHERE telegram_user_id = %s
                        """,
                        (user_id,),
                    ).fetchone()
                if row:
                    return {
                        "trial_used": int(row[0] or 0),
                        "paid_until": int(float(row[1])) if row[1] else 0,
                        "last_trial_signal_at": int(float(row[2])) if row[2] else 0,
                        "paywall_sent": bool(row[3]),
                    }
            except Exception as exc:
                logger.warning("access read failed: %s", type(exc).__name__)
                return {"trial_used": self.free_trial_signals, "paid_until": 0, "last_trial_signal_at": 0}
        if self._use_db():
            return {"trial_used": self.free_trial_signals, "paid_until": 0, "last_trial_signal_at": 0}
        return self._user(self._load_file(), str(chat_id))

    def _load_file(self) -> Dict:
        import json
        import os

        if not os.path.exists(self.state_file):
            return {"users": {}}
        try:
            with open(self.state_file, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            data.setdefault("users", {})
            return data
        except Exception as exc:
            logger.warning("access file read failed: %s", type(exc).__name__)
            return {"users": {}}

    def _save_file(self, state: Dict) -> bool:
        import json

        try:
            with open(self.state_file, "w", encoding="utf-8") as handle:
                json.dump(state, handle, indent=2)
            return True
        except Exception as exc:
            logger.warning("access file write failed: %s", type(exc).__name__)
            return False

    def _user(self, state: Dict, chat_id: str) -> Dict:
        users = state.setdefault("users", {})
        return users.setdefault(str(chat_id), {})
