"""Persist the deposit dialog step in Postgres."""

from __future__ import annotations

import logging
from typing import Any, Mapping

from aiogram.fsm.storage.base import BaseStorage, StorageKey
from psycopg.types.json import Json

logger = logging.getLogger("ucb.fsm")


def _state_name(state) -> str | None:
    if state is None:
        return None
    named = getattr(state, "state", None)
    return str(named if named is not None else state)


class PostgresFSMStorage(BaseStorage):
    def __init__(self, database_url: str):
        self.database_url = database_url

    def _key(self, key: StorageKey) -> tuple:
        return (
            int(key.bot_id),
            int(key.chat_id),
            int(key.user_id),
            int(key.thread_id or 0),
            str(key.business_connection_id or ""),
            str(key.destiny or "default"),
        )

    def _connect(self):
        import psycopg

        return psycopg.connect(self.database_url)

    async def set_state(self, key: StorageKey, state=None) -> None:
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO fsm_storage (
                        bot_id, chat_id, user_id, thread_id, business_connection_id, destiny, state
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (bot_id, chat_id, user_id, thread_id, business_connection_id, destiny)
                    DO UPDATE SET state = EXCLUDED.state, updated_at = NOW()
                    """,
                    (*self._key(key), _state_name(state)),
                )
        except Exception as exc:
            logger.warning("fsm state write failed: %s", type(exc).__name__)

    async def get_state(self, key: StorageKey) -> str | None:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT state FROM fsm_storage
                    WHERE bot_id = %s AND chat_id = %s AND user_id = %s
                      AND thread_id = %s AND business_connection_id = %s AND destiny = %s
                    """,
                    self._key(key),
                ).fetchone()
            return row[0] if row else None
        except Exception as exc:
            logger.warning("fsm state read failed: %s", type(exc).__name__)
            return None

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO fsm_storage (
                        bot_id, chat_id, user_id, thread_id, business_connection_id, destiny, data
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (bot_id, chat_id, user_id, thread_id, business_connection_id, destiny)
                    DO UPDATE SET data = EXCLUDED.data, updated_at = NOW()
                    """,
                    (*self._key(key), Json(dict(data))),
                )
        except Exception as exc:
            logger.warning("fsm data write failed: %s", type(exc).__name__)

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT data FROM fsm_storage
                    WHERE bot_id = %s AND chat_id = %s AND user_id = %s
                      AND thread_id = %s AND business_connection_id = %s AND destiny = %s
                    """,
                    self._key(key),
                ).fetchone()
            if not row or row[0] is None:
                return {}
            return dict(row[0])
        except Exception as exc:
            logger.warning("fsm data read failed: %s", type(exc).__name__)
            return {}

    async def close(self) -> None:
        return None
