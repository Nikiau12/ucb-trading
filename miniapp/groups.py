"""Shared persistent signal preferences; strategy rules remain independent."""
import json
import re
from pathlib import Path

GROUPS = json.loads((Path(__file__).parent / "asset_groups.json").read_text())
BY_SYMBOL = {symbol: group for group, symbols in GROUPS.items() for symbol in symbols}
GROUP_IDS = frozenset([*GROUPS, "ungrouped"])
REMOVED_SOURCES = frozenset({"spike", "smc", "scalp"})

def classify(symbol):
    match = re.fullmatch(r"([A-Z0-9]+?)[_/-]?USDT(?::USDT)?", str(symbol).strip().upper())
    return BY_SYMBOL.get(match[1] + "_USDT", "ungrouped") if match else "ungrouped"

def validate_groups(groups):
    # NULL = all; [] = none. Existing profiles retain their previous subscription.
    if groups is None:
        return None
    if not isinstance(groups, list) or len(groups) > len(GROUP_IDS):
        raise ValueError("invalid_groups")
    if any(not isinstance(g, str) or g not in GROUP_IDS for g in groups):
        raise ValueError("invalid_groups")
    return list(dict.fromkeys(groups))

def matches(symbol, groups):
    return groups is None or classify(symbol) in groups

def load_groups(connection, user_id):
    row = connection.execute("SELECT signal_groups FROM user_profiles WHERE telegram_user_id = %s", (user_id,)).fetchone()
    return validate_groups(row[0]) if row else None
