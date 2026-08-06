from __future__ import annotations

import json
import os
import time
from typing import Dict, Optional

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


def _ensure_profiles_table(connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS user_profiles (
            telegram_user_id BIGINT PRIMARY KEY,
            language TEXT NOT NULL DEFAULT 'en',
            deposit NUMERIC,
            risk_pct NUMERIC NOT NULL DEFAULT 1,
            leverage NUMERIC NOT NULL DEFAULT 10,
            margin TEXT NOT NULL DEFAULT 'cross',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


def _ensure_alert_state_table(connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS signal_alert_state (
            symbol TEXT PRIMARY KEY,
            side TEXT NOT NULL,
            confidence NUMERIC NOT NULL,
            entry NUMERIC,
            stop NUMERIC,
            tp1 NUMERIC,
            tp2 NUMERIC,
            sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


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
                _ensure_alert_state_table(connection)
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
            print(f"[state] database alert dedup read failed: {exc}")
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
                _ensure_alert_state_table(connection)
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
            print(f"[state] database alert dedup write failed: {exc}")
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
                _ensure_profiles_table(connection)
                row = connection.execute(
                    "SELECT language FROM user_profiles WHERE telegram_user_id = %s", (user_id,)
                ).fetchone()
                if row:
                    return row[0]
        except Exception as exc:
            print(f"[state] database language read failed: {exc}")
    return _load().get("user_langs", {}).get(str(user_id), "en")


def set_user_lang(user_id: int, lang: str) -> None:
    if _db_ready():
        try:
            with psycopg.connect(DATABASE_URL) as connection:
                _ensure_profiles_table(connection)
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
            print(f"[state] database language write failed: {exc}")
    state = _load()
    state.setdefault("user_langs", {})[str(user_id)] = lang
    _save(state)


_USER_DEFAULTS = {"deposit": None, "risk_pct": 1.0, "lev": 10.0, "margin": "cross"}


def get_user_settings(user_id: int) -> dict:
    if _db_ready():
        try:
            with psycopg.connect(DATABASE_URL) as connection:
                _ensure_profiles_table(connection)
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
            print(f"[state] database settings read failed: {exc}")
    saved = _load().get("user_settings", {}).get(str(user_id), {})
    return {**_USER_DEFAULTS, **saved}


def set_user_setting(user_id: int, key: str, value) -> None:
    db_column = {"deposit": "deposit", "risk_pct": "risk_pct", "lev": "leverage", "margin": "margin"}.get(key)
    if _db_ready() and db_column:
        try:
            with psycopg.connect(DATABASE_URL) as connection:
                _ensure_profiles_table(connection)
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
            print(f"[state] database setting write failed: {exc}")
    state = _load()
    state.setdefault("user_settings", {}).setdefault(str(user_id), {})[key] = value
    _save(state)


def save_signal(plan: dict, symbol: str, side: str, confidence: float):
    symbol = normalize_usdt_symbol(symbol)
    if not symbol or plan_payload_errors(plan):
        return None
    if not _db_ready():
        return None
    primary = plan.get("primary") or {}
    tps = primary.get("tps") or []
    rules = _signal_contract_rules(plan)
    try:
        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS signals (
                    id BIGSERIAL PRIMARY KEY, symbol TEXT NOT NULL, side TEXT NOT NULL,
                    confidence NUMERIC NOT NULL, price NUMERIC, entry NUMERIC, stop NUMERIC,
                    tp1 NUMERIC, tp2 NUMERIC, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            connection.execute(
                """
                ALTER TABLE signals ADD COLUMN IF NOT EXISTS price_unit NUMERIC;
                ALTER TABLE signals ADD COLUMN IF NOT EXISTS contract_size NUMERIC;
                ALTER TABLE signals ADD COLUMN IF NOT EXISTS vol_unit NUMERIC;
                ALTER TABLE signals ADD COLUMN IF NOT EXISTS min_vol NUMERIC;
                ALTER TABLE signals ADD COLUMN IF NOT EXISTS max_vol NUMERIC;
                ALTER TABLE signals ADD COLUMN IF NOT EXISTS max_leverage NUMERIC;
                """
            )
            row = connection.execute(
                """
                INSERT INTO signals (
                    symbol, side, confidence, price, entry, stop, tp1, tp2,
                    price_unit, contract_size, vol_unit, min_vol, max_vol, max_leverage
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (symbol, side.upper(), confidence, plan.get("price"), primary.get("entry"),
                 primary.get("stop"), tps[0].get("price") if tps else None,
                 tps[1].get("price") if len(tps) > 1 else None,
                 rules["price_unit"], rules["contract_size"], rules["vol_unit"],
                 rules["min_vol"], rules["max_vol"], rules["max_leverage"]),
            ).fetchone()
            connection.commit()
            return row[0] if row else None
    except Exception as exc:
        print(f"[state] signal history write failed: {exc}")
        return None


def grant_signal_access(user_id: int, signal_id: int) -> None:
    if not _db_ready() or not signal_id:
        return
    try:
        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS user_signal_access (
                    telegram_user_id BIGINT NOT NULL,
                    signal_id BIGINT NOT NULL,
                    granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (telegram_user_id, signal_id)
                )
                """
            )
            connection.execute(
                """
                INSERT INTO user_signal_access (telegram_user_id, signal_id)
                VALUES (%s, %s) ON CONFLICT DO NOTHING
                """,
                (user_id, signal_id),
            )
            connection.commit()
    except Exception as exc:
        print(f"[state] signal access write failed: {exc}")
