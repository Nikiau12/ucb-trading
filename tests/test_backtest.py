from trading.analytics.structure import Bar
from trading.backtest import BacktestConfig, resample_completed, run_backtest


HOUR = 60 * 60


def _bars(count=12):
    return [
        Bar(ts=index * HOUR, o=100, h=102, l=98, c=100, v=10)
        for index in range(count)
    ]


def _plan(side="long"):
    return {
        "symbol": "BTC_USDT",
        "primary": {
            "side": side,
            "confidence": 0.9,
            "entry": 100,
            "stop": 90 if side == "long" else 110,
            "tps": [
                {"price": 110 if side == "long" else 90, "pct": 0.5},
                {"price": 120 if side == "long" else 80, "pct": 0.5},
            ],
            "qty": 1,
            "risk_usdt": 10,
        },
    }


def test_resampling_excludes_incomplete_future_candles():
    bars = _bars(30)
    decision_time = 25 * HOUR

    four_hour = resample_completed(bars, 4 * HOUR, decision_time)
    daily = resample_completed(bars, 24 * HOUR, decision_time)

    assert [bar.ts for bar in four_hour] == [0, 4 * HOUR, 8 * HOUR, 12 * HOUR, 16 * HOUR, 20 * HOUR]
    assert [bar.ts for bar in daily] == [0]
    assert all(bar.ts + 4 * HOUR <= decision_time for bar in four_hour)
    assert all(bar.ts + 24 * HOUR <= decision_time for bar in daily)


def test_plan_builder_never_receives_future_or_partial_candles():
    decisions = []

    def builder(snapshot, **_kwargs):
        latest_1h = snapshot["kline_1h"]["data"][-1][0] + HOUR
        decisions.append(latest_1h)
        assert all(row[0] + HOUR <= latest_1h for row in snapshot["kline_1h"]["data"])
        assert all(row[0] + 4 * HOUR <= latest_1h for row in snapshot["kline_4h"]["data"])
        assert all(row[0] + 24 * HOUR <= latest_1h for row in snapshot["kline_1d"]["data"])
        return {"side": "skip", "confidence": 0, "reasons": ["test"]}

    run_backtest(
        _bars(40),
        config=BacktestConfig(warmup_hours=25, decision_interval_hours=3),
        plan_builder=builder,
    )

    assert decisions


def test_ambiguous_fill_candle_uses_stop_first():
    bars = _bars()
    bars[2] = Bar(ts=2 * HOUR, o=100, h=121, l=89, c=105, v=10)
    calls = 0

    def builder(_snapshot, **_kwargs):
        nonlocal calls
        calls += 1
        return _plan() if calls == 1 else {"side": "skip", "confidence": 0, "reasons": ["test"]}

    result = run_backtest(
        bars,
        config=BacktestConfig(
            warmup_hours=2, entry_expiry_bars=1, max_holding_bars=3,
            fee_bps=4, slippage_bps=2,
        ),
        plan_builder=builder,
    )

    assert result["summary"]["trades"] == 1
    assert result["trades"][0]["exit_reason"] == "stop"
    assert result["trades"][0]["net_pnl"] < -10


def test_fees_and_slippage_reduce_reported_performance():
    bars = _bars()
    bars[3] = Bar(ts=3 * HOUR, o=100, h=121, l=99, c=120, v=10)

    def run(fee_bps, slippage_bps):
        calls = 0

        def builder(_snapshot, **_kwargs):
            nonlocal calls
            calls += 1
            return _plan() if calls == 1 else {"side": "skip", "confidence": 0, "reasons": ["test"]}

        return run_backtest(
            bars,
            config=BacktestConfig(
                warmup_hours=2, entry_expiry_bars=1, max_holding_bars=4,
                fee_bps=fee_bps, slippage_bps=slippage_bps,
            ),
            plan_builder=builder,
        )

    frictionless = run(0, 0)
    realistic = run(4, 2)

    assert realistic["summary"]["net_pnl"] < frictionless["summary"]["net_pnl"]
    assert realistic["summary"]["fees_paid"] > 0
