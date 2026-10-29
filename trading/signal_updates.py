"""Signal lifecycle rules and human-readable trade update messages."""

from __future__ import annotations

import html
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Optional


TRACKABLE_STATUSES = {"waiting_entry", "active", "tp1_reached"}


def _as_float(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _reached(side: str, price: float, level: Any, *, rising: bool) -> bool:
    target = _as_float(level)
    if target is None:
        return False
    direction = str(side or "").upper()
    if direction == "LONG":
        return price >= target if rising else price <= target
    if direction == "SHORT":
        return price <= target if rising else price >= target
    return False


def advance_lifecycle(signal: dict, price: Any, now: datetime) -> dict:
    """Return the next lifecycle state without performing I/O.

    Entry is treated as a limit level. Stop checks are conservative and take
    precedence over targets. A direct jump to TP2 is terminal and intentionally
    does not enqueue a stale break-even instruction.
    """
    status = str(signal.get("status") or "waiting_entry")
    events: list[str] = []
    result = {"status": status, "events": events}
    if status not in TRACKABLE_STATUSES:
        return result

    entry_expires_at = signal.get("entry_expires_at")
    holding_expires_at = signal.get("holding_expires_at")
    if status == "waiting_entry" and entry_expires_at and now >= entry_expires_at:
        return {"status": "expired", "events": ["expired"]}
    if status != "waiting_entry" and holding_expires_at and now >= holding_expires_at:
        return {"status": "expired", "events": ["expired"]}

    current = _as_float(price)
    if current is None:
        return result
    side = str(signal.get("side") or "").upper()

    if status == "waiting_entry":
        if not _reached(side, current, signal.get("entry"), rising=False):
            return result
        status = "active"
        events.append("entry_reached")

    if status == "active":
        if _reached(side, current, signal.get("stop"), rising=False):
            return {"status": "stopped", "events": [*events, "stop_reached"]}
        if _reached(side, current, signal.get("tp2"), rising=True):
            return {"status": "tp2_reached", "events": [*events, "tp1_reached", "tp2_reached"]}
        if _reached(side, current, signal.get("tp1"), rising=True):
            return {"status": "tp1_reached", "events": [*events, "tp1_reached"]}

    if status == "tp1_reached":
        # After the TP1 instruction the remaining half is protected at the
        # signal entry, so that entry becomes the effective Stop (BE).
        if _reached(side, current, signal.get("entry"), rising=False):
            return {"status": "stopped", "events": ["stop_reached"]}
        if _reached(side, current, signal.get("tp2"), rising=True):
            return {"status": "tp2_reached", "events": ["tp2_reached"]}
    return {"status": status, "events": events}


def replay_lifecycle(signal: dict, candles: list[dict], now: datetime) -> dict:
    """Reconstruct a pre-feature signal from closed 1H candles.

    This is used once for recent production signals during migration. Ambiguous
    candles remain conservative: Stop is evaluated before either target.
    """
    created_at = _utc(signal.get("created_at"))
    entry_expires_at = signal.get("entry_expires_at") or created_at + timedelta(hours=12)
    if entry_expires_at.tzinfo is None:
        entry_expires_at = entry_expires_at.replace(tzinfo=timezone.utc)
    max_holding_seconds = max(1, int(signal.get("max_holding_seconds") or 14 * 86400))
    side = str(signal.get("side") or "").upper()
    entry = _as_float(signal.get("entry"))
    stop = _as_float(signal.get("stop"))
    tp1 = _as_float(signal.get("tp1"))
    tp2 = _as_float(signal.get("tp2"))
    if side not in {"LONG", "SHORT"} or None in {entry, stop, tp1, tp2}:
        return {"status": "expired", "expired_at": now}

    status = "waiting_entry"
    entry_hit_at = tp1_hit_at = tp2_hit_at = stop_hit_at = expired_at = None
    holding_expires_at = None
    ordered = sorted(candles or [], key=lambda item: int(item.get("time") or 0))
    for candle in ordered:
        try:
            candle_at = datetime.fromtimestamp(int(candle["time"]), timezone.utc)
            high = float(candle["high"])
            low = float(candle["low"])
        except (KeyError, TypeError, ValueError, OSError):
            continue
        if candle_at < created_at:
            continue
        # BingX includes the currently forming 1H candle. Historical replay
        # must only use closed candles or an intrahour wick could create a
        # false entry/target before that candle is final.
        if candle_at + timedelta(hours=1) > now:
            continue
        if status == "waiting_entry":
            if candle_at >= entry_expires_at:
                status, expired_at = "expired", entry_expires_at
                break
            entry_touched = low <= entry if side == "LONG" else high >= entry
            if not entry_touched:
                continue
            status = "active"
            entry_hit_at = candle_at
            holding_expires_at = candle_at + timedelta(seconds=max_holding_seconds)

        if holding_expires_at and candle_at >= holding_expires_at:
            status, expired_at = "expired", holding_expires_at
            break
        effective_stop = entry if status == "tp1_reached" else stop
        stop_touched = low <= effective_stop if side == "LONG" else high >= effective_stop
        tp1_touched = high >= tp1 if side == "LONG" else low <= tp1
        tp2_touched = high >= tp2 if side == "LONG" else low <= tp2
        if stop_touched:
            status, stop_hit_at = "stopped", candle_at
            break
        if tp2_touched:
            status = "tp2_reached"
            tp1_hit_at = tp1_hit_at or candle_at
            tp2_hit_at = candle_at
            break
        if status == "active" and tp1_touched:
            status, tp1_hit_at = "tp1_reached", candle_at

    if status == "waiting_entry" and now >= entry_expires_at:
        status, expired_at = "expired", entry_expires_at
    elif status in {"active", "tp1_reached"} and holding_expires_at and now >= holding_expires_at:
        status, expired_at = "expired", holding_expires_at
    return {
        "status": status,
        "entry_hit_at": entry_hit_at,
        "holding_expires_at": holding_expires_at,
        "tp1_hit_at": tp1_hit_at,
        "tp2_hit_at": tp2_hit_at,
        "stop_hit_at": stop_hit_at,
        "expired_at": expired_at,
    }


def _utc(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            parsed = datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_price(value: Any, price_unit: Any = None) -> str:
    number = _as_float(value)
    if number is None:
        return "-"
    decimals = 2
    try:
        unit = Decimal(str(price_unit))
        if unit > 0:
            decimals = max(0, min(10, -unit.normalize().as_tuple().exponent))
        elif number < 1:
            decimals = 6
    except (InvalidOperation, TypeError, ValueError):
        decimals = 6 if number < 1 else 2
    return f"{number:.{decimals}f}"


_COPY = {
    "ru": {
        "trade": "Сделка",
        "signal_date": "Сигнал от",
        "title": "TP1 достигнут",
        "action": "Действие сейчас",
        "fix": "Зафиксируйте 50% позиции",
        "move": "Перенесите Stop оставшейся позиции в безубыток",
        "be": "Ориентир БУ по цене входа",
        "actual": "Если ваша фактическая цена входа отличалась, ставьте БУ относительно своей цены.",
        "stop_title": "Stop сработал",
        "be_title": "Остаток закрыт в БУ",
        "stop_line": "Сделка закрыта по Stop",
        "be_line": "После TP1 остаток позиции закрыт в безубыток",
        "cancel": "Сетап аннулирован. Не входите повторно.",
        "wait": "Дождитесь нового сигнала — он придёт отдельным сообщением.",
        "be_level": "Цена БУ",
    },
    "en": {
        "trade": "Trade",
        "signal_date": "Signal from",
        "title": "TP1 reached",
        "action": "Action now",
        "fix": "Take profit on 50% of the position",
        "move": "Move the Stop on the remaining position to break-even",
        "be": "Break-even from the signal entry",
        "actual": "If your actual fill price differed, use your own entry for break-even.",
        "stop_title": "Stop reached",
        "be_title": "Remainder closed at break-even",
        "stop_line": "The trade was closed at Stop",
        "be_line": "After TP1, the remaining position closed at break-even",
        "cancel": "The setup is cancelled. Do not re-enter it.",
        "wait": "Wait for a new signal; it will arrive in a separate message.",
        "be_level": "Break-even price",
    },
    "de": {
        "trade": "Trade",
        "signal_date": "Signal vom",
        "title": "TP1 erreicht",
        "action": "Jetzt handeln",
        "fix": "50% der Position sichern",
        "move": "Stop der Restposition auf Einstand setzen",
        "be": "Einstand ab Signal-Einstieg",
        "actual": "Wenn dein tatsächlicher Einstieg abwich, nutze deinen eigenen Einstieg.",
        "stop_title": "Stop erreicht",
        "be_title": "Restposition am Einstand geschlossen",
        "stop_line": "Der Trade wurde am Stop geschlossen",
        "be_line": "Nach TP1 wurde die Restposition am Einstand geschlossen",
        "cancel": "Das Setup ist aufgehoben. Nicht erneut einsteigen.",
        "wait": "Warte auf ein neues Signal; es kommt als eigene Nachricht.",
        "be_level": "Einstandspreis",
    },
    "fr": {
        "trade": "Trade",
        "signal_date": "Signal du",
        "title": "TP1 atteint",
        "action": "Action maintenant",
        "fix": "Prenez vos bénéfices sur 50% de la position",
        "move": "Déplacez le Stop du solde au seuil de rentabilité",
        "be": "Seuil calculé depuis l'entrée du signal",
        "actual": "Si votre prix exécuté diffère, utilisez votre prix d'entrée réel.",
        "stop_title": "Stop atteint",
        "be_title": "Solde clôturé au seuil de rentabilité",
        "stop_line": "Le trade a été clôturé au Stop",
        "be_line": "Après TP1, le solde a été clôturé au seuil de rentabilité",
        "cancel": "Le setup est annulé. Ne rentrez pas à nouveau.",
        "wait": "Attendez un nouveau signal; il arrivera séparément.",
        "be_level": "Prix d'équilibre",
    },
    "es": {
        "trade": "Operación",
        "signal_date": "Señal del",
        "title": "TP1 alcanzado",
        "action": "Acción ahora",
        "fix": "Asegura el 50% de la posición",
        "move": "Mueve el Stop del resto al punto de equilibrio",
        "be": "Equilibrio desde la entrada de la señal",
        "actual": "Si tu entrada real fue distinta, usa tu propio precio de entrada.",
        "stop_title": "Stop alcanzado",
        "be_title": "Resto cerrado en equilibrio",
        "stop_line": "La operación se cerró por Stop",
        "be_line": "Después de TP1, el resto se cerró en el punto de equilibrio",
        "cancel": "El setup queda anulado. No vuelvas a entrar.",
        "wait": "Espera una nueva señal; llegará en otro mensaje.",
        "be_level": "Precio de equilibrio",
    },
}


def _copy(lang: str) -> dict:
    return _COPY.get(str(lang or "").lower(), _COPY["en"])


def signal_identity_footer(
    signal_id: int,
    symbol: str,
    side: str,
    *,
    lang: str,
    created_at: Any = None,
) -> str:
    words = _copy(lang)
    moment = _utc(created_at)
    identity = f"{str(symbol or '').upper()} · {str(side or '').upper()}"
    return (
        f"🆔 <b>{html.escape(words['trade'])} #{int(signal_id)}</b> · "
        f"<code>{html.escape(identity)}</code>\n"
        f"🗓 {html.escape(words['signal_date'])}: {moment:%d.%m.%Y %H:%M} UTC"
    )


def render_tp1_update(signal: dict, *, lang: str) -> str:
    words = _copy(lang)
    signal_id = int(signal["id"])
    symbol = str(signal.get("symbol") or "").upper()
    side = str(signal.get("side") or "").upper()
    tp1 = _format_price(signal.get("tp1"), signal.get("price_unit"))
    entry = _format_price(signal.get("entry"), signal.get("price_unit"))
    footer = signal_identity_footer(
        signal_id,
        symbol,
        side,
        lang=lang,
        created_at=signal.get("created_at"),
    )
    return (
        f"✅ <b>{html.escape(words['title'])}</b>\n\n"
        f"{footer}\n\n"
        f"TP1: <code>{html.escape(tp1)}</code>\n\n"
        f"<b>{html.escape(words['action'])}:</b>\n"
        f"• {html.escape(words['fix'])}\n"
        f"• {html.escape(words['move'])}\n"
        f"• {html.escape(words['be'])}: <code>{html.escape(entry)}</code>\n\n"
        f"<i>{html.escape(words['actual'])}</i>"
    )


def render_stop_update(signal: dict, *, lang: str) -> str:
    words = _copy(lang)
    at_break_even = bool(signal.get("tp1_hit_at"))
    level = _format_price(
        signal.get("entry") if at_break_even else signal.get("stop"),
        signal.get("price_unit"),
    )
    footer = signal_identity_footer(
        int(signal["id"]),
        str(signal.get("symbol") or "").upper(),
        str(signal.get("side") or "").upper(),
        lang=lang,
        created_at=signal.get("created_at"),
    )
    title = words["be_title"] if at_break_even else words["stop_title"]
    result = words["be_line"] if at_break_even else words["stop_line"]
    level_label = words["be_level"] if at_break_even else "Stop"
    return (
        f"🛑 <b>{html.escape(title)}</b>\n\n"
        f"{footer}\n\n"
        f"{html.escape(result)}: <code>{html.escape(level)}</code>\n\n"
        f"• {html.escape(words['cancel'])}\n"
        f"• {html.escape(words['wait'])}\n\n"
        f"<i>{html.escape(level_label)}: {html.escape(level)}</i>"
    )
