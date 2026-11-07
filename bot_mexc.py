#!/usr/bin/env python3
"""UCB_TRADING_BOT — единая система (aiogram)
Старый функционал : SMC / MTF / спайки / листинги / access control
Новый функционал  : /plan (EMA+ATR+ADX), /scan, /digest, /set, /settings, i18n x5
"""
from __future__ import annotations

import asyncio
import html
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

# Keep aiohttp's pure-Python parser as defense in depth for untrusted exchange
# responses, even though the pinned aiohttp release includes the parser fixes.
os.environ.setdefault("AIOHTTP_NO_EXTENSIONS", "1")

from aiogram import Bot, Dispatcher, types, Router, BaseMiddleware
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    BotCommandScopeChat,
    MenuButtonWebApp,
    WebAppInfo,
    Message,
    CallbackQuery,
)

# ── старые модули ──
from bingx.exchange_client_bingx import ExchangeClient
from core.smc_analyzer import SMCAnalyzer
from core.spike_scanner import SpikeScanner
from core.notifier import Notifier
from core.smart_engine import SmartContextEngine, SignalType, MTFFusionEngine
from core.coin_info_service import CoinInfoService
from core.listing_watcher import BingxListingWatcher
from core.access_manager import AccessManager
from core.config import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, ADMIN_CHAT_IDS, ADMIN_ACCESS_EXCLUDED_IDS,
    TOP_COINS_LIMIT, TARGET_COINS,
    SMART_SPIKE_MIN_SCORE, SMART_SPIKE_MIN_QUOTE_VOLUME,
    BINGX_LISTING_SNAPSHOT_FILE, BINGX_ANNOUNCEMENTS_SNAPSHOT_FILE,
    BINGX_LISTING_CHECK_INTERVAL, BINGX_NEW_LISTINGS_URL,
    FREE_TRIAL_SIGNALS, FREE_TRIAL_COOLDOWN_MINUTES, PAID_ACCESS_HOURS,
    USDT_PAYMENT_ADDRESS, USDT_PAYMENT_AMOUNT, USDT_PAYMENT_NETWORK,
    BINGX_REFERRAL_CODE, BINGX_REFERRAL_URL, REFERRAL_SUBSCRIPTION_PRICE_USDT,
    ACCESS_STATE_FILE, USER_REGISTRY_FILE, TRONGRID_API_KEY, MINI_APP_URL,
)
from core.tron_payment import TronPaymentVerifier
from core.chat_policy import is_private_chat, language_for_start
from core.access_handlers import bind_access_handlers
from core.background_loops import bind_background_loops
from core.free_text_handlers import bind_free_text_handler
from core.onboarding_handlers import bind_onboarding_handlers
from core.trading_handlers import bind_trading_handlers
from core.bot_commands import menu_commands
from core.payment_reasons import payment_reason_key
from core.worker_lock import hold_worker_lock
from core.fsm_storage import PostgresFSMStorage

# ── наши торговые модули из trading/ ──
_TRADING_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trading")
if _TRADING_DIR not in sys.path:
    sys.path.insert(0, _TRADING_DIR)

import bingx_snapshot as snap
from trading import group_plan as core_plan
import scanner as sc
import state as st
from i18n import LANG_BUTTONS, t as _t
from telegram_render import confidence_percent, render_telegram_plan
from auto_alert import render_auto_alert
from signal_updates import (
    signal_identity_footer,
)
from trading.notification_delivery import deliver_pending_signal_updates
from setup_text import no_setup_query, render_scan_card, render_setup, signal_query
from user_input import (
    asks_for_plan_scan,
    bare_plan_symbol,
    is_deposit_input,
    is_greeting,
    mentioned_plan_symbol,
    parse_deposit_amount,
    parse_setting,
)
from miniapp.schema import apply_migrations
from miniapp.bingx_agent import verify_direct_referral
from miniapp.referrals import (
    pending_referral_claims,
    review_referral_claim,
    submit_referral_claim,
)

logger = logging.getLogger("ucb.bot")

# ── конфиг сканера ──
with open(os.path.join(_TRADING_DIR, "config.json")) as _f:
    _CFG = json.load(_f)
SCAN_CFG  = _CFG["scanner"]
TRADE_CFG = _CFG["trading"]

# ── инициализация бота ──
bot_instance = Bot(token=TELEGRAM_BOT_TOKEN)
router = Router()
onboarding_router = Router(name="onboarding")
access_router = Router(name="access")
trading_router = Router(name="trading")
free_text_router = Router(name="free_text")

SPIKE_COOLDOWN = 4 * 3600
SETUP_COOLDOWN = 8 * 3600
SCAN_REFERENCE_DEPOSIT = 1000.0
MAJOR_SCAN_SYMBOLS = ["BTC_USDT", "ETH_USDT", "SOL_USDT"]
MAJOR_SCAN_MIN_CONFIDENCE = float(os.getenv("MAJOR_SCAN_MIN_CONFIDENCE", "0.50"))
SIGNAL_TRACKER_INTERVAL_SECONDS = max(
    5, int(os.getenv("SIGNAL_TRACKER_INTERVAL_SECONDS", "15"))
)
SIGNAL_REPLAY_BATCH_SIZE = max(
    1, min(200, int(os.getenv("SIGNAL_REPLAY_BATCH_SIZE", "100")))
)
SIGNAL_ENTRY_AUDIT_INTERVAL_SECONDS = max(
    60, int(os.getenv("SIGNAL_ENTRY_AUDIT_INTERVAL_SECONDS", "300"))
)
SIGNAL_ENTRY_AUDIT_BATCH_SIZE = max(
    1, min(20, int(os.getenv("SIGNAL_ENTRY_AUDIT_BATCH_SIZE", "3")))
)


class DepositSetup(StatesGroup):
    waiting_for_amount = State()

# ═══════════════════════════════════════════
# ПОЛЬЗОВАТЕЛИ
# ═══════════════════════════════════════════

def _user_id(message_or_user) -> str:
    user = getattr(message_or_user, "from_user", message_or_user)
    return str(user.id)


def _has_saved_deposit(user_id) -> bool:
    try:
        return float(st.get_user_settings(int(user_id)).get("deposit") or 0) > 0
    except (TypeError, ValueError):
        return False


# Recipients are loaded from Postgres after migrations, not from users.json.
active_users = set()

# ── старые сервисы ──
exchange        = ExchangeClient()
smc_analyzer    = SMCAnalyzer()
spike_scanner   = SpikeScanner()
smart_engine    = SmartContextEngine()
mtf_engine      = MTFFusionEngine()
coin_info_svc   = CoinInfoService()
access_manager  = AccessManager(
    ACCESS_STATE_FILE,
    free_trial_signals=FREE_TRIAL_SIGNALS,
    paid_access_hours=PAID_ACCESS_HOURS,
    payment_address=USDT_PAYMENT_ADDRESS,
    payment_amount=USDT_PAYMENT_AMOUNT,
    payment_network=USDT_PAYMENT_NETWORK,
)
listing_watcher = BingxListingWatcher(
    BINGX_LISTING_SNAPSHOT_FILE,
    announcements_snapshot_file=BINGX_ANNOUNCEMENTS_SNAPSHOT_FILE,
    announcements_url=BINGX_NEW_LISTINGS_URL,
)
payment_verifier = TronPaymentVerifier(
    USDT_PAYMENT_ADDRESS,
    USDT_PAYMENT_AMOUNT,
    api_key=TRONGRID_API_KEY,
)


def _payment_paywall(user_id) -> str:
    lang = get_lang(int(user_id))
    invoice = access_manager.ensure_open_invoice(str(user_id))
    if not invoice:
        return _t(lang, "payment_save_failed")
    text = _t(
        lang,
        "payment_paywall",
        free_signals=FREE_TRIAL_SIGNALS,
        amount=html.escape(str(invoice["expected_amount"])),
        days=PAID_ACCESS_HOURS // 24,
        network=html.escape(str(USDT_PAYMENT_NETWORK)),
        wallet=html.escape(str(USDT_PAYMENT_ADDRESS or "")),
    )
    if invoice.get("referral_status") == "expired":
        text += "\n\n" + _t(lang, "referral_expired")
    return text


def _trial_notice(chat_id, remaining: int) -> str:
    lang = get_lang(int(chat_id))
    base = _t(lang, "trial_remaining", count=remaining)
    if remaining <= 2:
        base += "\n" + _t(lang, "trial_low_cta")
    return base


def _format_wait_minutes(seconds: int) -> int:
    return max(1, int((seconds + 59) // 60))


notifier = Notifier(
    bot_instance,
    active_users,
    access_manager=access_manager,
    paywall_formatter=_payment_paywall,
    trial_formatter=_trial_notice,
)
def refresh_recipients() -> None:
    notifier.active_users.clear()
    notifier.active_users.update(st.load_alert_recipients(FREE_TRIAL_SIGNALS))


class PrivateChatMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        chat = getattr(event, "chat", None)
        if chat is None and getattr(event, "message", None) is not None:
            chat = event.message.chat
        if chat is not None and not is_private_chat(getattr(chat, "type", None)):
            user = getattr(event, "from_user", None)
            lang = get_lang(user.id) if user is not None else "en"
            text = _t(lang, "private_only")
            if isinstance(event, CallbackQuery):
                try:
                    await event.answer(text[:180], show_alert=True)
                except Exception:
                    logger.warning("private-chat callback answer failed")
            elif isinstance(event, Message):
                try:
                    await event.answer(text)
                except Exception:
                    logger.warning("private-chat reply failed")
            return None
        return await handler(event, data)


router.message.outer_middleware(PrivateChatMiddleware())
router.callback_query.outer_middleware(PrivateChatMiddleware())

# ═══════════════════════════════════════════
# ХЕЛПЕРЫ
# ═══════════════════════════════════════════

def is_admin(user_id) -> bool:
    """Admin rights follow the Telegram user id.

    ADMIN_CHAT_IDS keeps its name. In a private chat that id equals the chat
    id, so existing private-chat values still work. A group id does not.
    """
    normalized = str(user_id)
    return normalized in ADMIN_CHAT_IDS and normalized not in ADMIN_ACCESS_EXCLUDED_IDS

def format_ts(ts: int) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else "нет"

def get_lang(user_id: int) -> str:
    return st.get_user_lang(user_id)

def _lang_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    btns = [InlineKeyboardButton(text=lbl, callback_data=cb) for lbl, cb in LANG_BUTTONS]
    rows = [
        btns[:3],
        btns[3:],
        [InlineKeyboardButton(text=_t(lang, "deposit_button"), callback_data="set_deposit")],
    ]
    if MINI_APP_URL:
        rows.append([
            InlineKeyboardButton(
                text=_t(lang, "mini_app_button"),
                web_app=WebAppInfo(url=MINI_APP_URL),
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _deposit_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=_t(lang, "deposit_button"), callback_data="set_deposit")
    ]])


def _one_action_keyboard(lang: str, label_key: str, callback_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=_t(lang, label_key), callback_data=callback_data)
    ]])


def _help_keyboard(lang: str) -> InlineKeyboardMarkup:
    rows = [[
        InlineKeyboardButton(text=_t(lang, "request_plan"), callback_data="request_plan"),
        InlineKeyboardButton(text=_t(lang, "run_scan"), callback_data="run_scan"),
    ]]
    if MINI_APP_URL:
        rows.append([
            InlineKeyboardButton(
                text=_t(lang, "mini_app_button"),
                web_app=WebAppInfo(url=MINI_APP_URL),
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _plan_symbol_keyboard(lang: str, symbol: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=_t(lang, "plan_symbol", symbol=symbol),
            callback_data=f"plan_for:{symbol}",
        )
    ]])


def _signal_app_url(signal_id: int) -> str:
    parts = urlparse(MINI_APP_URL)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.pop("symbol", None)
    query.update(dict(parse_qsl(signal_query(signal_id))))
    return urlunparse(parts._replace(query=urlencode(query)))


def _language_only_keyboard() -> InlineKeyboardMarkup:
    buttons = [InlineKeyboardButton(text=label, callback_data=callback) for label, callback in LANG_BUTTONS]
    return InlineKeyboardMarkup(inline_keyboard=[buttons[:3], buttons[3:]])


def _panel_url(view: str | None = None) -> str:
    parts = urlparse(MINI_APP_URL)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if view:
        query["view"] = view
    return urlunparse(parts._replace(query=urlencode(query)))


def _webapp_button(lang: str, label_key: str, url: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=_t(lang, label_key), web_app=WebAppInfo(url=url))


def _no_setup_app_url(symbol: str) -> str:
    parts = urlparse(MINI_APP_URL)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.pop("signal_id", None)
    query.pop("symbol", None)
    query.update(dict(parse_qsl(no_setup_query(symbol))))
    return urlunparse(parts._replace(query=urlencode(query)))


def _no_setup_keyboard(lang: str, symbol: str) -> InlineKeyboardMarkup:
    if MINI_APP_URL:
        return InlineKeyboardMarkup(inline_keyboard=[[
            _webapp_button(lang, "open_setup", _no_setup_app_url(symbol))
        ]])
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=_t(lang, "another_symbol"), callback_data="another_symbol")
    ]])


def _open_setup_keyboard(signal_id, lang: str) -> InlineKeyboardMarkup | None:
    if not MINI_APP_URL or not signal_id:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[
        _webapp_button(lang, "open_setup", _signal_app_url(int(signal_id)))
    ]])


def _with_signal_identity(text: str, signal_id, symbol: str, side: str, lang: str) -> str:
    if not signal_id:
        return text
    return text + "\n\n" + signal_identity_footer(
        int(signal_id), symbol, side, lang=lang,
    )


def _alert_keyboard(signal_id, lang: str) -> InlineKeyboardMarkup:
    row = []
    if MINI_APP_URL and signal_id:
        row.append(_webapp_button(lang, "open_setup", _signal_app_url(int(signal_id))))
    row.append(InlineKeyboardButton(text=_t(lang, "alert_later"), callback_data="alert_later"))
    return InlineKeyboardMarkup(inline_keyboard=[row])


def _ready_keyboard(lang: str) -> InlineKeyboardMarkup:
    rows = []
    if MINI_APP_URL:
        rows.append([_webapp_button(lang, "open_setup", MINI_APP_URL)])
    rows.append([InlineKeyboardButton(text=_t(lang, "plan_btc"), callback_data="plan_for:BTC")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _settings_keyboard(lang: str) -> InlineKeyboardMarkup | None:
    if not MINI_APP_URL:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[
        _webapp_button(lang, "open_settings", _panel_url("settings"))
    ]])


def _ready_text(lang: str, deposit, risk) -> str:
    return _t(lang, "ready_next", deposit=f"{float(deposit):,.2f}", risk=risk)


def _deposit_prompt_reply(lang: str) -> tuple[str, None]:
    return _t(lang, "deposit_invalid") + "\n\n" + _t(lang, "deposit_prompt"), None


class _CommandView:
    """Reply through an existing chat message while attributing the user correctly."""

    def __init__(self, message, user, text: str):
        self.text = text
        self.from_user = user
        self.chat = getattr(message, "chat", None)
        self.message_id = getattr(message, "message_id", 0)
        self._message = message

    async def reply(self, text, **kwargs):
        return await self._message.reply(text, **kwargs)


def _callback_symbol(raw: str) -> str:
    return re.sub(r"[^A-Z0-9_]", "", str(raw or "").upper())[:40]


def _remember_personal_alert(user_id, **fields) -> int | None:
    signal_id = st.save_alert_signal(**fields)
    if signal_id:
        try:
            st.grant_signal_access(int(user_id), signal_id)
        except (TypeError, ValueError):
            logger.warning("alert access grant skipped")
    return signal_id


async def _set_user_commands(chat_id, lang: str) -> None:
    if chat_id is None:
        return
    try:
        await bot_instance.set_my_commands(
            menu_commands(lang),
            scope=BotCommandScopeChat(chat_id=int(chat_id)),
        )
    except Exception:
        logger.warning("set_my_commands failed")


async def _set_panel_menu(chat_id=None, lang: str = "en") -> None:
    if not MINI_APP_URL:
        return
    button = MenuButtonWebApp(
        text=_t(lang, "menu_webapp"),
        web_app=WebAppInfo(url=MINI_APP_URL),
    )
    try:
        if chat_id is None:
            await bot_instance.set_chat_menu_button(menu_button=button)
        else:
            await bot_instance.set_chat_menu_button(chat_id=chat_id, menu_button=button)
    except Exception:
        logger.warning("menu button failed")

def _parse_kv(parts):
    kv = {}
    for p in parts:
        if "=" in p:
            k, v = p.split("=", 1)
            kv[k.strip()] = v.strip()
    return kv

def _conf(plan: dict) -> float:
    if plan.get("side") == "skip":
        return float(plan.get("confidence", 0) or 0)
    return float((plan.get("primary") or {}).get("confidence", 0) or 0)

def norm_sym(s: str) -> str:
    s = s.upper().strip()
    if "_" not in s and s.endswith("USDT"):
        s = s[:-4] + "_USDT"
    return s


def _scan_symbols(symbols: list[str]) -> list[str]:
    seen = set()
    ordered = []
    for symbol in [*MAJOR_SCAN_SYMBOLS, *symbols, *core_plan.catalog()[1]]:
        normalized = norm_sym(str(symbol))
        if normalized in seen or not _is_usdt_pair(normalized):
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _is_major_symbol(symbol: str) -> bool:
    return norm_sym(symbol) in MAJOR_SCAN_SYMBOLS


def _is_actionable_plan(plan: dict) -> bool:
    symbol = plan.get("symbol", "")
    if (
        plan.get("side") == "skip"
        or core_plan.plan_payload_errors(plan)
        or not _is_usdt_pair(symbol)
        or _is_junk_symbol(symbol)
    ):
        return False
    min_conf = MAJOR_SCAN_MIN_CONFIDENCE if _is_major_symbol(symbol) else SCAN_CFG["min_confidence"]
    return _conf(plan) >= min_conf


def _rank_actionable_plans(plans: list[dict]) -> list[dict]:
    actionable = [plan for plan in plans if _is_actionable_plan(plan)]
    return sorted(actionable, key=lambda p: (0 if _is_major_symbol(p.get("symbol", "")) else 1, -_conf(p)))


def _parse_plan_request(text: str, settings: dict):
    parts = (text or "").split()[1:]
    if not parts:
        symbol = "BTC_USDT"
        kv = {}
    elif "=" in parts[0]:
        symbol = "BTC_USDT"
        kv = _parse_kv(parts)
    else:
        symbol = norm_sym(parts[0])
        kv = _parse_kv(parts[1:])

    if not _is_usdt_pair(symbol):
        raise ValueError("only USDT quote pairs are supported")

    if set(kv) - {"risk", "lev", "margin"}:
        raise ValueError("unsupported plan parameter")

    deposit = float(settings["deposit"])
    _key, risk_pct = parse_setting("risk", kv.get("risk", settings["risk_pct"]))
    _key, lev = parse_setting("lev", kv.get("lev", settings["lev"]))
    _key, margin = parse_setting("margin", kv.get("margin", settings["margin"]))
    if deposit <= 0:
        raise ValueError("invalid plan parameter")
    return symbol, deposit, risk_pct, lev, margin

async def gate_access(message: types.Message) -> str | None:
    """Return paid/trial/admin when the user may run a command. Do not debit yet."""
    user_id = _user_id(message)
    if is_admin(message.from_user.id):
        return "admin"
    allowed, mode = access_manager.check_access(user_id)
    if allowed:
        return mode
    lang = get_lang(message.from_user.id)
    if mode == "cooldown":
        wait = access_manager.status(user_id)["trial_cooldown_left"]
        await message.reply(
            _t(lang, "trial_cooldown", minutes=_format_wait_minutes(wait)),
            parse_mode="HTML",
        )
        return None
    await message.reply(_payment_paywall(user_id), parse_mode="HTML")
    return None


def debit_trial(user_id: str, mode: str | None) -> None:
    if mode == "trial":
        access_manager.consume_signal(str(user_id))


async def _finish_callback(callback: types.CallbackQuery, text: str | None = None, **kwargs) -> None:
    if text is not None and callback.message is not None:
        try:
            await callback.message.edit_text(text, **kwargs)
        except Exception:
            logger.warning("callback edit failed")
    try:
        await callback.answer()
    except Exception:
        logger.warning("callback answer failed")


async def require_deposit(message: types.Message) -> bool:
    if _has_saved_deposit(message.from_user.id):
        return True
    lang = get_lang(message.from_user.id)
    await message.reply(
        _t(lang, "no_deposit"),
        parse_mode="HTML",
        reply_markup=_deposit_keyboard(lang),
    )
    return False


async def _save_plan_signal(plan, symbol, side, confidence, *, source):
    def persist():
        checked = core_plan.prepare_for_publication(plan)
        if checked is None:
            return None
        plan.update(checked)
        return st.save_signal(plan, symbol, side, confidence, source=source)
    return await asyncio.get_running_loop().run_in_executor(None, persist)


async def _send_plan_and_record(message: types.Message, plan: dict, deposit: float, risk_pct: float, lang: str) -> bool:
    symbol = plan.get("symbol", "")
    side = str((plan.get("primary") or {}).get("side", "skip")).upper()
    if not symbol or side == "SKIP":
        return False
    text = render_scan_card(
        plan,
        symbol,
        side,
        deposit,
        risk_pct,
        float(plan.get("lev") or plan.get("requested_lev") or 10),
        lang=lang,
    )
    signal_id = await _save_plan_signal(plan, symbol, side, _conf(plan), source="manual")
    if plan.get("strategy") and not signal_id:
        return False
    if signal_id:
        st.grant_signal_access(message.from_user.id, signal_id)
        text = _with_signal_identity(text, signal_id, symbol, side, lang)
    await message.reply(
        text,
        parse_mode="HTML",
        reply_markup=_open_setup_keyboard(signal_id, lang),
    )
    return True


def _access_status_text(chat_id: str, lang: str) -> str:
    status = access_manager.status(chat_id)
    access_text = (
        _t(lang, "status_active", until=format_ts(status["paid_until"]))
        if status["has_paid_access"] else _t(lang, "status_inactive")
    )
    claim = status.get("payment_claim") or {}
    claim_text = (
        "\n\n" + _t(
            lang,
            "status_payment",
            tx=html.escape(str(claim.get("tx_hash", "—"))),
            status=html.escape(str(claim.get("status", "pending"))),
        )
        if claim else ""
    )
    return _t(
        lang,
        "status_summary",
        access=access_text,
        left=status["trial_left"],
        total=FREE_TRIAL_SIGNALS,
        claim=claim_text,
    )

# ═══════════════════════════════════════════
# КОМАНДЫ — ОБЩИЕ
# ═══════════════════════════════════════════

_onboarding_handlers = bind_onboarding_handlers(onboarding_router, sys.modules[__name__])
cmd_start = _onboarding_handlers.cmd_start
handle_lang_callback = _onboarding_handlers.handle_lang_callback
handle_deposit_callback = _onboarding_handlers.handle_deposit_callback
handle_request_plan = _onboarding_handlers.handle_request_plan
handle_retry_setup = _onboarding_handlers.handle_retry_setup
handle_run_scan = _onboarding_handlers.handle_run_scan
handle_alert_later = _onboarding_handlers.handle_alert_later
handle_another_symbol = _onboarding_handlers.handle_another_symbol
handle_plan_for = _onboarding_handlers.handle_plan_for
handle_retry_spikes = _onboarding_handlers.handle_retry_spikes
handle_deposit_amount = _onboarding_handlers.handle_deposit_amount


_access_handlers = bind_access_handlers(access_router, sys.modules[__name__])
cmd_help = _access_handlers.cmd_help
cmd_subscribe = _access_handlers.cmd_subscribe
cmd_referral = _access_handlers.cmd_referral
cmd_referrals = _access_handlers.cmd_referrals
cmd_approve_referral = _access_handlers.cmd_approve_referral
cmd_reject_referral = _access_handlers.cmd_reject_referral
cmd_status = _access_handlers.cmd_status
cmd_paid = _access_handlers.cmd_paid
cmd_grant = _access_handlers.cmd_grant
cmd_revoke = _access_handlers.cmd_revoke


# ═══════════════════════════════════════════
# КОМАНДЫ — SMC (старый функционал)
# ═══════════════════════════════════════════

_trading_handlers = bind_trading_handlers(trading_router, sys.modules[__name__])
cmd_setup = _trading_handlers.cmd_setup
cmd_spikes = _trading_handlers.cmd_spikes
cmd_plan = _trading_handlers.cmd_plan
cmd_set = _trading_handlers.cmd_set
cmd_settings = _trading_handlers.cmd_settings
cmd_scan = _trading_handlers.cmd_scan
cmd_digest = _trading_handlers.cmd_digest


async def _run_digest(chat_id, settings, lang, *, status_msg=None, detail_limit=3) -> bool:
    loop = asyncio.get_event_loop()
    try:
        top_symbols = await loop.run_in_executor(None, snap.top_symbols_by_volume, SCAN_CFG["top_n_symbols"])
        symbols = _scan_symbols(top_symbols)
        results = await loop.run_in_executor(
            None,
            lambda: sc.scan_all(
                symbols,
                deposit=settings["deposit"],
                risk_pct=settings["risk_pct"],
                lev=settings["lev"],
                margin=settings["margin"],
                workers=SCAN_CFG["workers"],
            ),
        )
        ranked = _rank_actionable_plans(results)
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        summary = _t(lang, "digest_title", time=now_str, total=len(results))
        empty_markup = (
            _one_action_keyboard(lang, "request_plan", "request_plan")
            if not ranked else None
        )

        try:
            if status_msg:
                await status_msg.edit_text(summary, parse_mode="HTML", reply_markup=empty_markup)
            else:
                await bot_instance.send_message(
                    chat_id=chat_id,
                    text=summary,
                    parse_mode="HTML",
                    reply_markup=empty_markup,
                )
        except Exception:
            logger.warning("digest summary send failed")
            return False

        for plan in ranked[:detail_limit]:
            try:
                user_id = int(chat_id)
            except (TypeError, ValueError):
                user_id = 0
            side = str((plan.get("primary") or {}).get("side", "skip")).upper()
            card = render_scan_card(
                plan,
                plan.get("symbol", ""),
                side,
                settings["deposit"],
                settings["risk_pct"],
                float(plan.get("lev") or settings.get("lev") or 10),
                lang=lang,
            )
            signal_id = await _save_plan_signal(plan, plan.get("symbol", ""), side, _conf(plan), source="manual")
            if plan.get("strategy") and not signal_id:
                continue
            if signal_id and user_id:
                st.grant_signal_access(user_id, signal_id)
                card = _with_signal_identity(
                    card, signal_id, plan.get("symbol", ""), side, lang,
                )
            await bot_instance.send_message(
                chat_id=chat_id,
                text=card,
                parse_mode="HTML",
                reply_markup=_open_setup_keyboard(signal_id, lang),
            )
            await asyncio.sleep(0.4)
        return True
    except Exception as exc:
        err = _t(lang, "digest_error", error=html.escape(str(exc)))
        try:
            if status_msg:
                await status_msg.edit_text(err, parse_mode="HTML")
            else:
                await bot_instance.send_message(chat_id=chat_id, text=err, parse_mode="HTML")
        except Exception:
            logger.warning("digest error reply failed")
        return False

# ═══════════════════════════════════════════
# SMC / SPIKE ЛОГИКА (старый функционал)
# ═══════════════════════════════════════════

async def _fetch_mtf(symbol: str) -> dict:
    dfs = {"1w": None, "1d": None, "4h": None, "1h": None, "15m": None}
    for tf in dfs:
        df = await (exchange.fetch_historical_data(symbol, tf) if tf == "1w" else exchange.fetch_ohlcv(symbol, tf))
        if not df.empty:
            smart_engine.add_context_indicators(df)
            dfs[tf] = df
        await asyncio.sleep(0.05)
    return dfs


async def _handle_setup(message: types.Message, coin: str):
    mode = await gate_access(message)
    if not mode:
        return
    lang = get_lang(message.from_user.id)
    symbol = await exchange.validate_symbol(coin)
    if not symbol:
        await message.reply(_t(lang, "coin_missing", coin=html.escape(coin)), parse_mode="HTML")
        return
    await message.reply(_t(lang, "setup_scanning", symbol=html.escape(symbol)), parse_mode="HTML")
    delivered = False
    try:
        found = False
        for tf in ["4h", "1d"]:
            df = await exchange.fetch_ohlcv(symbol, tf)
            if df.empty:
                continue
            smc_res = smc_analyzer.analyze_tf(df)
            setup = smc_analyzer.find_setup(smc_res)
            if setup:
                score = smart_engine.analyze_context(df, symbol, setup["type"])
                if score.signal != SignalType.NO_TRADE:
                    dfs = await _fetch_mtf(symbol)
                    verdict = mtf_engine.analyze(dfs)
                    if verdict.setup_type.name != "NO_TRADE":
                        msg = notifier.format_smc_setup(symbol, tf, setup, score, verdict, lang=lang)
                        alert_id = _remember_personal_alert(
                            message.from_user.id,
                            symbol=symbol,
                            side="LONG" if setup.get("type") == "LONG" else "SHORT",
                            confidence=float(getattr(score, "confidence", 0) or 0) / 100.0,
                            source="smc",
                            price=setup.get("entry"),
                            entry=setup.get("entry"),
                            stop=setup.get("stop_loss"),
                            tp1=setup.get("take_profit"),
                            timeframe=tf,
                        )
                        await message.reply(msg, parse_mode="HTML", reply_markup=_open_setup_keyboard(alert_id, lang))
                        found = True
                        delivered = True
        if not found:
            safe_symbol = _callback_symbol(symbol)
            await message.reply(
                _t(lang, "setup_none", symbol=html.escape(symbol)),
                parse_mode="HTML",
                reply_markup=_one_action_keyboard(lang, "retry_setup", f"retry_setup:{safe_symbol}"),
            )
    except Exception as exc:
        await message.reply(_t(lang, "command_error", error=html.escape(str(exc))), parse_mode="HTML")
        return
    if delivered:
        debit_trial(_user_id(message), mode)


async def _handle_spikes(message: types.Message):
    mode = await gate_access(message)
    if not mode:
        return
    lang = get_lang(message.from_user.id)
    await message.reply(_t(lang, "spikes_scanning"), parse_mode="HTML")
    delivered = False
    try:
        symbols = await exchange.get_top_pairs()
        found = []
        for symbol in symbols:
            df = await exchange.fetch_ohlcv(symbol, "15m")
            if df.empty:
                continue
            ticker = await exchange.fetch_ticker_cached(symbol)
            spike = spike_scanner.scan(df, ticker=ticker)
            if spike:
                found.append((symbol, spike))
            await asyncio.sleep(0.05)
        if not found:
            await message.reply(
                _t(lang, "spikes_none"),
                parse_mode="HTML",
                reply_markup=_one_action_keyboard(lang, "retry_spikes", "retry_spikes"),
            )
            return
        for sym, spk in found[:15]:
            coin_info = await coin_info_svc.get_coin_info(sym)
            msg = notifier.format_spike_alert(sym, "15m", spk, coin_info=coin_info, lang=lang)
            alert_id = _remember_personal_alert(
                message.from_user.id,
                symbol=sym,
                side="LONG" if spk.get("direction") == "up" else "SHORT",
                confidence=float(spk.get("score") or 0) / 100.0,
                source="spike",
                price=spk.get("current_price"),
                entry=spk.get("current_price"),
                timeframe="15m",
            )
            await message.reply(msg, parse_mode="HTML", reply_markup=_open_setup_keyboard(alert_id, lang))
            delivered = True
            await asyncio.sleep(0.1)
    except Exception as exc:
        await message.reply(_t(lang, "command_error", error=html.escape(str(exc))), parse_mode="HTML")
        return
    if delivered:
        debit_trial(_user_id(message), mode)

# ═══════════════════════════════════════════
# ОБРАБОТЧИК ТЕКСТА (natural language)
# ═══════════════════════════════════════════

_free_text_handlers = bind_free_text_handler(free_text_router, sys.modules[__name__])
handle_text = _free_text_handlers.handle_text


router.include_routers(
    onboarding_router, access_router, trading_router, free_text_router,
)

# ═══════════════════════════════════════════
# ФОНОВЫЕ ЦИКЛЫ
# ═══════════════════════════════════════════

_last_plan_1h_block: int = -1  # сканируем каждый час, повтор одной монеты — не чаще 4h

# Токены которые не нужно торговать — стоковые и левериджные
_JUNK_SUFFIXES = ("STOCK", "BULL", "BEAR", "ETF", "UP", "DOWN", "3L", "3S")

def _is_junk_symbol(symbol: str) -> bool:
    market = str(symbol or "").upper().strip().split(":", 1)[0]
    base = market.replace("/", "_").replace("-", "_").removesuffix("_USDT")
    return any(base.endswith(s) for s in _JUNK_SUFFIXES)

def _is_usdt_pair(symbol: str) -> bool:
    market = str(symbol or "").upper().strip().split(":", 1)[0]
    normalized = market.replace("/", "_").replace("-", "_")
    return normalized.endswith("_USDT")

async def _deliver_localized(kind: str, key: str, cooldown_seconds: int, render, alert=None) -> int:
    """Send one localized alert. Persist history only for users who received it."""
    if not st.cooldown_ready(kind, key, cooldown_seconds):
        return 0
    delivered = 0
    signal_id = None
    saved = False
    for chat_id in list(notifier.active_users):
        try:
            user_id = int(chat_id)
        except (TypeError, ValueError):
            continue
        if alert and not saved:
            payload = alert() if callable(alert) else dict(alert)
            signal_id = st.save_alert_signal(**payload)
            saved = True
        if await notifier.send_message_to_user(
            chat_id, render(get_lang(user_id)),
            reply_markup=_open_setup_keyboard(signal_id, get_lang(user_id)),
        ):
            delivered += 1
            if signal_id:
                st.grant_signal_access(user_id, signal_id)
        await asyncio.sleep(0.1)
    if st.should_persist_sent_marker(delivered):
        st.mark_cooldown(kind, key)
    return delivered


async def _broadcast_personal(render, alert: dict | None = None) -> None:
    """Deliver a listing in each recipient's language and keep it in their history."""
    signal_id = None
    saved = False
    for chat_id in list(notifier.active_users):
        try:
            user_id = int(chat_id)
        except (TypeError, ValueError):
            continue
        if alert and not saved:
            signal_id = st.save_alert_signal(**alert)
            saved = True
        if await notifier.send_message_to_user(
            chat_id, render(get_lang(user_id)),
            reply_markup=_open_setup_keyboard(signal_id, get_lang(user_id)),
        ):
            if signal_id:
                st.grant_signal_access(user_id, signal_id)
        await asyncio.sleep(0.1)


def _listing_symbol(symbol: str) -> str | None:
    normalized = st.normalize_usdt_symbol(symbol)
    if normalized:
        return normalized
    base = re.sub(r"[^A-Z0-9]", "", str(symbol or "").upper())
    if 2 <= len(base) <= 20 and base not in {"USDT", "BINGX", "UTC"}:
        return st.normalize_usdt_symbol(f"{base}_USDT")
    return None


def _public_signal_prices() -> dict[str, float]:
    prices: dict[str, float] = {}
    for item in snap.futures_all_tickers().get("data", []):
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol") or "").upper()
        try:
            price = float(item.get("lastPrice") or item.get("price"))
        except (TypeError, ValueError):
            continue
        if symbol and price > 0:
            prices[symbol] = price
    return prices


def _public_signal_candles(
    symbol: str, interval: str = "1h", limit: int = 400
) -> list[dict]:
    """Load public candles used to restore or audit one signal."""
    payload = snap.futures_kline(symbol, interval, limit)
    rows = payload.get("data", []) if isinstance(payload, dict) else []
    return rows if isinstance(rows, list) else []


async def _deliver_pending_signal_updates(loop) -> tuple[int, int]:
    """Deliver lifecycle messages after refreshing the trade states."""
    return await deliver_pending_signal_updates(
        loop, state=st, notifier=notifier, language_for_user=get_lang,
        open_setup_keyboard=_open_setup_keyboard,
    )


_background_loops = bind_background_loops(sys.modules[__name__])
market_scanner_loop = _background_loops.market_scanner_loop
plan_scanner_loop = _background_loops.plan_scanner_loop
signal_lifecycle_loop = _background_loops.signal_lifecycle_loop
listing_watcher_loop = _background_loops.listing_watcher_loop

# ═══════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════

async def main():
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    database_url = os.getenv("DATABASE_URL", "")
    apply_migrations(database_url)
    refresh_recipients()
    lock = hold_worker_lock(database_url)
    if lock is False:
        raise SystemExit(1)
    storage = PostgresFSMStorage(database_url) if database_url else MemoryStorage()
    dp = Dispatcher(storage=storage)
    dp.include_router(router)
    try:
        await bot_instance.set_my_commands(menu_commands("en"))
        for code in ("ru", "de", "fr", "es"):
            await bot_instance.set_my_commands(menu_commands(code), language_code=code)
    except Exception:
        logger.warning("set_my_commands failed")
    await _set_panel_menu(lang="en")
    logger.info("UCB_TRADING_BOT starting")
    t1 = asyncio.create_task(market_scanner_loop())
    t2 = asyncio.create_task(plan_scanner_loop())
    t3 = asyncio.create_task(listing_watcher_loop())
    t4 = asyncio.create_task(signal_lifecycle_loop())
    try:
        await dp.start_polling(bot_instance)
    finally:
        t1.cancel(); t2.cancel(); t3.cancel(); t4.cancel()
        await exchange.close()
        await notifier.close()
        if lock is not None:
            lock.close()

if __name__ == "__main__":
    asyncio.run(main())
