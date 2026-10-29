from __future__ import annotations

import asyncio
import time

import ccxt.async_support as ccxt
import pandas as pd

from core.config import BINGX_API_KEY, BINGX_API_SECRET, MEMECOIN_V2_LIMIT, TARGET_COINS


class ExchangeClient:
    """BingX USDT perpetual client.

    Public scanning is intentionally isolated from private credentials.  A
    signed CCXT client is constructed lazily only if an order method is called.
    """

    def __init__(self):
        self._exchange_options = {
            "enableRateLimit": True,
            "options": {"defaultType": "swap"},
        }
        self.exchange = ccxt.bingx(self._exchange_options)
        self._trading_exchange = None
        self._public_request_lock = None
        self._public_request_lock_loop = None
        self._last_public_request_at = 0.0
        self._public_request_interval = 1.0
        self._markets_loaded = False
        self._tickers_cache = {}
        self._tickers_cache_ts = 0.0

    async def load_markets_if_needed(self):
        if not self._markets_loaded:
            await self._public_request(self.exchange.load_markets)
            self._markets_loaded = True

    async def _public_request(self, operation, *args, **kwargs):
        current_loop = asyncio.get_running_loop()
        if self._public_request_lock is None or self._public_request_lock_loop is not current_loop:
            self._public_request_lock = asyncio.Lock()
            self._public_request_lock_loop = current_loop
        for attempt in range(4):
            try:
                async with self._public_request_lock:
                    elapsed = time.monotonic() - self._last_public_request_at
                    if elapsed < self._public_request_interval:
                        await asyncio.sleep(self._public_request_interval - elapsed)
                    try:
                        return await operation(*args, **kwargs)
                    finally:
                        self._last_public_request_at = time.monotonic()
            except Exception as exc:
                message = str(exc).lower()
                throttled = any(
                    marker in message
                    for marker in ("too many", "frequent", "rate limit", "429")
                )
                if not throttled or attempt == 3:
                    raise
                await asyncio.sleep(2 ** attempt)

    async def validate_symbol(self, raw_coin: str):
        await self.load_markets_if_needed()
        coin = raw_coin.upper().replace("USDT", "").replace("/", "").replace("-", "")
        target = f"{coin}/USDT:USDT"
        market = self.exchange.markets.get(target)
        if market and market.get("swap") and market.get("linear") and market.get("active", True):
            return target
        return None

    async def close(self):
        await self.exchange.close()
        if self._trading_exchange is not None:
            await self._trading_exchange.close()

    async def _get_trading_exchange(self):
        if not BINGX_API_KEY or not BINGX_API_SECRET:
            raise RuntimeError("BingX credentials are required to create orders")
        if self._trading_exchange is None:
            self._trading_exchange = ccxt.bingx({
                **self._exchange_options,
                "apiKey": BINGX_API_KEY,
                "secret": BINGX_API_SECRET,
            })
            await self._trading_exchange.load_markets()
        return self._trading_exchange

    async def get_top_pairs(self):
        try:
            tickers = await self.fetch_tickers_cached()
            ranked = []
            for symbol, ticker in tickers.items():
                market = self.exchange.markets.get(symbol, {})
                if not (
                    market.get("swap")
                    and market.get("linear")
                    and market.get("quote") == "USDT"
                    and market.get("active", True)
                ):
                    continue
                quote_volume = ticker.get("quoteVolume")
                if quote_volume is not None:
                    ranked.append((symbol, float(quote_volume)))
            ranked.sort(key=lambda item: item[1], reverse=True)
            top_symbols = [symbol for symbol, _ in ranked[:MEMECOIN_V2_LIMIT]]
            targets = [f"{coin}/USDT:USDT" for coin in TARGET_COINS]
            return list(dict.fromkeys([*targets, *top_symbols]))
        except Exception as exc:
            print(f"Error fetching BingX top pairs: {exc}")
            return [f"{coin}/USDT:USDT" for coin in TARGET_COINS]

    async def fetch_tickers_cached(self, ttl_seconds: int = 60) -> dict:
        await self.load_markets_if_needed()
        now = time.time()
        if self._tickers_cache and now - self._tickers_cache_ts < ttl_seconds:
            return self._tickers_cache
        self._tickers_cache = await self._public_request(self.exchange.fetch_tickers)
        self._tickers_cache_ts = now
        return self._tickers_cache

    async def fetch_ticker_cached(self, symbol: str) -> dict:
        return (await self.fetch_tickers_cached()).get(symbol, {})

    async def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 200) -> pd.DataFrame:
        try:
            rows = await self._public_request(
                self.exchange.fetch_ohlcv,
                symbol,
                timeframe,
                limit=limit,
            )
            frame = pd.DataFrame(
                rows,
                columns=["timestamp", "open", "high", "low", "close", "volume"],
            )
            frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="ms")
            for column in ("open", "high", "low", "close", "volume"):
                frame[column] = frame[column].astype(float)
            return frame
        except Exception as exc:
            print(f"Error fetching BingX OHLCV for {symbol} on {timeframe}: {exc}")
            return pd.DataFrame()

    async def fetch_historical_data(self, symbol: str, timeframe: str = "1w") -> pd.DataFrame:
        return await self.fetch_ohlcv(symbol, timeframe, limit=1000)

    async def create_market_order(self, symbol: str, side: str, amount: float, params=None):
        """Create a BingX perpetual market order when explicitly enabled upstream."""
        try:
            trading_exchange = await self._get_trading_exchange()
            return await trading_exchange.create_market_order(
                symbol,
                side,
                amount,
                None,
                params or {},
            )
        except Exception as exc:
            print(f"Error creating BingX order for {symbol}: {exc}")
            return None
