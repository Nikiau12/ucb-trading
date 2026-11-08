"""Conservative 4H development replay of baseline and new group patterns.

This is a fee/slippage *scenario*, not verified BingX execution. OHLC cannot
order multiple intrabar touches, so ambiguous paths have no PnL. The saved
funding calendars are audited separately; an incomplete calendar never becomes
zero funding or an after-all-cost result. No network, credentials or orders.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path

from evaluation.group_rule_trial import scan_development
from evaluation.sector_data import FOUR_HOURS, digest


FEE_BPS = 5.0
SLIPPAGE_BPS = 2.0


def replay_one(plan, bars, *, fee_bps=FEE_BPS, slippage_bps=SLIPPAGE_BPS):
    """Fail closed on same-bar ordering; no optimistic fill from a 4H wick."""
    if (not all(isinstance(value, (int, float)) and not isinstance(value, bool)
                and math.isfinite(value) and 0 <= value <= 100
                for value in (fee_bps, slippage_bps))):
        raise ValueError("Invalid fee/slippage scenario")
    side = plan["side"]
    if side not in ("long", "short") or not all(
            math.isfinite(plan[k]) for k in ("entry", "stop", "tp1", "tp2", "risk_price")):
        raise ValueError("Invalid trial plan")
    sign = 1 if side == "long" else -1
    entry, stop, tp1, tp2 = (plan[k] for k in ("entry", "stop", "tp1", "tp2"))
    risk = sign*(entry-stop)
    if not (risk > 0 and sign*(tp1-entry) > 0 and sign*(tp2-tp1) > 0
            and math.isclose(risk, plan["risk_price"], rel_tol=1e-9, abs_tol=1e-12)
            and plan["entry_expiry_seconds"] == 2*FOUR_HOURS):
        raise ValueError("Invalid levels or pending lifetime")
    by_time = {b.ts: b for b in bars}
    if len(by_time) != len(bars):
        raise ValueError("Duplicate 4H bar")
    signal_time = plan["signal_time"]
    pending = [by_time.get(signal_time+i*FOUR_HOURS) for i in range(2)]
    if None in pending:
        return {"status": "censored_data", "entered": None, "fee_slippage_net_r": None}
    entry_bar = None
    for bar in pending:
        hit_entry = bar.h >= entry if sign == 1 else bar.l <= entry
        hit_tp1 = bar.h >= tp1 if sign == 1 else bar.l <= tp1
        hit_stop = bar.l <= stop if sign == 1 else bar.h >= stop
        if not hit_entry:
            if hit_tp1 or hit_stop:
                return {"status": "cancelled_before_entry", "entered": False,
                        "fee_slippage_net_r": None}
            continue
        if hit_tp1 or hit_stop:
            return {"status": "ambiguous_entry_bar", "entered": None,
                    "fee_slippage_net_r": None}
        entry_bar = bar
        break
    if entry_bar is None:
        return {"status": "expired_before_entry", "entered": False,
                "fee_slippage_net_r": None}
    # A stop order gapping through its trigger fills no better than the open.
    raw_entry = max(entry, entry_bar.o) if sign == 1 else min(entry, entry_bar.o)
    fill_entry = raw_entry*(1+sign*slippage_bps/10_000)
    remaining, exits = 1.0, []
    tp1_bar = None
    deadline = entry_bar.ts + int(plan["max_holding_seconds"])
    for ts in range(entry_bar.ts+FOUR_HOURS, deadline, FOUR_HOURS):
        bar = by_time.get(ts)
        if bar is None:
            return {"status": "censored_data", "entered": True, "fee_slippage_net_r": None}
        if remaining == 1.0:
            hit_stop = bar.l <= stop if sign == 1 else bar.h >= stop
            hit_tp1 = bar.h >= tp1 if sign == 1 else bar.l <= tp1
            hit_tp2 = bar.h >= tp2 if sign == 1 else bar.l <= tp2
            hit_be = bar.l <= fill_entry if sign == 1 else bar.h >= fill_entry
            if (hit_stop and hit_tp1) or (hit_tp2 and hit_tp1) or (hit_tp1 and hit_be):
                return {"status": "ambiguous_exit_bar", "entered": True,
                        "fee_slippage_net_r": None}
            if hit_stop:
                exits.append((min(stop, bar.o) if sign == 1 else max(stop, bar.o), 1.0))
                status, remaining = "stopped_before_tp1", 0.0
                break
            if hit_tp1:
                exits.append((tp1, .5))
                remaining, tp1_bar = .5, bar.ts
        else:
            # The user moves the stop relative to their own actual entry.
            be = fill_entry
            hit_be = bar.l <= be if sign == 1 else bar.h >= be
            hit_tp2 = bar.h >= tp2 if sign == 1 else bar.l <= tp2
            if hit_be and hit_tp2:
                return {"status": "ambiguous_exit_bar", "entered": True,
                        "fee_slippage_net_r": None}
            if hit_be:
                exits.append((min(be, bar.o) if sign == 1 else max(be, bar.o), .5))
                status, remaining = "tp1_then_be", 0.0
                break
            if hit_tp2:
                exits.append((tp2, .5))
                status, remaining = "tp2", 0.0
                break
    if remaining:
        bar = by_time.get(deadline)
        if bar is None:
            return {"status": "censored_data", "entered": True, "fee_slippage_net_r": None}
        exits.append((bar.o, remaining))
        status = "timeout_after_tp1" if tp1_bar is not None else "timeout_after_entry"
    slipped_exits = [(price*(1-sign*slippage_bps/10_000), weight) for price, weight in exits]
    gross_after_slippage = sum(sign*(price-fill_entry)*weight/risk
                               for price, weight in slipped_exits)
    fee_r = (fee_bps/10_000)*(fill_entry+sum(price*weight for price, weight in slipped_exits))/risk
    return {"status": status, "entered": True,
            "fee_slippage_net_r": gross_after_slippage-fee_r,
            "fee_r": fee_r, "tp1_bar": tp1_bar,
            "cost_scope": "scenario_taker_fee_and_adverse_slippage_excludes_funding"}


def funding_audit(root, symbols):
    """Check saved funding integrity; never fill missing intervals with zeros."""
    status = {}
    for symbol in symbols:
        matches = list((Path(root)/"funding").glob(symbol+"-funding-*.json"))
        if len(matches) != 1:
            status[symbol] = "missing_or_duplicate_funding_file"
            continue
        raw = json.loads(matches[0].read_text())
        if raw.get("symbol") != symbol or digest(raw.get("rows")) != raw.get("rows_sha256"):
            status[symbol] = "funding_integrity_failed"
        elif raw.get("calendar_verified") is not True:
            status[symbol] = "calendar_not_verified"
        else:
            status[symbol] = "calendar_verified"
    return status


def summarize(plans, markets, funding_status):
    outcomes, by_group, values, per_symbol = Counter(), defaultdict(Counter), [], defaultdict(list)
    group_values = defaultdict(list)
    for plan in plans:
        per_symbol[plan["symbol"]].append(plan)
    # Conservatively reserve the full holding horizon after a possible entry.
    # This undercounts ideas but cannot create overlapping model trades.
    for symbol, rows in per_symbol.items():
        blocked_until = 0
        for plan in sorted(rows, key=lambda p: (p["signal_time"], p["side"], p["family"])):
            group_side = plan["group"]+":"+plan["side"]
            by_group[group_side]["raw_candidates"] += 1
            if plan["signal_time"] < blocked_until:
                outcomes["overlap_suppressed"] += 1
                by_group[group_side]["overlap_suppressed"] += 1
                continue
            result = replay_one(plan, markets[symbol])
            outcomes[result["status"]] += 1
            by_group[group_side][result["status"]] += 1
            if result["entered"]:
                outcomes["entered_or_ambiguous_entry"] += 1
            if result["fee_slippage_net_r"] is not None:
                values.append(result["fee_slippage_net_r"])
                group_values[group_side].append(result["fee_slippage_net_r"])
                by_group[group_side]["fee_slippage_modeled_closures"] += 1
            blocked_until = plan["signal_time"] + plan["entry_expiry_seconds"]
            if result["entered"] is not False:
                blocked_until += plan["max_holding_seconds"]
    return {"raw_candidates": len(plans), "outcomes": dict(sorted(outcomes.items())),
            "by_group_side": {key: {**dict(sorted(counter.items())),
                                    "fee_slippage_model_mean_r":
                                    (sum(group_values[key])/len(group_values[key]) if group_values[key] else None)}
                              for key, counter in sorted(by_group.items())},
            "fee_slippage_model_closures": len(values),
            "fee_slippage_model_mean_r": sum(values)/len(values) if values else None,
            "full_after_cost_result": None,
            "full_after_cost_reason": "funding calendar and intrabar order not fully verified",
            "funding_calendar_verified_symbols": sum(value == "calendar_verified" for value in funding_status.values())}


def compare(root, shortlist):
    trial, baseline, added, markets = scan_development(root, shortlist, return_details=True)
    funding = funding_audit(root, markets)
    if "funding_integrity_failed" in funding.values():
        raise ValueError("Saved funding payload changed")
    return {"mode": "offline_development_scenario_not_historical_validation",
            "live_eligible": False, "historical_validation_eligible": False,
            "profitability_established": False,
            "period": trial["period"], "new_patterns": trial["new_patterns"]["by_group_side_raw"],
            "baseline": summarize(baseline, markets, funding),
            "trial_only": summarize(added, markets, funding),
            "combined": summarize(baseline+added, markets, funding),
            "funding_audit": dict(sorted(funding.items())),
            "source": trial["source"],
            "limitations": ["4H OHLC cannot determine same-bar event order; such paths have no PnL",
                            "Fees 5 bps and adverse slippage 2 bps per fill are scenarios, not measured fills",
                            "Funding is not substituted with zero; no verified full-net statistic",
                            "Pending daily-regime-flip cancellation remains proposed, not replayed",
                            "Old development window was already viewed and groups have too few trades"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--shortlist", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(compare(args.root, args.shortlist), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
