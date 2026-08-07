from evaluation.run_btc_stability import (
    stability_eligible,
    stability_metrics,
    stability_score,
)


def summary(return_pct, trades=6, drawdown=2):
    return {
        "return_pct": return_pct,
        "trades": trades,
        "max_drawdown_pct": drawdown,
    }


def test_stability_requires_three_positive_windows_and_twenty_trades():
    metrics = stability_metrics([
        summary(1), summary(2), summary(1), summary(-0.5),
    ])
    assert metrics["positive_windows"] == 3
    assert metrics["total_trades"] == 24
    assert stability_eligible(metrics)
    assert not stability_eligible(stability_metrics([
        summary(1), summary(2), summary(-1), summary(-0.5),
    ]))
    assert not stability_eligible(stability_metrics([
        summary(1, 4), summary(2, 4), summary(1, 4), summary(-0.5, 4),
    ]))


def test_stability_score_penalizes_bad_worst_window_and_drawdown():
    stable = stability_metrics([
        summary(1), summary(1), summary(1), summary(1),
    ])
    fragile = stability_metrics([
        summary(3, drawdown=5), summary(3, drawdown=5),
        summary(3, drawdown=5), summary(-1, drawdown=5),
    ])
    assert stability_score(stable) > stability_score(fragile)
