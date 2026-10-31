"""Exact public USDT invoice prices."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


USDT_QUANTUM = Decimal("0.000001")


def quantize_usdt(amount) -> Decimal:
    return Decimal(str(amount)).quantize(USDT_QUANTUM, rounding=ROUND_HALF_UP)


def format_usdt(amount) -> str:
    value = format(quantize_usdt(amount), "f").rstrip("0").rstrip(".")
    if "." not in value:
        return value + ".00"
    whole, decimals = value.split(".", 1)
    return whole + "." + decimals.ljust(2, "0")
