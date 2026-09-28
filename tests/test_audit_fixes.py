import asyncio
import inspect
import json
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRADING_DIR = ROOT / "trading"
if str(TRADING_DIR) not in sys.path:
    sys.path.insert(0, str(TRADING_DIR))

from aiogram.exceptions import TelegramRetryAfter  # noqa: E402

from core.access_manager import AccessManager, decide_consume
from core.bot_commands import PUBLIC_COMMANDS, menu_commands
from core.chat_policy import is_private_chat, language_for_start
from core.notifier import Notifier
from core.payment_reasons import payment_reason_key
from core.worker_lock import hold_worker_lock
from miniapp import app as miniapp
from miniapp.invoice_amount import unique_invoice_amount
from trading import state
from trading.auto_alert import render_auto_alert
from trading.i18n import t
from trading.telegram_render import render_telegram_plan
from trading.user_input import parse_setting


def test_invoice_amounts_are_unique_and_stay_near_the_base_price():
    first = unique_invoice_amount("29.99", 1, set())
    second = unique_invoice_amount("29.99", 2, {first})

    assert first != second
    assert Decimal("29.99") < first < Decimal("30")
    assert Decimal("29.99") < second < Decimal("30")


def test_settle_failure_rolls_back_and_is_not_success(monkeypatch, tmp_path):
    manager = AccessManager(str(tmp_path / "access.json"), 5, 720, "TWallet", "29.99", "TRC20")
    manager.database_url = "postgresql://test"
    seen = {}

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            seen["rolled_back"] = exc_type is not None
            return False

    def fail(*_args, **_kwargs):
        raise RuntimeError("subscription update did not return paid_until")

    monkeypatch.setattr("core.access_manager.psycopg.connect", lambda *_args, **_kwargs: Connection())
    monkeypatch.setattr("miniapp.billing.settle_payment_transaction", fail)

    result = manager.settle_payment(
        "42",
        "a" * 64,
        paid_amount="29.990001",
        expected_amount="29.990001",
    )

    assert result == {"ok": False, "reason": "save_failed"}
    assert seen["rolled_back"] is True


def test_trial_decision_does_not_debit_before_delivery():
    user = {"trial_used": 1, "paid_until": 0, "last_trial_signal_at": 0}

    allowed, mode, updated = decide_consume(
        user, now=1_000, free_signals=5, cooldown_seconds=60
    )

    assert allowed is True
    assert mode == "trial"
    assert user["trial_used"] == 1
    assert updated["trial_used"] == 2
    assert updated["previous_trial_used"] == 1


def test_failed_send_does_not_consume_trial_credit():
    access = _Access()
    notifier = Notifier(bot=_Bot([RuntimeError("rejected")]), access_manager=access)

    delivered = asyncio.run(notifier.send_message_to_user("42", "hello"))

    assert delivered is False
    assert access.consumed == 0


def test_retry_after_then_success_consumes_trial_once(monkeypatch):
    monkeypatch.setattr("core.notifier.asyncio.sleep", _async_noop)
    access = _Access()
    flood = TelegramRetryAfter(method=object(), message="flood", retry_after=1)
    notifier = Notifier(bot=_Bot([flood, "ok"]), access_manager=access)

    delivered = asyncio.run(notifier.send_message_to_user("42", "hello"))

    assert delivered is True
    assert access.consumed == 1


def test_trial_update_requires_the_locked_row():
    source = inspect.getsource(AccessManager._lock_subscription) + inspect.getsource(AccessManager.consume_signal)
    assert "FOR UPDATE" in source
    assert "trial_used = %s" in source

    manager = AccessManager(":memory:", 5, 720, "TWallet", "29.99", "TRC20")
    manager.database_url = "postgresql://test"
    connection = _LockedConnection(rowcount=0)

    import core.access_manager as access_module

    original = access_module.psycopg.connect
    access_module.psycopg.connect = lambda *_args, **_kwargs: connection
    try:
        allowed, mode = manager.consume_signal("42")
    finally:
        access_module.psycopg.connect = original

    assert allowed is False
    assert mode == "conflict"
    assert connection.rolled_back is True


def test_html_renderers_escape_interpolated_values():
    plan = {
        "symbol": "<script>",
        "price": 1,
        "margin": "<img>",
        "trend": {"1d": "<b>", "4h": "up", "struct4h": "x", "bos": "y", "regime": "z"},
        "primary": {
            "side": "long",
            "confidence": 0.8,
            "entry": 1,
            "stop": 0.9,
            "tps": [{"price": 1.1}, {"price": 1.2}],
            "why": ["<svg>"],
            "reasons": ["<svg>"],
        },
        "context": {"regime": "<img>", "trend_1d": "<b>"},
    }

    rendered = render_telegram_plan(plan, deposit=1000, risk_pct=1, lang="en")
    alert = render_auto_alert(
        plan, "<script>", "LONG", 0.8, 1000, 1, 10, lang="en"
    )

    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered
    assert "<script>" not in alert
    assert "&lt;script&gt;" in alert
    assert "<img>" not in alert
    assert "80%" in rendered
    assert "80%" in alert
    assert "/ 1.0" not in alert


def test_confidence_percent_is_one_scale():
    plan = {
        "symbol": "BTC_USDT",
        "price": 100,
        "trend": {},
        "levels": {},
        "primary": {
            "side": "long",
            "confidence": 0.78,
            "entry": 100,
            "stop": 90,
            "tps": [{"price": 120}, {"price": 140}],
            "reasons": [],
        },
    }
    rendered = render_telegram_plan(plan, deposit=1000, risk_pct=1, lang="en")
    alert = render_auto_alert(plan, "BTC_USDT", "LONG", 0.78, 1000, 1, 10, lang="en")
    assert "78%" in rendered
    assert "78%" in alert
    assert "0.78" not in alert
    assert "/ 1.0" not in alert
    isolated = dict(plan, margin="isolated")
    named = render_telegram_plan(isolated, deposit=1000, risk_pct=1, lang="en")
    assert "ISOLATED + leverage" in named
    assert "CROSS +" not in named
    assert "Топ-5" not in t("ru", "scan_done_one", count=1)
    assert "Top 5" not in t("en", "scan_done_one", count=1)
    assert "Top" not in t("en", "scan_done_one", count=1)
    assert "≥65%" in t("en", "digest_high", count=1)
    assert "0.65" not in t("en", "digest_high", count=1)
    assert "50–65%" in t("ru", "digest_medium", count=2)


def test_listing_alerts_follow_the_recipient_language():
    english = Notifier().format_listing_alert("NEW_USDT", {"name": "New", "rank": 4}, lang="en")
    russian = Notifier().format_listing_alert("NEW_USDT", {"name": "New"}, lang="ru")
    assert "New MEXC pair" in english
    assert "Новая пара" not in english
    assert "Новая пара" in russian
    news = Notifier().format_listing_news_alert(
        {"title": "Lists NEW", "url": "https://mexc.example", "symbols": ["NEW"], "published_at": "2026-01-01"},
        lang="de",
    )
    assert "Listing-News" in news
    assert "Новость" not in news


def test_smc_confidence_renders_as_percent():
    from types import SimpleNamespace

    from core.notifier import Notifier

    score = SimpleNamespace(
        confidence=78,
        regime=SimpleNamespace(value="range"),
        phase=SimpleNamespace(value="unknown"),
        reasons=["structure"],
    )
    verdict = SimpleNamespace(
        confidence=64,
        setup_type=SimpleNamespace(name="no_trade"),
        risk_flags=[],
    )
    text = Notifier().format_smc_setup(
        "BTC_USDT",
        "4h",
        {"type": "LONG", "reason": "bos", "entry": 1, "stop_loss": 0.9, "take_profit": 1.2, "rr": 2},
        score,
        verdict,
        lang="en",
    )
    assert "78%" in text
    assert "64%" in text
    assert "/100" not in text


def test_set_limits_match_the_mini_app():
    assert parse_setting("risk", "0.1") == ("risk_pct", 0.1)
    assert parse_setting("risk", "5") == ("risk_pct", 5.0)
    assert parse_setting("lev", "100") == ("lev", 100.0)
    assert parse_setting("margin", "isolated") == ("margin", "isolated")
    for key, raw in (("risk", "0.09"), ("risk", "5.1"), ("lev", "0"), ("lev", "101"), ("margin", "both")):
        try:
            parse_setting(key, raw)
        except ValueError:
            continue
        raise AssertionError(f"{key}={raw} should be rejected")


def test_commands_stay_in_private_chats_and_start_keeps_language():
    assert is_private_chat("private") is True
    assert is_private_chat("group") is False
    assert language_for_start("ru", "") == ("ru", False)
    assert language_for_start("ru", "subscribe_de") == ("de", True)


def test_paid_feed_is_scanner_only_and_trial_feed_is_granted_only():
    assert "source = 'scanner'" in miniapp.PAID_SIGNALS_SQL
    assert "s.source <> 'scanner'" in miniapp.PAID_SIGNALS_SQL
    assert "user_signal_access" in miniapp.PAID_SIGNALS_SQL
    assert "user_signal_access" in miniapp.TRIAL_SIGNALS_SQL
    assert "source = 'scanner'" not in miniapp.TRIAL_SIGNALS_SQL
    assert "INSERT INTO user_signal_access" not in inspect.getsource(miniapp.signals)


def test_help_describes_the_hourly_scanner_and_manual_digest():
    help_text = t("en", "help", top_n=80)
    assert "every hour" in help_text
    assert "/digest" in help_text
    assert "00:05" not in help_text
    assert "04:05" not in help_text
    assert "78%" in help_text
    assert "0.0–1.0" not in help_text
    assert "<code>conf</code>" not in help_text
    russian = t("ru", "help", top_n=80)
    assert "78%" in russian
    assert "<code>entry</code>" not in russian
    assert "<code>stop</code>" not in russian
    assert "<code>conf</code>" not in russian
    assert "0.0–1.0" not in russian


def test_config_does_not_carry_a_bot_token():
    payload = json.loads((ROOT / "trading" / "config.json").read_text(encoding="utf-8"))
    assert "telegram" not in payload
    assert "token" not in json.dumps(payload).lower()


def test_postgres_language_write_does_not_copy_the_openclaw_file(monkeypatch, tmp_path):
    target = tmp_path / "bot_state.json"
    monkeypatch.setattr(state, "DATABASE_URL", "postgresql://test")
    monkeypatch.setattr(state, "STATE_PATH", str(target))

    def unavailable(*_args, **_kwargs):
        raise RuntimeError("no database")

    monkeypatch.setattr(state.psycopg, "connect", unavailable)
    state.set_user_lang(7, "ru")

    assert target.exists() is False


def test_public_menu_omits_admin_commands():
    commands = {name for name, _description in PUBLIC_COMMANDS}
    assert "grant" not in commands
    assert "revoke" not in commands
    assert "setup" not in commands
    assert "spikes" not in commands
    russian = {item.command: item.description for item in menu_commands("ru")}
    english = {item.command: item.description for item in menu_commands("en")}
    assert set(russian) == set(english)
    assert "setup" not in russian
    assert "spikes" not in russian
    assert russian["plan"] != english["plan"]
    assert "План" in russian["plan"]
    source = (ROOT / "bot_mexc.py").read_text(encoding="utf-8")
    assert 'Command("setup")' in source
    assert 'Command("spikes")' in source
    assert "BotCommandScopeChat" in source
    assert "language_code=code" in source


def test_payment_reasons_stay_distinct():
    assert payment_reason_key("wallet_not_configured") != "payment_not_found"
    assert payment_reason_key("transaction_expired") != payment_reason_key("wallet_not_configured")


def test_second_worker_does_not_poll(monkeypatch):
    assert hold_worker_lock("") is None

    class Connection:
        def execute(self, *_args, **_kwargs):
            return self

        def fetchone(self):
            return (False,)

        def close(self):
            return None

    import psycopg

    monkeypatch.setattr(psycopg, "connect", lambda *_args, **_kwargs: Connection())
    assert hold_worker_lock("postgresql://test") is False


class _Access:
    def __init__(self):
        self.consumed = 0

    def check_access(self, _chat_id):
        return True, "trial"

    def status(self, _chat_id):
        return {"trial_left": 3}

    def consume_signal(self, _chat_id):
        self.consumed += 1
        return True, "trial"

    def should_send_paywall(self, _chat_id):
        return False


class _Bot:
    def __init__(self, effects):
        self.effects = list(effects)

    async def send_message(self, **_kwargs):
        effect = self.effects.pop(0)
        if isinstance(effect, Exception):
            raise effect
        return effect


class _Result:
    def __init__(self, row=None, rowcount=1):
        self._row = row
        self.rowcount = rowcount

    def fetchone(self):
        return self._row


class _LockedConnection:
    def __init__(self, rowcount):
        self.rowcount = rowcount
        self.rolled_back = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_args):
        self.rolled_back = exc_type is not None
        return False

    def execute(self, query, _params=None):
        if "FOR UPDATE" in query:
            return _Result((0, None, None, False))
        if "UPDATE subscriptions" in query:
            return _Result(rowcount=self.rowcount)
        return _Result()


async def _async_noop(_seconds):
    return None
