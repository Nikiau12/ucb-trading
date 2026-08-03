import json
import os
import re
import time
import urllib.parse
import urllib.request
from html import unescape


class MexcListingWatcher:
    def __init__(
        self,
        snapshot_file: str,
        announcements_snapshot_file: str = "mexc_announcements_snapshot.json",
        announcements_url: str = "https://www.mexc.com/announcements/new-listings",
        min_first_run_silence: bool = True,
    ):
        self.snapshot_file = snapshot_file
        self.announcements_snapshot_file = announcements_snapshot_file
        self.announcements_url = announcements_url
        self.min_first_run_silence = min_first_run_silence
        self.last_checked_at = 0

    async def check_new_markets(self, exchange_client) -> list:
        await exchange_client.load_markets_if_needed()
        current = self._extract_mexc_usdt_markets(exchange_client.exchange.markets)
        previous = self._load_snapshot()

        if not previous:
            self._save_snapshot(current)
            return [] if self.min_first_run_silence else sorted(current)

        new_symbols = sorted(current - previous)
        if new_symbols:
            self._save_snapshot(current)
        else:
            self.last_checked_at = time.time()
        return new_symbols

    async def check_new_announcements(self) -> list:
        announcements = self._fetch_announcements()
        current_ids = {item["id"] for item in announcements}
        previous_ids = self._load_json_set(self.announcements_snapshot_file)

        if not previous_ids:
            self._save_json_set(self.announcements_snapshot_file, current_ids)
            return [] if self.min_first_run_silence else announcements

        new_items = [item for item in announcements if item["id"] not in previous_ids]
        if new_items:
            self._save_json_set(self.announcements_snapshot_file, current_ids | previous_ids)
        return new_items

    def _fetch_announcements(self) -> list:
        try:
            parsed = urllib.parse.urlparse(self.announcements_url)
            if parsed.scheme != "https" or parsed.hostname not in {"mexc.com", "www.mexc.com"}:
                raise ValueError("unsupported MEXC announcements URL")
            req = urllib.request.Request(
                self.announcements_url,
                headers={"user-agent": "mexc-signal-bot/1.0"},
            )
            with urllib.request.urlopen(req, timeout=15) as response:  # nosec B310
                page = response.read().decode("utf-8", errors="ignore")
        except Exception as e:
            print(f"[MexcListingWatcher] announcements fetch failed: {e}")
            return []

        pattern = re.compile(
            r'<a title="(?P<title>[^"]+)"[^>]+href="(?P<href>/announcements/article/[^"]+)"'
            r'.{0,500}?<time[^>]+dateTime="(?P<time>[^"]+)"',
            re.S,
        )
        announcements = []
        for match in pattern.finditer(page):
            title = unescape(match.group("title")).strip()
            href = match.group("href")
            published_at = match.group("time")
            if not self._looks_like_listing(title):
                continue
            announcements.append({
                "id": href.rsplit("/", 1)[-1],
                "title": title,
                "url": "https://www.mexc.com" + href,
                "published_at": published_at,
                "symbols": self._extract_symbols(title),
            })
        return announcements[:30]

    def _extract_mexc_usdt_markets(self, markets: dict) -> set:
        symbols = set()
        for symbol, market in markets.items():
            if not market.get("active", True):
                continue
            quote = str(market.get("quote", "")).upper()
            if quote == "USDT" and (market.get("spot") or market.get("swap")):
                symbols.add(symbol)
        return symbols

    def _load_snapshot(self) -> set:
        return self._load_json_set(self.snapshot_file)

    def _save_snapshot(self, symbols: set):
        self._save_json_set(self.snapshot_file, symbols)
        self.last_checked_at = time.time()

    def _load_json_set(self, path: str) -> set:
        if not os.path.exists(path):
            return set()
        try:
            with open(path, "r") as f:
                return set(json.load(f))
        except Exception as e:
            print(f"[MexcListingWatcher] snapshot read failed: {e}")
            return set()

    def _save_json_set(self, path: str, values: set):
        try:
            with open(path, "w") as f:
                json.dump(sorted(values), f, indent=2)
        except Exception as e:
            print(f"[MexcListingWatcher] snapshot write failed: {e}")

    def _looks_like_listing(self, title: str) -> bool:
        lowered = title.lower()
        keywords = [
            "listing",
            "list ",
            "will list",
            "pre-market",
            "new futures trading",
            "new spot",
            "coming soon",
        ]
        return any(keyword in lowered for keyword in keywords)

    def _extract_symbols(self, title: str) -> list:
        symbols = set()
        stop_words = {"UTC", "USDT", "MEXC", "ETF", "FEE"}
        for match in re.findall(r"\(([A-Z0-9]{1,12})\)", title):
            symbols.add(match)
        for match in re.findall(r"\b([A-Z0-9]{2,20})USDT\b", title):
            symbols.add(match)
        for match in re.findall(r"\b([A-Z0-9]{1,12})\s+USDT-M\b", title):
            symbols.add(match)
        list_match = re.search(r"Listings?:\s+([A-Z0-9,\s]+?)\s+USDT", title)
        if list_match:
            for match in re.findall(r"\b[A-Z0-9]{1,12}\b", list_match.group(1)):
                symbols.add(match)
        return sorted(symbol for symbol in symbols if symbol not in stop_words)
