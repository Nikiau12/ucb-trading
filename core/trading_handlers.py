"""Telegram trading commands; scanning and planning services stay in the entrypoint."""

import asyncio
import html
from types import SimpleNamespace

from aiogram import Router, types
from aiogram.filters import Command


def bind_trading_handlers(router: Router, services) -> SimpleNamespace:
    """Register trade commands while resolving shared services at call time."""

    @router.message(Command("setup"))
    async def cmd_setup(message: types.Message):
        if not await services.require_deposit(message):
            return
        parts = message.text.split()
        if len(parts) < 2:
            await message.reply(services._t(services.get_lang(message.from_user.id), "setup_usage"), parse_mode="HTML")
            return
        await services._handle_setup(message, parts[1].upper())


    @router.message(Command("spikes"))
    async def cmd_spikes(message: types.Message):
        if not await services.require_deposit(message):
            return
        await services._handle_spikes(message)

    # ═══════════════════════════════════════════
    # КОМАНДЫ — ПЛАН (наш функционал)
    # ═══════════════════════════════════════════

    @router.message(Command("plan"))
    async def cmd_plan(message: types.Message):
        services.logger.info("command.plan.received message_id=%s", message.message_id)
        if not await services.require_deposit(message):
            services.logger.info("command.plan.deposit_required message_id=%s", message.message_id)
            return
        user_id = services._user_id(message)
        mode = "admin"
        if not services.is_admin(message.from_user.id):
            mode = await services.gate_access(message)
            if not mode:
                return
        uid  = message.from_user.id
        lang = services.get_lang(uid)
        settings = services.st.get_user_settings(uid)
        try:
            symbol, deposit, risk_pct, lev, margin = services._parse_plan_request(message.text, settings)
        except (TypeError, ValueError):
            await message.reply(services._t(lang, "plan_usage"), parse_mode="HTML")
            return

        try:
            allowed = await asyncio.to_thread(services.snap.top_symbols_by_market_cap, 100)
        except Exception:
            await message.reply(services.personal_text(lang, 'universe_unavailable'))
            return
        if symbol not in allowed or not services.st.user_accepts_symbol(uid, symbol):
            await message.reply(services.personal_text(lang, 'outside_selection'))
            return
        status_msg = await message.reply(services._t(lang, "plan_loading", symbol=html.escape(symbol)), parse_mode="HTML")
        try:
            loop     = asyncio.get_event_loop()
            snapshot = await loop.run_in_executor(None, services.snap.build_snapshot_with_fallback, symbol)
            plan     = services.core_plan.make_plan(snapshot, deposit=deposit, risk_pct=risk_pct, lev=lev, margin=margin)
            side = str((plan.get("primary") or {}).get("side", "skip")).upper()
            signal_id = None
            markup = None
            if side == "SKIP":
                text = services.render_telegram_plan(plan, deposit=deposit, risk_pct=risk_pct, lang=lang)
                markup = services._no_setup_keyboard(lang, symbol)
            else:
                text = services.render_setup(
                    plan, symbol, side, services._conf(plan), deposit, risk_pct, lev, lang=lang,
                )
                signal_id = services.st.save_signal(plan, symbol, side, services._conf(plan), source="manual")
                if signal_id:
                    services.st.grant_signal_access(uid, signal_id)
                    text = services._with_signal_identity(text, signal_id, symbol, side, lang)
                markup = services._trade_keyboard(signal_id, lang)
            await status_msg.edit_text(
                text,
                parse_mode="HTML",
                reply_markup=markup,
            )
            if side != "SKIP":
                services.debit_trial(user_id, mode)
                if mode == "trial":
                    remaining = services.access_manager.status(user_id)["trial_left"]
                    await message.reply(services._trial_notice(user_id, remaining), parse_mode="HTML")
        except Exception as exc:
            services.logger.exception("command.plan.failed symbol=%s", symbol)
            await status_msg.edit_text(
                services._t(lang, "plan_error", error=html.escape(str(exc))),
                parse_mode="HTML",
            )


    @router.message(Command("set"))
    async def cmd_set(message: types.Message):
        uid  = message.from_user.id
        lang = services.get_lang(uid)
        kv   = services._parse_kv(message.text.split()[1:])
        if not kv:
            await message.reply(
                services._t(lang, "set_usage"),
                parse_mode="HTML",
                reply_markup=services._settings_keyboard(lang),
            )
            return
        for key, raw in kv.items():
            try:
                storage_key, value = services.parse_setting(key, raw)
            except ValueError as exc:
                reason = str(exc)
                if reason == "unknown":
                    await message.reply(services._t(lang, "set_unknown", key=html.escape(key)), parse_mode="HTML")
                elif reason == "deposit":
                    text, markup = services._deposit_prompt_reply(lang)
                    await message.reply(text, parse_mode="HTML", reply_markup=markup)
                else:
                    await message.reply(services._t(lang, "set_invalid", key=html.escape(key)), parse_mode="HTML")
                return
            if storage_key == 'deposit' and services.st._db_ready():
                with services.st.psycopg.connect(services.st.DATABASE_URL) as connection:
                    if services.st.accounts.account_status(connection, uid)['connected']:
                        await message.reply(services.personal_text(lang, 'balance_managed'))
                        return
            services.st.set_user_setting(uid, storage_key, value)
        if services._has_saved_deposit(uid):
            services.access_manager.ensure_user(str(uid))
            services.notifier.active_users.add(str(uid))
        await message.reply(
            services._t(lang, "set_saved"),
            parse_mode="HTML",
            reply_markup=services._settings_keyboard(lang),
        )


    @router.message(Command("settings"))
    async def cmd_settings(message: types.Message):
        uid      = message.from_user.id
        lang     = services.get_lang(uid)
        settings = services.st.get_user_settings(uid)
        deposit  = settings.get("deposit")
        text     = services._t(lang, "settings_title")
        text    += services._t(lang, "settings_deposit", val=f"{deposit:,.0f} USDT") if deposit else services._t(lang, "settings_deposit_missing")
        text    += services._t(lang, "settings_risk",   val=settings["risk_pct"])
        text    += services._t(lang, "settings_lev",    val=settings["lev"])
        text    += services._t(lang, "settings_margin", val=html.escape(str(settings["margin"])))
        text    += services._t(lang, "settings_change")
        text    += "\n\n━━━━━━━━━━━━━━━━\n" + services._access_status_text(str(uid), lang)
        await message.reply(text, parse_mode="HTML", reply_markup=services._settings_keyboard(lang))


    @router.message(Command("scan"))
    async def cmd_scan(message: types.Message):
        services.logger.info("command.scan.received message_id=%s", message.message_id)
        if not await services.require_deposit(message):
            services.logger.info("command.scan.deposit_required message_id=%s", message.message_id)
            return
        user_id = services._user_id(message)
        access_mode = "admin"
        if not services.is_admin(message.from_user.id):
            access_mode = await services.gate_access(message)
            if not access_mode:
                return
        uid      = message.from_user.id
        lang     = services.get_lang(uid)
        settings = services.st.get_user_settings(uid)
        deposit = settings["deposit"]

        status_msg = await message.reply(
            services._t(lang, "scan_starting", top_n=services.SCAN_CFG["top_n_symbols"]), parse_mode="HTML"
        )
        loop = asyncio.get_event_loop()
        try:
            top_symbols = await loop.run_in_executor(None, services.snap.top_symbols_by_market_cap, services.SCAN_CFG["top_n_symbols"])
            symbols = [s for s in services._scan_symbols(top_symbols) if services.st.user_accepts_symbol(uid, s)]
            results = await loop.run_in_executor(
                None,
                lambda: services.sc.scan_all(
                    symbols,
                    deposit=deposit,
                    risk_pct=settings["risk_pct"],
                    lev=settings["lev"],
                    margin=settings["margin"],
                    workers=services.SCAN_CFG["workers"],
                ),
            )
            actionable = services._rank_actionable_plans(results)
            if not actionable:
                await status_msg.edit_text(
                    services._t(lang, "scan_none"),
                    parse_mode="HTML",
                    reply_markup=services._one_action_keyboard(lang, "request_plan", "request_plan"),
                )
                return

            limit = 1 if access_mode == "trial" else 5
            delivered = 0
            shown = min(len(actionable), limit)
            done_key = "scan_done_one" if limit == 1 else "scan_done"
            await status_msg.edit_text(
                services._t(lang, done_key, count=shown, limit=limit),
                parse_mode="HTML",
            )
            for plan in actionable[:limit]:
                if await services._send_plan_and_record(message, plan, deposit, settings["risk_pct"], lang):
                    delivered += 1
                await asyncio.sleep(0.4)
            if delivered:
                services.debit_trial(user_id, access_mode)
            if access_mode == "trial" and delivered:
                remaining = services.access_manager.status(user_id)["trial_left"]
                await message.reply(services._trial_notice(user_id, remaining), parse_mode="HTML")
            elif len(actionable) > limit:
                await message.reply(services._t(lang, "scan_more", count=len(actionable) - limit), parse_mode="HTML")
        except Exception as exc:
            services.logger.exception("command.scan.failed")
            await status_msg.edit_text(
                services._t(lang, "scan_error", error=html.escape(str(exc))),
                parse_mode="HTML",
            )


    @router.message(Command("digest"))
    async def cmd_digest(message: types.Message):
        if not await services.require_deposit(message):
            return
        mode = await services.gate_access(message)
        if not mode:
            return
        uid      = message.from_user.id
        lang     = services.get_lang(uid)
        settings = services.st.get_user_settings(uid)
        access_status = services.access_manager.status(str(uid))
        detail_limit = 3 if mode == "admin" or access_status["has_paid_access"] else 1
        status_msg = await message.reply(services._t(lang, "digest_preparing"), parse_mode="HTML")
        delivered = await services._run_digest(str(uid), settings, lang, status_msg=status_msg, detail_limit=detail_limit)
        if delivered:
            services.debit_trial(str(uid), mode)



    return SimpleNamespace(
        cmd_setup=cmd_setup,
        cmd_spikes=cmd_spikes,
        cmd_plan=cmd_plan,
        cmd_set=cmd_set,
        cmd_settings=cmd_settings,
        cmd_scan=cmd_scan,
        cmd_digest=cmd_digest,
    )
