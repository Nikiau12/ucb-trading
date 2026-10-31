from contextlib import nullcontext
from decimal import Decimal
from pathlib import Path

import pytest

from core.access_manager import AccessManager
from miniapp import app as miniapp_app
from miniapp.billing import ensure_open_invoice
from miniapp.referrals import (
    effective_subscription_price,
    normalize_bingx_uid,
    review_referral_claim,
    submit_referral_claim,
)


ROOT = Path(__file__).resolve().parents[1]


class Result:
    def __init__(self, row=None, rows=None, rowcount=1):
        self.row = row
        self.rows = rows or []
        self.rowcount = rowcount

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


def test_bingx_uid_accepts_only_a_numeric_public_identifier():
    assert normalize_bingx_uid(" 12345678 ") == "12345678"
    for invalid in ("", "12345", "123-456", "mail@example.com", "1" * 21):
        with pytest.raises(ValueError):
            normalize_bingx_uid(invalid)


def test_verified_referral_gets_the_special_price_only_after_review():
    class Connection:
        def __init__(self, status):
            self.status = status

        def execute(self, _query, _params):
            return Result((self.status,) if self.status else None)

    assert effective_subscription_price(Connection("pending"), 1, "29.99", "10.00") == Decimal("29.99")
    assert effective_subscription_price(Connection("verified"), 1, "29.99", "10.00") == Decimal("10.00")


def test_one_bingx_uid_cannot_be_claimed_by_two_telegram_accounts():
    class Connection:
        def execute(self, _query, _params):
            return Result((777,))

    result = submit_referral_claim(
        Connection(),
        user_id=888,
        bingx_uid="12345678",
        referral_code="D8PYH62T",
    )
    assert result == {"ok": False, "reason": "uid_used"}


def test_review_cancels_an_open_invoice_so_the_price_is_recalculated():
    queries = []

    class Connection:
        def execute(self, query, params):
            queries.append((query, params))
            if "UPDATE bingx_referrals" in query:
                return Result((42, "12345678", "D8PYH62T", "verified"))
            return Result()

    reviewed = review_referral_claim(
        Connection(),
        user_id=42,
        status="verified",
        reviewed_by=1,
    )
    assert reviewed["status"] == "verified"
    assert any("UPDATE payment_invoices" in query and "cancelled" in query for query, _ in queries)


@pytest.mark.parametrize(
    ("verification_status", "stored_status"),
    [("verified", "verified"), ("not_eligible", "rejected")],
)
def test_miniapp_automatically_stores_the_agent_api_decision(
    monkeypatch, verification_status, stored_status
):
    queries = []

    class Connection:
        def execute(self, query, params=None):
            queries.append((query, params))
            if "UPDATE bingx_referrals" in query:
                return Result((42, "12345678", "D8PYH62T", params[0]))
            return Result()

    monkeypatch.setattr(
        miniapp_app,
        "verify_direct_referral",
        lambda _uid: {"status": verification_status, "reason": "test_reason"},
    )
    monkeypatch.setattr(miniapp_app, "db", lambda: nullcontext(Connection()))

    result = miniapp_app._automatic_referral_review(42, "12345678")

    assert result == {"status": stored_status, "verification_reason": "test_reason"}
    review_params = next(params for query, params in queries if "UPDATE bingx_referrals" in query)
    assert review_params == (stored_status, 0, 42, "12345678")


def test_miniapp_keeps_claim_pending_when_bingx_is_unavailable(monkeypatch):
    monkeypatch.setattr(
        miniapp_app,
        "verify_direct_referral",
        lambda _uid: {"status": "unavailable", "reason": "request_failed"},
    )
    monkeypatch.setattr(
        miniapp_app,
        "db",
        lambda: pytest.fail("database review must not run without a BingX decision"),
    )

    assert miniapp_app._automatic_referral_review(42, "12345678") == {
        "status": "pending",
        "verification_reason": "request_failed",
    }


def test_access_manager_builds_the_invoice_from_the_verified_price(monkeypatch, tmp_path):
    manager = AccessManager(str(tmp_path / "access.json"), 5, 720, "TWallet", "29.99", "TRC20")
    manager.database_url = "postgresql://test"
    seen = {}

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr("core.access_manager.psycopg.connect", lambda *_args, **_kwargs: Connection())
    monkeypatch.setattr(
        "miniapp.referrals.effective_subscription_price",
        lambda *_args, **_kwargs: Decimal("10.00"),
    )

    def fake_invoice(_connection, user_id, base_amount):
        seen.update(user_id=user_id, base_amount=base_amount)
        return {"id": 1, "expected_amount": "10.000001"}

    monkeypatch.setattr("miniapp.billing.ensure_open_invoice", fake_invoice)
    invoice = manager.ensure_open_invoice("42")
    assert invoice["expected_amount"] == "10.000001"
    assert seen == {"user_id": 42, "base_amount": Decimal("10.00")}


def test_wrong_price_open_invoice_is_cancelled_before_a_new_one_is_created():
    queries = []

    class Connection:
        def transaction(self):
            return nullcontext()

        def execute(self, query, params=None):
            queries.append((query, params))
            if "SELECT id, expected_amount::text, base_amount::text" in query:
                return Result((7, "29.990001", "29.99"))
            if "SELECT expected_amount::text" in query:
                return Result(rows=[])
            if "INSERT INTO payment_invoices" in query:
                return Result((8, "10.000042"))
            return Result()

    invoice = ensure_open_invoice(Connection(), 42, "10.00")
    assert invoice == {"id": 8, "expected_amount": "10.000042"}
    assert any("SET status = 'cancelled'" in query for query, _ in queries)
    insert_params = next(params for query, params in queries if "INSERT INTO payment_invoices" in query)
    assert insert_params[2] == Decimal("10.000000")


def test_mini_app_contains_the_referral_claim_flow():
    html = (ROOT / "miniapp" / "static" / "index.html").read_text()
    script = (ROOT / "miniapp" / "static" / "app.js").read_text()
    assert 'id="bingx-referral-link"' in html
    assert 'id="bingx-uid"' in html
    assert 'id="referral-form"' in html
    assert "/api/bingx-referral" in script
    assert "uid_used" in script
    assert "bingx.com" in script
