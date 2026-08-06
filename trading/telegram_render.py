from __future__ import annotations

import math
from decimal import Decimal
from typing import Any, Dict, Optional

from i18n import t as _t


def _fmt(x: Any) -> str:
    try:
        x = float(x)
        if not math.isfinite(x):
            return "n/a"
        if abs(x) >= 1000:
            return f"{x:,.0f}".replace(",", " ")
        if abs(x) >= 10:
            return f"{x:.2f}"
        return f"{x:.4f}"
    except Exception:
        return "n/a"


def _fmt_price(x: Any, price_unit: Any) -> str:
    try:
        value = float(x)
        unit = Decimal(str(price_unit)).normalize()
        if not math.isfinite(value) or not unit.is_finite() or unit <= 0:
            return _fmt(x)
        decimals = max(0, -unit.as_tuple().exponent)
        return f"{value:,.{decimals}f}".replace(",", " ")
    except Exception:
        return _fmt(x)


# Human-readable labels for internal reason codes
_REASON_LABELS: Dict[str, str] = {
    "ema_cross":          "EMA crossover",
    "ema_bullish":        "Bullish EMA stack",
    "ema_bearish":        "Bearish EMA stack",
    "bos":                "Break of structure",
    "bos_confirmed":      "BOS confirmed",
    "choch":              "Change of character",
    "support_hold":       "Support holding",
    "resistance_hold":    "Resistance holding",
    "support_break":      "Support broken",
    "resistance_break":   "Resistance broken",
    "ob_bullish":         "Bullish order block",
    "ob_bearish":         "Bearish order block",
    "fvg_bullish":        "Fair value gap (bullish)",
    "fvg_bearish":        "Fair value gap (bearish)",
    "trend_1d_up":        "Daily uptrend",
    "trend_1d_down":      "Daily downtrend",
    "trend_4h_up":        "4h uptrend",
    "trend_4h_down":      "4h downtrend",
    "volume_spike":       "Volume spike",
    "rsi_oversold":       "RSI oversold",
    "rsi_overbought":     "RSI overbought",
    "atr_low":            "Low volatility",
    "atr_high":           "High volatility",
    "near_support":       "Price near support",
    "near_resistance":    "Price near resistance",
    "liquidity_grab":     "Liquidity sweep",
    "mtf_aligned":        "Multi-timeframe aligned",
    "mtf_conflict":       "Multi-timeframe conflict",
    "high_conf":          "High confidence setup",
}


def _fmt_reasons(reasons: list, lang: str) -> str:
    if not reasons:
        return "—"
    labels = [_REASON_LABELS.get(r, r.replace("_", " ")) for r in reasons]
    return " · ".join(labels)


def _tp(scn: Dict[str, Any], i: int) -> Optional[float]:
    tps = scn.get("tps") or []
    if len(tps) > i and isinstance(tps[i], dict):
        return tps[i].get("price")
    return None


def render_telegram_plan(
    plan: Dict[str, Any],
    *,
    deposit: float,
    risk_pct: float,
    lang: str = "en",
) -> str:
    L = lang

    # ── SKIP ──
    if plan.get("side") == "skip":
        sym   = plan.get("symbol", "?")
        conf  = float(plan.get("confidence", 0.0) or 0.0)
        rs    = plan.get("reasons") or []
        why   = " · ".join(rs[:10]) if rs else "no_setup"
        cache = f"  {_t(L, 'r_cache_warn')}" if plan.get("used_cache") else ""
        return (
            f"{_t(L, 'r_context')}\n"
            f"📌 <b><code>{sym}</code> — SKIP</b>{cache}\n"
            f"{_t(L, 'r_skip_conf')}: <b>{conf:.2f}</b>\n"
            f"{_t(L, 'r_skip_reason')}: {why}\n\n"
            f"{_t(L, 'r_risk_rule')}\n"
            f"{_t(L, 'r_risk_text')}"
        )

    sym       = plan.get("symbol", "?")
    price     = plan.get("price")
    used_cache = bool(plan.get("used_cache"))
    lev       = plan.get("lev")
    margin    = plan.get("margin")

    tr  = plan.get("trend") or {}
    lvl = plan.get("levels") or {}
    sup = lvl.get("support")
    res = lvl.get("resistance")
    mid = lvl.get("mid")

    primary = plan.get("primary") or {}
    side    = str(primary.get("side", "skip")).upper()
    conf    = float(primary.get("confidence", 0.0) or 0.0)

    entry      = primary.get("entry")
    stop       = primary.get("stop")
    tp1        = _tp(primary, 0)
    tp2        = _tp(primary, 1)
    qty        = primary.get("qty")
    risk_usdt  = primary.get("risk_usdt")
    margin_need = primary.get("margin_need")
    price_unit = primary.get("price_unit")

    reasons      = primary.get("reasons") or []
    short_reasons = reasons[-10:] if len(reasons) > 10 else reasons
    why = _fmt_reasons(short_reasons, L)

    cache_tag = f"  {_t(L, 'r_cache_warn')}" if used_cache else ""
    side_tag  = "🟥" if side == "SHORT" else "🟩" if side == "LONG" else "🧊"
    mid_s = _fmt(mid) if isinstance(mid, (int, float)) and math.isfinite(float(mid)) else "n/a"
    # Confidence as percentage (consistent with Mini App display)
    conf_pct = f"{conf * 100:.0f}%"

    return (
        f"{_t(L, 'r_context')}\n"
        f"📌 <b><code>{sym}</code> — {_t(L, 'r_plan')}</b>{cache_tag}\n"
        f"{_t(L, 'r_price')}: <code>{_fmt_price(price, price_unit)}</code>\n\n"

        f"{_t(L, 'r_profile')}\n"
        f"{_t(L, 'r_deposit')}: <b>{_fmt(deposit)}</b>\n"
        f"{_t(L, 'r_risk')}: <b>{_fmt(deposit * (risk_pct / 100.0))}</b> USDT (<b>{risk_pct}%</b>)\n"
        f"{_t(L, 'r_lev')}: <b>{_fmt(lev)}x</b> ({margin})\n\n"

        f"{_t(L, 'r_regime')}\n"
        f"• {_t(L, 'r_trend_1d')}: <b>{tr.get('1d', '—')}</b> | "
        f"{_t(L, 'r_trend_4h')}: <b>{tr.get('4h', '—')}</b>\n"
        f"• {_t(L, 'r_struct')}: <b>{tr.get('struct4h', '—')}</b> | "
        f"{_t(L, 'r_bos')}: <b>{tr.get('bos', '—')}</b>\n"
        f"• {_t(L, 'r_regime_label')}: <b>{tr.get('regime', '—')}</b> | "
        f"{_t(L, 'r_mid')}: <b>{mid_s}</b>\n\n"

        f"{side_tag} <b>{_t(L, 'r_scenario')}</b>\n"
        f"✅ <b>{side}</b> — {_t(L, 'r_confidence')}: <b>{conf_pct}</b>\n"
        f"{_t(L, 'r_entry')}: <code>{_fmt_price(entry, price_unit)}</code>\n"
        f"{_t(L, 'r_stop')}: <code>{_fmt_price(stop, price_unit)}</code>\n"
        f"{_t(L, 'r_tp1')}: <code>{_fmt_price(tp1, price_unit)}</code>\n"
        f"{_t(L, 'r_tp2')}: <code>{_fmt_price(tp2, price_unit)}</code>\n\n"

        f"{_t(L, 'r_size')}\n"
        f"• {_t(L, 'r_qty')}: <code>{_fmt(qty)}</code>\n"
        f"• {_t(L, 'r_risk_label')}: <b>{_fmt(risk_usdt)}</b> USDT | "
        f"{_t(L, 'r_margin_need')}: <code>{_fmt(margin_need)}</code>\n\n"

        f"{_t(L, 'r_levels')}\n"
        f"{_t(L, 'r_support')}: <code>{_fmt(sup)}</code>\n"
        f"{_t(L, 'r_resistance')}: <code>{_fmt(res)}</code>\n\n"

        f"{_t(L, 'r_why')}\n"
        f"{why}\n\n"

        f"{_t(L, 'r_risk_rule')}\n"
        f"{_t(L, 'r_risk_text')}"
    )
