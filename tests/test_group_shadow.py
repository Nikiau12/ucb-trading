"""Virtual results are per signal and never presented as exchange fills."""
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from trading import group_shadow as shadow
from trading.group_plan import VERSION


NOW = datetime(2026, 11, 7, 20, tzinfo=timezone.utc)


def signal(*, side="LONG", status="stopped", entered=True, tp1=False, tp2=False,
           fee=.0005, group="core_btc"):
    short = side == "SHORT"
    return {"id": 42, "symbol": "BTC_USDT", "side": side,
            "entry": 100, "stop": 105 if short else 95,
            "tp1": 92 if short else 108, "tp2": 88 if short else 112,
            "created_at": NOW - timedelta(hours=4),
            "lifecycle_updated_at": NOW,
            "lifecycle_status": status,
            "entry_hit_at": NOW - timedelta(hours=3) if entered else None,
            "tp1_hit_at": NOW - timedelta(hours=2) if tp1 else None,
            "tp2_hit_at": NOW - timedelta(hours=1) if tp2 else None,
            "stop_hit_at": NOW - timedelta(hours=1) if status == "stopped" else None,
            "expired_at": NOW - timedelta(hours=1) if status == "expired" else None,
            "strategy": {"version": VERSION, "catalog_version": "catalog-test", "group": group,
                         "execution_checks": {"public_taker_fee": fee}}}


def test_no_entry_open_and_missing_funding_never_become_zero_profit():
    cancelled = shadow.model_result(signal(status="cancelled_before_entry", entered=False), now=NOW)
    assert cancelled["outcome"] == "cancelled_before_entry"
    assert cancelled["net_r"] is None and cancelled["entered_at"] is None
    open_trade = shadow.model_result(signal(status="tp1_reached", tp1=True), now=NOW)
    assert open_trade["outcome"] == "tp1_open" and open_trade["net_r"] is None
    pending = shadow.model_result(signal(), now=NOW)
    assert pending["outcome"] == "stopped_before_tp1"
    assert pending["cost_status"] == "pending_funding_history" and pending["net_r"] is None
    missing_fee = shadow.model_result(signal(fee=None), funding_complete=True, now=NOW)
    assert missing_fee["cost_status"] == "missing_signal_fee" and missing_fee["net_r"] is None


@pytest.mark.parametrize("side,tp1,tp2,expected_gross", [
    ("LONG", False, False, -1.0), ("SHORT", False, False, -1.0),
    ("LONG", True, False, .8), ("SHORT", True, False, .8),
    ("LONG", True, True, 2.0), ("SHORT", True, True, 2.0),
])
def test_long_short_stop_be_tp2_after_costs(side, tp1, tp2, expected_gross):
    status = "tp2_reached" if tp2 else "stopped"
    row = signal(side=side, status=status, tp1=tp1, tp2=tp2)
    if tp1 and tp2:
        row["tp1_hit_at"] = NOW - timedelta(hours=2)
    record = shadow.model_result(row, funding_complete=True, now=NOW)
    assert record["outcome"] == ("tp2" if tp2 else "tp1_then_be" if tp1 else "stopped_before_tp1")
    assert record["gross_r"] == pytest.approx(expected_gross)
    assert record["slippage_r"] > 0 and record["fee_r"] > 0
    assert record["funding_r"] == 0 and record["net_r"] < record["gross_r"]
    assert record["net_r"] == pytest.approx(record["gross_r"]-record["slippage_r"]-record["fee_r"])


def test_funding_uses_direction_mark_price_and_remaining_fraction():
    for side, sign in (("LONG", -1), ("SHORT", 1)):
        row = signal(side=side, status="tp2_reached", tp1=True, tp2=True)
        events = [(NOW - timedelta(hours=2, minutes=30), .001, 101),
                  (NOW - timedelta(hours=1, minutes=30), .001, 103)]
        record = shadow.model_result(row, funding_events=events, funding_complete=True, now=NOW)
        assert record["funding_r"] == pytest.approx(sign * (.001*101 + .001*103*.5) / 5)
        assert record["net_r"] == pytest.approx(record["gross_r"]-record["slippage_r"]
                                                 -record["fee_r"]+record["funding_r"])


def test_expiry_requires_nearby_closed_candle_and_bad_levels_fail_closed():
    expired = signal(status="expired", tp1=True)
    missing = shadow.model_result(expired, funding_complete=True, now=NOW)
    assert missing["outcome"] == "expired_after_tp1" and missing["cost_status"] == "pending_exit_price"
    priced = shadow.model_result(expired, funding_complete=True, expiry_price=104, now=NOW)
    assert priced["cost_status"] == "complete" and priced["gross_r"] == pytest.approx(1.2)
    bad = signal()
    bad["stop"] = 110
    assert shadow.model_result(bad, funding_complete=True, now=NOW)["cost_status"] == "invalid_levels"


def test_direct_jump_to_tp2_is_counted_but_not_claimed_as_two_fills():
    direct = signal(status="tp2_reached", tp1=True, tp2=True)
    direct["tp1_hit_at"] = direct["tp2_hit_at"]
    record = shadow.model_result(direct, funding_complete=True, now=NOW)
    assert record["outcome"] == "tp2"
    assert record["cost_status"] == "ambiguous_target_sequence"
    assert record["net_r"] is None


def test_funding_history_requires_both_boundaries_and_rejects_gaps(monkeypatch):
    captured = []
    def payload(path, params):
        captured.append((path,params))
        return {"data": [{"symbol":"BTC-USDT","fundingTime":int(ts.timestamp()*1000),
                          "fundingRate":rate,"markPrice":"100"}
                         for ts,rate in records]}
    monkeypatch.setattr(shadow, "_public", lambda: SimpleNamespace(http_get=payload,
        to_bingx_symbol=lambda _:"BTC-USDT"))
    start, end = NOW - timedelta(hours=18), NOW - timedelta(hours=2)
    records = [(NOW - timedelta(hours=20), .001), (NOW - timedelta(hours=12), -.001),
               (NOW - timedelta(hours=4), .001), (NOW + timedelta(hours=4), .001)]
    events, covered = shadow.funding_history("BTC_USDT", start, end, now=NOW+timedelta(hours=4))
    assert covered and len(events)==2 and events[0][1] < 0
    assert captured[0][0].endswith("fundingRate") and captured[0][1]["limit"] == 1000
    records.pop()
    assert shadow.funding_history("BTC_USDT", start, end, now=NOW+timedelta(hours=4))[1] is False
    records[:] = [(NOW - timedelta(hours=40), .001),
                  (NOW - timedelta(hours=12), -.001),
                  (NOW - timedelta(hours=1), .001)]
    assert shadow.funding_history("BTC_USDT", start, end, now=NOW)[1] is False
    records[:] = [(NOW - timedelta(hours=28), .001),
                  (NOW - timedelta(hours=20), .001),
                  (NOW - timedelta(hours=4), .001),
                  (NOW + timedelta(hours=4), .001)]
    assert shadow.funding_history("BTC_USDT", start, end, now=NOW+timedelta(hours=4))[1] is False


def test_expiry_close_ignores_forming_or_stale_candles(monkeypatch):
    expired = NOW - timedelta(hours=1, seconds=30)
    minute = int(expired.timestamp() // 60 * 60)
    rows = [[(minute-60)*1000,"1","1","1","103","1"],
            [minute*1000,"1","1","1","999","1"]]
    monkeypatch.setattr(shadow,"_public",lambda:SimpleNamespace(
        http_get=lambda *_args,**_kwargs:{"data":rows},to_bingx_symbol=lambda _:"BTC-USDT"))
    assert shadow.expiry_close("BTC_USDT",expired,now=NOW)==103
    rows.pop(0)
    assert shadow.expiry_close("BTC_USDT",expired,now=NOW) is None


def test_report_counts_one_signal_and_marks_small_samples():
    row = signal(status="tp2_reached",tp1=True,tp2=True)
    complete = shadow.model_result(row,funding_complete=True,now=NOW)
    item = {"signal_id":42,"strategy_version":VERSION,"catalog_version":"catalog-test",
            "asset_group":"core_btc","side":"long","entered_at":row["entry_hit_at"],
            "closed_at":complete["closed_at"],"outcome":complete["outcome"],
            "cost_status":complete["cost_status"],"net_r":complete["net_r"]}
    report = shadow.summarize([item],min_complete=20)
    selected = next(r for r in report["rows"] if r["catalog_version"]=="catalog-test")
    assert selected["signals"]==selected["entered"]==selected["complete_net"]==1
    assert selected["outcomes"]=={"tp2":1} and selected["net_positive_rate"] is None
    assert selected["sample_status"]=="insufficient_data"
    assert len([r for r in report["rows"] if r["strategy_version"]==VERSION])>=32
    assert report["overall"]["signals"]==1 and report["overall"]["complete_net"]==1
    assert report["rows"][0]["group"]=="core_btc"
    assert "недостаточно данных" in shadow.markdown_report({"days":30,**report})


def test_report_does_not_hide_a_terminal_signal_awaiting_sync():
    raw = signal(status="stopped", tp1=True)
    item = {"signal_id":42,"strategy_version":VERSION,"catalog_version":"catalog-test",
            "asset_group":"core_btc","side":"long","entered_at":raw["entry_hit_at"],
            "closed_at":None,"outcome":None,"cost_status":None,"net_r":None,
            "lifecycle_status":"stopped","tp1_hit_at":raw["tp1_hit_at"],
            "tp2_hit_at":None,"stop_hit_at":raw["stop_hit_at"],"expired_at":None}
    report = shadow.summarize([item])
    selected = next(r for r in report["rows"] if r["catalog_version"]=="catalog-test")
    assert selected["closed_entered"]==selected["pending_or_incomplete_net"]==1
    assert selected["not_yet_synced"]==1 and selected["complete_net"]==0
    assert selected["outcomes"]=={"tp1_then_be":1}


def test_worker_shadow_loop_isolated_from_signal_and_delivery_loops(monkeypatch):
    from core.background_loops import bind_background_loops
    seen = []
    def record(name, **kwargs):
        seen.append((name, kwargs))
        raise asyncio.CancelledError()
    monkeypatch.setattr(shadow,"sync_pending",lambda **kwargs:{
        "market_data_errors":0,"examined":1,"model_version":shadow.MODEL_VERSION})
    services = SimpleNamespace(st=SimpleNamespace(record_runtime_health=record),
                               logger=SimpleNamespace(warning=lambda *_args:None))
    asyncio.run(bind_background_loops(services).group_shadow_loop())
    assert seen[0][0] == "group_shadow" and seen[0][1]["success"] is True
