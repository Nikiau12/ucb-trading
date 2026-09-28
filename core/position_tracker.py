import asyncio
import time
from bingx.exchange_client_bingx import ExchangeClientBingX
from core.notifier import Notifier
from core.config import AUTO_TRADING_ENABLED, BINGX_MOVE_SL_TO_BREAKEVEN

notifier = Notifier()

class PositionTracker:
    def __init__(self, exchange: ExchangeClientBingX):
        self.exchange = exchange
        self.ROE_THRESHOLD = 0.25 # 25% ROE. Плечо x15 = ~1.66% чистого движения графика.
        self.cooldowns = {}

    async def track_loop(self):
        print("[PositionTracker] Запуск модуля активного слежения за позициями (Безубыток)...")
        while True:
            try:
                if not getattr(BINGX_MOVE_SL_TO_BREAKEVEN, '__bool__', False) or not AUTO_TRADING_ENABLED:
                    await asyncio.sleep(60)
                    continue
                    
                # 1. Загрузка открытых позиций
                positions = await self.exchange.exchange.fetch_positions()
                active_positions = [p for p in positions if float(p.get('contracts', 0)) > 0]
                
                if not active_positions:
                    await asyncio.sleep(60)
                    continue
                    
                # 2. Загрузка открытых ордеров (чтобы найти текущие стопы)
                open_orders = await self.exchange.exchange.fetch_open_orders(symbol=None)
                
                for pos in active_positions:
                    info = pos.get('info', {})
                    pos_id = str(info.get('positionId', ''))
                    if not pos_id:
                        pos_id = str(pos.get('id', ''))
                        
                    pnl_ratio = float(info.get('pnlRatio', 0))
                    symbol = pos['symbol']
                    side = info.get('positionSide', '')
                    avg_price = float(info.get('avgPrice', 0))
                    
                    if pnl_ratio >= self.ROE_THRESHOLD:
                        # Проверяем не переносили ли мы уже стоп недавно (анти-спам)
                        cooldown_key = f"{symbol}_{pos_id}"
                        if time.time() - self.cooldowns.get(cooldown_key, 0) < 300: # 5 мин кулдаун
                            continue
                            
                        # Ищем все SL ордера привязанные к этой позиции
                        sl_orders = []
                        for o in open_orders:
                            o_sym = o.get('symbol', '')
                            o_info = o.get('info', {})
                            if o_sym == symbol and str(o_info.get('positionID', '')) == pos_id:
                                o_type = o_info.get('type', '').upper()
                                if 'STOP' in o_type:
                                    sl_orders.append(o)
                                    
                        if sl_orders:
                            # Берем первый найденный стоп (обычно он один)
                            sl_ord = sl_orders[0]
                            o_info = sl_ord.get('info', {})
                            sl_price = float(o_info.get('stopPrice', sl_ord.get('stopPrice', 0)))
                            
                            needs_update = False
                            # Для LONG: avgPrice 100. Если SL на 90, update до 100.
                            if side == 'LONG' and sl_price < avg_price * 0.999:
                                needs_update = True
                            # Для SHORT: avgPrice 100. Если SL на 110, update до 100.
                            elif side == 'SHORT' and sl_price > avg_price * 1.001:
                                needs_update = True
                                
                            if needs_update:
                                print(f"[Tracker] 🛡 Монета {symbol} достигла профита {pnl_ratio*100:.1f}%. Перевод SL в Безубыток ({avg_price}).")
                                
                                # Отмена старого SL
                                await self.exchange.exchange.cancel_order(sl_ord['id'], symbol)
                                
                                # Подготовка нового SL
                                order_side = 'SELL' if side == 'LONG' else 'BUY'
                                qty = abs(float(info.get('positionAmt', 0)))
                                
                                params = {
                                    'stopPrice': avg_price,
                                    'workingType': 'MARK_PRICE',
                                    'positionID': pos_id,
                                    'positionSide': side
                                }
                                
                                # Создание нового безубыточного SL
                                await self.exchange.exchange.create_order(
                                    symbol=symbol,
                                    type='STOP_MARKET',
                                    side=order_side,
                                    amount=qty,
                                    price=None,
                                    params=params
                                )
                                
                                self.cooldowns[cooldown_key] = time.time()
                                await notifier.send_message(f"🛡 <b>БЕЗУБЫТОК АКТИВИРОВАН!</b> 🛡\n\nМонета: <b>{symbol}</b>\nТекущий профит: +{(pnl_ratio*100):.1f}%\nСтоп-Лосс безопасно перенесен на цену входа: {avg_price}")
                                await asyncio.sleep(2) # Защита от спама API
                                
            except Exception as e:
                print(f"[Tracker] Ошибка цикла: {e}")
                
            await asyncio.sleep(60) # Скан активных сделок раз в минуту
