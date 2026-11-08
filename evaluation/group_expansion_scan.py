"""Offline technical-only frequency screen on 27+25 captured 4H histories.

The additional instruments have no researched economic/identity passports and
their current tick, liquidity and catalog cannot be backfilled into 2026. Their
candidates are an optimistic exploratory screen, not a mathematical upper bound,
and never live or historical validation.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

from evaluation import sector_entries as research
from evaluation.group_frequency_lab import load_development_inputs, summarize_frequency
from evaluation.group_history_expansion import DATA_START, DATA_END, SCAN_START, SCAN_END, file_sha256
from evaluation.sector_data import CandleCapture, FOUR_HOURS, digest, write_json
from trading.group_catalog import registry


VERSION = "group-expansion-technical-screen-v1-2026-11-08"


def contract_ticks(path: Path, symbols: list[str]) -> dict[str, float]:
    raw = json.loads(path.read_text())
    if raw.get("response", {}).get("code") != 0:
        raise ValueError("Contracts snapshot unavailable")
    rows = {}
    for row in raw["response"]["data"]:
        symbol = row["symbol"].replace("-", "_")
        if symbol in rows:
            raise ValueError("Duplicate contract symbol")
        rows[symbol] = row
    ticks = {}
    for symbol in symbols:
        row = rows[symbol]
        precision = row.get("pricePrecision")
        if row.get("status") != 1 or type(precision) is not int or not 0 <= precision <= 18:
            raise ValueError("Invalid current contract tick: " + symbol)
        ticks[symbol] = 10.0 ** -precision
    return ticks


def scan(*, old_root: Path, old_shortlist: Path, new_root: Path, contracts_path: Path) -> dict:
    (preflight, old_shortlist_data, _decisions, old_plans, config, mapping, _passports,
     markets, ticks, old_hashes) = load_development_inputs(old_root, old_shortlist)
    manifest = json.loads((new_root / "selection-manifest.json").read_text())
    status = json.loads((new_root / "capture-status.json").read_text())
    catalog = registry()
    selected = manifest["selected"]
    new_symbols = [row["symbol"] for row in selected]
    if (manifest["mode"] != "offline_development_data_only"
            or manifest["live_eligible"] is not False
            or manifest["independent_validation"] is not False
            or manifest["window"] != {"data_start": DATA_START, "data_end": DATA_END,
                                      "scan_start": SCAN_START, "scan_end": SCAN_END}
            or preflight["data_start"] != DATA_START or preflight["data_end"] != DATA_END
            or preflight["scan_start"] != SCAN_START or preflight["scan_end"] != SCAN_END
            or manifest["provenance"]["catalog_sha256"] != catalog["sha256"]
            or manifest["provenance"]["contracts_sha256"] != file_sha256(contracts_path)
            or len(new_symbols) != len(set(new_symbols))
            or any(mapping.get(row["symbol"]) != row["group"] or row["symbol"] in markets
                   for row in selected)):
        raise ValueError("Expanded capture manifest or catalog changed")
    status_by_symbol = {row["symbol"]: row for row in status["complete"]}
    if (status["manifest_sha256"] != digest(manifest)
            or status["error"] is not None
            or len(status_by_symbol) != len(new_symbols)
            or set(status_by_symbol) != set(new_symbols)):
        raise ValueError("Expanded capture is incomplete")
    ticks.update(contract_ticks(contracts_path, new_symbols))
    capture = CandleCapture(new_root / "candles", collect=False)
    new_hashes = {}
    for symbol in new_symbols:
        bars, sha = capture.load(symbol, DATA_START, DATA_END)
        if (sha != status_by_symbol[symbol]["sha256"]
                or len(bars) != status_by_symbol[symbol]["bars"]
                or bars[0].ts != DATA_START
                or bars[-1].ts + FOUR_HOURS != SCAN_END
                or any(b.ts - a.ts != FOUR_HOURS for a, b in zip(bars, bars[1:]))):
            raise ValueError("Expanded 4H capture changed or has a gap: " + symbol)
        markets[symbol], new_hashes[symbol] = bars, sha
    new_plans, reasons = [], Counter()
    for as_of in range(SCAN_START, SCAN_END + 1, FOUR_HOURS):
        cache = {}
        for symbol in new_symbols:
            for side in ("long", "short"):
                result = research.candidate(symbol, side, markets, as_of=as_of,
                                            tick=ticks[symbol], passport=None,
                                            _feature_cache=cache)
                if result["status"] == "technical_candidate_not_admitted":
                    new_plans.append(result)
                elif result["status"] == "no_setup":
                    reasons[result.get("reason", "unknown")] += 1
                else:
                    raise ValueError("Blocked/unexpected expanded market data: " + symbol)
    expected = len(new_symbols) * 2 * ((SCAN_END - SCAN_START) // FOUR_HOURS + 1)
    if len(new_plans) + sum(reasons.values()) != expected:
        raise ValueError("Expanded technical decision grid incomplete")
    old_symbols = {row["symbol"] for row in old_shortlist_data["selected"]}
    if len(old_symbols) != 27 or old_symbols & set(new_symbols):
        raise ValueError("Original and expanded samples overlap")
    return {
        "version": VERSION, "mode": "offline_development_optimistic_technical_screen",
        "live_eligible": False, "independent_validation": False,
        "profitability_established": False, "economic_admitted": 0,
        "new_symbols_passports_verified": False,
        "new_symbols_additional_benchmarks_verified": False,
        "period": {"scan_start": SCAN_START, "scan_end": SCAN_END,
                   "original_symbols": len(old_symbols), "added_symbols": len(new_symbols)},
        "original_27": summarize_frequency(old_plans, SCAN_START, SCAN_END),
        "added_25_unreviewed": summarize_frequency(new_plans, SCAN_START, SCAN_END),
        "combined_52_unreviewed": summarize_frequency(old_plans + new_plans, SCAN_START, SCAN_END),
        "new_rejection_reasons": dict(sorted(reasons.items())),
        "source": {"old_4h_sha256": old_hashes, "new_4h_sha256": new_hashes,
                   "manifest_sha256": digest(manifest), "rules_sha256": digest(config),
                   "contracts_sha256": file_sha256(contracts_path),
                   "scan_implementation_sha256": file_sha256(Path(__file__))},
        "limitations": [
            "Additional symbols have no verified identity/mechanism passports or subtype benchmarks",
            "Historical universe, contract tick, fees and liquidity are not point-in-time verified",
            "No new-symbol funding, minute execution, historical order books or after-cost outcome",
            "Previously inspected development dates; not independent strategy validation",
            "Technical candidates are not delivered signals or filled trades",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-root", type=Path, required=True)
    parser.add_argument("--old-shortlist", type=Path, required=True)
    parser.add_argument("--new-root", type=Path, required=True)
    parser.add_argument("--contracts", type=Path, required=True)
    args = parser.parse_args()
    result = scan(old_root=args.old_root, old_shortlist=args.old_shortlist,
                  new_root=args.new_root, contracts_path=args.contracts)
    write_json(args.new_root / "technical-frequency-screen.json", result)
    print(json.dumps({"period": result["period"],
                      "original": result["original_27"]["technical_candidates"],
                      "added_unreviewed": result["added_25_unreviewed"]["technical_candidates"],
                      "combined_unreviewed": result["combined_52_unreviewed"]["technical_candidates"]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
