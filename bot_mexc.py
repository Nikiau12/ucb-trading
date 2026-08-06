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
from decimal import Decimal

# Keep aiohttp's pure-Python parser as defense in depth for untrusted exchange
# responses, even though the pinned aiohttp release includes the parser fixes.
os.environ.setdefault("AIOHTTP_NO_EXTENSIONS", "1")

from aiogram import Bot, Dispatcher, types, Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

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
from user_input import is_deposit_input, parse_deposit_amount

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

def load_users():
    if os.path.exists(USER_REGISTRY_FILE):
        try:
            with open(USER_REGISTRY_FILE) as f:
                return set(json.load(f))
        except Exception:
            pass
    return {str(TELEGRAM_CHAT_ID)} if TELEGRAM_CHAT_ID else set()

def save_user(chat_id: str):
    users = load_users()
    if chat_id not in users:
        users.add(chat_id)
        with open(USER_REGISTRY_FILE, "w") as f:
            json.dump(list(users), f)
        return True
    return False

def _has_saved_deposit(user_id) -> bool:
    try:
        return float(st.get_user_settings(int(user_id)).get("deposit") or 0) > 0
    except (TypeError, ValueError):
        return False


# Users without a deposit finish onboarding before receiving automatic signals.
active_users = {chat_id for chat_id in load_users() if _has_saved_deposit(chat_id)}

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


def _payment_paywall(chat_id) -> str:
    lang = get_lang(int(chat_id))
    return _t(
        lang,
        "payment_paywall",
        free_signals=FREE_TRIAL_SIGNALS,
        amount=USDT_PAYMENT_AMOUNT,
        days=PAID_ACCESS_HOURS // 24,
        network=USDT_PAYMENT_NETWORK,
        wallet=USDT_PAYMENT_ADDRESS,
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
# Notifier may add the fallback chat from the environment; onboarding still applies.
for _chat_id in list(notifier.active_users):
    if not _has_saved_deposit(_chat_id):
        notifier.active_users.discard(_chat_id)

# ═══════════════════════════════════════════
# ХЕЛПЕРЫ
# ═══════════════════════════════════════════

def is_admin(chat_id: str) -> bool:
    return str(chat_id) in ADMIN_CHAT_IDS

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
    risk_pct = float(kv.get("risk", settings["risk_pct"]))
    lev = float(kv.get("lev", settings["lev"]))
    margin = kv.get("margin", settings["margin"])
    if deposit <= 0 or risk_pct <= 0 or lev <= 0 or margin not in {"cross", "isolated"}:
        raise ValueError("invalid plan parameter")
    return symbol, deposit, risk_pct, lev, margin

async def require_access(message: types.Message) -> bool:
    chat_id = str(message.chat.id)
    if is_admin(chat_id):
        return True
    allowed, mode = access_manager.consume_signal(chat_id)
    if allowed:
        if mode == "trial":
            remaining = access_manager.status(chat_id)["trial_left"]
            await message.reply(_trial_notice(chat_id, remaining), parse_mode="HTML")
        return True
    if mode == "cooldown":
        wait = access_manager.status(chat_id)["trial_cooldown_left"]
        await message.reply(
            _t(get_lang(message.from_user.id), "trial_cooldown", minutes=_format_wait_minutes(wait)),
            parse_mode="HTML",
        )
        return False
    await message.reply(_payment_paywall(chat_id), parse_mode="HTML")
    return False


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
    signal_id = st.save_signal(plan, symbol, side, _conf(plan))
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
            tx=claim.get("tx_hash", "—"),
            status=claim.get("status", "pending"),
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
    chat_id = str(message.chat.id)
    is_new = save_user(chat_id)
    access_manager.ensure_user(chat_id)
    if is_new:
        print(f"Новый пользователь: {chat_id}")

    # Mini App payment buttons use /start subscribe_<language> deep links.
    start_payload = (message.text or "").split(maxsplit=1)
    payload = start_payload[1].strip().lower() if len(start_payload) > 1 else ""
    if payload.startswith("subscribe_"):
        lang = payload.removeprefix("subscribe_")
        if lang not in {"en", "ru", "de", "fr", "es"}:
            lang = get_lang(message.from_user.id)
        st.set_user_lang(message.from_user.id, lang)
        await state.clear()
        await message.reply(_payment_paywall(chat_id), parse_mode="HTML")
        return

    st.set_user_lang(message.from_user.id, "en")
    if not _has_saved_deposit(message.from_user.id):
        notifier.active_users.discard(chat_id)
        await state.set_state(DepositSetup.waiting_for_amount)
        await message.reply(
            ENGLISH_START_MESSAGE,
            parse_mode="HTML",
            reply_markup=_lang_keyboard("en"),
        )
        return

    notifier.active_users.add(chat_id)
    await state.clear()
    await message.reply(_t("en", "welcome"), parse_mode="HTML", reply_markup=_lang_keyboard("en"))


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
        notifier.active_users.add(str(callback.message.chat.id))
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=reply_markup)
    await callback.answer()


@router.callback_query(F.data == "set_deposit")
async def handle_deposit_callback(callback: types.CallbackQuery, state: FSMContext):
    lang = get_lang(callback.from_user.id)
    await state.set_state(DepositSetup.waiting_for_amount)
    await callback.message.reply(_t(lang, "deposit_prompt"), parse_mode="HTML")
    await callback.answer()


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
    save_user(str(message.chat.id))
    access_manager.ensure_user(str(message.chat.id))
    notifier.active_users.add(str(message.chat.id))
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
        _t(lang, "help",
           top_n=SCAN_CFG["top_n_symbols"],
           digest_hour=SCAN_CFG["daily_digest_utc_hour"]),
        parse_mode="HTML",
    )


@router.message(Command("subscribe"))
async def cmd_subscribe(message: types.Message):
    await message.reply(_payment_paywall(str(message.chat.id)), parse_mode="HTML")


@router.message(Command("status"))
async def cmd_status(message: types.Message):
    lang = get_lang(message.from_user.id)
    await message.reply(_access_status_text(str(message.chat.id), lang), parse_mode="HTML")


@router.message(Command("paid"))
async def cmd_paid(message: types.Message):
    lang = get_lang(message.from_user.id)
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply(_t(lang, "payment_paid_usage"), parse_mode="HTML")
        return
    chat_id = str(message.chat.id)
    tx_hash = parts[1].strip()
    if access_manager.find_payment_by_tx_hash(tx_hash):
        await message.reply(_t(lang, "payment_tx_used"), parse_mode="HTML")
        return

    status_msg = await message.reply(_t(lang, "payment_checking"), parse_mode="HTML")
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, payment_verifier.verify, tx_hash)
    except Exception as e:
        print(f"Payment verification failed: {e}")
        await status_msg.edit_text(_t(lang, "payment_verify_error"), parse_mode="HTML")
        return

    if not result.get("ok"):
        reason = result.get("reason")
        key = {
            "invalid_hash": "payment_invalid_hash",
            "amount_too_low": "payment_amount_low",
        }.get(reason, "payment_not_found")
        await status_msg.edit_text(
            _t(
                lang,
                key,
                paid=result.get("paid_amount", "0"),
                required=USDT_PAYMENT_AMOUNT,
            ),
            parse_mode="HTML",
        )
        return

    # Re-check after the network request to prevent two simultaneous claims.
    if access_manager.find_payment_by_tx_hash(tx_hash):
        await status_msg.edit_text(_t(lang, "payment_tx_used"), parse_mode="HTML")
        return

    payment_details = {key: value for key, value in result.items() if key not in {"ok", "tx_hash"}}
    claim = access_manager.record_payment_claim(chat_id, tx_hash, **payment_details)
    if claim is None:
        await status_msg.edit_text(_t(lang, "payment_tx_used"), parse_mode="HTML")
        return
    paid_until = access_manager.grant_access(chat_id, hours=PAID_ACCESS_HOURS)
    await status_msg.edit_text(
        _t(lang, "payment_approved", days=PAID_ACCESS_HOURS // 24, until=format_ts(paid_until)),
        parse_mode="HTML",
    )
    admin_msg = (
        f"💸 <b>Оплата подтверждена автоматически</b>\n\nUser: <code>{chat_id}</code>\n"
        f"Сумма: <b>{result['paid_amount']} USDT</b>\nTX: <code>{tx_hash}</code>\n"
        f"Доступ до: <b>{format_ts(paid_until)}</b>\n\nРезервная отмена: <code>/revoke {chat_id}</code>"
    )
    for admin_id in ADMIN_CHAT_IDS:
        try:
            await bot_instance.send_message(chat_id=admin_id, text=admin_msg, parse_mode="HTML")
        except Exception as e:
            print(f"Admin notify failed {admin_id}: {e}")


@router.message(Command("grant"))
async def cmd_grant(message: types.Message):
    if not is_admin(str(message.chat.id)):
        await message.reply("⛔️ Только для админа.")
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.reply("Использование: <code>/grant CHAT_ID [hours]</code>", parse_mode="HTML")
        return
    target = parts[1]
    hours = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else PAID_ACCESS_HOURS
    paid_until = access_manager.grant_access(target, hours=hours)
    await message.reply(
        f"✅ Доступ выдан <code>{target}</code> до <b>{format_ts(paid_until)}</b>",
        parse_mode="HTML",
    )
    try:
        await bot_instance.send_message(
            chat_id=target,
            text=f"✅ Оплата подтверждена. Доступ до <b>{format_ts(paid_until)}</b>.",
            parse_mode="HTML",
        )
    except Exception:
        pass


@router.message(Command("revoke"))
async def cmd_revoke(message: types.Message):
    if not is_admin(str(message.chat.id)):
        await message.reply("⛔️ Только для админа.")
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.reply("Использование: <code>/revoke CHAT_ID</code>", parse_mode="HTML")
        return
    access_manager.revoke_access(parts[1])
    await message.reply(f"✅ Доступ <code>{parts[1]}</code> отключен.", parse_mode="HTML")


# ═══════════════════════════════════════════
# КОМАНДЫ — SMC (старый функционал)
# ═══════════════════════════════════════════

@router.message(Command("setup"))
async def cmd_setup(message: types.Message):
    if not await require_deposit(message):
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.reply("ℹ️ Использование: <code>/setup BTC</code>", parse_mode="HTML")
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
    chat_id = str(message.chat.id)
    if not is_admin(chat_id):
        allowed, mode = access_manager.check_access(chat_id)
        if not allowed:
            if mode == "cooldown":
                wait = access_manager.status(chat_id)["trial_cooldown_left"]
                await message.reply(
                    _t(get_lang(message.from_user.id), "trial_cooldown", minutes=_format_wait_minutes(wait)),
                    parse_mode="HTML",
                )
                return
            await message.reply(_payment_paywall(chat_id), parse_mode="HTML")
            return
    uid  = message.from_user.id
    lang = get_lang(uid)
    settings = st.get_user_settings(uid)
    try:
        symbol, deposit, risk_pct, lev, margin = _parse_plan_request(message.text, settings)
    except (TypeError, ValueError):
        await message.reply(_t(lang, "plan_usage"), parse_mode="HTML")
        return

    status_msg = await message.reply(_t(lang, "plan_loading", symbol=symbol), parse_mode="HTML")
    try:
        loop     = asyncio.get_event_loop()
        snapshot = await loop.run_in_executor(None, snap.build_snapshot_with_fallback, symbol)
        plan     = core_plan.make_plan(snapshot, deposit=deposit, risk_pct=risk_pct, lev=lev, margin=margin)
        side = str((plan.get("primary") or {}).get("side", "skip")).upper()
        if not is_admin(chat_id) and side != "SKIP":
            allowed, mode = access_manager.consume_signal(chat_id)
            if not allowed:
                if mode == "cooldown":
                    wait = access_manager.status(chat_id)["trial_cooldown_left"]
                    await status_msg.edit_text(
                        _t(lang, "trial_cooldown", minutes=_format_wait_minutes(wait)),
                        parse_mode="HTML",
                    )
                    return
                await status_msg.edit_text(_payment_paywall(chat_id), parse_mode="HTML")
                return
        text     = render_telegram_plan(plan, deposit=deposit, risk_pct=risk_pct, lang=lang)
        await status_msg.edit_text(text, parse_mode="HTML")
        if side != "SKIP":
            signal_id = st.save_signal(plan, symbol, side, _conf(plan))
            if signal_id:
                st.grant_signal_access(uid, signal_id)
            if not is_admin(chat_id):
                remaining = access_manager.status(chat_id)["trial_left"]
                if access_manager.status(chat_id)["has_paid_access"] is False:
                    await message.reply(_trial_notice(chat_id, remaining), parse_mode="HTML")
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
    allowed = {"deposit": "deposit", "risk": "risk_pct", "lev": "lev", "margin": "margin"}
    updated = []
    for k, v in kv.items():
        if k not in allowed:
            await message.reply(_t(lang, "set_unknown", key=k), parse_mode="HTML")
            return
        try:
            val = v if k == "margin" else float(v)
        except ValueError:
            await message.reply(_t(lang, "deposit_invalid"), parse_mode="HTML")
            return
        if k == "deposit" and val <= 0:
            await message.reply(_t(lang, "deposit_invalid"), parse_mode="HTML")
            return
        st.set_user_setting(uid, allowed[k], val)
        updated.append(f"{k}={v}")
    if _has_saved_deposit(uid):
        save_user(str(message.chat.id))
        access_manager.ensure_user(str(message.chat.id))
        notifier.active_users.add(str(message.chat.id))
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
    text    += _t(lang, "settings_margin", val=settings["margin"])
    text    += _t(lang, "settings_change")
    text    += "\n\n━━━━━━━━━━━━━━━━\n" + _access_status_text(str(message.chat.id), lang)
    await message.reply(text, parse_mode="HTML")


@router.message(Command("scan"))
async def cmd_scan(message: types.Message):
    logger.info("command.scan.received message_id=%s", message.message_id)
    if not await require_deposit(message):
        logger.info("command.scan.deposit_required message_id=%s", message.message_id)
        return
    chat_id = str(message.chat.id)
    access_mode = "admin"
    if not is_admin(chat_id):
        allowed, access_mode = access_manager.check_access(chat_id)
        if not allowed:
            if access_mode == "cooldown":
                wait = access_manager.status(chat_id)["trial_cooldown_left"]
                await message.reply(
                    _t(get_lang(message.from_user.id), "trial_cooldown", minutes=_format_wait_minutes(wait)),
                    parse_mode="HTML",
                )
                return
            await message.reply(_payment_paywall(chat_id), parse_mode="HTML")
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
        if access_mode == "trial":
            allowed, mode = access_manager.consume_signal(chat_id)
            if not allowed:
                if mode == "cooldown":
                    wait = access_manager.status(chat_id)["trial_cooldown_left"]
                    await status_msg.edit_text(
                        _t(lang, "trial_cooldown", minutes=_format_wait_minutes(wait)),
                        parse_mode="HTML",
                    )
                    return
                await status_msg.edit_text(_payment_paywall(chat_id), parse_mode="HTML")
                return
        delivered = 0
        await status_msg.edit_text(_t(lang, "scan_done", count=min(len(actionable), limit)), parse_mode="HTML")
        for plan in actionable[:limit]:
            if await _send_plan_and_record(message, plan, deposit, settings["risk_pct"], lang):
                delivered += 1
            await asyncio.sleep(0.4)
        if access_mode == "trial":
            remaining = access_manager.status(chat_id)["trial_left"]
            await message.reply(_trial_notice(chat_id, remaining), parse_mode="HTML")
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
    if not await require_access(message):
        return
    uid      = message.from_user.id
    lang     = get_lang(uid)
    settings = st.get_user_settings(uid)
    access_status = access_manager.status(str(message.chat.id))
    detail_limit = 3 if is_admin(str(message.chat.id)) or access_status["has_paid_access"] else 1
    status_msg = await message.reply(_t(lang, "digest_preparing"), parse_mode="HTML")
    await _run_digest(str(message.chat.id), settings, lang, status_msg=status_msg, detail_limit=detail_limit)


async def _run_digest(chat_id, settings, lang, *, status_msg=None, detail_limit=3):
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
                sym  = r.get("symbol", "?")
                side = str((r.get("primary") or {}).get("side", "?")).upper()
                em   = "🟩" if side == "LONG" else "🟥"
                lines.append(f"  {em} <code>{sym}</code> {side} conf={_conf(r):.2f}")
            lines.append("")
        if medium:
            lines.append(_t(lang, "digest_medium", count=len(medium)))
            for r in medium[:10]:
                sym  = r.get("symbol", "?")
                side = str((r.get("primary") or {}).get("side", "?")).upper()
                lines.append(f"  • <code>{sym}</code> {side} conf={_conf(r):.2f}")
            lines.append("")
        lines.append(_t(lang, "digest_skipped", count=skipped))
        summary = "\n".join(lines)

        if status_msg:
            await status_msg.edit_text(summary, parse_mode="HTML")
        else:
            await bot_instance.send_message(chat_id=chat_id, text=summary, parse_mode="HTML")

        for plan in high[:detail_limit]:
            full = render_telegram_plan(plan, deposit=settings["deposit"], risk_pct=settings["risk_pct"], lang=lang)
            await bot_instance.send_message(chat_id=chat_id, text=full, parse_mode="HTML")
            try:
                user_id = int(chat_id)
            except (TypeError, ValueError):
                user_id = 0
            side = str((plan.get("primary") or {}).get("side", "skip")).upper()
            signal_id = st.save_signal(plan, plan.get("symbol", ""), side, _conf(plan))
            if signal_id and user_id:
                st.grant_signal_access(user_id, signal_id)
            await asyncio.sleep(0.4)
    except Exception as e:
        err = _t(lang, "digest_error", error=e)
        if status_msg:
            await status_msg.edit_text(err, parse_mode="HTML")
        else:
            await bot_instance.send_message(chat_id=chat_id, text=err, parse_mode="HTML")

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
    if not await require_access(message):
        return
    symbol = await exchange.validate_symbol(coin)
    if not symbol:
        await message.reply(f"❌ {coin} не найдена на MEXC.")
        return
    await message.reply(f"🔍 Анализирую {symbol} по SMC (4h / 1d)...")
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
                        msg = notifier.format_smc_setup(symbol, tf, setup, score, verdict)
                        await message.reply(msg, parse_mode="HTML")
                        found = True
        if not found:
            await message.reply(f"🤷 Нет свежих SMC сетапов по {symbol} на 4h/1d.")
    except Exception as e:
        await message.reply(f"❌ Ошибка: {e}")


async def _handle_spikes(message: types.Message):
    if not await require_access(message):
        return
    await message.reply("🚀 Сканирую всплески по Топ-250...")
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
            await message.reply("🤷 Аномалий не обнаружено.")
            return
        for sym, spk in found[:15]:
            coin_info = await coin_info_service.get_coin_info(sym)
            msg = notifier.format_spike_alert(sym, "15m", spk, coin_info=coin_info)
            await message.reply(msg, parse_mode="HTML")
            await asyncio.sleep(0.1)
    except Exception as e:
        await message.reply(f"❌ Ошибка: {e}")

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
        if not await require_access(message):
            return
        symbol = await exchange.validate_symbol(coin)
        if not symbol:
            await message.reply(f"❌ {coin} не найдена.")
            return
        await message.reply(f"🤖 Глубокий анализ {symbol} (15m→1w)...")
        try:
            dfs = await _fetch_mtf(symbol)
            analyses = {tf: smc_analyzer.analyze_tf(df) for tf, df in dfs.items() if df is not None}
            verdict = mtf_engine.analyze(dfs)
            msg = notifier.format_full_analysis(symbol, analyses, verdict)
            await message.reply(msg, parse_mode="HTML")
        except Exception as e:
            await message.reply(f"❌ Ошибка: {e}")
    elif any(kw in text for kw in ("сетап", "setup", "сигнал", "signal")) and coin:
        await _handle_setup(message, coin)

# ═══════════════════════════════════════════
# ФОНОВЫЕ ЦИКЛЫ
# ═══════════════════════════════════════════

last_spike_alert: dict = {}
last_setup_alert: dict = {}
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

def _fmt_price(p, price_unit=None) -> str:
    if p is None or p == "?":
        return "?"
    try:
        p = float(p)
        if price_unit is not None:
            unit = Decimal(str(price_unit)).normalize()
            decimals = max(0, -unit.as_tuple().exponent)
            return f"{p:,.{decimals}f}"
        if p >= 10000: return f"{p:,.0f}"
        if p >= 1000:  return f"{p:,.1f}"
        if p >= 10:    return f"{p:.2f}"
        if p >= 1:     return f"{p:.4f}"
        return f"{p:.6f}"
    except Exception:
        return str(p)

def _pct(a, b) -> str:
    try:
        return f"{abs(float(a) - float(b)) / float(b) * 100:.1f}%"
    except Exception:
        return ""

def _rr(entry, stop, tp) -> str:
    try:
        risk   = abs(float(entry) - float(stop))
        reward = abs(float(tp)    - float(entry))
        return f"RR {reward / risk:.1f}x" if risk else ""
    except Exception:
        return ""

def _fmt_usdt(value) -> str:
    try:
        return f"{float(value):,.2f}".replace(",", " ")
    except (TypeError, ValueError):
        return "—"


def _fmt_auto_alert(
    plan: dict,
    symbol: str,
    side: str,
    conf: float,
    deposit: float,
    risk_pct: float,
    leverage: float,
    uses_reference_deposit: bool = False,
) -> str:
    p       = plan.get("primary") or {}
    ctx     = plan.get("context") or {}
    tps     = p.get("tps") or []
    entry   = p.get("entry")
    stop_p  = p.get("stop")
    tp1     = tps[0]["price"] if tps else None
    tp2     = tps[1]["price"] if len(tps) > 1 else None
    price   = plan.get("price")
    price_unit = p.get("price_unit")
    regime  = str(ctx.get("regime", "")).upper() or "—"
    trend1d = str(ctx.get("trend_1d", "")).upper() or "—"
    why     = p.get("why") or []
    arrow   = "↗️" if side == "LONG" else "↘️"
    badge   = "🟢 LONG" if side == "LONG" else "🔴 SHORT"

    try:
        deposit = float(deposit)
        risk_pct = float(risk_pct)
        sizing = core_plan.position_size_for_contract(
            p, float(entry), float(stop_p), deposit, risk_pct, float(leverage)
        )
        risk_usdt = sizing["risk_usdt"]
        position_usdt = sizing["position_usdt"]
        margin_usdt = sizing["margin_usdt"]
        leverage = sizing["effective_leverage"]
        contract_vol = sizing["contract_vol"]
        leverage_limited = sizing["effective_leverage"] < sizing["requested_leverage"]
        sizing_errors = sizing["errors"]
    except (TypeError, ValueError, ZeroDivisionError):
        risk_usdt = position_usdt = margin_usdt = None
        contract_vol = None
        leverage_limited = False
        sizing_errors = []

    lines = [
        "━━━━━━━━━━━━━━━━━━",
        f"📊 <b>СИГНАЛ — {badge}</b>",
        "━━━━━━━━━━━━━━━━━━",
        "",
        f"🪙 <b><code>{symbol}</code></b>",
        f"💵 Цена сейчас: <code>{_fmt_price(price, price_unit)}</code>",
        f"🧭 Режим: <b>{regime}</b>  |  Тренд 1D: <b>{trend1d}</b>",
        f"⭐️ Уверенность: <b>{conf:.2f}</b> / 1.0",
        "",
        "─────────────────",
        f"{arrow} Вход:   <code>{_fmt_price(entry, price_unit)}</code>",
        f"🛑 Стоп:  <code>{_fmt_price(stop_p, price_unit)}</code>  ({_pct(stop_p, entry)} от входа)",
        f"🥅 TP1:   <code>{_fmt_price(tp1, price_unit)}</code>  (+{_pct(tp1, entry)})  {_rr(entry, stop_p, tp1)}",
        f"🥅 TP2:   <code>{_fmt_price(tp2, price_unit)}</code>  (+{_pct(tp2, entry)})  {_rr(entry, stop_p, tp2)}",
        "─────────────────",
        f"💰 Депозит: <b>{_fmt_usdt(deposit)} USDT</b>",
        f"📦 Объём позиции: <b>{_fmt_usdt(position_usdt)} USDT</b>",
        f"🔒 Нужно маржи при x{leverage:g}: <b>{_fmt_usdt(margin_usdt)} USDT</b>",
        f"🛡 Риск по стопу: <b>{_fmt_usdt(risk_usdt)} USDT</b> ({risk_pct:g}%)",
        "─────────────────",
    ]
    if contract_vol is not None:
        lines.insert(-1, f"📐 Контрактов MEXC: <b>{contract_vol:g}</b>")
    if leverage_limited:
        lines.insert(-1, "⚠️ Плечо снижено до максимума, разрешённого MEXC для этой монеты.")
    if "position_below_min_contract" in sizing_errors:
        lines.insert(-1, "⚠️ Для вашего риска минимальный контракт MEXC слишком велик; сделку открывать не нужно.")
    if uses_reference_deposit:
        lines.extend([
            "⚠️ <i>Расчёт на примере 1 000 USDT.</i>",
            "Укажи свой депозит через /start для личной суммы.",
            "",
        ])
    if why:
        lines.append(f"🔍 <i>{' · '.join(str(w) for w in why[:3])}</i>")
        lines.append("")
    lines.append(f"📋 Подробнее → /plan <code>{symbol}</code>")
    return "\n".join(lines)


async def market_scanner_loop():
    """Реалтайм сканер: спайки (15m) + SMC сетапы (4h/1d)."""
    while True:
        try:
            now = time.time()
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
                            if now - last_spike_alert.get(key, 0) > SPIKE_COOLDOWN:
                                coin_info = await coin_info_service.get_coin_info(symbol)
                                await notifier.send_message(
                                    notifier.format_spike_alert(symbol, tf, spike, coin_info=coin_info)
                                )
                                last_spike_alert[key] = now
                                await asyncio.sleep(0.1)

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
                            if now - last_setup_alert.get(key, 0) > SETUP_COOLDOWN:
                                await notifier.send_message(
                                    notifier.format_smc_setup(symbol, tf, setup, score, verdict)
                                )
                                last_setup_alert[key] = now
                                await asyncio.sleep(0.1)

                await asyncio.sleep(0.5)

            # чистка кэша
            now = time.time()
            last_spike_alert.update({k: v for k, v in last_spike_alert.items() if now - v <= SPIKE_COOLDOWN})
            last_setup_alert.update({k: v for k, v in last_setup_alert.items() if now - v <= SETUP_COOLDOWN})
            print("Фоновый цикл завершен. Ожидание 60 сек...")
            await asyncio.sleep(60)

        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"market_scanner_loop error: {e}")
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
                print(f"[PlanScanner] 1h block {block:02d}:00 — starting...")
                try:
                    loop = asyncio.get_event_loop()
                    symbols = await loop.run_in_executor(
                        None, snap.top_symbols_by_volume, SCAN_CFG["top_n_symbols"]
                    )
                    symbols = _scan_symbols(symbols)
                    # Используем системный дефолт для автоалёртов (без депозита пользователя)
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

                        signal_id = st.save_signal(plan, symbol, side, conf)
                        for chat_id in list(notifier.active_users):
                            try:
                                user_id = int(chat_id)
                            except (TypeError, ValueError):
                                user_id = 0
                            settings = st.get_user_settings(user_id)
                            saved_deposit = settings.get("deposit")
                            try:
                                saved_deposit = float(saved_deposit)
                            except (TypeError, ValueError):
                                saved_deposit = 0
                            uses_reference = saved_deposit <= 0
                            deposit = SCAN_REFERENCE_DEPOSIT if uses_reference else saved_deposit
                            alert = _fmt_auto_alert(
                                plan,
                                symbol,
                                side.upper(),
                                conf,
                                deposit=deposit,
                                risk_pct=settings.get("risk_pct", TRADE_CFG["default_risk_pct"]),
                                leverage=settings.get("lev", TRADE_CFG["default_lev"]),
                                uses_reference_deposit=uses_reference,
                            )
                            delivered = await notifier.send_message_to_user(chat_id, alert)
                            if delivered and signal_id:
                                st.grant_signal_access(user_id, signal_id)
                        st.mark_sent(symbol, side, conf, plan)
                        sent += 1
                        await asyncio.sleep(0.5)
                    print(f"[PlanScanner] Done: {len(results)} scanned, {sent} alerts sent")
                except Exception as e:
                    print(f"[PlanScanner] Error: {e}")

        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"plan_scanner_loop error: {e}")

        await asyncio.sleep(60)


async def listing_watcher_loop():
    while True:
        try:
            for item in (await listing_watcher.check_new_announcements())[:10]:
                symbol = item["symbols"][0] if item.get("symbols") else ""
                coin_info = await coin_info_service.get_coin_info(symbol) if symbol else {}
                await notifier.send_message(notifier.format_listing_news_alert(item, coin_info=coin_info))
                await asyncio.sleep(0.2)
            for symbol in (await listing_watcher.check_new_markets(exchange))[:20]:
                coin_info = await coin_info_service.get_coin_info(symbol)
                await notifier.send_message(notifier.format_listing_alert(symbol, coin_info=coin_info))
                await asyncio.sleep(0.2)
            await asyncio.sleep(MEXC_LISTING_CHECK_INTERVAL)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"listing_watcher_loop error: {e}")
            await asyncio.sleep(60)

# ═══════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════

async def main():
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    print("UCB_TRADING_BOT — unified system starting...")
    dp = Dispatcher()
    dp.include_router(router)
    t1 = asyncio.create_task(market_scanner_loop())
    t2 = asyncio.create_task(plan_scanner_loop())
    t3 = asyncio.create_task(listing_watcher_loop())
    try:
        await dp.start_polling(bot_instance)
    finally:
        t1.cancel(); t2.cancel(); t3.cancel()
        await exchange.close()
        await notifier.close()

if __name__ == "__main__":
    asyncio.run(main())
