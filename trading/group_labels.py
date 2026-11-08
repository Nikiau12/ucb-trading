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

JOURNAL_COPY = {
    "ru": ("Идея для самостоятельной оценки", "Оценка условий: {score}% — не вероятность прибыли.",
           "Проверьте контекст рынка и решите сами, входить ли в сделку."),
    "en": ("Idea for your own review", "Setup score: {score}% — not a profit probability.",
           "Review market context and decide for yourself whether to enter."),
    "de": ("Idee zur eigenen Prüfung", "Setup-Bewertung: {score}% — keine Gewinnwahrscheinlichkeit.",
           "Prüfe den Marktkontext und entscheide selbst über den Einstieg."),
    "fr": ("Idée à évaluer vous-même", "Évaluation du setup : {score}% — pas une probabilité de gain.",
           "Évaluez le marché et décidez vous-même si vous entrez."),
    "es": ("Idea para evaluar", "Evaluación del setup: {score}% — no es probabilidad de beneficio.",
           "Evalúa el mercado y decide por tu cuenta si entras."),
}

JOURNAL_WARNINGS = {
    "ru": ("Дневной контекст против направления.", "Тренд BTC против направления.", "Ориентир базового актива не проверен."),
    "en": ("Daily context opposes this direction.", "BTC trend opposes this direction.", "Underlying-asset reference is unverified."),
    "de": ("Der Tageskontext spricht gegen diese Richtung.", "Der BTC-Trend spricht gegen diese Richtung.", "Referenz des Basiswerts ungeprüft."),
    "fr": ("Le contexte journalier s’oppose à cette direction.", "La tendance BTC s’y oppose.", "Référence de l’actif sous-jacent non vérifiée."),
    "es": ("El contexto diario va en contra de esta dirección.", "La tendencia de BTC va en contra.", "Referencia del activo subyacente no verificada."),
}

GROUP_SKIP_COPY = {
    "ru": {
        "long": "Лонг", "short": "Шорт",
        "daily_regime": "1Д: рыночный режим не подходит",
        "relative_strength_btc": "1Д: сила относительно BTC не подходит",
        "relative_strength_subtype": "1Д: сила относительно ориентира группы не подходит",
        "daily_trend_age": "1Д: возраст тренда вне условий",
        "late_trend_extension": "1Д: цена слишком далеко от тренда",
        "daily_volatility": "1Д: волатильность вне условий",
        "price_confirmation": "4Ч: вход и уровни не прошли проверку",
        "regime_changed_during_retest": "1Д: режим изменился при ретесте",
        "blocked_data": "данные не удалось проверить; сигнал не создан",
        "other": "условия групповой стратегии не выполнены",
        "history": "Для этой монеты пока мало полной истории 4Ч/1Д.",
        "unavailable": "Не удалось проверить рыночные данные; сигнал не публикуется.",
        "market": "Текущая ликвидность или стоимость входа не прошла проверку.",
        "expired": "Точка входа уже пройдена или время действия сетапа истекло.",
        "sizing": "План не проходит ограничения контракта или выбранного риска.",
    },
    "en": {
        "long": "Long", "short": "Short",
        "daily_regime": "1D: market regime does not qualify",
        "relative_strength_btc": "1D: strength versus BTC does not qualify",
        "relative_strength_subtype": "1D: strength versus the group benchmark does not qualify",
        "daily_trend_age": "1D: trend age is outside the rule",
        "late_trend_extension": "1D: price is too extended from the trend",
        "daily_volatility": "1D: volatility is outside the rule",
        "price_confirmation": "4H: entry and levels did not qualify",
        "regime_changed_during_retest": "1D: regime changed during the retest",
        "blocked_data": "market data could not be verified; no signal was created",
        "other": "the group strategy conditions were not met",
        "history": "This coin does not yet have enough complete 4H/1D history.",
        "unavailable": "Market data could not be verified; no signal was published.",
        "market": "Current liquidity or entry costs did not pass the check.",
        "expired": "The entry was already passed or the setup expired.",
        "sizing": "The plan does not meet contract or selected-risk limits.",
    },
    "de": {
        "long": "Long", "short": "Short",
        "daily_regime": "1D: Marktregime passt nicht",
        "relative_strength_btc": "1D: Stärke gegenüber BTC passt nicht",
        "relative_strength_subtype": "1D: Stärke gegenüber der Gruppenreferenz passt nicht",
        "daily_trend_age": "1D: Trendalter liegt außerhalb der Regel",
        "late_trend_extension": "1D: Kurs ist zu weit vom Trend entfernt",
        "daily_volatility": "1D: Volatilität liegt außerhalb der Regel",
        "price_confirmation": "4H: Einstieg und Levels erfüllen die Regeln nicht",
        "regime_changed_during_retest": "1D: Regime änderte sich beim Retest",
        "blocked_data": "Marktdaten nicht verifizierbar; kein Signal erstellt",
        "other": "Gruppenstrategie-Bedingungen nicht erfüllt",
        "history": "Für diesen Coin fehlt noch vollständige 4H/1D-Historie.",
        "unavailable": "Marktdaten nicht verifizierbar; kein Signal veröffentlicht.",
        "market": "Liquidität oder Einstiegskosten bestehen die Prüfung nicht.",
        "expired": "Einstieg bereits passiert oder Setup abgelaufen.",
        "sizing": "Plan überschreitet Vertrags- oder Risikolimits.",
    },
    "fr": {
        "long": "Long", "short": "Short",
        "daily_regime": "1J : régime de marché non conforme",
        "relative_strength_btc": "1J : force relative au BTC non conforme",
        "relative_strength_subtype": "1J : force relative à la référence du groupe non conforme",
        "daily_trend_age": "1J : âge de la tendance hors des règles",
        "late_trend_extension": "1J : prix trop éloigné de la tendance",
        "daily_volatility": "1J : volatilité hors des règles",
        "price_confirmation": "4H : entrée et niveaux non validés",
        "regime_changed_during_retest": "1J : régime modifié pendant le retest",
        "blocked_data": "données invérifiables ; aucun signal créé",
        "other": "conditions de la stratégie de groupe non remplies",
        "history": "Historique complet 4H/1J encore insuffisant pour cette monnaie.",
        "unavailable": "Données de marché invérifiables ; aucun signal publié.",
        "market": "Liquidité ou coût d’entrée non conformes.",
        "expired": "Entrée déjà dépassée ou setup expiré.",
        "sizing": "Plan hors des limites du contrat ou du risque choisi.",
    },
    "es": {
        "long": "Long", "short": "Short",
        "daily_regime": "1D: el régimen de mercado no cumple las reglas",
        "relative_strength_btc": "1D: la fuerza frente a BTC no cumple las reglas",
        "relative_strength_subtype": "1D: la fuerza frente a la referencia del grupo no cumple las reglas",
        "daily_trend_age": "1D: la edad de la tendencia queda fuera de las reglas",
        "late_trend_extension": "1D: el precio está demasiado extendido",
        "daily_volatility": "1D: la volatilidad queda fuera de las reglas",
        "price_confirmation": "4H: la entrada y los niveles no cumplen las reglas",
        "regime_changed_during_retest": "1D: el régimen cambió durante el retest",
        "blocked_data": "no se pudieron verificar los datos; no se creó señal",
        "other": "no se cumplen las condiciones de la estrategia del grupo",
        "history": "Esta moneda aún no tiene suficiente historial completo 4H/1D.",
        "unavailable": "No se pudieron verificar los datos del mercado; no se publicó señal.",
        "market": "La liquidez o el coste de entrada no superaron la revisión.",
        "expired": "La entrada ya pasó o el setup caducó.",
        "sizing": "El plan no cumple los límites del contrato o del riesgo elegido.",
    },
}


def group_decision_explanation(record, lang):
    """Explain both sides of a group decision without exposing raw filter codes."""
    if not (record.get("strategy") or {}).get("experimental"):
        return None
    decisions = record.get("direction_decisions")
    if not isinstance(decisions, list) or len(decisions) != 2:
        return None
    words = GROUP_SKIP_COPY.get(lang, GROUP_SKIP_COPY["en"])
    by_side = {item["side"]: item for item in decisions
               if isinstance(item, dict) and item.get("side") in ("long", "short")}
    if set(by_side) != {"long", "short"}:
        return None
    lines = []
    for side in ("long", "short"):
        item = by_side[side]
        status = item.get("status")
        if status not in ("no_setup", "blocked_data"):
            return None
        reason = "blocked_data" if status == "blocked_data" else item.get("reason")
        explanation = words.get(reason, words["other"]) if isinstance(reason, str) else words["other"]
        lines.append(f"{words[side]}: {explanation}")
    return "\n".join(lines)


def strategy_notice(record, lang, *, details=True):
    meta = record.get("strategy") or {}
    if not meta.get("experimental"):
        return ""
    if meta.get("mode") == "journal_idea":
        words = JOURNAL_COPY.get(lang, JOURNAL_COPY["en"])
        primary = record.get("primary") or {}
        score = round(100 * float(primary.get("confidence", record.get("confidence", 0))))
        lines = [words[0], words[1].format(score=score), words[2]]
        if details:
            criteria = meta.get("criteria") or {}
            warnings = JOURNAL_WARNINGS.get(lang, JOURNAL_WARNINGS["en"])
            if criteria.get("daily_close") is False:
                lines.append(warnings[0])
            if criteria.get("btc_context") is False:
                lines.append(warnings[1])
            if meta.get("group") == "rwa":
                lines.append(warnings[2])
            until = datetime.fromtimestamp(meta["entry_expires_at"], timezone.utc).strftime("%d.%m %H:%M")
            lines.insert(2, COPY.get(lang, COPY["en"])[2].format(
                until=until, hours=int(meta["max_holding_seconds"] / 3600)))
        return "\n" + "\n".join(html.escape(line) for line in lines)
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
    if not isinstance(reason, str):
        return None
    words = GROUP_SKIP_COPY.get(lang, GROUP_SKIP_COPY["en"])
    if reason == "group_data_rejected:insufficient_group_history":
        return words["history"]
    if reason.startswith(("group_data_unavailable:", "group_data_rejected:")) or reason == "group_market_unavailable":
        return words["unavailable"]
    if reason.startswith("group_no_setup:"):
        return words["other"]
    if reason in ("group_liquidity_turnover", "group_spread", "group_depth",
                  "group_depth_notional", "group_price_impact", "group_estimated_fee_impact_cost"):
        return words["market"]
    if reason in ("group_trigger_already_used_or_invalidated", "group_setup_expired"):
        return words["expired"]
    if reason.startswith("group_sizing:"):
        return words["sizing"]
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
