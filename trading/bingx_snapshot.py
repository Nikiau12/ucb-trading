#!/usr/bin/env python3
"""BingX perpetual-futures market data normalized for the UCB strategy core.

The rest of the application deliberately keeps its historical internal symbol
format (``BTC_USDT``).  Only this exchange boundary converts it to BingX's
``BTC-USDT`` format.  Public market-data calls never receive private API keys.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from decimal import Decimal
from typing import Any, Callable, Dict, Optional

import requests


BASE = os.getenv("BINGX_PUBLIC_API_BASE", "https://open-api.bingx.com").rstrip("/")
CACHE_DIR = os.path.expanduser("~/.openclaw/trading/cache/bingx")
TOP_SYMBOLS_CACHE_PATH = os.path.join(CACHE_DIR, "top_symbols.json")
BINGX_MIN_REQUEST_INTERVAL = max(
    0.2, float(os.getenv("BINGX_MIN_REQUEST_INTERVAL", "1.0"))
)
BINGX_MAX_ATTEMPTS = max(1, int(os.getenv("BINGX_MAX_ATTEMPTS", "4")))
SNAPSHOT_MAX_STALE_SECONDS = max(
    0, int(os.getenv("BINGX_SNAPSHOT_MAX_STALE_SECONDS", "7200"))
)
TICKER_CACHE_TTL_SECONDS = max(
    1, int(os.getenv("BINGX_TICKER_CACHE_TTL_SECONDS", "60"))
)
CONTRACT_CACHE_TTL_SECONDS = max(
    60, int(os.getenv("BINGX_CONTRACT_CACHE_TTL_SECONDS", "3600"))
)
FALLBACK_SYMBOLS = ["BTC_USDT", "ETH_USDT", "SOL_USDT"]
# BingX exposes commodities, equities, indices, and FX through the same ticker
# endpoint.  Those synthetic assets use these provider prefixes and must not
# leak into a cryptocurrency scanner.
NON_CRYPTO_ASSET_PREFIXES = ("NCCO", "NCFX", "NCSI", "NCSK")

logger = logging.getLogger(__name__)


class BingxAPIError(RuntimeError):
    def __init__(self, message: str, *, code: Optional[int] = None):
        super().__init__(message)
        self.code = code


def to_bingx_symbol(symbol: str) -> str:
    """Convert supported internal/CCXT spellings to ``BASE-USDT``."""
    normalized = str(symbol).strip().upper()
    if "/" in normalized:
        normalized = normalized.split(":", 1)[0].replace("/", "-")
    else:
        normalized = normalized.replace("_", "-")
    if "-" not in normalized and normalized.endswith("USDT"):
        normalized = normalized[:-4] + "-USDT"
    if normalized.count("-") != 1 or not normalized.endswith("-USDT"):
        raise ValueError(f"unsupported BingX perpetual symbol: {symbol}")
    base, quote = normalized.split("-", 1)
    if not base.isalnum() or quote != "USDT":
        raise ValueError(f"unsupported BingX perpetual symbol: {symbol}")
    return normalized


def to_internal_symbol(symbol: str) -> str:
    return to_bingx_symbol(symbol).replace("-", "_")


class BingxPublicClient:
    """Thread-safe public REST client with a process-wide request budget."""

    def __init__(
        self,
        *,
        min_interval: float = BINGX_MIN_REQUEST_INTERVAL,
        max_attempts: int = BINGX_MAX_ATTEMPTS,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        request_get: Optional[Callable[..., Any]] = None,
    ):
        self.min_interval = max(0.0, min_interval)
        self.max_attempts = max(1, max_attempts)
        self._clock = clock
        self._sleep = sleep
        self._request_get = request_get
        self._lock = threading.Lock()
        self._last_request_at = 0.0

    def _wait_for_slot(self) -> None:
        with self._lock:
            delay = self.min_interval - (self._clock() - self._last_request_at)
            if delay > 0:
                self._sleep(delay)
            self._last_request_at = self._clock()

    @staticmethod
    def _payload_error(payload: Any) -> Optional[BingxAPIError]:
        if not isinstance(payload, dict):
            return BingxAPIError("unexpected BingX response")
        raw_code = payload.get("code", 0)
        try:
            code = int(raw_code)
        except (TypeError, ValueError):
            code = None
        if code not in (None, 0):
            return BingxAPIError(
                str(payload.get("msg") or payload.get("message") or "BingX API error"),
                code=code,
            )
        return None

    @staticmethod
    def _retryable(exc: Exception) -> bool:
        if isinstance(exc, BingxAPIError):
            message = str(exc).lower()
            return "too many" in message or "frequent" in message or exc.code in {100001}
        if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
            return True
        if isinstance(exc, requests.HTTPError) and exc.response is not None:
            return exc.response.status_code == 429 or exc.response.status_code >= 500
        return False

    def get(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: int = 10,
    ) -> Dict[str, Any]:
        request_get = self._request_get or requests.get
        for attempt in range(self.max_attempts):
            self._wait_for_slot()
            try:
                response = request_get(
                    f"{BASE}{path}",
                    params=params,
                    timeout=timeout,
                    headers={"User-Agent": "ucb-trading-bingx/1.0"},
                )
                response.raise_for_status()
                payload = response.json()
                payload_error = self._payload_error(payload)
                if payload_error:
                    raise payload_error
                return payload
            except Exception as exc:
                if not self._retryable(exc) or attempt + 1 >= self.max_attempts:
                    raise
                response = getattr(exc, "response", None)
                retry_after = None
                if response is not None:
                    try:
                        retry_after = float(response.headers.get("Retry-After", ""))
                    except (TypeError, ValueError):
                        retry_after = None
                backoff = retry_after if retry_after is not None else min(8.0, 2.0 ** attempt)
                logger.warning(
                    "BingX transient request path=%s attempt=%s/%s retry_in=%.1fs: %s",
                    path,
                    attempt + 1,
                    self.max_attempts,
                    backoff,
                    exc,
                )
                self._sleep(max(0.0, backoff))
        raise RuntimeError("unreachable")


_PUBLIC_CLIENT = BingxPublicClient()
_TICKER_CACHE_LOCK = threading.Lock()
_TICKER_CACHE: Dict[str, Dict[str, Any]] = {}
_TICKER_CACHE_TS = 0.0
_CONTRACT_CACHE_LOCK = threading.Lock()
_CONTRACT_CACHE: Dict[str, Dict[str, Any]] = {}
_CONTRACT_CACHE_TS = 0.0


def http_get(path: str, params: Optional[Dict[str, Any]] = None, timeout: int = 10):
    return _PUBLIC_CLIENT.get(path, params=params, timeout=timeout)


def _step_from_precision(value: Any) -> float:
    precision = max(0, int(value or 0))
    return float(Decimal(1).scaleb(-precision))


def normalize_contract(item: Dict[str, Any]) -> Dict[str, Any]:
    """Map BingX quantity rules to the exchange-neutral sizing schema."""
    bingx_symbol = to_bingx_symbol(str(item.get("symbol") or item.get("displayName")))
    quantity_step = _step_from_precision(item.get("quantityPrecision"))
    min_quantity = float(item.get("tradeMinQuantity") or quantity_step)
    return {
        "symbol": to_internal_symbol(bingx_symbol),
        "exchangeSymbol": bingx_symbol,
        "priceUnit": _step_from_precision(item.get("pricePrecision")),
        # BingX order quantity is denominated in the underlying asset.  A
        # canonical contract therefore represents one base unit.
        "contractSize": 1.0,
        "volUnit": quantity_step,
        "minVol": min_quantity,
        "maxVol": None,
        "maxLeverage": None,
        "minNotional": float(item.get("tradeMinUSDT") or 0),
        "active": int(item.get("status", 0) or 0) == 1
        and str(item.get("apiStateOpen", "false")).lower() == "true",
        "raw": dict(item),
    }


def is_crypto_contract(item: Dict[str, Any]) -> bool:
    asset = str(item.get("asset") or "").upper()
    return bool(asset) and not asset.startswith(NON_CRYPTO_ASSET_PREFIXES)


def futures_contracts() -> Dict[str, Any]:
    global _CONTRACT_CACHE, _CONTRACT_CACHE_TS
    with _CONTRACT_CACHE_LOCK:
        if time.time() - _CONTRACT_CACHE_TS <= CONTRACT_CACHE_TTL_SECONDS and _CONTRACT_CACHE:
            return {"code": 0, "msg": "", "data": list(_CONTRACT_CACHE.values())}
    payload = http_get("/openApi/swap/v2/quote/contracts")
    items = payload.get("data", []) if isinstance(payload, dict) else []
    normalized = [
        normalize_contract(item)
        for item in items
        if isinstance(item, dict)
        and str(item.get("symbol") or item.get("displayName") or "").endswith("-USDT")
        and is_crypto_contract(item)
    ]
    with _CONTRACT_CACHE_LOCK:
        _CONTRACT_CACHE = {item["symbol"]: item for item in normalized}
        _CONTRACT_CACHE_TS = time.time()
    return {"code": 0, "msg": "", "data": normalized}


def futures_contract_detail(symbol: str) -> Dict[str, Any]:
    internal_symbol = to_internal_symbol(symbol)
    futures_contracts()
    with _CONTRACT_CACHE_LOCK:
        detail = _CONTRACT_CACHE.get(internal_symbol)
    if detail is None:
        raise BingxAPIError(f"BingX contract metadata missing for {internal_symbol}")
    return dict(detail)


def _normalize_ticker(item: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(item)
    normalized["symbol"] = to_internal_symbol(str(item.get("symbol")))
    normalized["amount24"] = item.get("quoteVolume", 0)
    return normalized


def futures_all_tickers() -> Dict[str, Any]:
    global _TICKER_CACHE, _TICKER_CACHE_TS
    payload = http_get("/openApi/swap/v2/quote/ticker")
    items = payload.get("data", []) if isinstance(payload, dict) else []
    if isinstance(items, dict):
        items = [items]
    normalized = [
        _normalize_ticker(item)
        for item in items
        if isinstance(item, dict) and str(item.get("symbol") or "").endswith("-USDT")
    ]
    with _TICKER_CACHE_LOCK:
        _TICKER_CACHE = {item["symbol"]: item for item in normalized}
        _TICKER_CACHE_TS = time.time()
    return {"code": 0, "msg": "", "data": normalized}


def futures_ticker(symbol: str) -> Dict[str, Any]:
    internal_symbol = to_internal_symbol(symbol)
    with _TICKER_CACHE_LOCK:
        if time.time() - _TICKER_CACHE_TS <= TICKER_CACHE_TTL_SECONDS:
            cached = _TICKER_CACHE.get(internal_symbol)
            if cached is not None:
                return {"code": 0, "msg": "", "data": dict(cached)}
    payload = http_get(
        "/openApi/swap/v2/quote/ticker",
        {"symbol": to_bingx_symbol(symbol)},
    )
    item = payload.get("data") or {}
    return {"code": 0, "msg": "", "data": _normalize_ticker(item)}


def futures_funding(symbol: str) -> Dict[str, Any]:
    return http_get(
        "/openApi/swap/v2/quote/premiumIndex",
        {"symbol": to_bingx_symbol(symbol)},
    )


def futures_kline(symbol: str, interval: str, limit: int = 200) -> Dict[str, Any]:
    payload = http_get(
        "/openApi/swap/v3/quote/klines",
        {
            "symbol": to_bingx_symbol(symbol),
            "interval": interval,
            "limit": max(1, min(int(limit), 1440)),
        },
        timeout=15,
    )
    raw_rows = payload.get("data", []) if isinstance(payload, dict) else []
    rows = []
    for item in raw_rows:
        if isinstance(item, dict):
            rows.append({
                "time": int(item["time"]) // 1000,
                "open": item["open"],
                "high": item["high"],
                "low": item["low"],
                "close": item["close"],
                "volume": item.get("volume", 0),
            })
        elif isinstance(item, list) and len(item) >= 6:
            rows.append({
                "time": int(item[0]) // 1000,
                "open": item[1],
                "high": item[2],
                "low": item[3],
                "close": item[4],
                "volume": item[5],
            })
    rows.sort(key=lambda row: row["time"])
    return {"code": 0, "msg": "", "data": rows}


def extract_contract_symbols(payload: Any) -> list:
    items = payload.get("data", []) if isinstance(payload, dict) else payload
    return sorted({
        str(item.get("symbol"))
        for item in (items or [])
        if isinstance(item, dict) and item.get("symbol") and item.get("active", True)
    })


def cache_path(symbol: str) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, f"{to_internal_symbol(symbol)}.snapshot.json")


def load_cache(symbol: str):
    try:
        with open(cache_path(symbol), encoding="utf-8") as source:
            return json.load(source)
    except (OSError, ValueError, TypeError):
        return None


def save_cache(symbol: str, payload: dict) -> None:
    path = cache_path(symbol)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as target:
        json.dump(payload, target, ensure_ascii=False)
    os.replace(temporary, path)


def build_snapshot(symbol: str) -> dict:
    internal_symbol = to_internal_symbol(symbol)
    return {
        "ts": int(time.time() * 1000),
        "exchange": "bingx",
        "symbol": internal_symbol,
        "contract": futures_contract_detail(internal_symbol),
        "ticker": futures_ticker(internal_symbol),
        "kline_1h": futures_kline(internal_symbol, "1h", 200),
        "kline_4h": futures_kline(internal_symbol, "4h", 200),
        "kline_1d": futures_kline(internal_symbol, "1d", 200),
        "stale": False,
    }


def build_snapshot_with_fallback(symbol: str) -> dict:
    try:
        snapshot = build_snapshot(symbol)
        save_cache(symbol, snapshot)
        return snapshot
    except Exception as exc:
        cached = load_cache(symbol)
        if cached:
            source_ts = int(cached.get("ts", 0) or 0)
            age_seconds = max(0.0, time.time() - source_ts / 1000.0)
            if age_seconds > SNAPSHOT_MAX_STALE_SECONDS:
                raise RuntimeError(
                    f"cached BingX snapshot too old ({age_seconds:.0f}s > "
                    f"{SNAPSHOT_MAX_STALE_SECONDS}s)"
                ) from exc
            cached = dict(cached)
            cached["stale"] = True
            cached["stale_reason"] = str(exc)
            cached["stale_at"] = int(time.time() * 1000)
            return cached
        raise


def _save_top_symbols(symbols: list) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    temporary = TOP_SYMBOLS_CACHE_PATH + ".tmp"
    with open(temporary, "w", encoding="utf-8") as target:
        json.dump({"ts": int(time.time() * 1000), "symbols": symbols}, target)
    os.replace(temporary, TOP_SYMBOLS_CACHE_PATH)


def _load_top_symbols() -> list:
    try:
        with open(TOP_SYMBOLS_CACHE_PATH, encoding="utf-8") as source:
            payload = json.load(source)
        return [str(symbol) for symbol in payload.get("symbols", []) if symbol]
    except (OSError, ValueError, TypeError, AttributeError):
        return []


def top_symbols_by_volume(n: int = 250) -> list:
    try:
        items = futures_all_tickers().get("data", [])
        active_contracts = {
            str(item["symbol"])
            for item in futures_contracts().get("data", [])
            if isinstance(item, dict) and item.get("active")
        }
        ranked = sorted(
            (
                (str(item["symbol"]), float(item.get("quoteVolume") or 0))
                for item in items
                if isinstance(item, dict) and item.get("symbol") in active_contracts
            ),
            key=lambda value: value[1],
            reverse=True,
        )
        symbols = [symbol for symbol, _ in ranked[:n]]
        if not symbols:
            raise ValueError("BingX ticker list contains no symbols")
        _save_top_symbols(symbols)
        return symbols
    except Exception as exc:
        cached = _load_top_symbols()
        fallback = cached[:n] or FALLBACK_SYMBOLS[:n]
        logger.warning(
            "BingX ticker ranking unavailable; using %s cached/fallback symbols: %s",
            len(fallback),
            exc,
        )
        return fallback


def cmd_symbols() -> None:
    symbols = extract_contract_symbols(futures_contracts())
    print(json.dumps({"ts": int(time.time() * 1000), "count": len(symbols), "symbols": symbols}))


def cmd_snapshot(symbol: str) -> None:
    print(json.dumps(build_snapshot_with_fallback(symbol), ensure_ascii=False))


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: bingx_snapshot.py symbols | snapshot SYMBOL", file=sys.stderr)
        raise SystemExit(2)
    command = sys.argv[1].strip().lower()
    if command == "symbols":
        cmd_symbols()
        return
    if command == "snapshot" and len(sys.argv) >= 3:
        cmd_snapshot(sys.argv[2].strip().upper())
        return
    print("unknown command. use: symbols | snapshot SYMBOL", file=sys.stderr)
    raise SystemExit(2)


if __name__ == "__main__":
    main()
