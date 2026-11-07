"""Read-only, reproducible sector analysis. Never imports bot config or credentials.

Example (pdfplumber is required only for PDF extraction):
  python evaluation/sector_liquidity_audit.py --pdf report.pdf --out audit/ --collect
  python evaluation/sector_liquidity_audit.py --pdf report.pdf --out audit/

The second command replays saved public responses without network access.
No private endpoint, order, database, Telegram or Railway code is used.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import subprocess
import threading
import time
from urllib.parse import urlencode

BASE_URL = "https://open-api.bingx.com"
ALLOWED_PATHS = {
    "/openApi/swap/v2/quote/contracts",
    "/openApi/swap/v2/quote/ticker",
    "/openApi/swap/v2/quote/depth",
    "/openApi/swap/v3/quote/klines",
}
OUTCOME_MAP = {
    "Стоп до TP1": "stop",
    "TP1, затем БУ": "tp1_be",
    "TP1 и TP2": "tp2",
    "TP1, ещё активна": "tp1_open",
    "Активна до TP1": "active",
    "Истекла после входа": "expired",
}
PATTERN = re.compile(
    r"^#(?P<id>\d+)\s+(?P<symbol>[A-Z0-9]+_USDT)\s+"
    r"(?P<signal>\d\d\.\d\d \d\d:\d\d)\s+"
    r"(?P<entrytime>\d\d\.\d\d \d\d:\d\d)\s+"
    r"(?P<side>LONG|SHORT)\s+(?P<confidence>\d+\.\d+)%\s+"
    r"(?P<entry>\d+(?:\.\d+)?)\s+(?P<stop>\d+(?:\.\d+)?)\s+"
    r"(?P<tp1>\d+(?:\.\d+)?)\s+(?P<tp2>\d+(?:\.\d+)?)\s+"
    r"(?P<result>.+)$"
)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def validate_registry(registry):
    mapping = {}
    ids = set()
    for group in registry["groups"]:
        if group["id"] in ids:
            raise ValueError(f"Duplicate group: {group['id']}")
        ids.add(group["id"])
        for symbol in group["symbols"]:
            if symbol in mapping or not re.fullmatch(r"[A-Z0-9]+_USDT", symbol):
                raise ValueError(f"Duplicate or invalid symbol: {symbol}")
            mapping[symbol] = group["id"]
    return mapping


def extract_entries(pdf_path, registry):
    import pdfplumber
    mapping = validate_registry(registry)
    rows, seen = [], set()
    with pdfplumber.open(pdf_path) as pdf:
        first_page = pdf.pages[0].extract_text() or ""
        if "07.11.2026 13:36 Paris" not in first_page:
            raise ValueError("Unexpected PDF snapshot; update the explicit source controls first")
        for page_no, page in enumerate(pdf.pages, 1):
            for line in (page.extract_text() or "").splitlines():
                if not line.startswith("#"):
                    continue
                match = PATTERN.fullmatch(line)
                if not match:
                    raise ValueError(f"Unparsed entry on page {page_no}: {line}")
                row = match.groupdict()
                if row["id"] in seen:
                    raise ValueError(f"Duplicate signal ID: {row['id']}")
                seen.add(row["id"])
                if row["symbol"] not in mapping or row["result"] not in OUTCOME_MAP:
                    raise ValueError(f"Unmapped symbol or outcome: {row}")
                for key in ("entry", "stop", "tp1", "tp2", "confidence"):
                    row[key] = float(row[key])
                row["confidence"] /= 100
                row["id"] = int(row["id"])
                row["group"] = mapping[row["symbol"]]
                row["outcome"] = OUTCOME_MAP[row["result"]]
                row["pdf_page"] = page_no
                for key in ("signal", "entrytime"):
                    row[key + "_utc"] = datetime.strptime("2026 " + row[key], "%Y %d.%m %H:%M").replace(tzinfo=timezone.utc).isoformat()
                row["geometry_valid"] = (
                    row["stop"] < row["entry"] < row["tp1"] < row["tp2"]
                    if row["side"] == "LONG" else
                    row["stop"] > row["entry"] > row["tp1"] > row["tp2"]
                )
                rows.append(row)
    controls = {"stop": 176, "tp1_be": 39, "tp2": 46, "tp1_open": 14, "active": 29, "expired": 4}
    if len(rows) != 308 or len({r["symbol"] for r in rows}) != 89:
        raise ValueError("PDF row/symbol count does not match the preserved snapshot")
    if dict(Counter(r["outcome"] for r in rows)) != controls:
        raise ValueError("PDF outcome totals do not reconcile")
    return rows


def aggregate(rows, registry):
    result = []
    for group in registry["groups"]:
        for side in ("LONG", "SHORT"):
            subset = [r for r in rows if r["group"] == group["id"] and r["side"] == side]
            counts = Counter(r["outcome"] for r in subset)
            n = len(subset)
            closed = counts["stop"] + counts["tp1_be"] + counts["tp2"]
            positive = counts["tp1_be"] + counts["tp2"]
            result.append({
                "group": group["id"], "group_name": group["name_ru"], "side": side,
                "entries": n, "unique_symbols": len({r["symbol"] for r in subset}),
                **{k: counts[k] for k in OUTCOME_MAP.values()},
                "resolved": closed, "positive_model_outcomes": positive,
                "conditional_winrate": positive / closed if closed else None,
                "stop_per_entry": counts["stop"] / n if n else None,
                "tp1_reached_per_entry": (positive + counts["tp1_open"]) / n if n else None,
                "tp2_per_entry": counts["tp2"] / n if n else None,
                "small_resolved_sample": closed < 20,
            })
    return result


class PublicCollector:
    def __init__(self, raw_dir, interval=0.5):
        self.raw_dir = Path(raw_dir)
        self.lock = threading.Lock()
        self.last_request = 0.0
        self.interval = interval

    def fetch(self, name, path, params=None):
        if path not in ALLOWED_PATHS:
            raise ValueError("Only allowlisted public quote endpoints are permitted")
        params = params or {}
        if set(params) - {"symbol", "interval", "limit"}:
            raise ValueError("Unexpected public-query parameter")
        url = BASE_URL + path + ("?" + urlencode(params) if params else "")
        record = {"url": url, "requested_at_utc": utc_now()}
        for attempt in range(3):
            with self.lock:
                time.sleep(max(0, self.interval - (time.monotonic() - self.last_request)))
                self.last_request = time.monotonic()
            # curl uses the host's supported HTTPS transport. No authentication headers.
            request = subprocess.run(
                ["curl", "--disable", "--fail", "--silent", "--show-error", "--max-time", "20", url],
                capture_output=True, text=True, timeout=25, check=False,
            )
            record["received_at_utc"] = utc_now()
            try:
                if request.returncode:
                    raise ValueError(request.stderr.strip()[:400])
                body = json.loads(request.stdout)
                if body.get("code") != 0:
                    raise ValueError(f"BingX {body.get('code')}: {body.get('msg')}")
                record["response"] = body
                record.pop("error", None)
                break
            except (ValueError, json.JSONDecodeError) as exc:
                record["error"] = str(exc)
                if attempt < 2:
                    time.sleep(2 ** attempt)
        write_json(self.raw_dir / (name + ".json"), record)
        return name, "error" not in record


def collect(registry, out_dir):
    client = PublicCollector(out_dir / "raw")
    symbols = list(validate_registry(registry))
    start = utc_now()
    for name, path in (("contracts", "/openApi/swap/v2/quote/contracts"), ("tickers", "/openApi/swap/v2/quote/ticker")):
        name, ok = client.fetch(name, path)
        print(f"{name}: {'OK' if ok else 'ERROR'}", flush=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        for round_number in range(1, 4):
            jobs = [pool.submit(client.fetch, f"depth_{round_number}_{s}", "/openApi/swap/v2/quote/depth", {"symbol": s.replace("_", "-"), "limit": 1000}) for s in symbols]
            completed, failed = 0, 0
            for job in as_completed(jobs):
                _, ok = job.result()
                completed += 1
                failed += not ok
                if completed % 25 == 0 or completed == len(symbols):
                    print(f"book round {round_number}: {completed}/{len(symbols)}, errors={failed}", flush=True)
        jobs = [pool.submit(client.fetch, f"daily_{s}", "/openApi/swap/v3/quote/klines", {"symbol": s.replace("_", "-"), "interval": "1d", "limit": 32}) for s in symbols]
        completed, failed = 0, 0
        for job in as_completed(jobs):
            _, ok = job.result()
            completed += 1
            failed += not ok
            if completed % 25 == 0 or completed == len(symbols):
                print(f"daily candles: {completed}/{len(symbols)}, errors={failed}", flush=True)
    write_json(out_dir / "collection.json", {"started_at_utc": start, "finished_at_utc": utc_now(), "symbols": len(symbols), "request_interval_seconds": client.interval, "orderbook_rounds": 3})


def load_raw(raw_dir, name):
    path = raw_dir / (name + ".json")
    return json.loads(path.read_text()) if path.exists() else {"error": "not collected"}


def positive_number(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError("Nonpositive/nonfinite market value")
    return number


def simulated_impact(levels, mid, notional, side):
    """Same base quantity (notional/mid) on both sides, no actual order."""
    remaining = target_quantity = notional / mid
    cost = 0.0
    for price, quantity in levels:
        take = min(remaining, quantity)
        cost += take * price
        remaining -= take
        if remaining <= target_quantity * 1e-12:
            vwap = cost / target_quantity
            return ((vwap / mid - 1) if side == "buy" else (1 - vwap / mid)) * 10000
    return None


def book_metrics(record, max_age=120):
    if record.get("error"):
        return {"error": record["error"]}
    try:
        data = record["response"]["data"]
        # Coin quantities are in the instrument's quoted base unit, including 1000* tickers.
        bids = sorted([(positive_number(p), positive_number(q)) for p, q in data.get("bidsCoin", data["bids"])], reverse=True)
        asks = sorted([(positive_number(p), positive_number(q)) for p, q in data.get("asksCoin", data["asks"])])
        if not bids or not asks or bids[0][0] >= asks[0][0]:
            raise ValueError("Empty or crossed order book")
        received = datetime.fromisoformat(record["received_at_utc"]).timestamp()
        age = received - float(data["T"]) / 1000
        if age > max_age or age < -60:
            raise ValueError(f"Stale/future book timestamp: age={age:.1f}s")
        mid = (bids[0][0] + asks[0][0]) / 2
        metrics = {"mid": mid, "spread_bps": (asks[0][0] - bids[0][0]) / mid * 10000, "age_seconds": age, "received_at_utc": record["received_at_utc"]}
        for band in (10, 25, 50, 100):
            lower, upper = mid * (1 - band / 10000), mid * (1 + band / 10000)
            metrics[f"bid_depth_{band}bps_usdt"] = sum(p * q for p, q in bids if p >= lower)
            metrics[f"ask_depth_{band}bps_usdt"] = sum(p * q for p, q in asks if p <= upper)
            metrics[f"depth_{band}bps_complete"] = bids[-1][0] <= lower and asks[-1][0] >= upper
        for notional in (300, 1000, 5000):
            metrics[f"buy_{notional}_impact_bps"] = simulated_impact(asks, mid, notional, "buy")
            metrics[f"sell_{notional}_impact_bps"] = simulated_impact(bids, mid, notional, "sell")
        return metrics
    except (KeyError, ValueError, TypeError) as exc:
        return {"error": str(exc)}


def liquidity(registry, out_dir):
    raw_dir = out_dir / "raw"
    contracts_raw = load_raw(raw_dir, "contracts")
    tickers_raw = load_raw(raw_dir, "tickers")
    contracts = {r["symbol"]: r for r in contracts_raw.get("response", {}).get("data", [])}
    tickers = {r["symbol"]: r for r in tickers_raw.get("response", {}).get("data", [])}
    mapping = validate_registry(registry)
    limits = registry["review_thresholds"]
    rows = []
    for symbol, group in mapping.items():
        exchange_symbol = symbol.replace("_", "-")
        contract, ticker = contracts.get(exchange_symbol), tickers.get(exchange_symbol)
        books = [book_metrics(load_raw(raw_dir, f"depth_{i}_{symbol}"), limits["max_orderbook_age_seconds"]) for i in range(1, 4)]
        valid = [b for b in books if "error" not in b]
        row = {"symbol": symbol, "group": group, "exchange_symbol": exchange_symbol, "books_valid": len(valid), "books": books, "flags": []}
        row["active_contract"] = bool(contract and int(contract.get("status", 0)) == 1 and str(contract.get("apiStateOpen")).lower() == "true")
        row["quote_volume_24h_usdt"] = float(ticker["quoteVolume"]) if ticker and ticker.get("quoteVolume") is not None else None
        row["ticker_close_time_ms"] = ticker.get("closeTime") if ticker else None
        row["contract_launch_time_ms"] = contract.get("launchTime") if contract else None
        row["min_order_usdt"] = contract.get("tradeMinUSDT") if contract else None
        if not row["active_contract"]:
            row["flags"].append("contract_unavailable")
        if len(valid) < 3:
            row["flags"].append("incomplete_book_samples")
        if row["quote_volume_24h_usdt"] is None:
            row["flags"].append("missing_turnover")
        elif row["quote_volume_24h_usdt"] < limits["min_24h_quote_volume_usdt"]:
            row["flags"].append("24h_turnover_below_1m")
        if valid:
            row["spread_median_bps"] = statistics.median(b["spread_bps"] for b in valid)
            row["spread_max_bps"] = max(b["spread_bps"] for b in valid)
            row["min_bid_depth_50bps_usdt"] = min(b["bid_depth_50bps_usdt"] for b in valid)
            row["min_ask_depth_50bps_usdt"] = min(b["ask_depth_50bps_usdt"] for b in valid)
            row["depth_50bps_complete"] = all(b["depth_50bps_complete"] for b in valid)
            if row["spread_max_bps"] > limits["max_spread_bps"]:
                row["flags"].append("spread_above_10bps")
            if min(row["min_bid_depth_50bps_usdt"], row["min_ask_depth_50bps_usdt"]) < limits["min_depth_50bps_usdt_per_side"]:
                row["flags"].append("visible_depth_50bps_below_10k")
            for notional in (300, 1000, 5000):
                for side in ("buy", "sell"):
                    key = f"{side}_{notional}_impact_bps"
                    values = [b[key] for b in valid]
                    row[key.replace("_impact", "_max_impact")] = max(values) if all(x is not None for x in values) else None
            impacts = [row[f"{s}_1000_max_impact_bps"] for s in ("buy", "sell")]
            if any(x is None for x in impacts):
                row["flags"].append("insufficient_visible_depth_for_1000")
            elif max(impacts) > limits["max_1000usdt_impact_bps"]:
                row["flags"].append("1000usdt_impact_above_10bps")
        daily_raw = load_raw(raw_dir, f"daily_{symbol}")
        day_start = int(datetime.fromisoformat(daily_raw.get("received_at_utc", utc_now())).timestamp() // 86400 * 86400000)
        daily = sorted(daily_raw.get("response", {}).get("data", []), key=lambda x: int(x["time"]))
        daily = [r for r in daily if int(r["time"]) < day_start][-30:]
        daily_times = [int(r["time"]) for r in daily]
        consecutive = all(b - a == 86400000 for a, b in zip(daily_times, daily_times[1:]))
        row["completed_daily_bars"] = len(daily)
        row["daily_contiguous"] = consecutive
        # Quote turnover is NOT returned by this endpoint. Label close*base-volume as an estimate.
        row["median_daily_turnover_est_usdt"] = statistics.median(float(d["volume"]) * float(d["close"]) for d in daily) if daily else None
        row["daily_period_start_ms"] = daily_times[0] if daily else None
        row["daily_period_end_ms"] = daily_times[-1] if daily else None
        if len(daily) < 30 or not consecutive or (daily and daily_times[-1] != day_start - 86400000):
            row["flags"].append("incomplete_30d_history")
        row["data_status"] = "incomplete" if any(x in row["flags"] for x in ("contract_unavailable", "incomplete_book_samples", "missing_turnover")) else "complete"
        rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=Path(__file__).with_name("asset_groups.v1.json"))
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--collect", action="store_true")
    args = parser.parse_args()
    registry = json.loads(args.registry.read_text())
    entries = extract_entries(args.pdf, registry)
    args.out.mkdir(parents=True, exist_ok=True)
    write_json(args.out / "asset_groups.v1.json", registry)
    write_json(args.out / "entered_signals.json", entries)
    write_json(args.out / "group_side_statistics.json", aggregate(entries, registry))
    write_json(args.out / "methodology.json", {
        "source_pdf": args.pdf.name,
        "source_pdf_sha256": hashlib.sha256(args.pdf.read_bytes()).hexdigest(),
        "source_snapshot_utc": "2026-11-07T12:36:00+00:00",
        "registry_version": registry["version"],
        "historical_rows": len(entries), "historical_symbols": len(validate_registry(registry)),
        "geometry_invalid_signal_ids": [r["id"] for r in entries if not r["geometry_valid"]],
        "conditional_winrate": "(tp1_be + tp2) / (stop + tp1_be + tp2); open and expired excluded. Not net profitability.",
        "tp1_reached": "tp1_be + tp2 + tp1_open; TP2 must not be added twice.",
        "unit": "One signal ID, not an independently executed exchange order. Correlated/repeated setups are not deduplicated beyond signal ID.",
        "limitations": [
            "Historical performance and current liquidity are different observation windows. No retrospective liquidity filter is applied.",
            "Order-book measurements are three short-interval snapshots, not a 24-hour stability study.",
            "Visible depth may be a lower bound if 1000 returned levels do not reach the requested band.",
            "Simulated book impact includes spread but excludes fees, funding, quantity-step rounding, latency and future price moves.",
            "Daily turnover estimate is base volume times closing price, not exact traded quote volume.",
            "Small samples and changing market regimes do not establish a profitable strategy.",
        ],
        "public_api_docs": "https://bingx-api.github.io/docs-v3/",
    })
    if args.collect:
        collect(registry, args.out)
    liq = liquidity(registry, args.out)
    write_json(args.out / "liquidity.json", liq)
    print(json.dumps({"entries": len(entries), "symbols": len(liq), "complete_liquidity_rows": sum(r["data_status"] == "complete" for r in liq), "flags": dict(Counter(f for r in liq for f in r["flags"]))}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
