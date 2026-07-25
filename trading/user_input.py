from __future__ import annotations

from typing import Optional


def is_deposit_input(text: Optional[str]) -> bool:
    """Return True only for non-command text handled by deposit onboarding."""
    value = str(text or "").lstrip()
    return bool(value) and not value.startswith("/")


def parse_deposit_amount(text: Optional[str]) -> float:
    value = str(text or "").strip().replace(" ", "").replace(",", ".")
    deposit = float(value)
    if deposit <= 0 or deposit > 1_000_000_000:
        raise ValueError("deposit out of range")
    return deposit

