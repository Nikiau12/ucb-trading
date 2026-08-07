"""Pre-registered research-only BTC and ETH setup builders.

These builders consume only closed candles supplied by ``run_backtest``. They
are deliberately separate from the production trade-plan builder so research
cannot silently alter signals delivered to users.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from .analytics.indicators import OHLC, adx, atr, ema
from .trade_plan import normalize_for_contract, parse_bars, trade_plan_errors


@dataclass(frozen=True)
class BTCSetup:
    name: str
    kind: str
    lookback: int
    allowed_sides: tuple[str, ...] = ("long", "short")
    min_volume_ratio: float = 1.0
    min_atr_percentile: float = 25.0
    max_atr_percentile: float = 90.0
    enter_on_retest: bool = False


@dataclass(frozen=True)
class ETHSetup:
    name: str
    band_length: int
    band_std: float
    allowed_sides: tuple[str, ...] = ("long", "short")
    require_prior_outside: bool = False
    max_adx: float = 25.0
    max_atr_percentile: float = 80.0
    max_abs_ema_slope_atr: Optional[float] = None
    max_volume_ratio: Optional[float] = None


BTC_V1_SETUPS = (
    BTCSetup("btc_breakout20_long", "breakout", 20, ("long",)),
    BTCSetup("btc_breakout20_short", "breakout", 20, ("short",)),
    BTCSetup("btc_breakout20_both", "breakout", 20),
    BTCSetup("btc_breakout40_long", "breakout", 40, ("long",), 1.2),
    BTCSetup("btc_breakout40_short", "breakout", 40, ("short",), 1.2),
    BTCSetup("btc_continuation_long", "continuation", 20, ("long",), 1.0, 20.0, 85.0),
    BTCSetup("btc_continuation_short", "continuation", 20, ("short",), 1.0, 20.0, 85.0),
    BTCSetup("btc_continuation_both", "continuation", 20, min_volume_ratio=1.1, min_atr_percentile=20.0, max_atr_percentile=85.0),
)


ETH_V1_SETUPS = (
    ETHSetup("eth_band20_1p5_long", 20, 1.5, ("long",)),
    ETHSetup("eth_band20_1p5_short", 20, 1.5, ("short",)),
    ETHSetup("eth_band20_1p5_both", 20, 1.5),
    ETHSetup("eth_band20_2p0_both", 20, 2.0),
    ETHSetup("eth_band40_1p5_both", 40, 1.5),
    ETHSetup("eth_band40_2p0_both", 40, 2.0),
    ETHSetup("eth_band20_1p5_reentry", 20, 1.5, require_prior_outside=True),
    ETHSetup("eth_band40_1p5_reentry", 40, 1.5, require_prior_outside=True),
)


# Iteration 2 is based only on the iteration-1 selection diagnostics. BTC no
# longer chases the trigger close: it waits for a retest of the broken level or
# 1h EMA. ETH requires a flatter range and avoids high-volume shock candles.
BTC_V2_SETUPS = (
    BTCSetup("btc_retest20_long", "breakout", 20, ("long",), 1.0, 25.0, 90.0, True),
    BTCSetup("btc_retest20_short", "breakout", 20, ("short",), 1.0, 25.0, 90.0, True),
    BTCSetup("btc_retest40_long", "breakout", 40, ("long",), 1.2, 25.0, 90.0, True),
    BTCSetup("btc_retest40_short", "breakout", 40, ("short",), 1.2, 25.0, 90.0, True),
    BTCSetup("btc_ema_retest_long", "continuation", 20, ("long",), 1.0, 20.0, 85.0, True),
    BTCSetup("btc_ema_retest_short", "continuation", 20, ("short",), 1.0, 20.0, 85.0, True),
    BTCSetup("btc_ema_retest_long_volume", "continuation", 20, ("long",), 1.2, 20.0, 85.0, True),
    BTCSetup("btc_ema_retest_short_volume", "continuation", 20, ("short",), 1.2, 20.0, 85.0, True),
)


ETH_V2_SETUPS = (
    ETHSetup("eth_flat20_long", 20, 1.5, ("long",), True, 22.0, 65.0, 0.12, 1.5),
    ETHSetup("eth_flat20_short", 20, 1.5, ("short",), True, 22.0, 65.0, 0.12, 1.5),
    ETHSetup("eth_flat20_both", 20, 1.5, require_prior_outside=True, max_adx=22.0, max_atr_percentile=65.0, max_abs_ema_slope_atr=0.12, max_volume_ratio=1.5),
    ETHSetup("eth_flat20_deep", 20, 2.0, require_prior_outside=True, max_adx=22.0, max_atr_percentile=65.0, max_abs_ema_slope_atr=0.12, max_volume_ratio=1.5),
    ETHSetup("eth_flat40_long", 40, 1.5, ("long",), True, 25.0, 65.0, 0.12, 1.5),
    ETHSetup("eth_flat40_short", 40, 1.5, ("short",), True, 25.0, 65.0, 0.12, 1.5),
    ETHSetup("eth_flat40_both", 40, 1.5, require_prior_outside=True, max_adx=25.0, max_atr_percentile=65.0, max_abs_ema_slope_atr=0.12, max_volume_ratio=1.5),
    ETHSetup("eth_flat40_deep", 40, 2.0, require_prior_outside=True, max_adx=25.0, max_atr_percentile=65.0, max_abs_ema_slope_atr=0.12, max_volume_ratio=1.5),
)


BTC_SETUPS = BTC_V2_SETUPS
ETH_SETUPS = ETH_V2_SETUPS


def _skip(symbol: Any, *reasons: str) -> Dict[str, Any]:
    return {
        "symbol": symbol,
        "side": "skip",
        "confidence": 0.0,
        "reasons": list(reasons),
    }


def _atr_percentile(ohlc: list[OHLC], length: int = 14, window: int = 120) -> Optional[float]:
    latest, series = atr(ohlc, length, return_series=True)
    if latest is None or not series:
        return None
    history = [value for value in series[-window:] if math.isfinite(value)]
    if len(history) < 20:
        return None
    return 100.0 * sum(value <= latest for value in history) / len(history)


def _volume_ratio(volumes: list[float], window: int = 20) -> Optional[float]:
    if len(volumes) < window + 1:
        return None
    baseline = statistics.median(volumes[-window - 1:-1])
    return volumes[-1] / baseline if baseline > 0 else None


def _ema_slope_atr(closes: list[float], atr_last: float, lookback: int = 3) -> Optional[float]:
    _, series = ema(closes, 20, return_series=True)
    if not series or len(series) <= lookback or atr_last <= 0:
        return None
    return (series[-1] - series[-1 - lookback]) / atr_last


def closed_market_features(snapshot: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Return normalized features derived exclusively from closed candles."""
    bars_1h = parse_bars(snapshot, "kline_1h")[-180:]
    bars_4h = parse_bars(snapshot, "kline_4h")[-80:]
    if len(bars_1h) < 80 or len(bars_4h) < 35:
        return None
    closes_1h = [bar.c for bar in bars_1h]
    closes_4h = [bar.c for bar in bars_4h]
    ohlc_1h = [OHLC(bar.o, bar.h, bar.l, bar.c) for bar in bars_1h]
    ohlc_4h = [OHLC(bar.o, bar.h, bar.l, bar.c) for bar in bars_4h]
    atr_1h, _ = atr(ohlc_1h, 14, return_series=False)
    adx_4h, _ = adx(ohlc_4h, 14, return_series=False)
    ema20_4h, _ = ema(closes_4h, 20, return_series=False)
    ema50_4h, _ = ema(closes_4h, 50, return_series=False)
    ema20_1h, ema20_1h_series = ema(closes_1h, 20, return_series=True)
    if atr_1h is None or ema20_4h is None or ema50_4h is None or ema20_1h is None:
        return None
    return {
        "bars_1h": bars_1h,
        "bars_4h": bars_4h,
        "closes_1h": closes_1h,
        "atr_1h": float(atr_1h),
        "atr_percentile": _atr_percentile(ohlc_1h),
        "adx_4h": adx_4h,
        "ema20_4h": float(ema20_4h),
        "ema50_4h": float(ema50_4h),
        "ema20_1h": float(ema20_1h),
        "ema20_1h_series": ema20_1h_series,
        "ema_slope_atr": _ema_slope_atr(closes_1h, float(atr_1h)),
        "volume_ratio": _volume_ratio([bar.v for bar in bars_1h]),
    }


def _plan(
    snapshot: Dict[str, Any],
    *,
    side: str,
    entry: float,
    stop: float,
    tp1: float,
    tp2: float,
    confidence: float,
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
        return _skip(snapshot.get("symbol"), *(f"invalid_research_plan:{error}" for error in errors))
    primary = {
        "side": side,
        "confidence": confidence,
        "entry": entry,
        "stop": stop,
        "tps": [
            {"price": tp1, "pct": 0.5},
            {"price": tp2, "pct": 0.5},
        ],
        "qty": normalized["qty"],
        "risk_usdt": normalized["risk_usdt"],
        "reasons": reasons,
    }
    return {
        "symbol": snapshot.get("symbol"),
        "price": entry,
        "margin": margin,
        "trend": {"regime": regime},
        "levels": {},
        "primary": primary,
    }


def btc_plan_builder(setup: BTCSetup) -> Callable[..., Dict[str, Any]]:
    def build(
        snapshot: Dict[str, Any],
        *,
        deposit: float,
        risk_pct: float,
        lev: float,
        margin: str,
    ) -> Dict[str, Any]:
        features = closed_market_features(snapshot)
        if features is None:
            return _skip(snapshot.get("symbol"), "research_warmup")
        bars = features["bars_1h"]
        latest = bars[-1]
        previous = bars[-2]
        atr_1h = features["atr_1h"]
        atr_pct = features["atr_percentile"]
        volume_ratio = features["volume_ratio"]
        slope = features["ema_slope_atr"]
        if atr_pct is None or not setup.min_atr_percentile <= atr_pct <= setup.max_atr_percentile:
            return _skip(snapshot.get("symbol"), "btc_atr_regime_rejected")
        if volume_ratio is None or volume_ratio < setup.min_volume_ratio:
            return _skip(snapshot.get("symbol"), "btc_volume_rejected")

        trend_up = features["ema20_4h"] > features["ema50_4h"]
        trend_down = features["ema20_4h"] < features["ema50_4h"]
        side: Optional[str] = None
        trigger = ""
        if setup.kind == "breakout":
            prior = bars[-setup.lookback - 1:-1]
            ceiling = max(bar.h for bar in prior)
            floor = min(bar.l for bar in prior)
            if "long" in setup.allowed_sides and trend_up and latest.c > ceiling and latest.c > latest.o:
                side, trigger = "long", f"breakout_high={ceiling:.8f}"
            elif "short" in setup.allowed_sides and trend_down and latest.c < floor and latest.c < latest.o:
                side, trigger = "short", f"breakout_low={floor:.8f}"
        else:
            ema_series = features["ema20_1h_series"]
            prior_ema = float(ema_series[-2])
            if (
                "long" in setup.allowed_sides
                and trend_up
                and slope is not None and slope > 0.05
                and previous.l <= prior_ema
                and latest.c > features["ema20_1h"]
                and latest.c > latest.o
            ):
                side, trigger = "long", "continuation=ema20_reclaim"
            elif (
                "short" in setup.allowed_sides
                and trend_down
                and slope is not None and slope < -0.05
                and previous.h >= prior_ema
                and latest.c < features["ema20_1h"]
                and latest.c < latest.o
            ):
                side, trigger = "short", "continuation=ema20_reject"
        if side is None:
            return _skip(snapshot.get("symbol"), "btc_no_trigger")

        if setup.enter_on_retest and setup.kind == "breakout":
            entry = ceiling if side == "long" else floor
        elif setup.enter_on_retest:
            entry = features["ema20_1h"]
        else:
            entry = latest.c
        risk = atr_1h * 1.2
        stop = entry - risk if side == "long" else entry + risk
        tp1 = entry + risk if side == "long" else entry - risk
        tp2 = entry + 2 * risk if side == "long" else entry - 2 * risk
        reasons = [
            f"research_setup={setup.name}",
            trigger,
            f"atr1h_percentile={atr_pct:.1f}",
            f"volume_ratio={volume_ratio:.2f}",
            f"ema20_slope_atr={slope:.3f}" if slope is not None else "ema20_slope_atr=n/a",
        ]
        return _plan(
            snapshot,
            side=side,
            entry=entry,
            stop=stop,
            tp1=tp1,
            tp2=tp2,
            confidence=0.75,
            reasons=reasons,
            deposit=deposit,
            risk_pct=risk_pct,
            lev=lev,
            margin=margin,
            regime="trend",
        )

    return build


def _bands(values: list[float], length: int, multiple: float) -> tuple[float, float, float]:
    sample = values[-length:]
    middle = statistics.fmean(sample)
    deviation = statistics.pstdev(sample)
    return middle, middle - multiple * deviation, middle + multiple * deviation


def eth_plan_builder(setup: ETHSetup) -> Callable[..., Dict[str, Any]]:
    def build(
        snapshot: Dict[str, Any],
        *,
        deposit: float,
        risk_pct: float,
        lev: float,
        margin: str,
    ) -> Dict[str, Any]:
        features = closed_market_features(snapshot)
        if features is None:
            return _skip(snapshot.get("symbol"), "research_warmup")
        bars = features["bars_1h"]
        closes = features["closes_1h"]
        latest = bars[-1]
        previous = bars[-2]
        atr_1h = features["atr_1h"]
        atr_pct = features["atr_percentile"]
        adx_4h = features["adx_4h"]
        if adx_4h is None or adx_4h > setup.max_adx:
            return _skip(snapshot.get("symbol"), "eth_trend_regime_rejected")
        if atr_pct is None or atr_pct > setup.max_atr_percentile:
            return _skip(snapshot.get("symbol"), "eth_atr_regime_rejected")
        slope = features.get("ema_slope_atr")
        if (
            setup.max_abs_ema_slope_atr is not None
            and (slope is None or abs(slope) > setup.max_abs_ema_slope_atr)
        ):
            return _skip(snapshot.get("symbol"), "eth_range_slope_rejected")
        volume_ratio = features.get("volume_ratio")
        if (
            setup.max_volume_ratio is not None
            and (volume_ratio is None or volume_ratio > setup.max_volume_ratio)
        ):
            return _skip(snapshot.get("symbol"), "eth_shock_volume_rejected")
        middle, lower, upper = _bands(closes, setup.band_length, setup.band_std)
        previous_middle, previous_lower, previous_upper = _bands(
            closes[:-1], setup.band_length, setup.band_std
        )
        del previous_middle
        side: Optional[str] = None
        trigger = ""
        long_touch = latest.l <= lower and latest.c > lower and latest.c > latest.o
        short_touch = latest.h >= upper and latest.c < upper and latest.c < latest.o
        if setup.require_prior_outside:
            long_touch = long_touch and previous.c < previous_lower
            short_touch = short_touch and previous.c > previous_upper
        if "long" in setup.allowed_sides and long_touch:
            side, trigger = "long", "range_reclaim=lower_band"
        elif "short" in setup.allowed_sides and short_touch:
            side, trigger = "short", "range_reclaim=upper_band"
        if side is None:
            return _skip(snapshot.get("symbol"), "eth_no_reversion_trigger")

        entry = latest.c
        stop = min(latest.l, lower) - 0.20 * atr_1h if side == "long" else max(latest.h, upper) + 0.20 * atr_1h
        risk = abs(entry - stop)
        tp1 = middle
        tp2 = upper if side == "long" else lower
        if side == "long" and (tp1 - entry < risk or tp2 - entry < 1.8 * risk):
            return _skip(snapshot.get("symbol"), "eth_range_reward_too_small")
        if side == "short" and (entry - tp1 < risk or entry - tp2 < 1.8 * risk):
            return _skip(snapshot.get("symbol"), "eth_range_reward_too_small")
        reasons = [
            f"research_setup={setup.name}",
            trigger,
            f"adx4h={adx_4h:.1f}",
            f"atr1h_percentile={atr_pct:.1f}",
            f"band_middle={middle:.8f}",
            f"band_lower={lower:.8f}",
            f"band_upper={upper:.8f}",
        ]
        return _plan(
            snapshot,
            side=side,
            entry=entry,
            stop=stop,
            tp1=tp1,
            tp2=tp2,
            confidence=0.75,
            reasons=reasons,
            deposit=deposit,
            risk_pct=risk_pct,
            lev=lev,
            margin=margin,
            regime="range",
        )

    return build
