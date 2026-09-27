#!/usr/bin/env python3
"""UCB_TRADING_BOT — единая система (aiogram)
Старый функционал : SMC / MTF / спайки / листинги / access control
Новый функционал  : /plan (EMA+ATR+ADX), /scan, /digest, /set, /settings, i18n x5
"""
import asyncio
import html
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone

# Keep aiohttp's pure-Python parser as defense in depth for untrusted exchange
# responses, even though the pinned aiohttp release includes the parser fixes.
os.environ.setdefault("AIOHTTP_NO_EXTENSIONS", "1")

from aiogram import Bot, Dispatcher, types, Router, F, BaseMiddleware
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, Message, CallbackQuery

# ── старые модули ──
from mexc.exchange_client_mexc import ExchangeClient
from core.smc_analyzer import SMCAnalyzer
from core.spike_scanner import SpikeScanner
from core.notifier import Notifier
from core.smart_engine import SmartContextEngine, SignalType, MTFFusionEngine
from core.coin_info_service import CoinInfoService
from core.listing_watcher import MexcListingWatcher
from core.access_manager import AccessManager
from core.config import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, ADMIN_CHAT_IDS,
    TOP_COINS_LIMIT, TARGET_COINS,
    SMART_SPIKE_MIN_SCORE, SMART_SPIKE_MIN_QUOTE_VOLUME,
    MEXC_LISTING_SNAPSHOT_FILE, MEXC_ANNOUNCEMENTS_SNAPSHOT_FILE,
    MEXC_LISTING_CHECK_INTERVAL, MEXC_NEW_LISTINGS_URL,
    FREE_TRIAL_SIGNALS, FREE_TRIAL_COOLDOWN_MINUTES, PAID_ACCESS_HOURS,
    USDT_PAYMENT_ADDRESS, USDT_PAYMENT_AMOUNT, USDT_PAYMENT_NETWORK,
    ACCESS_STATE_FILE, USER_REGISTRY_FILE, TRONGRID_API_KEY, MINI_APP_URL,
)
from core.tron_payment import TronPaymentVerifier
from core.chat_policy import is_private_chat, language_for_start
from core.bot_commands import menu_commands
from core.payment_reasons import payment_reason_key
from core.worker_lock import hold_worker_lock
from core.fsm_storage import PostgresFSMStorage

# ── наши торговые модули из trading/ ──
_TRADING_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trading")
if _TRADING_DIR not in sys.path:
    sys.path.insert(0, _TRADING_DIR)

import mexc_snapshot as snap
import trade_plan as core_plan
import scanner as sc
import state as st
from i18n import LANG_BUTTONS, t as _t
from telegram_render import render_telegram_plan
from auto_alert import render_auto_alert
from user_input import is_deposit_input, parse_deposit_amount, parse_setting
from miniapp.schema import apply_migrations

logger = logging.getLogger("ucb.bot")

# ── конфиг сканера ──
with open(os.path.join(_TRADING_DIR, "config.json")) as _f:
    _CFG = json.load(_f)
SCAN_CFG  = _CFG["scanner"]
TRADE_CFG = _CFG["trading"]

# ── инициализация бота ──
bot_instance = Bot(token=TELEGRAM_BOT_TOKEN)
router = Router()

SPIKE_COOLDOWN = 4 * 3600
SETUP_COOLDOWN = 8 * 3600
SCAN_REFERENCE_DEPOSIT = 1000.0
MAJOR_SCAN_SYMBOLS = ["BTC_USDT", "ETH_USDT", "SOL_USDT"]
MAJOR_SCAN_MIN_CONFIDENCE = float(os.getenv("MAJOR_SCAN_MIN_CONFIDENCE", "0.50"))
ENGLISH_START_MESSAGE = (
    "👋 Welcome to <b>UCB_TRADING_BOT</b>\n\n"
    "I scan MEXC Futures 24/7, find high-probability setups and instantly calculate "
    "your exact entry, stop-loss, two take-profits and position size — "
    "all calibrated to your deposit and risk tolerance.\n\n"
    f"🎁 <b>You get {FREE_TRIAL_SIGNALS} free signals</b> — "
    f"one signal every {FREE_TRIAL_COOLDOWN_MINUTES} minutes, no payment needed.\n\n"
    "💰 <b>One step to start</b>\n"
    "Send your trading deposit as a number so I can size positions correctly.\n\n"
    "Example: <code>5000</code>"
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
listing_watcher = MexcListingWatcher(
    MEXC_LISTING_SNAPSHOT_FILE,
    announcements_snapshot_file=MEXC_ANNOUNCEMENTS_SNAPSHOT_FILE,
    announcements_url=MEXC_NEW_LISTINGS_URL,
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
    return _t(
        lang,
        "payment_paywall",
        free_signals=FREE_TRIAL_SIGNALS,
        amount=html.escape(str(invoice["expected_amount"])),
        days=PAID_ACCESS_HOURS // 24,
        network=html.escape(str(USDT_PAYMENT_NETWORK)),
        wallet=html.escape(str(USDT_PAYMENT_ADDRESS or "")),
    )


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


router.message.middleware(PrivateChatMiddleware())
router.callback_query.middleware(PrivateChatMiddleware())

# ═══════════════════════════════════════════
# ХЕЛПЕРЫ
# ═══════════════════════════════════════════

def is_admin(user_id) -> bool:
    """Admin rights follow the Telegram user id.

    ADMIN_CHAT_IDS keeps its name. In a private chat that id equals the chat
    id, so existing private-chat values still work. A group id does not.
    """
    return str(user_id) in ADMIN_CHAT_IDS

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
    for symbol in [*MAJOR_SCAN_SYMBOLS, *symbols]:
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


async def _send_plan_and_record(message: types.Message, plan: dict, deposit: float, risk_pct: float, lang: str) -> bool:
    symbol = plan.get("symbol", "")
    side = str((plan.get("primary") or {}).get("side", "skip")).upper()
    if not symbol or side == "SKIP":
        return False
    text = render_telegram_plan(plan, deposit=deposit, risk_pct=risk_pct, lang=lang)
    await message.reply(text, parse_mode="HTML")
    signal_id = st.save_signal(plan, symbol, side, _conf(plan), source="manual")
    if signal_id:
        st.grant_signal_access(message.from_user.id, signal_id)
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

@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = _user_id(message)
    access_manager.ensure_user(user_id)
    logger.info("command.start user_id=%s", user_id)

    start_payload = (message.text or "").split(maxsplit=1)
    payload = start_payload[1].strip().lower() if len(start_payload) > 1 else ""
    lang, persist = language_for_start(get_lang(message.from_user.id), payload)
    if persist:
        st.set_user_lang(message.from_user.id, lang)
    if payload.startswith("subscribe_"):
        await state.clear()
        await message.reply(_payment_paywall(user_id), parse_mode="HTML")
        return

    if not _has_saved_deposit(message.from_user.id):
        notifier.active_users.discard(user_id)
        await state.set_state(DepositSetup.waiting_for_amount)
        text = ENGLISH_START_MESSAGE if lang == "en" else (
            _t(lang, "welcome") + "\n\n" + _t(lang, "deposit_prompt")
        )
        await message.reply(text, parse_mode="HTML", reply_markup=_lang_keyboard(lang))
        return

    notifier.active_users.add(user_id)
    await state.clear()
    await message.reply(_t(lang, "welcome"), parse_mode="HTML", reply_markup=_lang_keyboard(lang))


@router.callback_query(lambda c: c.data.startswith("lang_"))
async def handle_lang_callback(callback: types.CallbackQuery, state: FSMContext):
    lang = callback.data.split("_")[1]
    st.set_user_lang(callback.from_user.id, lang)
    settings = st.get_user_settings(callback.from_user.id)
    text = _t(lang, "lang_set")
    reply_markup = None
    if not settings.get("deposit"):
        text += "\n\n" + _t(lang, "deposit_start_hint") + "\n\n" + _t(lang, "deposit_prompt")
        await state.set_state(DepositSetup.waiting_for_amount)
    else:
        notifier.active_users.add(str(callback.from_user.id))
    await _finish_callback(callback, text, parse_mode="HTML", reply_markup=reply_markup)


@router.callback_query(F.data == "set_deposit")
async def handle_deposit_callback(callback: types.CallbackQuery, state: FSMContext):
    lang = get_lang(callback.from_user.id)
    await state.set_state(DepositSetup.waiting_for_amount)
    try:
        await callback.message.reply(_t(lang, "deposit_prompt"), parse_mode="HTML")
    except Exception:
        logger.warning("deposit prompt failed")
    await _finish_callback(callback)


@router.message(
    DepositSetup.waiting_for_amount,
    lambda message: is_deposit_input(message.text),
)
async def handle_deposit_amount(message: types.Message, state: FSMContext):
    lang = get_lang(message.from_user.id)
    try:
        deposit = parse_deposit_amount(message.text)
    except (TypeError, ValueError):
        await message.reply(_t(lang, "deposit_invalid"), parse_mode="HTML")
        return

    st.set_user_setting(message.from_user.id, "deposit", deposit)
    access_manager.ensure_user(_user_id(message))
    notifier.active_users.add(_user_id(message))
    await state.clear()
    await message.reply(
        _t(lang, "deposit_saved", deposit=f"{deposit:,.2f}"),
        parse_mode="HTML",
        reply_markup=_lang_keyboard(lang),
    )


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    lang = get_lang(message.from_user.id)
    await message.reply(
        _t(lang, "help", top_n=SCAN_CFG["top_n_symbols"]),
        parse_mode="HTML",
    )


@router.message(Command("subscribe"))
async def cmd_subscribe(message: types.Message):
    await message.reply(_payment_paywall(_user_id(message)), parse_mode="HTML")


@router.message(Command("status"))
async def cmd_status(message: types.Message):
    lang = get_lang(message.from_user.id)
    await message.reply(_access_status_text(_user_id(message), lang), parse_mode="HTML")


@router.message(Command("paid"))
async def cmd_paid(message: types.Message):
    lang = get_lang(message.from_user.id)
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply(_t(lang, "payment_paid_usage"), parse_mode="HTML")
        return
    user_id = _user_id(message)
    tx_hash = parts[1].strip()
    invoice = access_manager.ensure_open_invoice(user_id)
    if not invoice:
        await message.reply(_t(lang, "payment_no_invoice"), parse_mode="HTML")
        return

    status_msg = await message.reply(_t(lang, "payment_checking"), parse_mode="HTML")
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: payment_verifier.verify(tx_hash, expected_amount=invoice["expected_amount"]),
        )
    except Exception:
        logger.warning("payment verification failed")
        await status_msg.edit_text(_t(lang, "payment_verify_error"), parse_mode="HTML")
        return

    if not result.get("ok"):
        await status_msg.edit_text(
            _t(
                lang,
                payment_reason_key(result.get("reason")),
                paid=html.escape(str(result.get("paid_amount", "0"))),
                required=html.escape(str(result.get("required_amount", invoice["expected_amount"]))),
            ),
            parse_mode="HTML",
        )
        return

    payment_details = {key: value for key, value in result.items() if key not in {"ok", "tx_hash"}}
    settled = access_manager.settle_payment(
        user_id,
        tx_hash,
        paid_amount=result.get("paid_amount"),
        expected_amount=invoice["expected_amount"],
        hours=PAID_ACCESS_HOURS,
        details=payment_details,
    )
    if not settled.get("ok"):
        await status_msg.edit_text(
            _t(lang, payment_reason_key(settled.get("reason"))),
            parse_mode="HTML",
        )
        return
    paid_until = int(settled["paid_until"])
    await status_msg.edit_text(
        _t(lang, "payment_approved", days=PAID_ACCESS_HOURS // 24, until=format_ts(paid_until)),
        parse_mode="HTML",
    )
    admin_msg = (
        "💸 <b>Payment confirmed</b>\n\n"
        f"User: <code>{html.escape(user_id)}</code>\n"
        f"Amount: <b>{html.escape(str(result.get('paid_amount')))} USDT</b>\n"
        f"TX: <code>{html.escape(tx_hash)}</code>\n"
        f"Access until: <b>{html.escape(format_ts(paid_until))}</b>"
    )
    for admin_id in ADMIN_CHAT_IDS:
        try:
            await bot_instance.send_message(chat_id=admin_id, text=admin_msg, parse_mode="HTML")
        except Exception:
            logger.warning("admin payment notify failed admin_id=%s", admin_id)


@router.message(Command("grant"))
async def cmd_grant(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.reply("⛔️ Admin only.")
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.reply("Usage: <code>/grant USER_ID [hours]</code>", parse_mode="HTML")
        return
    target = parts[1]
    hours = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else PAID_ACCESS_HOURS
    paid_until = access_manager.grant_access(target, hours=hours)
    if not paid_until:
        await message.reply(_t(get_lang(message.from_user.id), "payment_save_failed"), parse_mode="HTML")
        return
    safe_target = html.escape(target)
    await message.reply(
        f"✅ Access granted to <code>{safe_target}</code> until <b>{html.escape(format_ts(paid_until))}</b>",
        parse_mode="HTML",
    )
    try:
        await bot_instance.send_message(
            chat_id=target,
            text=f"✅ Access is active until <b>{html.escape(format_ts(paid_until))}</b>.",
            parse_mode="HTML",
        )
    except Exception:
        logger.warning("grant notice failed")


@router.message(Command("revoke"))
async def cmd_revoke(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.reply("⛔️ Admin only.")
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.reply("Usage: <code>/revoke USER_ID</code>", parse_mode="HTML")
        return
    if not access_manager.revoke_access(parts[1]):
        await message.reply(_t(get_lang(message.from_user.id), "payment_save_failed"), parse_mode="HTML")
        return
    await message.reply(f"✅ Access removed for <code>{html.escape(parts[1])}</code>.", parse_mode="HTML")


# ═══════════════════════════════════════════
# КОМАНДЫ — SMC (старый функционал)
# ═══════════════════════════════════════════

@router.message(Command("setup"))
async def cmd_setup(message: types.Message):
    if not await require_deposit(message):
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.reply(_t(get_lang(message.from_user.id), "setup_usage"), parse_mode="HTML")
        return
    await _handle_setup(message, parts[1].upper())


@router.message(Command("spikes"))
async def cmd_spikes(message: types.Message):
    if not await require_deposit(message):
        return
    await _handle_spikes(message)

# ═══════════════════════════════════════════
# КОМАНДЫ — ПЛАН (наш функционал)
# ═══════════════════════════════════════════

@router.message(Command("plan"))
async def cmd_plan(message: types.Message):
    logger.info("command.plan.received message_id=%s", message.message_id)
    if not await require_deposit(message):
        logger.info("command.plan.deposit_required message_id=%s", message.message_id)
        return
    user_id = _user_id(message)
    mode = "admin"
    if not is_admin(message.from_user.id):
        mode = await gate_access(message)
        if not mode:
            return
    uid  = message.from_user.id
    lang = get_lang(uid)
    settings = st.get_user_settings(uid)
    try:
        symbol, deposit, risk_pct, lev, margin = _parse_plan_request(message.text, settings)
    except (TypeError, ValueError):
        await message.reply(_t(lang, "plan_usage"), parse_mode="HTML")
        return

    status_msg = await message.reply(_t(lang, "plan_loading", symbol=html.escape(symbol)), parse_mode="HTML")
    try:
        loop     = asyncio.get_event_loop()
        snapshot = await loop.run_in_executor(None, snap.build_snapshot_with_fallback, symbol)
        plan     = core_plan.make_plan(snapshot, deposit=deposit, risk_pct=risk_pct, lev=lev, margin=margin)
        side = str((plan.get("primary") or {}).get("side", "skip")).upper()
        text     = render_telegram_plan(plan, deposit=deposit, risk_pct=risk_pct, lang=lang)
        await status_msg.edit_text(text, parse_mode="HTML")
        if side != "SKIP":
            signal_id = st.save_signal(plan, symbol, side, _conf(plan), source="manual")
            if signal_id:
                st.grant_signal_access(uid, signal_id)
            debit_trial(user_id, mode)
            if mode == "trial":
                remaining = access_manager.status(user_id)["trial_left"]
                await message.reply(_trial_notice(user_id, remaining), parse_mode="HTML")
    except Exception as exc:
        logger.exception("command.plan.failed symbol=%s", symbol)
        await status_msg.edit_text(
            _t(lang, "plan_error", error=html.escape(str(exc))),
            parse_mode="HTML",
        )


@router.message(Command("set"))
async def cmd_set(message: types.Message):
    uid  = message.from_user.id
    lang = get_lang(uid)
    kv   = _parse_kv(message.text.split()[1:])
    if not kv:
        await message.reply(_t(lang, "set_usage"), parse_mode="HTML")
        return
    updated = []
    for key, raw in kv.items():
        try:
            storage_key, value = parse_setting(key, raw)
        except ValueError as exc:
            reason = str(exc)
            if reason == "unknown":
                await message.reply(_t(lang, "set_unknown", key=html.escape(key)), parse_mode="HTML")
            elif reason == "deposit":
                await message.reply(_t(lang, "deposit_invalid"), parse_mode="HTML")
            else:
                await message.reply(_t(lang, "set_invalid", key=html.escape(key)), parse_mode="HTML")
            return
        st.set_user_setting(uid, storage_key, value)
        updated.append(f"{html.escape(key)}={html.escape(raw)}")
    if _has_saved_deposit(uid):
        access_manager.ensure_user(str(uid))
        notifier.active_users.add(str(uid))
    await message.reply(_t(lang, "set_saved", params=", ".join(updated)), parse_mode="HTML")


@router.message(Command("settings"))
async def cmd_settings(message: types.Message):
    uid      = message.from_user.id
    lang     = get_lang(uid)
    settings = st.get_user_settings(uid)
    deposit  = settings.get("deposit")
    text     = _t(lang, "settings_title")
    text    += _t(lang, "settings_deposit", val=f"{deposit:,.0f} USDT") if deposit else _t(lang, "settings_deposit_missing")
    text    += _t(lang, "settings_risk",   val=settings["risk_pct"])
    text    += _t(lang, "settings_lev",    val=settings["lev"])
    text    += _t(lang, "settings_margin", val=html.escape(str(settings["margin"])))
    text    += _t(lang, "settings_change")
    text    += "\n\n━━━━━━━━━━━━━━━━\n" + _access_status_text(str(uid), lang)
    await message.reply(text, parse_mode="HTML")


@router.message(Command("scan"))
async def cmd_scan(message: types.Message):
    logger.info("command.scan.received message_id=%s", message.message_id)
    if not await require_deposit(message):
        logger.info("command.scan.deposit_required message_id=%s", message.message_id)
        return
    user_id = _user_id(message)
    access_mode = "admin"
    if not is_admin(message.from_user.id):
        access_mode = await gate_access(message)
        if not access_mode:
            return
    uid      = message.from_user.id
    lang     = get_lang(uid)
    settings = st.get_user_settings(uid)
    deposit = settings["deposit"]

    status_msg = await message.reply(
        _t(lang, "scan_starting", top_n=SCAN_CFG["top_n_symbols"]), parse_mode="HTML"
    )
    loop = asyncio.get_event_loop()
    try:
        top_symbols = await loop.run_in_executor(None, snap.top_symbols_by_volume, SCAN_CFG["top_n_symbols"])
        symbols = _scan_symbols(top_symbols)
        results = await loop.run_in_executor(
            None,
            lambda: sc.scan_all(
                symbols,
                deposit=deposit,
                risk_pct=settings["risk_pct"],
                lev=settings["lev"],
                margin=settings["margin"],
                workers=SCAN_CFG["workers"],
            ),
        )
        actionable = _rank_actionable_plans(results)
        if not actionable:
            await status_msg.edit_text(_t(lang, "scan_none"), parse_mode="HTML")
            return

        limit = 1 if access_mode == "trial" else 5
        delivered = 0
        await status_msg.edit_text(_t(lang, "scan_done", count=min(len(actionable), limit)), parse_mode="HTML")
        for plan in actionable[:limit]:
            if await _send_plan_and_record(message, plan, deposit, settings["risk_pct"], lang):
                delivered += 1
            await asyncio.sleep(0.4)
        if delivered:
            debit_trial(user_id, access_mode)
        if access_mode == "trial" and delivered:
            remaining = access_manager.status(user_id)["trial_left"]
            await message.reply(_trial_notice(user_id, remaining), parse_mode="HTML")
        elif len(actionable) > limit:
            await message.reply(_t(lang, "scan_more", count=len(actionable) - limit), parse_mode="HTML")
    except Exception as exc:
        logger.exception("command.scan.failed")
        await status_msg.edit_text(
            _t(lang, "scan_error", error=html.escape(str(exc))),
            parse_mode="HTML",
        )


@router.message(Command("digest"))
async def cmd_digest(message: types.Message):
    if not await require_deposit(message):
        return
    mode = await gate_access(message)
    if not mode:
        return
    uid      = message.from_user.id
    lang     = get_lang(uid)
    settings = st.get_user_settings(uid)
    access_status = access_manager.status(str(uid))
    detail_limit = 3 if mode == "admin" or access_status["has_paid_access"] else 1
    status_msg = await message.reply(_t(lang, "digest_preparing"), parse_mode="HTML")
    delivered = await _run_digest(str(uid), settings, lang, status_msg=status_msg, detail_limit=detail_limit)
    if delivered:
        debit_trial(str(uid), mode)


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
        high    = [r for r in ranked if _conf(r) >= 0.65]
        medium  = [r for r in ranked if 0.50 <= _conf(r) < 0.65]
        skipped = len(results) - len(high) - len(medium)
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

        lines = [_t(lang, "digest_title", time=now_str, total=len(results)), ""]
        if high:
            lines.append(_t(lang, "digest_high", count=len(high)))
            for r in high[:15]:
                sym  = html.escape(str(r.get("symbol", "?")))
                side = html.escape(str((r.get("primary") or {}).get("side", "?")).upper())
                em   = "🟩" if side == "LONG" else "🟥"
                lines.append(f"  {em} <code>{sym}</code> {side} conf={_conf(r):.2f}")
            lines.append("")
        if medium:
            lines.append(_t(lang, "digest_medium", count=len(medium)))
            for r in medium[:10]:
                sym  = html.escape(str(r.get("symbol", "?")))
                side = html.escape(str((r.get("primary") or {}).get("side", "?")).upper())
                lines.append(f"  • <code>{sym}</code> {side} conf={_conf(r):.2f}")
            lines.append("")
        lines.append(_t(lang, "digest_skipped", count=skipped))
        summary = "\n".join(lines)

        try:
            if status_msg:
                await status_msg.edit_text(summary, parse_mode="HTML")
            else:
                await bot_instance.send_message(chat_id=chat_id, text=summary, parse_mode="HTML")
        except Exception:
            logger.warning("digest summary send failed")
            return False

        for plan in high[:detail_limit]:
            full = render_telegram_plan(plan, deposit=settings["deposit"], risk_pct=settings["risk_pct"], lang=lang)
            await bot_instance.send_message(chat_id=chat_id, text=full, parse_mode="HTML")
            try:
                user_id = int(chat_id)
            except (TypeError, ValueError):
                user_id = 0
            side = str((plan.get("primary") or {}).get("side", "skip")).upper()
            signal_id = st.save_signal(plan, plan.get("symbol", ""), side, _conf(plan), source="manual")
            if signal_id and user_id:
                st.grant_signal_access(user_id, signal_id)
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
                        await message.reply(msg, parse_mode="HTML")
                        found = True
                        delivered = True
        if not found:
            await message.reply(_t(lang, "setup_none", symbol=html.escape(symbol)), parse_mode="HTML")
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
            await message.reply(_t(lang, "spikes_none"), parse_mode="HTML")
            return
        for sym, spk in found[:15]:
            coin_info = await coin_info_svc.get_coin_info(sym)
            msg = notifier.format_spike_alert(sym, "15m", spk, coin_info=coin_info, lang=lang)
            await message.reply(msg, parse_mode="HTML")
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

_SKIP_WORDS = {"ПО", "НА", "ДАЙ", "И", "В", "ЗА", "THE", "A", "BY", "FOR", "OF"}

@router.message(F.text)
async def handle_text(message: types.Message):
    text  = message.text.lower()
    words = message.text.split()

    coin = next(
        (w.upper() for w in words
         if len(w) >= 2 and w.upper().isalpha() and w.upper() not in _SKIP_WORDS),
        None,
    )

    if any(kw in text for kw in ("всплеск", "памп", "дамп", "spike", "pump", "dump", "сканер")):
        await _handle_spikes(message)
    elif any(kw in text for kw in ("анализ", "analyze", "analyse")) and coin:
        mode = await gate_access(message)
        if not mode:
            return
        lang = get_lang(message.from_user.id)
        symbol = await exchange.validate_symbol(coin)
        if not symbol:
            await message.reply(_t(lang, "coin_missing", coin=html.escape(coin)), parse_mode="HTML")
            return
        await message.reply(_t(lang, "analysis_running", symbol=html.escape(symbol)), parse_mode="HTML")
        try:
            dfs = await _fetch_mtf(symbol)
            analyses = {tf: smc_analyzer.analyze_tf(df) for tf, df in dfs.items() if df is not None}
            verdict = mtf_engine.analyze(dfs)
            msg = notifier.format_full_analysis(symbol, analyses, verdict, lang=lang)
            await message.reply(msg, parse_mode="HTML")
        except Exception as exc:
            await message.reply(_t(lang, "command_error", error=html.escape(str(exc))), parse_mode="HTML")
            return
        debit_trial(_user_id(message), mode)
    elif any(kw in text for kw in ("сетап", "setup", "сигнал", "signal")) and coin:
        await _handle_setup(message, coin)

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

async def _deliver_localized(kind: str, key: str, cooldown_seconds: int, render) -> int:
    """Send one localized alert. Persist the cooldown only after a delivery."""
    if not st.cooldown_ready(kind, key, cooldown_seconds):
        return 0
    delivered = 0
    for chat_id in list(notifier.active_users):
        try:
            user_id = int(chat_id)
        except (TypeError, ValueError):
            continue
        if await notifier.send_message_to_user(chat_id, render(get_lang(user_id))):
            delivered += 1
        await asyncio.sleep(0.1)
    if st.should_persist_sent_marker(delivered):
        st.mark_cooldown(kind, key)
    return delivered


async def market_scanner_loop():
    """Реалтайм сканер: спайки (15m) + SMC сетапы (4h/1d)."""
    while True:
        try:
            cycle_started_at = time.monotonic()
            refresh_recipients()
            symbols = [symbol for symbol in await exchange.get_top_pairs() if _is_usdt_pair(symbol)]

            for i, symbol in enumerate(symbols):
                target_symbols = [f"{coin}/USDT" for coin in TARGET_COINS]
                is_smc = (i < TOP_COINS_LIMIT) or (symbol in target_symbols)

                for tf in ["15m", "4h", "1d"]:
                    df = await exchange.fetch_ohlcv(symbol, tf)
                    if df.empty:
                        continue

                    if tf == "15m":
                        ticker = await exchange.fetch_ticker_cached(symbol)
                        spike = spike_scanner.scan(df, ticker=ticker)
                        if spike:
                            if spike.get("score", 0) < SMART_SPIKE_MIN_SCORE:
                                continue
                            if spike.get("quote_volume", 0) and spike["quote_volume"] < SMART_SPIKE_MIN_QUOTE_VOLUME:
                                continue
                            key = f"{symbol}_{tf}_{spike['direction']}"
                            coin_info = await coin_info_svc.get_coin_info(symbol)
                            await _deliver_localized(
                                "spike",
                                key,
                                SPIKE_COOLDOWN,
                                lambda lang, _symbol=symbol, _tf=tf, _spike=spike, _info=coin_info: (
                                    notifier.format_spike_alert(_symbol, _tf, _spike, coin_info=_info, lang=lang)
                                ),
                            )

                    if tf in ["4h", "1d"] and is_smc:
                        smc_res = smc_analyzer.analyze_tf(df)
                        setup = smc_analyzer.find_setup(smc_res)
                        if setup:
                            score = smart_engine.analyze_context(df, symbol, setup["type"])
                            if score.signal == SignalType.NO_TRADE:
                                continue
                            dfs = await _fetch_mtf(symbol)
                            verdict = mtf_engine.analyze(dfs)
                            if verdict.setup_type.name == "NO_TRADE":
                                continue
                            key = f"{symbol}_{tf}_{setup['type']}"
                            await _deliver_localized(
                                "smc",
                                key,
                                SETUP_COOLDOWN,
                                lambda lang, _symbol=symbol, _tf=tf, _setup=setup, _score=score, _verdict=verdict: (
                                    notifier.format_smc_setup(
                                        _symbol, _tf, _setup, _score, _verdict, lang=lang
                                    )
                                ),
                            )

                await asyncio.sleep(0.5)

            st.record_runtime_health(
                "market_scanner",
                success=True,
                duration_seconds=time.monotonic() - cycle_started_at,
                details={"symbols": len(symbols)},
            )
            logger.info("market scanner cycle finished; sleeping 60s")
            await asyncio.sleep(60)

        except asyncio.CancelledError:
            break
        except Exception as exc:
            st.record_runtime_health("market_scanner", success=False, details={"error": type(exc).__name__})
            logger.warning("market_scanner_loop error: %s", type(exc).__name__)
            await asyncio.sleep(10)


async def plan_scanner_loop():
    """EMA/ATR планировщик — запускается через 5 мин после каждого закрытия 1h свечи.
    Повтор одной и той же монеты — не чаще раза в 4h (dedup в state.py).
    """
    global _last_plan_1h_block
    while True:
        try:
            now = datetime.now(timezone.utc)
            block = now.hour                      # 0..23, меняется каждый час
            minutes_since = now.minute

            if minutes_since >= 5 and _last_plan_1h_block != block:
                _last_plan_1h_block = block
                logger.info("plan scanner 1h block %02d:00 starting", block)
                scan_started_at = time.monotonic()
                try:
                    refresh_recipients()
                    loop = asyncio.get_event_loop()
                    symbols = await loop.run_in_executor(
                        None, snap.top_symbols_by_volume, SCAN_CFG["top_n_symbols"]
                    )
                    symbols = _scan_symbols(symbols)
                    results = await loop.run_in_executor(
                        None,
                        lambda: sc.scan_all(
                            symbols,
                            deposit=1000,  # reference only — position sizes in auto alerts are indicative
                            risk_pct=TRADE_CFG["default_risk_pct"],
                            lev=TRADE_CFG["default_lev"],
                            margin=TRADE_CFG["default_margin"],
                            workers=SCAN_CFG["workers"],
                        ),
                    )
                    sent = 0
                    for plan in _rank_actionable_plans(results):
                        conf   = _conf(plan)
                        symbol = plan.get("symbol", "")
                        side   = (plan.get("primary") or {}).get("side", "skip")

                        if not st.should_send_alert(symbol, side, conf, plan):
                            continue

                        signal_id = st.save_signal(plan, symbol, side, conf, source="scanner")
                        delivered_count = 0
                        for chat_id in list(notifier.active_users):
                            try:
                                user_id = int(chat_id)
                            except (TypeError, ValueError):
                                continue
                            settings = st.get_user_settings(user_id)
                            saved_deposit = settings.get("deposit")
                            try:
                                saved_deposit = float(saved_deposit)
                            except (TypeError, ValueError):
                                saved_deposit = 0
                            uses_reference = saved_deposit <= 0
                            deposit = SCAN_REFERENCE_DEPOSIT if uses_reference else saved_deposit
                            alert = render_auto_alert(
                                plan,
                                symbol,
                                side.upper(),
                                conf,
                                deposit=deposit,
                                risk_pct=settings.get("risk_pct", TRADE_CFG["default_risk_pct"]),
                                leverage=settings.get("lev", TRADE_CFG["default_lev"]),
                                lang=get_lang(user_id),
                                uses_reference_deposit=uses_reference,
                            )
                            if await notifier.send_message_to_user(chat_id, alert):
                                delivered_count += 1
                                if signal_id:
                                    st.grant_signal_access(user_id, signal_id)
                        if st.should_persist_sent_marker(delivered_count):
                            st.mark_sent(symbol, side, conf, plan)
                            sent += 1
                        await asyncio.sleep(0.5)
                    logger.info("plan scanner done: scanned=%s alerts=%s", len(results), sent)
                    st.record_runtime_health(
                        "plan_scanner",
                        success=True,
                        duration_seconds=time.monotonic() - scan_started_at,
                        details={
                            "requested": len(symbols),
                            "completed": len(results),
                            "failed": len(symbols) - len(results),
                            "stale": sum(bool(result.get("used_cache")) for result in results),
                            "alerts_sent": sent,
                        },
                    )
                except Exception as e:
                    st.record_runtime_health(
                        "plan_scanner",
                        success=False,
                        duration_seconds=time.monotonic() - scan_started_at,
                        details={"error": type(e).__name__},
                    )
                    logger.warning("plan scanner error: %s", type(e).__name__)

        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning("plan_scanner_loop error: %s", type(exc).__name__)

        await asyncio.sleep(60)


async def listing_watcher_loop():
    while True:
        try:
            for item in (await listing_watcher.check_new_announcements())[:10]:
                symbol = item["symbols"][0] if item.get("symbols") else ""
                coin_info = await coin_info_svc.get_coin_info(symbol) if symbol else {}
                await notifier.send_message(notifier.format_listing_news_alert(item, coin_info=coin_info))
                await asyncio.sleep(0.2)
            for symbol in (await listing_watcher.check_new_markets(exchange))[:20]:
                coin_info = await coin_info_svc.get_coin_info(symbol)
                await notifier.send_message(notifier.format_listing_alert(symbol, coin_info=coin_info))
                await asyncio.sleep(0.2)
            await asyncio.sleep(MEXC_LISTING_CHECK_INTERVAL)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning("listing_watcher_loop error: %s", type(exc).__name__)
            await asyncio.sleep(60)

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
        await bot_instance.set_my_commands(menu_commands())
    except Exception:
        logger.warning("set_my_commands failed")
    logger.info("UCB_TRADING_BOT starting")
    t1 = asyncio.create_task(market_scanner_loop())
    t2 = asyncio.create_task(plan_scanner_loop())
    t3 = asyncio.create_task(listing_watcher_loop())
    try:
        await dp.start_polling(bot_instance)
    finally:
        t1.cancel(); t2.cancel(); t3.cancel()
        await exchange.close()
        await notifier.close()
        if lock is not None:
            lock.close()

if __name__ == "__main__":
    asyncio.run(main())
