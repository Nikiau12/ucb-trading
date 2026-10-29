import asyncio

from bingx import exchange_client_bingx


def test_public_client_does_not_receive_private_credentials(monkeypatch):
    captured = {}

    def fake_bingx(config):
        captured.update(config)
        return object()

    monkeypatch.setattr(exchange_client_bingx.ccxt, "bingx", fake_bingx)
    monkeypatch.setattr(exchange_client_bingx, "BINGX_API_KEY", "private-key")
    monkeypatch.setattr(exchange_client_bingx, "BINGX_API_SECRET", "private-secret")
    exchange_client_bingx.ExchangeClient()
    assert "apiKey" not in captured
    assert "secret" not in captured


def test_public_request_retries_bingx_throttle(monkeypatch):
    monkeypatch.setattr(exchange_client_bingx.ccxt, "bingx", lambda config: object())
    client = exchange_client_bingx.ExchangeClient()
    client._public_request_interval = 0
    attempts = 0

    async def fake_sleep(_seconds):
        return None

    async def throttled_operation():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("BingX 429 too many requests")
        return "ok"

    monkeypatch.setattr(exchange_client_bingx.asyncio, "sleep", fake_sleep)
    assert asyncio.run(client._public_request(throttled_operation)) == "ok"
    assert attempts == 3
