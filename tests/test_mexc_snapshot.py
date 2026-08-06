from __future__ import annotations

import time

import pytest

from trading import mexc_snapshot


class FakeResponse:
    def __init__(self, payload, status_code=200, headers=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            error = mexc_snapshot.requests.HTTPError(f"HTTP {self.status_code}")
            error.response = self
            raise error

    def json(self):
        return self._payload


def test_public_client_retries_mexc_510_with_backoff():
    responses = iter(
        [
            FakeResponse({"success": False, "code": 510, "message": "Requests are too frequent"}),
            FakeResponse({"success": True, "code": 0, "data": {"lastPrice": "1"}}),
        ]
    )
    sleeps = []
    client = mexc_snapshot.MexcPublicClient(
        min_interval=0,
        max_attempts=3,
        sleep=sleeps.append,
        request_get=lambda *args, **kwargs: next(responses),
    )

    result = client.get("/api/v1/contract/ticker")

    assert result["success"] is True
    assert sleeps == [1.0]


def test_public_client_does_not_retry_parameter_errors():
    attempts = 0

    def request_get(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        return FakeResponse({"success": False, "code": 600, "message": "Parameter error"})

    client = mexc_snapshot.MexcPublicClient(
        min_interval=0,
        max_attempts=4,
        sleep=lambda _: None,
        request_get=request_get,
    )

    with pytest.raises(mexc_snapshot.MexcAPIError) as error:
        client.get("/api/v1/contract/ticker")

    assert error.value.code == 600
    assert attempts == 1


def test_snapshot_fetches_only_timeframes_used_by_trade_plan(monkeypatch):
    intervals = []
    monkeypatch.setattr(
        mexc_snapshot,
        "futures_contract_detail",
        lambda symbol: {"symbol": symbol, "priceUnit": 0.1, "contractSize": 0.001},
    )
    monkeypatch.setattr(mexc_snapshot, "futures_ticker", lambda symbol: {"data": {"lastPrice": "1"}})

    def fake_kline(symbol, interval, limit=200):
        intervals.append(interval)
        return {"data": {"time": [1], "open": [1], "high": [1], "low": [1], "close": [1], "vol": [1]}}

    monkeypatch.setattr(mexc_snapshot, "futures_kline", fake_kline)

    snapshot = mexc_snapshot.build_snapshot("BTC_USDT")

    assert intervals == ["Min60", "Hour4", "Day1"]
    assert "funding" not in snapshot
    assert "kline_15m" not in snapshot
    assert "kline_2d" not in snapshot
    assert "kline_1w" not in snapshot
    assert snapshot["contract"]["symbol"] == "BTC_USDT"


def test_contract_details_are_cached_for_all_symbols(monkeypatch):
    calls = 0
    payload = {
        "success": True,
        "code": 0,
        "data": [
            {"symbol": "BTC_USDT", "priceUnit": 0.1},
            {"symbol": "XPL_USDT", "priceUnit": 0.00001},
        ],
    }

    def fake_get(path):
        nonlocal calls
        calls += 1
        assert path == "/api/v1/contract/detail"
        return payload

    monkeypatch.setattr(mexc_snapshot, "http_get", fake_get)
    monkeypatch.setattr(mexc_snapshot, "_CONTRACT_CACHE", {})
    monkeypatch.setattr(mexc_snapshot, "_CONTRACT_CACHE_TS", 0.0)

    assert mexc_snapshot.futures_contract_detail("BTC_USDT")["priceUnit"] == 0.1
    assert mexc_snapshot.futures_contract_detail("XPL_USDT")["priceUnit"] == 0.00001
    assert calls == 1


def test_top_symbols_falls_back_to_last_successful_ranking(monkeypatch, tmp_path):
    cache_path = tmp_path / "top_symbols.json"
    monkeypatch.setattr(mexc_snapshot, "TOP_SYMBOLS_CACHE_PATH", str(cache_path))
    monkeypatch.setattr(mexc_snapshot, "CACHE_DIR", str(tmp_path))
    tickers = {
        "success": True,
        "code": 0,
        "data": [
            {"symbol": "LOW_USDT", "amount24": "10"},
            {"symbol": "HIGH_USDT", "amount24": "100"},
        ],
    }
    monkeypatch.setattr(mexc_snapshot, "futures_all_tickers", lambda: tickers)

    assert mexc_snapshot.top_symbols_by_volume(2) == ["HIGH_USDT", "LOW_USDT"]

    monkeypatch.setattr(
        mexc_snapshot,
        "futures_all_tickers",
        lambda: (_ for _ in ()).throw(mexc_snapshot.MexcAPIError("throttled", code=510)),
    )
    assert mexc_snapshot.top_symbols_by_volume(2) == ["HIGH_USDT", "LOW_USDT"]


def test_recent_snapshot_cache_is_marked_stale_without_hiding_source_age(monkeypatch):
    source_ts = int((time.time() - 60) * 1000)
    monkeypatch.setattr(mexc_snapshot, "build_snapshot", lambda symbol: (_ for _ in ()).throw(RuntimeError("510")))
    monkeypatch.setattr(mexc_snapshot, "load_cache", lambda symbol: {"symbol": symbol, "ts": source_ts})

    snapshot = mexc_snapshot.build_snapshot_with_fallback("BTC_USDT")

    assert snapshot["stale"] is True
    assert snapshot["ts"] == source_ts
    assert snapshot["stale_reason"] == "510"
    assert snapshot["stale_at"] >= source_ts


def test_expired_snapshot_cache_is_rejected(monkeypatch):
    source_ts = int((time.time() - mexc_snapshot.SNAPSHOT_MAX_STALE_SECONDS - 1) * 1000)
    monkeypatch.setattr(mexc_snapshot, "build_snapshot", lambda symbol: (_ for _ in ()).throw(RuntimeError("510")))
    monkeypatch.setattr(mexc_snapshot, "load_cache", lambda symbol: {"symbol": symbol, "ts": source_ts})

    with pytest.raises(RuntimeError, match="cached snapshot too old"):
        mexc_snapshot.build_snapshot_with_fallback("BTC_USDT")
