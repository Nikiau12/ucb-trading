"""Telegram access, referral, payment, and admin routes."""

import asyncio
import html
from types import SimpleNamespace

import psycopg
from aiogram import Router, types
from aiogram.filters import Command


def bind_access_handlers(router: Router, services) -> SimpleNamespace:
    """Register access routes while resolving shared bot services at call time."""

    @router.message(Command("help"))
    async def cmd_help(message: types.Message):
        lang = services.get_lang(message.from_user.id)
        await message.reply(
            services._t(lang, "help", top_n=services.SCAN_CFG["top_n_symbols"]),
            parse_mode="HTML",
            reply_markup=services._help_keyboard(lang),
        )


    @router.message(Command("subscribe"))
    async def cmd_subscribe(message: types.Message):
        await message.reply(services._payment_paywall(services._user_id(message)), parse_mode="HTML")


    @router.message(Command("referral"))
    async def cmd_referral(message: types.Message):
        lang = services.get_lang(message.from_user.id)
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.reply(
                services._t(
                    lang,
                    "referral_intro",
                    price=html.escape(str(services.REFERRAL_SUBSCRIPTION_PRICE_USDT)),
                    url=html.escape(services.BINGX_REFERRAL_URL, quote=True),
                ),
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            return
        bingx_uid = parts[1].strip()
        if not bingx_uid.isdigit() or not 6 <= len(bingx_uid) <= 20:
            await message.reply(services._t(lang, "referral_invalid_uid"), parse_mode="HTML")
            return
        if not services.st.DATABASE_URL:
            await message.reply(services._t(lang, "referral_save_failed"), parse_mode="HTML")
            return
        try:
            with psycopg.connect(services.st.DATABASE_URL) as connection:
                result = services.submit_referral_claim(
                    connection,
                    user_id=message.from_user.id,
                    bingx_uid=bingx_uid,
                    referral_code=services.BINGX_REFERRAL_CODE,
                )
        except Exception:
            services.logger.warning("referral claim save failed user_id=%s", message.from_user.id)
            await message.reply(services._t(lang, "referral_save_failed"), parse_mode="HTML")
            return
        if not result.get("ok"):
            key = "referral_uid_used" if result.get("reason") == "uid_used" else "referral_save_failed"
            await message.reply(services._t(lang, key), parse_mode="HTML")
            return
        if result.get("status") == "pending":
            verification = await asyncio.to_thread(
                services.verify_direct_referral,
                result["bingx_uid"],
            )
            target_status = {
                "verified": "verified",
                "not_eligible": "rejected",
            }.get(verification["status"])
            if target_status:
                try:
                    with psycopg.connect(services.st.DATABASE_URL) as connection:
                        reviewed = services.review_referral_claim(
                            connection,
                            user_id=message.from_user.id,
                            status=target_status,
                            reviewed_by=0,
                            expected_bingx_uid=result["bingx_uid"],
                        )
                    if reviewed:
                        result["status"] = reviewed["status"]
                except Exception:
                    services.logger.exception(
                        "automatic referral review save failed user_id=%s",
                        message.from_user.id,
                    )
            else:
                services.logger.warning(
                    "automatic referral review deferred user_id=%s reason=%s",
                    message.from_user.id,
                    verification["reason"],
                )
        if result.get("status") == "verified":
            await message.reply(
                services._t(lang, "referral_verified", price=services.REFERRAL_SUBSCRIPTION_PRICE_USDT),
                parse_mode="HTML",
            )
            return
        if result.get("status") == "rejected":
            await message.reply(
                services._t(lang, "referral_rejected", code=services.BINGX_REFERRAL_CODE),
                parse_mode="HTML",
            )
            return
        await message.reply(
            services._t(
                lang,
                "referral_pending",
                uid=html.escape(result["bingx_uid"]),
                price=html.escape(str(services.REFERRAL_SUBSCRIPTION_PRICE_USDT)),
            ),
            parse_mode="HTML",
        )
        admin_text = (
            "🤝 <b>Новая заявка BingX-реферала</b>\n\n"
            f"Telegram: <code>{message.from_user.id}</code>\n"
            f"BingX UID: <code>{html.escape(result['bingx_uid'])}</code>\n"
            f"Код: <code>{html.escape(services.BINGX_REFERRAL_CODE)}</code>\n\n"
            "Автоматическая проверка BingX временно недоступна. "
            "Проверь UID в Partner Hub → Users, затем отправь:\n"
            f"<code>/approve_referral {message.from_user.id}</code>\n"
            "или\n"
            f"<code>/reject_referral {message.from_user.id}</code>"
        )
        for admin_id in services.ADMIN_CHAT_IDS:
            try:
                await services.bot_instance.send_message(admin_id, admin_text, parse_mode="HTML")
            except Exception:
                services.logger.warning("referral admin notify failed admin_id=%s", admin_id)


    @router.message(Command("referrals"))
    async def cmd_referrals(message: types.Message):
        if not services.is_admin(message.from_user.id):
            await message.reply("⛔️ Admin only.")
            return
        try:
            with psycopg.connect(services.st.DATABASE_URL) as connection:
                claims = services.pending_referral_claims(connection)
        except Exception:
            services.logger.warning("pending referrals read failed")
            await message.reply("⚠️ Не удалось получить список заявок.")
            return
        if not claims:
            await message.reply("✅ Новых заявок BingX-рефералов нет.")
            return
        lines = ["🤝 <b>Заявки BingX-рефералов</b>"]
        for claim in claims:
            lines.append(
                f"\nTelegram: <code>{claim['telegram_user_id']}</code>"
                f"\nBingX UID: <code>{html.escape(claim['bingx_uid'])}</code>"
                f"\n<code>/approve_referral {claim['telegram_user_id']}</code>"
            )
        await message.reply("\n".join(lines), parse_mode="HTML")


    async def _review_referral(message: types.Message, status: str) -> None:
        if not services.is_admin(message.from_user.id):
            await message.reply("⛔️ Admin only.")
            return
        parts = (message.text or "").split()
        if len(parts) != 2 or not parts[1].isdigit():
            command = "approve_referral" if status == "verified" else "reject_referral"
            await message.reply(f"Usage: <code>/{command} USER_ID</code>", parse_mode="HTML")
            return
        target = int(parts[1])
        try:
            with psycopg.connect(services.st.DATABASE_URL) as connection:
                reviewed = services.review_referral_claim(
                    connection,
                    user_id=target,
                    status=status,
                    reviewed_by=message.from_user.id,
                )
        except Exception:
            services.logger.warning("referral review failed target=%s status=%s", target, status)
            await message.reply("⚠️ Не удалось сохранить решение.")
            return
        if not reviewed:
            await message.reply("❌ Заявка этого пользователя не найдена.")
            return
        await message.reply(
            f"✅ Заявка <code>{target}</code>: <b>{html.escape(status)}</b>.",
            parse_mode="HTML",
        )
        user_lang = services.get_lang(target)
        key = "referral_verified" if status == "verified" else "referral_rejected"
        kwargs = (
            {"price": services.REFERRAL_SUBSCRIPTION_PRICE_USDT}
            if status == "verified"
            else {"code": services.BINGX_REFERRAL_CODE}
        )
        try:
            await services.bot_instance.send_message(target, services._t(user_lang, key, **kwargs), parse_mode="HTML")
        except Exception:
            services.logger.warning("referral review notice failed target=%s", target)


    @router.message(Command("approve_referral"))
    async def cmd_approve_referral(message: types.Message):
        await _review_referral(message, "verified")


    @router.message(Command("reject_referral"))
    async def cmd_reject_referral(message: types.Message):
        await _review_referral(message, "rejected")


    @router.message(Command("status"))
    async def cmd_status(message: types.Message):
        lang = services.get_lang(message.from_user.id)
        await message.reply(services._access_status_text(services._user_id(message), lang), parse_mode="HTML")


    @router.message(Command("paid"))
    async def cmd_paid(message: types.Message):
        lang = services.get_lang(message.from_user.id)
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            await message.reply(services._t(lang, "payment_paid_usage"), parse_mode="HTML")
            return
        user_id = services._user_id(message)
        tx_hash = parts[1].strip()
        invoice = services.access_manager.ensure_open_invoice(user_id)
        if not invoice:
            await message.reply(services._t(lang, "payment_no_invoice"), parse_mode="HTML")
            return

        status_msg = await message.reply(services._t(lang, "payment_checking"), parse_mode="HTML")
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: services.payment_verifier.verify(tx_hash, expected_amount=invoice["expected_amount"]),
            )
        except Exception:
            services.logger.warning("payment verification failed")
            await status_msg.edit_text(services._t(lang, "payment_verify_error"), parse_mode="HTML")
            return

        if not result.get("ok"):
            await status_msg.edit_text(
                services._t(
                    lang,
                    services.payment_reason_key(result.get("reason")),
                    paid=html.escape(str(result.get("paid_amount", "0"))),
                    required=html.escape(str(result.get("required_amount", invoice["expected_amount"]))),
                ),
                parse_mode="HTML",
            )
            return

        payment_details = {key: value for key, value in result.items() if key not in {"ok", "tx_hash"}}
        settled = services.access_manager.settle_payment(
            user_id,
            tx_hash,
            paid_amount=result.get("paid_amount"),
            expected_amount=invoice["expected_amount"],
            hours=services.PAID_ACCESS_HOURS,
            details=payment_details,
        )
        if not settled.get("ok"):
            await status_msg.edit_text(
                services._t(lang, services.payment_reason_key(settled.get("reason"))),
                parse_mode="HTML",
            )
            return
        paid_until = int(settled["paid_until"])
        await status_msg.edit_text(
            services._t(lang, "payment_approved", days=services.PAID_ACCESS_HOURS // 24, until=services.format_ts(paid_until)),
            parse_mode="HTML",
        )
        admin_msg = (
            "💸 <b>Payment confirmed</b>\n\n"
            f"User: <code>{html.escape(user_id)}</code>\n"
            f"Amount: <b>{html.escape(str(result.get('paid_amount')))} USDT</b>\n"
            f"TX: <code>{html.escape(tx_hash)}</code>\n"
            f"Access until: <b>{html.escape(services.format_ts(paid_until))}</b>"
        )
        for admin_id in services.ADMIN_CHAT_IDS:
            try:
                await services.bot_instance.send_message(chat_id=admin_id, text=admin_msg, parse_mode="HTML")
            except Exception:
                services.logger.warning("admin payment notify failed admin_id=%s", admin_id)


    @router.message(Command("grant"))
    async def cmd_grant(message: types.Message):
        if not services.is_admin(message.from_user.id):
            await message.reply("⛔️ Admin only.")
            return
        parts = message.text.split()
        if len(parts) < 2:
            await message.reply("Usage: <code>/grant USER_ID [hours]</code>", parse_mode="HTML")
            return
        target = parts[1]
        hours = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else services.PAID_ACCESS_HOURS
        paid_until = services.access_manager.grant_access(target, hours=hours)
        if not paid_until:
            await message.reply(services._t(services.get_lang(message.from_user.id), "payment_save_failed"), parse_mode="HTML")
            return
        safe_target = html.escape(target)
        await message.reply(
            f"✅ Access granted to <code>{safe_target}</code> until <b>{html.escape(services.format_ts(paid_until))}</b>",
            parse_mode="HTML",
        )
        try:
            await services.bot_instance.send_message(
                chat_id=target,
                text=f"✅ Access is active until <b>{html.escape(services.format_ts(paid_until))}</b>.",
                parse_mode="HTML",
            )
        except Exception:
            services.logger.warning("grant notice failed")


    @router.message(Command("revoke"))
    async def cmd_revoke(message: types.Message):
        if not services.is_admin(message.from_user.id):
            await message.reply("⛔️ Admin only.")
            return
        parts = message.text.split()
        if len(parts) < 2:
            await message.reply("Usage: <code>/revoke USER_ID</code>", parse_mode="HTML")
            return
        if not services.access_manager.revoke_access(parts[1]):
            await message.reply(services._t(services.get_lang(message.from_user.id), "payment_save_failed"), parse_mode="HTML")
            return
        await message.reply(f"✅ Access removed for <code>{html.escape(parts[1])}</code>.", parse_mode="HTML")


    return SimpleNamespace(
        cmd_help=cmd_help,
        cmd_subscribe=cmd_subscribe,
        cmd_referral=cmd_referral,
        cmd_referrals=cmd_referrals,
        cmd_approve_referral=cmd_approve_referral,
        cmd_reject_referral=cmd_reject_referral,
        cmd_status=cmd_status,
        cmd_paid=cmd_paid,
        cmd_grant=cmd_grant,
        cmd_revoke=cmd_revoke,
    )
