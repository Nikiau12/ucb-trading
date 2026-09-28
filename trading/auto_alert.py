"""Localized automatic plan alerts. Same setup text as /plan and the panel."""

from __future__ import annotations


def render_auto_alert(
    plan: dict,
    symbol: str,
    side: str,
    conf: float,
    deposit: float,
    risk_pct: float,
    leverage: float,
    *,
    lang: str = "en",
    uses_reference_deposit: bool = False,
) -> str:
    try:
        from .setup_text import render_setup
    except ImportError:
        from setup_text import render_setup

    return render_setup(
        plan,
        symbol,
        side,
        conf,
        deposit,
        risk_pct,
        leverage,
        lang=lang,
        uses_reference_deposit=uses_reference_deposit,
    )
