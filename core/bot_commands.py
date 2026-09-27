"""Commands shown in the Telegram menu. Admin commands stay unlisted."""

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
    ("setup", "SMC setup for one coin"),
    ("spikes", "Scan volume spikes"),
)


def menu_commands() -> list[BotCommand]:
    return [BotCommand(command=command, description=description) for command, description in PUBLIC_COMMANDS]
