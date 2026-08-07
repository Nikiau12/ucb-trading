from evaluation.run_symbol_optimization import (
    confirmation_passes,
    profile_score,
    selection_eligible,
)
from evaluation.run_walk_forward import Candidate, accepts_candidate


def test_symbol_profile_can_restrict_direction():
    long_only = Candidate("long", 0.6, allowed_sides=("long",))
    long_plan = {
        "primary": {"side": "long", "reasons": []},
        "trend": {"regime": "trend"},
    }
    short_plan = {
        "primary": {"side": "short", "reasons": []},
        "trend": {"regime": "trend"},
    }
    assert accepts_candidate(long_plan, long_only)
    assert not accepts_candidate(short_plan, long_only)


def test_selection_requires_enough_profitable_trades():
    good = {
        "trades": 15,
        "return_pct": 1.0,
        "profit_factor": 1.1,
        "max_drawdown_pct": 2.0,
    }
    assert selection_eligible(good)
    assert not selection_eligible({**good, "trades": 14})
    assert not selection_eligible({**good, "return_pct": 0})
    assert not selection_eligible({**good, "profit_factor": 1})
    assert profile_score(good) == 0


def test_confirmation_must_beat_baseline_without_more_drawdown():
    baseline = {"return_pct": 0.5, "max_drawdown_pct": 3.0}
    candidate = {
        "trades": 5,
        "return_pct": 0.8,
        "profit_factor": 1.2,
        "max_drawdown_pct": 2.5,
    }
    assert confirmation_passes(candidate, baseline)
    assert not confirmation_passes({**candidate, "trades": 4}, baseline)
    assert not confirmation_passes({**candidate, "return_pct": 0.4}, baseline)
    assert not confirmation_passes({**candidate, "max_drawdown_pct": 3.1}, baseline)
