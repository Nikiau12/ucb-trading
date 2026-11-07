"""User-facing disclosure for versioned, not-yet-validated group rules."""
import html
from datetime import datetime, timezone

COPY = {
    "ru": ("Экспериментальная стратегия", "Вход по пробою уровня (STOP), не лимитный ордер",
           "Вход до {until} UTC · удержание до {hours} ч",
           "Прибыльность не подтверждена; это не вероятность успеха.",
           "До подтверждённого входа достигнут уровень отмены или порядок касаний не определён."),
    "en": ("Experimental strategy", "Enter on a level breakout (STOP), not a limit order",
           "Entry valid until {until} UTC · hold up to {hours} h",
           "Profitability is unverified; this is not a success probability.",
           "An invalidation level was reached before confirmed entry, or touch order is unknown."),
    "de": ("Experimentelle Strategie", "Einstieg beim Ausbruch (STOP), keine Limit-Order",
           "Einstieg bis {until} UTC · Haltedauer bis {hours} Std.",
           "Profitabilität unbestätigt; keine Erfolgswahrscheinlichkeit.",
           "Ungültigkeitsniveau vor bestätigtem Einstieg erreicht oder Reihenfolge unklar."),
    "fr": ("Stratégie expérimentale", "Entrée à la cassure (STOP), pas un ordre limite",
           "Entrée valable jusqu’à {until} UTC · durée maximale {hours} h",
           "Rentabilité non validée ; ce n’est pas une probabilité de réussite.",
           "Niveau d’invalidation atteint avant l’entrée confirmée ou ordre des contacts inconnu."),
    "es": ("Estrategia experimental", "Entrada por ruptura (STOP), no una orden límite",
           "Entrada válida hasta {until} UTC · duración máxima {hours} h",
           "Rentabilidad no validada; no es una probabilidad de éxito.",
           "Se alcanzó un nivel de invalidación antes de confirmar la entrada o el orden es incierto."),
}


def strategy_notice(record, lang, *, details=True):
    meta = record.get("strategy") or {}
    if not meta.get("experimental"):
        return ""
    words = COPY.get(lang, COPY["en"])
    lines = [words[0], words[3]]
    if details:
        lines.insert(1, words[1])
        until = datetime.fromtimestamp(meta["entry_expires_at"], timezone.utc).strftime("%d.%m %H:%M")
        lines.insert(2, words[2].format(until=until, hours=int(meta["max_holding_seconds"]/3600)))
    return "\n" + "\n".join(html.escape(line) for line in lines)


def cancellation_reason(signal, lang, legacy):
    if (signal.get("strategy") or {}).get("entry_type") == "stop":
        return COPY.get(lang, COPY["en"])[4]
    return legacy


def skip_explanation(lang, reason):
    if reason == "unclassified_symbol_no_group_fallback":
        return {
            "ru":"Для этой монеты пока не зафиксирована групповая стратегия.",
            "en":"No group strategy is registered for this coin yet.",
            "de":"Für diesen Coin ist noch keine Gruppenstrategie registriert.",
            "fr":"Aucune stratégie de groupe n’est encore définie pour cette monnaie.",
            "es":"Aún no hay una estrategia de grupo registrada para esta moneda.",
        }.get(lang, "No group strategy is registered for this coin yet.")
    if reason == "group_signal_not_saved":
        return {
            "ru":"Новый сетап не опубликован: уже есть открытая сделка, условия изменились или запись недоступна. Проверьте историю сигналов.",
            "en":"No new setup published: a trade is already open, conditions changed or storage is unavailable. Check signal history.",
            "de":"Kein neues Setup: Trade bereits offen, Bedingungen geändert oder Speicherung nicht verfügbar. Prüfe den Signalverlauf.",
            "fr":"Pas de nouveau setup : position déjà ouverte, conditions modifiées ou sauvegarde indisponible. Consultez l’historique.",
            "es":"No hay nuevo setup: operación abierta, condiciones modificadas o guardado no disponible. Revisa el historial.",
        }.get(lang, "Setup unavailable. Check signal history.")
    return None
