"""Public-only, bounded BingX candle capture for reproducible sector research.

No environment/config/private API imports. Downloading requires explicit --collect
in the caller; subsequent diagnosis replays the captured responses offline.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import urlencode, parse_qs, urlparse

from trading.analytics.structure import Bar

FOUR_HOURS = 14_400
DAY = 86_400


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def normalize_candles(rows):
    result = {}
    for row in rows:
        if isinstance(row, dict):
            values = [row[k] for k in ("time", "open", "high", "low", "close", "volume")]
        elif isinstance(row, list) and len(row) >= 6:
            values = row[:6]
        else:
            raise ValueError("Unexpected candle schema")
        stamp = int(values[0])
        stamp = stamp // 1000 if stamp > 10_000_000_000 else stamp
        o, h, low, c, v = map(float, values[1:])
        if stamp % FOUR_HOURS or not all(math.isfinite(x) for x in (o, h, low, c, v)):
            raise ValueError("Nonfinite or unaligned candle")
        if min(o, h, low, c) <= 0 or v < 0 or low > min(o, c) or h < max(o, c):
            raise ValueError("Invalid OHLCV")
        bar = Bar(stamp, o, h, low, c, v)
        if stamp in result and result[stamp] != bar:
            raise ValueError("Conflicting duplicate candle")
        result[stamp] = bar
    return sorted(result.values(), key=lambda b: b.ts)


class CandleCapture:
    def __init__(self, cache_dir, *, collect=False, interval=1.1, request=None):
        self.cache_dir = Path(cache_dir)
        self.collect = collect
        self.interval = max(1.0, interval)
        self.last_request = 0.0
        self.request = request

    def load(self, symbol, start, end):
        if not re.fullmatch(r"[A-Z0-9]+_USDT", symbol) or not 0 <= start < end:
            raise ValueError("Invalid symbol/window")
        path = self.cache_dir / f"{symbol}-4h-{start}-{end}.json"
        if path.exists():
            saved = json.loads(path.read_text())
            if saved["symbol"] != symbol or saved["start"] != start or saved["end"] != end:
                raise ValueError("Cache identity mismatch")
            if digest(saved["rows"]) != saved["sha256"]:
                raise ValueError("Cache digest mismatch")
            if saved.get("capture_version") == 2:
                self.verify(saved)
            return normalize_candles(saved["rows"]), saved["sha256"]
        if not self.collect:
            raise ValueError(f"Missing frozen cache for {symbol}; run with --collect")
        # Exclude the unfinished 4H bucket even if end is not aligned.
        complete_end = end // FOUR_HOURS * FOUR_HOURS
        pages, cursor, all_rows = [], complete_end * 1000 - 1, []
        # Explicit cap prevents infinite pagination and accidentally huge fetches.
        for _ in range(8):
            params = {"symbol": symbol.replace("_", "-"), "interval": "4h", "limit": 1440,
                      "startTime": start * 1000, "endTime": cursor}
            url = "https://open-api.bingx.com/openApi/swap/v3/quote/klines?" + urlencode(params)
            for attempt in range(3):
                try:
                    if self.request is not None:
                        body = self.request(params)
                    else:
                        time.sleep(max(0, self.interval - (time.monotonic() - self.last_request)))
                        self.last_request = time.monotonic()
                        response = subprocess.run(
                            ["curl", "--disable", "--fail", "--silent", "--show-error", "--max-time", "25", url],
                            capture_output=True, text=True, timeout=30, check=False,
                        )
                        if response.returncode:
                            raise ValueError(response.stderr.strip()[:200])
                        body = json.loads(response.stdout)
                    if body.get("code") != 0:
                        raise ValueError(f"BingX code={body.get('code')}")
                    page = normalize_candles(body.get("data", []))
                    break
                except (ValueError, json.JSONDecodeError):
                    if attempt == 2:
                        raise
                    time.sleep(2 ** attempt)
            pages.append({"url": url, "fetched_at": int(time.time()), "response": body, "sha256": digest(body)})
            if any(not start <= b.ts or b.ts + FOUR_HOURS > complete_end or b.ts * 1000 > cursor for b in page):
                raise ValueError("4H response outside requested completed window")
            if not page:
                break
            all_rows.extend([[b.ts, b.o, b.h, b.l, b.c, b.v] for b in page])
            earliest = page[0].ts
            # A short nonempty response is NOT proof of exhausted history:
            # the public API can return fewer rows than the requested limit.
            if earliest <= start:
                break
            next_cursor = earliest * 1000 - 1
            if next_cursor >= cursor:
                raise ValueError("Pagination made no progress")
            cursor = next_cursor
        else:
            raise ValueError("Candle page budget exceeded")
        bars = normalize_candles(all_rows)
        rows = [[b.ts, b.o, b.h, b.l, b.c, b.v] for b in bars]
        payload = {"capture_version": 2, "query_exhausted": True,
                   "symbol": symbol, "start": start, "end": end, "rows": rows,
                   "sha256": digest(rows), "pages": pages}
        self.verify(payload)
        write_json(path, payload)
        return bars, payload["sha256"]

    @staticmethod
    def verify(saved):
        start, end, symbol = saved["start"], saved["end"], saved["symbol"]
        complete_end = end // FOUR_HOURS * FOUR_HOURS
        cursor, rebuilt, exhausted = complete_end * 1000 - 1, [], False
        pages = saved.get("pages", [])
        if not 1 <= len(pages) <= 8 or saved.get("query_exhausted") is not True:
            raise ValueError("Missing 4H pagination proof")
        for page in pages:
            url = urlparse(page["url"])
            expected = {"symbol": [symbol.replace("_", "-")], "interval": ["4h"], "limit": ["1440"],
                        "startTime": [str(start * 1000)], "endTime": [str(cursor)]}
            if (exhausted or url.scheme != "https" or url.netloc != "open-api.bingx.com"
                    or url.path != "/openApi/swap/v3/quote/klines" or parse_qs(url.query) != expected):
                raise ValueError("Broken 4H pagination")
            body = page["response"]
            if body.get("code") != 0 or digest(body) != page["sha256"] or not isinstance(body.get("data"), list):
                raise ValueError("Modified 4H response")
            bars = normalize_candles(body["data"])
            if any(b.ts < start or b.ts + FOUR_HOURS > complete_end or b.ts * 1000 > cursor for b in bars):
                raise ValueError("4H response outside requested window")
            rebuilt.extend([[b.ts, b.o, b.h, b.l, b.c, b.v] for b in bars])
            exhausted = not bars or bars[0].ts == start
            if bars:
                cursor = bars[0].ts * 1000 - 1
        rows = [[b.ts, b.o, b.h, b.l, b.c, b.v] for b in normalize_candles(rebuilt)]
        if not exhausted or rows != saved["rows"] or digest(rows) != saved["sha256"]:
            raise ValueError("Incomplete or modified 4H capture")


def closed_snapshot(symbol, bars, decision_time):
    """Only the latest contiguous run, never a partially formed candle or day."""
    closed = [b for b in bars if b.ts + FOUR_HOURS <= decision_time]
    for i in range(len(closed) - 1, 0, -1):
        if closed[i].ts - closed[i - 1].ts != FOUR_HOURS:
            closed = closed[i:]
            break
    daily = []
    buckets = {}
    for b in closed:
        buckets.setdefault(b.ts // DAY * DAY, []).append(b)
    for start, chunk in sorted(buckets.items()):
        if start + DAY <= decision_time and len(chunk) == 6 and chunk[0].ts == start:
            daily.append(Bar(start, chunk[0].o, max(b.h for b in chunk), min(b.l for b in chunk), chunk[-1].c, sum(b.v for b in chunk)))
    def rows(items):
        return [[b.ts, b.o, b.h, b.l, b.c, b.v] for b in items]
    return {"symbol": symbol, "decision_time": decision_time,
            "ticker": {"data": {"lastPrice": closed[-1].c if closed else None}},
            "kline_4h": {"data": rows(closed[-240:])}, "kline_1d": {"data": rows(daily[-120:])},
            "kline_1h": {"data": []}, "stale": False}
