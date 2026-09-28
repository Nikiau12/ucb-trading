"""Apply SQL migrations once on process startup."""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger("ucb.schema")

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def _statements(script: str) -> list[str]:
    statements = []
    buffer: list[str] = []
    for line in script.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        buffer.append(line)
        if stripped.endswith(";"):
            statement = "\n".join(buffer).strip()
            if statement.endswith(";"):
                statement = statement[:-1].strip()
            if statement:
                statements.append(statement)
            buffer = []
    trailing = "\n".join(buffer).strip()
    if trailing:
        statements.append(trailing)
    return statements


def apply_migrations(database_url: str) -> None:
    if not database_url:
        return
    import psycopg

    with psycopg.connect(database_url) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            applied = connection.execute(
                "SELECT 1 FROM schema_migrations WHERE version = %s",
                (path.name,),
            ).fetchone()
            if applied:
                continue
            for statement in _statements(path.read_text(encoding="utf-8")):
                connection.execute(statement)
            connection.execute(
                "INSERT INTO schema_migrations (version) VALUES (%s)",
                (path.name,),
            )
            logger.info("applied migration %s", path.name)
        _import_legacy_access(connection)


def _import_legacy_access(connection) -> None:
    """Copy the old JSON access document into subscription rows once."""
    try:
        row = connection.execute("SELECT data FROM access_state WHERE id = 1").fetchone()
    except Exception as exc:
        logger.warning("legacy access read skipped: %s", type(exc).__name__)
        return
    if not row or row[0] is None:
        return
    data = row[0] if isinstance(row[0], dict) else json.loads(row[0])
    for raw_id, user in (data.get("users") or {}).items():
        if not str(raw_id).lstrip("-").isdigit():
            continue
        user_id = int(raw_id)
        paid_until = int(user.get("paid_until") or 0)
        last_trial = int(user.get("last_trial_signal_at") or 0)
        connection.execute(
            """
            INSERT INTO subscriptions (
                telegram_user_id, trial_used, paid_until, payment_status,
                last_trial_signal_at, paywall_sent
            )
            VALUES (
                %s, %s,
                CASE WHEN %s > 0 THEN TO_TIMESTAMP(%s) ELSE NULL END,
                %s,
                CASE WHEN %s > 0 THEN TO_TIMESTAMP(%s) ELSE NULL END,
                %s
            )
            ON CONFLICT (telegram_user_id) DO NOTHING
            """,
            (
                user_id,
                int(user.get("trial_used") or 0),
                paid_until,
                paid_until,
                (user.get("last_payment_claim") or {}).get("status"),
                last_trial,
                last_trial,
                bool(user.get("paywall_sent")),
            ),
        )
        claims = list(user.get("payment_claims") or [])
        legacy = user.get("last_payment_claim") or {}
        if legacy and not claims:
            claims.append(legacy)
        for claim in claims:
            tx_hash = str(claim.get("tx_hash") or "").strip().lower()
            if len(tx_hash) != 64:
                continue
            connection.execute(
                """
                INSERT INTO payment_claims (tx_hash, telegram_user_id, status, details)
                VALUES (%s, %s, %s, %s::jsonb)
                ON CONFLICT (tx_hash) DO NOTHING
                """,
                (
                    tx_hash,
                    user_id,
                    str(claim.get("status") or "pending"),
                    json.dumps({key: value for key, value in claim.items() if key != "tx_hash"}),
                ),
            )
