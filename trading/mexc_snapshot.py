#!/usr/bin/env python3
import json
import logging
import sys
import threading
import time
from urllib.parse import urlencode
from typing import Callable, Optional, Dict, Any

import warnings
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL*")

import os
import requests

BASE = "https://contract.mexc.com"
CACHE_DIR = os.path.expanduser("~/.openclaw/trading/cache")
TOP_SYMBOLS_CACHE_PATH = os.path.join(CACHE_DIR, "top_symbols.json")
MEXC_MIN_REQUEST_INTERVAL = max(0.1, float(os.getenv("MEXC_MIN_REQUEST_INTERVAL", "0.20")))
MEXC_MAX_ATTEMPTS = max(1, int(os.getenv("MEXC_MAX_ATTEMPTS", "4")))
SNAPSHOT_MAX_STALE_SECONDS = max(0, int(os.getenv("MEXC_SNAPSHOT_MAX_STALE_SECONDS", "7200")))
TICKER_CACHE_TTL_SECONDS = max(1, int(os.getenv("MEXC_TICKER_CACHE_TTL_SECONDS", "60")))
CONTRACT_CACHE_TTL_SECONDS = max(60, int(os.getenv("MEXC_CONTRACT_CACHE_TTL_SECONDS", "3600")))
FALLBACK_SYMBOLS = ["BTC_USDT", "ETH_USDT", "SOL_USDT"]

logger = logging.getLogger(__name__)


class MexcAPIError(RuntimeError):
    def __init__(self, message: str, *, code: Optional[int] = None):
        super().__init__(message)
        self.code = code


class MexcPublicClient:
    """Thread-safe public REST client with a process-wide request budget."""

    def __init__(
        self,
        *,
        min_interval: float = MEXC_MIN_REQUEST_INTERVAL,
        max_attempts: int = MEXC_MAX_ATTEMPTS,
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
    def _payload_error(payload: Any) -> Optional[MexcAPIError]:
        if not isinstance(payload, dict):
            return None
        raw_code = payload.get("code", 0)
        try:
            code = int(raw_code)
        except (TypeError, ValueError):
            code = None
        if payload.get("success") is False or code not in (None, 0):
            message = str(payload.get("message") or payload.get("msg") or "MEXC API error")
            return MexcAPIError(message, code=code)
        return None

    @staticmethod
    def _retryable(exc: Exception) -> bool:
        if isinstance(exc, MexcAPIError):
            return exc.code in {500, 501, 510}
        if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
            return True
        if isinstance(exc, requests.HTTPError) and exc.response is not None:
            return exc.response.status_code == 429 or exc.response.status_code >= 500
        return False

    def get(self, path: str, params: Optional[Dict[str, Any]] = None, timeout: int = 10):
        url = f"{BASE}{path}"
        if params:
            url = url + "?" + urlencode(params)
        request_get = self._request_get or requests.get

        for attempt in range(self.max_attempts):
            self._wait_for_slot()
            try:
                response = request_get(
                    url,
                    timeout=timeout,
                    headers={"User-Agent": "ucb-trading-mexc/1.2"},
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
                retry_after = None
                response = getattr(exc, "response", None)
                if response is not None:
                    try:
                        retry_after = float(response.headers.get("Retry-After", ""))
                    except (TypeError, ValueError):
                        retry_after = None
                backoff = retry_after if retry_after is not None else min(8.0, 2.0 ** attempt)
                logger.warning(
                    "MEXC request throttled/transient path=%s attempt=%s/%s retry_in=%.1fs: %s",
                    path,
                    attempt + 1,
                    self.max_attempts,
                    backoff,
                    exc,
                )
                self._sleep(max(0.0, backoff))

        raise RuntimeError("unreachable")


_PUBLIC_CLIENT = MexcPublicClient()
_TICKER_CACHE_LOCK = threading.Lock()
_TICKER_CACHE: Dict[str, Dict[str, Any]] = {}
_TICKER_CACHE_TS = 0.0
_CONTRACT_CACHE_LOCK = threading.Lock()
_CONTRACT_CACHE: Dict[str, Dict[str, Any]] = {}
_CONTRACT_CACHE_TS = 0.0

def http_get(path: str, params: Optional[Dict[str, Any]] = None, timeout: int = 10):
    return _PUBLIC_CLIENT.get(path, params=params, timeout=timeout)

def futures_contracts():
    global _CONTRACT_CACHE, _CONTRACT_CACHE_TS
    with _CONTRACT_CACHE_LOCK:
        if time.time() - _CONTRACT_CACHE_TS <= CONTRACT_CACHE_TTL_SECONDS and _CONTRACT_CACHE:
            return {"success": True, "code": 0, "data": list(_CONTRACT_CACHE.values())}
        payload = http_get("/api/v1/contract/detail")
        items = payload.get("data", []) if isinstance(payload, dict) else []
        if isinstance(items, list):
            _CONTRACT_CACHE = {
                str(item.get("symbol")): item
                for item in items
                if isinstance(item, dict) and item.get("symbol")
            }
            _CONTRACT_CACHE_TS = time.time()
        return payload


def futures_contract_detail(symbol: str) -> Dict[str, Any]:
    payload = futures_contracts()
    with _CONTRACT_CACHE_LOCK:
        detail = _CONTRACT_CACHE.get(symbol)
    if detail is None:
        raise MexcAPIError(f"MEXC contract metadata missing for {symbol}")
    return dict(detail)

def futures_ticker(symbol: str):
    with _TICKER_CACHE_LOCK:
        if time.time() - _TICKER_CACHE_TS <= TICKER_CACHE_TTL_SECONDS:
            cached = _TICKER_CACHE.get(symbol)
            if cached is not None:
                return {"success": True, "code": 0, "data": cached}
    return http_get("/api/v1/contract/ticker", {"symbol": symbol}, timeout=10)

def futures_funding(symbol: str):
    return http_get(f"/api/v1/contract/funding_rate/{symbol}", timeout=10)

def interval_seconds(interval: str) -> int:
    m = {
        "Min1": 60,
        "Min5": 5 * 60,
        "Min15": 15 * 60,
        "Min30": 30 * 60,
        "Min60": 60 * 60,
        "Hour4": 4 * 60 * 60,
        "Hour8": 8 * 60 * 60,
        "Day1": 24 * 60 * 60,
        "Day2": 2 * 24 * 60 * 60,
        "Week1": 7 * 24 * 60 * 60,
        "Month1": 30 * 24 * 60 * 60,
    }
    return m.get(interval, 60)

def futures_kline(symbol: str, interval: str, limit: int = 200):
    end = int(time.time())
    start = end - interval_seconds(interval) * limit
    return http_get(
        f"/api/v1/contract/kline/{symbol}",
        {"interval": interval, "start": start, "end": end},
        timeout=15
    )

def extract_contract_symbols(payload) -> list:
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = payload.get("data", payload)
    else:
        items = payload

    if isinstance(items, dict):
        for key in ("contracts", "symbols", "rows", "items", "list"):
            v = items.get(key)
            if isinstance(v, list):
                items = v
                break

    out = []
    if isinstance(items, list):
        for it in items:
            if isinstance(it, str):
                out.append(it)
            elif isinstance(it, dict):
                sym = it.get("symbol") or it.get("contractCode") or it.get("name")
                if sym:
                    out.append(str(sym))
    return sorted(set(out))

def cache_path(symbol: str) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    safe = symbol.replace("/", "_")
    return os.path.join(CACHE_DIR, f"{safe}.snapshot.json")

def load_cache(symbol: str):
    p = cache_path(symbol)
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def save_cache(symbol: str, payload: dict):
    p = cache_path(symbol)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    os.replace(tmp, p)

def cmd_symbols():
    payload = futures_contracts()
    syms = extract_contract_symbols(payload)
    print(json.dumps({"ts": int(time.time() * 1000), "count": len(syms), "symbols": syms}, ensure_ascii=False))

def build_snapshot(symbol: str) -> dict:
    return {
        "ts": int(time.time() * 1000),
        "symbol": symbol,
        "contract": futures_contract_detail(symbol),
        "ticker": futures_ticker(symbol),
        "kline_1h": futures_kline(symbol, "Min60", 200),
        "kline_4h": futures_kline(symbol, "Hour4", 200),
        "kline_1d": futures_kline(symbol, "Day1", 200),
        "stale": False,
    }

def build_snapshot_with_fallback(symbol: str) -> dict:
    try:
        out = build_snapshot(symbol)
        save_cache(symbol, out)
        return out
    except Exception as e:
        cached = load_cache(symbol)
        if cached:
            source_ts = int(cached.get("ts", 0) or 0)
            age_seconds = max(0.0, time.time() - source_ts / 1000.0)
            if age_seconds > SNAPSHOT_MAX_STALE_SECONDS:
                raise RuntimeError(
                    f"cached snapshot too old ({age_seconds:.0f}s > {SNAPSHOT_MAX_STALE_SECONDS}s)"
                ) from e
            cached = dict(cached)
            cached["stale"] = True
            cached["stale_reason"] = str(e)
            cached["stale_at"] = int(time.time() * 1000)
            return cached
        raise

def futures_all_tickers():
    global _TICKER_CACHE, _TICKER_CACHE_TS
    payload = http_get("/api/v1/contract/ticker")
    items = payload.get("data", []) if isinstance(payload, dict) else []
    if isinstance(items, list):
        with _TICKER_CACHE_LOCK:
            _TICKER_CACHE = {
                str(item.get("symbol")): item
                for item in items
                if isinstance(item, dict) and item.get("symbol")
            }
            _TICKER_CACHE_TS = time.time()
    return payload


def _save_top_symbols(symbols: list) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    tmp = TOP_SYMBOLS_CACHE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump({"ts": int(time.time() * 1000), "symbols": symbols}, handle)
    os.replace(tmp, TOP_SYMBOLS_CACHE_PATH)


def _load_top_symbols() -> list:
    try:
        with open(TOP_SYMBOLS_CACHE_PATH, encoding="utf-8") as handle:
            payload = json.load(handle)
        symbols = payload.get("symbols", []) if isinstance(payload, dict) else []
        return [str(symbol) for symbol in symbols if symbol]
    except (OSError, ValueError, TypeError):
        return []

def top_symbols_by_volume(n: int = 250) -> list:
    try:
        data = futures_all_tickers()
        items = data.get("data", []) if isinstance(data, dict) else (data or [])
        if not isinstance(items, list) or not items:
            raise ValueError("unexpected ticker format")
        tickers = []
        for t in items:
            if not isinstance(t, dict):
                continue
            sym = t.get("symbol", "")
            if not sym:
                continue
            vol = 0.0
            for key in ("amount24", "volume24", "turnover", "amount"):
                v = t.get(key)
                if v is not None:
                    try:
                        vol = float(v)
                        break
                    except Exception:
                        pass
            tickers.append((sym, vol))
        tickers.sort(key=lambda x: x[1], reverse=True)
        symbols = [sym for sym, _ in tickers[:n]]
        if not symbols:
            raise ValueError("ticker list contains no symbols")
        _save_top_symbols(symbols)
        return symbols
    except Exception as exc:
        cached = _load_top_symbols()
        fallback = cached[:n] or FALLBACK_SYMBOLS[:n]
        logger.warning("MEXC ticker ranking unavailable; using %s cached/fallback symbols: %s", len(fallback), exc)
        return fallback

def cmd_snapshot(symbol: str):
    out = build_snapshot_with_fallback(symbol)
    print(json.dumps(out, ensure_ascii=False))

def main():
    if len(sys.argv) < 2:
        print("usage: mexc_snapshot.py symbols | snapshot SYMBOL", file=sys.stderr)
        sys.exit(2)

    cmd = sys.argv[1].strip().lower()

    if cmd == "symbols":
        cmd_symbols()
        return

    if cmd == "snapshot":
        if len(sys.argv) < 3:
            print("usage: mexc_snapshot.py snapshot BTC_USDT", file=sys.stderr)
            sys.exit(2)
        symbol = sys.argv[2].strip().upper()
        cmd_snapshot(symbol)
        return

    print("unknown command. use: symbols | snapshot SYMBOL", file=sys.stderr)
    sys.exit(2)

if __name__ == "__main__":
    main()
