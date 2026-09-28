from __future__ import annotations
from typing import Any

LANG_BUTTONS = [
    ("🇷🇺 Русский",  "lang_ru"),
    ("🇬🇧 English",  "lang_en"),
    ("🇩🇪 Deutsch",  "lang_de"),
    ("🇫🇷 Français", "lang_fr"),
    ("🇪🇸 Español",  "lang_es"),
]

STRINGS: dict[str, dict[str, Any]] = {

    # ─────────────────────────── RUSSIAN ───────────────────────────
    "ru": {
        "welcome": (
            "👋 Добро пожаловать в <b>UCB_TRADING_BOT</b>\n\n"
            "Я сканирую MEXC Futures 24/7, нахожу сильные сетапы и мгновенно рассчитываю "
            "точку входа, стоп-лосс, два тейк-профита и размер позиции — "
            "с учётом твоего депозита и риск-профиля.\n\n"
            "🌐 Выбери язык:"
        ),
        "lang_set": "✅ Язык установлен: <b>Русский</b>\n\nПечатай /help — покажу все команды.",
        "choose_lang": "🌐 Выбери язык:",
        "deposit_button": "💰 Указать депозит",
        "mini_app_button": "📊 Открыть панель",
        "deposit_start_hint": (
            "Укажи депозит сейчас, чтобы бот рассчитывал размер позиции и риск именно для тебя. "
            "До этого планы, сканирование и автоматические сигналы недоступны."
        ),
        "deposit_prompt": "💰 Отправь сумму депозита одним числом, например: <code>5000</code>",
        "deposit_saved": (
            "✅ Депозит сохранён: <b>{deposit} USDT</b>\n\n"
            "Нажми /plan для плана по BTC или отправь /plan ETH_USDT для другой монеты."
        ),
        "deposit_invalid": "❌ Отправь положительное число, например: <code>5000</code>",
        "scan_reference_deposit": (
            "ℹ️ Депозит пока не указан. /scan всё равно запустится, но размеры позиции будут "
            "рассчитаны на примере <b>{deposit} USDT</b>."
        ),
        "help": (
            "📋 <b>UCB_TRADING_BOT — Справочник</b>\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "📌 <b>ПЛАНЫ</b>\n"
            "/plan\n"
            "   → план по BTC с сохранённым депозитом\n"
            "/plan BTC_USDT\n"
            "   → план с твоими сохранёнными параметрами\n"
            "/plan ETH_USDT lev=10 risk=2\n"
            "   → переопределить параметры для одного запроса\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "🔍 <b>СКАНИРОВАНИЕ</b>\n"
            "/scan — скан топ-{top_n} монет (~2–4 мин)\n"
            "   → только сетапы выше порога уверенности\n\n"
            "📊 <b>ДАЙДЖЕСТ</b>\n"
            "/digest — полный обзор рынка прямо сейчас\n"
            "   → высокая / средняя уверенность + скип\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "🔐 <b>ПОДПИСКА</b>\n"
            "/subscribe — инструкция по оплате USDT TRC20\n"
            "/paid TX_HASH — подтвердить оплату\n"
            "/status — статус доступа\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "⚙️ <b>ТВОИ ПАРАМЕТРЫ</b>\n"
            "/settings — посмотреть текущие параметры\n\n"
            "/set deposit=5000    — твой депозит для расчёта позиции\n"
            "/set risk=1          — % риска на сделку (по умолч. 1%)\n"
            "/set lev=20          — кредитное плечо (по умолч. 10x)\n"
            "/set margin=isolated — тип маржи (по умолч. cross)\n\n"
            "Можно сразу несколько:\n"
            "<code>/set deposit=5000 risk=1.5 lev=15</code>\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "📖 <b>ЧТО ЗНАЧИТ ПЛАН</b>\n"
            "<code>entry</code>   — цена входа (лимитный ордер)\n"
            "<code>stop</code>    — стоп-лосс\n"
            "<code>tp1/tp2</code> — тейк-профиты (по 50% позиции)\n"
            "<code>conf</code>    — уверенность алгоритма (0.0–1.0)\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "🕐 <b>РАСПИСАНИЕ (UTC)</b>\n"
            "Автосканирование: 00:05 / 04:05 / 08:05\n"
            "                  12:05 / 16:05 / 20:05\n"
            "Дайджест: {digest_hour}:00 ежедневно\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "⚠️ <b>ВАЖНО</b>\n"
            "Бот предоставляет аналитику, а не торговые сигналы.\n"
            "Решение о входе в сделку всегда остаётся за тобой.\n\n"
            "🌐 Сменить язык → /start"
        ),
        "no_deposit": (
            "⚠️ Депозит не установлен.\n\n"
            "Укажи свой депозит один раз:\n"
            "<code>/set deposit=5000</code>\n\n"
            "Бот запомнит — больше вводить не нужно."
        ),
        "set_usage": (
            "Использование:\n"
            "<code>/set deposit=5000</code>\n"
            "<code>/set risk=1.5</code>\n"
            "<code>/set lev=20</code>\n"
            "<code>/set deposit=5000 risk=1 lev=20</code>"
        ),
        "set_saved":       "✅ Сохранено: {params}",
        "set_unknown":     "❌ Неизвестный параметр: {key}. Доступны: deposit, risk, lev, margin",
        "settings_title":  "⚙️ <b>Твои параметры</b>\n\n",
        "settings_deposit":"💰 deposit: {val}\n",
        "settings_deposit_missing": "💰 deposit: <b>⚠️ не установлен</b> → <code>/set deposit=XXXX</code>\n",
        "settings_risk":   "🎯 risk: <b>{val}%</b>\n",
        "settings_lev":    "🧰 lev: <b>{val}x</b>\n",
        "settings_margin": "📐 margin: <b>{val}</b>\n\n",
        "settings_change": "Изменить: <code>/set deposit=X risk=X lev=X</code>",
        "deposit_not_set": "⚠️ не установлен → /set deposit=XXXX",
        "plan_loading":    "⏳ Загружаю {symbol}...",
        "plan_error":      "❌ Ошибка: {error}",
        "plan_usage": (
            "Использование:\n"
            "<code>/plan</code> — BTC\n"
            "<code>/plan ETH_USDT</code> — другая монета\n"
            "<code>/plan ETH_USDT lev=20 risk=1</code> — разовые настройки\n\n"
            "Депозит берётся из сохранённых настроек. Изменить: <code>/set deposit=5000</code>"
        ),
        "scan_starting":   "🔍 Сканирую топ-{top_n} монет (~2–4 мин)...",
        "scan_done":       "✅ Найдено {count} сетап(ов). Топ-5:",
        "scan_none":       "🧊 Нет сетапов выше порога уверенности",
        "scan_more":       "...и ещё {count}. Используй /digest для полного обзора.",
        "scan_error":      "❌ Ошибка сканирования: {error}",
        "digest_preparing":"📊 Готовлю дайджест...",
        "digest_title":    "📊 <b>Дайджест {time} UTC</b>\nПроверено: <b>{total}</b> монет",
        "digest_high":     "🟢 <b>Высокая уверенность ≥0.65 — {count} шт.</b>",
        "digest_medium":   "🟡 <b>Средняя уверенность 0.50–0.65 — {count} шт.</b>",
        "digest_skipped":  "🧊 Нет сетапа: <b>{count}</b> монет",
        "digest_error":    "❌ Ошибка дайджеста: {error}",
        "autoscan_error":  "⚠️ Ошибка автосканирования: {error}",
        # plan render labels
        "r_context":       "🧠 Контекст",
        "r_plan":          "план",
        "r_price":         "💵 Цена",
        "r_profile":       "🧷 Профиль",
        "r_deposit":       "💰 депозит",
        "r_risk":          "🎯 риск",
        "r_lev":           "🧰 плечо",
        "r_regime":        "🧭 Режим рынка",
        "r_trend_1d":      "trend 1D",
        "r_trend_4h":      "4H",
        "r_struct":        "структура 4H",
        "r_bos":           "BOS/CHOCH",
        "r_regime_label":  "режим",
        "r_mid":           "midrange",
        "r_scenario":      "Сценарий",
        "r_confidence":    "уверенность",
        "r_entry":         "🎯 entry",
        "r_stop":          "🛑 stop",
        "r_tp1":           "🥅 tp1",
        "r_tp2":           "🥅 tp2",
        "r_size":          "📦 Размер",
        "r_qty":           "кол-во",
        "r_risk_label":    "риск",
        "r_margin_need":   "маржа",
        "r_levels":        "🧱 Уровни",
        "r_support":       "🟩 поддержка",
        "r_resistance":    "🟥 сопротивление",
        "r_why":           "🔍 Почему",
        "r_risk_rule":     "🚨 Риск-правило",
        "r_risk_text":     "<b>CROSS + плечо — без стопа нельзя.</b> Стоп обязателен.",
        "r_skip_conf":     "🧊 Уверенность",
        "r_skip_reason":   "🔍 Причины",
        "r_cache_warn":    "⚠️<i>кэш</i>",
    },

    # ─────────────────────────── ENGLISH ───────────────────────────
    "en": {
        "welcome": (
            "👋 Welcome to <b>UCB_TRADING_BOT</b>\n\n"
            "I scan MEXC Futures 24/7, find high-probability setups and instantly calculate "
            "entry, stop-loss, two take-profits and position size — "
            "calibrated to your deposit and risk tolerance.\n\n"
            "🌐 Choose your language:"
        ),
        "lang_set": "✅ Language set: <b>English</b>\n\nType /help to see all commands.",
        "choose_lang": "🌐 Choose your language:",
        "deposit_button": "💰 Set deposit",
        "mini_app_button": "📊 Open dashboard",
        "deposit_start_hint": (
            "Set your deposit now so position size and risk can be calculated for you. "
            "The deposit is required before plans, scans and automatic signals are available."
        ),
        "deposit_prompt": "💰 Send your deposit as a number, for example: <code>5000</code>",
        "deposit_saved": (
            "✅ Deposit saved: <b>{deposit} USDT</b>\n\n"
            "Tap /plan for a BTC plan or send /plan ETH_USDT for another coin."
        ),
        "deposit_invalid": "❌ Send a positive number, for example: <code>5000</code>",
        "scan_reference_deposit": (
            "ℹ️ Your deposit is not set yet. /scan will still run, but position sizes will be "
            "calculated using a <b>{deposit} USDT</b> reference deposit."
        ),
        "help": (
            "📋 <b>UCB_TRADING_BOT — Commands</b>\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "📌 <b>PLANS</b>\n"
            "/plan\n"
            "   → BTC plan using your saved deposit\n"
            "/plan BTC_USDT\n"
            "   → plan with your saved parameters\n"
            "/plan ETH_USDT lev=10 risk=2\n"
            "   → override parameters for one request\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "🔍 <b>SCAN</b>\n"
            "/scan — scan top-{top_n} coins (~2–4 min)\n"
            "   → shows only setups above confidence threshold\n\n"
            "📊 <b>DIGEST</b>\n"
            "/digest — full market overview right now\n"
            "   → high / medium confidence + skipped\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "🔐 <b>SUBSCRIPTION</b>\n"
            "/subscribe — USDT TRC20 payment instructions\n"
            "/paid TX_HASH — confirm payment\n"
            "/status — access status\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "⚙️ <b>YOUR PARAMETERS</b>\n"
            "/settings — view your current parameters\n\n"
            "/set deposit=5000    — your deposit for position sizing\n"
            "/set risk=1          — % risk per trade (default 1%)\n"
            "/set lev=20          — leverage (default 10x)\n"
            "/set margin=isolated — margin type (default cross)\n\n"
            "Multiple at once:\n"
            "<code>/set deposit=5000 risk=1.5 lev=15</code>\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "📖 <b>WHAT THE PLAN MEANS</b>\n"
            "<code>entry</code>   — entry price (limit order)\n"
            "<code>stop</code>    — stop-loss\n"
            "<code>tp1/tp2</code> — take-profits (50% of position each)\n"
            "<code>conf</code>    — algorithm confidence (0.0–1.0)\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "🕐 <b>SCHEDULE (UTC)</b>\n"
            "Auto-scan: 00:05 / 04:05 / 08:05\n"
            "           12:05 / 16:05 / 20:05\n"
            "Digest: {digest_hour}:00 daily\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "⚠️ <b>DISCLAIMER</b>\n"
            "The bot provides analytics, not trading signals.\n"
            "The decision to enter a trade is always yours.\n\n"
            "🌐 Change language → /start"
        ),
        "no_deposit": (
            "⚠️ <b>Deposit required</b>\n\n"
            "Tap the button below and send your trading deposit as one number.\n"
            "Example: <code>5000</code>\n\n"
            "The bot saves it and uses it for every position calculation."
        ),
        "set_usage": (
            "Usage:\n"
            "<code>/set deposit=5000</code>\n"
            "<code>/set risk=1.5</code>\n"
            "<code>/set lev=20</code>\n"
            "<code>/set deposit=5000 risk=1 lev=20</code>"
        ),
        "set_saved":       "✅ Saved: {params}",
        "set_unknown":     "❌ Unknown parameter: {key}. Allowed: deposit, risk, lev, margin",
        "settings_title":  "⚙️ <b>Your settings</b>\n\n",
        "settings_deposit":"💰 deposit: {val}\n",
        "settings_deposit_missing": "💰 deposit: <b>⚠️ not set</b> → <code>/set deposit=XXXX</code>\n",
        "settings_risk":   "🎯 risk: <b>{val}%</b>\n",
        "settings_lev":    "🧰 lev: <b>{val}x</b>\n",
        "settings_margin": "📐 margin: <b>{val}</b>\n\n",
        "settings_change": "Change: <code>/set deposit=X risk=X lev=X</code>",
        "deposit_not_set": "⚠️ not set → /set deposit=XXXX",
        "plan_loading":    "⏳ Loading {symbol}...",
        "plan_error":      "❌ Error: {error}",
        "plan_usage": (
            "Usage:\n"
            "<code>/plan</code> — BTC\n"
            "<code>/plan ETH_USDT</code> — another coin\n"
            "<code>/plan ETH_USDT lev=20 risk=1</code> — one-time settings\n\n"
            "Your saved deposit is always used. Change it with <code>/set deposit=5000</code>."
        ),
        "scan_starting":   "🔍 Scanning top-{top_n} coins (~2–4 min)...",
        "scan_done":       "✅ Found {count} setup(s). Top 5:",
        "scan_none":       "🧊 No setups above confidence threshold",
        "scan_more":       "...and {count} more. Use /digest for a full overview.",
        "scan_error":      "❌ Scan error: {error}",
        "digest_preparing":"📊 Preparing digest...",
        "digest_title":    "📊 <b>Digest {time} UTC</b>\nChecked: <b>{total}</b> coins",
        "digest_high":     "🟢 <b>High confidence ≥0.65 — {count} setup(s)</b>",
        "digest_medium":   "🟡 <b>Medium confidence 0.50–0.65 — {count} setup(s)</b>",
        "digest_skipped":  "🧊 No setup: <b>{count}</b> coins",
        "digest_error":    "❌ Digest error: {error}",
        "autoscan_error":  "⚠️ Auto-scan error: {error}",
        "r_context":       "🧠 Context",
        "r_plan":          "plan",
        "r_price":         "💵 Price",
        "r_profile":       "🧷 Profile",
        "r_deposit":       "💰 deposit",
        "r_risk":          "🎯 risk",
        "r_lev":           "🧰 leverage",
        "r_regime":        "🧭 Market regime",
        "r_trend_1d":      "trend 1D",
        "r_trend_4h":      "4H",
        "r_struct":        "structure 4H",
        "r_bos":           "BOS/CHOCH",
        "r_regime_label":  "regime",
        "r_mid":           "midrange",
        "r_scenario":      "Scenario",
        "r_confidence":    "confidence",
        "r_entry":         "🎯 entry",
        "r_stop":          "🛑 stop",
        "r_tp1":           "🥅 tp1",
        "r_tp2":           "🥅 tp2",
        "r_size":          "📦 Size",
        "r_qty":           "qty",
        "r_risk_label":    "risk",
        "r_margin_need":   "margin",
        "r_levels":        "🧱 Levels",
        "r_support":       "🟩 support",
        "r_resistance":    "🟥 resistance",
        "r_why":           "🔍 Why",
        "r_risk_rule":     "🚨 Risk rule",
        "r_risk_text":     "<b>CROSS + leverage — stop-loss is mandatory.</b>",
        "r_skip_conf":     "🧊 Confidence",
        "r_skip_reason":   "🔍 Reasons",
        "r_cache_warn":    "⚠️<i>cache</i>",
    },

    # ─────────────────────────── GERMAN ───────────────────────────
    "de": {
        "welcome": (
            "👋 Hallo! Ich bin <b>UCB_TRADING_BOT</b>\n\n"
            "Dein Trading-Assistent für MEXC Futures.\n"
            "Ich analysiere den Markt auf 4h- und 1d-Kerzen, finde Setups\n"
            "und erstelle Pläne: Einstieg, Stop-Loss, zwei TPs und Positionsgröße.\n\n"
            "🌐 Wähle deine Sprache:"
        ),
        "lang_set": "✅ Sprache gesetzt: <b>Deutsch</b>\n\nTippe /help für alle Befehle.",
        "choose_lang": "🌐 Wähle deine Sprache:",
        "deposit_button": "💰 Kapital festlegen",
        "mini_app_button": "📊 Dashboard öffnen",
        "deposit_start_hint": (
            "Lege dein Kapital jetzt fest, damit Positionsgröße und Risiko für dich berechnet werden. "
            "Pläne, Scans und automatische Signale sind erst danach verfügbar."
        ),
        "deposit_prompt": "💰 Sende dein Kapital als Zahl, zum Beispiel: <code>5000</code>",
        "deposit_saved": (
            "✅ Kapital gespeichert: <b>{deposit} USDT</b>\n\n"
            "Tippe /plan für BTC oder sende /plan ETH_USDT für einen anderen Coin."
        ),
        "deposit_invalid": "❌ Sende eine positive Zahl, zum Beispiel: <code>5000</code>",
        "scan_reference_deposit": (
            "ℹ️ Dein Kapital ist noch nicht festgelegt. /scan läuft trotzdem; Positionsgrößen werden "
            "mit einem Referenzwert von <b>{deposit} USDT</b> berechnet."
        ),
        "help": (
            "📋 <b>UCB_TRADING_BOT — Befehle</b>\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "📌 <b>PLÄNE</b>\n"
            "/plan\n"
            "   → BTC-Plan mit deinem gespeicherten Kapital\n"
            "/plan BTC_USDT\n"
            "   → Plan mit deinen gespeicherten Parametern\n"
            "/plan ETH_USDT lev=10 risk=2\n"
            "   → Parameter für eine Anfrage überschreiben\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "🔍 <b>SCAN</b>\n"
            "/scan — Top-{top_n} Coins scannen (~2–4 Min)\n"
            "   → nur Setups über dem Konfidenzschwellenwert\n\n"
            "📊 <b>DIGEST</b>\n"
            "/digest — vollständige Marktübersicht jetzt\n"
            "   → hohe / mittlere Konfidenz + übersprungen\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "🔐 <b>ABONNEMENT</b>\n"
            "/subscribe — USDT-TRC20-Zahlungsanleitung\n"
            "/paid TX_HASH — Zahlung bestätigen\n"
            "/status — Zugangsstatus\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "⚙️ <b>DEINE PARAMETER</b>\n"
            "/settings — aktuelle Parameter anzeigen\n\n"
            "/set deposit=5000    — dein Kapital für die Positionsgröße\n"
            "/set risk=1          — Risiko-% pro Trade (Standard 1%)\n"
            "/set lev=20          — Hebel (Standard 10x)\n"
            "/set margin=isolated — Margin-Typ (Standard cross)\n\n"
            "Mehrere gleichzeitig:\n"
            "<code>/set deposit=5000 risk=1.5 lev=15</code>\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "📖 <b>WAS DER PLAN BEDEUTET</b>\n"
            "<code>entry</code>   — Einstiegskurs (Limit-Order)\n"
            "<code>stop</code>    — Stop-Loss\n"
            "<code>tp1/tp2</code> — Take-Profits (je 50 % der Position)\n"
            "<code>conf</code>    — Algorithmus-Konfidenz (0.0–1.0)\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "🕐 <b>ZEITPLAN (UTC)</b>\n"
            "Auto-Scan: 00:05 / 04:05 / 08:05\n"
            "           12:05 / 16:05 / 20:05\n"
            "Digest: {digest_hour}:00 täglich\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "⚠️ <b>HINWEIS</b>\n"
            "Der Bot liefert Analysen, keine Handelssignale.\n"
            "Die Entscheidung zum Handeln liegt immer bei dir.\n\n"
            "🌐 Sprache ändern → /start"
        ),
        "no_deposit": (
            "⚠️ Kapital nicht festgelegt.\n\n"
            "Lege dein Kapital einmalig fest:\n"
            "<code>/set deposit=5000</code>\n\n"
            "Der Bot merkt es sich — du musst es nicht erneut eingeben."
        ),
        "set_usage": (
            "Verwendung:\n"
            "<code>/set deposit=5000</code>\n"
            "<code>/set risk=1.5</code>\n"
            "<code>/set lev=20</code>\n"
            "<code>/set deposit=5000 risk=1 lev=20</code>"
        ),
        "set_saved":       "✅ Gespeichert: {params}",
        "set_unknown":     "❌ Unbekannter Parameter: {key}. Erlaubt: deposit, risk, lev, margin",
        "settings_title":  "⚙️ <b>Deine Parameter</b>\n\n",
        "settings_deposit":"💰 deposit: {val}\n",
        "settings_deposit_missing": "💰 deposit: <b>⚠️ nicht festgelegt</b> → <code>/set deposit=XXXX</code>\n",
        "settings_risk":   "🎯 risk: <b>{val}%</b>\n",
        "settings_lev":    "🧰 lev: <b>{val}x</b>\n",
        "settings_margin": "📐 margin: <b>{val}</b>\n\n",
        "settings_change": "Ändern: <code>/set deposit=X risk=X lev=X</code>",
        "deposit_not_set": "⚠️ nicht festgelegt → /set deposit=XXXX",
        "plan_loading":    "⏳ Lade {symbol}...",
        "plan_error":      "❌ Fehler: {error}",
        "plan_usage": (
            "Verwendung:\n"
            "<code>/plan</code> — BTC\n"
            "<code>/plan ETH_USDT</code> — anderer Coin\n"
            "<code>/plan ETH_USDT lev=20 risk=1</code> — einmalige Einstellungen\n\n"
            "Das gespeicherte Kapital wird immer verwendet. Ändern: <code>/set deposit=5000</code>"
        ),
        "scan_starting":   "🔍 Scanne Top-{top_n} Coins (~2–4 Min)...",
        "scan_done":       "✅ {count} Setup(s) gefunden. Top 5:",
        "scan_none":       "🧊 Keine Setups über dem Schwellenwert",
        "scan_more":       "...und {count} weitere. Nutze /digest für eine vollständige Übersicht.",
        "scan_error":      "❌ Scan-Fehler: {error}",
        "digest_preparing":"📊 Digest wird vorbereitet...",
        "digest_title":    "📊 <b>Digest {time} UTC</b>\nGeprüft: <b>{total}</b> Coins",
        "digest_high":     "🟢 <b>Hohe Konfidenz ≥0.65 — {count} Setup(s)</b>",
        "digest_medium":   "🟡 <b>Mittlere Konfidenz 0.50–0.65 — {count} Setup(s)</b>",
        "digest_skipped":  "🧊 Kein Setup: <b>{count}</b> Coins",
        "digest_error":    "❌ Digest-Fehler: {error}",
        "autoscan_error":  "⚠️ Auto-Scan-Fehler: {error}",
        "r_context":       "🧠 Kontext",
        "r_plan":          "Plan",
        "r_price":         "💵 Kurs",
        "r_profile":       "🧷 Profil",
        "r_deposit":       "💰 Kapital",
        "r_risk":          "🎯 Risiko",
        "r_lev":           "🧰 Hebel",
        "r_regime":        "🧭 Marktlage",
        "r_trend_1d":      "Trend 1D",
        "r_trend_4h":      "4H",
        "r_struct":        "Struktur 4H",
        "r_bos":           "BOS/CHOCH",
        "r_regime_label":  "Regime",
        "r_mid":           "Midrange",
        "r_scenario":      "Szenario",
        "r_confidence":    "Konfidenz",
        "r_entry":         "🎯 Einstieg",
        "r_stop":          "🛑 Stop",
        "r_tp1":           "🥅 TP1",
        "r_tp2":           "🥅 TP2",
        "r_size":          "📦 Größe",
        "r_qty":           "Menge",
        "r_risk_label":    "Risiko",
        "r_margin_need":   "Margin",
        "r_levels":        "🧱 Levels",
        "r_support":       "🟩 Unterstützung",
        "r_resistance":    "🟥 Widerstand",
        "r_why":           "🔍 Begründung",
        "r_risk_rule":     "🚨 Risikoregel",
        "r_risk_text":     "<b>CROSS + Hebel — Stop-Loss ist Pflicht.</b>",
        "r_skip_conf":     "🧊 Konfidenz",
        "r_skip_reason":   "🔍 Gründe",
        "r_cache_warn":    "⚠️<i>Cache</i>",
    },

    # ─────────────────────────── FRENCH ───────────────────────────
    "fr": {
        "welcome": (
            "👋 Bonjour ! Je suis <b>UCB_TRADING_BOT</b>\n\n"
            "Ton assistant de trading pour MEXC Futures.\n"
            "J'analyse le marché sur les bougies 4h et 1d, trouve des setups\n"
            "et crée des plans : entrée, stop-loss, deux TP et taille de position.\n\n"
            "🌐 Choisis ta langue :"
        ),
        "lang_set": "✅ Langue définie : <b>Français</b>\n\nTape /help pour voir toutes les commandes.",
        "choose_lang": "🌐 Choisis ta langue :",
        "deposit_button": "💰 Définir le dépôt",
        "mini_app_button": "📊 Ouvrir le tableau de bord",
        "deposit_start_hint": (
            "Indique ton dépôt pour calculer la taille de position et le risque selon ton capital. "
            "Les plans, scans et signaux automatiques seront disponibles ensuite."
        ),
        "deposit_prompt": "💰 Envoie ton dépôt sous forme de nombre, par exemple : <code>5000</code>",
        "deposit_saved": (
            "✅ Dépôt enregistré : <b>{deposit} USDT</b>\n\n"
            "Appuie sur /plan pour BTC ou envoie /plan ETH_USDT pour une autre monnaie."
        ),
        "deposit_invalid": "❌ Envoie un nombre positif, par exemple : <code>5000</code>",
        "scan_reference_deposit": (
            "ℹ️ Ton dépôt n'est pas encore défini. /scan fonctionnera quand même, mais les tailles "
            "seront calculées avec une référence de <b>{deposit} USDT</b>."
        ),
        "help": (
            "📋 <b>UCB_TRADING_BOT — Commandes</b>\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "📌 <b>PLANS</b>\n"
            "/plan\n"
            "   → plan BTC avec ton dépôt enregistré\n"
            "/plan BTC_USDT\n"
            "   → plan avec tes paramètres sauvegardés\n"
            "/plan ETH_USDT lev=10 risk=2\n"
            "   → remplacer les paramètres pour une requête\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "🔍 <b>SCAN</b>\n"
            "/scan — scanner le top {top_n} (~2–4 min)\n"
            "   → uniquement les setups au-dessus du seuil\n\n"
            "📊 <b>DIGEST</b>\n"
            "/digest — vue d'ensemble du marché maintenant\n"
            "   → haute / moyenne confiance + ignorés\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "🔐 <b>ABONNEMENT</b>\n"
            "/subscribe — instructions de paiement USDT TRC20\n"
            "/paid TX_HASH — confirmer le paiement\n"
            "/status — statut d'accès\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "⚙️ <b>TES PARAMÈTRES</b>\n"
            "/settings — voir tes paramètres actuels\n\n"
            "/set deposit=5000    — ton dépôt pour calculer la position\n"
            "/set risk=1          — % de risque par trade (défaut 1%)\n"
            "/set lev=20          — levier (défaut 10x)\n"
            "/set margin=isolated — type de marge (défaut cross)\n\n"
            "Plusieurs à la fois :\n"
            "<code>/set deposit=5000 risk=1.5 lev=15</code>\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "📖 <b>CE QUE SIGNIFIE LE PLAN</b>\n"
            "<code>entry</code>   — prix d'entrée (ordre limite)\n"
            "<code>stop</code>    — stop-loss\n"
            "<code>tp1/tp2</code> — take-profits (50 % de la position chacun)\n"
            "<code>conf</code>    — confiance de l'algorithme (0.0–1.0)\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "🕐 <b>PLANNING (UTC)</b>\n"
            "Scan auto : 00:05 / 04:05 / 08:05\n"
            "            12:05 / 16:05 / 20:05\n"
            "Digest : {digest_hour}:00 quotidiennement\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "⚠️ <b>AVERTISSEMENT</b>\n"
            "Le bot fournit des analyses, pas des signaux de trading.\n"
            "La décision d'entrer en position reste toujours la tienne.\n\n"
            "🌐 Changer de langue → /start"
        ),
        "no_deposit": (
            "⚠️ Dépôt non défini.\n\n"
            "Définis ton dépôt une seule fois :\n"
            "<code>/set deposit=5000</code>\n\n"
            "Le bot s'en souviendra — pas besoin de le ressaisir."
        ),
        "set_usage": (
            "Utilisation :\n"
            "<code>/set deposit=5000</code>\n"
            "<code>/set risk=1.5</code>\n"
            "<code>/set lev=20</code>\n"
            "<code>/set deposit=5000 risk=1 lev=20</code>"
        ),
        "set_saved":       "✅ Sauvegardé : {params}",
        "set_unknown":     "❌ Paramètre inconnu : {key}. Autorisés : deposit, risk, lev, margin",
        "settings_title":  "⚙️ <b>Tes paramètres</b>\n\n",
        "settings_deposit":"💰 deposit : {val}\n",
        "settings_deposit_missing": "💰 deposit : <b>⚠️ non défini</b> → <code>/set deposit=XXXX</code>\n",
        "settings_risk":   "🎯 risk : <b>{val}%</b>\n",
        "settings_lev":    "🧰 lev : <b>{val}x</b>\n",
        "settings_margin": "📐 margin : <b>{val}</b>\n\n",
        "settings_change": "Modifier : <code>/set deposit=X risk=X lev=X</code>",
        "deposit_not_set": "⚠️ non défini → /set deposit=XXXX",
        "plan_loading":    "⏳ Chargement de {symbol}...",
        "plan_error":      "❌ Erreur : {error}",
        "plan_usage": (
            "Utilisation :\n"
            "<code>/plan</code> — BTC\n"
            "<code>/plan ETH_USDT</code> — autre monnaie\n"
            "<code>/plan ETH_USDT lev=20 risk=1</code> — réglages temporaires\n\n"
            "Le dépôt enregistré est toujours utilisé. Modifier : <code>/set deposit=5000</code>"
        ),
        "scan_starting":   "🔍 Scan du top {top_n} en cours (~2–4 min)...",
        "scan_done":       "✅ {count} setup(s) trouvé(s). Top 5 :",
        "scan_none":       "🧊 Aucun setup au-dessus du seuil de confiance",
        "scan_more":       "...et {count} de plus. Utilise /digest pour une vue complète.",
        "scan_error":      "❌ Erreur de scan : {error}",
        "digest_preparing":"📊 Préparation du digest...",
        "digest_title":    "📊 <b>Digest {time} UTC</b>\nVérifié : <b>{total}</b> coins",
        "digest_high":     "🟢 <b>Haute confiance ≥0.65 — {count} setup(s)</b>",
        "digest_medium":   "🟡 <b>Confiance moyenne 0.50–0.65 — {count} setup(s)</b>",
        "digest_skipped":  "🧊 Pas de setup : <b>{count}</b> coins",
        "digest_error":    "❌ Erreur digest : {error}",
        "autoscan_error":  "⚠️ Erreur scan auto : {error}",
        "r_context":       "🧠 Contexte",
        "r_plan":          "plan",
        "r_price":         "💵 Prix",
        "r_profile":       "🧷 Profil",
        "r_deposit":       "💰 dépôt",
        "r_risk":          "🎯 risque",
        "r_lev":           "🧰 levier",
        "r_regime":        "🧭 Régime de marché",
        "r_trend_1d":      "tendance 1D",
        "r_trend_4h":      "4H",
        "r_struct":        "structure 4H",
        "r_bos":           "BOS/CHOCH",
        "r_regime_label":  "régime",
        "r_mid":           "midrange",
        "r_scenario":      "Scénario",
        "r_confidence":    "confiance",
        "r_entry":         "🎯 entrée",
        "r_stop":          "🛑 stop",
        "r_tp1":           "🥅 tp1",
        "r_tp2":           "🥅 tp2",
        "r_size":          "📦 Taille",
        "r_qty":           "qté",
        "r_risk_label":    "risque",
        "r_margin_need":   "marge",
        "r_levels":        "🧱 Niveaux",
        "r_support":       "🟩 support",
        "r_resistance":    "🟥 résistance",
        "r_why":           "🔍 Pourquoi",
        "r_risk_rule":     "🚨 Règle de risque",
        "r_risk_text":     "<b>CROSS + levier — le stop-loss est obligatoire.</b>",
        "r_skip_conf":     "🧊 Confiance",
        "r_skip_reason":   "🔍 Raisons",
        "r_cache_warn":    "⚠️<i>cache</i>",
    },

    # ─────────────────────────── SPANISH ───────────────────────────
    "es": {
        "welcome": (
            "👋 ¡Hola! Soy <b>UCB_TRADING_BOT</b>\n\n"
            "Tu asistente de trading para MEXC Futures.\n"
            "Analizo el mercado en velas de 4h y 1d, encuentro setups\n"
            "y creo planes: entrada, stop-loss, dos TP y tamaño de posición.\n\n"
            "🌐 Elige tu idioma:"
        ),
        "lang_set": "✅ Idioma establecido: <b>Español</b>\n\nEscribe /help para ver todos los comandos.",
        "choose_lang": "🌐 Elige tu idioma:",
        "deposit_button": "💰 Indicar depósito",
        "mini_app_button": "📊 Abrir panel",
        "deposit_start_hint": (
            "Indica tu depósito para calcular el tamaño de posición y el riesgo según tu capital. "
            "Los planes, escaneos y señales automáticas estarán disponibles después."
        ),
        "deposit_prompt": "💰 Envía tu depósito como un número, por ejemplo: <code>5000</code>",
        "deposit_saved": (
            "✅ Depósito guardado: <b>{deposit} USDT</b>\n\n"
            "Pulsa /plan para BTC o envía /plan ETH_USDT para otra moneda."
        ),
        "deposit_invalid": "❌ Envía un número positivo, por ejemplo: <code>5000</code>",
        "scan_reference_deposit": (
            "ℹ️ Tu depósito aún no está configurado. /scan funcionará igualmente, pero los tamaños "
            "se calcularán usando una referencia de <b>{deposit} USDT</b>."
        ),
        "help": (
            "📋 <b>UCB_TRADING_BOT — Comandos</b>\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "📌 <b>PLANES</b>\n"
            "/plan\n"
            "   → plan de BTC con tu depósito guardado\n"
            "/plan BTC_USDT\n"
            "   → plan con tus parámetros guardados\n"
            "/plan ETH_USDT lev=10 risk=2\n"
            "   → reemplazar parámetros para una sola consulta\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "🔍 <b>ESCANEO</b>\n"
            "/scan — escanear top {top_n} monedas (~2–4 min)\n"
            "   → solo setups sobre el umbral de confianza\n\n"
            "📊 <b>DIGEST</b>\n"
            "/digest — resumen completo del mercado ahora\n"
            "   → confianza alta / media + omitidos\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "🔐 <b>SUSCRIPCIÓN</b>\n"
            "/subscribe — instrucciones de pago USDT TRC20\n"
            "/paid TX_HASH — confirmar el pago\n"
            "/status — estado de acceso\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "⚙️ <b>TUS PARÁMETROS</b>\n"
            "/settings — ver tus parámetros actuales\n\n"
            "/set deposit=5000    — tu depósito para calcular la posición\n"
            "/set risk=1          — % de riesgo por trade (defecto 1%)\n"
            "/set lev=20          — apalancamiento (defecto 10x)\n"
            "/set margin=isolated — tipo de margen (defecto cross)\n\n"
            "Varios a la vez:\n"
            "<code>/set deposit=5000 risk=1.5 lev=15</code>\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "📖 <b>QUÉ SIGNIFICA EL PLAN</b>\n"
            "<code>entry</code>   — precio de entrada (orden límite)\n"
            "<code>stop</code>    — stop-loss\n"
            "<code>tp1/tp2</code> — take-profits (50% de la posición c/u)\n"
            "<code>conf</code>    — confianza del algoritmo (0.0–1.0)\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "🕐 <b>HORARIO (UTC)</b>\n"
            "Escaneo auto: 00:05 / 04:05 / 08:05\n"
            "              12:05 / 16:05 / 20:05\n"
            "Digest: {digest_hour}:00 diariamente\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "⚠️ <b>AVISO</b>\n"
            "El bot proporciona análisis, no señales de trading.\n"
            "La decisión de entrar en una operación es siempre tuya.\n\n"
            "🌐 Cambiar idioma → /start"
        ),
        "no_deposit": (
            "⚠️ Depósito no establecido.\n\n"
            "Establece tu depósito una sola vez:\n"
            "<code>/set deposit=5000</code>\n\n"
            "El bot lo recordará — no necesitas ingresarlo de nuevo."
        ),
        "set_usage": (
            "Uso:\n"
            "<code>/set deposit=5000</code>\n"
            "<code>/set risk=1.5</code>\n"
            "<code>/set lev=20</code>\n"
            "<code>/set deposit=5000 risk=1 lev=20</code>"
        ),
        "set_saved":       "✅ Guardado: {params}",
        "set_unknown":     "❌ Parámetro desconocido: {key}. Permitidos: deposit, risk, lev, margin",
        "settings_title":  "⚙️ <b>Tus parámetros</b>\n\n",
        "settings_deposit":"💰 deposit: {val}\n",
        "settings_deposit_missing": "💰 deposit: <b>⚠️ no establecido</b> → <code>/set deposit=XXXX</code>\n",
        "settings_risk":   "🎯 risk: <b>{val}%</b>\n",
        "settings_lev":    "🧰 lev: <b>{val}x</b>\n",
        "settings_margin": "📐 margin: <b>{val}</b>\n\n",
        "settings_change": "Cambiar: <code>/set deposit=X risk=X lev=X</code>",
        "deposit_not_set": "⚠️ no establecido → /set deposit=XXXX",
        "plan_loading":    "⏳ Cargando {symbol}...",
        "plan_error":      "❌ Error: {error}",
        "plan_usage": (
            "Uso:\n"
            "<code>/plan</code> — BTC\n"
            "<code>/plan ETH_USDT</code> — otra moneda\n"
            "<code>/plan ETH_USDT lev=20 risk=1</code> — ajustes temporales\n\n"
            "Siempre se usa el depósito guardado. Cámbialo con <code>/set deposit=5000</code>."
        ),
        "scan_starting":   "🔍 Escaneando top {top_n} monedas (~2–4 min)...",
        "scan_done":       "✅ {count} setup(s) encontrado(s). Top 5:",
        "scan_none":       "🧊 Sin setups sobre el umbral de confianza",
        "scan_more":       "...y {count} más. Usa /digest para una vista completa.",
        "scan_error":      "❌ Error de escaneo: {error}",
        "digest_preparing":"📊 Preparando digest...",
        "digest_title":    "📊 <b>Digest {time} UTC</b>\nVerificado: <b>{total}</b> monedas",
        "digest_high":     "🟢 <b>Alta confianza ≥0.65 — {count} setup(s)</b>",
        "digest_medium":   "🟡 <b>Confianza media 0.50–0.65 — {count} setup(s)</b>",
        "digest_skipped":  "🧊 Sin setup: <b>{count}</b> monedas",
        "digest_error":    "❌ Error en digest: {error}",
        "autoscan_error":  "⚠️ Error en escaneo automático: {error}",
        "r_context":       "🧠 Contexto",
        "r_plan":          "plan",
        "r_price":         "💵 Precio",
        "r_profile":       "🧷 Perfil",
        "r_deposit":       "💰 depósito",
        "r_risk":          "🎯 riesgo",
        "r_lev":           "🧰 apalancamiento",
        "r_regime":        "🧭 Régimen de mercado",
        "r_trend_1d":      "tendencia 1D",
        "r_trend_4h":      "4H",
        "r_struct":        "estructura 4H",
        "r_bos":           "BOS/CHOCH",
        "r_regime_label":  "régimen",
        "r_mid":           "midrange",
        "r_scenario":      "Escenario",
        "r_confidence":    "confianza",
        "r_entry":         "🎯 entrada",
        "r_stop":          "🛑 stop",
        "r_tp1":           "🥅 tp1",
        "r_tp2":           "🥅 tp2",
        "r_size":          "📦 Tamaño",
        "r_qty":           "cant.",
        "r_risk_label":    "riesgo",
        "r_margin_need":   "margen",
        "r_levels":        "🧱 Niveles",
        "r_support":       "🟩 soporte",
        "r_resistance":    "🟥 resistencia",
        "r_why":           "🔍 Por qué",
        "r_risk_rule":     "🚨 Regla de riesgo",
        "r_risk_text":     "<b>CROSS + apalancamiento — el stop-loss es obligatorio.</b>",
        "r_skip_conf":     "🧊 Confianza",
        "r_skip_reason":   "🔍 Razones",
        "r_cache_warn":    "⚠️<i>caché</i>",
    },
}


STRINGS["ru"].update({
    "payment_paywall": (
        "🔒 <b>Бесплатные сигналы использованы</b>\n\n"
        "Продолжи торговать с ботом — подписка на <b>{days} дней</b> стоит <b>{amount} USDT</b>.\n\n"
        "📋 <b>Как оплатить (3 шага):</b>\n"
        "1️⃣ Открой любую биржу или кошелёк (Binance, OKX, Trust Wallet…)\n"
        "2️⃣ Отправь <b>{amount} USDT</b> сетью <b>{network}</b> на адрес:\n"
        "<code>{wallet}</code>\n"
        "⚠️ Только сеть TRC20 (TRON) — не ERC20 и не BEP20!\n\n"
        "3️⃣ Скопируй хеш транзакции (TX Hash / TXID) и отправь:\n"
        "<code>/paid ВАШ_TX_HASH</code>\n\n"
        "Бот проверит перевод и активирует доступ автоматически (~1–2 мин).\n\n"
        "❓ Вопросы? /help"
    ),
    "trial_remaining": "🎁 Бесплатных сигналов осталось: <b>{count}</b>",
    "trial_low_cta": "⚡ Скоро закончатся — оформи подписку: /subscribe",
    "trial_cooldown": "⏳ Следующий бесплатный сигнал будет доступен примерно через <b>{minutes} мин.</b>\n\nХочешь получать больше сигналов без ожидания — оформи подписку: /subscribe",
    "payment_paid_usage": "Отправь хеш транзакции:\n<code>/paid TX_HASH</code>",
    "payment_checking": "🔎 Проверяю подтверждённую USDT TRC20-транзакцию...",
    "payment_tx_used": "❌ Этот TX-хеш уже использован для другой подписки.",
    "payment_invalid_hash": "❌ Неверный TX-хеш. Он должен содержать 64 символа.",
    "payment_not_found": "⏳ Подтверждённый перевод пока не найден. Проверь сеть, адрес и TX-хеш, затем повтори /paid через несколько минут.",
    "payment_amount_low": "❌ Получено {paid} USDT, требуется минимум {required} USDT.",
    "payment_verify_error": "⚠️ Сервис проверки временно недоступен. Попробуй /paid ещё раз через несколько минут.",
    "payment_approved": "✅ Оплата подтверждена. Доступ активирован на <b>{days} дней</b>, до <b>{until}</b>.",
    "status_active": "✅ Оплачено до: <b>{until}</b>",
    "status_inactive": "⏳ Активной подписки нет",
    "status_payment": "Последняя оплата:\nTX: <code>{tx}</code>\nСтатус: <b>{status}</b>",
    "status_summary": "👤 <b>Статус доступа</b>\n\n{access}\nБесплатных сигналов: <b>{left}</b> из {total}{claim}",
})

STRINGS["en"].update({
    "payment_paywall": (
        "🔒 <b>Your free signals are used up</b>\n\n"
        "Keep trading with the bot — <b>{days}-day access</b> costs <b>{amount} USDT</b>.\n\n"
        "📋 <b>How to pay (3 steps):</b>\n"
        "1️⃣ Open any exchange or wallet (Binance, OKX, Trust Wallet…)\n"
        "2️⃣ Send <b>{amount} USDT</b> via <b>{network}</b> to:\n"
        "<code>{wallet}</code>\n"
        "⚠️ TRC20 (TRON) network only — not ERC20 or BEP20!\n\n"
        "3️⃣ Copy the transaction hash (TX Hash / TXID) and send:\n"
        "<code>/paid YOUR_TX_HASH</code>\n\n"
        "The bot verifies the transfer and activates access automatically (~1–2 min).\n\n"
        "❓ Questions? /help"
    ),
    "trial_remaining": "🎁 Free signals remaining: <b>{count}</b>",
    "trial_low_cta": "⚡ Running out — subscribe now: /subscribe",
    "trial_cooldown": "⏳ Your next free signal will be available in about <b>{minutes} min.</b>\n\nWant more signals without waiting? Subscribe: /subscribe",
    "payment_paid_usage": "Send the transaction hash:\n<code>/paid TX_HASH</code>",
    "payment_checking": "🔎 Checking the confirmed USDT TRC20 transaction...",
    "payment_tx_used": "❌ This transaction hash has already been used for another subscription.",
    "payment_invalid_hash": "❌ Invalid transaction hash. It must contain 64 characters.",
    "payment_not_found": "⏳ Confirmed payment not found yet. Check the network, wallet and hash, then retry /paid in a few minutes.",
    "payment_amount_low": "❌ Received {paid} USDT; at least {required} USDT is required.",
    "payment_verify_error": "⚠️ The verification service is temporarily unavailable. Retry /paid in a few minutes.",
    "payment_approved": "✅ Payment confirmed. Access is active for <b>{days} days</b>, until <b>{until}</b>.",
    "status_active": "✅ Paid until: <b>{until}</b>",
    "status_inactive": "⏳ No active subscription",
    "status_payment": "Latest payment:\nTX: <code>{tx}</code>\nStatus: <b>{status}</b>",
    "status_summary": "👤 <b>Access status</b>\n\n{access}\nFree signals: <b>{left}</b> of {total}{claim}",
})

STRINGS["de"].update({
    "payment_paywall": (
        "🔒 <b>Deine kostenlosen Signale sind aufgebraucht</b>\n\n"
        "Zugang für <b>{days} Tage</b>: <b>{amount} USDT</b>.\n"
        "Netzwerk: <b>{network}</b>\nWallet:\n<code>{wallet}</code>\n\n"
        "Nach der Zahlung sende:\n<code>/paid TX_HASH</code>\n\n"
        "Der Bot prüft die Transaktion und aktiviert den Zugang automatisch."
    ),
    "trial_remaining": "🎁 Verbleibende kostenlose Signale: <b>{count}</b>",
    "trial_low_cta": "⚡ Bald aufgebraucht — jetzt abonnieren: /subscribe",
    "trial_cooldown": "⏳ Dein nächstes kostenloses Signal ist in ca. <b>{minutes} Min.</b> verfügbar.\n\nMehr Signale ohne Warten: /subscribe",
    "payment_paid_usage": "Sende den Transaktions-Hash:\n<code>/paid TX_HASH</code>",
    "payment_checking": "🔎 Bestätigte USDT-TRC20-Transaktion wird geprüft...",
    "payment_tx_used": "❌ Dieser Transaktions-Hash wurde bereits verwendet.",
    "payment_invalid_hash": "❌ Ungültiger Transaktions-Hash. Er muss 64 Zeichen enthalten.",
    "payment_not_found": "⏳ Bestätigte Zahlung noch nicht gefunden. Prüfe Netzwerk, Wallet und Hash und versuche /paid später erneut.",
    "payment_amount_low": "❌ Erhalten: {paid} USDT; erforderlich: mindestens {required} USDT.",
    "payment_verify_error": "⚠️ Der Prüfdienst ist vorübergehend nicht verfügbar. Versuche /paid später erneut.",
    "payment_approved": "✅ Zahlung bestätigt. Zugang für <b>{days} Tage</b> bis <b>{until}</b> aktiviert.",
    "status_active": "✅ Bezahlt bis: <b>{until}</b>",
    "status_inactive": "⏳ Kein aktives Abonnement",
    "status_payment": "Letzte Zahlung:\nTX: <code>{tx}</code>\nStatus: <b>{status}</b>",
    "status_summary": "👤 <b>Zugangsstatus</b>\n\n{access}\nKostenlose Signale: <b>{left}</b> von {total}{claim}",
})

STRINGS["fr"].update({
    "payment_paywall": (
        "🔒 <b>Tes signaux gratuits sont épuisés</b>\n\n"
        "Accès pendant <b>{days} jours</b> : <b>{amount} USDT</b>.\n"
        "Réseau : <b>{network}</b>\nPortefeuille :\n<code>{wallet}</code>\n\n"
        "Après le paiement, envoie :\n<code>/paid TX_HASH</code>\n\n"
        "Le bot vérifiera la transaction et activera automatiquement l'accès."
    ),
    "trial_remaining": "🎁 Signaux gratuits restants : <b>{count}</b>",
    "trial_low_cta": "⚡ Bientôt épuisés — abonnez-vous maintenant : /subscribe",
    "trial_cooldown": "⏳ Ton prochain signal gratuit sera disponible dans environ <b>{minutes} min.</b>\n\nPour plus de signaux sans attente : /subscribe",
    "payment_paid_usage": "Envoie le hash de transaction :\n<code>/paid TX_HASH</code>",
    "payment_checking": "🔎 Vérification de la transaction USDT TRC20 confirmée...",
    "payment_tx_used": "❌ Ce hash de transaction a déjà été utilisé.",
    "payment_invalid_hash": "❌ Hash incorrect. Il doit contenir 64 caractères.",
    "payment_not_found": "⏳ Paiement confirmé introuvable. Vérifie le réseau, le portefeuille et le hash, puis réessaie /paid.",
    "payment_amount_low": "❌ Reçu : {paid} USDT ; minimum requis : {required} USDT.",
    "payment_verify_error": "⚠️ Le service de vérification est indisponible. Réessaie /paid dans quelques minutes.",
    "payment_approved": "✅ Paiement confirmé. Accès activé pendant <b>{days} jours</b>, jusqu'au <b>{until}</b>.",
    "status_active": "✅ Payé jusqu'au : <b>{until}</b>",
    "status_inactive": "⏳ Aucun abonnement actif",
    "status_payment": "Dernier paiement :\nTX : <code>{tx}</code>\nStatut : <b>{status}</b>",
    "status_summary": "👤 <b>Statut d'accès</b>\n\n{access}\nSignaux gratuits : <b>{left}</b> sur {total}{claim}",
})

STRINGS["es"].update({
    "payment_paywall": (
        "🔒 <b>Tus señales gratuitas se han agotado</b>\n\n"
        "Acceso durante <b>{days} días</b>: <b>{amount} USDT</b>.\n"
        "Red: <b>{network}</b>\nBilletera:\n<code>{wallet}</code>\n\n"
        "Después del pago, envía:\n<code>/paid TX_HASH</code>\n\n"
        "El bot verificará la transacción y activará el acceso automáticamente."
    ),
    "trial_remaining": "🎁 Señales gratuitas restantes: <b>{count}</b>",
    "trial_low_cta": "⚡ Casi agotadas — suscríbete ahora: /subscribe",
    "trial_cooldown": "⏳ Tu próxima señal gratuita estará disponible en unos <b>{minutes} min.</b>\n\nPara más señales sin esperar: /subscribe",
    "payment_paid_usage": "Envía el hash de la transacción:\n<code>/paid TX_HASH</code>",
    "payment_checking": "🔎 Verificando la transacción USDT TRC20 confirmada...",
    "payment_tx_used": "❌ Este hash de transacción ya fue utilizado.",
    "payment_invalid_hash": "❌ Hash incorrecto. Debe contener 64 caracteres.",
    "payment_not_found": "⏳ Aún no se encontró el pago confirmado. Revisa la red, la billetera y el hash, y repite /paid.",
    "payment_amount_low": "❌ Recibido: {paid} USDT; se requieren al menos {required} USDT.",
    "payment_verify_error": "⚠️ El servicio de verificación no está disponible. Repite /paid en unos minutos.",
    "payment_approved": "✅ Pago confirmado. Acceso activado durante <b>{days} días</b>, hasta <b>{until}</b>.",
    "status_active": "✅ Pagado hasta: <b>{until}</b>",
    "status_inactive": "⏳ Sin suscripción activa",
    "status_payment": "Último pago:\nTX: <code>{tx}</code>\nEstado: <b>{status}</b>",
    "status_summary": "👤 <b>Estado de acceso</b>\n\n{access}\nSeñales gratuitas: <b>{left}</b> de {total}{claim}",
})


def t(lang: str, key: str, **kwargs: Any) -> str:
    lang_strings = STRINGS.get(lang, STRINGS["en"])
    text = lang_strings.get(key) or STRINGS["en"].get(key, key)
    return text.format(**kwargs) if kwargs else text
