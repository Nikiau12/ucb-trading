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
