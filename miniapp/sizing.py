from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_FLOOR
from typing import Any, Dict, List, Optional


def _positive_decimal(value: Any) -> Optional[Decimal]:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return parsed if parsed.is_finite() and parsed > 0 else None


def position_size_for_contract(
    rules: Dict[str, Any],
    entry: float,
    stop: float,
    deposit: float,
    risk_pct: float,
    leverage: float,
) -> Dict[str, Any]:
    """Calculate a user-specific position using executable MEXC contract volume."""
    risk_budget = max(0.0, float(deposit)) * (max(0.0, float(risk_pct)) / 100.0)
    dist = abs(float(entry) - float(stop))
    requested_leverage = max(1.0, float(leverage))
    max_leverage = _positive_decimal(rules.get("max_leverage", rules.get("maxLeverage")))
    effective_leverage = min(
        requested_leverage,
        float(max_leverage) if max_leverage is not None else requested_leverage,
    )
    contract_size = _positive_decimal(rules.get("contract_size", rules.get("contractSize")))
    vol_unit = _positive_decimal(rules.get("vol_unit", rules.get("volUnit")))
    min_vol = _positive_decimal(rules.get("min_vol", rules.get("minVol")))
    max_vol = _positive_decimal(rules.get("max_vol", rules.get("maxVol")))
    errors: List[str] = []

    if dist <= 0:
        errors.append("invalid_stop_distance")
        qty = contract_vol = actual_risk = 0.0
    elif contract_size is None or vol_unit is None:
        qty = risk_budget / dist
        contract_vol = None
        actual_risk = risk_budget
    else:
        desired_qty = Decimal(str(risk_budget / dist))
        desired_vol = desired_qty / contract_size
        contract_vol_dec = (desired_vol / vol_unit).to_integral_value(rounding=ROUND_FLOOR) * vol_unit
        if max_vol is not None:
            contract_vol_dec = min(contract_vol_dec, max_vol)
        if min_vol is not None and contract_vol_dec < min_vol:
            errors.append("position_below_min_contract")
            contract_vol_dec = Decimal("0")
        qty = float(contract_vol_dec * contract_size)
        contract_vol = float(contract_vol_dec)
        actual_risk = qty * dist

    position_usdt = qty * float(entry)
    return {
        "risk_budget_usdt": risk_budget,
        "risk_usdt": actual_risk,
        "qty": qty,
        "contract_vol": contract_vol,
        "contract_size": float(contract_size) if contract_size is not None else None,
        "position_usdt": position_usdt,
        "margin_usdt": position_usdt / effective_leverage,
        "requested_leverage": requested_leverage,
        "effective_leverage": effective_leverage,
        "max_leverage": float(max_leverage) if max_leverage is not None else None,
        "dist": dist,
        "errors": errors,
    }
