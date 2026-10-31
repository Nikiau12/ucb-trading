import hashlib
import hmac

import pytest
import requests

from miniapp.bingx_agent import RELATION_PATH, verify_direct_referral


class Response:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def json(self):
        return self.payload


def test_agent_request_is_signed_in_the_same_order_that_is_transmitted():
    captured = {}

    def fake_get(url, **kwargs):
        captured.update(url=url, **kwargs)
        return Response(
            {
                "code": 0,
                "data": {
                    "uid": "12345678",
                    "inviteResult": True,
                    "directInvitation": True,
                },
            }
        )

    result = verify_direct_referral(
        "12345678",
        api_key="agent-key",
        api_secret="agent-secret",
        now_ms=1_700_000_000_000,
        request_get=fake_get,
    )

    canonical = "recvWindow=5000&timestamp=1700000000000&uid=12345678"
    expected_signature = hmac.new(
        b"agent-secret", canonical.encode(), hashlib.sha256
    ).hexdigest()
    assert result == {"status": "verified", "reason": "direct_referral"}
    assert captured["url"].endswith(RELATION_PATH)
    assert captured["params"] == [
        ("recvWindow", "5000"),
        ("timestamp", "1700000000000"),
        ("uid", "12345678"),
        ("signature", expected_signature),
    ]
    assert captured["headers"] == {
        "X-BX-APIKEY": "agent-key",
        "X-SOURCE-KEY": "BX-AI-SKILL",
    }
    assert captured["timeout"] == 8


@pytest.mark.parametrize(
    ("invite_result", "direct", "expected_reason"),
    [
        (False, False, "not_referred"),
        (True, False, "indirect_referral"),
    ],
)
def test_only_direct_team_referrals_are_eligible(invite_result, direct, expected_reason):
    def fake_get(*_args, **_kwargs):
        return Response(
            {
                "code": 0,
                "data": {
                    "uid": 12345678,
                    "inviteResult": invite_result,
                    "directInvitation": direct,
                },
            }
        )

    result = verify_direct_referral(
        "12345678",
        api_key="key",
        api_secret="secret",
        request_get=fake_get,
    )
    assert result == {"status": "not_eligible", "reason": expected_reason}


def test_temporary_agent_api_errors_are_not_treated_as_rejections():
    def timeout(*_args, **_kwargs):
        raise requests.Timeout("private details must not escape")

    assert verify_direct_referral(
        "12345678",
        api_key="key",
        api_secret="secret",
        request_get=timeout,
    ) == {"status": "unavailable", "reason": "request_failed"}

    assert verify_direct_referral(
        "12345678",
        api_key="key",
        api_secret="secret",
        request_get=lambda *_args, **_kwargs: Response({"code": 100500}),
    ) == {"status": "unavailable", "reason": "bingx_code_100500"}


def test_missing_credentials_and_mismatched_uid_fail_closed(monkeypatch):
    monkeypatch.delenv("BINGX_AGENT_API_KEY", raising=False)
    monkeypatch.delenv("BINGX_AGENT_API_SECRET", raising=False)
    assert verify_direct_referral("12345678") == {
        "status": "unavailable",
        "reason": "credentials_missing",
    }

    result = verify_direct_referral(
        "12345678",
        api_key="key",
        api_secret="secret",
        request_get=lambda *_args, **_kwargs: Response(
            {
                "code": 0,
                "data": {
                    "uid": "87654321",
                    "inviteResult": True,
                    "directInvitation": True,
                },
            }
        ),
    )
    assert result == {"status": "unavailable", "reason": "invalid_response"}
