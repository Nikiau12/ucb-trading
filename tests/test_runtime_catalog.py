import copy
import json
from pathlib import Path

import pytest

from evaluation import sector_entries as research
from trading import group_candidates, group_plan
from trading.group_catalog import registry, coverage
from trading.scan_diagnostics import summarize_scan, summarize_trade_outcomes, trade_bucket
from trading.analytics.structure import Bar
from test_sector_entries_v2 import trend_bars, breakout_bars, range_bars, mirror


def test_runtime_membership_is_additive_and_ui_parity_is_validated():
    current = registry()
    assert len(current["baseline"]) == 89
    assert len(current["mapping"]) == 111
    assert all(current["mapping"][s] == g for s, g in current["baseline"].items())
    assert current["mapping"]["PAXG_USDT"] == "rwa"
    assert "ONDO_USDT" not in current["mapping"]
    assert current["mapping"]["1000SHIB_USDT"] == "meme"
    assert "SHIB_USDT" not in current["mapping"]
    assert "AVAX_USDT" not in research.load_entries()[1]


def test_coverage_distinguishes_manual_review_from_new_unknowns():
    report = coverage(["BTC_USDT", "NEAR_USDT", "CC_USDT", "NEW_USDT", "NEAR_USDT"])
    assert report["requested"] == 4 and report["classified"] == 2
    assert report["pending_review"] == {"CC_USDT": "identity_and_group_review_required"}
    assert report["unknown_symbols"] == ["NEW_USDT"]


GROUP_SYMBOLS = [next(s for s, g in registry()["baseline"].items() if g == key)
                 for key in research.load_entries()[0]["groups"]]


@pytest.mark.parametrize("symbol", GROUP_SYMBOLS)
@pytest.mark.parametrize("side", ["long", "short"])
@pytest.mark.parametrize("scenario", ["valid", "regime", "volatility", "data", "price"])
def test_runtime_extension_rules_match_frozen_baseline(monkeypatch, symbol, side, scenario):
    config, mapping = research.load_entries()
    profile = config["groups"][mapping[symbol]]
    family = profile[side].replace("TR", "R")
    bars = {"T": trend_bars, "B": breakout_bars, "R": range_bars}[family]()
    if side == "short":
        bars = mirror(bars)
    sign = 1 if side == "long" else -1
    as_of = bars[-1].ts + research.FOUR_HOURS
    benchmark = []

    def features(series, _as_of):
        if scenario == "data":
            raise ValueError("gapped candles")
        return {"regime": "transition" if scenario == "regime" else ("neutral" if family == "R" else ("up" if sign == 1 else "down")),
                "age": 5, "return20": 0 if series is benchmark else sign * .1,
                "volatility_ok": scenario != "volatility", "bars": bars,
                "daily": [Bar(0, 100, 101, 99, 100, 100)], "d": {"ema20": [100], "atr": [2]},
                "h": {"atr": [2] * len(bars), "ema20": [100], "ema50": [100-sign], "adx": [30]}}

    monkeypatch.setattr(research, "features", features)
    if scenario == "price":
        monkeypatch.setattr(research, "form_plan", lambda *_a, **_kw: None)
    markets = {"BTC_USDT": benchmark, symbol: bars}
    expected = research.candidate(symbol, side, markets, as_of=as_of, tick=.01)
    actual = group_candidates.extended_candidate(symbol, side, markets, as_of=as_of, tick=.01)
    for key in ("implementation_sha256", "decision_key"):
        expected.pop(key, None)
        actual.pop(key, None)
    assert actual == expected
    # Existing symbols retain the exact original decision identity as well.
    assert group_candidates.candidate(symbol, side, markets, as_of=as_of, tick=.01) == research.candidate(symbol, side, markets, as_of=as_of, tick=.01)


@pytest.mark.parametrize("symbol", sorted(set(registry()["mapping"]) - set(registry()["baseline"])))
def test_new_symbols_use_exact_contract_and_existing_group_binding(monkeypatch, symbol):
    observed = []
    def form(*_args, **kwargs):
        observed.append(kwargs)
        return None
    # Downstream market validation remains fail-closed for every new symbol.
    monkeypatch.setattr(research, "form_plan", form)
    result = group_candidates.candidate(symbol, "long", {}, as_of=14400, tick=.01)
    assert result["status"] == "blocked_data"
    assert observed == []


def test_unknown_symbols_never_reach_group_rule_engine():
    with pytest.raises(ValueError, match="No fallback"):
        group_candidates.candidate("SHIB_USDT", "long", {}, as_of=14400, tick=.01)


@pytest.mark.parametrize("symbol", sorted(set(registry()["mapping"]) - set(registry()["baseline"])))
def test_new_symbol_positive_route_retains_identity_and_group_parameters(monkeypatch, symbol):
    group = registry()["mapping"][symbol]
    profile = research.load_entries()[0]["groups"][group]
    family = profile["long"]
    as_of = 14400
    instrument, benchmark = [1], [2]
    def feature(series, _as_of):
        return {"regime": "neutral" if family == "R" else "up", "age": 5,
                "return20": .1 if series is instrument else 0, "volatility_ok": True,
                "bars": [], "daily": [Bar(0,100,101,99,100,1)],
                "d": {"ema20": [100], "atr": [2]},
                "h": {"atr": [2], "ema20": [100], "ema50": [99], "adx": [30]}}
    def form(_bars, _atrs, side, selected_family, tick, **kwargs):
        assert selected_family == family and kwargs["rv_min"] == profile["rv_long"]
        return {"family": selected_family, "side": side, "signal_time": as_of,
                "breakout_time": as_of, "entry": 100, "stop": 95, "tp1": 108, "tp2": 112}
    monkeypatch.setattr(research, "features", feature)
    monkeypatch.setattr(research, "form_plan", form)
    result = group_candidates.candidate(symbol, "long", {symbol: instrument, "BTC_USDT": benchmark}, as_of=as_of, tick=.01)
    assert result["status"] == "technical_candidate_not_admitted"
    assert result["symbol"] == symbol and result["group"] == group
    assert result["max_holding_seconds"] == min(profile["max_hours"], 72 if family == "R" else 96) * 3600
    assert result["entry"] == 100 and result["tp2"] == 112  # Never rescale numerical-prefix contracts.


def test_market_filter_rejections_are_not_reported_as_broken_data():
    summary, _ = summarize_scan(["AVAX_USDT"], [{"symbol": "AVAX_USDT", "side": "skip",
        "reasons": ["group_liquidity_turnover"]}], strategy_version="test")
    assert summary["outcomes"]["blocked_market"] == 1 and summary["failed"] == 0


def test_scan_statistics_keep_failures_cancellations_and_no_setups_distinct():
    symbols = ["BTC_USDT", "ETH_USDT", "SOL_USDT", "CC_USDT", "AVAX_USDT", "NEAR_USDT"]
    plans = [
        {"symbol": "BTC_USDT", "primary": {"side": "long"}, "secret": "never persist"},
        {"symbol": "ETH_USDT", "side": "skip", "reasons": ["group_no_setup:daily_regime/price_confirmation"],
         "direction_decisions": [{"side": "long", "status": "no_setup", "reason": "daily_regime"}]},
        {"symbol": "SOL_USDT", "side": "skip", "reasons": ["group_data_unavailable:gapped candles"]},
        {"symbol": "CC_USDT", "side": "skip", "reasons": ["unclassified_symbol_no_group_fallback"]},
        {"symbol": "AVAX_USDT", "side": "skip", "reasons": ["group_sizing:volume_too_small"]},
    ]
    before = copy.deepcopy(plans)
    summary, rows = summarize_scan(symbols, plans, strategy_version="test")
    assert summary["outcomes"] == {"candidate": 1, "no_setup": 1, "blocked_catalog": 1,
                                    "blocked_market": 1, "insufficient_history": 0, "data_unavailable": 2}
    assert summary["failed"] == 2 and summary["completed"] == 4
    assert summary["strategy_evaluated"] == 3 and summary["pending_catalog_review"] == 1
    assert summary["by_group_direction"] == {"core_btc:long": {"candidate": 1}, "core_eth:long": {"no_setup": 1}}
    assert len(rows) == 6 and plans == before
    assert "secret" not in json.dumps(rows) and "gapped candles" not in json.dumps(rows)


def test_stale_data_is_not_a_successful_no_setup():
    summary, _ = summarize_scan(["BTC_USDT"], [{"symbol": "BTC_USDT", "used_cache": True}], strategy_version="test")
    assert summary["failed"] == summary["stale"] == 1


def test_short_listed_history_is_distinct_from_stale_or_failed_data():
    short = {"symbol": "JST_USDT", "side": "skip",
             "reasons": ["group_data_rejected:insufficient_group_history"]}
    summary, rows = summarize_scan(["JST_USDT"], [short], strategy_version="test")
    assert summary["schema_version"] == 2
    assert summary["failed"] == summary["strategy_evaluated"] == 0
    assert summary["outcomes"]["insufficient_history"] == 1
    assert summary["history_not_ready"] == [{"symbol": "JST_USDT", "group": "defi",
        "outcome": "insufficient_history", "reasons": ["group_data_rejected"],
        "detail_code": "insufficient_group_history"}]
    assert rows == summary["history_not_ready"]
    stale = {"symbol": "JST_USDT", "side": "skip",
             "reasons": ["group_data_rejected:stale_group_history"]}
    unavailable, _ = summarize_scan(["JST_USDT"], [stale], strategy_version="test")
    assert unavailable["failed"] == 1 and unavailable["outcomes"]["insufficient_history"] == 0


def test_group_history_keeps_short_listing_and_stale_response_separate(monkeypatch):
    from types import SimpleNamespace
    as_of = 120000 * group_plan.FOUR_HOURS
    rows = [SimpleNamespace(ts=as_of - group_plan.FOUR_HOURS)] * 725
    monkeypatch.setattr(group_plan, "_public", lambda: SimpleNamespace(
        futures_kline=lambda *_args: {"data": []}))
    monkeypatch.setattr(group_plan, "parse_bars", lambda *_args: rows)
    group_plan._histories.clear()
    with pytest.raises(ValueError, match="insufficient_group_history"):
        group_plan.history("JST_USDT", as_of)
    rows = [SimpleNamespace(ts=as_of - group_plan.FOUR_HOURS - 1)] * 726
    with pytest.raises(ValueError, match="stale_group_history"):
        group_plan.history("JST_USDT", as_of)


def test_frozen_research_registry_is_not_rewritten():
    raw = json.loads(Path("evaluation/asset_groups.v1.json").read_text())
    assert raw["version"] == "2026-11-07-v1"
    assert sum(len(g["symbols"]) for g in raw["groups"]) == 89


@pytest.mark.parametrize("status,entered,tp1,tp2,expected", [
    ("cancelled_before_entry", False, False, False, "cancelled_before_entry"),
    ("expired", False, False, False, "expired_before_entry"),
    ("waiting_entry", False, False, False, "awaiting_entry"),
    ("active", True, False, False, "active_without_tp1_model"),
    ("tp1_reached", True, True, False, "tp1_open_model"),
    ("stopped", True, False, False, "stop_before_tp1_model"),
    ("stopped", True, True, False, "tp1_then_stop_model"),
    ("tp2_reached", True, True, True, "tp2_model"),
    ("expired", True, False, False, "expired_after_entry_model"),
    ("expired", True, True, False, "expired_after_tp1_model"),
    ("stopped", False, False, False, "inconsistent_lifecycle"),
])
def test_trade_outcomes_require_confirmed_model_entry(status, entered, tp1, tp2, expected):
    assert trade_bucket(status, entered or None, tp1 or None, tp2 or None) == expected


def test_outcome_report_separates_versions_directions_and_unentered_signals():
    rows = [("v1", "catalog-1", "l1", "LONG", "cancelled_before_entry", None, None, None),
            ("v1", "catalog-1", "l1", "LONG", "stopped", 1, None, None),
            ("v1", "catalog-1", "l1", "SHORT", "stopped", 1, 2, None),
            ("v2", "catalog-2", "l1", "SHORT", "tp2_reached", 1, 2, 3)]
    result = summarize_trade_outcomes(rows)
    assert result["overall"]["signals"] == 4 and result["overall"]["entered"] == 3
    assert result["overall"]["buckets"] == {
        "cancelled_before_entry": 1, "stop_before_tp1_model": 1,
        "tp1_then_stop_model": 1, "tp2_model": 1,
    }
    assert len(result["by_group_direction_version"]) == 3
    assert result["by_group_direction_version"][0]["entered"] == 1
