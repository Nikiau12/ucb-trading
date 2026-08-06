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
import telegram_render  # noqa: E402
from analytics.structure import Bar, Swing  # noqa: E402


def test_stale_snapshot_is_always_skipped():
    plan = trade_plan.make_plan(
        {"symbol": "BTC_USDT", "stale": True},
        deposit=300.0,
        risk_pct=2.0,
        lev=10.0,
        margin="isolated",
    )

    assert plan == {
        "symbol": "BTC_USDT",
        "side": "skip",
        "confidence": 0.0,
        "reasons": ["stale_market_data"],
        "used_cache": True,
    }


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


def test_contract_normalization_uses_valid_ticks_and_does_not_exceed_risk():
    normalized = trade_plan.normalize_for_contract(
        {
            "contract": {
                "priceUnit": 0.01,
                "contractSize": 0.1,
                "volUnit": 1,
                "minVol": 1,
                "maxVol": 1000,
            }
        },
        "long",
        entry=100.006,
        stop=95.009,
        tp1=105.001,
        tp2=110.001,
        deposit=100.0,
        risk_pct=1.0,
    )

    assert normalized["entry"] == 100.01
    assert normalized["stop"] == 95.0
    assert normalized["tp1"] == 105.01
    assert normalized["tp2"] == 110.01
    assert normalized["contract_vol"] == 1
    assert normalized["qty"] == 0.1
    assert 0 < normalized["risk_usdt"] <= 1.0
    assert normalized["errors"] == []


def test_short_contract_prices_round_away_from_entry():
    normalized = trade_plan.normalize_for_contract(
        {
            "contract": {
                "priceUnit": 0.1,
                "contractSize": 0.01,
                "volUnit": 1,
                "minVol": 1,
            }
        },
        "short",
        entry=100.04,
        stop=104.91,
        tp1=95.09,
        tp2=90.09,
        deposit=100.0,
        risk_pct=1.0,
    )

    assert normalized["entry"] == 100.0
    assert normalized["stop"] == 105.0
    assert normalized["tp1"] == 95.0
    assert normalized["tp2"] == 90.0


def test_plan_is_rejected_when_minimum_contract_exceeds_risk_budget():
    normalized = trade_plan.normalize_for_contract(
        {
            "contract": {
                "priceUnit": 0.1,
                "contractSize": 1,
                "volUnit": 1,
                "minVol": 1,
            }
        },
        "long",
        entry=100.0,
        stop=95.0,
        tp1=105.0,
        tp2=110.0,
        deposit=10.0,
        risk_pct=1.0,
    )

    assert normalized["contract_vol"] == 0
    assert normalized["qty"] == 0
    assert "position_below_min_contract" in normalized["errors"]


def test_price_formatter_preserves_exchange_tick_precision():
    assert telegram_render._fmt_price(63159.7, 0.1) == "63 159.7"
    assert telegram_render._fmt_price(0.07365, 0.00001) == "0.07365"
