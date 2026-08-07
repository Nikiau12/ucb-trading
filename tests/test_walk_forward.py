import pytest

from evaluation.run_walk_forward import (
    Candidate,
    accepts_candidate,
    aggregate,
    final_gate_passes,
    training_eligible,
    validation_passes,
)


def test_alignment_requires_both_timeframes_to_match_side():
    policy = Candidate("aligned", 0.6, require_trend_alignment=True)
    assert accepts_candidate(
        {"primary": {"side": "long"}, "trend": {"1d": "up", "4h": "up"}},
        policy,
    )
    assert not accepts_candidate(
        {"primary": {"side": "long"}, "trend": {"1d": "up", "4h": "down"}},
        policy,
    )


def test_training_gate_requires_cross_symbol_evidence():
    good = {"trades": 40, "net_pnl": 1, "symbols_positive": 2}
    assert training_eligible(good)
    assert not training_eligible({**good, "symbols_positive": 1})
    assert not training_eligible({**good, "net_pnl": 0})


def test_validation_and_test_gates_compare_with_baseline():
    baseline = {"return_pct": 0.4, "max_drawdown_pct": 2.0}
    candidate = {
        "trades": 20,
        "return_pct": 0.7,
        "profit_factor": 1.1,
        "max_drawdown_pct": 1.9,
    }
    assert validation_passes(candidate, baseline)
    assert final_gate_passes(candidate, baseline)
    assert not validation_passes({**candidate, "return_pct": 0.6}, baseline)


def test_aggregate_builds_portfolio_metrics_in_exit_order():
    def result(pnl, exit_time):
        return {
            "trades": [{"net_pnl": pnl, "fees": 1, "exit_time": exit_time}],
            "summary": {"net_pnl": pnl},
        }

    summary = aggregate({"BTC": result(100, 2), "ETH": result(-50, 1)}, 1_000)
    assert summary["trades"] == 2
    assert summary["net_pnl"] == 50
    assert summary["return_pct"] == pytest.approx(2.5)
    assert summary["symbols_positive"] == 1
    assert summary["fees_paid"] == 2
