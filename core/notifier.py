from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter
from core.config import ADMIN_CHAT_IDS
from core.smart_engine import MTFVerdict
import asyncio
import html
import logging
import sys
from pathlib import Path

logger = logging.getLogger("ucb.notifier")


def _tr(lang: str, key: str, **kwargs) -> str:
    root = str(Path(__file__).resolve().parents[1])
    if root not in sys.path:
        sys.path.insert(0, root)
    from trading.i18n import t

    return t(lang or "en", key, **kwargs)


def _esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=False)


def _score_percent(value) -> str:
    """Show an SMC-style 0–100 score as a percent."""
    try:
        return f"{float(value):.0f}%"
    except (TypeError, ValueError):
        return "0%"

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

    def _t(self, key: str, lang: str = "ru") -> str:
        translated = _tr(lang, f"term_{str(key or '').lower()}")
        if translated.startswith("term_"):
            translated = self.TRANSLATIONS.get(str(key or "").lower(), str(key or "").replace("_", " ").capitalize())
        return _esc(translated)

    def _legacy_t(self, key: str) -> str:
        if not key:
            return ""
        k = str(key).lower()
        return self.TRANSLATIONS.get(k, key.replace('_', ' ').capitalize())

    async def send_message(self, text: str, gated: bool = True) -> bool:
        if not self.bot:
            logger.info("notifier has no bot; message was not sent")
            return False

        if not self.active_users:
            logger.info("notifier has no recipients")
            return False

        delivered = False
        for chat_id in list(self.active_users):
            if await self.send_message_to_user(chat_id, text, gated=gated):
                delivered = True
        return delivered

    async def _deliver(self, chat_id, text: str, reply_markup=None) -> bool:
        delay = 0.0
        for attempt in range(4):
            if delay:
                await asyncio.sleep(delay)
            try:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                )
                return True
            except TelegramRetryAfter as exc:
                delay = float(getattr(exc, "retry_after", 1) or 1) + 0.1
                logger.warning(
                    "telegram flood control chat_id=%s retry_after=%s attempt=%s",
                    chat_id,
                    delay,
                    attempt + 1,
                )
            except Exception as exc:
                logger.warning(
                    "telegram send failed chat_id=%s error=%s",
                    chat_id,
                    type(exc).__name__,
                )
                return False
        logger.warning("telegram send gave up after flood control chat_id=%s", chat_id)
        return False

    async def send_message_to_user(self, chat_id, text: str, gated: bool = True, reply_markup=None) -> bool:
        """Send one alert. Trial credit is spent only after Telegram accepts it."""
        if not self.bot:
            logger.info("notifier has no bot; message was not sent chat_id=%s", chat_id)
            return False

        mode = None
        if gated and self.access_manager and str(chat_id) not in ADMIN_CHAT_IDS:
            allowed, mode = self.access_manager.check_access(str(chat_id))
            if not allowed:
                if mode == "cooldown":
                    return False
                if self.access_manager.should_send_paywall(str(chat_id)):
                    paywall = (
                        self.paywall_formatter(chat_id)
                        if self.paywall_formatter
                        else self.access_manager.format_paywall()
                    )
                    await self._deliver(chat_id, paywall)
                return False
            if mode == "trial" and self.trial_formatter:
                remaining = max(0, int(self.access_manager.status(str(chat_id))["trial_left"]) - 1)
                text += "\n\n" + self.trial_formatter(chat_id, remaining)
        delivered = await self._deliver(chat_id, text, reply_markup=reply_markup)
        if not delivered:
            return False
        if mode == "trial":
            self.access_manager.consume_signal(str(chat_id))
        return True

    async def close(self):
        pass # The bot session will be closed by the main aiogram loop

    def _money(self, value, na="н/д"):
        if value is None:
            return na
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

    def format_listing_alert(self, symbol, coin_info=None, lang="en"):
        coin_info = coin_info or {}
        na = _tr(lang, "listing_na")
        rank = coin_info.get("rank") or na
        return _tr(
            lang,
            "listing_new",
            symbol=html.escape(str(symbol)),
            name=html.escape(str(coin_info.get("name", symbol))),
            rank=html.escape(str(rank)),
            cap=html.escape(self._money(coin_info.get("market_cap"), na=na)),
            volume=html.escape(self._money(coin_info.get("volume_24h"), na=na)),
            risk=html.escape(str(coin_info.get("risk_label", "unknown"))),
        )

    def format_listing_news_alert(self, announcement, coin_info=None, lang="en"):
        coin_info = coin_info or {}
        announcement = announcement or {}
        na = _tr(lang, "listing_na")
        symbols = ", ".join(str(item) for item in announcement.get("symbols", [])) or na
        rank = coin_info.get("rank") or na
        return _tr(
            lang,
            "listing_news",
            title=html.escape(str(announcement.get("title") or na)),
            url=html.escape(str(announcement.get("url") or "")),
            symbols=html.escape(symbols),
            published=html.escape(str(announcement.get("published_at") or na)),
            name=html.escape(str(coin_info.get("name", symbols))),
            rank=html.escape(str(rank)),
            cap=html.escape(self._money(coin_info.get("market_cap"), na=na)),
            volume=html.escape(self._money(coin_info.get("volume_24h"), na=na)),
            risk=html.escape(str(coin_info.get("risk_label", "unknown"))),
        )

    def format_spike_alert(self, symbol, timeframe, spike_data, coin_info=None, lang="en"):
        coin_info = coin_info or {}
        direction = (
            _tr(lang, "spike_long") if spike_data['direction'] == 'up' else _tr(lang, "spike_short")
        )
        reasons = spike_data.get("reasons", [])
        risk_flags = spike_data.get("risk_flags", [])
        rank = coin_info.get("rank") or "н/д"
        safe_symbol = html.escape(str(symbol))
        safe_name = html.escape(str(coin_info.get('name', symbol)))
        safe_risk = html.escape(str(coin_info.get('risk_label', 'unknown')))
        safe_coin_type = html.escape(self._coin_type_text(coin_info.get('risk_label')))

        msg = (
            f"🚀 <b>{_tr(lang, 'spike_title')}: {safe_symbol}</b>\n\n"
            f"{_tr(lang, 'spike_direction')}: <b>{_esc(direction)}</b>\n"
            f"{_tr(lang, 'spike_quality')}: <b>{_esc(spike_data.get('score', 0))}/100 ({_esc(spike_data.get('quality', 'D'))})</b>\n"
            f"{_tr(lang, 'spike_timeframe')}: {_esc(timeframe)}\n\n"
            f"{_tr(lang, 'spike_price_before')}: {spike_data['start_price']:.5f}\n"
            f"{_tr(lang, 'spike_price_now')}: {spike_data['current_price']:.5f}\n"
            f"{_tr(lang, 'spike_change')}: {spike_data['pct_change']:.2f}%\n"
            f"{_tr(lang, 'spike_volume')}: x{spike_data['volume_ratio']:.1f}\n"
            f"24h Volume: {self._money(spike_data.get('quote_volume') or coin_info.get('volume_24h'))}\n\n"
            f"{_tr(lang, 'spike_coin')}: <b>{safe_name}</b>\n"
            f"CoinGecko: #{_esc(rank)}\n"
            f"Market Cap: {self._money(coin_info.get('market_cap'))}\n"
            f"{_tr(lang, 'spike_risk')}: <b>{safe_risk}</b>\n"
            f"{_tr(lang, 'spike_type')}: <b>{safe_coin_type}</b>\n"
            f"1h / 24h: {self._pct(coin_info.get('price_change_1h'))} / {self._pct(coin_info.get('price_change_24h'))}"
        )

        if reasons:
            msg += f"\n\n✅ <b>{_tr(lang, 'spike_why')}:</b>\n"
            for reason in reasons:
                msg += f"• {html.escape(str(reason))}\n"

        if risk_flags:
            msg += f"\n⚠️ <b>{_tr(lang, 'spike_risks')}:</b>\n"
            for risk in risk_flags:
                msg += f"• {html.escape(str(risk))}\n"

        return msg

    def format_smc_setup(self, symbol, timeframe, setup_data, context_score=None, verdict: MTFVerdict=None, lang="en"):
        direction_icon = "🟢 LONG" if setup_data['type'] == 'LONG' else "🔴 SHORT"
        msg = (
            f"🎯 <b>{_tr(lang, 'smc_title')}: {_esc(symbol)}</b>\n"
            f"📈 {_tr(lang, 'smc_direction')}: {_esc(direction_icon)}\n"
            f"⏱ {_tr(lang, 'spike_timeframe')}: {_esc(timeframe)}\n"
            f"🧠 {_tr(lang, 'smc_pattern')}: {_esc(setup_data['reason'])}\n\n"
        )
        
        if context_score:
            msg += (
                f"🧠 <b>{_tr(lang, 'smc_analysis')}: {_score_percent(context_score.confidence)}</b>\n"
                f"📊 {_tr(lang, 'smc_regime')}: {_esc(context_score.regime.value.upper())} | "
                f"{_tr(lang, 'smc_phase')}: {_esc(context_score.phase.value.upper())}\n"
            )
            for reason in context_score.reasons:
                msg += f"  • {_esc(reason)}\n"
            msg += "\n"

        if verdict:
            msg += (
                f"🌐 <b>MTF: {_score_percent(verdict.confidence)}</b>\n"
                f"🧭 {_tr(lang, 'smc_setup_type')}: {self._t(verdict.setup_type.name, lang)}\n"
            )
            if verdict.risk_flags:
                msg += f"⚠️ <b>{_tr(lang, 'smc_risks')}:</b>\n"
                for risk in verdict.risk_flags:
                    msg += f"  • {self._t(risk, lang)}\n"
            else:
                msg += f"✅ <b>{_tr(lang, 'smc_no_risk')}</b>\n"
            msg += "\n"

        msg += (
            f"🎯 <b>{_tr(lang, 'smc_entry')}</b>: {setup_data['entry']:.5f}\n"
            f"🛑 <b>{_tr(lang, 'smc_stop')}</b>: {setup_data['stop_loss']:.5f}\n"
            f"✅ <b>{_tr(lang, 'smc_tp')}</b>: {setup_data['take_profit']:.5f}\n"
            f"⚖️ RR: 1:{_esc(setup_data['rr'])}"
        )
        return msg

    def format_full_analysis(self, symbol, analyses, verdict: MTFVerdict, lang="en"):
        safe_symbol = _esc(symbol)
        msg_parts = [f"📊 <b>{_tr(lang, 'analysis_title')}: {safe_symbol}</b>\n"]
        msg_parts.append(f"🌐 <b>{_tr(lang, 'analysis_macro')}</b>: {self._t(verdict.macro_bias.name, lang)}")
        msg_parts.append(f"📅 <b>{_tr(lang, 'analysis_active')}</b>: {self._t(verdict.active_bias.name, lang)}")
        msg_parts.append(f"🧭 <b>{_tr(lang, 'analysis_setup')}</b>: {self._t(verdict.setup_type.name, lang)}")
        msg_parts.append(f"⚖️ <b>{_tr(lang, 'analysis_confirm')}</b>: {self._t(verdict.confirmation_state.name, lang)}")
        msg_parts.append(f"⚡️ <b>{_tr(lang, 'analysis_trigger')}</b>: {self._t(verdict.trigger_state.name, lang)}")
        msg_parts.append(f"🧠 <b>{_tr(lang, 'analysis_confidence')}</b>: {_score_percent(verdict.confidence)}\n")

        if verdict.risk_flags:
            msg_parts.append(f"⚠️ <b>{_tr(lang, 'smc_risks')}:</b>")
            for risk in verdict.risk_flags:
                msg_parts.append(f"  • {self._t(risk, lang)}")
            msg_parts.append("")
        else:
            msg_parts.append(f"✅ <b>{_tr(lang, 'analysis_clean')}</b>\n")

        tf_1h = analyses.get("1h", {})
        msg_parts.append(f"🔎 <b>{_tr(lang, 'analysis_zones')}:</b>")
        if 'fvg' in tf_1h and tf_1h['fvg']:
            last_fvg = tf_1h['fvg'][-1]
            fvg_type = _tr(lang, "bias_bull") if last_fvg['FVG'] == 1 else _tr(lang, "bias_bear")
            top = last_fvg.get('Top', 0)
            bottom = last_fvg.get('Bottom', 0)
            msg_parts.append(f"• FVG ({_esc(fvg_type)}): {bottom:.4f} - {top:.4f}")
        else:
            msg_parts.append(f"• {_tr(lang, 'analysis_no_fvg')}")

        if 'order_blocks' in tf_1h and tf_1h['order_blocks']:
            last_ob = tf_1h['order_blocks'][-1]
            ob_type = _tr(lang, "bias_bull") if last_ob['OB'] == 1 else _tr(lang, "bias_bear")
            top = last_ob.get('Top', 0)
            bottom = last_ob.get('Bottom', 0)
            msg_parts.append(f"• OB ({_esc(ob_type)}): {bottom:.4f} - {top:.4f}")

        tf_15m = analyses.get("15m", {})
        if 'liquidity' in tf_15m and tf_15m['liquidity']:
            msg_parts.append(f"\n💧 <b>{_tr(lang, 'analysis_liquidity')}:</b>")
            for liq in tf_15m['liquidity'][-2:]:
                liq_type = _tr(lang, "liq_buy") if liq['Liquidity'] == 1 else _tr(lang, "liq_sell")
                lvl = liq.get('Level', 0)
                msg_parts.append(f"• {_esc(liq_type)}: {lvl:.4f}")

        msg_parts.append(f"\n💡 <b>{_tr(lang, 'analysis_opinion')}:</b>")
        if verdict.confidence >= 70:
            msg_parts.append(_tr(lang, "analysis_high"))
        elif verdict.confidence >= 50:
            msg_parts.append(_tr(lang, "analysis_mid"))
        elif verdict.confidence >= 35:
            msg_parts.append(_tr(lang, "analysis_low"))
        else:
            msg_parts.append(_tr(lang, "analysis_none"))

        return "\n".join(msg_parts)
