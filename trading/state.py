from __future__ import annotations

import json
import logging
import os
import time
from typing import Dict, Optional

logger = logging.getLogger("ucb.state")

try:
    from .trade_plan import plan_payload_errors
except ImportError:
    from trade_plan import plan_payload_errors

try:
    import psycopg
except ImportError:
    psycopg = None

STATE_PATH = os.path.expanduser("~/.openclaw/trading/bot_state.json")
DATABASE_URL = os.getenv("DATABASE_URL", "")
SIGNAL_DEDUP_COOLDOWN_SECS = int(float(os.getenv("SIGNAL_DEDUP_HOURS", "4")) * 3600)
SIGNAL_HARD_COOLDOWN_SECS = int(float(os.getenv("SIGNAL_HARD_COOLDOWN_MINUTES", "30")) * 60)
SIGNAL_LEVEL_TOLERANCE = float(os.getenv("SIGNAL_LEVEL_TOLERANCE_PCT", "1.5")) / 100


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
        for key in ("price_unit", "contract_size", "vol_unit", "min_vol", "max_vol", "max_leverage")
    }


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


def set_user_lang(user_id: int, lang: str) -> None:
    if _db_ready():
        try:
            with psycopg.connect(DATABASE_URL) as connection:
                connection.execute(
                    """
                    INSERT INTO user_profiles (telegram_user_id, language) VALUES (%s, %s)
                    ON CONFLICT (telegram_user_id) DO UPDATE
                    SET language = EXCLUDED.language, updated_at = NOW()
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


def save_signal(plan: dict, symbol: str, side: str, confidence: float, source: str = "scanner"):
    symbol = normalize_usdt_symbol(symbol)
    if not symbol or plan_payload_errors(plan):
        return None
    if not _db_ready():
        return None
    primary = plan.get("primary") or {}
    tps = primary.get("tps") or []
    rules = _signal_contract_rules(plan)
    origin = source if source in {"scanner", "manual"} else "manual"
    try:
        with psycopg.connect(DATABASE_URL) as connection:
            row = connection.execute(
                """
                INSERT INTO signals (
                    symbol, side, confidence, price, entry, stop, tp1, tp2,
                    price_unit, contract_size, vol_unit, min_vol, max_vol, max_leverage,
                    source
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (symbol, side.upper(), confidence, plan.get("price"), primary.get("entry"),
                 primary.get("stop"), tps[0].get("price") if tps else None,
                 tps[1].get("price") if len(tps) > 1 else None,
                 rules["price_unit"], rules["contract_size"], rules["vol_unit"],
                 rules["min_vol"], rules["max_vol"], rules["max_leverage"], origin),
            ).fetchone()
            connection.commit()
            return row[0] if row else None
    except Exception as exc:
        logger.warning("signal history write failed: %s", type(exc).__name__)
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
            connection.commit()
    except Exception as exc:
        logger.warning("signal access write failed: %s", type(exc).__name__)


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
