"""Public experimental group rules shared by the scanner and /plan.

The immutable research definitions are reused, not promoted as validated models.
Only new signals use this adapter. It never reads/writes existing trades, sends
messages, loads credentials or places orders. Missing market data fails closed.
"""
from __future__ import annotations

from functools import lru_cache
import logging
import math
import threading
import time

from evaluation.sector_entries import candidate, load_entries, load_passports
from evaluation.sector_data import FOUR_HOURS, digest
from trading.trade_plan import (normalize_for_contract, parse_bars, plan_payload_errors,
                                last_price_from_snapshot)

VERSION = "group-rules-v1-2026-11-07"
logger = logging.getLogger(__name__)
_history_lock = threading.Lock()
_histories = {}


@lru_cache(maxsize=1)
def catalog():
    definitions, mapping = load_entries()
    return definitions, mapping, load_passports()


def _public():
    # The entrypoint historically imports trading/ modules by short name.
    # Reuse that exact client and its shared request limiter when present.
    import sys
    client = sys.modules.get("bingx_snapshot")
    if client is None:
        from trading import bingx_snapshot as client
    return client


def history(symbol, as_of, snapshot=None):
    if snapshot is not None:
        bars = parse_bars(snapshot, "kline_4h")
        if len(bars) >= 726:
            return bars
    key = (symbol, as_of)
    # Serialize cache misses, including simultaneous /plan and background scans.
    with _history_lock:
        if key not in _histories:
            rows = _public().futures_kline(symbol, "4h", 1440)
            bars = parse_bars({"kline_4h": rows}, "kline_4h")
            if len(bars) < 726 or max(b.ts for b in bars) < as_of-FOUR_HOURS:
                raise ValueError("insufficient_group_history")
            for old in list(_histories):
                if old[1] != as_of:
                    _histories.pop(old)
            if len(_histories) >= 160:
                _histories.pop(next(iter(_histories)))
            _histories[key] = bars
        return _histories[key]


def _finite(value, *, positive=True):
    if isinstance(value, bool):
        raise ValueError("invalid_market_number")
    result = float(value)
    if not math.isfinite(result) or (result <= 0 if positive else result < 0):
        raise ValueError("invalid_market_number")
    return result


def check_execution_market(snapshot, plan, sizing, now):
    """Current liquidity/fee checks; never claim historical or actual fill costs."""
    ticker = snapshot.get("ticker", {}).get("data", {})
    if isinstance(ticker, list):
        ticker = ticker[0] if len(ticker)==1 else {}
    turnover = _finite(ticker.get("quoteVolume", ticker.get("amount24", 0)))
    meme = plan["group"] == "meme"
    if turnover < (5_000_000 if meme else 1_000_000):
        raise ValueError("group_liquidity_turnover")
    body = _public().http_get("/openApi/swap/v2/quote/depth", {
        "symbol": plan["symbol"].replace("_", "-"), "limit": 1000,
    })
    book = body.get("data", {})
    now = int(time.time()) if now is None else now
    if body.get("code") != 0 or not isinstance(book, dict):
        raise ValueError("group_orderbook_unavailable")
    stamp = _finite(book.get("T"))/1000
    if not -5 <= now-stamp <= 120:
        raise ValueError("group_orderbook_stale")
    sides = {}
    for name in ("bids", "asks"):
        raw = book.get(name+"Coin", book.get(name))
        if not isinstance(raw, list) or not raw:
            raise ValueError("group_orderbook_empty")
        levels = [(_finite(r[0]), _finite(r[1])) for r in raw]
        prices = [p for p,q in levels]
        if prices != sorted(set(prices), reverse=name=="bids"):
            raise ValueError("group_orderbook_unordered")
        sides[name] = levels
    bid, ask = sides["bids"][0][0], sides["asks"][0][0]
    mid = (bid+ask)/2
    spread = (ask-bid)/mid*10000
    if not 0 < spread <= 10:
        raise ValueError("group_spread")
    depth = {name: sum(p*q for p,q in rows if abs(p/mid-1)<=.005) for name,rows in sides.items()}
    if min(depth.values()) < (25_000 if meme else 10_000):
        raise ValueError("group_depth")
    notional = max(1000., sizing["position_usdt"])
    quantity = notional/mid
    impacts = []
    for name in ("bids","asks"):
        remaining, value = quantity, 0.
        for price, size in sides[name]:
            taken = min(remaining, size)
            value += taken*price
            remaining -= taken
            if remaining <= quantity*1e-12:
                break
        if remaining > quantity*1e-12:
            raise ValueError("group_depth_notional")
        impacts.append(abs(value/quantity/mid-1)*10000)
    if max(impacts) > (5 if meme else 10):
        raise ValueError("group_price_impact")
    raw_contract = snapshot["contract"].get("raw", {})
    fee = _finite(raw_contract.get("takerFeeRate"), positive=False)
    if fee > .01:
        raise ValueError("invalid_contract_fee")
    # Conservative public taker scenario, not the user's account fee tier.
    cost_r = 2*(fee+max(impacts)/10000)*plan["entry"]/plan["risk_price"]
    if cost_r > (.15 if meme else .2):
        raise ValueError("group_estimated_fee_impact_cost")
    return {"observed_at":now, "spread_bps":spread, "impact_bps":max(impacts),
            "checked_notional":notional, "public_taker_fee":fee, "fee_impact_r":cost_r,
            "funding_and_actual_fills_verified":False}


def check_unused_trigger(plan, now, current):
    """Do not publish a closed-bar trigger already consumed before delivery."""
    sign = 1 if plan["side"] == "long" else -1
    if sign*(current-plan["entry"]) >= 0 or sign*(current-plan["stop"]) <= 0:
        raise ValueError("group_trigger_already_used_or_invalidated")
    elapsed = now-plan["signal_time"]
    if not 0 <= elapsed < plan["entry_expiry_seconds"]:
        raise ValueError("group_setup_expired")
    limit = min(1440, int(elapsed//60)+2)
    raw = _public().futures_kline(plan["symbol"],"1m",limit)
    bars = parse_bars({"kline_1h":raw},"kline_1h")
    relevant = [b for b in bars if b.ts >= plan["signal_time"] and b.ts <= now]
    expected = list(range(plan["signal_time"], now//60*60, 60))
    if [b.ts for b in relevant if b.ts+60<=now] != expected:
        raise ValueError("group_trigger_path_missing")
    for bar in relevant:
        if (bar.h >= plan["entry"] or bar.l <= plan["stop"]) if sign==1 else (bar.l <= plan["entry"] or bar.h >= plan["stop"]):
            raise ValueError("group_trigger_already_used_or_invalidated")


def make_plan(snapshot, deposit, risk_pct, lev, margin, *, now=None, markets=None):
    """A single deterministic group route for both entrypoints, with no legacy fallback."""
    realtime = now is None
    now = int(time.time()) if now is None else int(now)
    symbol = str(snapshot.get("symbol", "")).upper().replace("-", "_")
    definitions, mapping, passports = catalog()
    group = mapping.get(symbol)
    strategy = {"version":VERSION,"group":group,"experimental":True,"entry_type":"stop",
        "timeframes":["4h","1d"],"definitions_sha256":digest(definitions),
        "confidence_is_probability":False,"profitability_validated":False,
        "economic_admission":"not_independently_verified",
        "funding_supply_incident_gold_reference_verified":False}
    def skip(reason):
        logger.info("group_plan symbol=%s group=%s result=skip reason=%s",symbol,group,reason)
        return {"symbol":symbol,"side":"skip","confidence":0.,"reasons":[reason],
                "used_cache":bool(snapshot.get("stale")),"strategy":dict(strategy)}
    if not group:
        return skip("unclassified_symbol_no_group_fallback")
    if snapshot.get("stale") or snapshot.get("fallback",{}).get("used_cache"):
        return skip("stale_market_data")
    if snapshot.get("exchange", "bingx") != "bingx":
        return skip("wrong_exchange")
    try:
        for setting in (deposit, risk_pct, lev):
            _finite(setting)
        observed = int(snapshot["ts"])/1000
        if not -5 <= now-observed <= 600:
            return skip("stale_market_data")
        detail = snapshot["contract"]
        if detail.get("symbol") != symbol or detail.get("active") is not True:
            return skip("active_matching_contract_required")
        tick = _finite(detail["priceUnit"])
        current = _finite(last_price_from_snapshot(snapshot))
        as_of = now//FOUR_HOURS*FOUR_HOURS
        market = dict(markets or {})
        market.setdefault(symbol, history(symbol,as_of,snapshot) if symbol not in market else market[symbol])
        binding = definitions["groups"][group]
        passport = passports.get(symbol)
        required = ["BTC_USDT"] if binding["btc"] != "none" else []
        if passport and passport.get("additional_benchmark"):
            required.append(passport["additional_benchmark"])
        for benchmark in required:
            if benchmark not in market:
                market[benchmark] = history(benchmark,as_of)
        choices, reasons = [], []
        feature_cache = {}
        for side in ("long","short"):
            result = candidate(symbol,side,market,as_of=as_of,tick=tick,passport=passport,_feature_cache=feature_cache)
            if result["status"] == "technical_candidate_not_admitted":
                choices.append(result)
            else:
                reasons.append(result.get("reason","no_group_setup"))
        if len(choices) != 1:
            return skip("conflicting_group_directions" if choices else "group_no_setup:"+"/".join(reasons))
        raw = choices[0]
        normalized = normalize_for_contract(snapshot, raw["side"], raw["entry"],raw["stop"],raw["tp1"],raw["tp2"],deposit,risk_pct,lev)
        if normalized["errors"]:
            return skip("group_sizing:"+"/".join(normalized["errors"]))
        # Definition prices already obey tick rules; never silently improve targets.
        if any(normalized[k] != raw[k] for k in ("entry","stop","tp1","tp2")):
            return skip("group_contract_rounding_changed_levels")
        # Market requests can take seconds. Check the observation clock after
        # fetching, while keeping an injected clock deterministic in tests.
        execution = check_execution_market(snapshot,raw,normalized,None if realtime else now)
        delivered_at = int(time.time()) if realtime else now
        check_unused_trigger(raw,delivered_at,current)
        direction = raw["daily_regime"]
        strategy.update(family=raw["family"],signal_time=as_of,
            entry_expires_at=as_of+raw["entry_expiry_seconds"],max_holding_seconds=raw["max_holding_seconds"],
            decision_key=raw["decision_key"],execution_checks=execution, verified_at=delivered_at)
        primary = dict(normalized, side=raw["side"], confidence=1.,
            entry_type="stop", entry_expiry_bars=2, max_holding_bars=raw["max_holding_seconds"]//FOUR_HOURS,
            entry_expiry_seconds=as_of+raw["entry_expiry_seconds"]-delivered_at,
            max_holding_seconds=raw["max_holding_seconds"],
            tps=[{"price":raw["tp1"],"pct":.5},{"price":raw["tp2"],"pct":.5}],
            reasons=["trend_1d="+direction,"regime="+("range" if raw["family"]=="R" else "trend")])
        plan = {"symbol":symbol,"price":current,"primary":primary,"alternate":None,
            "trend":{"1d":direction,"regime":"range" if raw["family"]=="R" else "trend"},
            "used_cache":False,"strategy":strategy,"lev":lev,"margin":margin}
        errors = plan_payload_errors(plan)
        if errors:
            return skip("invalid_group_plan:"+"/".join(errors))
        logger.info("group_plan symbol=%s group=%s family=%s side=%s version=%s result=candidate",symbol,group,raw["family"],raw["side"],VERSION)
        return plan
    except (ValueError, TypeError, KeyError, IndexError, ArithmeticError) as exc:
        return skip("group_data_rejected:"+str(exc)[:160])
    except Exception as exc:
        logger.warning("group market data unavailable symbol=%s error=%s",symbol,type(exc).__name__)
        return skip("group_market_unavailable")


def prepare_for_publication(plan):
    """Recheck after a whole-universe scan; never send an already used trigger."""
    meta = plan.get("strategy") or {}
    if not meta:
        return plan
    try:
        primary = plan["primary"]
        raw = dict(primary, symbol=plan["symbol"], group=meta["group"],
                   signal_time=meta["signal_time"], entry_expiry_seconds=8*3600,
                   risk_price=abs(primary["entry"]-primary["stop"]))
        ticker = _public().futures_ticker(plan["symbol"])
        snapshot = {"ticker":ticker, "contract":{"raw":{
            "takerFeeRate":meta["execution_checks"]["public_taker_fee"]}}}
        price = _finite(last_price_from_snapshot(snapshot))
        execution = check_execution_market(snapshot, raw, primary, None)
        now = int(time.time())
        check_unused_trigger(raw, now, price)
        return {**plan, "price":price, "strategy":{**meta,
                "verified_at":now, "execution_checks":execution}}
    except Exception as exc:
        logger.info("group publication rejected symbol=%s reason=%s",plan.get("symbol"),type(exc).__name__)
        return None
