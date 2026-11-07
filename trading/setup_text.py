"""One setup text for chat and the Mini App.

Field names come from the same i18n keys the panel uses. The Russian text
does not print the raw tokens entry, midrange, or deposit.
"""

from __future__ import annotations

import html

try:
    from .i18n import t as _t
    from .telegram_render import confidence_percent
    from .trade_plan import position_size_for_contract
except ImportError:
    from i18n import t as _t
    from telegram_render import confidence_percent
    from trade_plan import position_size_for_contract


_BIAS = {
    "en": {"up": "BULLISH", "down": "BEARISH", "flat": "Flat", "trend": "Trend", "range": "Range"},
    "ru": {"up": "РОСТ", "down": "ПАДЕНИЕ", "flat": "Флэт", "trend": "Тренд", "range": "Диапазон"},
    "de": {"up": "STEIGEND", "down": "FALLEND", "flat": "Seitwärts", "trend": "Trend", "range": "Range"},
    "fr": {"up": "HAUSSIER", "down": "BAISSIER", "flat": "Plat", "trend": "Tendance", "range": "Range"},
    "es": {"up": "ALCISTA", "down": "BAJISTA", "flat": "Plano", "trend": "Tendencia", "range": "Rango"},
}

_LEAKED_TOKENS = ("entry", "midrange", "deposit")


def _esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=False)


def _bias(lang: str, value: str) -> str:
    words = _BIAS.get(lang) or _BIAS["en"]
    return words.get(str(value or "").lower(), "")


def _parts(raw: str) -> dict[str, str]:
    found = {}
    for piece in str(raw or "").split(";"):
        if "=" in piece:
            key, value = piece.split("=", 1)
            found[key] = value
    return found


def regime_text(lang: str, raw: str) -> str:
    """1D/4H regime in the user's language. Not a candle-window return."""
    parts = _parts(raw)
    day = _bias(lang, parts.get("1d", ""))
    hour = _bias(lang, parts.get("4h", ""))
    if not day and not hour:
        return ""
    return f"1D {day} · 4H {hour}".strip()


def reason_text(lang: str, raw: str) -> str:
    lines = []
    for piece in str(raw or "").split(" · "):
        item = piece.strip()
        if not item or any(token in item.lower() for token in _LEAKED_TOKENS):
            continue
        if item.startswith("trend_1d="):
            word = _bias(lang, item.split("=", 1)[1])
            if word:
                lines.append(f"{_t(lang, 'tf_1d')}: {word}")
        elif item.startswith("trend_4h="):
            word = _bias(lang, item.split("=", 1)[1])
            if word:
                lines.append(f"{_t(lang, 'tf_4h')}: {word}")
        elif item.startswith("struct_4h="):
            word = _bias(lang, item.split("=", 1)[1])
            if word:
                lines.append(f"{_t(lang, 'tf_struct')}: {word}")
        elif item.startswith("regime="):
            word = _bias(lang, item.split("=", 1)[1])
            if word:
                lines.append(f"{_t(lang, 'tf_regime')}: {word}")
        elif item.startswith("bos="):
            lines.append(f"BOS/CHOCH: {_esc(item.split('=', 1)[1])}")
    return " · ".join(lines)


def signal_query(signal_id: int) -> str:
    return f"signal_id={int(signal_id)}"


def no_setup_query(symbol: str) -> str:
    """Panel link for a symbol that has no setup. Never a signal id."""
    pair = str(symbol or "").strip().upper()
    base = pair[:-5] if pair.endswith("_USDT") else ""
    if not base or not base.isalnum() or not 2 <= len(base) <= 20:
        raise ValueError("symbol")
    return f"no_setup={pair}"


def _fmt_price(price, price_unit=None) -> str:
    if price is None:
        return "—"
    try:
        from decimal import Decimal

        value = float(price)
        if price_unit is not None:
            unit = Decimal(str(price_unit)).normalize()
            decimals = max(0, -unit.as_tuple().exponent)
            return f"{value:,.{decimals}f}"
        if value >= 1000:
            return f"{value:,.1f}"
        if value >= 1:
            return f"{value:.4f}"
        return f"{value:.6f}"
    except (TypeError, ValueError, ArithmeticError):
        return _esc(price)


def _fmt_usdt(value) -> str:
    try:
        return f"{float(value):,.2f}".replace(",", " ")
    except (TypeError, ValueError):
        return "—"


def render_setup(
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
    """Shared trade ticket for manual plans, scan results and automatic signals."""
    del conf
    primary = plan.get("primary") or {}
    targets = primary.get("tps") or []
    entry = primary.get("entry")
    stop = primary.get("stop")
    tp1 = targets[0]["price"] if targets else None
    tp2 = targets[1]["price"] if len(targets) > 1 else None
    price_unit = primary.get("price_unit")
    direction = str(side or "").upper()
    position_usdt = None
    sizing_errors = []
    leverage_limited = False
    try:
        sizing = position_size_for_contract(
            primary, float(entry), float(stop), float(deposit), float(risk_pct), float(leverage)
        )
        position_usdt = sizing["position_usdt"]
        sizing_errors = sizing["errors"]
        leverage_limited = sizing["effective_leverage"] < sizing["requested_leverage"]
    except (TypeError, ValueError, ZeroDivisionError, KeyError):
        pass
    reasons = primary.get("reasons") or plan.get("reasons") or []
    reason_raw = " · ".join(str(item) for item in reasons if item)
    why = reason_text(lang, reason_raw).split(" · ", 1)[0]
    lines = [
        f"<b>{_esc(symbol)}</b> {_esc(direction)}",
        f"{_t(lang, 'alert_price_now')}: <code>{_esc(_fmt_price(plan.get('price'), price_unit))}</code>",
        f"{_t(lang, 'alert_entry')}: <code>{_esc(_fmt_price(entry, price_unit))}</code>",
        f"{_t(lang, 'alert_stop')}: <code>{_esc(_fmt_price(stop, price_unit))}</code>",
        f"TP1: <code>{_esc(_fmt_price(tp1, price_unit))}</code>",
        f"TP2: <code>{_esc(_fmt_price(tp2, price_unit))}</code>",
        f"{_t(lang, 'alert_position')}: <b>{_fmt_usdt(position_usdt)} USDT</b>",
    ]
    ratio = _reward_risk(entry, stop, tp1)
    if ratio:
        lines.append(ratio)
    if why:
        lines.append(why)
    if "position_below_min_contract" in sizing_errors or "position_below_min_notional" in sizing_errors:
        lines.append(_t(lang, "alert_min_contract"))
    elif leverage_limited:
        lines.append(_t(lang, "alert_lev_capped"))
    if uses_reference_deposit:
        lines.append(_t(lang, "alert_reference"))
    return "\n".join(lines)


def render_alert_block(
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
    """Automatic signals use the same fields and ordering as manual plans."""
    return render_setup(plan, symbol, side, conf, deposit, risk_pct, leverage,
                        lang=lang, uses_reference_deposit=uses_reference_deposit)


def _reward_risk(entry, stop, tp1) -> str | None:
    try:
        risk = abs(float(entry) - float(stop))
        reward = abs(float(tp1) - float(entry))
    except (TypeError, ValueError):
        return None
    if risk == 0:
        return None
    return f"{reward / risk:.1f}R"


def render_scan_card(
    plan: dict,
    symbol: str,
    side: str,
    deposit: float,
    risk_pct: float,
    leverage: float,
    *,
    lang: str = "en",
) -> str:
    """Scan/digest signals use the same trade ticket as /plan."""
    return render_setup(plan, symbol, side, 0, deposit, risk_pct, leverage, lang=lang)
