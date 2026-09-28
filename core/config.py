import os
from dotenv import load_dotenv

load_dotenv()

# MEXC API Credentials (Bot 1 - Signals)
MEXC_API_KEY = os.getenv("MEXC_API_KEY", "")
MEXC_API_SECRET = os.getenv("MEXC_API_SECRET", "")

# Telegram Bot Credentials
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
# Values are Telegram user ids. The variable name is unchanged: in a private
# chat the user id equals the chat id, so existing private-chat values still work.
ADMIN_CHAT_IDS = {
    chat_id.strip()
    for chat_id in os.getenv("ADMIN_CHAT_IDS", TELEGRAM_CHAT_ID).split(",")
    if chat_id.strip()
}

# Config variables
TIMEFRAMES = ["15m", "1h", "4h", "1d", "1w"]

# Core Target Pairs (Единый источник правды)
TARGET_COINS = ["BTC", "ETH", "SOL"]

# How many top coins by volume to track for SMC main strategy
TOP_COINS_LIMIT = 50

# How many coins to track for the Spike/Pump Scanner (to catch memecoins/shitcoins outside top 50)
MEMECOIN_V2_LIMIT = 250

# Spike Scanner parameters (Tuned for 15m pumps)
SPIKE_VOLUME_MULTIPLIER = 4.0 # Candle volume must be 4x the moving average (stricter for accuracy)
SPIKE_PRICE_ATR_MULTIPLIER = 2.5 # Candle body must be 2.5x the ATR
SPIKE_MIN_PCT_CHANGE = 2.0 # Minimum % move in 15m candle to trigger pump alert
SMART_SPIKE_MIN_SCORE = int(os.getenv("SMART_SPIKE_MIN_SCORE", "65"))
SMART_SPIKE_MIN_QUOTE_VOLUME = float(os.getenv("SMART_SPIKE_MIN_QUOTE_VOLUME", "500000"))

# New listing watcher
MEXC_LISTING_SNAPSHOT_FILE = os.getenv("MEXC_LISTING_SNAPSHOT_FILE", "mexc_markets_snapshot.json")
MEXC_ANNOUNCEMENTS_SNAPSHOT_FILE = os.getenv("MEXC_ANNOUNCEMENTS_SNAPSHOT_FILE", "mexc_announcements_snapshot.json")
MEXC_LISTING_CHECK_INTERVAL = int(os.getenv("MEXC_LISTING_CHECK_INTERVAL", "600"))
MEXC_NEW_LISTINGS_URL = os.getenv("MEXC_NEW_LISTINGS_URL", "https://www.mexc.com/announcements/new-listings")

# Payments / access control
FREE_TRIAL_SIGNALS = int(os.getenv("FREE_TRIAL_SIGNALS", "5"))
FREE_TRIAL_COOLDOWN_MINUTES = int(os.getenv("FREE_TRIAL_COOLDOWN_MINUTES", "30"))
PAID_ACCESS_DAYS = int(os.getenv("SUBSCRIPTION_DAYS", "30"))
PAID_ACCESS_HOURS = PAID_ACCESS_DAYS * 24
USDT_PAYMENT_ADDRESS = os.getenv("USDT_PAYMENT_ADDRESS", "")
USDT_PAYMENT_AMOUNT = os.getenv("SUBSCRIPTION_PRICE_USDT", "29.99")
USDT_PAYMENT_NETWORK = os.getenv("USDT_PAYMENT_NETWORK", "TRC20")
ACCESS_STATE_FILE = os.getenv("ACCESS_STATE_FILE", "user_access.json")
USER_REGISTRY_FILE = os.getenv("USER_REGISTRY_FILE", "users.json")
TRONGRID_API_KEY = os.getenv("TRONGRID_API_KEY", "")
MINI_APP_URL = os.getenv("MINI_APP_URL", "").strip()
if MINI_APP_URL.startswith("http://"):
    MINI_APP_URL = "https://" + MINI_APP_URL.removeprefix("http://")
elif MINI_APP_URL and not MINI_APP_URL.startswith("https://"):
    MINI_APP_URL = "https://" + MINI_APP_URL

# SMC Analyzer parameters
SMC_LOOKBACK_PERIOD = 200 # Candles to look back for structure

# Global Risk Management (For Alerts / MEXC)
RISK_PER_TRADE_PERCENT = 1.0 # 1% of total balance per trade
MAX_OPEN_POSITIONS = 3
LEVERAGE = 10

# BTC-only trade policy
BTC_LONG_ONLY_MODE = False # Разрешаем и BTC-лонги, и BTC-шорты, но только по дневному тренду
BTC_REQUIRE_DAILY_UPTREND = True # Лонги только если BTC выше дневной EMA200 и EMA20 > EMA50; шорты зеркально по медвежьему тренду
BTC_MAX_DAILY_ATR_PCT = 0.045 # Не входить, если дневной ATR выше 4.5% цены
BTC_MIN_RISK_REWARD = 1.8 # Минимальный плановый RR для BTC-сделки
