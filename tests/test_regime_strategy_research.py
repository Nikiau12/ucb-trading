from evaluation.run_regime_strategy_research import (
    confirmation_passes_v2,
    stress_passes,
)


def summary(trades=10, return_pct=1, profit_factor=1.5, drawdown=2):
    return {
        "trades": trades,
        "return_pct": return_pct,
        "profit_factor": profit_factor,
        "max_drawdown_pct": drawdown,
    }


def test_stress_gate_requires_sample_profit_and_profit_factor():
    assert stress_passes(summary(), 10)
    assert not stress_passes(summary(trades=9), 10)
    assert not stress_passes(summary(return_pct=-0.1), 10)
    assert not stress_passes(summary(profit_factor=0.9), 10)


def test_confirmation_gate_requires_both_stress_cases():
    baseline = summary(return_pct=0.2, drawdown=3)
    candidate = summary(trades=6, return_pct=1, drawdown=2)
    stress = summary(trades=3, return_pct=0.2, drawdown=2)

    assert confirmation_passes_v2(candidate, baseline, stress, stress)
    assert not confirmation_passes_v2(
        candidate, baseline, summary(trades=2), stress
    )
