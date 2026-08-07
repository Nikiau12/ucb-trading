#!/usr/bin/env python3
"""Stateful SOL paper trading for a frozen 1D-context + 4H setup.

The script never sends an order. Repeated invocations process newly closed 4H
candles and atomically persist a virtual pending order, position and trade log.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from trading.analytics.structure import Bar
from trading.backtest import HOUR_SECONDS, build_snapshot, resample_completed
from trading.higher_timeframe_setups import SOL_4H_1D_SETUPS, htf_plan_builder
from trading.trade_plan import plan_payload_errors

from .run_walk_forward import fetch_bars, fetch_contract


SYMBOL = "SOL_USDT"
FOUR_HOURS = 4 * HOUR_SECONDS
# Frozen after native-4H selection. It failed independent confirmation, so the
# scheduler remains paused; the harness is ready only for an explicitly
# approved forward-observation run.
PROFILE = SOL_4H_1D_SETUPS[2]
PLAN_BUILDER = htf_plan_builder(PROFILE)
FEE_BPS = 4.0
SLIPPAGE_BPS = 2.0
ENTRY_EXPIRY_BARS = 2
MAX_HOLDING_BARS = 42


def new_state(now_close: int) -> Dict[str, Any]:
    return {
        "version": 2,
        "symbol": SYMBOL,
        "profile": PROFILE.name,
        "started_at": now_close,
        "last_candle_close": now_close,
        "equity": 1_000.0,
        "pending": None,
        "position": None,
        "trades": [],
        "signals_rejected": 0,
        "signal_timeframes": ["4h", "1d"],
    }


def _slipped(price: float, side: str, action: str) -> float:
    rate = SLIPPAGE_BPS / 10_000.0
    is_buy = (side == "long" and action == "entry") or (
        side == "short" and action == "exit"
    )
    return price * (1 + rate if is_buy else 1 - rate)


def _fee(price: float, qty: float) -> float:
    return abs(price * qty) * FEE_BPS / 10_000.0


def _pnl(side: str, entry: float, exit_price: float, qty: float) -> float:
    direction = 1.0 if side == "long" else -1.0
    return direction * (exit_price - entry) * qty


def _close_position(
    state: Dict[str, Any],
    candle: Bar,
    exit_price: float,
    reason: str,
) -> None:
    position = state["position"]
    remaining = float(position["remaining_qty"])
    gross = float(position["gross_pnl"]) + _pnl(
        position["side"], float(position["entry_price"]), exit_price, remaining
    )
    fees = float(position["fees"]) + _fee(exit_price, remaining)
    net = gross - fees
    state["equity"] = float(state["equity"]) + net
    state["trades"].append({
        "signal_time": position["signal_time"],
        "entry_time": position["entry_time"],
        "exit_time": candle.ts + FOUR_HOURS,
        "side": position["side"],
        "entry_price": position["entry_price"],
        "exit_price": exit_price,
        "exit_reason": reason,
        "gross_pnl": gross,
        "fees": fees,
        "net_pnl": net,
        "equity_after": state["equity"],
    })
    state["position"] = None


def advance_candle(state: Dict[str, Any], candle: Bar) -> None:
    pending = state.get("pending")
    if pending is not None:
        if candle.ts >= int(pending["expires_at"]):
            state["pending"] = None
        elif candle.ts >= int(pending["signal_time"]):
            entry = float(pending["entry"])
            if candle.l <= entry <= candle.h:
                side = pending["side"]
                qty = float(pending["qty"])
                entry_price = _slipped(entry, side, "entry")
                state["position"] = {
                    **pending,
                    "entry_time": candle.ts,
                    "entry_price": entry_price,
                    "remaining_qty": qty,
                    "tp1_filled": False,
                    "gross_pnl": 0.0,
                    "fees": _fee(entry_price, qty),
                    "holding_bars": 0,
                }
                state["pending"] = None

    position = state.get("position")
    if position is None:
        return
    position["holding_bars"] = int(position["holding_bars"]) + 1
    side = position["side"]
    stop = float(position["stop"])
    stop_hit = candle.l <= stop if side == "long" else candle.h >= stop
    if stop_hit:
        _close_position(
            state,
            candle,
            _slipped(stop, side, "exit"),
            "stop_after_tp1" if position["tp1_filled"] else "stop",
        )
        return

    # Match the conservative backtest: no target credit on the fill candle.
    if candle.ts == int(position["entry_time"]):
        return
    tp1 = float(position["tp1"])
    tp2 = float(position["tp2"])
    tp1_hit = candle.h >= tp1 if side == "long" else candle.l <= tp1
    tp2_hit = candle.h >= tp2 if side == "long" else candle.l <= tp2
    if not position["tp1_filled"] and tp1_hit:
        close_qty = min(float(position["qty"]) * 0.5, float(position["remaining_qty"]))
        exit_price = _slipped(tp1, side, "exit")
        position["gross_pnl"] += _pnl(side, float(position["entry_price"]), exit_price, close_qty)
        position["fees"] += _fee(exit_price, close_qty)
        position["remaining_qty"] -= close_qty
        position["tp1_filled"] = True
    if tp2_hit and float(position["remaining_qty"]) > 0:
        _close_position(state, candle, _slipped(tp2, side, "exit"), "tp2")
        return
    if int(position["holding_bars"]) >= MAX_HOLDING_BARS:
        _close_position(
            state, candle, _slipped(candle.c, side, "exit"), "timeout"
        )


def maybe_create_signal(
    state: Dict[str, Any],
    bars: list[Bar],
    decision_time: int,
    contract: Dict[str, Any],
) -> None:
    if state.get("pending") is not None or state.get("position") is not None:
        return
    snapshot = build_snapshot(
        SYMBOL,
        bars,
        decision_time,
        contract,
        source_interval_hours=4,
    )
    plan = PLAN_BUILDER(
        snapshot,
        deposit=max(float(state["equity"]), 0.01),
        risk_pct=1,
        lev=10,
        margin="cross",
    )
    primary = plan.get("primary") or {}
    confidence = float(primary.get("confidence") or plan.get("confidence") or 0)
    if (
        plan.get("side") == "skip"
        or confidence < 0.60
        or plan_payload_errors(plan)
    ):
        state["signals_rejected"] = int(state["signals_rejected"]) + 1
        return
    state["pending"] = {
        "signal_time": decision_time,
        "expires_at": decision_time + ENTRY_EXPIRY_BARS * FOUR_HOURS,
        "side": primary["side"],
        "confidence": confidence,
        "entry": primary["entry"],
        "stop": primary["stop"],
        "tp1": primary["tps"][0]["price"],
        "tp2": primary["tps"][1]["price"],
        "qty": primary["qty"],
        "risk_usdt": primary["risk_usdt"],
    }


def save_state(path: Path, state: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def migrate_empty_hourly_state(state: Dict[str, Any], now_close: int) -> Dict[str, Any]:
    if int(state.get("version") or 0) >= 2:
        return state
    if state.get("pending") or state.get("position") or state.get("trades"):
        raise RuntimeError("Cannot migrate an active hourly paper-trading state")
    return {
        **state,
        "version": 2,
        "profile": PROFILE.name,
        "last_candle_close": now_close,
        "signals_rejected": 0,
        "signal_timeframes": ["4h", "1d"],
        "migrated_from_hourly_at": now_close,
    }


def run_once(state_path: Path, now_close: Optional[int] = None) -> Dict[str, Any]:
    now_close = now_close or (int(time.time()) // FOUR_HOURS * FOUR_HOURS)
    cache_dir = Path("/tmp/ucb-sol-paper-data")
    source_bars = fetch_bars(SYMBOL, 4_000, cache_dir, end_close=now_close)
    bars = resample_completed(
        source_bars,
        FOUR_HOURS,
        now_close,
        HOUR_SECONDS,
    )
    contract = fetch_contract(SYMBOL, cache_dir)
    if state_path.exists():
        loaded = json.loads(state_path.read_text())
        state = migrate_empty_hourly_state(loaded, now_close)
        migrated = state is not loaded
        last_close = int(state["last_candle_close"])
        for candle in bars:
            candle_close = candle.ts + FOUR_HOURS
            if not last_close < candle_close <= now_close:
                continue
            advance_candle(state, candle)
            maybe_create_signal(state, bars, candle_close, contract)
            state["last_candle_close"] = candle_close
        if migrated:
            maybe_create_signal(state, bars, now_close, contract)
    else:
        state = new_state(now_close)
        maybe_create_signal(state, bars, now_close, contract)
    save_state(state_path, state)
    return state


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Frozen SOL paper trader (no real orders)")
    parser.add_argument(
        "--state",
        type=Path,
        default=Path("/tmp/ucb-sol-paper/state.json"),
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    state = run_once(args.state)
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
