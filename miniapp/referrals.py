"""BingX referral claims and the verified subscription discount."""

from __future__ import annotations

from decimal import Decimal


REFERRAL_STATUSES = {"pending", "verified", "rejected"}


def normalize_bingx_uid(value: str) -> str:
    uid = str(value or "").strip()
    if not uid.isdigit() or not 6 <= len(uid) <= 20:
        raise ValueError("invalid_bingx_uid")
    return uid


def referral_snapshot(connection, user_id: int) -> dict:
    row = connection.execute(
        """
        SELECT
            r.bingx_uid,
            r.referral_code,
            r.status,
            r.submitted_at,
            r.reviewed_at,
            CASE
                WHEN r.status <> 'verified' THEN TRUE
                WHEN s.paid_until IS NULL THEN TRUE
                WHEN s.paid_until > NOW() THEN TRUE
                WHEN r.reviewed_at > s.paid_until THEN TRUE
                ELSE FALSE
            END AS verification_current
        FROM bingx_referrals r
        LEFT JOIN subscriptions s ON s.telegram_user_id = r.telegram_user_id
        WHERE r.telegram_user_id = %s
        """,
        (int(user_id),),
    ).fetchone()
    if not row:
        return {
            "bingx_uid": None,
            "referral_code": None,
            "status": "none",
            "submitted_at": None,
            "reviewed_at": None,
            "requires_reverification": False,
        }
    status = "expired" if row[2] == "verified" and not bool(row[5]) else row[2]
    return {
        "bingx_uid": row[0],
        "referral_code": row[1],
        "status": status,
        "submitted_at": row[3],
        "reviewed_at": row[4],
        "requires_reverification": status == "expired",
    }


def effective_subscription_price(
    connection,
    user_id: int,
    standard_price,
    referral_price,
) -> Decimal:
    status = referral_snapshot(connection, user_id)["status"]
    return Decimal(str(referral_price if status == "verified" else standard_price))


def submit_referral_claim(connection, *, user_id: int, bingx_uid: str, referral_code: str) -> dict:
    uid = normalize_bingx_uid(bingx_uid)
    code = str(referral_code or "").strip().upper()
    owner = connection.execute(
        """
        SELECT telegram_user_id
        FROM bingx_referrals
        WHERE bingx_uid = %s AND referral_code = %s
        """,
        (uid, code),
    ).fetchone()
    if owner and int(owner[0]) != int(user_id):
        return {"ok": False, "reason": "uid_used"}

    current = connection.execute(
        """
        SELECT
            r.bingx_uid,
            r.status,
            CASE
                WHEN s.paid_until IS NULL THEN TRUE
                WHEN s.paid_until > NOW() THEN TRUE
                WHEN r.reviewed_at > s.paid_until THEN TRUE
                ELSE FALSE
            END AS verification_current
        FROM bingx_referrals r
        LEFT JOIN subscriptions s ON s.telegram_user_id = r.telegram_user_id
        WHERE r.telegram_user_id = %s
        FOR UPDATE OF r
        """,
        (int(user_id),),
    ).fetchone()
    if current and current[1] == "verified" and bool(current[2]):
        return {
            "ok": current[0] == uid,
            "reason": None if current[0] == uid else "already_verified",
            "status": "verified",
            "bingx_uid": current[0],
        }

    row = connection.execute(
        """
        INSERT INTO bingx_referrals (
            telegram_user_id, bingx_uid, referral_code, status, submitted_at,
            reviewed_at, reviewed_by
        )
        VALUES (%s, %s, %s, 'pending', NOW(), NULL, NULL)
        ON CONFLICT (telegram_user_id) DO UPDATE SET
            bingx_uid = EXCLUDED.bingx_uid,
            referral_code = EXCLUDED.referral_code,
            status = 'pending',
            submitted_at = NOW(),
            reviewed_at = NULL,
            reviewed_by = NULL
        RETURNING bingx_uid, status
        """,
        (int(user_id), uid, code),
    ).fetchone()
    return {"ok": True, "bingx_uid": row[0], "status": row[1]}


def review_referral_claim(
    connection,
    *,
    user_id: int,
    status: str,
    reviewed_by: int,
    expected_bingx_uid: str | None = None,
) -> dict | None:
    if status not in {"verified", "rejected"}:
        raise ValueError("invalid_referral_status")
    row = connection.execute(
        """
        UPDATE bingx_referrals
        SET status = %s, reviewed_at = NOW(), reviewed_by = %s
        WHERE telegram_user_id = %s
          AND bingx_uid = COALESCE(%s, bingx_uid)
        RETURNING telegram_user_id, bingx_uid, referral_code, status
        """,
        (status, int(reviewed_by), int(user_id), expected_bingx_uid),
    ).fetchone()
    if not row:
        return None

    # An invoice created before review may contain the wrong base price.
    connection.execute(
        """
        UPDATE payment_invoices
        SET status = 'cancelled'
        WHERE telegram_user_id = %s AND status = 'open'
        """,
        (int(user_id),),
    )
    return {
        "telegram_user_id": int(row[0]),
        "bingx_uid": row[1],
        "referral_code": row[2],
        "status": row[3],
    }


def pending_referral_claims(connection, *, limit: int = 20) -> list[dict]:
    rows = connection.execute(
        """
        SELECT telegram_user_id, bingx_uid, referral_code, submitted_at
        FROM bingx_referrals
        WHERE status = 'pending'
        ORDER BY submitted_at
        LIMIT %s
        """,
        (max(1, min(int(limit), 100)),),
    ).fetchall()
    return [
        {
            "telegram_user_id": int(row[0]),
            "bingx_uid": row[1],
            "referral_code": row[2],
            "submitted_at": row[3],
        }
        for row in rows
    ]
