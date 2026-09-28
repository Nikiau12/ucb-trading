import asyncio
import traceback
import pandas as pd
import numpy as np
from datetime import datetime, timezone

from bingx.exchange_client_bingx import ExchangeClientBingX
from core.btc_trade_policy import evaluate_btc_setup
from core.notifier import Notifier
from core.smart_engine import SmartContextEngine, SignalType
from core.config import AUTO_TRADING_ENABLED, BINGX_LEVERAGE, TARGET_COINS, FLAG_MIN_POLE_PERCENT, FLAG_MAX_RETRACEMENT, FLAG_MARGIN_PER_TRADE

notifier = Notifier()

class FlagPatternScanner:
    def __init__(self, exchange: ExchangeClientBingX):
        self.exchange = exchange
        self.symbols = [f"{coin}/USDT:USDT" for coin in TARGET_COINS]
        self.interval = 300  # Scan every 5 minutes
        self.smart_engine = SmartContextEngine()
        
        # Risk settings
        self.margin_per_trade = FLAG_MARGIN_PER_TRADE
        self.min_pole_pct = FLAG_MIN_POLE_PERCENT
        self.max_retracement = FLAG_MAX_RETRACEMENT
        self.cooldowns = {}

    def get_swing_points(self, df: pd.DataFrame, window=3):
        """Finds local minimums and maximums"""
        df['swing_high'] = df['high'] == df['high'].rolling(window=2*window+1, center=True).max()
        df['swing_low'] = df['low'] == df['low'].rolling(window=2*window+1, center=True).min()
        return df

    def analyze_flag(self, symbol: str, df: pd.DataFrame):
        """
        Scans for Bull/Bear flag pattern and returns setup if currently touching 
        the entry boundary (2nd, 3rd, 4th touch).
        """
        # Minimum candles needed to form a proper pole and flag
        if len(df) < 50: return None
        
        df = self.get_swing_points(df.copy(), window=3)
        
        # We look at the last 60 candles
        recent_df = df.tail(60).copy()
        recent_df['idx'] = range(len(recent_df))
        
        # ========================================================
        # BEAR FLAG DETECTION (Short)
        # ========================================================
        # 1. Find the lowest point as the end of the potential 'Pole'
        min_idx = recent_df['low'].idxmin()
        pole_bottom_row = recent_df.loc[min_idx]
        pole_bottom_price = pole_bottom_row['low']
        
        # Ensure the bottom is not too recent, need time for flag to form
        idx_of_bottom = pole_bottom_row['idx']
        flag_length = len(recent_df) - idx_of_bottom - 1
        
        # We need at least 10 candles after the dump to form a flag
        if flag_length >= 10:
            # 2. Check the pole before the bottom
            pole_df = recent_df[recent_df['idx'] <= idx_of_bottom]
            max_idx = pole_df['high'].idxmax()
            pole_top_price = pole_df.loc[max_idx, 'high']
            
            pole_drop_pct = (pole_top_price - pole_bottom_price) / pole_top_price * 100
            
            # Pole must be a sharp drop
            if pole_drop_pct >= self.min_pole_pct:
                flag_df = recent_df[recent_df['idx'] > idx_of_bottom].copy()
                
                # Retrieve swing highs inside the flag
                swing_highs = flag_df[flag_df['swing_high']]
                
                # If we have at least 1 established swing high in the flag
                if len(swing_highs) >= 1:
                    # Mathematical line fit for upper boundary using all highs in the flag
                    # to represent the ascending channel ceiling
                    x = flag_df['idx'].values
                    y = flag_df['high'].values
                    
                    if len(x) > 1:
                        slope, intercept = np.polyfit(x, y, 1)
                        
                        # Bear flag must have an ascending or almost flat channel (slope > -small_val)
                        # We don't want steep descending channels
                        current_idx = flag_df['idx'].iloc[-1]
                        projected_resistance = slope * current_idx + intercept
                        
                        current_price = flag_df['close'].iloc[-1]
                        current_high = flag_df['high'].iloc[-1]
                        
                        # Has the price retraced more than max retracement of the pole?
                        max_retracement_allowed = pole_bottom_price + (pole_top_price - pole_bottom_price) * self.max_retracement
                        if current_price < max_retracement_allowed and slope > -0.001: 
                            
                            # Count Touches
                            touches = 0
                            for _, sh in swing_highs.iterrows():
                                sh_proj = slope * sh['idx'] + intercept
                                if sh['high'] >= sh_proj * 0.999: # 0.1% tolerance
                                    touches += 1
                                    
                            # Check if the current candle is touching resistance and making a higher high
                            # than the last confirmed swing high
                            last_swing_high_price = swing_highs['high'].max()
                            is_touching_now = current_high >= projected_resistance * 0.9985
                            is_higher_high = current_high >= last_swing_high_price * 0.999
                            
                            if is_touching_now and is_higher_high and touches >= 1: # touches=1 means current makes it the 2nd
                                
                                # Setup triggered!
                                atr = df['high'].rolling(14).max() - df['low'].rolling(14).min()
                                atr_val = atr.iloc[-1]
                                
                                stop_loss = current_high + (atr_val * 1.5) # Stop above the channel
                                take_profit = pole_bottom_price # Target is the bottom of the pole
                                
                                return {
                                    "symbol": symbol,
                                    "setup": "SHORT",
                                    "reasoning": f"Bear Flag detected! Touching upper channel boundary. (Touch #{touches+1}, Slope: {slope:.5f})",
                                    "entry": current_price,
                                    "stop": stop_loss,
                                    "target": take_profit
                                }

        # ========================================================
        # BULL FLAG DETECTION (Long)
        # ========================================================
        # 1. Find the highest point as the end of the potential 'Pole'
        max_idx_bull = recent_df['high'].idxmax()
        pole_top_row = recent_df.loc[max_idx_bull]
        pole_top_price = pole_top_row['high']
        
        idx_of_top = pole_top_row['idx']
        flag_length_bull = len(recent_df) - idx_of_top - 1
        
        if flag_length_bull >= 10:
            pole_df_bull = recent_df[recent_df['idx'] <= idx_of_top]
            min_idx_bull = pole_df_bull['low'].idxmin()
            pole_bottom_price_bull = pole_df_bull.loc[min_idx_bull, 'low']
            
            pole_pump_pct = (pole_top_price - pole_bottom_price_bull) / pole_bottom_price_bull * 100
            
            if pole_pump_pct >= self.min_pole_pct:
                flag_df_bull = recent_df[recent_df['idx'] > idx_of_top].copy()
                swing_lows = flag_df_bull[flag_df_bull['swing_low']]
                
                if len(swing_lows) >= 1:
                    x_bull = flag_df_bull['idx'].values
                    y_bull = flag_df_bull['low'].values
                    
                    if len(x_bull) > 1:
                        slope_bull, intercept_bull = np.polyfit(x_bull, y_bull, 1)
                        
                        current_idx_bull = flag_df_bull['idx'].iloc[-1]
                        projected_support = slope_bull * current_idx_bull + intercept_bull
                        
                        current_price_bull = flag_df_bull['close'].iloc[-1]
                        current_low_bull = flag_df_bull['low'].iloc[-1]
                        
                        max_drop_allowed = pole_top_price - (pole_top_price - pole_bottom_price_bull) * self.max_retracement
                        
                        # Slope should be negative or slightly flat for a bull flag channel
                        if current_price_bull > max_drop_allowed and slope_bull < 0.001:
                            touches_bull = 0
                            for _, sl in swing_lows.iterrows():
                                sl_proj = slope_bull * sl['idx'] + intercept_bull
                                if sl['low'] <= sl_proj * 1.001: 
                                    touches_bull += 1
                                    
                            last_swing_low_price = swing_lows['low'].min()
                            is_touching_now_bull = current_low_bull <= projected_support * 1.0015
                            is_lower_low = current_low_bull <= last_swing_low_price * 1.001
                            
                            if is_touching_now_bull and is_lower_low and touches_bull >= 1:
                                atr_val = (df['high'].rolling(14).max() - df['low'].rolling(14).min()).iloc[-1]
                                stop_loss = current_low_bull - (atr_val * 1.5)
                                take_profit = pole_top_price 
                                
                                return {
                                    "symbol": symbol,
                                    "setup": "LONG",
                                    "reasoning": f"Bull Flag detected! Touching lower channel boundary. (Touch #{touches_bull+1}, Slope: {slope_bull:.5f})",
                                    "entry": current_price_bull,
                                    "stop": stop_loss,
                                    "target": take_profit
                                }

        return None

    async def run_loop(self):
        print("🚩 [Flag Scanner] Модуль поиска Флагов продолжения тренда запущен.")
        await asyncio.sleep(15) 
        
        while True:
            try:
                for symbol in self.symbols:
                    now = datetime.now(timezone.utc).timestamp()
                    
                    if symbol in self.cooldowns and (now - self.cooldowns[symbol]) < 7200:
                        continue

                    # Сканируем рабочий фрейм 1d (По просьбе пользователя)
                    df_1d = await self.exchange.fetch_ohlcv(symbol, "1d", limit=250)
                    if df_1d.empty: continue
                    
                    setup = self.analyze_flag(symbol, df_1d)
                    
                    if setup:
                        policy_ok, policy_reasons, policy_metrics = evaluate_btc_setup(
                            setup["setup"],
                            setup["entry"],
                            setup["stop"],
                            setup["target"],
                            df_1d
                        )
                        if not policy_ok:
                            print(f"[Flag Scanner] BTC policy rejected {symbol} {setup['setup']}: {policy_reasons}")
                            continue

                        # Фильтр AI для подтверждения
                        score = self.smart_engine.analyze_context(df_1d, symbol, setup['setup'])
                        if score.signal == SignalType.NO_TRADE or score.confidence < 50:
                            print(f"[Flag Scanner] AI отклонил сетап {symbol}: Уверенность {score.confidence}% < 50%")
                            continue
                            
                        print(f"🚨 ПАТТЕРН ФЛАГА (AI {score.confidence}%): {symbol} -> {setup['setup']}")
                        
                        entry_price = float(setup['entry'])
                        position_coin_size = (self.margin_per_trade * BINGX_LEVERAGE) / entry_price
                        side = 'buy' if setup['setup'] == "LONG" else 'sell'
                        
                        order_status = "ОЖИДАЕМ (Автоторговля выключена)"
                        if AUTO_TRADING_ENABLED:
                            # ПРИНУДИТЕЛЬНОЕ ПЛЕЧО ПЕРЕД ВХОДОМ
                            await self.exchange.set_leverage(symbol, BINGX_LEVERAGE)
                            
                            order = await self.exchange.create_market_order_with_sl_tp(
                                symbol=symbol,
                                side=side,
                                amount=position_coin_size,
                                stop_loss=setup['stop'],
                                take_profit=setup['target']
                            )
                            if order:
                                order_status = "✅ ОРДЕР УСПЕШНО ОТКРЫТ"
                                self.cooldowns[symbol] = now
                            else:
                                order_status = "❌ ОШИБКА ИСПОЛНЕНИЯ БИРЖЕЙ"

                        message = (
                            f"🚩 <b>[FLAG PATTERN EXECUTED]</b> 🚩\n\n"
                            f"Монета: <b>{symbol}</b>\n"
                            f"Сетап: <b>{setup['setup']}</b>\n"
                            f"🤖 <b>AI Уверенность: {score.confidence}%</b>\n"
                            f"Статус: <b>{order_status}</b>\n\n"
                            f"Обоснование: {setup['reasoning']}\n\n"
                            f"Вход (Market): <b>{setup['entry']:.4f}</b>\n"
                            f"Стоп: <b>{setup['stop']:.4f}</b>\n"
                            f"Цель: <b>{setup['target']:.4f}</b>\n"
                            f"BTC Policy RR: <b>{policy_metrics.get('rr', 0):.2f}</b>, Daily ATR: <b>{policy_metrics.get('atr_pct', 0):.2%}</b>\n"
                        )
                        await notifier.send_message(message)
                        
            except Exception as e:
                print(f"Ошибка в цикле FlagPatternScanner: {e}")
                traceback.print_exc()
                
            await asyncio.sleep(self.interval)
