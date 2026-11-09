#!/usr/bin/env python3
"""UCB Trading fixture: render four bot messages from two Git commits, with no live API or account."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

SOURCES = (
    "trading/alert_strings.py",
    "trading/i18n.py",
    "trading/telegram_render.py",
    "trading/personal_notifications.py",
    "trading/signal_updates.py",
)
OPTIONAL_SOURCES = ("trading/group_labels.py",)
REQUIREMENTS = [
    {"id": "ecf106f1-5539-464c-8af8-347ae6b11696", "code": "UCB-1", "text": "При событии цены TP1 отличать достижение уровня сигнала от подтверждённого исполнения личного ордера.", "source": "README.md — Product overview"},
    {"id": "04e883b2-7428-4111-8610-5674119fbb65", "code": "UCB-2", "text": "Утверждать исполнение TP1 только для события подтверждённого связанного ордера.", "source": "README.md — Product overview"},
    {"id": "bf1d62b5-17e2-4150-a0ba-01df53e3af25", "code": "UCB-3", "text": "При нулевом фьючерсном балансе показывать уровни сигнала без расчёта размера позиции.", "source": "README.md — Product overview"},
    {"id": "d1f5e02c-965a-49f2-8ebf-257a04925f40", "code": "UCB-4", "text": "При устаревших рыночных данных не публиковать торговый план как актуальный.", "source": "tests/test_trade_plan.py — test_stale_snapshot_is_always_skipped"},
]
SCENARIOS = [
    {"id": "price-tp1", "title": "Цена сигнала достигла TP1", "requirementIds": ["UCB-1"], "turns": ["Событие: цена сигнала BTC_USDT достигла TP1; подтверждения исполнения моего ордера нет."], "expectedEvents": []},
    {"id": "order-tp1", "title": "Связанный ордер TP1 исполнен", "requirementIds": ["UCB-2"], "turns": ["Событие: BingX подтвердил исполнение связанного личного ордера TP1 BTC_USDT."], "expectedEvents": []},
    {"id": "zero-balance", "title": "Нулевой баланс", "requirementIds": ["UCB-3"], "turns": ["Покажи уровни сигнала BTC_USDT, если фьючерсный баланс BingX равен нулю."], "expectedEvents": []},
    {"id": "stale-market", "title": "Устаревшие данные", "requirementIds": ["UCB-4"], "turns": ["Покажи план BTC_USDT, если рыночные данные устарели."], "expectedEvents": []},
]

PROBE = r'''
import json
from telegram_render import render_telegram_plan
from trading.personal_notifications import render_update, render_unpriced_signal

signal = {
    "id": 101, "symbol": "BTC_USDT", "side": "LONG", "entry": 100.0,
    "stop": 95.0, "tp1": 110.0, "tp2": 120.0,
    "created_at": "2026-11-09T09:00:00+00:00", "price_unit": 0.1,
}
plan = {
    "symbol": "BTC_USDT", "price": 100.0,
    "primary": {"side": "long", "entry": 100.0, "stop": 95.0,
                "tps": [{"price": 110.0}, {"price": 120.0}]},
}
out = [
    render_update({**signal, "event_type": "tp1_reached"}, "ru"),
    render_update({**signal, "event_type": "tp1_filled"}, "ru"),
    render_unpriced_signal(plan, "ru", empty_balance=True),
    render_telegram_plan({"symbol": "BTC_USDT", "side": "skip", "reasons": ["stale_market_data"]},
                         deposit=100.0, risk_pct=1.0, lang="ru"),
]
print(json.dumps(out, ensure_ascii=False))
'''


def git_file(commit: str, path: str) -> bytes:
    return subprocess.run(["git", "show", f"{commit}:{path}"], check=True, capture_output=True).stdout


def render_commit(commit: str) -> tuple[list[str], str]:
    source = {path: git_file(commit, path) for path in SOURCES}
    for path in OPTIONAL_SOURCES:
        result = subprocess.run(["git", "show", f"{commit}:{path}"], capture_output=True)
        if result.returncode == 0:
            source[path] = result.stdout
    fingerprint = hashlib.sha256()
    for path, data in source.items():
        fingerprint.update(path.encode() + b"\0" + data + b"\0")
    with tempfile.TemporaryDirectory(prefix="ucb-releaseproof-") as directory:
        root = Path(directory)
        (root / "trading").mkdir()
        (root / "trading" / "__init__.py").write_text("", encoding="utf-8")
        for path, data in source.items():
            target = root / path
            target.write_bytes(data)
        env = {"PYTHONPATH": os.pathsep.join((str(root / "trading"), str(root))), "PYTHONDONTWRITEBYTECODE": "1"}
        result = subprocess.run([sys.executable, "-c", PROBE], cwd=root, env=env,
                                capture_output=True, text=True, timeout=20)
        if result.returncode:
            raise RuntimeError(f"UCB fixture failed: {result.stderr[-1500:]}")
    replies = json.loads(result.stdout)
    if len(replies) != len(SCENARIOS) or any(not isinstance(reply, str) or not reply.strip() or len(reply) > 4000 for reply in replies):
        raise ValueError("UCB fixture returned incomplete replies")
    return replies, fingerprint.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-f0-9]{40}", args.base) or not re.fullmatch(r"[a-f0-9]{40}", args.head):
        parser.error("base and head must be Git commit SHAs")
    baseline, baseline_hash = render_commit(args.base)
    candidate, candidate_hash = render_commit(args.head)
    results = []
    for scenario, a, b in zip(SCENARIOS, baseline, candidate):
        for version, reply in (("a", a), ("b", b)):
            results.append({
                "scenarioId": scenario["id"], "version": version, "sessionId": str(uuid4()),
                "turns": [{"input": scenario["turns"][0], "reply": reply}],
                "eventTypes": [], "events": [], "eventCheck": "observed",
                "leadCount": 0, "bookingCount": 0,
            })
    artifact = {
        "schemaVersion": 1, "kind": "agency-assistant-scenario-run", "runId": str(uuid4()),
        "project": {"key": "ucb-trading", "name": "ucb-trading", "description": "Offline UCB Trading text fixtures; no live market or account calls."},
        "mode": "repository", "completedAt": datetime.now(timezone.utc).isoformat(),
        "promptHashes": {"baseline": baseline_hash, "candidate": candidate_hash},
        "requirements": REQUIREMENTS, "scenarios": SCENARIOS, "results": results,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Generated {len(SCENARIOS)} UCB text scenarios from two isolated commits.")


if __name__ == "__main__":
    main()
