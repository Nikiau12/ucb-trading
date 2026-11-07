"""Per-user tracking callbacks. They never modify exchange orders."""
import asyncio
from aiogram import Router, types

def bind_personal_handlers(router: Router, services):
    @router.callback_query(lambda c: c.data and c.data.startswith('trade:'))
    async def trade_status(callback: types.CallbackQuery):
        lang = services.get_lang(callback.from_user.id)
        try:
            _, action, raw_id = callback.data.split(':')
            if action not in ('enter', 'exit') or not raw_id.isdigit():
                raise ValueError()
            active = action == 'enter'
            await asyncio.to_thread(services.st.set_trade_tracking, callback.from_user.id, int(raw_id), active)
        except Exception:
            await callback.answer(services.personal_text(lang, 'tracking_failed'), show_alert=True)
            return
        if callback.message:
            if active:
                await callback.message.edit_reply_markup(reply_markup=services._trade_keyboard(int(raw_id), lang, active=True))
            else:
                await callback.message.edit_reply_markup(reply_markup=services._open_setup_keyboard(int(raw_id), lang))
        await callback.answer(services.personal_text(lang, 'tracking_on' if active else 'tracking_off'))
