"""Localized automatic plan alerts."""

from __future__ import annotations

import html
from decimal import Decimal

try:
    from .i18n import t as _t
    from .trade_plan import position_size_for_contract
except ImportError:
    from i18n import t as _t
    from trade_plan import position_size_for_contract


def _esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=False)


def _fmt_price(price, price_unit=None) -> str:
    if price is None:
        return "?"
    try:
        value = float(price)
        if price_unit is not None:
            unit = Decimal(str(price_unit)).normalize()
            decimals = max(0, -unit.as_tuple().exponent)
            return f"{value:,.{decimals}f}"
        if value >= 10000:
            return f"{value:,.0f}"
        if value >= 1000:
            return f"{value:,.1f}"
        if value >= 10:
            return f"{value:.2f}"
        if value >= 1:
            return f"{value:.4f}"
        return f"{value:.6f}"
    except (TypeError, ValueError, ArithmeticError):
        return _esc(price)


def _pct(left, right) -> str:
    try:
        return f"{abs(float(left) - float(right)) / float(right) * 100:.1f}%"
    except (TypeError, ValueError, ZeroDivisionError):
        return ""


def _rr(entry, stop, target) -> str:
    try:
        risk = abs(float(entry) - float(stop))
        reward = abs(float(target) - float(entry))
        return f"RR {reward / risk:.1f}x" if risk else ""
    except (TypeError, ValueError, ZeroDivisionError):
        return ""


def _fmt_usdt(value) -> str:
    try:
        return f"{float(value):,.2f}".replace(",", " ")
    except (TypeError, ValueError):
        return "—"


def render_auto_alert(
    plan: dict,
    symbol: str,
    side: str,
    conf: float,
    deposit: float,
    risk_pct: float,
    leverage: float,
    *,
    lang: str = "en",
    uses_reference_deposit: bool = False,
) -> str:
    primary = plan.get("primary") or {}
    context = plan.get("context") or {}
    targets = primary.get("tps") or []
    entry = primary.get("entry")
    stop = primary.get("stop")
    tp1 = targets[0]["price"] if targets else None
    tp2 = targets[1]["price"] if len(targets) > 1 else None
    price_unit = primary.get("price_unit")
    regime = str(context.get("regime", "")).upper() or "—"
    trend = str(context.get("trend_1d", "")).upper() or "—"
    why = primary.get("why") or []
    badge = "🟢 LONG" if str(side).upper() == "LONG" else "🔴 SHORT"
    contract_vol = None
    leverage_limited = False
    sizing_errors: list = []
    risk_usdt = position_usdt = margin_usdt = None
    try:
        sizing = position_size_for_contract(
            primary, float(entry), float(stop), float(deposit), float(risk_pct), float(leverage)
        )
        risk_usdt = sizing["risk_usdt"]
        position_usdt = sizing["position_usdt"]
        margin_usdt = sizing["margin_usdt"]
        leverage = sizing["effective_leverage"]
        contract_vol = sizing["contract_vol"]
        leverage_limited = sizing["effective_leverage"] < sizing["requested_leverage"]
        sizing_errors = sizing["errors"]
    except (TypeError, ValueError, ZeroDivisionError, KeyError):
        pass

    lines = [
        "━━━━━━━━━━━━━━━━━━",
        f"📊 <b>{_t(lang, 'alert_signal')} — {badge}</b>",
        "━━━━━━━━━━━━━━━━━━",
        "",
        f"🪙 <b><code>{_esc(symbol)}</code></b>",
        f"💵 {_t(lang, 'alert_price_now')}: <code>{_esc(_fmt_price(plan.get('price'), price_unit))}</code>",
        (
            f"🧭 {_t(lang, 'alert_regime')}: <b>{_esc(regime)}</b>  |  "
            f"{_t(lang, 'alert_trend')}: <b>{_esc(trend)}</b>"
        ),
        f"⭐️ {_t(lang, 'alert_confidence')}: <b>{float(conf):.2f}</b> / 1.0",
        "",
        "─────────────────",
        f"{'↗️' if str(side).upper() == 'LONG' else '↘️'} {_t(lang, 'alert_entry')}: <code>{_esc(_fmt_price(entry, price_unit))}</code>",
        (
            f"🛑 {_t(lang, 'alert_stop')}: <code>{_esc(_fmt_price(stop, price_unit))}</code>  "
            f"({_pct(stop, entry)} {_t(lang, 'alert_from_entry')})"
        ),
        (
            f"🥅 TP1: <code>{_esc(_fmt_price(tp1, price_unit))}</code>  "
            f"(+{_pct(tp1, entry)})  {_rr(entry, stop, tp1)}"
        ),
        (
            f"🥅 TP2: <code>{_esc(_fmt_price(tp2, price_unit))}</code>  "
            f"(+{_pct(tp2, entry)})  {_rr(entry, stop, tp2)}"
        ),
        "─────────────────",
        f"💰 {_t(lang, 'alert_deposit')}: <b>{_fmt_usdt(deposit)} USDT</b>",
        f"📦 {_t(lang, 'alert_position')}: <b>{_fmt_usdt(position_usdt)} USDT</b>",
        f"🔒 {_t(lang, 'alert_margin')}: <b>{_fmt_usdt(margin_usdt)} USDT</b> (x{_esc(f'{float(leverage):g}')})",
        f"🛡 {_t(lang, 'alert_risk')}: <b>{_fmt_usdt(risk_usdt)} USDT</b> ({_esc(f'{float(risk_pct):g}')}%)",
        "─────────────────",
    ]
    if contract_vol is not None:
        lines.insert(-1, f"📐 {_t(lang, 'alert_contracts')}: <b>{contract_vol:g}</b>")
    if leverage_limited:
        lines.insert(-1, f"⚠️ {_t(lang, 'alert_lev_capped')}")
    if "position_below_min_contract" in sizing_errors:
        lines.insert(-1, f"⚠️ {_t(lang, 'alert_min_contract')}")
    if uses_reference_deposit:
        lines.extend(["", f"⚠️ <i>{_t(lang, 'alert_reference')}</i>", ""])
    if why:
        safe_why = " · ".join(_esc(item) for item in list(why)[:3])
        lines.append(f"🔍 <i>{safe_why}</i>")
        lines.append("")
    lines.append(f"📋 {_t(lang, 'alert_more')} /plan <code>{_esc(symbol)}</code>")
    return "\n".join(lines)
