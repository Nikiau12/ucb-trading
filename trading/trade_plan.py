#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple

from miniapp.sizing import _positive_decimal, position_size_for_contract

try:
    from .analytics.indicators import ema, rsi, atr, adx, OHLC, volatility_regime
    from .analytics.structure import Bar, swings, last_structure_bias, bos_choch
    from .analytics.levels import cluster_levels, nearest_levels, midrange_ratio
except ImportError:
    # The CLI and the production bot also load this module directly from trading/.
    from analytics.indicators import ema, rsi, atr, adx, OHLC, volatility_regime
    from analytics.structure import Bar, swings, last_structure_bias, bos_choch
    from analytics.levels import cluster_levels, nearest_levels, midrange_ratio

# ----------------------------
# Tunables
# ----------------------------

MAX_RR_TP1 = 3.0  # do not choose swing TP1 if it is farther than this R
MIN_RR_TP1 = 1.0  # do not publish setups whose first target pays less than the risk
MIN_RR_TP2 = 1.8  # TP2 must materially improve the payoff over TP1

# ----------------------------
# Utils
# ----------------------------

def _to_float(x: Any) -> float:
    try:
        return float(x)
    except Exception:
        return float("nan")

def _to_int(x: Any) -> int:
    try:
        return int(float(x))
    except Exception:
        return 0

def _pick_first(d: Dict[str, Any], keys: List[str]) -> Any:
    for k in keys:
        if isinstance(d, dict) and k in d:
            return d[k]
    return None

def last_price_from_snapshot(snapshot: Dict[str, Any]) -> Optional[float]:
    t = snapshot.get("ticker")
    if not isinstance(t, dict):
        return None
    v = None
    if isinstance(t.get("data"), dict):
        v = _pick_first(t["data"], ["lastPrice", "last", "price", "markPrice"])
    if v is None:
        v = _pick_first(t, ["lastPrice", "last", "price", "markPrice"])
    if v is None:
        return None
    p = _to_float(v)
    return p if math.isfinite(p) else None

# ----------------------------
# Kline extraction (robust)
# ----------------------------

def _looks_like_row_list(x: Any) -> bool:
    return isinstance(x, (list, tuple)) and len(x) >= 6

def _looks_like_row_dict(x: Any) -> bool:
    if not isinstance(x, dict):
        return False
    keys = set(x.keys())
    need = {"open", "high", "low", "close"}
    alt = {"o", "h", "l", "c"}
    return (need.issubset(keys) or alt.issubset(keys))

def _extract_from_columnar(d: Dict[str, Any]) -> Optional[List[List[Any]]]:
    t = d.get("time", d.get("t"))
    o = d.get("open", d.get("o"))
    h = d.get("high", d.get("h"))
    l = d.get("low", d.get("l"))
    c = d.get("close", d.get("c"))
    v = d.get("vol", d.get("volume", d.get("v")))

    if not (isinstance(t, list) and isinstance(o, list) and isinstance(h, list) and isinstance(l, list) and isinstance(c, list)):
        return None
    n = min(len(t), len(o), len(h), len(l), len(c), len(v) if isinstance(v, list) else 10**9)
    if n <= 0:
        return None
    return [[t[i], o[i], h[i], l[i], c[i], v[i] if isinstance(v, list) else 0] for i in range(n)]

def find_kline_rows_any(x: Any) -> Optional[List[Any]]:
    if x is None:
        return None
    if isinstance(x, list):
        if x and (_looks_like_row_list(x[0]) or _looks_like_row_dict(x[0])):
            return x
        for item in x[:8]:
            r = find_kline_rows_any(item)
            if r is not None:
                return r
        return None
    if isinstance(x, dict):
        col = _extract_from_columnar(x)
        if col is not None:
            return col
        for key in ["data", "items", "result", "klines", "candles", "rows", "list"]:
            if key in x:
                r = find_kline_rows_any(x[key])
                if r is not None:
                    return r
        for v in list(x.values())[:80]:
            r = find_kline_rows_any(v)
            if r is not None:
                return r
    return None

def parse_bars(snapshot: Dict[str, Any], kline_key: str) -> List[Bar]:
    kdata = snapshot.get(kline_key)
    if kdata is None:
        return []
    if isinstance(kdata, dict) and isinstance(kdata.get("data"), dict):
        rows = find_kline_rows_any(kdata["data"])
    else:
        rows = find_kline_rows_any(kdata)
    if not rows:
        return []
    out: List[Bar] = []
    for r in rows:
        if _looks_like_row_list(r):
            ts = _to_int(r[0])
            o, h, l, c, v = map(_to_float, r[1:6])
            if ts and all(math.isfinite(x) for x in (o, h, l, c)):
                out.append(Bar(ts=ts, o=o, h=h, l=l, c=c, v=v))
        elif _looks_like_row_dict(r):
            ts = _to_int(_pick_first(r, ["t", "time", "ts", "timestamp", "openTime"]))
            o = _to_float(_pick_first(r, ["o", "open"]))
            h = _to_float(_pick_first(r, ["h", "high"]))
            l = _to_float(_pick_first(r, ["l", "low"]))
            c = _to_float(_pick_first(r, ["c", "close"]))
            v = _to_float(_pick_first(r, ["v", "vol", "volume"]))
            if ts and all(math.isfinite(x) for x in (o, h, l, c)):
                out.append(Bar(ts=ts, o=o, h=h, l=l, c=c, v=v))
    out.sort(key=lambda b: b.ts)
    return out

# ----------------------------
# Logic
# ----------------------------

def trend_ema2050(closes: List[float]) -> str:
    e20, _ = ema(closes, 20, return_series=False)
    e50, _ = ema(closes, 50, return_series=False)
    if e20 is None or e50 is None:
        return "flat"
    return "up" if e20 > e50 else "down" if e20 < e50 else "flat"

def risk_position_size(deposit: float, risk_pct: float, entry: float, stop: float) -> Tuple[float, float, float]:
    risk_usdt = deposit * (risk_pct / 100.0)
    dist = abs(entry - stop)
    if dist <= 0:
        return risk_usdt, 0.0, dist
    qty = risk_usdt / dist
    return risk_usdt, qty, dist


def _round_step(value: float, step: Decimal, rounding: str) -> float:
    units = (Decimal(str(value)) / step).to_integral_value(rounding=rounding)
    return float(units * step)


def normalize_for_contract(
    snapshot: Dict[str, Any],
    side: str,
    entry: float,
    stop: float,
    tp1: float,
    tp2: float,
    deposit: float,
    risk_pct: float,
    leverage: float = 1.0,
) -> Dict[str, Any]:
    """Make prices and size executable under the symbol's MEXC contract rules."""
    detail = snapshot.get("contract")
    if not isinstance(detail, dict):
        risk_usdt, qty, dist = risk_position_size(deposit, risk_pct, entry, stop)
        effective_leverage = max(1.0, float(leverage))
        position_usdt = qty * entry
        return {
            "entry": entry, "stop": stop, "tp1": tp1, "tp2": tp2,
            "risk_usdt": risk_usdt, "qty": qty, "dist": dist,
            "contract_vol": None, "contract_size": None, "vol_unit": None,
            "min_vol": None, "max_vol": None, "max_leverage": None,
            "effective_leverage": effective_leverage,
            "position_usdt": position_usdt,
            "margin_usdt": position_usdt / effective_leverage,
            "price_unit": None, "errors": [],
        }

    price_unit = _positive_decimal(detail.get("priceUnit"))
    if price_unit is not None:
        entry = _round_step(entry, price_unit, ROUND_HALF_UP)
        if side == "long":
            stop = _round_step(stop, price_unit, ROUND_FLOOR)
            tp1 = _round_step(tp1, price_unit, ROUND_CEILING)
            tp2 = _round_step(tp2, price_unit, ROUND_CEILING)
        else:
            stop = _round_step(stop, price_unit, ROUND_CEILING)
            tp1 = _round_step(tp1, price_unit, ROUND_FLOOR)
            tp2 = _round_step(tp2, price_unit, ROUND_FLOOR)

    sizing = position_size_for_contract(detail, entry, stop, deposit, risk_pct, leverage=leverage)
    contract_size = _positive_decimal(detail.get("contractSize"))
    vol_unit = _positive_decimal(detail.get("volUnit"))
    min_vol = _positive_decimal(detail.get("minVol"))
    max_vol = _positive_decimal(detail.get("maxVol"))
    max_leverage = _positive_decimal(detail.get("maxLeverage"))
    if contract_size is None or vol_unit is None:
        sizing["errors"].append("invalid_contract_rules")

    return {
        "entry": entry, "stop": stop, "tp1": tp1, "tp2": tp2,
        "risk_usdt": sizing["risk_usdt"], "qty": sizing["qty"], "dist": sizing["dist"],
        "contract_vol": sizing["contract_vol"],
        "contract_size": float(contract_size) if contract_size is not None else None,
        "vol_unit": float(vol_unit) if vol_unit is not None else None,
        "min_vol": float(min_vol) if min_vol is not None else None,
        "max_vol": float(max_vol) if max_vol is not None else None,
        "max_leverage": float(max_leverage) if max_leverage is not None else None,
        "effective_leverage": sizing["effective_leverage"],
        "position_usdt": sizing["position_usdt"],
        "margin_usdt": sizing["margin_usdt"],
        "price_unit": float(price_unit) if price_unit is not None else None,
        "errors": sizing["errors"],
    }

def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))

def rr_metrics(
    entry: float,
    stop: float,
    tp1: float,
    tp2: float,
    side: Optional[str] = None,
) -> Tuple[float, float]:
    r = abs(entry - stop)
    if r <= 0:
        return 0.0, 0.0
    if side == "long":
        rr1 = (tp1 - entry) / r
        rr2 = (tp2 - entry) / r
    elif side == "short":
        rr1 = (entry - tp1) / r
        rr2 = (entry - tp2) / r
    else:
        # Backwards-compatible mode for callers that only need distances.
        rr1 = abs(tp1 - entry) / r
        rr2 = abs(tp2 - entry) / r
    return rr1, rr2


def trade_plan_errors(
    side: str,
    entry: float,
    stop: float,
    tp1: float,
    tp2: float,
) -> List[str]:
    """Return invariant violations that make a two-target plan unsafe to publish."""
    prices = {"entry": entry, "stop": stop, "tp1": tp1, "tp2": tp2}
    errors = [
        f"{name}_not_positive_finite"
        for name, value in prices.items()
        if not math.isfinite(value) or value <= 0
    ]
    if errors:
        return errors

    if side == "long":
        if not stop < entry:
            errors.append("long_stop_not_below_entry")
        if not entry < tp1:
            errors.append("long_tp1_not_above_entry")
        if not tp1 < tp2:
            errors.append("long_tp2_not_above_tp1")
    elif side == "short":
        if not stop > entry:
            errors.append("short_stop_not_above_entry")
        if not entry > tp1:
            errors.append("short_tp1_not_below_entry")
        if not tp1 > tp2:
            errors.append("short_tp2_not_below_tp1")
    else:
        return ["unknown_side"]

    rr1, rr2 = rr_metrics(entry, stop, tp1, tp2, side=side)
    # Small tolerance avoids rejecting an exact threshold because of binary
    # floating-point representation (for example 1.8 becoming 1.799999...).
    rr_epsilon = 1e-9
    if rr1 + rr_epsilon < MIN_RR_TP1:
        errors.append(f"rr1_below_min({rr1:.2f}<{MIN_RR_TP1:.2f})")
    if rr2 + rr_epsilon < MIN_RR_TP2:
        errors.append(f"rr2_below_min({rr2:.2f}<{MIN_RR_TP2:.2f})")
    if rr2 <= rr1:
        errors.append("rr2_not_greater_than_rr1")
    return errors


def plan_payload_errors(plan: Dict[str, Any]) -> List[str]:
    """Validate the primary scenario at storage and delivery boundaries."""
    if plan.get("side") == "skip":
        return []
    primary = plan.get("primary")
    if not isinstance(primary, dict):
        return ["missing_primary"]
    targets = primary.get("tps")
    if not isinstance(targets, list) or len(targets) < 2:
        return ["missing_two_targets"]
    try:
        side = str(primary.get("side", "")).lower()
        entry = float(primary["entry"])
        stop = float(primary["stop"])
        tp1 = float(targets[0]["price"])
        tp2 = float(targets[1]["price"])
    except (KeyError, TypeError, ValueError, IndexError):
        return ["malformed_primary"]
    return trade_plan_errors(side, entry, stop, tp1, tp2)


def _range_targets(side: str, entry: float, stop: float, boundary: float) -> Tuple[float, float]:
    """Use 1R as the partial target and the far range boundary as TP2."""
    risk = abs(entry - stop)
    if side == "long":
        return entry + risk * MIN_RR_TP1, boundary
    if side == "short":
        return entry - risk * MIN_RR_TP1, boundary
    raise ValueError(f"unknown side: {side}")

def _nearest_swing_tp_long(highs4: List[Any], entry: float, min_rr: float, r: float, max_rr: float = MAX_RR_TP1) -> Optional[float]:
    cands = [sw.price for sw in highs4[-80:] if sw.price > entry]
    if not cands:
        return None
    tp = min(cands)
    rr = abs(tp - entry) / max(1e-9, r)
    return tp if (rr >= min_rr and rr <= max_rr) else None

def _next_swing_tp_long(highs4: List[Any], tp1: float) -> Optional[float]:
    cands = [sw.price for sw in highs4[-80:] if sw.price > tp1]
    return min(cands) if cands else None

def _nearest_swing_tp_short(lows4: List[Any], entry: float, min_rr: float, r: float, max_rr: float = MAX_RR_TP1) -> Optional[float]:
    cands = [sw.price for sw in lows4[-80:] if sw.price < entry]
    if not cands:
        return None
    tp = max(cands)  # closest below entry
    rr = abs(entry - tp) / max(1e-9, r)
    return tp if (rr >= min_rr and rr <= max_rr) else None

def _next_swing_tp_short(lows4: List[Any], tp1: float) -> Optional[float]:
    cands = [sw.price for sw in lows4[-80:] if sw.price < tp1]
    return max(cands) if cands else None

# ----------------------------
# Plan
# ----------------------------

def make_plan(snapshot: Dict[str, Any], deposit: float, risk_pct: float, lev: float, margin: str) -> Dict[str, Any]:
    used_cache = bool(snapshot.get("stale") or snapshot.get("fallback", {}).get("used_cache"))
    if used_cache:
        return {
            "symbol": snapshot.get("symbol"),
            "side": "skip",
            "confidence": 0.0,
            "reasons": ["stale_market_data"],
            "used_cache": True,
        }

    bars_4h = parse_bars(snapshot, "kline_4h")
    bars_1d = parse_bars(snapshot, "kline_1d")
    bars_1h = parse_bars(snapshot, "kline_1h")

    lp = last_price_from_snapshot(snapshot)
    if lp is None and bars_4h:
        lp = bars_4h[-1].c

    if not bars_4h or not bars_1d or lp is None:
        return {"symbol": snapshot.get("symbol"), "side": "skip", "confidence": 0.0,
                "reasons": ["not_enough_data"], "used_cache": used_cache}

    closes_4h = [b.c for b in bars_4h]
    closes_1d = [b.c for b in bars_1d]
    closes_1h = [b.c for b in bars_1h] if bars_1h else []

    # Trends (main)
    t1d = trend_ema2050(closes_1d)
    t4h = trend_ema2050(closes_4h)

    # Structure / BOS on 4h
    highs4, lows4 = swings(bars_4h, 2, 2)
    struct4 = last_structure_bias(highs4, lows4)
    bos = bos_choch(highs4, lows4, bars_4h[-1].c)

    # 4h indicators
    e20_4h, _ = ema(closes_4h, 20, return_series=False)
    ohlc4h = [OHLC(o=b.o, h=b.h, l=b.l, c=b.c) for b in bars_4h]
    atr4h, _ = atr(ohlc4h, 14, return_series=False)
    if atr4h is None:
        atr4h = sum((b.h - b.l) for b in bars_4h[-50:]) / max(1, min(50, len(bars_4h)))
    adx4h, _ = adx(ohlc4h, 14, return_series=False)

    vol_reg = volatility_regime(float(atr4h), float(lp))

    # AUX RSI(1h)
    rsi_1h = None
    ema20_1h = None
    momentum_1h = "neutral"
    candle_1h = "neutral"
    if closes_1h:
        rsi_1h, _ = rsi(closes_1h, 14, return_series=False)
        ema20_1h, _ = ema(closes_1h, 20, return_series=False)
        latest_1h = bars_1h[-1]
        if latest_1h.c > latest_1h.o:
            candle_1h = "bullish"
        elif latest_1h.c < latest_1h.o:
            candle_1h = "bearish"
        if ema20_1h is not None:
            if latest_1h.c > latest_1h.o and latest_1h.c > ema20_1h:
                momentum_1h = "up"
            elif latest_1h.c < latest_1h.o and latest_1h.c < ema20_1h:
                momentum_1h = "down"

    # Levels from swings (4h+1d) for range + midrange context
    swing_prices = [s.price for s in highs4[-80:]] + [s.price for s in lows4[-80:]]
    highs1d, lows1d = swings(bars_1d, 2, 2)
    swing_prices += [s.price for s in highs1d[-60:]] + [s.price for s in lows1d[-60:]]

    tol = max(float(atr4h) * 0.40, float(lp) * 0.0018)
    levels = cluster_levels(swing_prices, tol=tol)
    sup, res = nearest_levels(levels, float(lp))
    mr = midrange_ratio(sup, res, float(lp))

    reasons_common = [
        f"trend_1d={t1d}",
        f"trend_4h={t4h}",
        f"struct_4h={struct4}",
        f"bos={bos}",
        f"ema20_4h≈{e20_4h:.2f}" if e20_4h is not None else "ema20_4h=n/a",
        f"atr4h≈{float(atr4h):.2f}",
        f"adx4h≈{adx4h:.1f}" if adx4h is not None else "adx4h=n/a",
        f"vol={vol_reg}",
        f"max_rr_tp1={MAX_RR_TP1:.1f}",
        f"min_rr_tp1={MIN_RR_TP1:.1f}",
        f"min_rr_tp2={MIN_RR_TP2:.1f}",
    ]
    if rsi_1h is not None:
        reasons_common.append(f"rsi1h≈{rsi_1h:.1f}")
    if ema20_1h is not None:
        reasons_common.append(f"ema20_1h≈{ema20_1h:.2f}")
    reasons_common.append(f"momentum1h={momentum_1h}")
    reasons_common.append(f"candle1h={candle_1h}")
    if used_cache:
        reasons_common.append("used_cache_snapshot")

    # Regime detection
    is_trend = False
    if adx4h is not None and adx4h >= 22:
        if t1d == t4h and t1d != "flat":
            is_trend = True
        elif struct4 in ("up", "down") and t4h != "flat":
            is_trend = True
    regime = "trend" if is_trend else "range"
    reasons_common.append(f"regime={regime}")

    # Direction bias (only 1d + 4h + structure)
    bias_long = 0
    bias_short = 0
    def apply_tf(tf: str, w: int):
        nonlocal bias_long, bias_short
        if tf == "up": bias_long += w
        elif tf == "down": bias_short += w
    apply_tf(t1d, 4)
    apply_tf(t4h, 3)
    apply_tf(struct4, 1)

    block_long = (bos == "CHOCH_down")
    block_short = (bos == "CHOCH_up")
    if block_long: reasons_common.append("filter=choch_down_blocks_long")
    if block_short: reasons_common.append("filter=choch_up_blocks_short")

    # Midrange filter
    mid_penalty = 0.0
    mid_skip = False
    if mr is not None and sup is not None and res is not None:
        ds = abs(float(lp) - sup)
        dr = abs(res - float(lp))
        if regime == "range":
            if mr > 0.80 and min(ds, dr) > float(atr4h) * 0.55:
                mid_skip = True
            elif mr > 0.70 and min(ds, dr) > float(atr4h) * 0.40:
                mid_penalty = 0.20
        else:
            if mr > 0.85 and min(ds, dr) > float(atr4h) * 0.60:
                mid_skip = True
            elif mr > 0.75 and min(ds, dr) > float(atr4h) * 0.45:
                mid_penalty = 0.15
        if mid_skip: reasons_common.append("filter=midrange_skip")
        elif mid_penalty > 0: reasons_common.append("filter=midrange_penalty")

    # Vol penalty (soft)
    vol_penalty = 0.0
    if vol_reg == "quiet":
        vol_penalty = 0.05
        reasons_common.append("filter=quiet_penalty")
    if vol_reg == "wild":
        vol_penalty = 0.10
        reasons_common.append("filter=wild_penalty")

    # RSI penalties (soft)
    rsi_pen_long = 0.0
    rsi_pen_short = 0.0
    if rsi_1h is not None:
        if rsi_1h > 70:
            rsi_pen_long = 0.15
            reasons_common.append("filter=rsi1h_high_penalty_long")
        if rsi_1h < 30:
            rsi_pen_short = 0.15
            reasons_common.append("filter=rsi1h_low_penalty_short")

    if e20_4h is None:
        return {"symbol": snapshot.get("symbol"), "side": "skip", "confidence": 0.0,
                "reasons": ["no_ema20_4h"], "used_cache": used_cache}

    entry_buf = float(atr4h) * 0.10

    if vol_reg == "wild":
        stop_mult = 1.8
    elif vol_reg == "quiet":
        stop_mult = 1.2
    else:
        stop_mult = 1.4
    stop_buf = float(atr4h) * stop_mult
    reasons_common.append(f"stop_mult={stop_mult:.2f}")

    far_kill = 1.25 if regime == "trend" else 1.60
    far_pen  = 0.75 if regime == "trend" else 1.10

    def base_conf(long_side: bool) -> float:
        if long_side:
            raw = (bias_long - bias_short + 7) / 14.0
        else:
            raw = (bias_short - bias_long + 7) / 14.0
        return clamp01(raw)

    def apply_filters(conf: float, long_side: bool, reasons: List[str], dist_entry_atr: float) -> float:
        c = conf
        if mid_skip:
            c = 0.0
        else:
            c = clamp01(c - mid_penalty)
        c = clamp01(c - vol_penalty)

        if long_side:
            c = clamp01(c - rsi_pen_long)
            if block_long:
                c = 0.0
        else:
            c = clamp01(c - rsi_pen_short)
            if block_short:
                c = 0.0

        # Distance-to-entry
        if dist_entry_atr >= far_kill:
            reasons.append(f"filter=entry_too_far(dATR={dist_entry_atr:.2f})")
            c = 0.0
        elif dist_entry_atr >= far_pen:
            reasons.append(f"filter=entry_far_penalty(dATR={dist_entry_atr:.2f})")
            c = clamp01(c - 0.15)

        return c

    def build_long() -> Dict[str, Any]:
        if regime == "trend":
            entry = float(e20_4h) - entry_buf
            entry_reason = "entry=limit_on_ema20_4h"
        else:
            entry = (sup if sup is not None else float(lp))
            entry_reason = "entry=range_support"

        stop = entry - stop_buf
        dist = abs(entry - stop)
        r = dist

        tp1_reason = "tp1=1R"
        tp2_reason = "tp2=2R"

        if regime == "range" and res is not None:
            tp1, tp2 = _range_targets("long", entry, stop, res)
            tp1_reason = f"tp1={MIN_RR_TP1:.1f}R"
            tp2_reason = "tp2=range_boundary"
        else:
            tp1 = entry + dist * 1.0
            tp2 = entry + dist * 2.0

            stp1 = _nearest_swing_tp_long(highs4, entry, 0.70, r)
            if stp1 is not None:
                tp1 = stp1
                tp1_reason = "tp1=swing4h"

            if res is not None and res > entry:
                tp1 = min(tp1, res)

            stp2 = _next_swing_tp_long(highs4, tp1) if tp1_reason == "tp1=swing4h" else None

            # RULE:
            # if TP1 is swing, TP2 baseline is not 2R but (RR(TP1)+1R),
            # so TP2 is always further than TP1. If next swing exists, use it,
            # but never closer than baseline.
            rr_to_tp1 = abs(tp1 - entry) / max(1e-9, dist)
            base_rr2 = 2.0
            if tp1_reason == "tp1=swing4h":
                base_rr2 = max(2.0, rr_to_tp1 + 1.0)
            base_tp2 = entry + dist * base_rr2

            if stp2 is not None:
                tp2 = max(base_tp2, stp2)
                tp2_reason = "tp2=swing4h"
            else:
                tp2 = base_tp2
                tp2_reason = f"tp2={base_rr2:.1f}R"

            if tp2 <= tp1:
                tp2 = base_tp2
                tp2_reason = "tp2=fix_order"

        normalized = normalize_for_contract(
            snapshot, "long", entry, stop, tp1, tp2, deposit, risk_pct, lev
        )
        entry, stop = normalized["entry"], normalized["stop"]
        tp1, tp2 = normalized["tp1"], normalized["tp2"]
        risk_usdt, qty, dist = normalized["risk_usdt"], normalized["qty"], normalized["dist"]

        rr1, rr2 = rr_metrics(entry, stop, tp1, tp2, side="long")
        margin_need = normalized["margin_usdt"]
        dist_entry_atr = abs(entry - float(lp)) / max(1e-9, float(atr4h))

        reasons = reasons_common + [
            entry_reason,
            "stop=ATR4h_buffer",
            "tp=50/50",
            tp1_reason,
            tp2_reason,
            f"rr1={rr1:.2f}",
            f"rr2={rr2:.2f}",
            f"entry_dist_ATR4h={dist_entry_atr:.2f}",
        ]
        conf = apply_filters(base_conf(True), True, reasons, dist_entry_atr)
        plan_errors = [*normalized["errors"], *trade_plan_errors("long", entry, stop, tp1, tp2)]
        if plan_errors:
            reasons.extend(f"filter=invalid_plan({error})" for error in plan_errors)
            conf = 0.0

        return {
            "side": "long",
            "confidence": conf,
            "entry": entry,
            "stop": stop,
            "tps": [{"price": tp1, "pct": 0.50}, {"price": tp2, "pct": 0.50}],
            "qty": qty,
            "contract_vol": normalized["contract_vol"],
            "contract_size": normalized["contract_size"],
            "vol_unit": normalized["vol_unit"],
            "min_vol": normalized["min_vol"],
            "max_vol": normalized["max_vol"],
            "max_leverage": normalized["max_leverage"],
            "effective_leverage": normalized["effective_leverage"],
            "price_unit": normalized.get("price_unit"),
            "risk_usdt": risk_usdt,
            "margin_need": margin_need,
            "reasons": reasons,
        }

    def build_short() -> Dict[str, Any]:
        if regime == "trend":
            entry = float(e20_4h) + entry_buf
            entry_reason = "entry=limit_on_ema20_4h"
        else:
            entry = (res if res is not None else float(lp))
            entry_reason = "entry=range_resistance"

        stop = entry + stop_buf
        dist = abs(entry - stop)
        r = dist

        tp1_reason = "tp1=1R"
        tp2_reason = "tp2=2R"

        if regime == "range" and sup is not None:
            tp1, tp2 = _range_targets("short", entry, stop, sup)
            tp1_reason = f"tp1={MIN_RR_TP1:.1f}R"
            tp2_reason = "tp2=range_boundary"
        else:
            tp1 = entry - dist * 1.0
            tp2 = entry - dist * 2.0

            stp1 = _nearest_swing_tp_short(lows4, entry, 0.70, r)
            if stp1 is not None:
                tp1 = stp1
                tp1_reason = "tp1=swing4h"

            if sup is not None and sup < entry:
                tp1 = max(tp1, sup)

            stp2 = _next_swing_tp_short(lows4, tp1) if tp1_reason == "tp1=swing4h" else None

            # RULE:
            # if TP1 is swing, TP2 baseline is not 2R but (RR(TP1)+1R),
            # so TP2 is always further than TP1. If next swing exists, use it,
            # but never closer than baseline.
            rr_to_tp1 = abs(entry - tp1) / max(1e-9, dist)
            base_rr2 = 2.0
            if tp1_reason == "tp1=swing4h":
                base_rr2 = max(2.0, rr_to_tp1 + 1.0)
            base_tp2 = entry - dist * base_rr2

            if stp2 is not None:
                tp2 = min(base_tp2, stp2)
                tp2_reason = "tp2=swing4h"
            else:
                tp2 = base_tp2
                tp2_reason = f"tp2={base_rr2:.1f}R"

            if tp2 >= tp1:
                tp2 = base_tp2
                tp2_reason = "tp2=fix_order"

        normalized = normalize_for_contract(
            snapshot, "short", entry, stop, tp1, tp2, deposit, risk_pct, lev
        )
        entry, stop = normalized["entry"], normalized["stop"]
        tp1, tp2 = normalized["tp1"], normalized["tp2"]
        risk_usdt, qty, dist = normalized["risk_usdt"], normalized["qty"], normalized["dist"]

        rr1, rr2 = rr_metrics(entry, stop, tp1, tp2, side="short")
        margin_need = normalized["margin_usdt"]
        dist_entry_atr = abs(entry - float(lp)) / max(1e-9, float(atr4h))

        reasons = reasons_common + [
            entry_reason,
            "stop=ATR4h_buffer",
            "tp=50/50",
            tp1_reason,
            tp2_reason,
            f"rr1={rr1:.2f}",
            f"rr2={rr2:.2f}",
            f"entry_dist_ATR4h={dist_entry_atr:.2f}",
        ]
        conf = apply_filters(base_conf(False), False, reasons, dist_entry_atr)
        plan_errors = [*normalized["errors"], *trade_plan_errors("short", entry, stop, tp1, tp2)]
        if plan_errors:
            reasons.extend(f"filter=invalid_plan({error})" for error in plan_errors)
            conf = 0.0

        return {
            "side": "short",
            "confidence": conf,
            "entry": entry,
            "stop": stop,
            "tps": [{"price": tp1, "pct": 0.50}, {"price": tp2, "pct": 0.50}],
            "qty": qty,
            "contract_vol": normalized["contract_vol"],
            "contract_size": normalized["contract_size"],
            "vol_unit": normalized["vol_unit"],
            "min_vol": normalized["min_vol"],
            "max_vol": normalized["max_vol"],
            "max_leverage": normalized["max_leverage"],
            "effective_leverage": normalized["effective_leverage"],
            "price_unit": normalized.get("price_unit"),
            "risk_usdt": risk_usdt,
            "margin_need": margin_need,
            "reasons": reasons,
        }

    long_s = build_long()
    short_s = build_short()
    primary = long_s if long_s["confidence"] >= short_s["confidence"] else short_s

    if max(long_s["confidence"], short_s["confidence"]) < 0.15:
        invalid_reasons = [
            reason
            for scenario in (long_s, short_s)
            for reason in scenario.get("reasons", [])
            if reason.startswith("filter=invalid_plan(")
        ]
        return {
            "symbol": snapshot.get("symbol"),
            "side": "skip",
            "confidence": max(long_s["confidence"], short_s["confidence"]),
            "reasons": ["filters_killed_setup", *dict.fromkeys(invalid_reasons)],
            "used_cache": used_cache,
            "trend": {"1d": t1d, "4h": t4h, "struct4h": struct4, "bos": bos, "regime": regime},
            "levels": {"support": sup, "resistance": res, "tol": tol, "mid": mr},
        }

    return {
        "symbol": snapshot.get("symbol"),
        "price": float(lp),
        "used_cache": used_cache,
        "margin": margin,
        "lev": float(primary.get("effective_leverage") or lev),
        "requested_lev": float(lev),
        "trend": {"1d": t1d, "4h": t4h, "struct4h": struct4, "bos": bos, "regime": regime},
        "levels": {"support": sup, "resistance": res, "tol": tol, "mid": mr},
        "scenarios": {"long": long_s, "short": short_s},
        "primary": primary,
    }

# ----------------------------
# Snapshot loader
# ----------------------------

def load_snapshot(symbol: str) -> Dict[str, Any]:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    snap_py = os.path.join(script_dir, "mexc_snapshot.py")

    p = subprocess.run([sys.executable, snap_py, "snapshot", symbol], capture_output=True, text=True)
    if p.returncode == 0:
        try:
            return json.loads(p.stdout)
        except Exception:
            pass

    # Fallback: read cache written by mexc_snapshot.py
    safe = symbol.replace("/", "_")
    cache_path = os.path.join(os.path.expanduser("~/.openclaw/trading/cache"), f"{safe}.snapshot.json")
    with open(cache_path, "r", encoding="utf-8") as f:
        j = json.load(f)
    j["stale"] = True
    return j

# ----------------------------
# CLI / output
# ----------------------------

def parse_kv_args(argv: List[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for a in argv:
        if "=" in a:
            k, v = a.split("=", 1)
            out[k.strip()] = v.strip()
    return out

def fmt_money(x: Optional[float]) -> str:
    try:
        if x is None or not math.isfinite(float(x)):
            return "n/a"
        return f"{float(x):.2f}"
    except Exception:
        return "n/a"

def print_plan(plan: Dict[str, Any]) -> None:
    if plan.get("side") == "skip":
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return

    sym = plan["symbol"]
    price = plan["price"]
    head = f"{sym} | price={fmt_money(price)} | lev={plan['lev']} {plan['margin']}"
    if plan.get("used_cache"):
        head += " | ⚠️cache"
    print(head)

    tr = plan["trend"]
    print(f"trend: 1d={tr['1d']} 4h={tr['4h']} struct4h={tr['struct4h']} bos={tr['bos']} regime={tr['regime']}")

    lvl = plan["levels"]
    mid = lvl.get("mid")
    mid_s = f"{mid:.2f}" if isinstance(mid, (int, float)) and math.isfinite(float(mid)) else "n/a"
    print(f"levels: support={fmt_money(lvl['support'])} resistance={fmt_money(lvl['resistance'])} tol≈{fmt_money(lvl['tol'])} mid≈{mid_s}")
    print("")

    def show(name: str, s: Dict[str, Any]) -> None:
        print(f"[{name.upper()}] conf={s['confidence']:.2f}")
        print(f"  entry={fmt_money(s['entry'])} stop={fmt_money(s['stop'])}")
        tps = s.get("tps") or []
        if len(tps) >= 2:
            print(f"  tp1={fmt_money(tps[0]['price'])} ({int(tps[0]['pct']*100)}%)  tp2={fmt_money(tps[1]['price'])} ({int(tps[1]['pct']*100)}%)")
        print(f"  qty≈{s['qty']:.6f}  risk≈{fmt_money(s['risk_usdt'])}  margin_need≈{fmt_money(s['margin_need'])}")
        rs = s.get("reasons", [])[-16:]
        print("  reasons: " + "; ".join(rs))
        print("")

    show("primary", plan["primary"])
    show("long", plan["scenarios"]["long"])
    show("short", plan["scenarios"]["short"])

def main() -> int:
    if len(sys.argv) < 2:
        print("usage: trade_plan.py SYMBOL deposit=3000 risk=1 lev=20 margin=cross", file=sys.stderr)
        return 2

    symbol = sys.argv[1]
    kv = parse_kv_args(sys.argv[2:])

    deposit = float(kv.get("deposit", "3000"))
    risk_pct = float(kv.get("risk", "1"))
    lev = float(kv.get("lev", "20"))
    margin = kv.get("margin", "cross")

    snapshot = load_snapshot(symbol)
    plan = make_plan(snapshot, deposit=deposit, risk_pct=risk_pct, lev=lev, margin=margin)
    print_plan(plan)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
