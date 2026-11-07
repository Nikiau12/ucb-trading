"""Fallback natural-language Telegram route, kept after command routers."""

from __future__ import annotations

import html
from types import SimpleNamespace

from aiogram import F, Router, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext


def bind_free_text_handler(router: Router, services) -> SimpleNamespace:
    """Register idle-state text handling without intercepting FSM dialogs."""

    @router.message(StateFilter(None), F.text)
    async def handle_text(message: types.Message, state: FSMContext | None = None):
        text = message.text.lower()
        lang = services.get_lang(message.from_user.id)
        if services.is_greeting(message.text):
            if not services.st.language_is_chosen(message.from_user.id):
                await message.reply(services._t("en", "choose_lang"), parse_mode="HTML", reply_markup=services._language_only_keyboard())
                return
            if not services._has_saved_deposit(message.from_user.id):
                if state is not None:
                    await state.set_state(services.DepositSetup.waiting_for_amount)
                await message.reply(services._t(lang, "deposit_prompt"), parse_mode="HTML")
                return
            settings = services.st.get_user_settings(message.from_user.id)
            await message.reply(
                services._ready_text(lang, settings.get("deposit"), settings.get("risk_pct")),
                parse_mode="HTML",
                reply_markup=services._ready_keyboard(lang),
            )
            return
        if services.asks_for_plan_scan(message.text):
            await services.cmd_scan(services._CommandView(message, message.from_user, "/scan"))
            return

        coin = services.mentioned_plan_symbol(message.text)

        if any(kw in text for kw in ("всплеск", "памп", "дамп", "spike", "pump", "dump")):
            await services._handle_spikes(message)
        elif any(kw in text for kw in ("анализ", "analyze", "analyse", "analysis")):
            if not coin:
                await message.reply(services._t(lang, "another_symbol_prompt"), parse_mode="HTML")
                return
            await services.cmd_plan(services._CommandView(message, message.from_user, '/plan ' + coin))
        elif any(kw in text for kw in ("сетап", "setup", "сигнал", "signal")):
            if not coin:
                await message.reply(services._t(lang, "another_symbol_prompt"), parse_mode="HTML")
                return
            await services._handle_setup(message, coin)
        else:
            symbol = services.bare_plan_symbol(message.text)
            if symbol:
                await message.reply(
                    services._t(lang, "plan_symbol_prompt", symbol=html.escape(symbol)),
                    parse_mode="HTML",
                    reply_markup=services._plan_symbol_keyboard(lang, symbol),
                )


    return SimpleNamespace(handle_text=handle_text)
