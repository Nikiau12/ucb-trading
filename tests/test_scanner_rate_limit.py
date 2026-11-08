from trading import bingx_snapshot, scanner


def test_rate_limited_warmup_does_not_scan_any_symbol(monkeypatch):
    def blocked():
        raise bingx_snapshot.BingxAPIError("rate limited", code=100410)
    monkeypatch.setattr(scanner.snap, "cached_futures_all_tickers", blocked)
    monkeypatch.setattr(scanner.snap, "build_group_snapshot", lambda *_:
                        (_ for _ in ()).throw(AssertionError("No per-symbol request allowed")))
    results = scanner.scan_all(["BTC_USDT", "ETH_USDT"], deposit=300, risk_pct=2,
                               lev=10, margin="cross", workers=1)
    assert [row["error_code"] for row in results] == [100410, 100410]


def test_rate_limit_stops_remaining_symbol_requests(monkeypatch):
    seen = []
    monkeypatch.setattr(scanner.snap, "cached_futures_all_tickers", lambda: {"data": []})
    monkeypatch.setattr(scanner.core, "catalog", lambda: (None, {
        "BTC_USDT": "core_btc", "ETH_USDT": "core_eth", "SOL_USDT": "core_sol"}, None))
    def blocked(symbol):
        seen.append(symbol)
        raise bingx_snapshot.BingxAPIError("rate limited", code=100410)
    monkeypatch.setattr(scanner.snap, "build_group_snapshot", blocked)
    results = scanner.scan_all(["BTC_USDT", "ETH_USDT", "SOL_USDT"], deposit=300,
                               risk_pct=2, lev=10, margin="cross", workers=1)
    assert seen == ["BTC_USDT"]
    assert len(results) == 3
    assert all(row["error_code"] == 100410 for row in results)
