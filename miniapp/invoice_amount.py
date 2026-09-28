"""Unique per-user USDT invoice amounts.

The suffix is small (under 0.01 USDT) and unique among open invoices so a
public TRC20 transfer can be matched to one payer.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


USDT_QUANTUM = Decimal("0.000001")
SUFFIX_SLOTS = 9999


def quantize_usdt(amount) -> Decimal:
    return Decimal(str(amount)).quantize(USDT_QUANTUM, rounding=ROUND_HALF_UP)


def unique_invoice_amount(base_amount, user_id: int, taken: set[Decimal]) -> Decimal:
    """Return base price plus a unique 0.000001–0.009999 suffix."""
    base = quantize_usdt(base_amount)
    blocked = {quantize_usdt(amount) for amount in taken}
    start = (int(user_id) % SUFFIX_SLOTS) + 1
    for offset in range(SUFFIX_SLOTS):
        slot = ((start - 1 + offset) % SUFFIX_SLOTS) + 1
        amount = quantize_usdt(base + (Decimal(slot) * USDT_QUANTUM))
        if amount not in blocked and amount > base:
            return amount
    raise RuntimeError("no free invoice amount")


def format_usdt(amount) -> str:
    return format(quantize_usdt(amount), "f")
