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
    assert config.get("dbname","").startswith("ucb_group_test")
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
