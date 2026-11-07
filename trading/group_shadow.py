"""Independent, model-only accounting for versioned group signals.

No account keys, user identifiers, notifications or order endpoints are used.
One signal counts once even if many Telegram users see it. Levels are assumed
filled with a fixed adverse-slippage scenario; this is NOT a user's PnL.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
import math
import os
import sys

from trading.group_catalog import registry
from trading.group_plan import VERSION as STRATEGY_VERSION


MODEL_VERSION = "group-shadow-v1-2026-11-07"
SLIPPAGE_BPS = 2.0
MIN_COMPLETE_SAMPLE = 20
MAX_FUNDING_GAP = timedelta(hours=24)
FUNDING_ENVELOPE = timedelta(hours=48)
EVENT_ORDER_WINDOW = timedelta(minutes=5)
TERMINAL = frozenset({"stopped_before_tp1", "tp1_then_be", "tp2",
                      "expired_after_entry", "expired_after_tp1"})


def _public():
    # The worker imports this module by its historical short name. Share its
    # rate limiter instead of constructing a second public BingX client.
    client = sys.modules.get("bingx_snapshot")
    if client is None:
        from trading import bingx_snapshot as client
    return client


def _number(value, *, zero=False):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) and (result >= 0 if zero else result > 0) else None


def _utc(value):
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def outcome(row):
    """Keep unentered, open, terminal and inconsistent signals separate."""
    status, entry = row["lifecycle_status"], _utc(row.get("entry_hit_at"))
    tp1 = _utc(row.get("tp1_hit_at"))
    if entry is None:
        return {"cancelled_before_entry": "cancelled_before_entry",
                "expired": "expired_before_entry", "waiting_entry": "awaiting_entry",
                "replay_pending": "awaiting_replay"}.get(status, "invalid_lifecycle")
    if status == "active" and tp1 is None:
        return "active"
    if status == "tp1_reached" and tp1 is not None:
        return "tp1_open"
    if status == "stopped" and _utc(row.get("stop_hit_at")) is not None:
        return "tp1_then_be" if tp1 else "stopped_before_tp1"
    if status == "tp2_reached" and tp1 and _utc(row.get("tp2_hit_at")):
        return "tp2"
    if status == "expired" and _utc(row.get("expired_at")):
        return "expired_after_tp1" if tp1 else "expired_after_entry"
    return "invalid_lifecycle"


def _fills(row, label, expiry_price):
    side = str(row.get("side") or "").lower()
    entry, stop, tp1, tp2 = (_number(row.get(k)) for k in ("entry", "stop", "tp1", "tp2"))
    if side not in {"long", "short"} or None in (entry, stop, tp1, tp2):
        return None
    sign = 1 if side == "long" else -1
    if not (sign * (entry - stop) > 0 and sign * (tp1 - entry) > 0
            and sign * (tp2 - tp1) > 0):
        return None
    if label == "stopped_before_tp1":
        fills = [(stop, 1.0)]
    elif label == "tp1_then_be":
        fills = [(tp1, .5), (entry, .5)]
    elif label == "tp2":
        fills = [(tp1, .5), (tp2, .5)]
    elif label == "expired_after_entry":
        fills = [(expiry_price, 1.0)] if _number(expiry_price) else None
    elif label == "expired_after_tp1":
        fills = [(tp1, .5), (expiry_price, .5)] if _number(expiry_price) else None
    else:
        fills = None
    return (entry, abs(entry - stop), sign, fills) if fills else None


def funding_history(symbol, entered_at, closed_at, *, now=None):
    """Read settled public rates with both adjacent events as coverage proof.

    A missing post-exit event delays accounting, rather than treating unknown
    funding as zero. A 24-hour gap or truncated page also fails closed.
    """
    start, end = _utc(entered_at), _utc(closed_at)
    now = _utc(now) or datetime.now(timezone.utc)
    if not start or not end or end < start:
        raise ValueError("invalid_funding_window")
    client = _public()
    begin = max(0, int((start - FUNDING_ENVELOPE).timestamp() * 1000))
    finish = int(min(now, end + FUNDING_ENVELOPE).timestamp() * 1000)
    payload = client.http_get("/openApi/swap/v2/quote/fundingRate", {
        "symbol": client.to_bingx_symbol(symbol), "startTime": begin,
        "endTime": finish, "limit": 1000,
    })
    raw = payload.get("data")
    if not isinstance(raw, list):
        raise ValueError("invalid_funding_response")
    rows = {}
    for item in raw:
        if not isinstance(item, dict) or item.get("symbol") != client.to_bingx_symbol(symbol):
            raise ValueError("invalid_funding_symbol")
        stamp = item.get("fundingTime")
        if isinstance(stamp, bool) or not isinstance(stamp, (int, str)):
            raise ValueError("invalid_funding_timestamp")
        stamp = int(stamp)
        mark = _number(item.get("markPrice"))
        # Negative funding is legitimate.
        try:
            rate = float(item["fundingRate"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("invalid_funding_rate") from None
        if not math.isfinite(rate) or abs(rate) > .1 or mark is None or not begin <= stamp <= finish:
            raise ValueError("invalid_funding_record")
        if stamp in rows and rows[stamp] != (rate, mark):
            raise ValueError("conflicting_funding_record")
        rows[stamp] = (rate, mark)
    records = [(datetime.fromtimestamp(ts / 1000, timezone.utc), *rows[ts]) for ts in sorted(rows)]
    gaps = [right[0] - left[0] for left, right in zip(records, records[1:])]
    # A skipped 8h settlement would otherwise look like a plausible 16h gap.
    # A changed funding interval is deliberately held for review as well.
    shortest = min(gaps) if gaps else None
    complete = bool(len(raw) < 1000 and any(ts < start for ts, _, _ in records)
                    and any(ts > end for ts, _, _ in records)
                    and shortest is not None
                    and all(gap <= MAX_FUNDING_GAP and gap <= shortest * 1.05
                            for gap in gaps))
    events = [(ts, rate, mark) for ts, rate, mark in records if start < ts < end]
    # Exact ties with entry, TP1 or exit cannot be ordered from lifecycle polls.
    if any(abs(ts - boundary) <= EVENT_ORDER_WINDOW
           for ts, _, _ in records for boundary in (start, end)):
        complete = False
    return events, complete


def expiry_close(symbol, expired_at, *, now=None):
    """Use the last fully closed 1m candle before the model timeout."""
    end = _utc(expired_at)
    now = _utc(now) or datetime.now(timezone.utc)
    if not end or end > now:
        return None
    client = _public()
    end_ms = int(end.timestamp() * 1000)
    payload = client.http_get("/openApi/swap/v3/quote/klines", {
        "symbol": client.to_bingx_symbol(symbol), "interval": "1m",
        "startTime": end_ms - 180_000, "endTime": end_ms, "limit": 5,
    })
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise ValueError("invalid_expiry_candles")
    found = []
    for item in rows:
        if isinstance(item, list) and len(item) >= 5:
            stamp, price = item[0], item[4]
        elif isinstance(item, dict):
            stamp, price = item.get("time"), item.get("close")
        else:
            continue
        try:
            stamp = int(stamp)
        except (TypeError, ValueError):
            continue
        if stamp < 10_000_000_000:
            stamp *= 1000
        if stamp + 60_000 <= end_ms and end_ms - (stamp + 60_000) <= 120_000:
            value = _number(price)
            if value is not None:
                found.append((stamp, value))
    return max(found)[1] if found else None


def model_result(row, *, funding_events=(), funding_complete=False, expiry_price=None,
                 now=None, data_error=None):
    """Pure price-level accounting. Missing evidence keeps net R NULL."""
    now = _utc(now) or datetime.now(timezone.utc)
    label = outcome(row)
    meta = row.get("strategy") or {}
    result = {"signal_id": row["id"], "model_version": MODEL_VERSION,
              "strategy_version": str(meta.get("version") or "unknown"),
              "catalog_version": str(meta.get("catalog_version") or "unknown"),
              "asset_group": str(meta.get("group") or "ungrouped"),
              "side": str(row.get("side") or "").lower(),
              "signal_created_at": row["created_at"],
              "lifecycle_updated_at": row["lifecycle_updated_at"],
              "lifecycle_status": row["lifecycle_status"],
              "entered_at": _utc(row.get("entry_hit_at")), "closed_at": None,
              "outcome": label, "cost_status": "not_closed", "gross_r": None,
              "slippage_r": None, "fee_r": None, "funding_r": None,
              "net_r": None, "retry_after": None,
              "details": {"slippage_scenario_bps": SLIPPAGE_BPS,
                          "model_only": True, "actual_user_fills_verified": False}}
    if data_error:
        result["details"]["market_data_error_type"] = str(data_error)[:80]
    if label not in TERMINAL:
        if label == "invalid_lifecycle":
            result["cost_status"] = "invalid_lifecycle"
        return result
    closed_key = ("stop_hit_at" if label in ("stopped_before_tp1", "tp1_then_be")
                  else "tp2_hit_at" if label == "tp2" else "expired_at")
    closed = _utc(row.get(closed_key))
    result["closed_at"] = closed
    if not closed or not result["entered_at"] or closed < result["entered_at"]:
        result["cost_status"] = "invalid_lifecycle"
        return result
    tp1_at = _utc(row.get("tp1_hit_at"))
    if tp1_at and not result["entered_at"] <= tp1_at <= closed:
        result["cost_status"] = "invalid_lifecycle"
        return result
    if label == "tp2" and tp1_at == closed:
        # A single tracker observation can cross both targets. It proves the
        # model's TP2 state, not two separate executable partial fills.
        result["cost_status"] = "ambiguous_target_sequence"
        return result
    if label in ("expired_after_entry", "expired_after_tp1") and expiry_price is None:
        result["cost_status"] = "pending_exit_price"
        result["retry_after"] = now + timedelta(hours=1)
        return result
    geometry = _fills(row, label, expiry_price)
    if geometry is None:
        result["cost_status"] = "invalid_levels"
        return result
    entry, risk, sign, exits = geometry
    gross = sum(weight * sign * (price - entry) / risk for price, weight in exits)
    slip = SLIPPAGE_BPS / 10000
    slipped_entry = entry * (1 + sign * slip)
    slipped_exits = [(price * (1 - sign * slip), weight) for price, weight in exits]
    after_slippage = sum(weight * sign * (price - slipped_entry) / risk
                         for price, weight in slipped_exits)
    if not all(math.isfinite(value) for value in (gross, after_slippage, slipped_entry)):
        result["cost_status"] = "invalid_levels"
        return result
    result["gross_r"] = gross
    result["slippage_r"] = gross - after_slippage
    if expiry_price is not None:
        result["details"]["expiry_price_source"] = "last_closed_1m_before_timeout"
    fee = _number((meta.get("execution_checks") or {}).get("public_taker_fee"), zero=True)
    if fee is None or fee > .01:
        result["cost_status"] = "missing_signal_fee"
        return result
    result["fee_r"] = fee * (slipped_entry + sum(price * weight for price, weight in slipped_exits)) / risk
    if not math.isfinite(result["fee_r"]):
        result["cost_status"] = "invalid_levels"
        result["fee_r"] = None
        return result
    result["details"]["fee_source"] = "public_taker_fee_saved_with_signal"
    if not funding_complete:
        result["cost_status"] = "pending_funding_history"
        result["retry_after"] = now + timedelta(hours=1)
        return result
    tp1 = tp1_at
    if tp1 and any(abs(stamp - tp1) <= EVENT_ORDER_WINDOW for stamp, _, _ in funding_events):
        result["cost_status"] = "ambiguous_funding_at_tp1"
        return result
    funding = 0.0
    for stamp, rate, mark in funding_events:
        stamp = _utc(stamp)
        if stamp is None or not result["entered_at"] < stamp < closed:
            result["cost_status"] = "invalid_funding_window"
            return result
        fraction = .5 if tp1 and stamp > tp1 else 1.0
        funding += -sign * rate * mark * fraction / risk
    if not math.isfinite(funding):
        result["cost_status"] = "invalid_funding_window"
        return result
    result["funding_r"] = funding
    result["net_r"] = after_slippage - result["fee_r"] + funding
    result["cost_status"] = "complete"
    result["details"].update(funding_source="bingx_public_settlement_history_model",
                             funding_events=len(funding_events))
    return result


def _load_pending(database_url, limit):
    import psycopg
    with psycopg.connect(database_url, connect_timeout=5) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        connection.execute("SET LOCAL statement_timeout = '10s'")
        rows = connection.execute("""SELECT s.id,s.symbol,s.side,s.entry,s.stop,s.tp1,s.tp2,
                   s.created_at,s.strategy_metadata,l.status,l.entry_hit_at,l.tp1_hit_at,
                   l.tp2_hit_at,l.stop_hit_at,l.expired_at,l.updated_at
            FROM signals s JOIN signal_lifecycle l ON l.signal_id=s.id
            LEFT JOIN group_shadow_results r ON r.signal_id=s.id AND r.model_version=%s
            WHERE s.strategy_metadata->>'version' LIKE 'group-rules-%%'
              AND s.strategy_metadata->>'group' IS NOT NULL
              AND (r.signal_id IS NULL OR r.lifecycle_updated_at < l.updated_at
                   OR (r.retry_after IS NOT NULL AND r.retry_after <= NOW()))
            ORDER BY (r.signal_id IS NOT NULL), s.id LIMIT %s""", (MODEL_VERSION, limit)).fetchall()
    keys = ("id", "symbol", "side", "entry", "stop", "tp1", "tp2", "created_at",
            "strategy", "lifecycle_status", "entry_hit_at", "tp1_hit_at",
            "tp2_hit_at", "stop_hit_at", "expired_at", "lifecycle_updated_at")
    return [dict(zip(keys, row)) for row in rows]


def _save_results(database_url, results):
    import psycopg
    with psycopg.connect(database_url, connect_timeout=5) as connection:
        connection.execute("SET LOCAL statement_timeout = '10s'")
        for row in results:
            connection.execute("""INSERT INTO group_shadow_results (
                signal_id,model_version,strategy_version,catalog_version,asset_group,side,
                signal_created_at,lifecycle_updated_at,lifecycle_status,entered_at,closed_at,
                outcome,cost_status,gross_r,slippage_r,fee_r,funding_r,net_r,details,retry_after
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
            ON CONFLICT (signal_id,model_version) DO UPDATE SET
                lifecycle_updated_at=EXCLUDED.lifecycle_updated_at,
                lifecycle_status=EXCLUDED.lifecycle_status,entered_at=EXCLUDED.entered_at,
                closed_at=EXCLUDED.closed_at,outcome=EXCLUDED.outcome,
                cost_status=EXCLUDED.cost_status,gross_r=EXCLUDED.gross_r,
                slippage_r=EXCLUDED.slippage_r,fee_r=EXCLUDED.fee_r,
                funding_r=EXCLUDED.funding_r,net_r=EXCLUDED.net_r,
                details=EXCLUDED.details,retry_after=EXCLUDED.retry_after,updated_at=NOW()
            WHERE group_shadow_results.lifecycle_updated_at <= EXCLUDED.lifecycle_updated_at""",
                (row["signal_id"],row["model_version"],row["strategy_version"],
                 row["catalog_version"],row["asset_group"],row["side"],
                 row["signal_created_at"],row["lifecycle_updated_at"],row["lifecycle_status"],
                 row["entered_at"],row["closed_at"],row["outcome"],row["cost_status"],
                 row["gross_r"],row["slippage_r"],row["fee_r"],row["funding_r"],
                 row["net_r"],json.dumps(row["details"]),row["retry_after"]))


def sync_pending(*, database_url=None, limit=50, now=None):
    """Run at worker startup/hourly; safe to retry after any interruption."""
    database_url = database_url or os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL is required")
    if not 1 <= limit <= 200:
        raise ValueError("limit must be between 1 and 200")
    now = _utc(now) or datetime.now(timezone.utc)
    pending = _load_pending(database_url, limit)
    evaluated, failures = [], 0
    for signal in pending:
        label = outcome(signal)
        expiry_price, funding_events, covered = None, (), False
        error = None
        if label in ("expired_after_entry", "expired_after_tp1"):
            try:
                expiry_price = expiry_close(signal["symbol"], signal["expired_at"], now=now)
            except Exception as exc:
                error, failures = type(exc).__name__, failures + 1
        preliminary = model_result(signal, expiry_price=expiry_price, now=now, data_error=error)
        if preliminary["cost_status"] == "pending_funding_history":
            closed_key = ("stop_hit_at" if label in ("stopped_before_tp1", "tp1_then_be")
                          else "tp2_hit_at" if label == "tp2" else "expired_at")
            try:
                funding_events, covered = funding_history(signal["symbol"],
                    signal["entry_hit_at"], signal[closed_key], now=now)
            except Exception as exc:
                error, failures = type(exc).__name__, failures + 1
        evaluated.append(model_result(signal, funding_events=funding_events,
            funding_complete=covered, expiry_price=expiry_price, now=now, data_error=error))
    if evaluated:
        _save_results(database_url, evaluated)
    return {"examined":len(evaluated),"complete":sum(r["cost_status"]=="complete" for r in evaluated),
            "pending_costs":sum(r["cost_status"].startswith("pending_") for r in evaluated),
            "market_data_errors":failures,"model_version":MODEL_VERSION}


def _drawdown_r(rows):
    cumulative = peak = maximum = 0.0
    for row in sorted(rows, key=lambda r: (r["closed_at"], r["signal_id"])):
        cumulative += float(row["net_r"])
        peak = max(peak, cumulative)
        maximum = max(maximum, peak - cumulative)
    return maximum


def summarize(rows, *, min_complete=MIN_COMPLETE_SAMPLE):
    """Group the same persisted signal once, never one result per recipient."""
    catalog = registry()
    current = (STRATEGY_VERSION, catalog["version"])
    keyed = {(current[0], current[1], group, side): []
             for group in set(catalog["mapping"].values()) for side in ("long", "short")}
    for row in rows:
        key = (row["strategy_version"],row["catalog_version"],
               row["asset_group"],row["side"])
        keyed.setdefault(key, []).append(row)
    output = []
    priority = {"core_btc": 0, "core_eth": 1, "core_sol": 2}
    ordered = sorted(keyed.items(), key=lambda item: (
        item[0][0] != current[0] or item[0][1] != current[1],
        item[0][0], item[0][1], priority.get(item[0][2], 3), item[0][2], item[0][3]))
    for (version, catalog_version, group, side), items in ordered:
        def label(record):
            if record["outcome"]:
                return record["outcome"]
            return outcome({"lifecycle_status":record["lifecycle_status"],
                "entry_hit_at":record["entered_at"],"tp1_hit_at":record["tp1_hit_at"],
                "tp2_hit_at":record["tp2_hit_at"],"stop_hit_at":record["stop_hit_at"],
                "expired_at":record["expired_at"]})
        buckets = Counter(label(r) for r in items)
        entered = sum(r["entered_at"] is not None for r in items)
        closed = [r for r in items if label(r) in TERMINAL]
        complete = [r for r in closed if r["cost_status"] == "complete" and r["net_r"] is not None]
        net = sum(float(r["net_r"]) for r in complete)
        enough = len(complete) >= min_complete
        output.append({"strategy_version":version,"catalog_version":catalog_version,
            "group":group,"side":side,"signals":len(items),"entered":entered,
            "closed_entered":len(closed),"complete_net":len(complete),
            "pending_or_incomplete_net":len(closed)-len(complete),
            "not_yet_synced":sum(r["outcome"] is None for r in items),
            "outcomes":dict(sorted(buckets.items())),
            "net_r_sum":round(net,6) if complete else None,
            "net_r_mean":round(net/len(complete),6) if complete else None,
            "closed_trade_curve_drawdown_r":round(_drawdown_r(complete),6) if complete else None,
            "net_positive_rate":round(sum(float(r["net_r"])>0 for r in complete)/len(complete),4)
                                 if enough else None,
            "sample_status":"provisional_needs_independent_validation" if enough else "insufficient_data"})
    return {"model_version":MODEL_VERSION,
            "unit":"one_signal_modelled_R_not_user_fills_or_account_equity",
            "min_complete_for_provisional_rate":min_complete,
            "drawdown_note":"Sequential closed-trade R curve; not portfolio drawdown with overlapping positions.",
            "overall":{"signals":sum(r["signals"] for r in output),
                       "entered":sum(r["entered"] for r in output),
                       "closed_entered":sum(r["closed_entered"] for r in output),
                       "complete_net":sum(r["complete_net"] for r in output),
                       "pending_or_incomplete_net":sum(r["pending_or_incomplete_net"] for r in output),
                       "not_yet_synced":sum(r["not_yet_synced"] for r in output)},
            "rows":output}


def load_report(*, database_url=None, days=30, min_complete=MIN_COMPLETE_SAMPLE):
    database_url = database_url or os.environ.get("DATABASE_URL")
    if not database_url or not 1 <= days <= 365 or not 1 <= min_complete <= 10000:
        raise ValueError("Valid DATABASE_URL, days and min_complete required")
    import psycopg
    with psycopg.connect(database_url, connect_timeout=5) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        connection.execute("SET LOCAL statement_timeout = '10s'")
        raw = connection.execute("""SELECT s.id,s.created_at,
                   s.strategy_metadata->>'version',s.strategy_metadata->>'catalog_version',
                   s.strategy_metadata->>'group',LOWER(s.side),l.entry_hit_at,
                   r.closed_at,r.outcome,r.cost_status,r.net_r,l.status,
                   l.tp1_hit_at,l.tp2_hit_at,l.stop_hit_at,l.expired_at,
                   r.lifecycle_updated_at,l.updated_at,r.lifecycle_status
            FROM signals s JOIN signal_lifecycle l ON l.signal_id=s.id
            LEFT JOIN group_shadow_results r ON r.signal_id=s.id AND r.model_version=%s
            WHERE s.strategy_metadata->>'version' LIKE 'group-rules-%%'
              AND s.strategy_metadata->>'group' IS NOT NULL
              AND s.created_at >= NOW() - %s * INTERVAL '1 day'""",
            (MODEL_VERSION, days)).fetchall()
    keys = ("signal_id","created_at","strategy_version","catalog_version","asset_group",
            "side","entered_at","closed_at","outcome","cost_status","net_r",
            "lifecycle_status","tp1_hit_at","tp2_hit_at","stop_hit_at","expired_at",
            "shadow_updated_at","lifecycle_updated_at","shadow_status")
    rows = [dict(zip(keys,row)) for row in raw]
    for row in rows:
        # Never display a prior accounting snapshot after the live lifecycle
        # advances. Derive the current outcome now; leave costs NULL until the
        # independent hourly worker catches up.
        fresh = (row["shadow_updated_at"] is not None
                 and row["shadow_updated_at"] >= row["lifecycle_updated_at"]
                 and row["shadow_status"] == row["lifecycle_status"])
        if not fresh:
            row.update(outcome=None, cost_status=None, net_r=None, closed_at=None)
    return {"days":days, **summarize(rows,min_complete=min_complete)}


def markdown_report(report):
    def cell(value):
        return "—" if value is None else str(value)
    lines = ["# Виртуальные результаты групповых сигналов",
             "", f"Период: {report['days']} дней. 1 сигнал = 1 наблюдение, не число пользователей.",
             ("Всего: {signals} сигналов, {entered} входов, {closed_entered} закрытых входов, "
              "{complete_net} полных расчётов, {pending_or_incomplete_net} без полного net, "
              "{not_yet_synced} ещё не синхронизировано.").format(**report["overall"]),
             "Это модель уровней с условным проскальзыванием 2 б.п.; не реальные исполнения и не гарантия прибыли.",
             "1R = исходное расстояние от входа до стопа; результат измеряется в долях этого риска.",
             "Чистый результат показывается только при наличии сохранённой комиссии и полной истории funding.",
             "Просадка — кривая закрытых сделок в R, не просадка счёта при перекрывающихся позициях."]
    heading = "| Группа | Напр. | Сигналов | Входов | Отмена/истёк до входа | Стоп | TP1→БУ | TP2 | Истёк после входа | Полный net | Средний net R | Просадка R | Положит. net | Статус |"
    rule = "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"
    previous_version = None
    for row in report["rows"]:
        version = (row["strategy_version"],row["catalog_version"])
        if version != previous_version:
            lines.extend(("", f"## Стратегия {version[0]} · каталог {version[1]}",
                          "", heading, rule))
            previous_version = version
        outcomes = row["outcomes"]
        lines.append("| " + " | ".join(map(cell, (row["group"],row["side"],row["signals"],
            row["entered"],outcomes.get("cancelled_before_entry",0)+outcomes.get("expired_before_entry",0),
            outcomes.get("stopped_before_tp1",0),outcomes.get("tp1_then_be",0),
            outcomes.get("tp2",0),outcomes.get("expired_after_entry",0)+outcomes.get("expired_after_tp1",0),
            row["complete_net"],row["net_r_mean"],row["closed_trade_curve_drawdown_r"],
            (f"{row['net_positive_rate']*100:.1f}%" if row["net_positive_rate"] is not None else None),
            "недостаточно данных" if row["sample_status"]=="insufficient_data" else "предварительно"))) + " |")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sync", action="store_true", help="Persist missing model rows; public market data only")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--min-complete", type=int, default=MIN_COMPLETE_SAMPLE)
    parser.add_argument("--format", choices=("json","markdown"), default="markdown")
    args = parser.parse_args()
    if args.sync:
        print(json.dumps(sync_pending(),ensure_ascii=False))
        return
    report = load_report(days=args.days,min_complete=args.min_complete)
    print(json.dumps(report,ensure_ascii=False,indent=2,default=str)
          if args.format=="json" else markdown_report(report),end="\n" if args.format=="json" else "")


if __name__ == "__main__":
    main()
