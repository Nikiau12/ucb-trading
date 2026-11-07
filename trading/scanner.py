from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

try:
    import bingx_snapshot as snap
except ImportError:
    from trading import bingx_snapshot as snap
from trading import group_plan as core

logger = logging.getLogger(__name__)


def _conf(plan: Dict) -> float:
    if plan.get("side") == "skip":
        return float(plan.get("confidence", 0) or 0)
    return float((plan.get("primary") or {}).get("confidence", 0) or 0)


def scan_symbol(
    symbol: str,
    deposit: float,
    risk_pct: float,
    lev: float,
    margin: str,
) -> Optional[Dict[str, Any]]:
    try:
        # Unclassified markets need no expensive history or ticker request.
        if symbol not in core.catalog()[1]:
            return core.make_plan({"symbol": symbol}, deposit, risk_pct, lev, margin)
        snapshot = snap.build_group_snapshot(symbol)
        return core.make_plan(snapshot, deposit=deposit, risk_pct=risk_pct, lev=lev, margin=margin)
    except Exception as e:
        logger.warning("scan_symbol %s error=%s code=%s", symbol, type(e).__name__, getattr(e, "code", None))
        return {"symbol": symbol, "side": "skip", "confidence": 0,
                "reasons": ["group_market_unavailable"],
                "error_type": type(e).__name__, "error_code": getattr(e, "code", None)}


def scan_all(
    symbols: List[str],
    *,
    deposit: float,
    risk_pct: float,
    lev: float,
    margin: str,
    workers: int = 10,
) -> List[Dict[str, Any]]:
    started_at = time.monotonic()
    symbols = list(dict.fromkeys(symbols))
    if symbols:
        try:
            # One current whole-market ticker snapshot, rather than N identical
            # requests. Individual tickers still refresh when this cache expires.
            snap.futures_all_tickers()
        except Exception as exc:
            logger.warning("scanner ticker warmup unavailable error=%s", type(exc).__name__)
    results: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {
            ex.submit(scan_symbol, sym, deposit, risk_pct, lev, margin): sym
            for sym in symbols
        }
        for f in as_completed(futures):
            r = f.result()
            if r is not None:
                results.append(r)
    results.sort(key=_conf, reverse=True)
    logger.info(
        "scan_all completed requested=%s completed=%s failed=%s stale=%s duration_seconds=%.2f workers=%s",
        len(symbols),
        len(results),
        sum(r.get("reasons") == ["group_market_unavailable"] for r in results),
        sum(bool(result.get("used_cache")) for result in results),
        time.monotonic() - started_at,
        workers,
    )
    return results
