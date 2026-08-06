from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest
from hypothesis import given, strategies as st


TRADING_DIR = Path(__file__).resolve().parents[1] / "trading"
if str(TRADING_DIR) not in sys.path:
    sys.path.insert(0, str(TRADING_DIR))

import trade_plan  # noqa: E402
from analytics.structure import Bar, Swing  # noqa: E402


@given(
    entry=st.floats(min_value=0.000001, max_value=1_000_000, allow_nan=False, allow_infinity=False),
    risk_ratio=st.floats(min_value=0.0001, max_value=0.25, allow_nan=False, allow_infinity=False),
    rr2=st.floats(min_value=1.8, max_value=20, allow_nan=False, allow_infinity=False),
)
@pytest.mark.parametrize("side", ["long", "short"])
def test_valid_two_target_geometry_has_no_errors(side, entry, risk_ratio, rr2):
    risk = entry * risk_ratio
    if side == "long":
        stop, tp1, tp2 = entry - risk, entry + risk, entry + risk * rr2
    else:
        stop, tp1, tp2 = entry + risk, entry - risk, entry - risk * rr2
        if tp2 <= 0:
            return

    assert trade_plan.trade_plan_errors(side, entry, stop, tp1, tp2) == []


@pytest.mark.parametrize(
    ("side", "entry", "stop", "tp1", "tp2", "expected_error"),
    [
        ("long", 100.0, 95.0, 105.0, 105.0, "long_tp2_not_above_tp1"),
        ("short", 100.0, 105.0, 95.0, 95.0, "short_tp2_not_below_tp1"),
        ("long", 100.0, 105.0, 110.0, 120.0, "long_stop_not_below_entry"),
        ("short", 100.0, 95.0, 90.0, 80.0, "short_stop_not_above_entry"),
    ],
)
def test_trade_plan_errors_reject_invalid_order(side, entry, stop, tp1, tp2, expected_error):
    assert expected_error in trade_plan.trade_plan_errors(side, entry, stop, tp1, tp2)


@pytest.mark.parametrize("bad_price", [0.0, -1.0, math.nan, math.inf])
def test_trade_plan_errors_reject_non_positive_or_non_finite_prices(bad_price):
    errors = trade_plan.trade_plan_errors("long", 100.0, 95.0, 105.0, bad_price)
    assert "tp2_not_positive_finite" in errors


def _patch_range_market(monkeypatch, support: float, resistance: float) -> None:
    bars = [Bar(ts=i + 1, o=100.0, h=101.0, l=99.0, c=100.0, v=1.0) for i in range(80)]
    monkeypatch.setattr(trade_plan, "parse_bars", lambda snapshot, key: bars)
    monkeypatch.setattr(trade_plan, "last_price_from_snapshot", lambda snapshot: 100.0)
    monkeypatch.setattr(trade_plan, "trend_ema2050", lambda closes: "flat")
    monkeypatch.setattr(trade_plan, "ema", lambda *args, **kwargs: (100.0, None))
    monkeypatch.setattr(trade_plan, "atr", lambda *args, **kwargs: (5.0, None))
    monkeypatch.setattr(trade_plan, "adx", lambda *args, **kwargs: (10.0, None))
    monkeypatch.setattr(trade_plan, "rsi", lambda *args, **kwargs: (50.0, None))
    monkeypatch.setattr(trade_plan, "volatility_regime", lambda *args: "normal")
    monkeypatch.setattr(
        trade_plan,
        "swings",
        lambda *args, **kwargs: ([Swing(1, resistance, "H")], [Swing(2, support, "L")]),
    )
    monkeypatch.setattr(trade_plan, "last_structure_bias", lambda *args: "flat")
    monkeypatch.setattr(trade_plan, "bos_choch", lambda *args: "none")
    monkeypatch.setattr(trade_plan, "cluster_levels", lambda *args, **kwargs: [support, resistance])
    monkeypatch.setattr(trade_plan, "nearest_levels", lambda *args: (support, resistance))
    monkeypatch.setattr(trade_plan, "midrange_ratio", lambda *args: 0.5)


def test_range_plan_uses_distinct_ordered_targets(monkeypatch):
    _patch_range_market(monkeypatch, support=93.0, resistance=107.0)

    plan = trade_plan.make_plan(
        {"symbol": "XPL_USDT", "ticker": {}},
        deposit=300.0,
        risk_pct=2.0,
        lev=10.0,
        margin="isolated",
    )

    assert plan.get("side") != "skip"
    for side, scenario in plan["scenarios"].items():
        tp1, tp2 = (target["price"] for target in scenario["tps"])
        assert tp1 != tp2
        assert trade_plan.trade_plan_errors(
            side, scenario["entry"], scenario["stop"], tp1, tp2
        ) == []


def test_narrow_range_is_skipped_instead_of_publishing_duplicate_targets(monkeypatch):
    _patch_range_market(monkeypatch, support=97.0, resistance=103.0)

    plan = trade_plan.make_plan(
        {"symbol": "XPL_USDT", "ticker": {}},
        deposit=300.0,
        risk_pct=2.0,
        lev=10.0,
        margin="isolated",
    )

    assert plan["side"] == "skip"
    assert any("invalid_plan" in reason for reason in plan["reasons"])


def test_payload_validation_rejects_duplicate_targets_before_delivery():
    plan = {
        "primary": {
            "side": "short",
            "entry": 0.0754,
            "stop": 0.07842,
            "tps": [{"price": 0.07325}, {"price": 0.07325}],
        }
    }

    errors = trade_plan.plan_payload_errors(plan)

    assert "short_tp2_not_below_tp1" in errors
    assert "rr2_not_greater_than_rr1" in errors
