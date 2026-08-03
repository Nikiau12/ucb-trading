import asyncio

from mexc import exchange_client_mexc


def test_public_market_client_does_not_receive_private_credentials(monkeypatch):
    captured = {}

    def fake_mexc(config):
        captured.update(config)
        return object()

    monkeypatch.setattr(exchange_client_mexc.ccxt, "mexc", fake_mexc)
    monkeypatch.setattr(exchange_client_mexc, "MEXC_API_KEY", "expired-key")
    monkeypatch.setattr(exchange_client_mexc, "MEXC_API_SECRET", "expired-secret")

    exchange_client_mexc.ExchangeClient()

    assert "apiKey" not in captured
    assert "secret" not in captured


def test_public_request_retries_mexc_throttle(monkeypatch):
    monkeypatch.setattr(exchange_client_mexc.ccxt, "mexc", lambda config: object())
    client = exchange_client_mexc.ExchangeClient()
    client._public_request_interval = 0
    attempts = 0

    async def fake_sleep(_seconds):
        return None

    async def throttled_operation():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError('mexc {"code":510,"message":"Requests are too frequent"}')
        return "ok"

    monkeypatch.setattr(exchange_client_mexc.asyncio, "sleep", fake_sleep)

    assert asyncio.run(client._public_request(throttled_operation)) == "ok"
    assert attempts == 3
