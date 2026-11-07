"""Small, non-personal decision journal. No orders, strategy changes or PnL claims.

Read-only commands:
  python -m trading.scan_diagnostics --live-universe
  python -m trading.scan_diagnostics --dry-scan  (public data; no DB or messages)
  python -m trading.scan_diagnostics --hours 24   (DATABASE_URL required)
  python -m trading.scan_diagnostics --outcomes --hours 24
"""
from collections import Counter, defaultdict
import argparse
import json
import os

from trading.group_catalog import coverage, registry

OUTCOMES = ("candidate", "no_setup", "blocked_catalog", "blocked_market", "data_unavailable")


def decision(plan):
    reasons = [str(r).split(":", 1)[0] for r in plan.get("reasons", [])]
    if "unclassified_symbol_no_group_fallback" in reasons:
        outcome = "blocked_catalog"
    elif plan.get("used_cache") or any(r in reasons for r in (
        "group_market_unavailable", "group_data_rejected", "group_data_unavailable",
        "stale_market_data", "scan_result_missing",
    )):
        outcome = "data_unavailable"
    elif plan.get("primary") and plan.get("side") != "skip":
        outcome = "candidate"
    elif "group_no_setup" in reasons:
        outcome = "no_setup"
    else:
        outcome = "blocked_market"
    return outcome, reasons


def summarize_scan(symbols, results, *, strategy_version):
    catalog = registry()
    symbols = list(dict.fromkeys(symbols))
    # Only requested symbols; no user IDs, balances, credentials, raw API errors
    # or executable prices are accepted into this operational journal.
    indexed = {p.get("symbol"): p for p in results if p.get("symbol") in symbols}
    outcomes, reasons, by_group, directions, rows = Counter(), Counter(), defaultdict(Counter), defaultdict(Counter), []
    errors = Counter()
    direction_reasons = defaultdict(Counter)
    for symbol in symbols:
        plan = indexed.get(symbol, {"symbol": symbol, "side": "skip", "reasons": ["scan_result_missing"]})
        outcome, codes = decision(plan)
        group = catalog["mapping"].get(symbol, "ungrouped")
        outcomes[outcome] += 1
        reasons.update(set(codes))
        by_group[group][outcome] += 1
        row = {"symbol": symbol, "group": group, "outcome": outcome, "reasons": codes}
        if outcome == "data_unavailable":
            detail = str(next(iter(plan.get("reasons", [])), "")).partition(":")[2]
            if detail.isidentifier():
                row["detail_code"] = detail
        error_type = plan.get("error_type")
        if isinstance(error_type, str) and error_type.isidentifier():
            row["error_type"] = error_type[:80]
            errors[row["error_type"]] += 1
        if type(plan.get("error_code")) is int:
            row["error_code"] = plan["error_code"]
        primary = plan.get("primary") or {}
        if primary.get("side") in ("long", "short"):
            row["side"] = primary["side"]
            directions[group + ":" + primary["side"]][outcome] += 1
        side_decisions = []
        for item in plan.get("direction_decisions", []):
            if item.get("side") in ("long", "short") and item.get("status") in ("no_setup", "blocked_data"):
                status = item["status"]
                # Data failures are never disguised as lack of a setup.
                directions[group + ":" + item["side"]][status] += 1
                reason = str(item.get("reason") or "unknown")
                side_decisions.append({"side": item["side"], "status": status,
                                       "reason": reason if reason.isidentifier() else "data_validation"})
                direction_reasons[group + ":" + item["side"]][side_decisions[-1]["reason"]] += 1
        if side_decisions:
            row["directions"] = side_decisions
        if symbol in catalog["pending"]:
            row["review_reason"] = catalog["pending"][symbol]
        rows.append(row)
    summary = {"schema_version": 1, "strategy_version": strategy_version,
               "catalog_version": catalog["version"], "requested": len(symbols),
               "completed": len(symbols) - outcomes["data_unavailable"],
               "failed": outcomes["data_unavailable"],
               "strategy_evaluated": sum(outcomes[key] for key in ("candidate", "no_setup", "blocked_market")),
               "pending_catalog_review": outcomes["blocked_catalog"],
               "stale": sum(bool(p.get("used_cache")) for p in indexed.values()),
               "outcomes": {key: outcomes[key] for key in OUTCOMES},
               "reasons": dict(reasons), "errors": dict(errors), "by_group": {g: dict(v) for g, v in by_group.items()},
               "by_group_direction": {g: dict(v) for g, v in directions.items()},
               "reason_counts_by_group_direction": {g: dict(v) for g, v in direction_reasons.items()},
               "data_failures": [row for row in rows if row["outcome"] == "data_unavailable"],
               "coverage": coverage(symbols)}
    return summary, rows


def trade_bucket(status, entry_hit_at, tp1_hit_at, tp2_hit_at):
    """Model outcome, never an exchange fill or after-cost PnL."""
    if status == "cancelled_before_entry" and not entry_hit_at:
        return "cancelled_before_entry"
    if status == "expired" and not entry_hit_at:
        return "expired_before_entry"
    if status in ("replay_pending", "waiting_entry") and not entry_hit_at:
        return "awaiting_entry"
    if not entry_hit_at:
        return "inconsistent_lifecycle"
    if status == "tp2_reached" and tp2_hit_at:
        return "tp2_model"
    if status == "stopped":
        return "tp1_then_stop_model" if tp1_hit_at else "stop_before_tp1_model"
    if status == "expired":
        return "expired_after_tp1_model" if tp1_hit_at else "expired_after_entry_model"
    if status == "tp1_reached" and tp1_hit_at:
        return "tp1_open_model"
    if status == "active":
        return "active_without_tp1_model"
    return "inconsistent_lifecycle"


def summarize_trade_outcomes(rows):
    """Count distinct signals, never users, alerts or hourly rechecks."""
    group_totals, overall = defaultdict(Counter), Counter()
    for version, catalog_version, group, side, status, entry_at, tp1_at, tp2_at in rows:
        direction = str(side).lower()
        if direction not in ("long", "short"):
            continue
        key = (version, catalog_version or "baseline", group or "ungrouped", direction)
        bucket = trade_bucket(status, entry_at, tp1_at, tp2_at)
        group_totals[key][bucket] += 1
        overall[bucket] += 1
    open_or_entered = ("active_without_tp1_model", "tp1_open_model", "stop_before_tp1_model",
                       "tp1_then_stop_model", "tp2_model", "expired_after_entry_model",
                       "expired_after_tp1_model")
    def totals(counts):
        return {"signals": sum(counts.values()), "entered": sum(counts[k] for k in open_or_entered),
                "buckets": dict(sorted(counts.items()))}
    return {"unit": "distinct_model_signals_not_user_fills_or_profit",
            "overall": totals(overall),
            "by_group_direction_version": [
                {"strategy_version": version, "catalog_version": catalog,
                 "group": group, "side": direction, **totals(counts)}
                for (version, catalog, group, direction), counts in sorted(group_totals.items())
            ]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--live-universe", action="store_true")
    mode.add_argument("--dry-scan", action="store_true")
    mode.add_argument("--outcomes", action="store_true")
    parser.add_argument("--hours", type=int, default=24)
    args = parser.parse_args()
    if args.live_universe or args.dry_scan:
        from miniapp.universe import top_symbols
        symbols = top_symbols()
        if args.dry_scan:
            from trading import scanner, group_plan
            results = scanner.scan_all(symbols, deposit=1000, risk_pct=2, lev=10, margin="cross", workers=2)
            summary, _ = summarize_scan(symbols, results, strategy_version=group_plan.VERSION)
            print(json.dumps({"mode": "dry_scan_no_persistence_or_delivery", **summary}, ensure_ascii=False, indent=2))
        else:
            print(json.dumps(coverage(symbols), ensure_ascii=False, indent=2))
        return
    if not 1 <= args.hours <= 24 * 90:
        parser.error("hours must be between 1 and 2160")
    if not os.environ.get("DATABASE_URL"):
        parser.error("DATABASE_URL is required for a read-only journal report")
    import psycopg
    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=5) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        connection.execute("SET LOCAL statement_timeout = '10s'")
        if args.outcomes:
            rows = connection.execute(
                """SELECT s.strategy_metadata->>'version',
                          s.strategy_metadata->>'catalog_version',
                          s.strategy_metadata->>'group', s.side, l.status,
                          l.entry_hit_at, l.tp1_hit_at, l.tp2_hit_at
                   FROM signals s LEFT JOIN signal_lifecycle l ON l.signal_id=s.id
                   WHERE s.strategy_metadata->>'version' IS NOT NULL
                     AND s.created_at >= NOW() - %s * INTERVAL '1 hour'""", (args.hours,)
            ).fetchall()
            print(json.dumps({"hours": args.hours, **summarize_trade_outcomes(rows)},
                             ensure_ascii=False, indent=2))
            return
        rows = connection.execute(
            """SELECT strategy_version,catalog_version,summary FROM scanner_runs
               WHERE started_at >= NOW() - %s * INTERVAL '1 hour' ORDER BY started_at""", (args.hours,)
        ).fetchall()
    # Versions stay separate. These are scanner attempts, not unique trades or a win rate.
    totals = {}
    for version, catalog_version, summary in rows:
        key = (version, catalog_version)
        item = totals.setdefault(key, {"runs": 0, "outcomes": Counter(), "reasons": Counter(),
                                       "by_group": defaultdict(Counter), "by_group_direction": defaultdict(Counter),
                                       "reason_counts_by_group_direction": defaultdict(Counter)})
        item["runs"] += 1
        item["outcomes"].update(summary["outcomes"])
        item["reasons"].update(summary["reasons"])
        for group, counts in summary["by_group"].items():
            item["by_group"][group].update(counts)
        for direction, counts in summary.get("by_group_direction", {}).items():
            item["by_group_direction"][direction].update(counts)
        for direction, counts in summary.get("reason_counts_by_group_direction", {}).items():
            item["reason_counts_by_group_direction"][direction].update(counts)
    print(json.dumps({"hours": args.hours, "unit": "scanner_attempts_not_trades",
                      "versions": [{"strategy_version": v, "catalog_version": c, **data}
                                   for (v, c), data in totals.items()]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
