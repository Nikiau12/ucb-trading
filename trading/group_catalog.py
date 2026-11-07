"""Reviewed runtime membership, kept separate from the frozen research universe."""
from functools import lru_cache
import json
from pathlib import Path
import re

from evaluation.sector_entries import load_entries
from evaluation.sector_data import digest


@lru_cache(maxsize=1)
def registry():
    definitions, baseline = load_entries()
    review = json.loads(Path(__file__).with_name("asset_group_extensions.json").read_text())
    mapping = dict(baseline)
    for row in review["additions"]:
        symbol, group = row["symbol"], row["group"]
        if (not re.fullmatch(r"[A-Z0-9]+_USDT", symbol) or symbol in mapping
                or group not in definitions["groups"] or not row["source"].startswith("https://")
                or not row["basis"]):
            raise ValueError("Invalid or duplicate runtime group review")
        mapping[symbol] = group
    pending = review["pending"]
    if any(not re.fullmatch(r"[A-Z0-9]+_USDT", s) or s in mapping or not reason
           for s, reason in pending.items()):
        raise ValueError("Invalid pending group review")
    display = json.loads((Path(__file__).resolve().parents[1] / "miniapp/asset_groups.json").read_text())
    displayed = {s: g for g, symbols in display.items() for s in symbols}
    if (displayed != mapping or set(display) != set(definitions["groups"])
            or sum(map(len, display.values())) != len(mapping)):
        raise ValueError("Scanner and Mini App group catalogs differ")
    return {"version": review["version"], "sha256": digest(review),
            "mapping": mapping, "baseline": baseline, "pending": pending}


def coverage(symbols):
    """Classification coverage is not liquidity/strategy approval."""
    catalog = registry()
    symbols = list(dict.fromkeys(symbols))
    classified = [s for s in symbols if s in catalog["mapping"]]
    pending = {s: catalog["pending"][s] for s in symbols if s in catalog["pending"]}
    unknown = [s for s in symbols if s not in catalog["mapping"] and s not in pending]
    return {"catalog_version": catalog["version"], "requested": len(symbols),
            "classified": len(classified), "classified_symbols": classified,
            "pending_review": pending, "unknown_symbols": unknown}
