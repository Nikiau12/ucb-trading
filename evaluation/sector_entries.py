"""Deterministic 1D/4H sector candidates. No production imports or side effects.

Technical candidates and admission are separate: an old chart can be inspected
without pretending a passport or order book observed today was available then.
All evidence gates are explicit and fail closed. No order is placed here.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
import hashlib
import json
import math
from pathlib import Path
from statistics import median

from evaluation.sector_data import digest, FOUR_HOURS, DAY
from evaluation.sector_liquidity_audit import validate_registry
from trading.analytics.structure import Bar


def ema(values, period):
    out = [None] * len(values)
    if len(values) >= period:
        out[period-1] = sum(values[:period]) / period
        for i in range(period, len(values)):
            out[i] = out[i-1] + 2/(period+1) * (values[i] - out[i-1])
    return out


def rma(values, period):
    out, seed = [None] * len(values), []
    for i, value in enumerate(values):
        if value is None:
            continue
        if i and out[i-1] is not None:
            out[i] = (out[i-1] * (period-1) + value) / period
        else:
            seed.append(value)
            if len(seed) == period:
                out[i] = sum(seed) / period
    return out


def indicators(bars):
    closes = [b.c for b in bars]
    tr, plus, minus = [None], [None], [None]
    for previous, current in zip(bars, bars[1:]):
        tr.append(max(current.h-current.l, abs(current.h-previous.c), abs(current.l-previous.c)))
        up, down = current.h-previous.h, previous.l-current.l
        plus.append(up if up > down and up > 0 else 0.)
        minus.append(down if down > up and down > 0 else 0.)
    atr, p, m = rma(tr,14), rma(plus,14), rma(minus,14)
    dx = [None if a is None else (100*abs(x-y)/(x+y) if x+y else 0.) for a,x,y in zip(atr,p,m)]
    return {"ema20": ema(closes,20), "ema50": ema(closes,50), "atr": atr, "adx": rma(dx,14)}


def percentile(values, fraction=.9):
    values = sorted(values)
    index = (len(values)-1) * fraction
    lo, hi = int(math.floor(index)), int(math.ceil(index))
    return values[lo] + (values[hi]-values[lo]) * (index-lo)


def features(bars, as_of):
    if type(as_of) is not int or as_of % FOUR_HOURS:
        raise ValueError("Decision must follow a closed UTC 4H candle")
    closed = [b for b in bars if b.ts + FOUR_HOURS <= as_of]
    if len(closed) < 200 or closed[-1].ts + FOUR_HOURS != as_of:
        raise ValueError("Insufficient or stale 4H data")
    for b in closed:
        if type(b.ts) is not int or b.ts % FOUR_HOURS or not all(math.isfinite(v) for v in (b.o,b.h,b.l,b.c,b.v)):
            raise ValueError("Invalid candle")
        if min(b.o,b.h,b.l,b.c) <= 0 or b.v < 0 or b.l > min(b.o,b.c) or b.h < max(b.o,b.c):
            raise ValueError("Invalid OHLCV")
    if any(b.ts-a.ts != FOUR_HOURS for a,b in zip(closed,closed[1:])):
        raise ValueError("Unordered, duplicate or gapped candles")
    days = {}
    for b in closed:
        days.setdefault(b.ts//DAY*DAY, []).append(b)
    daily = [Bar(t, bs[0].o, max(b.h for b in bs), min(b.l for b in bs), bs[-1].c, sum(b.v for b in bs))
             for t,bs in days.items() if len(bs)==6 and bs[0].ts==t and t+DAY<=as_of]
    if len(daily) < 120:
        raise ValueError("Insufficient complete daily data")
    h, d = indicators(closed), indicators(daily)
    directed = []
    for i,b in enumerate(daily):
        a,e20,e50,adx = (d[k][i] for k in ("atr","ema20","ema50","adx"))
        if i < 52 or any(v is None for v in (a,e20,e50,adx)) or a <= 0:
            directed.append("unknown")
        elif b.c > e20 > e50 and e20 > d["ema20"][i-3] and adx >= 20:
            directed.append("up")
        elif b.c < e20 < e50 and e20 < d["ema20"][i-3] and adx >= 20:
            directed.append("down")
        else:
            directed.append("other")
    confirmed = []
    for i,direction in enumerate(directed):
        if i and direction in ("up","down") and direction == directed[i-1]:
            confirmed.append(direction)
        elif d["adx"][i] is not None and d["atr"][i] and d["ema50"][i] is not None and d["adx"][i] < 20 and abs(d["ema20"][i]-d["ema50"][i]) <= .5*d["atr"][i]:
            confirmed.append("neutral")
        else:
            confirmed.append("transition")
    age = 0
    for direction in reversed(directed):
        if direction != directed[-1] or direction not in ("up","down"):
            break
        age += 1
    vol = [a/b.c for a,b in zip(d["atr"],daily) if a is not None]
    return {"bars":closed, "daily":daily, "h":h, "d":d, "regime":confirmed[-1],
            "regime_by_day":dict(zip([b.ts+DAY for b in daily],confirmed)), "age":age,
            "return20":daily[-1].c/daily[-21].c-1,
            "volatility_ok":len(vol)>=91 and vol[-1]<=percentile(vol[-91:-1]),
            "decision_time":as_of}


def relative_volume(bars, index):
    if index < 20:
        return 0.
    baseline = median(b.v for b in bars[index-20:index])
    return bars[index].v/baseline if baseline > 0 else 0.


def spaced_touches(bars, level, tolerance, upper):
    chosen = []
    for i,b in enumerate(bars):
        if abs((b.h if upper else b.l)-level) <= tolerance and (not chosen or i-chosen[-1]>=4):
            chosen.append(i)
    return chosen


def round_price(value, tick, upward):
    q, step = Decimal(str(value)), Decimal(str(tick))
    return float((q/step).to_integral_value(rounding=ROUND_CEILING if upward else ROUND_FLOOR)*step)


def form_plan(bars, atrs, side, family, tick, *, ema20=None, ema50=None, adx=None, rv_min=0):
    """Price geometry on CLOSED bars only. Returns None when no trigger exists."""
    s, t, a, i = (1 if side=="long" else -1), bars[-1], atrs[-1], len(bars)-1
    if side not in ("long","short") or family not in ("T","B","R") or not a or a <= 0:
        return None
    if not math.isfinite(tick) or tick <= 0:
        raise ValueError("Positive contract tick required")
    lower = upper = breakout_time = None
    if family == "T":
        if (ema20 is None or ema50 is None or adx is None or adx < 25
                or s*(ema20-ema50)<=0 or s*(t.c-ema20)<=0 or s*(t.c-t.o)<=0
                or (t.l>ema20 if s==1 else t.h<ema20) or t.h-t.l>2*a
                or relative_volume(bars,i)<rv_min):
            return None
        entry = t.h+tick if s==1 else t.l-tick
        stop = min(b.l for b in bars[-3:])-.25*a if s==1 else max(b.h for b in bars[-3:])+.25*a
    elif family == "B":
        # Earliest still-valid breakout owns the retest; no same-bar breakout entry.
        candidate = None
        for k in range(max(20,i-3),i):
            window, b, ak = bars[k-20:k], bars[k], atrs[k]
            if not ak or ak<=0:
                continue
            level = max(b.h for b in window) if s==1 else min(b.l for b in window)
            distance = s*(b.c-level)
            if not (.1*ak < distance <= ak and b.h-b.l<=2.5*ak and relative_volume(bars,k)>=max(1.5,rv_min)):
                continue
            for j in range(k+1,i+1):
                r = bars[j]
                if s*(r.c-level)<-.25*ak:
                    break
                extreme = r.l if s==1 else r.h
                retest = abs(extreme-level)<=.25*ak and s*(r.c-level)>0 and s*(r.c-r.o)>0
                if retest:
                    if j==i:
                        candidate = (k,level)
                    break  # First retest already consumed; never reissue it.
            if candidate:
                break
        if candidate is None:
            return None
        k, level = candidate
        breakout_time = bars[k].ts+FOUR_HOURS
        entry = t.h+tick if s==1 else t.l-tick
        stop = t.l-.25*a if s==1 else t.h+.25*a
    else:
        prior = bars[-61:-1]
        if len(prior)!=60:
            return None
        lower, upper = min(b.l for b in prior), max(b.h for b in prior)
        if not 4*a<=upper-lower<=10*a:
            return None
        if any(len(spaced_touches(prior,level,.25*a,high))<3 for level,high in ((lower,False),(upper,True))):
            return None
        if any(b.c<lower-.25*a or b.c>upper+.25*a for b in prior[-12:]):
            return None
        boundary, extreme = (lower,t.l) if s==1 else (upper,t.h)
        if abs(extreme-boundary)>.25*a or s*(t.c-boundary)<=.25*a or s*(t.c-t.o)<=0:
            return None
        entry = t.h+tick if s==1 else t.l-tick
        stop = lower-.25*a if s==1 else upper+.25*a
    entry, stop = round_price(entry,tick,s==1), round_price(stop,tick,s==-1)
    risk = s*(entry-stop)
    if risk<=0 or min(entry,stop)<=0 or (family!="R" and not .75*a<=risk<=2.5*a):
        return None
    tp1 = (lower+upper)/2 if family=="R" else entry+s*1.5*risk
    tp2 = (upper-.25*a if s==1 else lower+.25*a) if family=="R" else entry+s*3*risk
    # Targets round toward entry. No optimistic extra R from rounding.
    tp1, tp2 = round_price(tp1,tick,s==-1), round_price(tp2,tick,s==-1)
    if min(tp1,tp2)<=0 or not (s*(tp1-entry)>0 and s*(tp2-tp1)>0):
        return None
    if family=="R" and (s*(tp1-entry)<risk or s*(tp2-entry)<2*risk):
        return None
    if family=="T" and len(bars)>=61:
        prior=bars[-61:-1]
        level=max(b.h for b in prior) if s==1 else min(b.l for b in prior)
        if len(spaced_touches(prior,level,.25*a,s==1))>=3 and 0<s*(level-entry)<s*(tp1-entry):
            return None
    return {"family":family,"side":side,"entry":entry,"stop":stop,"tp1":tp1,"tp2":tp2,"risk_price":risk,
            "atr4h":a,"breakout_time":breakout_time,"range_lower":lower,"range_upper":upper,
            "entry_type":"stop","trigger_price_type":"contract_last","signal_time":t.ts+FOUR_HOURS,
            "entry_expiry_seconds":2*FOUR_HOURS}


def load_entries():
    base=Path(__file__).parent
    config=json.loads((base/"sector_entries.v2.json").read_text())
    assets=json.loads((base/"asset_groups.v1.json").read_text())
    mapping=validate_registry(assets)
    if config["mode"]!="offline_research_only" or config["live_eligible"] is not False or config["timeframes"]!=["4h","1d"]:
        raise ValueError("Non-research configuration forbidden")
    if set(config["groups"])!=set(mapping.values()):
        raise ValueError("Every group requires exactly one binding")
    for p in config["groups"].values():
        if any(p[s] not in ("T","B","R","TR") for s in ("long","short")) or p["btc"] not in ("none","same","not_opposite"):
            raise ValueError("Invalid strategy binding")
        if p["max_hours"] not in (72,96):
            raise ValueError("Holding bound changed")
    return config,mapping


def load_passports():
    base=Path(__file__).parent
    raw=json.loads((base/"sector_passports.v2.json").read_text())
    _,mapping=load_entries()
    if raw["mode"]!="offline_research_only" or raw["live_eligible"] is not False or type(raw["reviewed_at"]) is not int:
        raise ValueError("Invalid economic review scope")
    result={}
    for row in raw["assets"]:
        symbol=row["symbol"]
        if symbol in result or mapping.get(symbol)!=row["group"] or row["mechanism_status"] not in ("documented","incomplete"):
            raise ValueError("Passport identity or status mismatch")
        if not row["sources"] or any(not s.startswith("https://") for s in row["sources"]):
            raise ValueError("Passport requires primary source URLs")
        result[symbol]=dict(row,reviewed_at=raw["reviewed_at"],version=raw["version"],
                           historical_backfill_allowed=False,live_eligible=False)
    return result


def regime_allowed(f, benchmark, p, side, family):
    desired, opposite = ("up","down") if side=="long" else ("down","up")
    if f["regime"] != ("neutral" if family=="R" else desired):
        return False
    if p["btc"]=="none":
        return True
    if benchmark is None or benchmark["regime"] not in ("up","down","neutral","transition"):
        return False
    return benchmark["regime"]==desired if p["btc"]=="same" else benchmark["regime"]!=opposite


def candidate(symbol, side, markets, *, as_of, tick, passport=None, _feature_cache=None):
    config,mapping=load_entries()
    if symbol not in mapping or side not in ("long","short"):
        raise ValueError("No fallback for unknown instrument or direction")
    group=mapping[symbol]; p=config["groups"][group]
    if passport is not None and (passport.get("symbol")!=symbol or passport.get("group")!=group):
        raise ValueError("Passport belongs to a different instrument/group")
    def get(s):
        key=(s,as_of)
        if _feature_cache is not None and key in _feature_cache:
            return _feature_cache[key]
        value=features(markets[s],as_of)
        if _feature_cache is not None:
            _feature_cache[key]=value
        return value
    try:
        f=get(symbol); btc=get("BTC_USDT") if p["btc"]!="none" else None
    except (ValueError,KeyError) as exc:
        return {"status":"blocked_data","reason":str(exc),"live_eligible":False}
    family=p[side]
    if family=="TR":
        family="R" if f["regime"]=="neutral" else "T"
    if not regime_allowed(f,btc,p,side,family):
        return {"status":"no_setup","reason":"daily_regime","live_eligible":False}
    sign=1 if side=="long" else -1
    if p["rs"] and family!="R" and sign*(f["return20"]-btc["return20"])<=0:
        return {"status":"no_setup","reason":"relative_strength_btc","live_eligible":False}
    extra=(passport or {}).get("additional_benchmark")
    if extra and group in ("scaling","defi"):
        try:
            other=get(extra)
        except (ValueError,KeyError):
            return {"status":"blocked_data","reason":"additional_benchmark_missing","live_eligible":False}
        if sign*(f["return20"]-other["return20"])<=0:
            return {"status":"no_setup","reason":"relative_strength_subtype","live_eligible":False}
    if "trend_age" in p and not p["trend_age"][0]<=f["age"]<=p["trend_age"][1]:
        return {"status":"no_setup","reason":"daily_trend_age","live_eligible":False}
    if family=="T" and sign*(f["daily"][-1].c-f["d"]["ema20"][-1])>2*f["d"]["atr"][-1]:
        return {"status":"no_setup","reason":"late_trend_extension","live_eligible":False}
    if side=="long" and p["volatility_long"] and not f["volatility_ok"]:
        return {"status":"no_setup","reason":"daily_volatility","live_eligible":False}
    plan=form_plan(f["bars"],f["h"]["atr"],side,family,tick,ema20=f["h"]["ema20"][-1],
                   ema50=f["h"]["ema50"][-1],adx=f["h"]["adx"][-1],rv_min=p["rv_"+side])
    if plan is None:
        return {"status":"no_setup","reason":"price_confirmation","live_eligible":False}
    if family=="B":
        # A breakout waiting across a daily regime change cannot be resurrected.
        for boundary in range(plan["breakout_time"],as_of+1,FOUR_HOURS):
            try:
                before=get(symbol) if boundary==as_of else features(markets[symbol],boundary)
                ref=btc if boundary==as_of else (features(markets["BTC_USDT"],boundary) if p["btc"]!="none" else None)
                if not regime_allowed(before,ref,p,side,family):
                    return {"status":"no_setup","reason":"regime_changed_during_retest","live_eligible":False}
            except (KeyError,ValueError):
                return {"status":"blocked_data","reason":"retest_context_missing","live_eligible":False}
    plan.update(symbol=symbol,group=group,profile_version=config["version"],profile_sha256=digest(config),
                implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                passport_sha256=digest(passport) if passport else None,
                max_holding_seconds=min(p["max_hours"],72 if family=="R" else 96)*3600,
                daily_regime=f["regime"],daily_trend_age=f["age"],status="technical_candidate_not_admitted",
                live_eligible=False,historical_validation_eligible=False)
    plan["decision_key"]=digest({k:plan[k] for k in ("symbol","side","signal_time","profile_sha256","passport_sha256","implementation_sha256","family")})
    return plan


def admission(plan, passport, evidence, *, as_of):
    """Risk evidence is point-in-time, explicitly sourced and expiring.

    Evidence records: {symbol, known_at, expires_at, source, value}. Required
    kinds are contract, liquidity, incident, supply, cost, and extra gold/funding.
    Economic review is not a trading approval or proof of current solvency.
    """
    issues=[]
    if plan.get("status")!="technical_candidate_not_admitted" or plan.get("signal_time")!=as_of:
        return {"admitted":False,"reasons":["no_current_candidate"],"live_eligible":False}
    if (not passport or passport.get("symbol")!=plan["symbol"] or passport.get("group")!=plan["group"]
            or passport.get("mechanism_status")!="documented" or type(passport.get("reviewed_at")) is not int
            or not 0<=passport["reviewed_at"]<=as_of):
        issues.append("passport_not_available_or_incomplete")
    try:
        if not passport or plan.get("passport_sha256")!=digest(passport):
            issues.append("passport_changed_since_candidate")
    except (ValueError,TypeError):
        issues.append("invalid_passport")
    if not passport or passport.get("identity_status") not in ("documented_native_asset","verified_contract_mapping"):
        issues.append("token_contract_identity_unverified")
    def record(kind):
        r=evidence.get(kind)
        if (not isinstance(r,dict) or r.get("symbol")!=plan["symbol"] or not r.get("source")
                or type(r.get("known_at")) is not int or type(r.get("expires_at")) is not int
                or not r["known_at"]<=as_of<=r["expires_at"]):
            issues.append(kind+"_missing_future_or_stale")
            return None
        return r.get("value")
    contract=record("contract")
    if not isinstance(contract,dict) or contract.get("active") is not True or contract.get("units_verified") is not True:
        issues.append("contract_not_verified")
    liq=record("liquidity")
    meme=plan["group"]=="meme"
    if not isinstance(liq,dict):
        issues.append("liquidity_not_verified")
    else:
        try:
            stamps=liq["snapshot_times"]
            if (not isinstance(stamps,list) or len(stamps)!=3 or any(type(t) is not int for t in stamps)
                    or sorted(set(stamps))!=stamps or not as_of-60<=stamps[0]<=stamps[-1]<=as_of or as_of-stamps[-1]>10):
                raise ValueError("Three recent books required")
            limits={"turnover_min":5e6 if meme else 1e6,"depth_min":25000 if meme else 10000,"impact_max":5 if meme else 10}
            nums=[liq[k] for k in ("turnover","bid_depth","ask_depth","spread_bps","buy_impact_bps","sell_impact_bps","assessed_notional")]
            if any(isinstance(v,bool) or not isinstance(v,(float,int)) or not math.isfinite(v) or v<0 for v in nums):
                raise ValueError("Invalid liquidity values")
            if (liq["turnover"]<limits["turnover_min"] or min(liq["bid_depth"],liq["ask_depth"])<limits["depth_min"]
                    or liq["spread_bps"]>10 or max(liq["buy_impact_bps"],liq["sell_impact_bps"])>limits["impact_max"]
                    or liq["assessed_notional"]<=0):
                issues.append("liquidity_threshold")
        except (KeyError,ValueError,TypeError):
            issues.append("invalid_liquidity_observation")
    incident=record("incident")
    if (not isinstance(incident,dict) or incident.get("clear") is not True
            or type(incident.get("normal_since")) is not int or not 0<=incident["normal_since"]<=as_of-2*DAY):
        issues.append("incident_or_recovery_window")
    supply=record("supply")
    if (not isinstance(supply,dict) or type(supply.get("coverage_start")) is not int or type(supply.get("coverage_end")) is not int
            or not 0<=supply["coverage_start"]<=as_of-DAY or supply["coverage_end"]<as_of+DAY):
        issues.append("supply_calendar_incomplete")
    else:
        events=supply.get("events")
        if not isinstance(events,list):
            issues.append("supply_events_missing")
        else:
            for event in events:
                try:
                    amount,circulating,ts=event["amount"],event["circulating"],event["time"]
                    if (type(ts) is not int or ts<0 or not all(isinstance(v,(float,int)) and not isinstance(v,bool) and math.isfinite(v) for v in (amount,circulating))
                            or amount<0 or circulating<=0):
                        raise ValueError("Unknown release denominator")
                    if abs(ts-as_of)<=DAY and amount/circulating>=.01:
                        issues.append("large_release_blackout")
                except (KeyError,ValueError,TypeError):
                    issues.append("unknown_supply_event")
    cost=record("cost")
    if not isinstance(cost,dict) or cost.get("estimated_total_r") is None or isinstance(cost["estimated_total_r"],bool) or not isinstance(cost["estimated_total_r"],(float,int)) or not math.isfinite(cost["estimated_total_r"]) or not 0<=cost["estimated_total_r"]<=(.15 if meme else .2):
        issues.append("unknown_or_excessive_pretrade_cost")
    if meme:
        f=record("funding_forecast")
        if not isinstance(f,dict) or f.get("settled_history") is not False:
            issues.append("funding_forecast_missing")
        else:
            try:
                if isinstance(f["rate"],bool) or isinstance(f["interval_hours"],bool):
                    raise ValueError("Invalid funding estimate")
                rate,hours=float(f["rate"]),float(f["interval_hours"])
                if not math.isfinite(rate) or not math.isfinite(hours) or hours<=0:
                    raise ValueError("Invalid funding estimate")
                if (1 if plan["side"]=="long" else -1)*rate*8/hours>.0005:
                    issues.append("crowded_funding_side")
            except (KeyError,ValueError,TypeError):
                issues.append("funding_forecast_missing")
    if plan["group"]=="rwa":
        gold=record("gold")
        try:
            direction="up" if plan["side"]=="long" else "down"
            if (not isinstance(gold,dict) or gold["session_open"] is not True or gold["license_verified"] is not True
                    or any(isinstance(gold[k],bool) or not isinstance(gold[k],(float,int)) or not math.isfinite(gold[k]) for k in ("quote_time","spot_price","reference_price","perp_price"))
                    or not as_of-60<=gold["quote_time"]<=as_of or gold["regime"]!=direction
                    or gold["spot_price"]<=0 or gold["reference_price"]<=0 or gold["perp_price"]<=0
                    or abs(gold["spot_price"]/gold["reference_price"]-1)>.005
                    or abs(gold["perp_price"]/gold["spot_price"]-1)>.005):
                issues.append("gold_reference_unavailable_or_divergent")
        except (KeyError,TypeError,ZeroDivisionError):
            issues.append("gold_reference_unavailable_or_divergent")
    return {"admitted":not issues,"reasons":sorted(set(issues)),"decision_key":plan["decision_key"],
            "live_eligible":False,"historical_validation_eligible":False}
