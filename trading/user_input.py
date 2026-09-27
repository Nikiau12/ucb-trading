from __future__ import annotations

from typing import Optional


def is_deposit_input(text: Optional[str]) -> bool:
    """Return True only for non-command text handled by deposit onboarding."""
    value = str(text or "").lstrip()
    return bool(value) and not value.startswith("/")


RISK_MIN = 0.1
RISK_MAX = 5.0
LEVERAGE_MIN = 1.0
LEVERAGE_MAX = 100.0
MARGIN_MODES = {"cross", "isolated"}


def parse_setting(key: str, raw: str):
    """Validate one /set value using the same limits as the Mini App.

    Returns (storage_key, value). Raises ValueError when the value is rejected.
    """
    name = str(key or "").strip().lower()
    if name not in {"deposit", "risk", "lev", "margin"}:
        raise ValueError("unknown")
    if name == "margin":
        margin = str(raw or "").strip().lower()
        if margin not in MARGIN_MODES:
            raise ValueError("margin")
        return "margin", margin
    try:
        value = float(str(raw).strip().replace(",", "."))
    except (TypeError, ValueError) as exc:
        raise ValueError(name) from exc
    if name == "deposit":
        if value <= 0 or value > 1_000_000_000:
            raise ValueError("deposit")
        return "deposit", value
    if name == "risk":
        if value < RISK_MIN or value > RISK_MAX:
            raise ValueError("risk")
        return "risk_pct", value
    if value < LEVERAGE_MIN or value > LEVERAGE_MAX:
        raise ValueError("lev")
    return "lev", value


def parse_deposit_amount(text: Optional[str]) -> float:
    value = str(text or "").strip().replace(" ", "").replace(",", ".")
    deposit = float(value)
    if deposit <= 0 or deposit > 1_000_000_000:
        raise ValueError("deposit out of range")
    return deposit

