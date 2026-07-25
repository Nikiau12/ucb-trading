import hashlib
import hmac
import json
import time
from typing import Optional
from urllib.parse import urlencode

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from miniapp import app as miniapp


def _signed_init_data(
    token: str,
    user: dict,
    auth_date: Optional[int] = None,
) -> str:
    values = {
        "auth_date": str(auth_date or int(time.time())),
        "user": json.dumps(user, separators=(",", ":")),
    }
    data_check_string = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    values["hash"] = hmac.new(
        secret,
        data_check_string.encode(),
        hashlib.sha256,
    ).hexdigest()
    return urlencode(values)


@pytest.fixture
def demo_client(monkeypatch):
    monkeypatch.setattr(miniapp, "BOT_TOKEN", "")
    monkeypatch.setattr(miniapp, "DATABASE_URL", "")
    with TestClient(miniapp.app) as client:
        yield client


def test_demo_profile_and_signal_history_are_available(demo_client):
    profile = demo_client.get("/api/me")
    signals = demo_client.get("/api/signals")

    assert profile.status_code == 200
    assert profile.json()["first_name"] == "Nikita"
    assert profile.json()["trial_left"] == 3
    assert signals.status_code == 200
    assert {item["symbol"] for item in signals.json()} == {
        "BTC_USDT",
        "ETH_USDT",
        "SOL_USDT",
    }


def test_settings_validation_rejects_unsupported_values(demo_client):
    bad_language = demo_client.patch("/api/settings", json={"language": "xx"})
    bad_margin = demo_client.patch("/api/settings", json={"margin": "unsupported"})

    assert bad_language.status_code == 422
    assert bad_margin.status_code == 422


def test_market_endpoint_validates_input_before_external_request(demo_client):
    bad_symbol = demo_client.get("/api/market/BTC-EUR")
    bad_timeframe = demo_client.get("/api/market/BTC_USDT?timeframe=5m")

    assert bad_symbol.status_code == 422
    assert bad_timeframe.status_code == 422


def test_telegram_init_data_signature_is_verified(monkeypatch):
    token = "123456:test-token"
    user = {"id": 42, "first_name": "Nikita", "language_code": "en"}
    monkeypatch.setattr(miniapp, "BOT_TOKEN", token)

    assert miniapp.telegram_user(_signed_init_data(token, user)) == user


def test_invalid_or_expired_telegram_init_data_is_rejected(monkeypatch):
    token = "123456:test-token"
    user = {"id": 42, "first_name": "Nikita"}
    monkeypatch.setattr(miniapp, "BOT_TOKEN", token)

    invalid = _signed_init_data(token, user) + "broken"
    expired = _signed_init_data(token, user, auth_date=int(time.time()) - 90_000)

    with pytest.raises(HTTPException) as invalid_error:
        miniapp.telegram_user(invalid)
    with pytest.raises(HTTPException) as expired_error:
        miniapp.telegram_user(expired)

    assert invalid_error.value.status_code == 401
    assert expired_error.value.status_code == 401


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("BTC_USDT", "BTC_USDT"),
        ("eth/usdt", "ETH_USDT"),
        ("sol-usdt:usdt", "SOL_USDT"),
        ("BTC_EUR", None),
    ],
)
def test_usdt_symbol_normalization(value, expected):
    assert miniapp.normalize_usdt_symbol(value) == expected
