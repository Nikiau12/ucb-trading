"""Closed-candle geometry, disclosure and scanner admission checks."""
from types import SimpleNamespace

import pytest

from trading import group_journal_ideas as journal
from trading import group_plan
from trading.group_labels import strategy_notice


def bar(ts, o, h, l, c, v=100):
    return SimpleNamespace(ts=ts, o=o, h=h, l=l, c=c, v=v)


def feature():
    bars = [bar(i * 14400, 101, 102, 100, 101) for i in range(60)]
    bars[-2] = bar(58 * 14400, 100.5, 101.5, 99.7, 100.8)
    bars[-1] = bar(59 * 14400, 100.8, 102.4, 100.4, 102)
    h = {key: [value] * 60 for key, value in
         (("atr", 2), ("ema20", 100), ("ema50", 99))}
    return {"bars": bars, "h": h, "daily": [bar(0, 100, 103, 97, 102)],
            "d": {"ema20": [100], "ema50": [99]}, "regime": "transition"}


def test_journal_geometry_uses_last_closed_4h_bar_and_valid_levels():
    data = feature()
    plan = journal._geometry(data, "long", "trend_flag", .01)
    assert plan is not None
    assert plan["signal_time"] == 60 * 14400
    assert plan["entry"] > data["bars"][-1].h
    assert plan["stop"] < plan["entry"] < plan["tp1"] < plan["tp2"]
    assert (plan["tp1"] - plan["entry"]) / plan["risk_price"] >= 1
    assert journal._geometry(data, "short", "trend_flag", .01) is None


def test_no_idea_on_flat_bar_or_invalid_atr():
    data = feature()
    data["bars"][-1] = bar(59 * 14400, 101, 101.1, 100.9, 101)
    assert journal._geometry(data, "long", "trend_flag", .01) is None
    data = feature()
    data["h"]["atr"][-1] = None
    assert journal._geometry(data, "long", "trend_flag", .01) is None


def test_journal_score_is_disclosed_as_rules_not_profit_probability(monkeypatch):
    data = feature()
    monkeypatch.setattr(journal.base, "features", lambda _bars, _as_of: data)
    result = journal.candidate("BTC_USDT", "long", {"BTC_USDT": data["bars"]},
                               as_of=60 * 14400, tick=.01, _feature_cache={})
    assert result["status"] == "technical_candidate_not_admitted"
    assert result["criteria_score"] == .85
    plan = {"strategy": {"experimental": True, "mode": "journal_idea",
                         "entry_expires_at": 61 * 14400, "max_holding_seconds": 96 * 3600},
            "primary": {"confidence": result["criteria_score"]}}
    notice = strategy_notice(plan, "ru")
    assert "85%" in notice and "не вероятность прибыли" in notice
    assert "Экспериментальная стратегия" not in notice
    saved_notice = strategy_notice({"strategy": plan["strategy"], "confidence": .75},
                                   "ru", details=False)
    assert "75%" in saved_notice


def test_scanner_precheck_does_not_fetch_depth_or_1m(monkeypatch):
    as_of = 60 * 14400
    current = as_of + 300
    snapshot = {"symbol": "BTC_USDT", "ts": current * 1000, "exchange": "bingx",
                "contract": {"symbol": "BTC_USDT", "active": True, "priceUnit": .01,
                             "contractSize": 1, "volUnit": .001, "minVol": .001,
                             "maxLeverage": 5, "raw": {"takerFeeRate": .0005}},
                "ticker": {"data": {"lastPrice": 99, "quoteVolume": 10_000_000}}}
    raw = {"symbol": "BTC_USDT", "group": "core_btc", "side": "long", "family": "journal_trend_flag",
           "entry": 100., "stop": 95., "tp1": 106.25, "tp2": 111.25,
           "risk_price": 5., "signal_time": as_of, "entry_expiry_seconds": 8 * 3600,
           "max_holding_seconds": 96 * 3600, "daily_regime": "transition",
           "criteria": {"daily_close": True}, "criteria_score": .65,
           "profile_version": journal.VERSION, "decision_key": "journal-sample",
           "status": "technical_candidate_not_admitted"}
    monkeypatch.setattr(group_plan, "history", lambda *_args: [])
    monkeypatch.setattr(group_plan, "candidate", lambda _symbol, side, *_args, **_kw:
                        raw if side == "long" else {"status": "no_setup", "reason": "none"})
    monkeypatch.setattr(group_plan, "check_execution_market", lambda *_a, **_kw:
                        pytest.fail("Scanner must defer the depth book"))
    monkeypatch.setattr(group_plan, "check_unused_trigger", lambda *_a, **_kw:
                        pytest.fail("Scanner must defer the 1m path"))
    plan = group_plan.make_plan(snapshot, 300, 2, 10, "cross", now=current, market_checks=False)
    assert plan["primary"]["confidence"] == .65
    assert plan["strategy"]["version"] == journal.VERSION
    assert plan["strategy"]["execution_checks"]["scanner_precheck_only"] is True
