#!/usr/bin/env python3
"""Walk-forward backtest for the production UCB trade-plan strategy.

The engine deliberately uses only candles that were closed at the decision
timestamp. Orders become eligible on the next candle and ambiguous candles are
resolved against the strategy (stop before take-profit).
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from .analytics.structure import Bar
from .trade_plan import make_plan, plan_payload_errors


PlanBuilder = Callable[..., Dict[str, Any]]
PlanFilter = Callable[[Dict[str, Any]], bool]
HOUR_SECONDS = 60 * 60


@dataclass(frozen=True)
class BacktestConfig:
    initial_deposit: float = 1_000.0
    risk_pct: float = 1.0
    leverage: float = 10.0
    margin: str = "cross"
    min_confidence: float = 0.60
    fee_bps: float = 4.0
    slippage_bps: float = 2.0
    entry_expiry_bars: int = 12
    max_holding_bars: int = 24 * 14
    warmup_hours: int = 24 * 60
    decision_interval_hours: int = 1

    def validate(self) -> None:
        if self.initial_deposit <= 0 or not 0 < self.risk_pct <= 100:
            raise ValueError("Deposit and risk_pct must be positive")
        if self.leverage < 1 or self.fee_bps < 0 or self.slippage_bps < 0:
            raise ValueError("Leverage, fees and slippage must be non-negative")
        if min(self.entry_expiry_bars, self.max_holding_bars, self.warmup_hours) < 1:
            raise ValueError("Backtest window values must be positive")
        if self.decision_interval_hours < 1:
            raise ValueError("decision_interval_hours must be positive")


@dataclass(frozen=True)
class TradeResult:
    signal_time: int
    entry_time: int
    exit_time: int
    side: str
    confidence: float
    planned_entry: float
    entry_price: float
    stop: float
    tp1: float
    tp2: float
    qty: float
    exit_reason: str
    gross_pnl: float
    fees: float
    net_pnl: float
    risk_usdt: float
    r_multiple: float
    holding_bars: int
    signal_context: Dict[str, Any] = field(default_factory=dict)


def _row(bar: Bar) -> List[float]:
    return [bar.ts, bar.o, bar.h, bar.l, bar.c, bar.v]


def validate_bars(bars: Sequence[Bar]) -> List[Bar]:
    ordered = sorted(bars, key=lambda bar: bar.ts)
    if len(ordered) != len({bar.ts for bar in ordered}):
        raise ValueError("Duplicate candle timestamps")
    for bar in ordered:
        values = (bar.o, bar.h, bar.l, bar.c)
        if not all(math.isfinite(value) and value > 0 for value in values):
            raise ValueError(f"Invalid OHLC values at {bar.ts}")
        if bar.l > min(bar.o, bar.c) or bar.h < max(bar.o, bar.c) or bar.l > bar.h:
            raise ValueError(f"Inconsistent OHLC range at {bar.ts}")
    return ordered


def resample_completed(bars: Sequence[Bar], period_seconds: int, decision_time: int) -> List[Bar]:
    """Aggregate only full higher-timeframe candles closed by decision_time."""
    buckets: Dict[int, List[Bar]] = {}
    for bar in bars:
        bucket_start = (bar.ts // period_seconds) * period_seconds
        if bucket_start + period_seconds > decision_time:
            continue
        buckets.setdefault(bucket_start, []).append(bar)

    result: List[Bar] = []
    expected = period_seconds // HOUR_SECONDS
    for bucket_start in sorted(buckets):
        group = buckets[bucket_start]
        if len(group) != expected:
            continue
        result.append(Bar(
            ts=bucket_start,
            o=group[0].o,
            h=max(bar.h for bar in group),
            l=min(bar.l for bar in group),
            c=group[-1].c,
            v=sum(bar.v for bar in group),
        ))
    return result


def build_snapshot(
    symbol: str,
    history: Sequence[Bar],
    decision_time: int,
    contract_rules: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    closed_1h = [bar for bar in history if bar.ts + HOUR_SECONDS <= decision_time]
    if not closed_1h:
        raise ValueError("No closed candles at decision time")
    snapshot = {
        "symbol": symbol,
        "ticker": {"data": {"lastPrice": closed_1h[-1].c}},
        "kline_1h": {"data": [_row(bar) for bar in closed_1h]},
        "kline_4h": {"data": [_row(bar) for bar in resample_completed(closed_1h, 4 * HOUR_SECONDS, decision_time)]},
        "kline_1d": {"data": [_row(bar) for bar in resample_completed(closed_1h, 24 * HOUR_SECONDS, decision_time)]},
        "stale": False,
    }
    if contract_rules is not None:
        snapshot["contract"] = dict(contract_rules)
    return snapshot


def _build_snapshot_from_precomputed(
    symbol: str,
    bars_1h: Sequence[Bar],
    bars_4h: Sequence[Bar],
    bars_1d: Sequence[Bar],
    signal_index: int,
    decision_time: int,
    contract_rules: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    def completed_end_index(source: Sequence[Bar], period: int) -> int:
        # Equivalent to bisect_right(..., key=...), without allocating a list
        # on every decision and while remaining compatible with Python 3.9.
        low, high = 0, len(source)
        while low < high:
            middle = (low + high) // 2
            if source[middle].ts + period <= decision_time:
                low = middle + 1
            else:
                high = middle
        return low

    end_4h = completed_end_index(bars_4h, 4 * HOUR_SECONDS)
    end_1d = completed_end_index(bars_1d, 24 * HOUR_SECONDS)
    closed_1h = bars_1h[max(0, signal_index - 499): signal_index + 1]
    closed_4h = bars_4h[max(0, end_4h - 500):end_4h]
    closed_1d = bars_1d[max(0, end_1d - 400):end_1d]
    snapshot = {
        "symbol": symbol,
        "ticker": {"data": {"lastPrice": closed_1h[-1].c}},
        "kline_1h": {"data": [_row(bar) for bar in closed_1h]},
        "kline_4h": {"data": [_row(bar) for bar in closed_4h]},
        "kline_1d": {"data": [_row(bar) for bar in closed_1d]},
        "stale": False,
    }
    if contract_rules is not None:
        snapshot["contract"] = dict(contract_rules)
    return snapshot


def _slipped(price: float, side: str, action: str, bps: float) -> float:
    rate = bps / 10_000.0
    is_buy = (side == "long" and action == "entry") or (side == "short" and action == "exit")
    return price * (1 + rate if is_buy else 1 - rate)


def _pnl(side: str, entry: float, exit_price: float, qty: float) -> float:
    direction = 1.0 if side == "long" else -1.0
    return direction * (exit_price - entry) * qty


def _fee(price: float, qty: float, fee_bps: float) -> float:
    return abs(price * qty) * fee_bps / 10_000.0


def _simulate_order(
    bars: Sequence[Bar],
    signal_index: int,
    primary: Dict[str, Any],
    confidence: float,
    config: BacktestConfig,
    signal_context: Optional[Dict[str, Any]] = None,
) -> tuple[Optional[TradeResult], int]:
    side = str(primary["side"]).lower()
    planned_entry = float(primary["entry"])
    stop = float(primary["stop"])
    tp1 = float(primary["tps"][0]["price"])
    tp2 = float(primary["tps"][1]["price"])
    qty = float(primary.get("qty") or 0)
    risk_usdt = float(primary.get("risk_usdt") or (abs(planned_entry - stop) * qty))
    if qty <= 0 or risk_usdt <= 0:
        return None, signal_index + 1

    last_entry_index = min(len(bars) - 1, signal_index + config.entry_expiry_bars)
    entry_index = None
    for index in range(signal_index + 1, last_entry_index + 1):
        candle = bars[index]
        if candle.l <= planned_entry <= candle.h:
            entry_index = index
            break
    if entry_index is None:
        return None, last_entry_index + 1

    entry_price = _slipped(planned_entry, side, "entry", config.slippage_bps)
    entry_fee = _fee(entry_price, qty, config.fee_bps)
    remaining = qty
    gross = 0.0
    exit_fees = 0.0
    tp1_filled = False
    exit_reason = "timeout"
    exit_index = min(len(bars) - 1, entry_index + config.max_holding_bars)

    for index in range(entry_index, exit_index + 1):
        candle = bars[index]
        stop_hit = candle.l <= stop if side == "long" else candle.h >= stop
        tp1_hit = candle.h >= tp1 if side == "long" else candle.l <= tp1
        tp2_hit = candle.h >= tp2 if side == "long" else candle.l <= tp2

        # Intrabar order is unknowable from OHLC. Stop-first is deliberately
        # pessimistic and prevents inflated backtest results.
        if stop_hit:
            exit_price = _slipped(stop, side, "exit", config.slippage_bps)
            gross += _pnl(side, entry_price, exit_price, remaining)
            exit_fees += _fee(exit_price, remaining, config.fee_bps)
            remaining = 0.0
            exit_reason = "stop_after_tp1" if tp1_filled else "stop"
            exit_index = index
            break

        # The entry and target order inside the fill candle is unknowable from
        # OHLC. Do not award a same-candle take-profit without tick data.
        if index == entry_index:
            continue

        if not tp1_filled and tp1_hit:
            closed_qty = qty * float(primary["tps"][0].get("pct", 0.5))
            closed_qty = min(closed_qty, remaining)
            exit_price = _slipped(tp1, side, "exit", config.slippage_bps)
            gross += _pnl(side, entry_price, exit_price, closed_qty)
            exit_fees += _fee(exit_price, closed_qty, config.fee_bps)
            remaining -= closed_qty
            tp1_filled = True

        if tp2_hit and remaining > 0:
            exit_price = _slipped(tp2, side, "exit", config.slippage_bps)
            gross += _pnl(side, entry_price, exit_price, remaining)
            exit_fees += _fee(exit_price, remaining, config.fee_bps)
            remaining = 0.0
            exit_reason = "tp2"
            exit_index = index
            break

    if remaining > 0:
        exit_price = _slipped(bars[exit_index].c, side, "exit", config.slippage_bps)
        gross += _pnl(side, entry_price, exit_price, remaining)
        exit_fees += _fee(exit_price, remaining, config.fee_bps)

    fees = entry_fee + exit_fees
    net = gross - fees
    result = TradeResult(
        signal_time=bars[signal_index].ts + HOUR_SECONDS,
        entry_time=bars[entry_index].ts,
        exit_time=bars[exit_index].ts + HOUR_SECONDS,
        side=side,
        confidence=confidence,
        planned_entry=planned_entry,
        entry_price=entry_price,
        stop=stop,
        tp1=tp1,
        tp2=tp2,
        qty=qty,
        exit_reason=exit_reason,
        gross_pnl=gross,
        fees=fees,
        net_pnl=net,
        risk_usdt=risk_usdt,
        r_multiple=net / risk_usdt,
        holding_bars=exit_index - entry_index + 1,
        signal_context=dict(signal_context or {}),
    )
    return result, exit_index + 1


def summarize(trades: Sequence[TradeResult], config: BacktestConfig) -> Dict[str, Any]:
    equity = config.initial_deposit
    peak = equity
    max_drawdown = 0.0
    gross_profit = 0.0
    gross_loss = 0.0
    for trade in trades:
        equity += trade.net_pnl
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, (peak - equity) / peak if peak else 0.0)
        if trade.net_pnl > 0:
            gross_profit += trade.net_pnl
        elif trade.net_pnl < 0:
            gross_loss += abs(trade.net_pnl)
    wins = sum(trade.net_pnl > 0 for trade in trades)
    return {
        "trades": len(trades),
        "wins": wins,
        "losses": len(trades) - wins,
        "win_rate_pct": 100 * wins / len(trades) if trades else 0.0,
        "initial_deposit": config.initial_deposit,
        "final_equity": equity,
        "net_pnl": equity - config.initial_deposit,
        "return_pct": 100 * (equity / config.initial_deposit - 1),
        "max_drawdown_pct": 100 * max_drawdown,
        "profit_factor": gross_profit / gross_loss if gross_loss else None,
        "average_r": sum(trade.r_multiple for trade in trades) / len(trades) if trades else 0.0,
        "fees_paid": sum(trade.fees for trade in trades),
    }


def run_backtest(
    bars: Sequence[Bar],
    *,
    symbol: str = "BTC_USDT",
    config: Optional[BacktestConfig] = None,
    contract_rules: Optional[Dict[str, Any]] = None,
    plan_builder: PlanBuilder = make_plan,
    plan_filter: Optional[PlanFilter] = None,
    evaluation_start: Optional[int] = None,
    evaluation_end: Optional[int] = None,
) -> Dict[str, Any]:
    config = config or BacktestConfig()
    config.validate()
    ordered = validate_bars(bars)
    if evaluation_start is not None and evaluation_end is not None and evaluation_start >= evaluation_end:
        raise ValueError("evaluation_start must be before evaluation_end")
    if evaluation_end is not None:
        # Keep the earlier candles as indicator warm-up, but never allow an
        # order or exit to observe a candle closing after the evaluation window.
        ordered = [bar for bar in ordered if bar.ts + HOUR_SECONDS <= evaluation_end]
    final_decision_time = ordered[-1].ts + HOUR_SECONDS if ordered else 0
    all_4h = resample_completed(ordered, 4 * HOUR_SECONDS, final_decision_time)
    all_1d = resample_completed(ordered, 24 * HOUR_SECONDS, final_decision_time)
    trades: List[TradeResult] = []
    skipped_plans = 0
    unfilled_orders = 0
    index = max(0, config.warmup_hours - 1)
    if evaluation_start is not None:
        while index < len(ordered) and ordered[index].ts + HOUR_SECONDS < evaluation_start:
            index += 1

    while index < len(ordered) - 1:
        decision_time = ordered[index].ts + HOUR_SECONDS
        snapshot = _build_snapshot_from_precomputed(
            symbol, ordered, all_4h, all_1d, index, decision_time, contract_rules
        )
        equity = config.initial_deposit + sum(trade.net_pnl for trade in trades)
        plan = plan_builder(
            snapshot,
            deposit=max(equity, 0.01),
            risk_pct=config.risk_pct,
            lev=config.leverage,
            margin=config.margin,
        )
        primary = plan.get("primary") or {}
        confidence = float(primary.get("confidence") or plan.get("confidence") or 0)
        if (
            plan.get("side") == "skip"
            or plan_payload_errors(plan)
            or confidence < config.min_confidence
            or (plan_filter is not None and not plan_filter(plan))
        ):
            skipped_plans += 1
            index += config.decision_interval_hours
            continue

        signal_context = {
            "trend": dict(plan.get("trend") or {}),
            "levels": dict(plan.get("levels") or {}),
            "reasons": list(primary.get("reasons") or []),
        }
        trade, next_index = _simulate_order(
            ordered, index, primary, confidence, config, signal_context
        )
        if trade is None:
            unfilled_orders += 1
        else:
            trades.append(trade)
        index = max(index + 1, next_index)

    return {
        "methodology": {
            "signal_data": "closed candles only",
            "first_entry_bar": "next 1h candle after signal",
            "ambiguous_intrabar_policy": "stop_first",
            "overlapping_positions": False,
            "fees_bps_per_fill": config.fee_bps,
            "slippage_bps_per_fill": config.slippage_bps,
            "evaluation_start": evaluation_start,
            "evaluation_end": evaluation_end,
        },
        "config": asdict(config),
        "summary": summarize(trades, config),
        "skipped_plans": skipped_plans,
        "unfilled_orders": unfilled_orders,
        "trades": [asdict(trade) for trade in trades],
    }


def load_csv(path: Path) -> List[Bar]:
    bars: List[Bar] = []
    with path.open(newline="") as source:
        for row in csv.DictReader(source):
            raw_time = row.get("timestamp") or row.get("time") or row.get("date")
            if raw_time is None:
                raise ValueError("CSV requires timestamp/time/date column")
            try:
                timestamp = int(float(raw_time))
                if timestamp > 10_000_000_000:
                    timestamp //= 1_000
            except ValueError:
                timestamp = int(datetime.fromisoformat(raw_time.replace("Z", "+00:00")).timestamp())
            bars.append(Bar(
                ts=timestamp,
                o=float(row["open"]), h=float(row["high"]),
                l=float(row["low"]), c=float(row["close"]),
                v=float(row.get("volume") or row.get("vol") or 0),
            ))
    return validate_bars(bars)


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Walk-forward UCB strategy backtest")
    parser.add_argument("csv", type=Path, help="1h OHLCV CSV")
    parser.add_argument("--symbol", default="BTC_USDT")
    parser.add_argument("--deposit", type=float, default=1_000.0)
    parser.add_argument("--risk", type=float, default=1.0)
    parser.add_argument("--fee-bps", type=float, default=4.0)
    parser.add_argument("--slippage-bps", type=float, default=2.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    result = run_backtest(
        load_csv(args.csv), symbol=args.symbol,
        config=BacktestConfig(
            initial_deposit=args.deposit,
            risk_pct=args.risk,
            fee_bps=args.fee_bps,
            slippage_bps=args.slippage_bps,
        ),
    )
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(payload + "\n")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
