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
    clock = [100.]
    def sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds
    client = bingx_snapshot.BingxPublicClient(
        min_interval=0,
        max_attempts=3,
        sleep=sleep,
        clock=lambda: clock[0],
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


@pytest.mark.parametrize("code,message", [(100410, "rate limited"), (100500, "请稍后重试"),
                                         (109500, "internal error"), (109701, "network request exception"),
                                         (999999, "请稍后重试")])
def test_public_transient_errors_have_bounded_retries(code, message):
    clock, calls, sleeps = [100.], [], []
    def request(*_args, **_kwargs):
        calls.append(1)
        return FakeResponse({"code": code, "msg": message})
    def sleep(delay):
        sleeps.append(delay)
        clock[0] += delay
    client = bingx_snapshot.BingxPublicClient(min_interval=0, max_attempts=3,
        request_get=request, clock=lambda: clock[0], sleep=sleep)
    with pytest.raises(bingx_snapshot.BingxAPIError):
        client.get("/public")
    assert len(calls) == 3 and sleeps == [1, 2]


@pytest.mark.parametrize("code", [100001, 100004, 100400, 100413, 100419, 100421, 109400, 109403, 109425, 109429])
def test_signature_permission_and_parameter_errors_are_not_retried(code):
    calls = []
    client = bingx_snapshot.BingxPublicClient(min_interval=0,
        request_get=lambda *_a, **_kw: calls.append(1) or FakeResponse({"code": code, "msg": "please retry later"}),
        sleep=lambda *_: pytest.fail("permanent error was retried"))
    with pytest.raises(bingx_snapshot.BingxAPIError):
        client.get("/public")
    assert calls == [1]


@pytest.mark.parametrize("payload", [{}, {"code": None}, {"code": "garbage"}, {"code": False}, {"code": .2}, []])
def test_malformed_api_code_is_not_treated_as_success(payload):
    client = bingx_snapshot.BingxPublicClient(min_interval=0,
        request_get=lambda *_a, **_kw: FakeResponse(payload))
    with pytest.raises(bingx_snapshot.BingxAPIError):
        client.get("/public")


@pytest.mark.parametrize("header", ["NaN", "inf", "-1", "broken"])
def test_invalid_retry_after_uses_finite_default(header):
    responses = iter([FakeResponse({}, 429, {"Retry-After": header}), FakeResponse({"code": 0})])
    clock, sleeps = [100.], []
    def sleep(delay):
        sleeps.append(delay)
        clock[0] += delay
    client = bingx_snapshot.BingxPublicClient(min_interval=0, clock=lambda: clock[0], sleep=sleep,
        request_get=lambda *_a, **_kw: next(responses))
    assert client.get("/public") == {"code": 0}
    assert sleeps == [1]


def test_long_retry_after_pauses_other_requests_without_blocking_worker():
    calls = []
    client = bingx_snapshot.BingxPublicClient(min_interval=0, clock=lambda: 100.,
        sleep=lambda *_: pytest.fail("long backoff blocked the scanner"),
        request_get=lambda *_a, **_kw: calls.append(1) or FakeResponse({}, 429, {"Retry-After": "600"}))
    with pytest.raises(bingx_snapshot.requests.HTTPError):
        client.get("/public")
    with pytest.raises(bingx_snapshot.BingxAPIError, match="cooldown"):
        client.get("/public")
    assert calls == [1]


def test_group_snapshot_does_not_fetch_legacy_candles_or_disk_fallback(monkeypatch):
    monkeypatch.setattr(bingx_snapshot, "futures_contract_detail", lambda s: {"symbol": s})
    monkeypatch.setattr(bingx_snapshot, "futures_ticker", lambda s: {"code": 0, "data": {"lastPrice": "1"}})
    monkeypatch.setattr(bingx_snapshot, "futures_kline", lambda *_: pytest.fail("redundant candles"))
    monkeypatch.setattr(bingx_snapshot, "load_cache", lambda *_: pytest.fail("stale fallback"))
    assert bingx_snapshot.build_group_snapshot("AVAX-USDT")["symbol"] == "AVAX_USDT"
    monkeypatch.setattr(bingx_snapshot, "futures_ticker", lambda *_: (_ for _ in ()).throw(bingx_snapshot.BingxAPIError("unavailable")))
    with pytest.raises(bingx_snapshot.BingxAPIError):
        bingx_snapshot.build_group_snapshot("AVAX_USDT")


def test_concurrent_contract_metadata_fetch_is_single_flight(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    calls = []
    monkeypatch.setattr(bingx_snapshot, "_CONTRACT_CACHE", {})
    monkeypatch.setattr(bingx_snapshot, "_CONTRACT_CACHE_TS", 0)
    def request(*_args, **_kwargs):
        calls.append(1)
        time.sleep(.01)
        return {"code": 0, "data": [{"symbol": "BTC-USDT", "asset": "BTC", "status": 1, "apiStateOpen": "true"}]}
    monkeypatch.setattr(bingx_snapshot, "http_get", request)
    with ThreadPoolExecutor(max_workers=8) as executor:
        result = list(executor.map(bingx_snapshot.futures_contract_detail, ["BTC_USDT"] * 8))
    assert calls == [1]
    assert all(row["symbol"] == "BTC_USDT" for row in result)
