"""Offline frequency diagnostics must never be mistaken for live signals."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from evaluation import group_frequency_lab as lab
from evaluation.group_frequency_lab import full_weeks, one_day_trend, summarize_frequency
from evaluation.sector_data import FOUR_HOURS


def utc(day, hour=0):
    return int(datetime(2026, 7, day, hour, tzinfo=timezone.utc).timestamp())


def feature(*, close=105, ema20=100, ema50=95, prior_ema20=90,
            adx=25, atr=2, regime="transition"):
    return {
        "daily": [SimpleNamespace(c=100) for _ in range(3)] + [SimpleNamespace(c=close)],
        "d": {
            "ema20": [prior_ema20, 95, 98, ema20],
            "ema50": [85, 89, 92, ema50],
            "adx": [None, None, None, adx],
            "atr": [None, None, None, atr],
        },
        "regime": regime,
    }


def plan(symbol, side, timestamp, group="l1"):
    return {
        "symbol": symbol,
        "side": side,
        "group": group,
        "signal_time": timestamp,
        "entry_expiry_seconds": 2 * FOUR_HOURS,
        "max_holding_seconds": 72 * 3600,
    }


def test_one_closed_daily_trend_changes_only_directional_confirmation():
    assert one_day_trend(feature()) == "up"
    assert one_day_trend(feature(close=80, ema20=90, ema50=95,
                                 prior_ema20=100)) == "down"
    assert one_day_trend(feature(adx=19)) == "transition"
    assert one_day_trend(feature(close=99, regime="neutral")) == "neutral"
    assert one_day_trend(feature(atr=0)) == "transition"


def test_only_complete_utc_weeks_enter_frequency_denominator():
    assert full_weeks(utc(6), utc(19, 20)) == ["2026-07-06", "2026-07-13"]
    assert full_weeks(utc(7), utc(19, 20)) == ["2026-07-13"]
    assert full_weeks(utc(7), utc(19, 16)) == []
    with pytest.raises(ValueError, match="scan window"):
        full_weeks(utc(7) + 1, utc(19, 20))


def test_frequency_excludes_simultaneous_conflicts_and_reserves_symbol_lifetime():
    rows = [
        plan("BTC_USDT", "long", utc(6, 4), "core_btc"),
        plan("BTC_USDT", "short", utc(6, 4), "core_btc"),
        plan("ETH_USDT", "long", utc(6, 4), "core_eth"),
        plan("ETH_USDT", "long", utc(7, 4), "core_eth"),
        plan("ETH_USDT", "long", utc(10, 4), "core_eth"),
    ]
    result = summarize_frequency(rows, utc(6), utc(12, 20))
    assert result["technical_candidates"] == 5
    assert result["same_time_conflict_candidates"] == 2
    assert result["conservative_distinct_candidates"] == 2
    assert result["raw_per_full_week"] == {"2026-07-06": 5}
    assert result["conservative_distinct_per_full_week"] == {"2026-07-06": 2}
    assert result["full_weeks_with_20_raw"] == 0


def test_duplicate_candidate_and_invalid_lifetime_fail_closed():
    row = plan("BTC_USDT", "long", utc(6, 4))
    with pytest.raises(ValueError, match="Duplicate"):
        summarize_frequency([row, row], utc(6), utc(12, 20))
    with pytest.raises(ValueError, match="lifetime"):
        summarize_frequency([{**row, "max_holding_seconds": 97 * 3600}],
                            utc(6), utc(12, 20))
    with pytest.raises(ValueError, match="outside"):
        summarize_frequency([row], utc(7), utc(12, 20))


def test_variant_scan_fails_closed_when_capture_is_blocked():
    original_features = lab.research.features
    with patch.object(lab.research, "candidate",
                      return_value={"status": "blocked_data", "reason": "gap"}):
        with pytest.raises(ValueError, match="blocked"):
            lab.scan_one_day_trend(
                {"scan_start": utc(6), "scan_end": utc(6)}, ["BTC_USDT"],
                {}, {}, {"BTC_USDT": {}}, {"BTC_USDT": []},
                {"BTC_USDT": .01})
    assert lab.research.features is original_features
