import asyncio
import os
from types import SimpleNamespace

from fastapi.testclient import TestClient


# bot_mexc validates the token while constructing the aiogram Bot. No network
# request is made; the value is isolated to the test process.
os.environ["TELEGRAM_BOT_TOKEN"] = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"
os.environ["DATABASE_URL"] = ""

from core import config as bot_config  # noqa: E402

# Other test modules may have imported core.config before this file is
# collected. Update the already-cached module as well as the environment.
bot_config.TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
bot_config.DATABASE_URL = ""

import bot_mexc as bot  # noqa: E402
from core.access_manager import AccessManager  # noqa: E402
from miniapp import app as miniapp  # noqa: E402


class FakeSentMessage:
    def __init__(self, text):
        self.text = text
        self.edits = []

    async def edit_text(self, text, **_kwargs):
        self.text = text
        self.edits.append(text)


class FakeMessage:
    def __init__(self, text, user_id=4242):
        self.text = text
        self.chat = SimpleNamespace(id=user_id)
        self.from_user = SimpleNamespace(id=user_id)
        self.message_id = len(text)
        self.replies = []

    async def reply(self, text, **_kwargs):
        sent = FakeSentMessage(text)
        self.replies.append(sent)
        return sent


class FakeState:
    def __init__(self):
        self.value = None

    async def set_state(self, value):
        self.value = value

    async def clear(self):
        self.value = None


def _actionable_plan():
    return {
        "symbol": "BTC_USDT",
        "price": 100,
        "lev": 10,
        "margin": "cross",
        "trend": {},
        "levels": {},
        "primary": {
            "side": "long",
            "confidence": 0.8,
            "entry": 100,
            "stop": 95,
            "tps": [{"price": 105, "pct": 0.5}, {"price": 110, "pct": 0.5}],
            "qty": 0.6,
            "risk_usdt": 3,
            "margin_need": 6,
            "reasons": [],
        },
    }


def test_complete_new_user_trial_and_payment_journey(monkeypatch, tmp_path):
    settings = {"language": "en", "deposit": None, "risk_pct": 1.0, "lev": 10.0, "margin": "cross"}
    granted_signals = []
    manager = AccessManager(
        str(tmp_path / "access.json"),
        free_trial_signals=5,
        paid_access_hours=24 * 30,
        payment_address="TTestWallet",
        payment_amount="29.99",
        payment_network="TRC20",
    )
    manager.trial_cooldown_seconds = 0

    monkeypatch.setattr(bot, "access_manager", manager)
    monkeypatch.setattr(bot, "save_user", lambda _chat_id: True)
    monkeypatch.setattr(bot.st, "get_user_settings", lambda _user_id: dict(settings))
    monkeypatch.setattr(bot.st, "set_user_lang", lambda _user_id, value: settings.update(language=value))
    monkeypatch.setattr(bot.st, "set_user_setting", lambda _user_id, key, value: settings.update({key: value}))
    monkeypatch.setattr(bot.st, "save_signal", lambda *_args, **_kwargs: 77)
    monkeypatch.setattr(bot.st, "grant_signal_access", lambda user_id, signal_id: granted_signals.append((user_id, signal_id)))
    monkeypatch.setattr(bot.snap, "build_snapshot_with_fallback", lambda _symbol: {"symbol": "BTC_USDT"})
    monkeypatch.setattr(bot.core_plan, "make_plan", lambda *_args, **_kwargs: _actionable_plan())
    monkeypatch.setattr(bot, "render_telegram_plan", lambda *_args, **_kwargs: "EXECUTABLE SIGNAL")
    monkeypatch.setattr(bot, "is_admin", lambda _chat_id: False)
    monkeypatch.setattr(bot, "ADMIN_CHAT_IDS", set())
    monkeypatch.setattr(
        bot.payment_verifier,
        "verify",
        lambda tx_hash: {"ok": True, "tx_hash": tx_hash, "paid_amount": "29.99", "from": "TUser"},
    )

    async def journey():
        state = FakeState()
        start = FakeMessage("/start")
        await bot.cmd_start(start, state)
        assert state.value == bot.DepositSetup.waiting_for_amount
        assert start.replies

        deposit = FakeMessage("300")
        await bot.handle_deposit_amount(deposit, state)
        assert settings["deposit"] == 300.0
        assert state.value is None

        plan = FakeMessage("/plan BTC_USDT")
        await bot.cmd_plan(plan)
        assert any("EXECUTABLE SIGNAL" in message.text for message in plan.replies)
        assert manager.status("4242")["trial_left"] == 4
        assert granted_signals == [(4242, 77)]

        for _ in range(4):
            assert manager.consume_signal("4242")[0] is True
        assert manager.check_access("4242") == (False, "paywall")

        paid = FakeMessage("/paid " + "a" * 64)
        await bot.cmd_paid(paid)
        assert manager.status("4242")["has_paid_access"] is True
        assert manager.status("4242")["payment_claim"]["status"] == "approved"

        status = FakeMessage("/status")
        await bot.cmd_status(status)
        assert status.replies

    asyncio.run(journey())

    monkeypatch.setattr(miniapp, "DATABASE_URL", "")
    monkeypatch.setattr(miniapp, "BOT_TOKEN", "")
    monkeypatch.setattr(miniapp, "DEMO_MODE", True)
    with TestClient(miniapp.app) as client:
        assert client.get("/api/me").status_code == 200
        signals = client.get("/api/signals")
        assert signals.status_code == 200
        assert signals.json()[0]["sizing"]["tradable"] is True
