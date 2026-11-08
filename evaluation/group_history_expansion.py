"""Bounded, public-only BingX 4H history expansion for development research.

The November 7 liquidity audit is a *current* snapshot, not historical proof.
This module does not inspect outcomes, run strategies, use credentials, or touch
the frozen forward experiment. Network collection requires explicit --collect.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path

from evaluation.sector_data import CandleCapture, FOUR_HOURS, digest, write_json
from trading.group_catalog import registry


VERSION = "group-history-expansion-v1-2026-11-08"
DATA_START = 1_772_323_200     # 2026-03-01 00:00 UTC; 1D indicator warm-up
DATA_END = 1_794_054_960       # same request cutoff as the original 27 captures
SCAN_START = 1_782_864_000     # 2026-07-01 00:00 UTC
SCAN_END = 1_794_052_800       # 2026-11-07 20:00 UTC


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unique_by(rows, field):
    result = {}
    for row in rows:
        key = row[field]
        if key in result:
            raise ValueError("Duplicate " + field + ": " + str(key))
        result[key] = row
    return result


def round_robin_by_group(rows):
    """Cover groups before taking second instruments, never rank by PnL."""
    buckets = defaultdict(list)
    for row in rows:
        buckets[row["group"]].append(row)
    for group in buckets:
        buckets[group].sort(key=lambda row: (-row["quote_volume_24h_usdt"], row["symbol"]))
    return [row for index in range(max(map(len, buckets.values()), default=0))
            for group in sorted(buckets) if index < len(buckets[group])
            for row in (buckets[group][index],)]


def select_inputs(liquidity_path: Path, shortlist_path: Path, contracts_path: Path) -> dict:
    liquidity = json.loads(liquidity_path.read_text())
    shortlist = json.loads(shortlist_path.read_text())
    contracts = json.loads(contracts_path.read_text())
    catalog = registry()
    mapping = catalog["mapping"]
    audit = unique_by(liquidity, "symbol")
    chosen = unique_by(shortlist["selected"], "symbol")
    contract_rows = unique_by(
        ({**row, "normalized_symbol": row["symbol"].replace("-", "_")}
         for row in contracts["response"]["data"]), "normalized_symbol")
    if (contracts["response"].get("code") != 0
            or any(symbol not in mapping or row["group"] != mapping[symbol]
                   for symbol, row in audit.items())
            or any(symbol not in mapping or row["group"] != mapping[symbol]
                   for symbol, row in chosen.items())):
        raise ValueError("Catalog or snapshot identity mismatch")
    eligible, excluded = [], []
    for symbol, group in sorted(mapping.items()):
        row = audit.get(symbol)
        reason = None
        if symbol in chosen:
            reason = "already_in_original_27"
        elif row is None:
            reason = "no_comparable_liquidity_audit"
        elif row.get("active_contract") is not True or row.get("data_status") != "complete":
            reason = "inactive_or_incomplete_current_audit"
        elif row.get("flags") or row.get("books_valid") != 3:
            reason = "current_liquidity_or_depth_flag"
        elif (not isinstance(row.get("contract_launch_time_ms"), int)
              or row["contract_launch_time_ms"] > DATA_START * 1000):
            reason = "contract_launched_after_history_start"
        elif (symbol not in contract_rows
              or contract_rows[symbol].get("status") != 1
              or contract_rows[symbol].get("launchTime") != row["contract_launch_time_ms"]):
            reason = "contract_snapshot_disagrees"
        elif (not isinstance(row.get("quote_volume_24h_usdt"), (int, float))
              or row["quote_volume_24h_usdt"] <= 0):
            reason = "invalid_current_volume"
        if reason:
            excluded.append({"symbol": symbol, "group": group, "reason": reason})
        else:
            eligible.append({"symbol": symbol, "group": group,
                             "quote_volume_24h_usdt": row["quote_volume_24h_usdt"],
                             "contract_launch_time_ms": row["contract_launch_time_ms"]})
    ordered = round_robin_by_group(eligible)
    return {
        "version": VERSION,
        "mode": "offline_development_data_only",
        "live_eligible": False,
        "independent_validation": False,
        "historical_universe_point_in_time_verified": False,
        "historical_liquidity_verified": False,
        "rules": "active and unflagged current audit, 3 books, complete 30d audit, launched by data start; group round-robin by current 24h volume",
        "window": {"data_start": DATA_START, "data_end": DATA_END,
                   "scan_start": SCAN_START, "scan_end": SCAN_END},
        "provenance": {"liquidity_sha256": file_sha256(liquidity_path),
                       "shortlist_sha256": file_sha256(shortlist_path),
                       "contracts_sha256": file_sha256(contracts_path),
                       "catalog_sha256": catalog["sha256"]},
        "catalog_count": len(mapping), "already_captured_count": len(chosen),
        "additional_count": len(ordered), "selected": ordered, "excluded": excluded,
    }


def collect(manifest: dict, root: Path, limit: int) -> dict:
    """Collect a predeclared prefix; cache validation and failures are fail-closed."""
    if not 1 <= limit <= len(manifest["selected"]):
        raise ValueError("Limit must be within the predeclared additional set")
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = root / "selection-manifest.json"
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text())
        if digest(existing) != digest(manifest):
            raise ValueError("Selection manifest changed; new root required")
    else:
        write_json(manifest_path, manifest)
    status_path = root / "capture-status.json"
    status = {"version": VERSION, "manifest_sha256": digest(manifest),
              "requested_prefix": limit, "complete": [], "error": None}
    capture = CandleCapture(root / "candles", collect=True)
    for item in manifest["selected"][:limit]:
        symbol = item["symbol"]
        try:
            bars, sha = capture.load(symbol, DATA_START, DATA_END)
            if (not bars or bars[0].ts != DATA_START
                    or bars[-1].ts + FOUR_HOURS != DATA_END // FOUR_HOURS * FOUR_HOURS
                    or any(b.ts - a.ts != FOUR_HOURS for a, b in zip(bars, bars[1:]))):
                raise ValueError("Incomplete 4H grid")
            cache_path = root / "candles" / f"{symbol}-4h-{DATA_START}-{DATA_END}.json"
            saved = json.loads(cache_path.read_text())
            if saved.get("capture_version") != 2 or saved["sha256"] != sha:
                raise ValueError("Missing verified BingX pagination proof")
            status["complete"].append({"symbol": symbol, "group": item["group"],
                                       "bars": len(bars), "sha256": sha,
                                       "pages": len(saved["pages"])})
        except (ValueError, KeyError, OSError) as exc:
            status["error"] = {"symbol": symbol, "message": str(exc)}
            write_json(status_path, status)
            raise
        write_json(status_path, status)
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--liquidity", type=Path, required=True)
    parser.add_argument("--shortlist", type=Path, required=True)
    parser.add_argument("--contracts", type=Path, required=True)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--collect", action="store_true")
    args = parser.parse_args()
    manifest = select_inputs(args.liquidity, args.shortlist, args.contracts)
    if args.collect:
        if args.root is None:
            parser.error("--root is required with --collect")
        status = collect(manifest, args.root, args.limit or len(manifest["selected"]))
        print(json.dumps({"additional_count": manifest["additional_count"], **status},
                         ensure_ascii=False, indent=2))
    else:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
