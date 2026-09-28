import hashlib
import hmac
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from miniapp import app as miniapp


ROOT_DIR = Path(__file__).resolve().parents[1]


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
    monkeypatch.setattr(miniapp, "DEMO_MODE", True)
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
    assert all(item["sizing"]["risk_usdt"] == pytest.approx(4.0) for item in signals.json())


def test_personal_signal_sizing_uses_contract_rules_and_exchange_leverage_limit():
    signal = {
        "entry": 100.0,
        "stop": 95.0,
        "contract_size": 0.1,
        "vol_unit": 1,
        "min_vol": 1,
        "max_vol": 100,
        "max_leverage": 20,
    }
    profile = {"deposit": 100.0, "risk_pct": 1.0, "leverage": 50.0}

    payload = miniapp.attach_personal_sizing(signal, profile)

    assert payload["sizing"]["contract_vol"] == 2
    assert payload["sizing"]["risk_usdt"] == pytest.approx(1.0)
    assert payload["sizing"]["position_usdt"] == pytest.approx(20.0)
    assert payload["sizing"]["effective_leverage"] == 20
    assert payload["sizing"]["margin_usdt"] == pytest.approx(1.0)
    assert payload["sizing"]["tradable"] is True


def test_miniapp_imports_from_railway_service_root():
    result = subprocess.run(
        [sys.executable, "-c", "import app"],
        cwd=ROOT_DIR / "miniapp",
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_railway_deployment_requires_live_health_endpoint():
    config = json.loads((ROOT_DIR / "miniapp" / "railway.json").read_text())

    assert config["deploy"]["healthcheckPath"] == "/health"
    assert config["deploy"]["healthcheckTimeout"] == 60


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


def test_missing_telegram_auth_is_rejected_outside_demo(monkeypatch):
    monkeypatch.setattr(miniapp, "BOT_TOKEN", "")
    monkeypatch.setattr(miniapp, "DATABASE_URL", "")
    monkeypatch.setattr(miniapp, "DEMO_MODE", False)

    with pytest.raises(HTTPException) as error:
        miniapp.telegram_user("")

    assert error.value.status_code == 401


def test_security_headers_are_present(demo_client):
    response = demo_client.get("/")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors" in response.headers["content-security-policy"]
    assert response.headers["referrer-policy"] == "no-referrer"


def test_health_and_prometheus_metrics_are_available(demo_client, monkeypatch):
    monkeypatch.setenv("METRICS_TOKEN", "metrics-secret")
    health = demo_client.get("/health")
    demo_client.get("/api/me")
    metrics = demo_client.get("/metrics")

    assert health.status_code == 200
    assert health.json() == {"ok": True}
    assert "scanner" not in health.json()
    assert demo_client.get("/api/me").json()["scanner_live"] is False
    assert metrics.status_code == 401
    metrics = demo_client.get(
        "/metrics",
        headers={"Authorization": "Bearer metrics-secret"},
    )
    assert metrics.status_code == 200
    assert "ucb_app_uptime_seconds" in metrics.text
    assert 'path="/api/me",status="200"' in metrics.text


def test_health_returns_503_when_production_database_is_unavailable(monkeypatch):
    monkeypatch.setattr(miniapp, "DATABASE_URL", "postgresql://unavailable")
    monkeypatch.setattr(
        miniapp.psycopg,
        "connect",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("database unavailable")),
    )

    response = miniapp.health()

    assert response.status_code == 503
    assert json.loads(response.body) == {"ok": False}


def test_signed_session_without_database_returns_503(monkeypatch):
    token = "123456:test-token"
    user = {"id": 42, "first_name": "Nikita", "language_code": "en"}
    monkeypatch.setattr(miniapp, "BOT_TOKEN", token)
    monkeypatch.setattr(miniapp, "DATABASE_URL", "")
    monkeypatch.setattr(miniapp, "DEMO_MODE", True)
    init_data = _signed_init_data(token, user)
    with TestClient(miniapp.app) as client:
        profile = client.get("/api/me", headers={"X-Telegram-Init-Data": init_data})
        signals = client.get("/api/signals", headers={"X-Telegram-Init-Data": init_data})

    assert profile.status_code == 503
    assert signals.status_code == 503
    assert "400.0" not in profile.text
    assert "BTC_USDT" not in signals.text


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


def test_payment_screen_stays_open_until_a_verified_hash():
    root = ROOT_DIR / "miniapp" / "static"
    html = (root / "index.html").read_text()
    script = (root / "app.js").read_text()

    assert 'id="payment-panel"' in html
    assert 'id="payment-copy"' in html
    assert 'id="payment-hash"' in html
    assert 'id="payment-retry"' in html
    assert 'data-i18n="accessOpen"' in html
    assert "Доступ открыт" in script or "accessOpen:'Доступ открыт'" in script
    assert "tg?.close()" not in script
    assert "access_open!==true" in script
    assert "showPaymentError" in script
    assert "showPaymentSuccess" in script


def test_remaining_interface_gaps_are_in_the_mini_app():
    root = ROOT_DIR / "miniapp" / "static"
    html = (root / "index.html").read_text()
    script = (root / "app.js").read_text()
    css = (root / "styles.css").read_text()

    assert "width:390px" not in css
    assert "right:24px" not in css
    assert 'id="subscription-title"' in html
    assert 'id="chart-skeleton"' in html
    assert 'id="chart-frame"' in html
    assert 'id="payment-sheet"' in html
    assert 'data-i18n="sizeDisclaimer"' in html
    assert 'data-i18n="hello"' not in html
    assert "исполнен" not in html
    assert "executionPlan" not in html
    assert "/paid" not in html
    assert "font:16px/1.45" in css
    assert "min-height:44px" in css
    assert "chart-skeleton" in css
    assert "syncSymbolPicker" in script
    assert "signal-row" in script
    assert "scannerSilent" in script
    assert "lastScan" in script
    assert "paymentWaiting" in script
    assert "paymentMismatch" in script
    assert "accessOpenUntil" in script
    assert "confidenceLabel(signal)" in script and "confidenceNote" in script
    assert "coincap.io" not in script
    assert "lucide" not in script
    assert "unpkg.com/lucide" not in html
    assert 'id="payment-state"' in html
    assert 'id="language"' in html
    assert "trade-levels" not in css
    assert "level-line" not in css
    assert "signal_id" in script
    assert "setHeaderColor?.('#090b10')" in script
    assert "MainButton" in script
    assert "riskUsdt/distance" not in script
    assert "filterEmpty" in script
    assert "saveFailed" in script
    assert "const previous=language" in script
    assert "position_below_min_contract" in script
    assert "settingsAccessCopy" in script
    assert "pay.hidden=paid" in script


def test_unverified_payment_hash_does_not_open_access(monkeypatch):
    token = "123456:test-token"
    user = {"id": 42, "first_name": "Nikita", "language_code": "en"}
    settled = []
    monkeypatch.setattr(miniapp, "BOT_TOKEN", token)
    monkeypatch.setattr(miniapp, "DATABASE_URL", "postgresql://test")
    monkeypatch.setattr(miniapp, "DEMO_MODE", False)
    monkeypatch.setattr(miniapp, "PAYMENT_WALLET", "TWallet")
    monkeypatch.setattr(miniapp, "_open_invoice_amount", lambda _user_id: "29.990001")
    monkeypatch.setattr(
        miniapp,
        "_verify_tx",
        lambda *_args, **_kwargs: {"ok": False, "reason": "not_found"},
    )
    monkeypatch.setattr(miniapp, "_settle_tx", lambda **kwargs: settled.append(kwargs))
    init_data = _signed_init_data(token, user)
    denied = miniapp.claim_payment(
        miniapp.PaymentClaim(tx_hash="ab" * 32),
        x_telegram_init_data=init_data,
    )

    assert denied.status_code == 422
    assert json.loads(denied.body)["ok"] is False
    assert json.loads(denied.body)["access_open"] is False
    assert settled == []
    with pytest.raises(ValidationError):
        miniapp.PaymentClaim(tx_hash="not-a-hash")
    assert settled == []


def test_verified_payment_opens_access_on_the_same_contract(monkeypatch):
    token = "123456:test-token"
    user = {"id": 42, "first_name": "Nikita", "language_code": "en"}
    monkeypatch.setattr(miniapp, "BOT_TOKEN", token)
    monkeypatch.setattr(miniapp, "DATABASE_URL", "postgresql://test")
    monkeypatch.setattr(miniapp, "DEMO_MODE", False)
    monkeypatch.setattr(miniapp, "PAYMENT_WALLET", "TWallet")
    monkeypatch.setattr(miniapp, "_open_invoice_amount", lambda _user_id: "29.990001")
    monkeypatch.setattr(
        miniapp,
        "_verify_tx",
        lambda *_args, **_kwargs: {"ok": True, "paid_amount": "29.990001"},
    )
    monkeypatch.setattr(
        miniapp,
        "_settle_tx",
        lambda **_kwargs: {"ok": True, "paid_until": 1_800_000_000},
    )
    init_data = _signed_init_data(token, user)
    opened = miniapp.claim_payment(
        miniapp.PaymentClaim(tx_hash="cd" * 32),
        x_telegram_init_data=init_data,
    )

    assert opened["access_open"] is True


def test_demo_payment_cannot_grant_access(demo_client):
    response = demo_client.post("/api/payment", json={"tx_hash": "ab" * 32})

    assert response.status_code == 503
    assert response.json().get("access_open") is not True
