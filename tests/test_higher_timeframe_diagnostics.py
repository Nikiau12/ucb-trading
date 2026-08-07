from evaluation.diagnose_higher_timeframe_trades import diagnostic_summary, _trend_age


def test_trend_age_counts_current_alignment_run():
    closes = [100.0] * 55 + [100.0 + index for index in range(20)]
    assert _trend_age(closes) > 0


def test_diagnostic_summary_separates_winners_and_losers():
    rows = [
        {
            "net_pnl": 10.0,
            "r_multiple": 1.0,
            "holding_bars": 2,
            "adx_4h": 30.0,
            "atr_4h_pct": 2.0,
            "daily_trend_age_bars": 10,
            "daily_extension_atr": 0.4,
            "close_4h_extension_atr": 0.2,
            "pullback_depth_atr": 0.3,
            "trigger_body_ratio": 0.7,
            "side": "long",
            "exit_reason": "tp2",
        },
        {
            "net_pnl": -10.0,
            "r_multiple": -1.0,
            "holding_bars": 3,
            "adx_4h": 20.0,
            "atr_4h_pct": 4.0,
            "daily_trend_age_bars": 20,
            "daily_extension_atr": 1.0,
            "close_4h_extension_atr": 0.5,
            "pullback_depth_atr": 0.8,
            "trigger_body_ratio": 0.3,
            "side": "short",
            "exit_reason": "stop",
        },
    ]
    summary = diagnostic_summary(rows)
    assert summary["all"]["trades"] == 2
    assert summary["winners"]["mean_r"] == 1.0
    assert summary["losers"]["mean_r"] == -1.0
    assert summary["by_side"] == {"long": 1, "short": 1}
