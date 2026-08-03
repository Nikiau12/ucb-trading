import asyncio
import ccxt.async_support as ccxt
import pandas as pd
import time
from core.config import MEXC_API_KEY, MEXC_API_SECRET, MEMECOIN_V2_LIMIT, TARGET_COINS

class ExchangeClient:
    def __init__(self):
        # Market scanning only uses public endpoints. Keeping credentials off the
        # public client prevents an expired key from breaking ticker/OHLCV reads.
        self._exchange_options = {
            'enableRateLimit': True,
            'options': {
                'defaultType': 'swap', # We want to trade Futures (Perpetual Swaps)
            }
        }
        self.exchange = ccxt.mexc(self._exchange_options)
        self._trading_exchange = None
        self._markets_loaded = False
        self._tickers_cache = {}
        self._tickers_cache_ts = 0
        
    async def load_markets_if_needed(self):
        if not self._markets_loaded:
            await self.exchange.load_markets()
            self._markets_loaded = True

    async def validate_symbol(self, raw_coin: str) -> str:
        """
        Takes a raw coin string (like 'PEPE' or 'PEPEUSDT') and tries to find a valid Perpetual Swap trading pair on MEXC.
        Returns the formatted symbol (e.g. 'PEPE/USDT:USDT') or None if not found.
        """
        await self.load_markets_if_needed()
        
        # Normalize input
        coin = raw_coin.upper().replace("USDT", "")
        # MEXC futures symbols format ccxt uses: 'BTC/USDT:USDT'
        target_symbol = f"{coin}/USDT:USDT"
        
        if target_symbol in self.exchange.markets:
            return target_symbol
            
        # Fallback to Spot if Futures doesn't exist? For SMC bot, futures are preferred.
        spot_symbol = f"{coin}/USDT"
        if spot_symbol in self.exchange.markets:
            return spot_symbol
            
        return None

    async def close(self):
        await self.exchange.close()
        if self._trading_exchange is not None:
            await self._trading_exchange.close()

    async def _get_trading_exchange(self):
        if not MEXC_API_KEY or not MEXC_API_SECRET:
            raise RuntimeError("MEXC credentials are required to create orders")
        if self._trading_exchange is None:
            self._trading_exchange = ccxt.mexc({
                **self._exchange_options,
                'apiKey': MEXC_API_KEY,
                'secret': MEXC_API_SECRET,
            })
            await self._trading_exchange.load_markets()
        return self._trading_exchange

    async def get_top_pairs(self):
        """Fetches the top N USDT perpetual pairs by 24h quote volume."""
        try:
            tickers = await self.fetch_tickers_cached()
            usdt_pairs = []
            for symbol, ticker in tickers.items():
                # On MEXC futures, symbols are usually like BTC/USDT:USDT
                # Check for USDT margin swaps
                if symbol.endswith('USDT') or symbol.endswith('USDT:USDT'):
                    quote_volume = ticker.get('quoteVolume', 0)
                    if quote_volume is not None:
                        usdt_pairs.append((symbol, quote_volume))
            
            # Sort by volume descending
            usdt_pairs.sort(key=lambda x: x[1], reverse=True)
            
            # Extract top N symbols
            top_symbols = [pair[0] for pair in usdt_pairs[:MEMECOIN_V2_LIMIT]]
            
            # Ensure our target coins are included
            target_symbols = [f"{coin}/USDT" for coin in TARGET_COINS]
            final_symbols = list(set(target_symbols + top_symbols))
            return final_symbols
            
        except Exception as e:
            print(f"Error fetching top pairs: {e}")
            target_symbols = [f"{coin}/USDT" for coin in TARGET_COINS]
            return target_symbols

    async def fetch_tickers_cached(self, ttl_seconds: int = 60) -> dict:
        now = time.time()
        if self._tickers_cache and now - self._tickers_cache_ts < ttl_seconds:
            return self._tickers_cache
        self._tickers_cache = await self.exchange.fetch_tickers()
        self._tickers_cache_ts = now
        return self._tickers_cache

    async def fetch_ticker_cached(self, symbol: str) -> dict:
        tickers = await self.fetch_tickers_cached()
        return tickers.get(symbol, {})

    async def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 200) -> pd.DataFrame:
        """Fetch OHLCV historical data and return as a Pandas DataFrame."""
        try:
            # We don't always need to format symbol to ccxt standard if we got it from fetch_tickers, 
            # but usually it's good to be safe.
            ohlcv = await self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            # Convert types to float
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].astype(float)
                
            return df
            
        except Exception as e:
            print(f"Error fetching OHLCV for {symbol} on {timeframe}: {e}")
            return pd.DataFrame() # Return empty df on error

    async def fetch_historical_data(self, symbol: str, timeframe: str = '1w') -> pd.DataFrame:
        """
        Fetches the maximum available historical data for '1w' (weekly) timeframe
        to determine the all-time macro trend of the coin.
        """
        try:
            # Setting limit=1000 for weekly timeframe will fetch roughly 20 years of data.
            # since=0 forces it to start from the beginning of available history on some exchanges (if supported).
            ohlcv = await self.exchange.fetch_ohlcv(symbol, timeframe, since=0, limit=1000)
            
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].astype(float)
                
            return df
        except Exception as e:
            print(f"Error fetching historical data for {symbol}: {e}")
            return pd.DataFrame()

    async def create_market_order(self, symbol: str, side: str, amount: float, params: dict = None):
        """
        Create a market order (LONG/SHORT) on MEXC futures.
        `side` should be 'buy' or 'sell'.
        `params` can contain {'stopLossPrice': ..., 'takeProfitPrice': ...}
        """
        try:
            if params is None:
                params = {}
            trading_exchange = await self._get_trading_exchange()
            order = await trading_exchange.create_market_order(symbol, side, amount, None, params)
            print(f"Order executed: {order}")
            return order
        except Exception as e:
            print(f"Error creating order for {symbol}: {e}")
            return None
