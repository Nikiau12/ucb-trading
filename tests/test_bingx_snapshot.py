from __future__ import annotations

import time

import pytest

from trading import bingx_snapshot


class FakeResponse:
    def __init__(self, payload, status_code=200, headers=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            error = bingx_snapshot.requests.HTTPError(f"HTTP {self.status_code}")
            error.response = self
            raise error

    def json(self):
        return self._payload


def test_symbol_conversion_accepts_internal_and_ccxt_formats():
    assert bingx_snapshot.to_bingx_symbol("BTC_USDT") == "BTC-USDT"
    assert bingx_snapshot.to_bingx_symbol("BTC/USDT:USDT") == "BTC-USDT"
    assert bingx_snapshot.to_internal_symbol("BTC-USDT") == "BTC_USDT"
    with pytest.raises(ValueError):
        bingx_snapshot.to_bingx_symbol("BTC-EUR")


def test_public_client_retries_rate_limit_response():
    responses = iter([
        FakeResponse({}, status_code=429),
        FakeResponse({"code": 0, "msg": "", "data": {"lastPrice": "1"}}),
    ])
    sleeps = []
    client = bingx_snapshot.BingxPublicClient(
        min_interval=0,
        max_attempts=3,
        sleep=sleeps.append,
        request_get=lambda *args, **kwargs: next(responses),
    )
    result = client.get("/openApi/swap/v2/quote/ticker")
    assert result["code"] == 0
    assert sleeps == [1.0]


def test_contract_normalization_uses_base_asset_quantity():
    contract = bingx_snapshot.normalize_contract({
        "symbol": "BTC-USDT",
        "quantityPrecision": 4,
        "pricePrecision": 1,
        "tradeMinQuantity": "0.0001",
        "tradeMinUSDT": "2",
        "status": 1,
        "apiStateOpen": "true",
    })
    assert contract["symbol"] == "BTC_USDT"
    assert contract["priceUnit"] == 0.1
    assert contract["contractSize"] == 1.0
    assert contract["volUnit"] == 0.0001
    assert contract["minVol"] == 0.0001
    assert contract["minNotional"] == 2.0
    assert contract["active"] is True


def test_non_crypto_bingx_products_are_excluded():
    assert bingx_snapshot.is_crypto_contract({"asset": "BTC"}) is True
    assert bingx_snapshot.is_crypto_contract({"asset": "NCCOGOLD2USD"}) is False
    assert bingx_snapshot.is_crypto_contract({"asset": "NCFXEUR2USD"}) is False


def test_volume_ranking_uses_only_active_crypto_contracts(monkeypatch):
    monkeypatch.setattr(
        bingx_snapshot,
        "futures_all_tickers",
        lambda: {"data": [
            {"symbol": "NCCOGOLD2USD_USDT", "quoteVolume": "999"},
            {"symbol": "OLD_USDT", "quoteVolume": "500"},
            {"symbol": "BTC_USDT", "quoteVolume": "100"},
        ]},
    )
    monkeypatch.setattr(
        bingx_snapshot,
        "futures_contracts",
        lambda: {"data": [
            {"symbol": "BTC_USDT", "active": True},
            {"symbol": "OLD_USDT", "active": False},
        ]},
    )
    monkeypatch.setattr(bingx_snapshot, "_save_top_symbols", lambda symbols: None)
    assert bingx_snapshot.top_symbols_by_volume(10) == ["BTC_USDT"]


def test_kline_is_sorted_and_converted_to_seconds(monkeypatch):
    monkeypatch.setattr(
        bingx_snapshot,
        "http_get",
        lambda *args, **kwargs: {
            "code": 0,
            "data": [
                {"time": 8_000, "open": "2", "high": "3", "low": "1", "close": "2", "volume": "4"},
                {"time": 4_000, "open": "1", "high": "2", "low": "0.5", "close": "1.5", "volume": "3"},
            ],
        },
    )
    rows = bingx_snapshot.futures_kline("BTC_USDT", "4h")["data"]
    assert [row["time"] for row in rows] == [4, 8]


def test_snapshot_uses_only_strategy_timeframes(monkeypatch):
    intervals = []
    monkeypatch.setattr(
        bingx_snapshot,
        "futures_contract_detail",
        lambda symbol: {"symbol": symbol, "priceUnit": 0.1, "contractSize": 1},
    )
    monkeypatch.setattr(
        bingx_snapshot,
        "futures_ticker",
        lambda symbol: {"code": 0, "data": {"lastPrice": "1"}},
    )

    def fake_kline(symbol, interval, limit=200):
        intervals.append(interval)
        return {"code": 0, "data": []}

    monkeypatch.setattr(bingx_snapshot, "futures_kline", fake_kline)
    snapshot = bingx_snapshot.build_snapshot("BTC_USDT")
    assert intervals == ["1h", "4h", "1d"]
    assert snapshot["exchange"] == "bingx"


def test_recent_cache_is_marked_stale(monkeypatch):
    source_ts = int((time.time() - 60) * 1000)
    monkeypatch.setattr(
        bingx_snapshot,
        "build_snapshot",
        lambda symbol: (_ for _ in ()).throw(RuntimeError("rate limited")),
    )
    monkeypatch.setattr(
        bingx_snapshot,
        "load_cache",
        lambda symbol: {"symbol": symbol, "ts": source_ts, "exchange": "bingx"},
    )
    snapshot = bingx_snapshot.build_snapshot_with_fallback("BTC_USDT")
    assert snapshot["stale"] is True
    assert snapshot["ts"] == source_ts
