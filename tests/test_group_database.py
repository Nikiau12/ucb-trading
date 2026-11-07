"""Real Postgres integration. Only a disposable loopback test database is allowed."""
import asyncio
import copy
from datetime import datetime, timedelta, timezone
import os
from types import SimpleNamespace
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
import pytest

from miniapp import schema
from trading import state
from trading.group_plan import VERSION
from trading.notification_delivery import deliver_pending_signal_updates


@pytest.fixture
def database(monkeypatch):
    url=os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to a disposable loopback Postgres")
    config=conninfo_to_dict(url)
    assert config.get("host") in ("127.0.0.1","localhost")
    assert config.get("dbname","").startswith("ucb_test")
    name="group_test_"+uuid4().hex
    with psycopg.connect(url,autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(name)))
    scoped=make_conninfo(url, options="-c search_path="+name)
    try:
        with psycopg.connect(scoped) as conn:
            conn.execute("CREATE TABLE schema_migrations (version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ DEFAULT NOW())")
            for path in sorted(schema.MIGRATIONS_DIR.glob("*.sql")):
                if path.name.startswith("012_"):
                    continue
                for statement in schema._statements(path.read_text()):
                    conn.execute(statement)
                conn.execute("INSERT INTO schema_migrations(version) VALUES (%s)",(path.name,))
            legacy=conn.execute(
                """INSERT INTO signals(symbol,side,confidence,price,entry,stop,tp1,tp2)
                   VALUES ('BTC_USDT','LONG',0.8,99,100,95,108,112) RETURNING id"""
            ).fetchone()[0]
            conn.execute(
                """INSERT INTO signal_lifecycle(signal_id,status,entry_expires_at,max_holding_seconds)
                   VALUES (%s,'active',NOW()+INTERVAL '3 hours',1209600)""",(legacy,))
            before=conn.execute(
                """SELECT to_jsonb(s),to_jsonb(l) FROM signals s
                   JOIN signal_lifecycle l ON l.signal_id=s.id WHERE s.id=%s""",(legacy,)
            ).fetchone()
        schema.apply_migrations(scoped)
        schema.apply_migrations(scoped)  # Restart/multiple services: idempotent.
        with psycopg.connect(scoped) as conn:
            after=conn.execute(
                """SELECT to_jsonb(s)-'strategy_metadata',to_jsonb(l) FROM signals s
                   JOIN signal_lifecycle l ON l.signal_id=s.id WHERE s.id=%s""",(legacy,)
            ).fetchone()
        assert before==after, "An existing trade changed during migration"
        monkeypatch.setattr(state,"DATABASE_URL",scoped)
        yield scoped,legacy
    finally:
        with psycopg.connect(url,autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(name)))


def new_plan(symbol="ETH_USDT"):
    now=datetime.now(timezone.utc).timestamp()
    return {"symbol":symbol,"price":99,"trend":{"1d":"up","regime":"trend"},
            "primary":{"side":"long","confidence":1,"entry":100,"stop":95,
                       "tps":[{"price":108,"pct":.5},{"price":112,"pct":.5}],
                       "price_unit":.01,"contract_size":1,"vol_unit":.001,
                       "min_vol":.001,"max_leverage":10},
            "strategy":{"version":VERSION,"decision_key":uuid4().hex,"group":"core_eth",
                        "family":"T","experimental":True,"entry_type":"stop",
                        "entry_expires_at":now+3600,"max_holding_seconds":96*3600,
                        "verified_at":now}}


def test_new_signal_database_api_lifecycle_and_notification_roundtrip(database,monkeypatch):
    url,legacy=database
    plan=new_plan()
    signal_id=state.save_signal(plan,"ETH_USDT","LONG",1)
    assert signal_id and signal_id!=legacy
    state.grant_signal_access(4242,signal_id)
    from miniapp.tracking import set_tracking
    with psycopg.connect(url) as connection:
        set_tracking(connection,4242,signal_id,True)
    loaded=next(s for s in state.load_trackable_signals() if s["id"]==signal_id)
    assert loaded["strategy"]==plan["strategy"]
    assert loaded["max_holding_seconds"]==96*3600
    assert state.save_signal(plan,"ETH_USDT","LONG",1) is None
    assert state.save_signal(plan,"ETH_USDT","LONG",1,source="manual")==signal_id
    assert state.update_signal_lifecycle(signal_id,99)["status"]=="waiting_entry"
    assert state.update_signal_lifecycle(signal_id,100)["status"]=="active"
    assert state.update_signal_lifecycle(signal_id,108)["status"]=="tp1_reached"
    state.update_signal_lifecycle(signal_id,108)  # Same transition twice is one event.
    pending=state.load_pending_signal_updates()
    assert len(pending)==1 and pending[0]["strategy"]==plan["strategy"]
    from miniapp import app
    monkeypatch.setattr(app,"DATABASE_URL",url)
    monkeypatch.setattr(app,"get_user",lambda *_:{"id":4242})
    monkeypatch.setattr(app.universe,"top_symbols",lambda *_args,**_kwargs:["BTC_USDT","ETH_USDT","SOL_USDT"])
    api=app.signals(signal_id=signal_id,x_telegram_init_data="test")
    assert len(api)==1 and api[0]["strategy"]==plan["strategy"]
    assert api[0]["trade_status"]=="tp1_reached"
    sent=[]
    async def send(user,text,**kwargs):
        sent.append((user,text,kwargs))
        return True
    async def deliver():
        return await deliver_pending_signal_updates(
            asyncio.get_running_loop(),state=state,notifier=SimpleNamespace(send_message_to_user=send),
            language_for_user=lambda _:"ru",open_setup_keyboard=lambda signal_id,lang:f"signal_id={signal_id}")
    assert asyncio.run(deliver())==(1,1)
    assert "Экспериментальная стратегия" in sent[0][1]
    assert sent[0][2]["reply_markup"]==f"signal_id={signal_id}"
    assert asyncio.run(deliver())==(0,0)
    assert state.update_signal_lifecycle(signal_id,100)["status"]=="stopped"
    assert state.load_pending_signal_updates()[0]["event_type"]=="stop_reached"
    # Migration and new trades do not retrofit the old position's policy.
    with psycopg.connect(url) as conn:
        old=conn.execute(
            """SELECT s.strategy_metadata,s.entry,s.stop,s.tp1,s.tp2,l.status,l.max_holding_seconds
               FROM signals s JOIN signal_lifecycle l ON l.signal_id=s.id WHERE s.id=%s""",(legacy,)
        ).fetchone()
    assert old==(None,100,95,108,112,"active",1209600)


def test_new_rules_cannot_overlap_any_old_open_trade_and_cannot_reset_deadlines(database):
    _,legacy=database
    blocked=new_plan("BTC_USDT")
    assert state.save_signal(blocked,"BTC_USDT","LONG",1) is None
    assert state.save_signal(blocked,"BTC_USDT","LONG",1,source="manual") is None
    stale=new_plan()
    stale["strategy"]["verified_at"]-=61
    assert state.save_signal(stale,"ETH_USDT","LONG",1) is None
    expired=new_plan()
    expired["strategy"]["entry_expires_at"]-=7200
    assert state.save_signal(expired,"ETH_USDT","LONG",1) is None
    # Duplicate entrypoints serialize on the same symbol, leaving one signal.
    from concurrent.futures import ThreadPoolExecutor
    plans=[new_plan("SOL_USDT"),new_plan("SOL_USDT")]
    with ThreadPoolExecutor(2) as pool:
        result=list(pool.map(lambda p:state.save_signal(p,"SOL_USDT","LONG",1),plans))
    assert sum(s is not None for s in result)==1


def test_new_waiting_audit_preserves_stop_entry_and_reconstructs_tp2(database):
    _,_=database
    plan=new_plan()
    signal_id=state.save_signal(plan,"ETH_USDT","LONG",1)
    state.grant_signal_access(4242,signal_id)
    signal=next(s for s in state.load_trackable_signals() if s["id"]==signal_id)
    start=int(signal["created_at"].timestamp())+1
    candles=[{"time":start+i*60,"high":v,"low":v} for i,v in enumerate((99,100,108,112))]
    now=datetime.fromtimestamp(start+5*60,timezone.utc)
    result=state.audit_waiting_signal_lifecycle(signal_id,candles,checked_at=now)
    assert result["status"]=="tp2_reached"
    assert not state.load_pending_signal_updates()  # No stale instruction to move to BE after TP2.


def test_scheduled_group_signal_is_persisted_delivered_and_accessible_without_automatic_tracking(database,monkeypatch):
    import test_user_journey_e2e as journey
    from core import background_loops
    bot=journey.bot
    url,_=database
    plan=new_plan()
    class ScanClock(datetime):
        @classmethod
        def now(cls,tz=None):
            return datetime(2026,11,7,20,5,tzinfo=tz)
    sent=[]
    async def send(user,text,**kwargs):
        sent.append((user,text,kwargs))
        return True
    record=bot.st.record_runtime_health
    def finish(name,**kwargs):
        record(name,**kwargs)
        raise asyncio.CancelledError()
    monkeypatch.setattr(background_loops,"datetime",ScanClock)
    monkeypatch.setattr(bot,"_last_plan_1h_block",-1)
    monkeypatch.setattr(bot,"refresh_recipients",lambda:None)
    monkeypatch.setattr(bot.st,"DATABASE_URL",url)
    monkeypatch.setattr(bot.snap,"top_symbols_by_market_cap",lambda *_:["ETH_USDT"])
    monkeypatch.setattr(bot.sc,"scan_all",lambda *_args,**_kwargs:[plan])
    monkeypatch.setattr(bot.core_plan,"prepare_for_publication",lambda p:p)
    monkeypatch.setattr(bot.notifier,"active_users",{"4242"})
    monkeypatch.setattr(bot.notifier,"send_message_to_user",send)
    monkeypatch.setattr(bot.st,"record_runtime_health",finish)
    monkeypatch.setattr(bot,"get_lang",lambda *_:"ru")
    monkeypatch.setattr(bot,"MINI_APP_URL","https://example.test")
    asyncio.run(bot.plan_scanner_loop())
    assert len(sent)==1 and "Экспериментальная стратегия" in sent[0][1]
    assert "STOP" in sent[0][1]
    with psycopg.connect(url) as conn:
        row=conn.execute("SELECT id,strategy_metadata FROM signals WHERE symbol='ETH_USDT'").fetchone()
        assert row[1]==plan["strategy"]
        assert conn.execute("SELECT signal_id FROM user_signal_access WHERE telegram_user_id=4242").fetchone()[0]==row[0]
        assert conn.execute("SELECT count(*) FROM user_trade_tracking").fetchone()[0]==0
        assert conn.execute("SELECT symbol FROM signal_alert_state").fetchone()[0]=="ETH_USDT"
        health=conn.execute("SELECT details FROM runtime_health WHERE component='plan_scanner'").fetchone()[0]
        assert health["strategy_version"]==VERSION and health["alerts_sent"]==1
        journal=conn.execute("SELECT run_id,summary,decisions FROM scanner_runs").fetchone()
        assert journal[1]["outcomes"]["candidate"]==1
        assert journal[1]["signals_persisted"]==1
        assert journal[2][0]["symbol"]=="ETH_USDT"
        assert state.record_scan_run(journal[0],ScanClock.now(timezone.utc),journal[1],journal[2])
        assert conn.execute("SELECT count(*) FROM scanner_runs").fetchone()[0]==1


def test_scan_journal_report_is_versioned_and_read_only(database, monkeypatch, capsys):
    import json
    from trading.scan_diagnostics import main, summarize_scan
    url, _ = database
    for version in ("version-a", "version-b"):
        summary, decisions = summarize_scan(["BTC_USDT"], [{"symbol": "BTC_USDT", "side": "skip",
            "reasons": ["group_no_setup:daily_regime/daily_regime"]}], strategy_version=version)
        assert state.record_scan_run(version, datetime.now(timezone.utc), summary, decisions)
    assert state.record_scan_run("version-a-old-schema", datetime.now(timezone.utc),
                                 {**summary, "strategy_version": "version-a", "schema_version": 1}, decisions)
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setattr("sys.argv", ["scan_diagnostics", "--hours", "24"])
    main()
    report = json.loads(capsys.readouterr().out)
    assert report["unit"] == "scanner_attempts_not_trades"
    assert {r["strategy_version"] for r in report["versions"]} == {"version-a", "version-b"}
    assert {r["diagnostics_schema_version"] for r in report["versions"]} == {1, 2}
    assert len(report["versions"]) == 3
    assert all(r["runs"] == 1 and r["outcomes"]["no_setup"] == 1 for r in report["versions"])
    with psycopg.connect(url) as conn:
        assert conn.execute("SELECT count(*) FROM scanner_runs").fetchone()[0] == 3
        assert conn.execute("SELECT count(*) FROM signals").fetchone()[0] == 1  # Only legacy fixture.


def test_outcome_cli_reads_only_new_strategy_lifecycle(database, monkeypatch, capsys):
    import json
    from trading.scan_diagnostics import main
    url, legacy_id = database
    with psycopg.connect(url) as conn:
        for symbol, side, group, version, status, entry, tp1, tp2 in (
            ("AVAX_USDT", "LONG", "l1", "v1", "stopped", True, False, False),
            ("NEAR_USDT", "SHORT", "l1", "v2", "tp2_reached", True, True, True),
            ("PAXG_USDT", "LONG", "rwa", "v1", "cancelled_before_entry", False, False, False),
        ):
            meta = {"version": version, "catalog_version": "catalog-2", "group": group}
            signal_id = conn.execute("""INSERT INTO signals(symbol,side,confidence,strategy_metadata)
                VALUES (%s,%s,0.8,%s::jsonb) RETURNING id""",
                (symbol, side, json.dumps(meta))).fetchone()[0]
            conn.execute("""INSERT INTO signal_lifecycle
                (signal_id,status,entry_expires_at,entry_hit_at,tp1_hit_at,tp2_hit_at)
                VALUES (%s,%s,NOW()+INTERVAL '1 hour',
                        CASE WHEN %s THEN NOW() ELSE NULL END,
                        CASE WHEN %s THEN NOW() ELSE NULL END,
                        CASE WHEN %s THEN NOW() ELSE NULL END)""",
                (signal_id, status, entry, tp1, tp2))
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setattr("sys.argv", ["scan_diagnostics", "--outcomes", "--hours", "24"])
    main()
    report = json.loads(capsys.readouterr().out)
    assert report["overall"]["signals"] == 3 and report["overall"]["entered"] == 2
    assert report["overall"]["buckets"] == {
        "cancelled_before_entry": 1, "stop_before_tp1_model": 1, "tp2_model": 1,
    }
    assert {r["strategy_version"] for r in report["by_group_direction_version"]} == {"v1", "v2"}
    with psycopg.connect(url) as conn:
        assert conn.execute("SELECT status FROM signal_lifecycle WHERE signal_id=%s", (legacy_id,)).fetchone()[0] == "active"
        assert conn.execute("SELECT count(*) FROM signals").fetchone()[0] == 4


def test_group_shadow_sync_is_per_signal_idempotent_and_read_only_to_trades(database, monkeypatch):
    from trading import group_shadow as shadow
    from trading.group_catalog import registry
    url, legacy_id = database
    plan = new_plan()
    plan["strategy"]["catalog_version"] = registry()["version"]
    plan["strategy"]["execution_checks"] = {"public_taker_fee": .0005}
    signal_id = state.save_signal(plan, "ETH_USDT", "LONG", 1)
    first = shadow.sync_pending(database_url=url)
    assert first["examined"] == 1 and first["complete"] == 0
    with psycopg.connect(url) as conn:
        record = conn.execute("""SELECT outcome,net_r FROM group_shadow_results
            WHERE signal_id=%s""", (signal_id,)).fetchone()
        assert record == ("awaiting_entry", None)
        assert conn.execute("SELECT count(*) FROM group_shadow_results WHERE signal_id=%s", (legacy_id,)).fetchone()[0] == 0
    assert state.update_signal_lifecycle(signal_id, 100)["status"] == "active"
    assert state.update_signal_lifecycle(signal_id, 108)["status"] == "tp1_reached"
    assert state.update_signal_lifecycle(signal_id, 100)["status"] == "stopped"
    stale_report = shadow.load_report(database_url=url)
    stale_group = next(r for r in stale_report["rows"] if r["group"] == "core_eth"
                       and r["side"] == "long" and r["catalog_version"] == registry()["version"])
    assert stale_group["outcomes"] == {"tp1_then_be": 1}
    assert stale_group["closed_entered"] == stale_group["not_yet_synced"] == 1
    assert stale_group["complete_net"] == 0 and stale_group["net_r_mean"] is None
    monkeypatch.setattr(shadow, "funding_history", lambda *_args, **_kwargs: ([], True))
    completed = shadow.sync_pending(database_url=url)
    assert completed["examined"] == completed["complete"] == 1
    assert shadow.sync_pending(database_url=url)["examined"] == 0
    with psycopg.connect(url) as conn:
        before = conn.execute("""SELECT outcome,cost_status,gross_r,net_r,lifecycle_status
            FROM group_shadow_results WHERE signal_id=%s""", (signal_id,)).fetchone()
        assert before[0:2] == ("tp1_then_be", "complete")
        assert float(before[2]) == pytest.approx(.8) and float(before[3]) < .8
        assert before[4] == "stopped"
        assert conn.execute("SELECT count(*) FROM group_shadow_results WHERE signal_id=%s", (signal_id,)).fetchone()[0] == 1
        assert conn.execute("SELECT status FROM signal_lifecycle WHERE signal_id=%s", (legacy_id,)).fetchone()[0] == "active"
        assert conn.execute("SELECT count(*) FROM user_signal_access").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM signal_update_deliveries").fetchone()[0] == 0
    report = shadow.load_report(database_url=url)
    selected = next(r for r in report["rows"] if r["group"] == "core_eth" and r["side"] == "long"
                    and r["catalog_version"] == registry()["version"])
    assert selected["signals"] == selected["entered"] == selected["complete_net"] == 1
    assert selected["outcomes"] == {"tp1_then_be": 1}
    assert selected["sample_status"] == "insufficient_data"


def test_group_shadow_missing_funding_retries_without_guessing_zero(database, monkeypatch):
    from trading import group_shadow as shadow
    url, _ = database
    plan = new_plan()
    plan["strategy"]["execution_checks"] = {"public_taker_fee": .0005}
    signal_id = state.save_signal(plan, "ETH_USDT", "LONG", 1)
    state.update_signal_lifecycle(signal_id, 100)
    state.update_signal_lifecycle(signal_id, 95)
    monkeypatch.setattr(shadow, "funding_history", lambda *_args, **_kwargs: ([], False))
    assert shadow.sync_pending(database_url=url)["pending_costs"] == 1
    with psycopg.connect(url) as conn:
        row = conn.execute("SELECT cost_status,net_r FROM group_shadow_results WHERE signal_id=%s", (signal_id,)).fetchone()
        assert row == ("pending_funding_history", None)
        conn.execute("UPDATE group_shadow_results SET retry_after=NOW()-INTERVAL '1 second' WHERE signal_id=%s", (signal_id,))
    monkeypatch.setattr(shadow, "funding_history", lambda *_args, **_kwargs: ([], True))
    assert shadow.sync_pending(database_url=url)["complete"] == 1
    with psycopg.connect(url) as conn:
        row = conn.execute("SELECT cost_status,net_r FROM group_shadow_results WHERE signal_id=%s", (signal_id,)).fetchone()
        assert row[0] == "complete" and row[1] is not None


def test_group_shadow_cli_reports_all_groups_without_writing(database, monkeypatch, capsys):
    from trading import group_shadow as shadow
    url, legacy_id = database
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setattr("sys.argv", ["group_shadow", "--days", "30", "--format", "markdown"])
    with psycopg.connect(url) as conn:
        before = conn.execute("SELECT count(*) FROM group_shadow_results").fetchone()[0]
    shadow.main()
    text = capsys.readouterr().out
    assert "Стратегия group-rules-v1" in text
    assert "core_btc | long | 0" in text
    assert "недостаточно данных" in text
    with psycopg.connect(url) as conn:
        assert conn.execute("SELECT count(*) FROM group_shadow_results").fetchone()[0] == before
        assert conn.execute("SELECT status FROM signal_lifecycle WHERE signal_id=%s", (legacy_id,)).fetchone()[0] == "active"
