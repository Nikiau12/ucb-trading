import asyncio
import json
import time
import urllib.parse
import urllib.request


class CoinInfoService:
    def __init__(self, ttl_seconds: int = 6 * 60 * 60):
        self.ttl_seconds = ttl_seconds
        self._symbol_cache = {}
        self._info_cache = {}

    async def get_coin_info(self, symbol: str) -> dict:
        coin = self._extract_base_symbol(symbol)
        if not coin:
            return {}

        cache_key = coin.upper()
        cached = self._info_cache.get(cache_key)
        if cached and time.time() - cached["ts"] < self.ttl_seconds:
            return cached["data"]

        coin_id = await self._resolve_coin_id(coin)
        if not coin_id:
            return {
                "symbol": coin,
                "name": coin,
                "risk_label": "unknown",
                "note": "Нет данных CoinGecko",
            }

        market = await self._fetch_json(
            "https://api.coingecko.com/api/v3/coins/markets?"
            + urllib.parse.urlencode({
                "vs_currency": "usd",
                "ids": coin_id,
                "price_change_percentage": "1h,24h,7d",
            })
        )
        if not market:
            return {}

        item = market[0]
        data = {
            "id": coin_id,
            "symbol": item.get("symbol", coin).upper(),
            "name": item.get("name", coin),
            "rank": item.get("market_cap_rank"),
            "market_cap": item.get("market_cap"),
            "fdv": item.get("fully_diluted_valuation"),
            "volume_24h": item.get("total_volume"),
            "price_change_1h": item.get("price_change_percentage_1h_in_currency"),
            "price_change_24h": item.get("price_change_percentage_24h_in_currency"),
            "risk_label": self._risk_label(item.get("market_cap_rank"), item.get("market_cap")),
        }
        self._info_cache[cache_key] = {"ts": time.time(), "data": data}
        return data

    async def _resolve_coin_id(self, symbol: str) -> str:
        cache_key = symbol.upper()
        cached = self._symbol_cache.get(cache_key)
        if cached and time.time() - cached["ts"] < self.ttl_seconds:
            return cached["id"]

        data = await self._fetch_json(
            "https://api.coingecko.com/api/v3/search?"
            + urllib.parse.urlencode({"query": symbol})
        )
        coins = data.get("coins", []) if isinstance(data, dict) else []
        exact = [
            coin for coin in coins
            if str(coin.get("symbol", "")).upper() == cache_key
        ]
        if not exact:
            return ""

        exact.sort(key=lambda coin: coin.get("market_cap_rank") or 10**9)
        coin_id = exact[0].get("id", "")
        self._symbol_cache[cache_key] = {"ts": time.time(), "id": coin_id}
        return coin_id

    async def _fetch_json(self, url: str):
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "api.coingecko.com":
            raise ValueError("unsupported CoinGecko URL")

        def request():
            req = urllib.request.Request(
                url,
                headers={
                    "accept": "application/json",
                    "user-agent": "mexc-signal-bot/1.0",
                },
            )
            with urllib.request.urlopen(req, timeout=10) as response:  # nosec B310
                return json.loads(response.read().decode("utf-8"))

        try:
            return await asyncio.to_thread(request)
        except Exception as e:
            print(f"[CoinInfoService] request failed: {e}")
            return {}

    def _extract_base_symbol(self, symbol: str) -> str:
        base = symbol.split("/")[0] if "/" in symbol else symbol
        return base.replace("USDT", "").replace("_", "").upper()

    def _risk_label(self, rank, market_cap) -> str:
        if rank and rank <= 50:
            return "blue chip"
        if rank and rank <= 200:
            return "large cap"
        if rank and rank <= 500:
            return "mid cap"
        if market_cap and market_cap >= 50_000_000:
            return "small cap"
        if market_cap:
            return "micro cap"
        return "unknown"
