"""Commands shown in the Telegram menu. Admin commands stay unlisted.

/setup and /spikes still run when typed. They stay out of this menu so they
are not listed beside /plan and /scan.
"""

from aiogram.types import BotCommand


PUBLIC_COMMANDS = (
    ("start", "Start and choose a language"),
    ("help", "How the bot works"),
    ("plan", "Plan for a USDT pair"),
    ("scan", "Scan liquid markets"),
    ("digest", "Market digest on request"),
    ("set", "Deposit, risk, leverage, margin"),
    ("settings", "Show saved settings"),
    ("subscribe", "USDT TRC20 payment instructions"),
    ("paid", "Submit a payment hash"),
    ("status", "Access status"),
)

MENU_LANGUAGES = ("en", "ru", "de", "fr", "es")

_MENU_TEXT = {
    "ru": {
        "start": "Старт и выбор языка",
        "help": "Как работает бот",
        "plan": "План по паре USDT",
        "scan": "Скан ликвидных рынков",
        "digest": "Дайджест рынка по запросу",
        "set": "Депозит, риск, плечо, маржа",
        "settings": "Сохранённые настройки",
        "subscribe": "Оплата USDT TRC20",
        "paid": "Отправить хеш оплаты",
        "status": "Статус доступа",
    },
    "de": {
        "start": "Start und Sprache wählen",
        "help": "So funktioniert der Bot",
        "plan": "Plan für ein USDT-Paar",
        "scan": "Liquide Märkte scannen",
        "digest": "Marktdigest auf Abruf",
        "set": "Kapital, Risiko, Hebel, Margin",
        "settings": "Gespeicherte Einstellungen",
        "subscribe": "USDT-TRC20-Zahlung",
        "paid": "Zahlungs-Hash senden",
        "status": "Zugangsstatus",
    },
    "fr": {
        "start": "Démarrer et choisir la langue",
        "help": "Comment fonctionne le bot",
        "plan": "Plan pour une paire USDT",
        "scan": "Scanner les marchés liquides",
        "digest": "Digest du marché à la demande",
        "set": "Dépôt, risque, levier, marge",
        "settings": "Réglages enregistrés",
        "subscribe": "Paiement USDT TRC20",
        "paid": "Envoyer le hash de paiement",
        "status": "Statut d'accès",
    },
    "es": {
        "start": "Inicio y elección de idioma",
        "help": "Cómo funciona el bot",
        "plan": "Plan para un par USDT",
        "scan": "Escanear mercados líquidos",
        "digest": "Resumen del mercado",
        "set": "Depósito, riesgo, apalancamiento",
        "settings": "Ajustes guardados",
        "subscribe": "Pago USDT TRC20",
        "paid": "Enviar el hash del pago",
        "status": "Estado del acceso",
    },
}


def menu_commands(lang: str = "en") -> list[BotCommand]:
    descriptions = {name: text for name, text in PUBLIC_COMMANDS}
    descriptions.update(_MENU_TEXT.get(lang) or {})
    return [
        BotCommand(command=name, description=descriptions[name])
        for name, _text in PUBLIC_COMMANDS
    ]
