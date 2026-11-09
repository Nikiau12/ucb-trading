"""Signal lifecycle rules and human-readable trade update messages."""

from __future__ import annotations

import html
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Optional
from trading.group_labels import strategy_notice, cancellation_reason


TRACKABLE_STATUSES = {"waiting_entry", "active", "tp1_reached"}


def _as_float(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _touched(side: str, high: float, low: float, level: Any, *, rising: bool) -> bool:
    target = _as_float(level)
    if target is None:
        return False
    direction = str(side or "").upper()
    if direction == "LONG":
        return high >= target if rising else low <= target
    if direction == "SHORT":
        return low <= target if rising else high >= target
    return False


def _level_transition(signal: dict, status: str, high: float, low: float) -> dict:
    """Apply the same level priority to a live price or a closed candle.

    A target and entry inside one candle have unknown order, so an unentered
    setup is cancelled. After entry, Stop wins ambiguous Stop/target candles.
    """
    events: list[str] = []
    side = str(signal.get("side") or "").upper()
    if status == "waiting_entry":
        stop_entry = (signal.get("strategy") or {}).get("entry_type") == "stop"
        if _touched(side, high, low, signal.get("tp1"), rising=True):
            return {"status": "cancelled_before_entry", "events": ["cancelled_before_entry"]}
        if stop_entry and _touched(side, high, low, signal.get("stop"), rising=False):
            return {"status": "cancelled_before_entry", "events": ["cancelled_before_entry"]}
        if not _touched(side, high, low, signal.get("entry"), rising=stop_entry):
            return {"status": status, "events": events}
        status = "active"
        events.append("entry_reached")

    if status == "active":
        if _touched(side, high, low, signal.get("stop"), rising=False):
            return {"status": "stopped", "events": [*events, "stop_reached"]}
        if _touched(side, high, low, signal.get("tp2"), rising=True):
            return {"status": "tp2_reached", "events": [*events, "tp1_reached", "tp2_reached"]}
        if _touched(side, high, low, signal.get("tp1"), rising=True):
            return {"status": "tp1_reached", "events": [*events, "tp1_reached"]}

    if status == "tp1_reached":
        # The remaining half is protected at the entry price after TP1.
        if _touched(side, high, low, signal.get("entry"), rising=False):
            return {"status": "stopped", "events": ["stop_reached"]}
        if _touched(side, high, low, signal.get("tp2"), rising=True):
            return {"status": "tp2_reached", "events": ["tp2_reached"]}
    return {"status": status, "events": events}


def advance_lifecycle(signal: dict, price: Any, now: datetime) -> dict:
    """Return the next lifecycle state without performing I/O.

    Legacy entry is a limit; versioned group signals use a stop trigger.
    Stop checks are conservative and take
    precedence over targets. A direct jump to TP2 is terminal and intentionally
    does not enqueue a stale break-even instruction.
    """
    status = str(signal.get("status") or "waiting_entry")
    result = {"status": status, "events": []}
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
    return _level_transition(signal, status, current, current)


def replay_lifecycle(
    signal: dict,
    candles: list[dict],
    now: datetime,
    *,
    candle_seconds: int = 3600,
) -> dict:
    """Reconstruct a signal from chronologically ordered closed candles.

    A target reached before entry cancels the setup. If Entry and TP1 occur in
    the same smallest available candle, their order cannot be proven, so the
    setup is cancelled conservatively. Stop remains conservative after entry.
    """
    created_at = _utc(signal.get("created_at"))
    entry_expires_at = signal.get("entry_expires_at") or created_at + timedelta(hours=12)
    if entry_expires_at.tzinfo is None:
        entry_expires_at = entry_expires_at.replace(tzinfo=timezone.utc)
    max_holding_seconds = max(1, int(signal.get("max_holding_seconds") or 14 * 86400))
    side = str(signal.get("side") or "").upper()
    levels = tuple(_as_float(signal.get(key)) for key in ("entry", "stop", "tp1", "tp2"))
    if side not in {"LONG", "SHORT"} or None in levels:
        return {"status": "expired", "expired_at": now}

    status = "waiting_entry"
    entry_hit_at = tp1_hit_at = tp2_hit_at = stop_hit_at = expired_at = None
    cancelled_at = None
    holding_expires_at = None
    candle_duration = timedelta(seconds=max(1, int(candle_seconds)))
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
        # BingX includes the currently forming candle. Historical replay must
        # use only closed candles or a live wick could create a false event.
        if candle_at + candle_duration > now:
            continue
        if status == "waiting_entry":
            if candle_at >= entry_expires_at:
                status, expired_at = "expired", entry_expires_at
                break
        elif holding_expires_at and candle_at >= holding_expires_at:
            status, expired_at = "expired", holding_expires_at
            break

        outcome = _level_transition(signal, status, high, low)
        events = outcome["events"]
        if "cancelled_before_entry" in events:
            status, cancelled_at = "cancelled_before_entry", candle_at
            break
        if "entry_reached" in events:
            entry_hit_at = candle_at
            holding_expires_at = candle_at + timedelta(seconds=max_holding_seconds)
        status = outcome["status"]
        if "tp1_reached" in events:
            tp1_hit_at = tp1_hit_at or candle_at
        if "stop_reached" in events:
            stop_hit_at = candle_at
            break
        if "tp2_reached" in events:
            tp2_hit_at = candle_at
            break

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
        "cancelled_at": cancelled_at,
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
        "signal": "Сигнал",
        "signal_date": "Сигнал от",
        "title": "TP1 достигнут",
        "action": "Действие сейчас",
        "fix": "Зафиксируйте 50% позиции",
        "move": "Перенесите Stop оставшейся позиции в безубыток",
        "be": "Ориентир БУ по цене входа",
        "actual": "Если ваша фактическая цена входа отличалась, ставьте БУ относительно своей цены.",
        "stop_title": "Stop сработал",
        "be_title": "Остаток закрыт в БУ",
        "stop_line": "Цена сигнала достигла Stop",
        "be_line": "После TP1 остаток позиции закрыт в безубыток",
        "cancel": "Прежние уровни сигнала больше не действуют.",
        "wait": "Дождитесь нового сигнала — он придёт отдельным сообщением.",
        "be_level": "Цена БУ",
        "cancel_before_entry_title": "Сигнал больше не актуален",
        "entry_not_reached": "Вход по сигналу не подтверждён",
        "tp1_first": "Цена достигла TP1 раньше подтверждённого входа",
        "do_not_enter": "Не используйте прежние уровни. Дождитесь нового сигнала.",
    },
    "en": {
        "signal": "Signal",
        "signal_date": "Signal from",
        "title": "TP1 reached",
        "action": "Action now",
        "fix": "Take profit on 50% of the position",
        "move": "Move the Stop on the remaining position to break-even",
        "be": "Break-even from the signal entry",
        "actual": "If your actual fill price differed, use your own entry for break-even.",
        "stop_title": "Stop reached",
        "be_title": "Remainder closed at break-even",
        "stop_line": "Signal price reached Stop",
        "be_line": "After TP1, the remaining position closed at break-even",
        "cancel": "The previous signal levels no longer apply.",
        "wait": "Wait for a new signal; it will arrive in a separate message.",
        "be_level": "Break-even price",
        "cancel_before_entry_title": "Signal no longer valid",
        "entry_not_reached": "Signal entry was not confirmed",
        "tp1_first": "Price reached TP1 before confirmed entry",
        "do_not_enter": "Do not use these levels. Wait for a new signal.",
    },
    "de": {
        "signal": "Signal",
        "signal_date": "Signal vom",
        "title": "TP1 erreicht",
        "action": "Jetzt handeln",
        "fix": "50% der Position sichern",
        "move": "Stop der Restposition auf Einstand setzen",
        "be": "Einstand ab Signal-Einstieg",
        "actual": "Wenn dein tatsächlicher Einstieg abwich, nutze deinen eigenen Einstieg.",
        "stop_title": "Stop erreicht",
        "be_title": "Restposition am Einstand geschlossen",
        "stop_line": "Signalpreis erreichte Stop",
        "be_line": "Nach TP1 wurde die Restposition am Einstand geschlossen",
        "cancel": "Die bisherigen Signalniveaus gelten nicht mehr.",
        "wait": "Warte auf ein neues Signal; es kommt als eigene Nachricht.",
        "be_level": "Einstandspreis",
        "cancel_before_entry_title": "Signal nicht mehr gültig",
        "entry_not_reached": "Signal-Einstieg nicht bestätigt",
        "tp1_first": "Preis erreichte TP1 vor bestätigtem Einstieg",
        "do_not_enter": "Diese Niveaus nicht verwenden. Warte auf ein neues Signal.",
    },
    "fr": {
        "signal": "Signal",
        "signal_date": "Signal du",
        "title": "TP1 atteint",
        "action": "Action maintenant",
        "fix": "Prenez vos bénéfices sur 50% de la position",
        "move": "Déplacez le Stop du solde au seuil de rentabilité",
        "be": "Seuil calculé depuis l'entrée du signal",
        "actual": "Si votre prix exécuté diffère, utilisez votre prix d'entrée réel.",
        "stop_title": "Stop atteint",
        "be_title": "Solde clôturé au seuil de rentabilité",
        "stop_line": "Le prix du signal a atteint le Stop",
        "be_line": "Après TP1, le solde a été clôturé au seuil de rentabilité",
        "cancel": "Les anciens niveaux du signal ne sont plus valables.",
        "wait": "Attendez un nouveau signal; il arrivera séparément.",
        "be_level": "Prix d'équilibre",
        "cancel_before_entry_title": "Signal non valable",
        "entry_not_reached": "Entrée du signal non confirmée",
        "tp1_first": "Prix au TP1 avant entrée confirmée",
        "do_not_enter": "N’utilisez pas ces niveaux. Attendez un nouveau signal.",
    },
    "es": {
        "signal": "Señal",
        "signal_date": "Señal del",
        "title": "TP1 alcanzado",
        "action": "Acción ahora",
        "fix": "Asegura el 50% de la posición",
        "move": "Mueve el Stop del resto al punto de equilibrio",
        "be": "Equilibrio desde la entrada de la señal",
        "actual": "Si tu entrada real fue distinta, usa tu propio precio de entrada.",
        "stop_title": "Stop alcanzado",
        "be_title": "Resto cerrado en equilibrio",
        "stop_line": "El precio de la señal alcanzó Stop",
        "be_line": "Después de TP1, el resto se cerró en el punto de equilibrio",
        "cancel": "Los niveles anteriores de la señal ya no son válidos.",
        "wait": "Espera una nueva señal; llegará en otro mensaje.",
        "be_level": "Precio de equilibrio",
        "cancel_before_entry_title": "Señal ya no válida",
        "entry_not_reached": "Entrada de señal no confirmada",
        "tp1_first": "Precio alcanzó TP1 antes de entrada confirmada",
        "do_not_enter": "No uses estos niveles. Espera una nueva señal.",
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
        f"🆔 <b>{html.escape(words['signal'])} #{int(signal_id)}</b> · "
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
        + strategy_notice(signal, lang, details=False)
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
        + strategy_notice(signal, lang, details=False)
    )


def render_cancelled_before_entry_update(signal: dict, *, lang: str) -> str:
    words = _copy(lang)
    entry = _format_price(signal.get("entry"), signal.get("price_unit"))
    tp1 = _format_price(signal.get("tp1"), signal.get("price_unit"))
    footer = signal_identity_footer(
        int(signal["id"]),
        str(signal.get("symbol") or "").upper(),
        str(signal.get("side") or "").upper(),
        lang=lang,
        created_at=signal.get("created_at"),
    )
    return (
        f"🚫 <b>{html.escape(words['cancel_before_entry_title'])}</b>\n\n"
        f"{footer}\n\n"
        f"Entry: <code>{html.escape(entry)}</code>\n"
        f"TP1: <code>{html.escape(tp1)}</code>\n\n"
        f"• {html.escape(words['entry_not_reached'])}\n"
        f"• {html.escape(cancellation_reason(signal, lang, words['tp1_first']))}\n\n"
        f"<b>{html.escape(words['do_not_enter'])}</b>"
        + strategy_notice(signal, lang, details=False)
    )
