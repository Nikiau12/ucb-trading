"""One long-polling worker per database."""

from __future__ import annotations

import logging

logger = logging.getLogger("ucb.worker_lock")

# Stable key so every process competes for the same session advisory lock.
WORKER_LOCK_KEY = 748219331501


def hold_worker_lock(database_url: str):
    """Hold a Postgres advisory lock for the life of the returned connection.

    Returns the open connection, None when no database is configured (local
    file mode), or False when another process already holds the lock.
    """
    if not database_url:
        logger.warning("DATABASE_URL is unset; polling lock was not acquired")
        return None
    import psycopg

    connection = psycopg.connect(database_url, autocommit=True)
    row = connection.execute(
        "SELECT pg_try_advisory_lock(%s)",
        (WORKER_LOCK_KEY,),
    ).fetchone()
    if not row or not row[0]:
        connection.close()
        logger.error("another polling worker holds the lock; this process will exit")
        return False
    return connection
