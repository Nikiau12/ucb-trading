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
        {
            "primary": {"side": "long"},
            "trend": {"1d": "up", "4h": "up", "regime": "trend"},
        },
        policy,
    )
    assert not accepts_candidate(
        {
            "primary": {"side": "long"},
            "trend": {"1d": "up", "4h": "down", "regime": "trend"},
        },
        policy,
    )


def test_setup_v2_filters_regime_adx_and_rsi_direction():
    plan = {
        "primary": {
            "side": "long",
            "reasons": ["adx4h≈27.3", "rsi1h≈55.1"],
        },
        "trend": {"1d": "up", "4h": "up", "regime": "trend"},
    }
    policy = Candidate(
        "trend_confirmation",
        0.6,
        allowed_regimes=("trend",),
        min_adx=25,
        require_rsi_momentum=True,
    )
    assert accepts_candidate(plan, policy)
    assert not accepts_candidate(
        {**plan, "trend": {**plan["trend"], "regime": "range"}}, policy
    )
    assert not accepts_candidate(
        {**plan, "primary": {**plan["primary"], "reasons": ["adx4h≈24.9", "rsi1h≈55.1"]}},
        policy,
    )
    assert not accepts_candidate(
        {**plan, "primary": {**plan["primary"], "reasons": ["adx4h≈27.3", "rsi1h≈45.0"]}},
        policy,
    )


def test_setup_v3_filters_entry_distance_and_caps_exhausted_adx():
    policy = Candidate(
        "near_entry",
        0.6,
        allowed_regimes=("trend",),
        max_adx=40,
        min_entry_distance_atr=0.1,
        max_entry_distance_atr=0.5,
    )

    def plan(adx, distance):
        return {
            "primary": {
                "side": "short",
                "reasons": [f"adx4h≈{adx}", f"entry_dist_ATR4h={distance}"],
            },
            "trend": {"regime": "trend"},
        }

    assert accepts_candidate(plan(39.9, 0.3), policy)
    assert not accepts_candidate(plan(40, 0.3), policy)
    assert not accepts_candidate(plan(35, 0.09), policy)
    assert not accepts_candidate(plan(35, 0.51), policy)


def test_closed_1h_confirmation_must_match_trade_side():
    policy = Candidate("confirmation", 0.6, require_1h_confirmation=True)

    def plan(side, momentum):
        return {
            "primary": {"side": side, "reasons": [f"momentum1h={momentum}"]},
            "trend": {"regime": "trend"},
        }

    assert accepts_candidate(plan("long", "up"), policy)
    assert accepts_candidate(plan("short", "down"), policy)
    assert not accepts_candidate(plan("long", "neutral"), policy)
    assert not accepts_candidate(plan("short", "up"), policy)


def test_training_gate_requires_cross_symbol_evidence():
    good = {"trades": 40, "net_pnl": 1, "symbols_positive": 2, "symbols_total": 3}
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
