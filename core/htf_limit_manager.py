import asyncio
import time
from bingx.exchange_client_bingx import ExchangeClientBingX
from core.notifier import Notifier
from smartmoneyconcepts import smc
from core.smart_engine import SmartContextEngine, Regime
from core.config import AUTO_TRADING_ENABLED, BINGX_MARGIN_PER_ORDER, BINGX_BTC_ETH_MARGIN_PER_ORDER, BINGX_LEVERAGE, TARGET_COINS

notifier = Notifier()

class HTFLimitManager:
    def __init__(self, exchange: ExchangeClientBingX):
        self.exchange = exchange
        self.symbols = [f"{coin}/USDT:USDT" for coin in TARGET_COINS]
        self.interval = 1800 # 30 минут
        self.risk_amount = BINGX_MARGIN_PER_ORDER # Default
        self.tp_ratio = 3.0 # Risk:Reward 1:3
        self.smart_engine = SmartContextEngine()

    async def get_macro_trend(self, symbol):
        df_1d = await self.exchange.fetch_ohlcv(symbol, "1d", limit=250)
        if df_1d.empty: return "CHOPPY"
        
        self.smart_engine.add_context_indicators(df_1d)
        regime = self.smart_engine.regime_classifier.classify(df_1d)
        
        if regime in [Regime.UPTREND, Regime.EXPANSION]:
            return "BULLISH"
        elif regime == Regime.DOWNTREND:
            return "BEARISH"
        return "CHOPPY"

    def get_pois(self, df, current_price):
        from smartmoneyconcepts import smc
        fvg_data = smc.fvg(df)
        df_fvg = df.copy()
        for col in ['FVG', 'Top', 'Bottom', 'MitigatedIndex']:
            df_fvg[col] = fvg_data[col]

        pois = []
        active_bulls = df_fvg[(df_fvg['FVG'] == 1) & (df_fvg['MitigatedIndex'] == 0)]
        valid_bulls = active_bulls[active_bulls['Top'] < current_price]
        if not valid_bulls.empty:
            best = valid_bulls.loc[valid_bulls['Top'].idxmax()]
            pois.append({
                'direction': 'LONG',
                'entry': best['Top'],
                'sl': best['Bottom'] - (best['Top'] - best['Bottom']) * 0.1
            })

        active_bears = df_fvg[(df_fvg['FVG'] == -1) & (df_fvg['MitigatedIndex'] == 0)]
        valid_bears = active_bears[active_bears['Bottom'] > current_price]
        if not valid_bears.empty:
            best = valid_bears.loc[valid_bears['Bottom'].idxmin()]
            pois.append({
                'direction': 'SHORT',
                'entry': best['Bottom'],
                'sl': best['Top'] + (best['Top'] - best['Bottom']) * 0.1
            })
            
        return pois

    async def run_loop(self):
        print("🚀 [HTF Sniper] Запущен агрессивный двусторонний сканер (Лимитные Капканы)")
        await asyncio.sleep(5)
        
        while True:
            try:
                if not AUTO_TRADING_ENABLED:
                    await asyncio.sleep(self.interval)
                    continue
                # 1. Определяем Глобальный Макро-Тренд по Биткоину (Вожаку)
                btc_symbol = "BTC/USDT:USDT"
                try:
                    global_macro_trend = await self.get_macro_trend(btc_symbol)
                    print(f"🌍 [HTF Sniper] Глобальный тренд рынка (по {btc_symbol}): {global_macro_trend}")
                except Exception as e:
                    print(f"Ошибка получения тренда BTC: {e}")
                    global_macro_trend = "CHOPPY" # Fallback

                for symbol in self.symbols:
                    try:
                        print(f"[HTF Sniper] Анализ {symbol}...")
                        current_price = await self.exchange.fetch_ticker_price(symbol)
                        
                        all_pois = []
                        
                        # 4H Analysis
                        df_4h = await self.exchange.fetch_ohlcv(symbol, "4h", limit=200)
                        pois_4h = self.get_pois(df_4h, current_price)
                        for p in pois_4h: p['tf'] = "4h"
                        all_pois.extend(pois_4h)
                        
                        # 30m Analysis
                        df_30m = await self.exchange.fetch_ohlcv(symbol, "30m", limit=200)
                        pois_30m = self.get_pois(df_30m, current_price)
                        for p in pois_30m: p['tf'] = "30m"
                        all_pois.extend(pois_30m)

                        # Отменяем старые LIMIT ордера по этой монете
                        open_orders = await self.exchange.exchange.fetch_open_orders(symbol)
                        limits = [o for o in open_orders if o['type'] == 'limit']
                        for o in limits:
                            await self.exchange.exchange.cancel_order(o['id'], symbol)

                        if not all_pois:
                            print(f"[HTF Sniper] Не найдено активных POI для {symbol}.")
                            continue

                        # Используем общий тренд биткоина для всех монет
                        macro_trend = global_macro_trend
                        print(f"└ Тренд для {symbol} установлен как {macro_trend} (поводырь BTC)")
                        
                        # 1. СТРОГИЙ ФИЛЬТР ПО ТРЕНДУ (Приоритет направления)
                        if macro_trend == "BULLISH":
                            all_pois = [p for p in all_pois if p['direction'] == 'LONG']
                            if all_pois: print(f"└ Бычий рынок: Разрешены только LONG капканы.")
                        elif macro_trend == "BEARISH":
                            all_pois = [p for p in all_pois if p['direction'] == 'SHORT']
                            if all_pois: print(f"└ Медвежий рынок: Разрешены только SHORT капканы.")
                        
                        # 2. ФИЛЬТР УЗКОГО БОКОВИКА (Флэт)
                        if macro_trend == "CHOPPY":
                            long_pois = [p for p in all_pois if p['direction'] == 'LONG']
                            short_pois = [p for p in all_pois if p['direction'] == 'SHORT']
                            
                            if long_pois and short_pois:
                                best_long = max(long_pois, key=lambda x: x['entry'])
                                best_short = min(short_pois, key=lambda x: x['entry'])
                                distance_pct = (best_short['entry'] - best_long['entry']) / current_price * 100
                                
                                if distance_pct < 4.0:
                                    print(f"[HTF Sniper] ⚠️ Флэт, но лимитки слишком близко ({distance_pct:.2f}% < 4.0%). Отменяем обе.")
                                    all_pois = []
                                else:
                                    print(f"[HTF Sniper] ⚖️ Флэт. Широкий канал ({distance_pct:.2f}%). Разрешены двусторонние капканы.")
                        
                        if not all_pois:
                            continue

                        # Расставляем новые капканы
                        alert_messages = []
                        for poi in all_pois:
                            direction = poi['direction']
                            tf = poi['tf']
                            entry_price = poi['entry']
                            stop_loss = float(poi['sl'])
                            
                            if entry_price == stop_loss: continue
                                
                            distance_to_sl = abs(entry_price - stop_loss)
                            if distance_to_sl / entry_price < 0.005: # Слишком узкий стоп (менее 0.5% движения)
                                if direction == "LONG": stop_loss = entry_price * 0.99
                                else: stop_loss = entry_price * 1.01
                                distance_to_sl = abs(entry_price - stop_loss)
                                
                            tp_price = entry_price + (distance_to_sl * self.tp_ratio) if direction == "LONG" else entry_price - (distance_to_sl * self.tp_ratio)

                            is_btc_eth = any(coin in symbol for coin in ['BTC', 'ETH'])
                            current_risk = BINGX_BTC_ETH_MARGIN_PER_ORDER if is_btc_eth else self.risk_amount
                            position_coin_size = (current_risk * BINGX_LEVERAGE) / entry_price
                            side = 'buy' if direction == "LONG" else 'sell'
                            
                            order = await self.exchange.create_limit_order_with_sl_tp(
                                symbol=symbol, side=side, amount=position_coin_size, 
                                price=entry_price, stop_loss=stop_loss, take_profit=tp_price
                            )
                            
                            if order:
                                alert_messages.append(
                                    f"• <b>{tf}</b> {'🟢 LONG' if direction == 'LONG' else '🔴 SHORT'}: Вход <b>{entry_price:.4f}</b> (SL: {stop_loss:.4f}, TP: {tp_price:.4f})"
                                )

                        if alert_messages:
                            mode_text = "🟢 ТОЛЬКО LONG" if macro_trend == "BULLISH" else ("🔴 ТОЛЬКО SHORT" if macro_trend == "BEARISH" else "⚖️ ОБЕ СТОРОНЫ (Широкий Флэт)")
                            msg = (f"🎯 <b>[HTF Снайпер - Капканы Расставлены]</b> 🎯\n\n"
                                   f"Монета: <b>{symbol}</b>\n"
                                   f"Режим тренда (1D): <b>{mode_text}</b>\n\n" + 
                                   "\n".join(alert_messages))
                            await notifier.send_message(msg)

                    except Exception as e:
                        print(f"Ошибка в сканере HTF {symbol}: {e}")
                        
            except Exception as e:
                print(f"Критическая ошибка HTF цикла: {e}")
                
            print(f"[HTF Sniper] Цикл завершен. Ожидание {self.interval // 60} минут...")
            await asyncio.sleep(self.interval)
