import copy
from dataclasses import replace
import math
from unittest.mock import patch

import pytest

from evaluation.sector_entries import (
    admission, candidate, ema, features, form_plan, indicators, load_entries,
    load_passports, percentile, relative_volume, rma, spaced_touches,
)
from evaluation.sector_data import FOUR_HOURS, DAY, digest
from trading.analytics.structure import Bar


def mirror(bars):
    return [Bar(b.ts,200-b.o,200-b.l,200-b.h,200-b.c,b.v) for b in bars]


def trend_bars():
    bars=[Bar(i*FOUR_HOURS,100,101,99,100,100) for i in range(60)]
    bars.append(Bar(60*FOUR_HOURS,100,102,99.8,101.5,130))
    return bars


def breakout_bars():
    bars=[Bar(i*FOUR_HOURS,100,101,99,100,100) for i in range(60)]
    bars.extend([Bar(60*FOUR_HOURS,100.8,102,100.5,101.6,200),
                 Bar(61*FOUR_HOURS,101.2,102,100.8,101.6,100)])
    return bars


def range_bars():
    bars=[Bar(i*FOUR_HOURS,104,108,102,106,100) for i in range(60)]
    for i in (0,8,16):
        bars[i]=replace(bars[i],l=100)
    for i in (4,12,20):
        bars[i]=replace(bars[i],h=110)
    bars.append(Bar(60*FOUR_HOURS,100.4,101.2,100.1,101,100))
    return bars


@pytest.mark.parametrize("side",["long","short"])
@pytest.mark.parametrize("family,factory",[("T",trend_bars),("B",breakout_bars),("R",range_bars)])
def test_all_three_price_families_have_positive_mirrored_triggers(side,family,factory):
    bars=factory() if side=="long" else mirror(factory())
    plan=form_plan(bars,[2]*len(bars),side,family,.01,ema20=100,ema50=99 if side=="long" else 101,adx=30)
    assert plan and plan["family"]==family
    sign=1 if side=="long" else -1
    assert sign*(plan["entry"]-plan["stop"])>0
    assert sign*(plan["tp1"]-plan["entry"])>0
    assert sign*(plan["tp2"]-plan["tp1"])>0
    assert plan["signal_time"]==bars[-1].ts+FOUR_HOURS
    assert plan["entry_type"]=="stop"
    for key in ("entry","stop","tp1","tp2"):
        assert plan[key]*100==pytest.approx(round(plan[key]*100))


def test_breakout_without_separate_retest_never_enters():
    bars=breakout_bars()[:-1]
    assert form_plan(bars,[2]*len(bars),"long","B",.01) is None


def test_breakout_first_retest_cannot_be_reissued_next_bar():
    bars=breakout_bars()
    bars.append(replace(bars[-1],ts=bars[-1].ts+FOUR_HOURS))
    assert form_plan(bars,[2]*len(bars),"long","B",.01) is None


def test_failed_breakout_not_revived_by_later_retest():
    bars=breakout_bars(); bars[-1]=replace(bars[-1],o=100.6,l=99.9,c=100)
    bars.append(Bar(62*FOUR_HOURS,101.2,102,100.8,101.6,100))
    assert form_plan(bars,[2]*len(bars),"long","B",.01) is None


def test_breakout_retest_expiry_and_low_volume():
    bars=breakout_bars(); bars[60]=replace(bars[60],v=110)
    assert form_plan(bars,[2]*len(bars),"long","B",.01) is None
    bars=breakout_bars()[:61]
    bars += [Bar(i*FOUR_HOURS,102,103,101.8,102.5,100) for i in range(61,64)]
    bars.append(Bar(64*FOUR_HOURS,101.2,102,100.8,101.6,100))
    assert form_plan(bars,[2]*len(bars),"long","B",.01) is None


def test_range_requires_three_separated_touches_each_side():
    bars=range_bars()
    bars[8]=replace(bars[8],l=102)
    assert form_plan(bars,[2]*len(bars),"long","R",.01) is None
    assert spaced_touches([Bar(i,1,2,1,1.5,1) for i in range(9)],2,.1,True)==[0,4,8]


def test_range_rejects_poor_reward_after_rounding():
    bars=range_bars(); bars[-1]=replace(bars[-1],h=104.8)
    assert form_plan(bars,[2]*len(bars),"long","R",.01) is None


def test_trend_rejects_late_candle_bad_stop_or_no_reversal():
    bars=trend_bars()
    assert form_plan(bars,[2]*len(bars),"long","T",.01,ema20=100,ema50=99,adx=24) is None
    bars[-1]=replace(bars[-1],c=99.9)
    assert form_plan(bars,[2]*len(bars),"long","T",.01,ema20=100,ema50=99,adx=30) is None


def test_wilder_seeds_and_flat_series_are_explicit():
    assert ema([1,2,3,4],3)==[None,None,2,3]
    assert rma([None,1,2,3,4],3)==[None,None,None,2,pytest.approx(8/3)]
    bars=[Bar(i*FOUR_HOURS,100,101,99,100,1) for i in range(80)]
    result=indicators(bars)
    assert result["atr"][13] is None and result["atr"][14]==2
    assert result["adx"][26] is None and result["adx"][27]==0
    assert percentile(list(range(100)))==pytest.approx(89.1)


def test_relative_volume_excludes_current_bar_from_baseline():
    bars=[Bar(i*FOUR_HOURS,100,101,99,100,10) for i in range(21)]
    bars[-1]=replace(bars[-1],v=1000)
    assert relative_volume(bars,20)==100


def history():
    bars=[]
    for i in range(780):
        c=100+i*.03+math.sin(i/10)
        bars.append(Bar(i*FOUR_HOURS,c-.1,c+1,c-1,c,100))
    return bars


def test_features_drop_future_and_current_incomplete_day():
    bars=history(); end=768*FOUR_HOURS
    baseline=features(bars[:768],end)
    future=bars[:768]+[replace(b, c=10000,h=20000) for b in bars[768:]]
    assert features(future,end)==baseline
    early=features(bars,end+FOUR_HOURS)
    assert early["daily"][-1].ts+DAY==end


@pytest.mark.parametrize("change",["gap","duplicate","stale","short","nan","unaligned"])
def test_invalid_histories_fail_closed(change):
    bars=history(); end=780*FOUR_HOURS
    if change=="gap": bars.pop(500)
    if change=="duplicate": bars.insert(500,bars[500])
    if change=="stale": bars=bars[:-1]
    if change=="short": bars=bars[-200:]
    if change=="nan": bars[-1]=replace(bars[-1],c=float("nan"))
    if change=="unaligned": end+=1
    with pytest.raises(ValueError): features(bars,end)


def test_catalog_all_groups_and_passports_match():
    config,mapping=load_entries(); passports=load_passports()
    assert len(config["groups"])==16 and len(passports)==27
    assert len({p["group"] for p in passports.values()})==16
    assert all(mapping[s]==p["group"] for s,p in passports.items())
    assert passports["DOOD_USDT"]["mechanism_status"]=="incomplete"
    assert passports["STRK_USDT"]["additional_benchmark"]=="ETH_USDT"
    assert passports["TIA_USDT"]["additional_benchmark"] is None
    assert all(p["live_eligible"] is False for p in passports.values())


def gate_inputs(group="core_btc"):
    now=200*DAY
    plan={"symbol":"BTC_USDT","group":group,"side":"long","status":"technical_candidate_not_admitted",
          "signal_time":now,"decision_key":"fixture"}
    passport={"symbol":"BTC_USDT","group":group,"mechanism_status":"documented","reviewed_at":now-1,
              "identity_status":"documented_native_asset"}
    plan["passport_sha256"]=digest(passport)
    def record(value): return {"symbol":"BTC_USDT","known_at":now-1,"expires_at":now+1,"source":"synthetic_fixture","value":value}
    evidence={
        "contract":record({"active":True,"units_verified":True}),
        "liquidity":record({"snapshot_times":[now-50,now-25,now-1],"turnover":6e6,"bid_depth":30000,"ask_depth":30000,
                            "spread_bps":2,"buy_impact_bps":2,"sell_impact_bps":2,"assessed_notional":1000}),
        "incident":record({"clear":True,"normal_since":now-3*DAY}),
        "supply":record({"coverage_start":now-DAY,"coverage_end":now+DAY,"events":[]}),
        "cost":record({"estimated_total_r":.1}),
        "funding_forecast":record({"rate":.0001,"interval_hours":8,"settled_history":False}),
        "gold":record({"session_open":True,"license_verified":True,"quote_time":now-1,"regime":"up",
                       "spot_price":2000,"reference_price":2000,"perp_price":2000}),
    }
    return now,plan,passport,evidence


@pytest.mark.parametrize("group",list(load_entries()[0]["groups"]))
def test_all_group_admission_paths_only_accept_complete_evidence(group):
    now,plan,passport,evidence=gate_inputs(group)
    result=admission(plan,passport,evidence,as_of=now)
    assert result["admitted"] and not result["live_eligible"]


@pytest.mark.parametrize("kind",["contract","liquidity","incident","supply","cost"])
def test_missing_future_or_stale_gate_evidence_blocks(kind):
    now,plan,passport,evidence=gate_inputs()
    for change in ("missing","future","stale","wrong_symbol"):
        data=copy.deepcopy(evidence)
        if change=="missing": data.pop(kind)
        elif change=="future": data[kind]["known_at"]=now+1
        elif change=="stale": data[kind]["expires_at"]=now-1
        else: data[kind]["symbol"]="ETH_USDT"
        assert not admission(plan,passport,data,as_of=now)["admitted"]


def test_passport_cannot_be_backfilled_or_assumed_verified():
    now,plan,passport,evidence=gate_inputs()
    passport["reviewed_at"]=now+1
    assert not admission(plan,passport,evidence,as_of=now)["admitted"]
    passport["reviewed_at"]=now-1; passport["identity_status"]="contract_mapping_pending"
    assert not admission(plan,passport,evidence,as_of=now)["admitted"]


def test_release_blackout_and_incident_recovery():
    now,plan,passport,evidence=gate_inputs()
    evidence["supply"]["value"]["events"]=[{"time":now+DAY,"amount":1,"circulating":100}]
    assert "large_release_blackout" in admission(plan,passport,evidence,as_of=now)["reasons"]
    evidence["supply"]["value"]["events"]=[]
    evidence["incident"]["value"]["normal_since"]=now-DAY
    assert not admission(plan,passport,evidence,as_of=now)["admitted"]


def test_meme_funding_is_directional_and_not_settled_history():
    now,plan,passport,evidence=gate_inputs("meme")
    evidence["funding_forecast"]["value"]["rate"]=.001
    assert not admission(plan,passport,evidence,as_of=now)["admitted"]
    plan["side"]="short"
    assert admission(plan,passport,evidence,as_of=now)["admitted"]
    evidence["funding_forecast"]["value"]["settled_history"]=True
    assert not admission(plan,passport,evidence,as_of=now)["admitted"]


@pytest.mark.parametrize("field,value",[("session_open",False),("quote_time",1),("reference_price",float("nan")),("perp_price",2100)])
def test_gold_reference_never_silently_falls_back_to_btc(field,value):
    now,plan,passport,evidence=gate_inputs("rwa")
    evidence["gold"]["value"][field]=value
    assert not admission(plan,passport,evidence,as_of=now)["admitted"]


def test_unknown_market_no_fallback_and_stale_data_no_signal():
    with pytest.raises(ValueError): candidate("MISSING_USDT","long",{},as_of=DAY,tick=.1)
    assert candidate("BTC_USDT","long",{},as_of=DAY,tick=.1)["status"]=="blocked_data"


@pytest.mark.parametrize("group",list(load_entries()[0]["groups"]))
@pytest.mark.parametrize("side",["long","short"])
def test_every_group_routes_to_its_registered_family(group,side):
    config,mapping=load_entries(); symbol=next(s for s,g in mapping.items() if g==group)
    desired="up" if side=="long" else "down"; sign=1 if side=="long" else -1
    family=config["groups"][group][side]
    regime="neutral" if family=="R" else desired
    def f(ret,reg):
        return {"regime":reg,"return20":ret,"age":3,"volatility_ok":True,"daily":[Bar(0,100,101,99,100,1)],
                "d":{"ema20":[100],"atr":[2]},"bars":trend_bars(),"h":{"ema20":[100],"ema50":[99],"adx":[30],"atr":[2]*61}}
    asset=f(sign*.2,regime); btc=f(sign*.1,desired)
    cache={(symbol,200*DAY):asset,("BTC_USDT",200*DAY):btc}
    if symbol=="BTC_USDT":cache[(symbol,200*DAY)]=asset
    def geometry(*args,**kwargs):
        return {"family":args[3],"signal_time":200*DAY,"breakout_time":200*DAY,"side":side}
    with patch("evaluation.sector_entries.form_plan",side_effect=geometry):
        out=candidate(symbol,side,{},as_of=200*DAY,tick=.01,_feature_cache=cache)
    assert out["status"]=="technical_candidate_not_admitted"
    assert out["family"]==("T" if family=="TR" else family)
    assert out["max_holding_seconds"]<=96*3600 and not out["live_eligible"]


def test_eth_neutral_routes_to_range_not_best_historical_model():
    config,_=load_entries()
    assert config["groups"]["core_eth"]["long"]=="TR"
    # Actual switch is determined before price confirmation, not by PnL.
    with patch("evaluation.sector_entries.features") as get, patch("evaluation.sector_entries.form_plan",return_value=None) as form:
        get.side_effect=[{"regime":"neutral","return20":0},{"regime":"neutral","return20":0}]
        # Supply the remaining technical arrays, without trend-only fields.
        get.side_effect=[{"regime":"neutral","return20":0,"bars":[],"h":{"atr":[],"ema20":[1],"ema50":[1],"adx":[1]}},
                         {"regime":"neutral","return20":0}]
        candidate("ETH_USDT","long",{"ETH_USDT":[],"BTC_USDT":[]},as_of=200*DAY,tick=.1)
        assert form.call_args.args[3]=="R"


@pytest.mark.parametrize("value",[None,True,float("nan"),"yesterday"])
def test_invalid_passport_date_cannot_bypass_gate(value):
    now,plan,passport,evidence=gate_inputs()
    passport["reviewed_at"]=value
    assert not admission(plan,passport,evidence,as_of=now)["admitted"]


def test_updated_passport_requires_new_candidate_with_subtype_filters():
    now,plan,passport,evidence=gate_inputs()
    passport["additional_benchmark"]="ETH_USDT"
    assert "passport_changed_since_candidate" in admission(plan,passport,evidence,as_of=now)["reasons"]
    with pytest.raises(ValueError):
        candidate("BTC_USDT","long",{},as_of=now,tick=.1,passport={"symbol":"ETH_USDT","group":"core_eth"})


@pytest.mark.parametrize("value",[None,True,float("nan"),"yesterday"])
def test_invalid_calendar_coverage_blocks_instead_of_assuming_known(value):
    now,plan,passport,evidence=gate_inputs()
    evidence["supply"]["value"]["coverage_start"]=value
    assert not admission(plan,passport,evidence,as_of=now)["admitted"]


def test_boolean_or_non_integer_times_are_not_evidence():
    now,plan,passport,evidence=gate_inputs("meme")
    evidence["funding_forecast"]["value"]["rate"]=False
    assert not admission(plan,passport,evidence,as_of=now)["admitted"]
    now,plan,passport,evidence=gate_inputs()
    evidence["liquidity"]["value"]["snapshot_times"]=[now-50.,now-25.,now-1.]
    assert not admission(plan,passport,evidence,as_of=now)["admitted"]
