from aiogram import Bot
from core.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, ADMIN_CHAT_IDS
from core.smart_engine import Regime, MTFVerdict
import asyncio
import html

class Notifier:
    TRANSLATIONS = {
        "bullish": "🟢 Бычий (Восходящий)",
        "bearish": "🔴 Медвежий (Нисходящий)",
        "neutral": "⚪️ Нейтральный (Флэт / Боковик)",
        
        "bullish_continuation": "📈 Продолжение роста",
        "bearish_continuation": "📉 Продолжение падения",
        "bullish_reversal": "🚀 Бычий разворот (Ловля дна)",
        "bearish_reversal": "🩸 Медвежий разворот (Тест хая)",
        "counter_trend_bounce": "⚠️ Опасный контр-трендовый отскок",
        "no_trade": "🚫 Вне рынка",
        
        "strong": "🟢 Сильное",
        "moderate": "🟡 Умеренное",
        "weak": "🔴 Слабое",
        "conflicting": "⚠️ Противоречивое",
        "aligned": "✅ Сформирован",
        "pending": "⏳ В процессе формирования",
        "noisy": "🌪 Рыночный шум",
        
        "countertrend_to_macro": "Сделка против макро-тренда (Высокий Риск)",
        "countertrend_context": "Локальное движение цены не поддерживает сетап",
        "neutral or mixed macro context": "Старшие ТФ смешанные или в боковике (вероятен распил)",
        "setup conflicts with active bias": "Сетап заходит против сильного дневного тренда",
        "weak_confirmation": "Слабое структурное подтверждение",
        "noisy structure": "Рваная/шумная локальная структура цены",
        "choppy range environment": "Опасная торговля внутри узкого диапазона"
    }

    def __init__(
        self,
        bot: Bot = None,
        active_users: set = None,
        access_manager=None,
        paywall_formatter=None,
        trial_formatter=None,
    ):
        self.bot = bot
        self.active_users = active_users if active_users is not None else set()
        self.access_manager = access_manager
        self.paywall_formatter = paywall_formatter
        self.trial_formatter = trial_formatter
        if TELEGRAM_CHAT_ID: # Fallback just in case
            self.active_users.add(str(TELEGRAM_CHAT_ID))
            
    def _t(self, key: str) -> str:
        if not key:
            return ""
        k = str(key).lower()
        return self.TRANSLATIONS.get(k, key.replace('_', ' ').capitalize())

    async def send_message(self, text: str, gated: bool = True):
        if not self.bot:
            print(f"[Notifier - console only] {text}")
            return

        if not self.active_users:
            print(f"[Notifier - no active users] {text}")
            return

        for chat_id in list(self.active_users):
            await self.send_message_to_user(chat_id, text, gated=gated)

    async def send_message_to_user(self, chat_id, text: str, gated: bool = True) -> bool:
        """Send one personalized alert while preserving trial/paywall checks."""
        if not self.bot:
            print(f"[Notifier - console only, {chat_id}] {text}")
            return False

        try:
            if gated and self.access_manager and str(chat_id) not in ADMIN_CHAT_IDS:
                allowed, mode = self.access_manager.consume_signal(str(chat_id))
                if not allowed:
                    if mode == "cooldown":
                        return False
                    if self.access_manager.should_send_paywall(str(chat_id)):
                        await self.bot.send_message(
                            chat_id=chat_id,
                            text=(
                                self.paywall_formatter(chat_id)
                                if self.paywall_formatter
                                else self.access_manager.format_paywall()
                            ),
                            parse_mode="HTML",
                        )
                    return False
                if mode == "trial" and self.trial_formatter:
                    remaining = self.access_manager.status(str(chat_id))["trial_left"]
                    text += "\n\n" + self.trial_formatter(chat_id, remaining)
            await self.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
            return True
        except Exception as e:
            print(f"Failed to send telegram message to {chat_id}: {e}")
            return False

    async def close(self):
        pass # The bot session will be closed by the main aiogram loop

    def _money(self, value):
        if value is None:
            return "н/д"
        try:
            value = float(value)
        except (TypeError, ValueError):
            return "н/д"
        if value >= 1_000_000_000:
            return f"${value / 1_000_000_000:.2f}B"
        if value >= 1_000_000:
            return f"${value / 1_000_000:.2f}M"
        if value >= 1_000:
            return f"${value / 1_000:.1f}K"
        return f"${value:.0f}"

    def _pct(self, value):
        if value is None:
            return "н/д"
        try:
            return f"{float(value):+.2f}%"
        except (TypeError, ValueError):
            return "н/д"

    def _coin_type_text(self, risk_label):
        labels = {
            "blue chip": "крупная монета — высокая ликвидность, риск ниже среднего",
            "large cap": "крупная/сильная монета — обычно ликвидная, риск умеренный",
            "mid cap": "средняя монета — потенциал выше, риск заметный",
            "small cap": "маленькая монета — высокая волатильность и повышенный риск",
            "micro cap": "микрокап — очень рискованная монета, возможны резкие пампы/дампы",
            "unknown": "тип не определен — данных мало, риск повышенный",
        }
        return labels.get(str(risk_label or "unknown").lower(), labels["unknown"])

    def format_listing_alert(self, symbol, coin_info=None):
        coin_info = coin_info or {}
        rank = coin_info.get("rank") or "н/д"
        safe_symbol = html.escape(str(symbol))
        safe_name = html.escape(str(coin_info.get('name', symbol)))
        safe_risk = html.escape(str(coin_info.get('risk_label', 'unknown')))
        return (
            f"🆕 <b>Новая пара на MEXC: {safe_symbol}</b>\n\n"
            f"Монета: <b>{safe_name}</b>\n"
            f"Рейтинг CoinGecko: #{rank}\n"
            f"Market Cap: {self._money(coin_info.get('market_cap'))}\n"
            f"24h Volume: {self._money(coin_info.get('volume_24h'))}\n"
            f"Риск-профиль: <b>{safe_risk}</b>\n\n"
            f"⚠️ Новые листинги часто двигаются резко. Не входи без плана и стопа."
        )

    def format_listing_news_alert(self, announcement, coin_info=None):
        coin_info = coin_info or {}
        title = html.escape(str(announcement.get("title", "MEXC listing news")))
        url = html.escape(str(announcement.get("url", "")))
        symbols = ", ".join(announcement.get("symbols", [])) or "н/д"
        rank = coin_info.get("rank") or "н/д"
        safe_name = html.escape(str(coin_info.get('name', symbols)))
        safe_risk = html.escape(str(coin_info.get('risk_label', 'unknown')))
        return (
            f"📰 <b>Новость MEXC по листингу</b>\n\n"
            f"<b>{title}</b>\n"
            f"Тикеры: <b>{html.escape(symbols)}</b>\n"
            f"Опубликовано: {html.escape(str(announcement.get('published_at', 'н/д')))}\n\n"
            f"Монета: <b>{safe_name}</b>\n"
            f"Рейтинг CoinGecko: #{rank}\n"
            f"Market Cap: {self._money(coin_info.get('market_cap'))}\n"
            f"24h Volume: {self._money(coin_info.get('volume_24h'))}\n"
            f"Риск-профиль: <b>{safe_risk}</b>\n\n"
            f"Ссылка: {url}"
        )

    def format_spike_alert(self, symbol, timeframe, spike_data, coin_info=None):
        coin_info = coin_info or {}
        direction = "🟢 LONG (Памп)" if spike_data['direction'] == 'up' else "🔴 SHORT (Дамп)"
        reasons = spike_data.get("reasons", [])
        risk_flags = spike_data.get("risk_flags", [])
        rank = coin_info.get("rank") or "н/д"
        safe_symbol = html.escape(str(symbol))
        safe_name = html.escape(str(coin_info.get('name', symbol)))
        safe_risk = html.escape(str(coin_info.get('risk_label', 'unknown')))
        safe_coin_type = html.escape(self._coin_type_text(coin_info.get('risk_label')))

        msg = (
            f"🚀 <b>УМНЫЙ СИГНАЛ: {safe_symbol}</b>\n\n"
            f"Направление: <b>{direction}</b>\n"
            f"Качество: <b>{spike_data.get('score', 0)}/100 ({spike_data.get('quality', 'D')})</b>\n"
            f"Таймфрейм: {timeframe}\n\n"
            f"Цена ДО: {spike_data['start_price']:.5f}\n"
            f"Цена СЕЙЧАС: {spike_data['current_price']:.5f}\n"
            f"Изменение цены: {spike_data['pct_change']:.2f}%\n"
            f"Объем свечи: x{spike_data['volume_ratio']:.1f} к среднему\n"
            f"24h Volume: {self._money(spike_data.get('quote_volume') or coin_info.get('volume_24h'))}\n\n"
            f"Монета: <b>{safe_name}</b>\n"
            f"Рейтинг CoinGecko: #{rank}\n"
            f"Market Cap: {self._money(coin_info.get('market_cap'))}\n"
            f"Риск-профиль: <b>{safe_risk}</b>\n"
            f"Тип монеты: <b>{safe_coin_type}</b>\n"
            f"1h / 24h: {self._pct(coin_info.get('price_change_1h'))} / {self._pct(coin_info.get('price_change_24h'))}"
        )

        if reasons:
            msg += "\n\n✅ <b>Почему сигнал важен:</b>\n"
            for reason in reasons:
                msg += f"• {html.escape(str(reason))}\n"

        if risk_flags:
            msg += "\n⚠️ <b>Риски:</b>\n"
            for risk in risk_flags:
                msg += f"• {html.escape(str(risk))}\n"

        return msg

    def format_smc_setup(self, symbol, timeframe, setup_data, context_score=None, verdict: MTFVerdict=None):
        direction_icon = "🟢 LONG" if setup_data['type'] == 'LONG' else "🔴 SHORT"
        msg = (
            f"🎯 <b>SMC СЕТАП: {symbol}</b>\n"
            f"📈 Направление: {direction_icon}\n"
            f"⏱ Таймфрейм: {timeframe}\n"
            f"🧠 Паттерн: {setup_data['reason']}\n\n"
        )
        
        if context_score:
            msg += (
                f"🧠 <b>Умный Анализ (V9): {context_score.confidence}/100</b>\n"
                f"📊 Режим: {context_score.regime.value.upper()} | Фаза: {context_score.phase.value.upper()}\n"
            )
            for reason in context_score.reasons:
                msg += f"  • {reason}\n"
            msg += "\n"

        if verdict:
            msg += (
                f"🌐 <b>MTF Fusion (V11): {verdict.confidence}/100</b>\n"
                f"🧭 Тип Сетапа: {self._t(verdict.setup_type.name)}\n"
            )
            if verdict.risk_flags:
                msg += "⚠️ <b>Факторы Риска:</b>\n"
                for risk in verdict.risk_flags:
                    msg += f"  • {self._t(risk)}\n"
            else:
                msg += "✅ <b>Факторы Риска: Отсутствуют (Рынок чист)</b>\n"
            msg += "\n"

        msg += (
            f"🎯 <b>Точка входа (Entry)</b>: {setup_data['entry']:.5f}\n"
            f"🛑 <b>Стоп-Лосс (SL)</b>: {setup_data['stop_loss']:.5f}\n"
            f"✅ <b>Тейк-Профит (TP)</b>: {setup_data['take_profit']:.5f}\n"
            f"⚖️ Risk:Reward: 1:{setup_data['rr']}"
        )
        return msg

    def format_full_analysis(self, symbol, analyses, verdict: MTFVerdict):
        msg_parts = [f"📊 <b>ПОЛНЫЙ ТЕХНИЧЕСКИЙ АНАЛИЗ (MTF Fusion V11): {symbol}</b>\n"]
        
        # 1. MTF Verdict Section
        msg_parts.append(f"🌐 <b>Макро Тренд (1W)</b>: {self._t(verdict.macro_bias.name)}")
        msg_parts.append(f"📅 <b>Активный Тренд (1D)</b>: {self._t(verdict.active_bias.name)}")
        msg_parts.append(f"🧭 <b>Тип Сетапа (4H)</b>: {self._t(verdict.setup_type.name)}")
        msg_parts.append(f"⚖️ <b>Подтверждение (1H)</b>: {self._t(verdict.confirmation_state.name)}")
        msg_parts.append(f"⚡️ <b>Триггер (15m)</b>: {self._t(verdict.trigger_state.name)}")
        msg_parts.append(f"🧠 <b>Уверенность MTF</b>: {verdict.confidence}/100\n")
        
        if verdict.risk_flags:
            msg_parts.append("⚠️ <b>Факторы Риска:</b>")
            for risk in verdict.risk_flags:
                msg_parts.append(f"  • {self._t(risk)}")
            msg_parts.append("")
        else:
            msg_parts.append("✅ <b>Риски минимальны (Синхронизация ТФ)</b>\n")
            
        # Nearest POI (FVG / OB) on 1h
        tf_1h = analyses.get("1h", {})
        msg_parts.append("🔎 <b>Ближайшие зоны интереса (1h):</b>")
        if 'fvg' in tf_1h and tf_1h['fvg']:
            last_fvg = tf_1h['fvg'][-1]
            fvg_type = "Бычий" if last_fvg['FVG'] == 1 else "Медвежий"
            top = last_fvg.get('Top', 0)
            bottom = last_fvg.get('Bottom', 0)
            msg_parts.append(f"• Свежий {fvg_type} имбаланс (FVG): {bottom:.4f} - {top:.4f}")
        else:
            msg_parts.append("• Явных имбалансов поблизости нет.")
            
        if 'order_blocks' in tf_1h and tf_1h['order_blocks']:
            last_ob = tf_1h['order_blocks'][-1]
            ob_type = "Бычий" if last_ob['OB'] == 1 else "Медвежий"
            top = last_ob.get('Top', 0)
            bottom = last_ob.get('Bottom', 0)
            msg_parts.append(f"• Актуальный {ob_type} Ордерблок (OB): {bottom:.4f} - {top:.4f}")
            
        # Liquidity on 15m
        tf_15m = analyses.get("15m", {})
        if 'liquidity' in tf_15m and tf_15m['liquidity']:
            msg_parts.append("\n💧 <b>Зоны ликвидности (15m):</b>")
            for liq in tf_15m['liquidity'][-2:]:
                liq_type = "Buy-side (Сверху)" if liq['Liquidity'] == 1 else "Sell-side (Снизу)"
                lvl = liq.get('Level', 0)
                msg_parts.append(f"• {liq_type} скопление стопов на уровне: {lvl:.4f}")
        
        # AI Verdict Context Engine Logic
        msg_parts.append("\n💡 <b>Мнение Бота:</b>")
        
        if verdict.confidence >= 70:
            msg_parts.append("Тренды синхронизированы. Рынок имеет четкое направленное движение. Идеальное время для торговли в направлении макро-тренда от ближайших зон.")
        elif verdict.confidence >= 50:
            msg_parts.append("Есть незначительные рассинхроны между таймфреймами, но общая картина понятна. Можно торговать со сниженным риском.")
        elif verdict.confidence >= 35:
            msg_parts.append("Смешанная картина. Присутствуют контр-трендовые отскоки или слабая структура. Будьте осторожны.")
        else:
            msg_parts.append("На рынке полный хаос и конфликты таймфреймов. Настоятельно рекомендуется воздержаться от сделок до прояснения ситуации.")

        return "\n".join(msg_parts)
