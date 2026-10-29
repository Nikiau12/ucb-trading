from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

logger = logging.getLogger("ucb.state")

try:
    from .trade_plan import plan_payload_errors
except ImportError:
    from trade_plan import plan_payload_errors

try:
    from .signal_updates import advance_lifecycle, replay_lifecycle
except ImportError:
    from signal_updates import advance_lifecycle, replay_lifecycle

try:
    import psycopg
except ImportError:
    psycopg = None

STATE_PATH = os.path.expanduser("~/.openclaw/trading/bot_state.json")
DATABASE_URL = os.getenv("DATABASE_URL", "")
SIGNAL_DEDUP_COOLDOWN_SECS = int(float(os.getenv("SIGNAL_DEDUP_HOURS", "4")) * 3600)
SIGNAL_HARD_COOLDOWN_SECS = int(float(os.getenv("SIGNAL_HARD_COOLDOWN_MINUTES", "30")) * 60)
SIGNAL_LEVEL_TOLERANCE = float(os.getenv("SIGNAL_LEVEL_TOLERANCE_PCT", "1.5")) / 100
SIGNAL_REPLAY_TP1_NOTIFICATION_MAX_AGE_HOURS = max(
    1, int(os.getenv("SIGNAL_REPLAY_TP1_NOTIFICATION_MAX_AGE_HOURS", "48"))
)


def normalize_usdt_symbol(symbol: str) -> Optional[str]:
    market = str(symbol or "").upper().strip().split(":", 1)[0]
    normalized = market.replace("/", "_").replace("-", "_")
    if not normalized.endswith("_USDT"):
        return None
    return normalized


def _db_ready() -> bool:
    return bool(DATABASE_URL and psycopg)


def record_runtime_health(
    component: str,
    *,
    success: bool,
    duration_seconds: Optional[float] = None,
    details: Optional[dict] = None,
) -> None:
    """Persist a low-cardinality worker heartbeat for production monitoring."""
    if not _db_ready() or not component:
        return
    payload = json.dumps(details or {})
    try:
        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute(
                """
                INSERT INTO runtime_health (
                    component, status, last_seen_at, last_success_at, last_error_at,
                    duration_seconds, consecutive_failures, details
                )
                VALUES (
                    %s, %s, NOW(),
                    CASE WHEN %s THEN NOW() ELSE NULL END,
                    CASE WHEN %s THEN NULL ELSE NOW() END,
                    %s, CASE WHEN %s THEN 0 ELSE 1 END, %s
                )
                ON CONFLICT (component) DO UPDATE SET
                    status = EXCLUDED.status,
                    last_seen_at = NOW(),
                    last_success_at = CASE
                        WHEN %s THEN NOW() ELSE runtime_health.last_success_at END,
                    last_error_at = CASE
                        WHEN %s THEN runtime_health.last_error_at ELSE NOW() END,
                    duration_seconds = EXCLUDED.duration_seconds,
                    consecutive_failures = CASE
                        WHEN %s THEN 0 ELSE runtime_health.consecutive_failures + 1 END,
                    details = EXCLUDED.details
                """,
                (
                    component, "ok" if success else "error", success, success,
                    duration_seconds, success, payload, success, success, success,
                ),
            )
            connection.commit()
    except Exception as exc:
        logger.warning("runtime health write failed: %s", type(exc).__name__)


def _plan_levels(plan: Optional[dict]) -> dict:
    primary = (plan or {}).get("primary") or {}
    targets = primary.get("tps") or []
    return {
        "entry": primary.get("entry"),
        "stop": primary.get("stop"),
        "tp1": targets[0].get("price") if targets else None,
        "tp2": targets[1].get("price") if len(targets) > 1 else None,
    }


def _signal_contract_rules(plan: Optional[dict]) -> dict:
    primary = (plan or {}).get("primary") or {}
    return {
        key: primary.get(key)
        for key in (
            "price_unit", "contract_size", "vol_unit", "min_vol", "max_vol",
            "max_leverage", "min_notional",
        )
    }


def _signal_lifecycle_durations(plan: Optional[dict]) -> tuple[int, int]:
    """Return entry-validity and maximum-holding durations in seconds."""
    primary = (plan or {}).get("primary") or {}
    try:
        entry_bars = max(1, int(primary.get("entry_expiry_bars") or 3))
    except (TypeError, ValueError):
        entry_bars = 3
    try:
        holding_bars = max(1, int(primary.get("max_holding_bars") or 84))
    except (TypeError, ValueError):
        holding_bars = 84
    four_hours = 4 * 60 * 60
    return entry_bars * four_hours, holding_bars * four_hours


def _levels_are_similar(previous: dict, current: dict) -> bool:
    compared = 0
    for key in ("entry", "stop", "tp1", "tp2"):
        try:
            old = float(previous.get(key))
            new = float(current.get(key))
        except (TypeError, ValueError):
            continue
        if old <= 0 or new <= 0:
            continue
        compared += 1
        if abs(new - old) / old > SIGNAL_LEVEL_TOLERANCE:
            return False
    return compared > 0


def _alert_is_allowed(previous: Optional[dict], side: str, levels: dict, now: float) -> bool:
    if previous is None:
        return True
    age = now - float(previous.get("ts", 0) or 0)
    if age < SIGNAL_HARD_COOLDOWN_SECS:
        return False
    if age >= SIGNAL_DEDUP_COOLDOWN_SECS:
        return True
    if str(previous.get("side", "")).upper() != str(side).upper():
        return True
    return not _levels_are_similar(previous, levels)


def _load() -> Dict:
    if not os.path.exists(STATE_PATH):
        return {"alerts": {}}
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"alerts": {}}


def _save(state: Dict) -> None:
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_PATH)


def should_send_alert(symbol: str, side: str, conf: float, plan: Optional[dict] = None) -> bool:
    symbol = normalize_usdt_symbol(symbol)
    if not symbol or plan_payload_errors(plan or {}):
        return False
    levels = _plan_levels(plan)
    now = time.time()
    if _db_ready():
        try:
            with psycopg.connect(DATABASE_URL) as connection:
                row = connection.execute(
                    """
                    SELECT side, confidence, entry, stop, tp1, tp2, EXTRACT(EPOCH FROM sent_at)
                    FROM signal_alert_state WHERE symbol = %s
                    """,
                    (symbol,),
                ).fetchone()
                connection.commit()
            previous = None if row is None else {
                "side": row[0], "conf": float(row[1]), "entry": row[2], "stop": row[3],
                "tp1": row[4], "tp2": row[5], "ts": float(row[6]),
            }
            return _alert_is_allowed(previous, side, levels, now)
        except Exception as exc:
            logger.warning("alert dedup read failed: %s", type(exc).__name__)
            return False
    previous = _load().get("alerts", {}).get(symbol)
    return _alert_is_allowed(previous, side, levels, now)


def mark_sent(symbol: str, side: str, conf: float, plan: Optional[dict] = None) -> None:
    symbol = normalize_usdt_symbol(symbol)
    if not symbol or plan_payload_errors(plan or {}):
        return
    levels = _plan_levels(plan)
    if _db_ready():
        try:
            with psycopg.connect(DATABASE_URL) as connection:
                connection.execute(
                    """
                    INSERT INTO signal_alert_state
                        (symbol, side, confidence, entry, stop, tp1, tp2, sent_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (symbol) DO UPDATE SET
                        side = EXCLUDED.side,
                        confidence = EXCLUDED.confidence,
                        entry = EXCLUDED.entry,
                        stop = EXCLUDED.stop,
                        tp1 = EXCLUDED.tp1,
                        tp2 = EXCLUDED.tp2,
                        sent_at = NOW()
                    """,
                    (symbol, side.upper(), conf, levels["entry"], levels["stop"],
                     levels["tp1"], levels["tp2"]),
                )
                connection.commit()
        except Exception as exc:
            logger.warning("alert dedup write failed: %s", type(exc).__name__)
        return
    state = _load()
    state.setdefault("alerts", {})[symbol] = {
        "side": side.upper(),
        "conf": conf,
        **levels,
        "ts": time.time(),
    }
    _save(state)


def get_user_lang(user_id: int) -> str:
    if _db_ready():
        try:
            with psycopg.connect(DATABASE_URL) as connection:
                row = connection.execute(
                    "SELECT language FROM user_profiles WHERE telegram_user_id = %s", (user_id,)
                ).fetchone()
                if row and row[0]:
                    return row[0]
        except Exception as exc:
            logger.warning("language read failed: %s", type(exc).__name__)
        return "en"
    return _load().get("user_langs", {}).get(str(user_id), "en")


def language_is_chosen(user_id: int) -> bool:
    if _db_ready():
        try:
            with psycopg.connect(DATABASE_URL) as connection:
                row = connection.execute(
                    "SELECT language_chosen FROM user_profiles WHERE telegram_user_id = %s",
                    (user_id,),
                ).fetchone()
                return bool(row and row[0])
        except Exception as exc:
            logger.warning("language choice read failed: %s", type(exc).__name__)
        return False
    return str(user_id) in (_load().get("user_langs") or {})


def set_user_lang(user_id: int, lang: str) -> None:
    if _db_ready():
        try:
            with psycopg.connect(DATABASE_URL) as connection:
                connection.execute(
                    """
                    INSERT INTO user_profiles (telegram_user_id, language, language_chosen)
                    VALUES (%s, %s, TRUE)
                    ON CONFLICT (telegram_user_id) DO UPDATE
                    SET language = EXCLUDED.language, language_chosen = TRUE, updated_at = NOW()
                    """,
                    (user_id, lang),
                )
                connection.commit()
        except Exception as exc:
            logger.warning("language write failed: %s", type(exc).__name__)
        return
    state = _load()
    state.setdefault("user_langs", {})[str(user_id)] = lang
    _save(state)


_USER_DEFAULTS = {"deposit": None, "risk_pct": 1.0, "lev": 10.0, "margin": "cross"}


def get_user_settings(user_id: int) -> dict:
    if _db_ready():
        try:
            with psycopg.connect(DATABASE_URL) as connection:
                row = connection.execute(
                    """
                    SELECT deposit, risk_pct, leverage, margin
                    FROM user_profiles WHERE telegram_user_id = %s
                    """,
                    (user_id,),
                ).fetchone()
                if row:
                    return {
                        "deposit": float(row[0]) if row[0] is not None else None,
                        "risk_pct": float(row[1]),
                        "lev": float(row[2]),
                        "margin": row[3],
                    }
        except Exception as exc:
            logger.warning("settings read failed: %s", type(exc).__name__)
        return dict(_USER_DEFAULTS)
    saved = _load().get("user_settings", {}).get(str(user_id), {})
    return {**_USER_DEFAULTS, **saved}


def set_user_setting(user_id: int, key: str, value) -> None:
    db_column = {"deposit": "deposit", "risk_pct": "risk_pct", "lev": "leverage", "margin": "margin"}.get(key)
    if _db_ready() and db_column:
        try:
            with psycopg.connect(DATABASE_URL) as connection:
                connection.execute(
                    "INSERT INTO user_profiles (telegram_user_id) VALUES (%s) ON CONFLICT DO NOTHING",
                    (user_id,),
                )
                connection.execute(
                    f"UPDATE user_profiles SET {db_column} = %s, updated_at = NOW() WHERE telegram_user_id = %s",
                    (value, user_id),
                )
                connection.commit()
        except Exception as exc:
            logger.warning("setting write failed: %s", type(exc).__name__)
        return
    if _db_ready():
        return
    state = _load()
    state.setdefault("user_settings", {}).setdefault(str(user_id), {})[key] = value
    _save(state)


def signal_context(plan: dict) -> tuple[str, str, str]:
    """Reason, 1D/4H regime, and setup timeframe stored with the signal."""
    trend = plan.get("trend") or {}
    primary = plan.get("primary") or {}
    reasons = [str(item) for item in (primary.get("reasons") or plan.get("reasons") or []) if item]
    safe = [
        item for item in reasons
        if not any(token in item.lower() for token in ("entry", "midrange", "deposit"))
    ]
    reason = " · ".join(safe)[:500]
    regime = f"1d={trend.get('1d') or ''};4h={trend.get('4h') or ''};regime={trend.get('regime') or ''}"
    return reason, regime, "4h"


def save_signal(plan: dict, symbol: str, side: str, confidence: float, source: str = "scanner"):
    symbol = normalize_usdt_symbol(symbol)
    if not symbol or plan_payload_errors(plan):
        return None
    if not _db_ready():
        return None
    primary = plan.get("primary") or {}
    tps = primary.get("tps") or []
    rules = _signal_contract_rules(plan)
    entry_expiry_seconds, max_holding_seconds = _signal_lifecycle_durations(plan)
    reason, regime, timeframe = signal_context(plan)
    origin = source if source in {"scanner", "manual"} else "manual"
    try:
        with psycopg.connect(DATABASE_URL) as connection:
            row = connection.execute(
                """
                INSERT INTO signals (
                    symbol, side, confidence, price, entry, stop, tp1, tp2,
                    price_unit, contract_size, vol_unit, min_vol, max_vol, max_leverage,
                    min_notional,
                    reason, regime, timeframe, source
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (symbol, side.upper(), confidence, plan.get("price"), primary.get("entry"),
                 primary.get("stop"), tps[0].get("price") if tps else None,
                 tps[1].get("price") if len(tps) > 1 else None,
                 rules["price_unit"], rules["contract_size"], rules["vol_unit"],
                 rules["min_vol"], rules["max_vol"], rules["max_leverage"],
                 rules["min_notional"],
                 reason, regime, timeframe, origin),
            ).fetchone()
            if row:
                connection.execute(
                    """
                    INSERT INTO signal_lifecycle (
                        signal_id, status, entry_expires_at, max_holding_seconds
                    )
                    VALUES (
                        %s, 'waiting_entry',
                        NOW() + (%s * INTERVAL '1 second'), %s
                    )
                    ON CONFLICT (signal_id) DO NOTHING
                    """,
                    (row[0], entry_expiry_seconds, max_holding_seconds),
                )
            connection.commit()
            return row[0] if row else None
    except Exception as exc:
        logger.warning("signal history write failed: %s", type(exc).__name__)
        return None


def save_alert_signal(
    symbol: str,
    side: str,
    confidence: float,
    *,
    source: str,
    price=None,
    entry=None,
    stop=None,
    tp1=None,
    tp2=None,
):
    """Store a spike, SMC, or listing alert for one user's history.

    The source is never ``scanner``, so the row stays out of the shared feed.
    Callers grant access only to users who actually received the alert.
    """
    if source not in {"spike", "smc", "listing"}:
        return None
    symbol = normalize_usdt_symbol(symbol)
    if not symbol or not _db_ready():
        return None
    direction = str(side or "").upper()
    if direction not in {"LONG", "SHORT"}:
        direction = "LONG"
    try:
        stored_confidence = max(0.0, min(float(confidence), 1.0))
    except (TypeError, ValueError):
        stored_confidence = 0.0
    try:
        with psycopg.connect(DATABASE_URL) as connection:
            row = connection.execute(
                """
                INSERT INTO signals (
                    symbol, side, confidence, price, entry, stop, tp1, tp2, source
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (symbol, direction, stored_confidence, price, entry, stop, tp1, tp2, source),
            ).fetchone()
            connection.commit()
            return row[0] if row else None
    except Exception as exc:
        logger.warning("alert history write failed: %s", type(exc).__name__)
        return None


def grant_signal_access(user_id: int, signal_id: int) -> None:
    if not _db_ready() or not signal_id:
        return
    try:
        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute(
                """
                INSERT INTO user_signal_access (telegram_user_id, signal_id)
                VALUES (%s, %s) ON CONFLICT DO NOTHING
                """,
                (user_id, signal_id),
            )
            # A very fast market can reach TP1 while the original Telegram
            # message is still being delivered. Backfill that recipient's
            # update atomically so the race cannot lose the BE instruction.
            connection.execute(
                """
                INSERT INTO signal_update_deliveries (
                    signal_id, telegram_user_id, event_type
                )
                SELECT %s, %s, 'tp1_reached'
                FROM signal_lifecycle
                WHERE signal_id = %s AND status = 'tp1_reached'
                ON CONFLICT (signal_id, telegram_user_id, event_type) DO NOTHING
                """,
                (signal_id, user_id, signal_id),
            )
            connection.commit()
    except Exception as exc:
        logger.warning("signal access write failed: %s", type(exc).__name__)


def load_trackable_signals(limit: int = 200) -> list[dict]:
    """Load signals whose entry, TP1, or TP2 still needs public-price tracking."""
    if not _db_ready():
        return []
    try:
        with psycopg.connect(DATABASE_URL) as connection:
            rows = connection.execute(
                """
                SELECT s.id, s.symbol, s.side, s.entry, s.stop, s.tp1, s.tp2,
                       s.created_at, s.price_unit, l.status, l.entry_expires_at,
                       l.holding_expires_at, l.max_holding_seconds
                FROM signal_lifecycle l
                JOIN signals s ON s.id = l.signal_id
                WHERE l.status IN ('replay_pending', 'waiting_entry', 'active', 'tp1_reached')
                  AND s.source IN ('scanner', 'manual')
                ORDER BY
                    CASE WHEN l.status = 'replay_pending' THEN 0 ELSE 1 END,
                    CASE WHEN l.status = 'replay_pending' THEN s.created_at END DESC,
                    s.created_at ASC
                LIMIT %s
                """,
                (max(1, min(int(limit), 1000)),),
            ).fetchall()
        keys = (
            "id", "symbol", "side", "entry", "stop", "tp1", "tp2",
            "created_at", "price_unit", "status", "entry_expires_at",
            "holding_expires_at", "max_holding_seconds",
        )
        return [dict(zip(keys, row)) for row in rows]
    except Exception as exc:
        logger.warning("signal lifecycle read failed: %s", type(exc).__name__)
        return []


def update_signal_lifecycle(
    signal_id: int,
    price=None,
    *,
    checked_at: Optional[datetime] = None,
) -> Optional[dict]:
    """Atomically advance one signal and enqueue a TP1 update for its recipients."""
    if not _db_ready() or not signal_id:
        return None
    now = checked_at or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    try:
        with psycopg.connect(DATABASE_URL) as connection:
            row = connection.execute(
                """
                SELECT s.id, s.symbol, s.side, s.entry, s.stop, s.tp1, s.tp2,
                       s.created_at, s.price_unit, l.status, l.entry_expires_at,
                       l.holding_expires_at, l.max_holding_seconds, l.entry_hit_at,
                       l.tp1_hit_at, l.tp2_hit_at, l.stop_hit_at, l.expired_at
                FROM signal_lifecycle l
                JOIN signals s ON s.id = l.signal_id
                WHERE s.id = %s
                FOR UPDATE OF l
                """,
                (int(signal_id),),
            ).fetchone()
            if not row:
                return None
            keys = (
                "id", "symbol", "side", "entry", "stop", "tp1", "tp2",
                "created_at", "price_unit", "status", "entry_expires_at",
                "holding_expires_at", "max_holding_seconds", "entry_hit_at",
                "tp1_hit_at", "tp2_hit_at", "stop_hit_at", "expired_at",
            )
            signal = dict(zip(keys, row))
            outcome = advance_lifecycle(signal, price, now)
            events = set(outcome["events"])
            if "entry_reached" in events and signal["entry_hit_at"] is None:
                signal["entry_hit_at"] = now
                signal["holding_expires_at"] = now + timedelta(
                    seconds=int(signal["max_holding_seconds"] or 0)
                )
            if "tp1_reached" in events and signal["tp1_hit_at"] is None:
                signal["tp1_hit_at"] = now
            if "tp2_reached" in events and signal["tp2_hit_at"] is None:
                signal["tp2_hit_at"] = now
            if "stop_reached" in events and signal["stop_hit_at"] is None:
                signal["stop_hit_at"] = now
            if "expired" in events and signal["expired_at"] is None:
                signal["expired_at"] = now
            connection.execute(
                """
                UPDATE signal_lifecycle
                SET status = %s, holding_expires_at = %s, entry_hit_at = %s,
                    tp1_hit_at = %s, tp2_hit_at = %s, stop_hit_at = %s,
                    expired_at = %s, last_price = COALESCE(%s, last_price),
                    last_checked_at = %s, updated_at = NOW()
                WHERE signal_id = %s
                """,
                (
                    outcome["status"], signal["holding_expires_at"],
                    signal["entry_hit_at"], signal["tp1_hit_at"],
                    signal["tp2_hit_at"], signal["stop_hit_at"],
                    signal["expired_at"], price, now, int(signal_id),
                ),
            )
            if outcome["status"] == "tp1_reached" and "tp1_reached" in events:
                connection.execute(
                    """
                    INSERT INTO signal_update_deliveries (
                        signal_id, telegram_user_id, event_type
                    )
                    SELECT %s, telegram_user_id, 'tp1_reached'
                    FROM user_signal_access
                    WHERE signal_id = %s
                    ON CONFLICT (signal_id, telegram_user_id, event_type) DO NOTHING
                    """,
                    (int(signal_id), int(signal_id)),
                )
            if outcome["status"] in {"tp2_reached", "stopped", "expired"}:
                # Never deliver a delayed BE instruction after the trade has
                # already reached a terminal state.
                connection.execute(
                    """
                    UPDATE signal_update_deliveries
                    SET status = 'sent', sent_at = COALESCE(sent_at, NOW()),
                        last_error = 'cancelled_after_terminal_state'
                    WHERE signal_id = %s AND event_type = 'tp1_reached'
                      AND status IN ('pending', 'failed')
                    """,
                    (int(signal_id),),
                )
            connection.commit()
            return {**signal, "status": outcome["status"], "events": list(outcome["events"])}
    except Exception as exc:
        logger.warning("signal lifecycle update failed id=%s: %s", signal_id, type(exc).__name__)
        return None


def replay_signal_lifecycle(
    signal_id: int,
    candles: list[dict],
    *,
    checked_at: Optional[datetime] = None,
) -> Optional[dict]:
    """Rebuild one recent pre-migration signal and persist its true state."""
    if not _db_ready() or not signal_id:
        return None
    now = checked_at or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    try:
        with psycopg.connect(DATABASE_URL) as connection:
            row = connection.execute(
                """
                SELECT s.id, s.symbol, s.side, s.entry, s.stop, s.tp1, s.tp2,
                       s.created_at, s.price_unit, l.status, l.entry_expires_at,
                       l.holding_expires_at, l.max_holding_seconds
                FROM signal_lifecycle l
                JOIN signals s ON s.id = l.signal_id
                WHERE s.id = %s AND l.status = 'replay_pending'
                FOR UPDATE OF l
                """,
                (int(signal_id),),
            ).fetchone()
            if not row:
                return None
            keys = (
                "id", "symbol", "side", "entry", "stop", "tp1", "tp2",
                "created_at", "price_unit", "status", "entry_expires_at",
                "holding_expires_at", "max_holding_seconds",
            )
            signal = dict(zip(keys, row))
            restored = replay_lifecycle(signal, candles, now)
            connection.execute(
                """
                UPDATE signal_lifecycle
                SET status = %s, holding_expires_at = %s, entry_hit_at = %s,
                    tp1_hit_at = %s, tp2_hit_at = %s, stop_hit_at = %s,
                    expired_at = %s, last_checked_at = %s, updated_at = NOW()
                WHERE signal_id = %s AND status = 'replay_pending'
                """,
                (
                    restored["status"], restored.get("holding_expires_at"),
                    restored.get("entry_hit_at"), restored.get("tp1_hit_at"),
                    restored.get("tp2_hit_at"), restored.get("stop_hit_at"),
                    restored.get("expired_at"), now, int(signal_id),
                ),
            )
            tp1_hit_at = restored.get("tp1_hit_at")
            recent_tp1 = bool(
                restored["status"] == "tp1_reached"
                and tp1_hit_at
                and now - tp1_hit_at
                <= timedelta(hours=SIGNAL_REPLAY_TP1_NOTIFICATION_MAX_AGE_HOURS)
            )
            if recent_tp1:
                connection.execute(
                    """
                    INSERT INTO signal_update_deliveries (
                        signal_id, telegram_user_id, event_type
                    )
                    SELECT %s, telegram_user_id, 'tp1_reached'
                    FROM user_signal_access
                    WHERE signal_id = %s
                    ON CONFLICT (signal_id, telegram_user_id, event_type) DO NOTHING
                    """,
                    (int(signal_id), int(signal_id)),
                )
            connection.commit()
            return {**signal, **restored, "replayed": True, "tp1_update_queued": recent_tp1}
    except Exception as exc:
        logger.warning("signal lifecycle replay failed id=%s: %s", signal_id, type(exc).__name__)
        return None


def load_pending_signal_updates(limit: int = 100) -> list[dict]:
    if not _db_ready():
        return []
    try:
        with psycopg.connect(DATABASE_URL) as connection:
            rows = connection.execute(
                """
                SELECT d.signal_id, d.telegram_user_id, d.event_type, d.attempts,
                       s.symbol, s.side, s.entry, s.tp1, s.created_at, s.price_unit
                FROM signal_update_deliveries d
                JOIN signals s ON s.id = d.signal_id
                WHERE d.status IN ('pending', 'failed')
                  AND d.attempts < 5
                  AND d.next_attempt_at <= NOW()
                ORDER BY d.created_at ASC
                LIMIT %s
                """,
                (max(1, min(int(limit), 500)),),
            ).fetchall()
        keys = (
            "id", "telegram_user_id", "event_type", "attempts", "symbol",
            "side", "entry", "tp1", "created_at", "price_unit",
        )
        return [dict(zip(keys, row)) for row in rows]
    except Exception as exc:
        logger.warning("signal update delivery read failed: %s", type(exc).__name__)
        return []


def mark_signal_update_delivery(
    signal_id: int,
    telegram_user_id: int,
    event_type: str,
    *,
    sent: bool,
    error: str = "",
    retry_seconds: int = 60,
) -> None:
    if not _db_ready():
        return
    try:
        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute(
                """
                UPDATE signal_update_deliveries
                SET status = %s, attempts = attempts + 1,
                    sent_at = CASE WHEN %s THEN NOW() ELSE sent_at END,
                    last_error = %s,
                    next_attempt_at = CASE
                        WHEN %s THEN next_attempt_at
                        ELSE NOW() + (%s * INTERVAL '1 second')
                    END
                WHERE signal_id = %s AND telegram_user_id = %s AND event_type = %s
                """,
                (
                    "sent" if sent else "failed", sent,
                    None if sent else str(error or "delivery_failed")[:200], sent,
                    max(10, min(int(retry_seconds), 3600)), int(signal_id),
                    int(telegram_user_id), str(event_type),
                ),
            )
            connection.commit()
    except Exception as exc:
        logger.warning("signal update delivery write failed: %s", type(exc).__name__)


def should_persist_sent_marker(delivered_count: int) -> bool:
    """A signal is sent only after at least one recipient actually got it."""
    return int(delivered_count) > 0


def load_alert_recipients(free_trial_signals: int) -> set[str]:
    """Profiles with a deposit and either paid access or trial credits left."""
    if not _db_ready():
        recipients = set()
        for user_id, settings in _load().get("user_settings", {}).items():
            try:
                deposit = float((settings or {}).get("deposit") or 0)
            except (TypeError, ValueError):
                deposit = 0
            if deposit > 0:
                recipients.add(str(user_id))
        return recipients
    try:
        with psycopg.connect(DATABASE_URL) as connection:
            rows = connection.execute(
                """
                SELECT p.telegram_user_id
                FROM user_profiles p
                LEFT JOIN subscriptions s ON s.telegram_user_id = p.telegram_user_id
                WHERE p.deposit > 0
                  AND (
                    s.paid_until > NOW()
                    OR COALESCE(s.trial_used, 0) < %s
                  )
                """,
                (int(free_trial_signals),),
            ).fetchall()
        return {str(row[0]) for row in rows}
    except Exception as exc:
        logger.warning("recipient load failed: %s", type(exc).__name__)
        return set()


def cooldown_ready(kind: str, key: str, cooldown_seconds: int) -> bool:
    if _db_ready():
        try:
            with psycopg.connect(DATABASE_URL) as connection:
                row = connection.execute(
                    """
                    SELECT EXTRACT(EPOCH FROM last_sent_at)
                    FROM scanner_cooldowns
                    WHERE kind = %s AND alert_key = %s
                    """,
                    (kind, key),
                ).fetchone()
            if row is None or row[0] is None:
                return True
            return time.time() - float(row[0]) >= cooldown_seconds
        except Exception as exc:
            logger.warning("cooldown read failed: %s", type(exc).__name__)
            return False
    previous = _load().get("cooldowns", {}).get(f"{kind}:{key}", 0)
    return time.time() - float(previous or 0) >= cooldown_seconds


def mark_cooldown(kind: str, key: str) -> None:
    if _db_ready():
        try:
            with psycopg.connect(DATABASE_URL) as connection:
                connection.execute(
                    """
                    INSERT INTO scanner_cooldowns (kind, alert_key, last_sent_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (kind, alert_key) DO UPDATE SET last_sent_at = NOW()
                    """,
                    (kind, key),
                )
                connection.commit()
        except Exception as exc:
            logger.warning("cooldown write failed: %s", type(exc).__name__)
        return
    state = _load()
    state.setdefault("cooldowns", {})[f"{kind}:{key}"] = time.time()
    _save(state)
