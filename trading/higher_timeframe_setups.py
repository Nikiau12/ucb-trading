"""Research-only strategies whose complete signal input is 4H and 1D.

Hourly candles are not read here. They may be used upstream only to construct
complete four-hour candles before this builder is called.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from .analytics.indicators import OHLC, adx, atr, ema
from .analytics.structure import swings
from .research_setups import structural_range
from .trade_plan import normalize_for_contract, parse_bars, trade_plan_errors


@dataclass(frozen=True)
class HTFSetup:
    name: str
    kind: str
    lookback_4h: int
    allowed_sides: tuple[str, ...] = ("long", "short")
    min_adx_4h: Optional[float] = None
    max_adx_4h: Optional[float] = None
    min_volume_ratio: float = 0.0
    min_touches: int = 2
    reclaim_bars: int = 2
    max_daily_trend_age: Optional[int] = None
    max_daily_extension_atr: Optional[float] = None
    min_close_extension_atr: Optional[float] = None
    max_atr_4h_pct: Optional[float] = None


BTC_4H_1D_SETUPS = (
    HTFSetup("btc_4h_pullback_long", "trend_pullback", 20, ("long",), 20.0),
    HTFSetup("btc_4h_pullback_short", "trend_pullback", 20, ("short",), 20.0),
    HTFSetup("btc_4h_pullback_both", "trend_pullback", 20, min_adx_4h=25.0),
    HTFSetup("btc_4h_breakout12_long", "breakout", 12, ("long",), 20.0, min_volume_ratio=1.0),
    HTFSetup("btc_4h_breakout24_long", "breakout", 24, ("long",), 20.0, min_volume_ratio=1.1),
    HTFSetup("btc_4h_breakout24_both", "breakout", 24, min_adx_4h=20.0, min_volume_ratio=1.1),
)


ETH_4H_1D_SETUPS = (
    HTFSetup("eth_4h_range30_t2_r1_long", "range", 30, ("long",), max_adx_4h=25.0, min_touches=2, reclaim_bars=1),
    HTFSetup("eth_4h_range30_t2_r1_short", "range", 30, ("short",), max_adx_4h=25.0, min_touches=2, reclaim_bars=1),
    HTFSetup("eth_4h_range30_t2_r2_both", "range", 30, max_adx_4h=25.0, min_touches=2, reclaim_bars=2),
    HTFSetup("eth_4h_range30_t3_r2_both", "range", 30, max_adx_4h=25.0, min_touches=3, reclaim_bars=2),
    HTFSetup("eth_4h_range60_t2_r1_both", "range", 60, max_adx_4h=28.0, min_touches=2, reclaim_bars=1),
    HTFSetup("eth_4h_range60_t3_r2_both", "range", 60, max_adx_4h=28.0, min_touches=3, reclaim_bars=2),
)


SOL_4H_1D_SETUPS = (
    HTFSetup("sol_4h_pullback_long", "trend_pullback", 16, ("long",), 20.0),
    HTFSetup("sol_4h_pullback_short", "trend_pullback", 16, ("short",), 20.0),
    HTFSetup("sol_4h_pullback_both", "trend_pullback", 16, min_adx_4h=25.0),
    HTFSetup("sol_4h_breakout12_long", "breakout", 12, ("long",), 20.0, min_volume_ratio=1.0),
    HTFSetup("sol_4h_breakout12_short", "breakout", 12, ("short",), 20.0, min_volume_ratio=1.0),
    HTFSetup("sol_4h_breakout24_both", "breakout", 24, min_adx_4h=20.0, min_volume_ratio=1.1),
)


# These compact libraries were pre-registered after diagnosing selection data.
# They are exploratory only: the previously observed confirmation period cannot
# be used to validate them, so they require a new forward window.
BTC_4H_DIAGNOSTIC_CANDIDATES = (
    HTFSetup(
        "btc_4h_pullback_long_age60",
        "trend_pullback",
        20,
        ("long",),
        20.0,
        max_daily_trend_age=60,
    ),
    HTFSetup(
        "btc_4h_pullback_long_reclaim20",
        "trend_pullback",
        20,
        ("long",),
        20.0,
        min_close_extension_atr=0.20,
    ),
    HTFSetup(
        "btc_4h_pullback_long_age60_reclaim20",
        "trend_pullback",
        20,
        ("long",),
        20.0,
        max_daily_trend_age=60,
        min_close_extension_atr=0.20,
    ),
)


SOL_4H_DIAGNOSTIC_CANDIDATES = (
    HTFSetup(
        "sol_4h_pullback_long_quality",
        "trend_pullback",
        16,
        ("long",),
        25.0,
        max_daily_trend_age=65,
        max_daily_extension_atr=2.30,
        min_close_extension_atr=0.15,
    ),
    HTFSetup(
        "sol_4h_pullback_short_early_lowvol",
        "trend_pullback",
        16,
        ("short",),
        25.0,
        max_daily_trend_age=25,
        max_daily_extension_atr=1.80,
        max_atr_4h_pct=3.30,
    ),
    HTFSetup(
        "sol_4h_pullback_both_conservative",
        "trend_pullback",
        16,
        min_adx_4h=25.0,
        max_daily_trend_age=50,
        max_daily_extension_atr=2.30,
        min_close_extension_atr=0.15,
        max_atr_4h_pct=4.00,
    ),
)


def _skip(symbol: Any, reason: str) -> Dict[str, Any]:
    return {
        "symbol": symbol,
        "side": "skip",
        "confidence": 0.0,
        "reasons": [reason],
    }


def _volume_ratio(volumes: list[float], window: int = 20) -> Optional[float]:
    if len(volumes) < window + 1:
        return None
    baseline = statistics.median(volumes[-window - 1:-1])
    return volumes[-1] / baseline if baseline > 0 else None


def htf_features(snapshot: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    bars_4h = parse_bars(snapshot, "kline_4h")[-240:]
    bars_1d = parse_bars(snapshot, "kline_1d")[-120:]
    if len(bars_4h) < 80 or len(bars_1d) < 55:
        return None
    closes_4h = [bar.c for bar in bars_4h]
    closes_1d = [bar.c for bar in bars_1d]
    ohlc_4h = [OHLC(bar.o, bar.h, bar.l, bar.c) for bar in bars_4h]
    atr_4h, _ = atr(ohlc_4h, 14, return_series=False)
    adx_4h, _ = adx(ohlc_4h, 14, return_series=False)
    ema20_4h, ema20_4h_series = ema(closes_4h, 20, return_series=True)
    ema50_4h, _ = ema(closes_4h, 50, return_series=False)
    ema20_1d, ema20_1d_series = ema(closes_1d, 20, return_series=True)
    ema50_1d, ema50_1d_series = ema(closes_1d, 50, return_series=True)
    atr_1d, _ = atr(
        [OHLC(bar.o, bar.h, bar.l, bar.c) for bar in bars_1d],
        14,
        return_series=False,
    )
    if None in (atr_4h, atr_1d, adx_4h, ema20_4h, ema50_4h, ema20_1d, ema50_1d):
        return None
    trend_up_1d = ema20_1d > ema50_1d
    daily_trend_age = 0
    for fast, slow in zip(reversed(ema20_1d_series), reversed(ema50_1d_series)):
        if (fast > slow) != trend_up_1d:
            break
        daily_trend_age += 1
    highs, lows = swings(bars_4h, 2, 2)
    return {
        "bars_4h": bars_4h,
        "bars_1d": bars_1d,
        "atr_4h": float(atr_4h),
        "adx_4h": float(adx_4h),
        "ema20_4h": float(ema20_4h),
        "ema20_4h_series": ema20_4h_series,
        "trend_4h": "up" if ema20_4h > ema50_4h else "down",
        "trend_1d": "up" if trend_up_1d else "down",
        "ema20_1d": float(ema20_1d),
        "atr_1d": float(atr_1d),
        "daily_trend_age": daily_trend_age,
        "volume_ratio": _volume_ratio([bar.v for bar in bars_4h]),
        "swing_highs": highs,
        "swing_lows": lows,
    }


def _build_plan(
    snapshot: Dict[str, Any],
    *,
    side: str,
    entry: float,
    stop: float,
    tp1: float,
    tp2: float,
    reasons: list[str],
    deposit: float,
    risk_pct: float,
    lev: float,
    margin: str,
    regime: str,
) -> Dict[str, Any]:
    normalized = normalize_for_contract(
        snapshot, side, entry, stop, tp1, tp2, deposit, risk_pct, lev
    )
    entry = normalized["entry"]
    stop = normalized["stop"]
    tp1 = normalized["tp1"]
    tp2 = normalized["tp2"]
    errors = [
        *normalized["errors"],
        *trade_plan_errors(side, entry, stop, tp1, tp2),
    ]
    if errors:
        return _skip(snapshot.get("symbol"), f"invalid_4h_plan:{errors[0]}")
    primary = {
        "side": side,
        "confidence": 0.75,
        "entry": entry,
        "stop": stop,
        "tps": [
            {"price": tp1, "pct": 0.5},
            {"price": tp2, "pct": 0.5},
        ],
        "qty": normalized["qty"],
        "risk_usdt": normalized["risk_usdt"],
        "entry_expiry_bars": 2,
        "max_holding_bars": 42,
        "reasons": reasons,
    }
    return {
        "symbol": snapshot.get("symbol"),
        "price": entry,
        "margin": margin,
        "trend": {"1d": reasons[0], "4h": reasons[1], "regime": regime},
        "levels": {},
        "primary": primary,
    }


def htf_plan_builder(setup: HTFSetup) -> Callable[..., Dict[str, Any]]:
    def build(
        snapshot: Dict[str, Any],
        *,
        deposit: float,
        risk_pct: float,
        lev: float,
        margin: str,
    ) -> Dict[str, Any]:
        if (snapshot.get("kline_1h") or {}).get("data"):
            return _skip(snapshot.get("symbol"), "unexpected_1h_signal_data")
        features = htf_features(snapshot)
        if features is None:
            return _skip(snapshot.get("symbol"), "4h_1d_warmup")
        bars = features["bars_4h"]
        latest = bars[-1]
        atr_4h = features["atr_4h"]
        adx_4h = features["adx_4h"]
        volume_ratio = features["volume_ratio"]
        if setup.min_adx_4h is not None and adx_4h < setup.min_adx_4h:
            return _skip(snapshot.get("symbol"), "4h_adx_too_low")
        if setup.max_adx_4h is not None and adx_4h > setup.max_adx_4h:
            return _skip(snapshot.get("symbol"), "4h_adx_too_high")
        if setup.min_volume_ratio and (
            volume_ratio is None or volume_ratio < setup.min_volume_ratio
        ):
            return _skip(snapshot.get("symbol"), "4h_volume_rejected")
        if (
            setup.max_daily_trend_age is not None
            and features["daily_trend_age"] > setup.max_daily_trend_age
        ):
            return _skip(snapshot.get("symbol"), "1d_trend_too_mature")
        atr_4h_pct = 100 * atr_4h / latest.c
        if setup.max_atr_4h_pct is not None and atr_4h_pct > setup.max_atr_4h_pct:
            return _skip(snapshot.get("symbol"), "4h_volatility_too_high")

        side: Optional[str] = None
        entry = stop = tp1 = tp2 = 0.0
        regime = "trend"
        trigger = ""
        if setup.kind in ("trend_pullback", "breakout"):
            trend_up = features["trend_1d"] == features["trend_4h"] == "up"
            trend_down = features["trend_1d"] == features["trend_4h"] == "down"
            if setup.kind == "trend_pullback":
                ema20 = features["ema20_4h"]
                if (
                    "long" in setup.allowed_sides
                    and trend_up
                    and latest.l <= ema20
                    and latest.c > ema20
                    and latest.c > latest.o
                ):
                    side, entry, trigger = "long", ema20, "4h_pullback=ema20_reclaim"
                elif (
                    "short" in setup.allowed_sides
                    and trend_down
                    and latest.h >= ema20
                    and latest.c < ema20
                    and latest.c < latest.o
                ):
                    side, entry, trigger = "short", ema20, "4h_pullback=ema20_reject"
            else:
                prior = bars[-setup.lookback_4h - 1:-1]
                ceiling = max(bar.h for bar in prior)
                floor = min(bar.l for bar in prior)
                if (
                    "long" in setup.allowed_sides
                    and trend_up
                    and latest.c > ceiling
                    and latest.c > latest.o
                ):
                    side, entry, trigger = "long", ceiling, "4h_breakout=high_retest"
                elif (
                    "short" in setup.allowed_sides
                    and trend_down
                    and latest.c < floor
                    and latest.c < latest.o
                ):
                    side, entry, trigger = "short", floor, "4h_breakout=low_retest"
            if side is not None:
                if setup.max_daily_extension_atr is not None:
                    signed_daily_extension = (
                        (bars[-1].c - features["ema20_1d"]) / features["atr_1d"]
                        if side == "long"
                        else (features["ema20_1d"] - bars[-1].c) / features["atr_1d"]
                    )
                    if signed_daily_extension > setup.max_daily_extension_atr:
                        return _skip(snapshot.get("symbol"), "1d_extension_too_large")
                if setup.min_close_extension_atr is not None:
                    signed_close_extension = (
                        (latest.c - features["ema20_4h"]) / atr_4h
                        if side == "long"
                        else (features["ema20_4h"] - latest.c) / atr_4h
                    )
                    if signed_close_extension < setup.min_close_extension_atr:
                        return _skip(snapshot.get("symbol"), "4h_reclaim_too_weak")
                risk = 1.2 * atr_4h
                stop = entry - risk if side == "long" else entry + risk
                tp1 = entry + risk if side == "long" else entry - risk
                tp2 = entry + 2.2 * risk if side == "long" else entry - 2.2 * risk
        else:
            regime = "range"
            range_data = structural_range(bars, atr_4h, setup.lookback_4h)
            if range_data is None:
                return _skip(snapshot.get("symbol"), "4h_range_missing")
            if (
                range_data["support_touches"] < setup.min_touches
                or range_data["resistance_touches"] < setup.min_touches
                or not 3.0 <= range_data["width_atr"] <= 14.0
            ):
                return _skip(snapshot.get("symbol"), "4h_range_structure_rejected")
            recent = bars[-setup.reclaim_bars:]
            support = range_data["support"]
            resistance = range_data["resistance"]
            middle = range_data["middle"]
            if (
                "long" in setup.allowed_sides
                and min(bar.l for bar in recent) <= support
                and latest.c > support
                and latest.c > latest.o
            ):
                side, entry, trigger = "long", latest.c, "4h_range=support_reclaim"
                stop = min(bar.l for bar in recent) - 0.2 * atr_4h
                tp1, tp2 = middle, resistance
            elif (
                "short" in setup.allowed_sides
                and max(bar.h for bar in recent) >= resistance
                and latest.c < resistance
                and latest.c < latest.o
            ):
                side, entry, trigger = "short", latest.c, "4h_range=resistance_reclaim"
                stop = max(bar.h for bar in recent) + 0.2 * atr_4h
                tp1, tp2 = middle, support
            if side is not None:
                risk = abs(entry - stop)
                reward1 = tp1 - entry if side == "long" else entry - tp1
                reward2 = tp2 - entry if side == "long" else entry - tp2
                if reward1 < risk or reward2 < 1.8 * risk:
                    return _skip(snapshot.get("symbol"), "4h_range_reward_too_small")

        if side is None:
            return _skip(snapshot.get("symbol"), "no_closed_4h_trigger")
        reasons = [
            features["trend_1d"],
            features["trend_4h"],
            f"research_setup={setup.name}",
            trigger,
            f"adx4h={adx_4h:.1f}",
            f"atr4h={atr_4h:.8f}",
            f"volume4h_ratio={volume_ratio:.2f}" if volume_ratio is not None else "volume4h_ratio=n/a",
            "signal_timeframes=4h+1d",
        ]
        return _build_plan(
            snapshot,
            side=side,
            entry=entry,
            stop=stop,
            tp1=tp1,
            tp2=tp2,
            reasons=reasons,
            deposit=deposit,
            risk_pct=risk_pct,
            lev=lev,
            margin=margin,
            regime=regime,
        )

    return build
