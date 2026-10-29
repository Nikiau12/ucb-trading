from evaluation.run_bingx_forward_validation import (
    FORWARD_START,
    FROZEN_PROFILES,
    FOUR_HOURS,
    last_completed_4h,
    normalize_rows,
    profile_status,
    validate_continuity,
)


def test_forward_profiles_are_predeclared_for_each_asset():
    assert set(FROZEN_PROFILES) == {"BTC_USDT", "ETH_USDT", "SOL_USDT"}
    assert all(FROZEN_PROFILES[symbol] for symbol in FROZEN_PROFILES)
    assert FORWARD_START == 1786089600


def test_normalize_rows_sorts_reverse_bingx_dict_response():
    base = 1_700_006_400
    rows = [
        {"time": (base + 4 * FOUR_HOURS) * 1000, "open": "2", "high": "3", "low": "1", "close": "2.5", "volume": "8"},
        {"time": base * 1000, "open": "1", "high": "2", "low": "0.5", "close": "1.5", "volume": "5"},
    ]
    bars = normalize_rows(rows)
    assert [bar.ts for bar in bars] == [base, base + 4 * FOUR_HOURS]
    assert bars[1].c == 2.5


def test_last_completed_4h_never_returns_partial_candle():
    assert last_completed_4h(FOUR_HOURS * 9 + 123) == FOUR_HOURS * 9


def test_forward_gate_needs_minimum_sample_and_positive_edge():
    good = {
        "trades": 20,
        "return_pct": 2,
        "average_r": 0.2,
        "profit_factor": 1.2,
    }
    assert profile_status({**good, "trades": 19}) == "insufficient_sample"
    assert profile_status({**good, "return_pct": -1}) == "rejected"
    assert profile_status(good) == "forward_gate_passed"


def test_continuity_rejects_missing_4h_candle():
    base = 1_700_006_400
    rows = [
        [base * 1000, "1", "2", "0.5", "1.5", "5"],
        [(base + 2 * FOUR_HOURS) * 1000, "1", "2", "0.5", "1.5", "5"],
    ]
    bars = normalize_rows(rows)
    try:
        validate_continuity(bars, base, base + 3 * FOUR_HOURS)
    except RuntimeError as exc:
        assert "gaps" in str(exc)
    else:
        raise AssertionError("missing candle must fail validation")
