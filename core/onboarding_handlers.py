"""Telegram onboarding routes, registered with the bot's shared services."""

from types import SimpleNamespace

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup


def bind_onboarding_handlers(router: Router, services) -> SimpleNamespace:
    """Bind onboarding routes while resolving shared services at call time.

    The bot entrypoint still owns its services and public handler aliases. This
    keeps existing command dispatch and tests stable during the module split.
    """

    @router.message(Command("start"))
    async def cmd_start(message: types.Message, state: FSMContext):
        user_id = services._user_id(message)
        services.access_manager.ensure_user(user_id)
        services.logger.info("command.start user_id=%s", user_id)

        start_payload = (message.text or "").split(maxsplit=1)
        payload = start_payload[1].strip().lower() if len(start_payload) > 1 else ""
        lang, persist = services.language_for_start(
            services.get_lang(message.from_user.id), payload,
        )
        if persist:
            services.st.set_user_lang(message.from_user.id, lang)
        chat_id = getattr(getattr(message, "chat", None), "id", None) or message.from_user.id
        await services._set_user_commands(chat_id, lang)
        if payload.startswith("subscribe_"):
            await state.clear()
            await message.reply(services._payment_paywall(user_id), parse_mode="HTML")
            return

        await services._set_panel_menu(message.from_user.id, lang)
        if payload == "plan":
            await state.clear()
            await services.cmd_plan(
                services._CommandView(message, message.from_user, "/plan BTC_USDT"),
            )
            return
        if not services.st.language_is_chosen(message.from_user.id):
            await state.clear()
            await message.reply(
                services._t("en", "choose_lang"), parse_mode="HTML",
                reply_markup=services._language_only_keyboard(),
            )
            return
        if not services._has_saved_deposit(message.from_user.id):
            # A deposit is needed for sizing, not for eligible signal alerts.
            services.notifier.active_users.add(user_id)
            await state.set_state(services.DepositSetup.waiting_for_amount)
            await message.reply(services._t(lang, "deposit_prompt"), parse_mode="HTML")
            return

        services.notifier.active_users.add(user_id)
        await state.clear()
        settings = services.st.get_user_settings(message.from_user.id)
        await message.reply(
            services._ready_text(lang, settings.get("deposit"), settings.get("risk_pct")),
            parse_mode="HTML",
            reply_markup=services._ready_keyboard(lang),
        )

    async def continue_after_language(
        callback: types.CallbackQuery, text: str, markup: InlineKeyboardMarkup,
    ) -> None:
        """Show the next step even if editing the language screen fails."""
        message = callback.message
        if message is not None:
            try:
                await message.edit_text(text, parse_mode="HTML", reply_markup=markup)
            except Exception:
                services.logger.warning("language step edit failed")
                try:
                    await message.reply(text, parse_mode="HTML", reply_markup=markup)
                except Exception:
                    services.logger.warning("language step reply failed")
        try:
            await callback.answer()
        except Exception:
            services.logger.warning("callback answer failed")

    @router.callback_query(lambda callback: callback.data and callback.data.startswith("lang_"))
    async def handle_lang_callback(callback: types.CallbackQuery, state: FSMContext):
        lang = callback.data.split("_", 1)[1]
        services.st.set_user_lang(callback.from_user.id, lang)
        settings = services.st.get_user_settings(callback.from_user.id)
        if not settings.get("deposit"):
            services.notifier.active_users.add(str(callback.from_user.id))
            await state.set_state(services.DepositSetup.waiting_for_amount)
            text = services._t(lang, "deposit_prompt")
            markup = InlineKeyboardMarkup(inline_keyboard=[])
        else:
            services.notifier.active_users.add(str(callback.from_user.id))
            await state.clear()
            text = services._ready_text(
                lang, settings.get("deposit"), settings.get("risk_pct"),
            )
            markup = services._ready_keyboard(lang)
        await continue_after_language(callback, text, markup)
        await services._set_user_commands(callback.from_user.id, lang)
        await services._set_panel_menu(callback.from_user.id, lang)

    @router.callback_query(F.data == "set_deposit")
    async def handle_deposit_callback(callback: types.CallbackQuery, state: FSMContext):
        lang = services.get_lang(callback.from_user.id)
        await state.set_state(services.DepositSetup.waiting_for_amount)
        try:
            await callback.message.reply(services._t(lang, "deposit_prompt"), parse_mode="HTML")
        except Exception:
            services.logger.warning("deposit prompt failed")
        await services._finish_callback(callback)

    @router.callback_query(F.data == "request_plan")
    async def handle_request_plan(callback: types.CallbackQuery):
        await services._finish_callback(callback)
        if callback.message is None:
            return
        await services.cmd_plan(
            services._CommandView(callback.message, callback.from_user, "/plan BTC_USDT"),
        )

    @router.callback_query(F.data.startswith("retry_setup:"))
    async def handle_retry_setup(callback: types.CallbackQuery):
        await services._finish_callback(callback)
        if callback.message is None:
            return
        coin = services._callback_symbol(callback.data.split(":", 1)[1])
        if not coin:
            return
        await services._handle_setup(
            services._CommandView(callback.message, callback.from_user, f"/setup {coin}"),
            coin,
        )

    @router.callback_query(F.data == "run_scan")
    async def handle_run_scan(callback: types.CallbackQuery):
        await services._finish_callback(callback)
        if callback.message is None:
            return
        await services.cmd_scan(
            services._CommandView(callback.message, callback.from_user, "/scan"),
        )

    @router.callback_query(F.data == "alert_later")
    async def handle_alert_later(callback: types.CallbackQuery):
        try:
            if callback.message is not None:
                await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            services.logger.warning("later dismiss failed")
        await services._finish_callback(callback)

    @router.callback_query(F.data == "another_symbol")
    async def handle_another_symbol(callback: types.CallbackQuery):
        lang = services.get_lang(callback.from_user.id)
        try:
            if callback.message is not None:
                await callback.message.reply(
                    services._t(lang, "another_symbol_prompt"), parse_mode="HTML",
                )
        except Exception:
            services.logger.warning("another symbol prompt failed")
        await services._finish_callback(callback)

    @router.callback_query(F.data.startswith("plan_for:"))
    async def handle_plan_for(callback: types.CallbackQuery):
        await services._finish_callback(callback)
        if callback.message is None:
            return
        coin = services._callback_symbol(callback.data.split(":", 1)[1])
        if not coin:
            return
        await services.cmd_plan(
            services._CommandView(callback.message, callback.from_user, f"/plan {coin}_USDT"),
        )

    @router.callback_query(F.data == "retry_spikes")
    async def handle_retry_spikes(callback: types.CallbackQuery):
        await services._finish_callback(callback)
        if callback.message is None:
            return
        await services._handle_spikes(
            services._CommandView(callback.message, callback.from_user, "/spikes"),
        )

    @router.message(
        services.DepositSetup.waiting_for_amount,
        lambda message: services.is_deposit_input(message.text),
    )
    async def handle_deposit_amount(message: types.Message, state: FSMContext):
        lang = services.get_lang(message.from_user.id)
        try:
            deposit = services.parse_deposit_amount(message.text)
        except (TypeError, ValueError):
            text, markup = services._deposit_prompt_reply(lang)
            await message.reply(text, parse_mode="HTML", reply_markup=markup)
            return

        services.st.set_user_setting(message.from_user.id, "deposit", deposit)
        services.access_manager.ensure_user(services._user_id(message))
        services.notifier.active_users.add(services._user_id(message))
        await state.clear()
        settings = services.st.get_user_settings(message.from_user.id)
        await message.reply(
            services._ready_text(lang, deposit, settings.get("risk_pct")),
            parse_mode="HTML",
            reply_markup=services._ready_keyboard(lang),
        )

    return SimpleNamespace(
        cmd_start=cmd_start,
        handle_lang_callback=handle_lang_callback,
        handle_deposit_callback=handle_deposit_callback,
        handle_request_plan=handle_request_plan,
        handle_retry_setup=handle_retry_setup,
        handle_run_scan=handle_run_scan,
        handle_alert_later=handle_alert_later,
        handle_another_symbol=handle_another_symbol,
        handle_plan_for=handle_plan_for,
        handle_retry_spikes=handle_retry_spikes,
        handle_deposit_amount=handle_deposit_amount,
    )
