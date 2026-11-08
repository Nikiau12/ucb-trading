"""Isolated account/group/tracking tests. Exchange and Telegram traffic is mocked."""
import hashlib
import hmac
import json
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse, parse_qs, urlencode

import psycopg
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from psycopg.conninfo import make_conninfo
from psycopg.types.json import Jsonb

from miniapp import bingx_account as accounts, groups, tracking, universe, app
from miniapp.schema import apply_migrations
from trading import state
from trading.personal_notifications import render_update


def test_cipher_binds_credentials_to_the_user_and_needs_a_server_key(monkeypatch):
    monkeypatch.setenv('BINGX_CREDENTIALS_KEY', Fernet.generate_key().decode())
    encrypted = accounts.encrypt_credentials(10, 'private-api-key', 'private-api-secret')
    assert 'private-api' not in encrypted
    assert accounts.decrypt_credentials(10, encrypted) == ('private-api-key','private-api-secret')
    with pytest.raises(accounts.AccountUnavailable):
        accounts.decrypt_credentials(11, encrypted)
    monkeypatch.delenv('BINGX_CREDENTIALS_KEY')
    with pytest.raises(accounts.AccountUnavailable):
        accounts.encrypt_credentials(10, 'key', 'secret')


def test_private_client_signs_only_read_requests_and_never_follows_redirects():
    calls = []
    def get(url, **kwargs):
        calls.append((url,kwargs))
        return SimpleNamespace(status_code=200,json=lambda:{'code':0,'data':[{'asset':'USDT','balance':'0'}]})
    client = accounts.BingxAccountClient('key','secret',request_get=get,clock=lambda:100)
    assert client.balance() == 0
    url, kwargs = calls[0]
    unsigned, signature = url.split('?')[1].rsplit('&signature=',1)
    assert signature == hmac.new(b'secret',unsigned.encode(),hashlib.sha256).hexdigest()
    assert kwargs['headers'] == {'X-BX-APIKEY':'key'}
    assert kwargs['allow_redirects'] is False
    with pytest.raises(ValueError): client.get('/openApi/swap/v2/trade/closeAllPositions')


@pytest.mark.parametrize('value',['NaN','Infinity','-1',None])
def test_invalid_balance_is_never_used(value):
    get=lambda *_a,**_k: SimpleNamespace(status_code=200,json=lambda:{'code':0,'data':[{'asset':'USDT','balance':value}]})
    with pytest.raises(accounts.AccountUnavailable):
        accounts.BingxAccountClient('k','s',request_get=get).balance()


def test_private_errors_do_not_contain_credentials_or_signed_url():
    import requests
    def get(*_a,**_k): raise requests.ConnectionError('https://host?signature=TOP_SECRET')
    with pytest.raises(accounts.AccountUnavailable) as error:
        accounts.BingxAccountClient('key','secret',request_get=get).balance()
    assert 'TOP_SECRET' not in str(error.value)
    assert error.value.__suppress_context__


def test_group_union_all_none_and_unknown_are_distinct():
    assert groups.matches('BTC-USDT',['core_btc','core_eth','meme'])
    assert groups.matches('1000PEPE/USDT:USDT',['meme'])
    assert not groups.matches('SOL_USDT',['core_btc','core_eth'])
    assert groups.matches('UNKNOWN_USDT',None)
    assert not groups.matches('BTC_USDT',[])
    assert groups.matches('UNKNOWN_USDT',['ungrouped'])
    for bad in [['ALL'],['__proto__'],'core_btc',[None]]:
        with pytest.raises(ValueError): groups.validate_groups(bad)


def test_market_cap_is_global_top100_not_volume_or_next_available():
    coins=[{'symbol':'btc','market_cap_rank':1},{'symbol':'usdt','market_cap_rank':2},
           {'symbol':'pepe','market_cap_rank':99},{'symbol':'new','market_cap_rank':101}]
    contracts=[{'symbol':s,'status':1,'apiStateOpen':'true','volume':v} for s,v in [('BTC-USDT',1),('1000PEPE-USDT',2),('NEW-USDT',999999)]]
    assert universe.select_symbols(coins,contracts) == ['BTC_USDT','1000PEPE_USDT']


def test_expired_capitalization_cache_fails_closed(monkeypatch):
    monkeypatch.setattr(universe,'_symbols',['BTC_USDT'])
    monkeypatch.setattr(universe,'_checked_at',1)
    monkeypatch.setattr(universe,'_retry_at',999999)
    monkeypatch.setattr(universe.time,'monotonic',lambda:7*3600)
    with pytest.raises(universe.UniverseUnavailable): universe.top_symbols()


def _order(**changes):
    return {'orderId':'o1','symbol':'BTC-USDT','side':'SELL','positionSide':'LONG',
            'positionId':'p1','type':'TAKE_PROFIT_MARKET','status':'NEW','stopPrice':'110',
            'executedQty':'0', **changes}


def test_order_matching_rejects_ambiguity_wrong_direction_and_partial_fill():
    signal={'symbol':'BTC_USDT','side':'LONG','tp1':110,'price_unit':.01,'tp1_order_id':'o1'}
    position={'positionId':'p1'}
    assert tracking.matching_tp1_order(signal,[_order()],position)['orderId']=='o1'
    assert tracking.matching_tp1_order(signal,[_order(),_order(orderId='o2')],position) is None
    for order in [_order(side='BUY'),_order(stopPrice='111'),_order(positionId='p2'),_order(positionSide='BOTH')]:
        assert tracking.matching_tp1_order(signal,[order],position) is None
    assert not tracking.order_confirms_tp1(signal,_order(status='PARTIALLY_FILLED',executedQty='0.5'))
    assert not tracking.order_confirms_tp1(signal,_order(orderId='old',status='FILLED',executedQty='1'))
    assert tracking.order_confirms_tp1(signal,_order(status='FILLED',executedQty='1'))


def test_notification_distinguishes_price_from_user_fill_in_every_language():
    event={'id':1,'symbol':'BTC_USDT','side':'LONG','tp1':110,'created_at':datetime.now(timezone.utc)}
    for lang in ['en','ru','de','fr','es']:
        price=render_update({**event,'event_type':'tp1_reached'},lang)
        filled=render_update({**event,'event_type':'tp1_filled'},lang)
        assert price != filled
        assert 'BTC_USDT' in price and 'BTC_USDT' in filled
        assert 'BingX' in filled


@pytest.fixture
def database(monkeypatch):
    base=os.getenv('TEST_DATABASE_URL','')
    if not base: pytest.skip('Set TEST_DATABASE_URL to an isolated local PostgreSQL')
    parsed=urlparse(base)
    assert parsed.hostname in ('127.0.0.1','localhost') and parsed.path.startswith('/ucb_test')
    schema='personal_'+uuid.uuid4().hex
    with psycopg.connect(base,autocommit=True) as c:
        c.execute(psycopg.sql.SQL('CREATE SCHEMA {}').format(psycopg.sql.Identifier(schema)))
    dsn=make_conninfo(base, options='-csearch_path='+schema)
    apply_migrations(dsn)
    monkeypatch.setattr(state,'DATABASE_URL',dsn)
    monkeypatch.setattr(app,'DATABASE_URL',dsn)
    monkeypatch.setenv('BINGX_CREDENTIALS_KEY',Fernet.generate_key().decode())
    monkeypatch.setattr(app.universe,'top_symbols',lambda n=100:['BTC_USDT','ETH_USDT','SOL_USDT'])
    try:
        with psycopg.connect(dsn) as c:
            for uid in (1,2):
                c.execute('INSERT INTO user_profiles (telegram_user_id,deposit) VALUES (%s,400)',(uid,))
                c.execute('INSERT INTO subscriptions (telegram_user_id) VALUES (%s)',(uid,))
        yield dsn
    finally:
        with psycopg.connect(base,autocommit=True) as c:
            c.execute(psycopg.sql.SQL('DROP SCHEMA {} CASCADE').format(psycopg.sql.Identifier(schema)))


def seed_signal(dsn,symbol='BTC_USDT',users=(1,2),source='scanner'):
    with psycopg.connect(dsn) as c:
        sid=c.execute("INSERT INTO signals(symbol,side,confidence,price,entry,stop,tp1,tp2,price_unit,source) VALUES (%s,'LONG',0.8,100,100,90,110,120,0.01,%s) RETURNING id",(symbol,source)).fetchone()[0]
        c.execute("INSERT INTO signal_lifecycle(signal_id,status,entry_expires_at,holding_expires_at,entry_hit_at) VALUES (%s,'active',NOW()+INTERVAL '12 hours',NOW()+INTERVAL '7 days',NOW())",(sid,))
        for uid in users:c.execute('INSERT INTO user_signal_access(telegram_user_id,signal_id) VALUES (%s,%s)',(uid,sid))
    return sid


def test_migration_is_repeatable_and_preserves_settings(database):
    apply_migrations(database)
    with psycopg.connect(database) as c:
        assert c.execute('SELECT deposit,risk_pct,leverage,signal_groups FROM user_profiles WHERE telegram_user_id=1').fetchone()==(400,1,10,None)


def test_zero_balance_recipient_keeps_access_gate(database):
    with psycopg.connect(database) as c:
        c.execute("UPDATE user_profiles SET deposit=0 WHERE telegram_user_id IN (1,2)")
        c.execute("UPDATE subscriptions SET paid_until=NOW()+INTERVAL '1 day',trial_used=5 WHERE telegram_user_id=1")
        c.execute("UPDATE subscriptions SET paid_until=NULL,trial_used=5 WHERE telegram_user_id=2")
        c.execute("INSERT INTO user_profiles (telegram_user_id,deposit) VALUES (3,0)")
        c.execute("INSERT INTO subscriptions (telegram_user_id,trial_used) VALUES (3,0)")
    assert state.load_alert_recipients(5) == {'1','3'}


def test_local_recipient_selection_does_not_require_deposit(monkeypatch):
    monkeypatch.setattr(state,'_db_ready',lambda:False)
    monkeypatch.setattr(state,'_load',lambda:{'user_settings':{'1':{'deposit':0},'2':{'deposit':None}},'user_langs':{'3':'ru'}})
    assert state.load_alert_recipients(5) == {'1','2','3'}


def test_only_opted_in_user_gets_events_and_exit_cancels_pending(database):
    sid=seed_signal(database)
    with psycopg.connect(database) as c:tracking.set_tracking(c,1,sid,True)
    outcome=state.update_signal_lifecycle(sid,111)
    assert outcome['status']=='tp1_reached'
    pending=state.load_pending_signal_updates()
    assert [(p['telegram_user_id'],p['event_type']) for p in pending]==[(1,'tp1_reached')]
    with psycopg.connect(database) as c:tracking.set_tracking(c,1,sid,False)
    assert state.load_pending_signal_updates()==[]
    state.update_signal_lifecycle(sid,121)
    assert state.load_pending_signal_updates()==[]
    with psycopg.connect(database) as c:
        with pytest.raises(tracking.TrackingError,match='already_exited'):tracking.set_tracking(c,1,sid,True)


def test_access_is_not_a_tracking_subscription_and_other_user_cannot_exit(database):
    sid=seed_signal(database,users=(1,),source='manual')
    with psycopg.connect(database) as c:
        with pytest.raises(tracking.TrackingError):tracking.set_tracking(c,2,sid,True)
    state.update_signal_lifecycle(sid,111)
    state.grant_signal_access(1,sid)
    assert state.load_pending_signal_updates()==[]
    with psycopg.connect(database) as c:
        tracking.set_tracking(c,1,sid,True)
        with pytest.raises(tracking.TrackingError):tracking.set_tracking(c,2,sid,False)
    assert state.tracking_is_active(1,sid)


def test_multiple_coins_are_independent_and_duplicate_market_is_rejected(database):
    btc=seed_signal(database);eth=seed_signal(database,'ETH_USDT');other=seed_signal(database)
    with psycopg.connect(database) as c:
        tracking.set_tracking(c,1,btc,True);tracking.set_tracking(c,1,eth,True)
        assert tracking.set_tracking(c,1,btc,True)['tracking_status']=='active'
        with pytest.raises(tracking.TrackingError,match='market_already_tracked'):tracking.set_tracking(c,1,other,True)
        tracking.set_tracking(c,1,btc,False)
    assert state.tracking_is_active(1,eth)


class FakeAccount:
    balances={'key-user1':400.,'key-user2':900.}
    filled=False
    def __init__(self,key,secret):self.key=key
    def balance(self):return self.balances[self.key]
    def positions(self,symbol):return [{'symbol':'BTC-USDT','positionSide':'LONG','positionId':'p1','positionAmt':'1'}]
    def open_orders(self,symbol):return [_order()]
    def order(self,symbol,oid):return _order(status='FILLED' if self.filled else 'NEW',executedQty='1' if self.filled else '0')


def test_personal_balances_change_existing_sizing_without_cross_user_leak(database,monkeypatch):
    monkeypatch.setattr(accounts,'BingxAccountClient',FakeAccount)
    monkeypatch.setattr(FakeAccount,'balances',{'key-user1':400.,'key-user2':900.})
    with psycopg.connect(database) as c:
        accounts.connect_account(c,1,'key-user1','secret-one');accounts.connect_account(c,2,'key-user2','secret-two')
        encrypted=c.execute('SELECT credentials FROM bingx_accounts ORDER BY telegram_user_id').fetchall()
        assert 'secret-one' not in str(encrypted) and 'key-user1' not in str(encrypted)
    FakeAccount.balances['key-user1']=500.
    with psycopg.connect(database) as c:
        assert accounts.refresh_balance(c,1)==500.
        assert accounts.refresh_balance(c,2)==900.
    assert state.get_user_settings(1)['deposit']==500.
    assert state.get_user_settings(2)['deposit']==900.
    signal={'source':'scanner','side':'LONG','entry':100,'stop':90,'tp1':110,'tp2':120}
    a=app.attach_personal_sizing(signal,{'deposit':400,'risk_pct':1,'leverage':10})['sizing']
    b=app.attach_personal_sizing(signal,{'deposit':500,'risk_pct':1,'leverage':10})['sizing']
    assert b['position_usdt']==a['position_usdt']*1.25
    assert app.attach_personal_sizing(signal,{'balance_unavailable':True,'deposit':500})['sizing'] is None


def test_exchange_fill_is_confirmed_only_for_the_linked_user_once(database,monkeypatch):
    monkeypatch.setattr(accounts,'BingxAccountClient',FakeAccount)
    monkeypatch.setattr(FakeAccount,'filled',False)
    sid=seed_signal(database)
    with psycopg.connect(database) as c:
        accounts.connect_account(c,1,'key-user1','secret-one')
        tracking.set_tracking(c,1,sid,True)
        tracking.reconcile_user(c,1)
        assert c.execute('SELECT tp1_order_id,execution_state FROM user_trade_tracking').fetchone()==('o1','order_linked')
    assert state.load_pending_signal_updates()==[]
    FakeAccount.filled=True
    with psycopg.connect(database) as c:tracking.reconcile_user(c,1);tracking.reconcile_user(c,1)
    pending=state.load_pending_signal_updates()
    assert [(p['telegram_user_id'],p['event_type']) for p in pending]==[(1,'tp1_filled')]


def api_for(monkeypatch,uid):
    monkeypatch.setattr(app,'get_user',lambda _value:{'id':uid,'first_name':'Test'})
    monkeypatch.setattr(app,'require_database',lambda _value:None)
    return TestClient(app.app)


def test_group_preference_persists_and_filters_api_before_history_limit(database,monkeypatch):
    btc=seed_signal(database);eth=seed_signal(database,'ETH_USDT');sol=seed_signal(database,'SOL_USDT')
    for _ in range(35):seed_signal(database,'SOL_USDT')
    client=api_for(monkeypatch,1)
    result=client.patch('/api/settings',json={'signal_groups':['core_btc','core_eth','meme']})
    assert result.status_code==200
    with psycopg.connect(database) as c:assert groups.load_groups(c,1)==['core_btc','core_eth','meme']
    assert {s['id'] for s in client.get('/api/signals').json()}=={btc,eth}
    assert client.patch('/api/settings',json={'signal_groups':['bad']}).status_code==422
    assert client.patch('/api/settings',json={'signal_groups':[]}).status_code==200
    assert client.get('/api/signals').json()==[]
    assert client.patch('/api/settings',json={'signal_groups':None}).status_code==200
    assert client.get('/api/signals').json()


def test_active_trade_survives_group_change_and_capitalization_outage(database,monkeypatch):
    sid=seed_signal(database)
    client=api_for(monkeypatch,1)
    assert client.patch(f'/api/signals/{sid}/tracking',json={'active':True}).status_code==200
    client.patch('/api/settings',json={'signal_groups':[]})
    monkeypatch.setattr(app.universe,'top_symbols',lambda:(_ for _ in ()).throw(universe.UniverseUnavailable()))
    signals=client.get('/api/signals').json()
    assert len(signals)==1 and signals[0]['id']==sid and signals[0]['tracking_status']=='active'
    assert client.patch(f'/api/signals/{sid}/tracking',json={'active':False}).status_code==200
    assert client.get('/api/signals').json()==[]


def test_removed_sources_are_hidden_and_account_fields_are_not_echoed(database,monkeypatch):
    sid=seed_signal(database,source='spike')
    client=api_for(monkeypatch,1)
    assert client.get(f'/api/signals?signal_id={sid}').json()==[]
    assert client.patch(f'/api/signals/{sid}/tracking',json={'active':True}).status_code==409
    response=client.post('/api/bingx-account',json={'api_key':'SECRET_MUST_NOT_APPEAR'})
    assert response.status_code==422 and 'SECRET_MUST_NOT_APPEAR' not in response.text


def test_one_unavailable_coin_does_not_rollback_another_fill(database,monkeypatch):
    class PartialOutage(FakeAccount):
        def positions(self,symbol):
            if symbol=='ETH_USDT':raise accounts.AccountUnavailable('unavailable')
            return super().positions(symbol)
    monkeypatch.setattr(accounts,'BingxAccountClient',PartialOutage)
    monkeypatch.setattr(FakeAccount,'filled',True)
    btc=seed_signal(database);eth=seed_signal(database,'ETH_USDT')
    with psycopg.connect(database) as c:
        accounts.connect_account(c,1,'key-user1','secret-one')
        tracking.set_tracking(c,1,btc,True);tracking.set_tracking(c,1,eth,True)
        c.execute("UPDATE user_trade_tracking SET tp1_order_id='o1',position_id='p1' WHERE signal_id=%s",(btc,))
        tracking.reconcile_user(c,1)
    assert [(p['id'],p['event_type']) for p in state.load_pending_signal_updates()]==[(btc,'tp1_filled')]


def test_zero_balance_signal_has_no_reference_deposit_or_position_amount():
    from trading.personal_notifications import render_unpriced_signal
    plan={'symbol':'BTC_USDT','primary':{'side':'long','entry':100,'stop':90,'tps':[{'price':110},{'price':120}]}}
    text=render_unpriced_signal(plan,'ru',empty_balance=True)
    no_deposit=render_unpriced_signal(plan,'ru',no_deposit=True)
    assert 'равен нулю' in text and 'продолжают приходить' in text
    assert 'нулю или не указан' in no_deposit and 'продолжают приходить' in no_deposit
    assert '1000' not in text and '1000' not in no_deposit and 'TP2' in text


def test_new_account_and_tracking_routes_require_telegram_auth(monkeypatch):
    monkeypatch.setattr(app,'DEMO_MODE',False)
    monkeypatch.setattr(app,'DATABASE_URL','')
    client=TestClient(app.app)
    for method,path,payload in [('POST','/api/bingx-account',{'api_key':'dummy-key','api_secret':'dummy-secret'}),
                                ('DELETE','/api/bingx-account',None),
                                ('PATCH','/api/signals/1/tracking',{'active':True})]:
        response=client.request(method,path,json=payload)
        assert response.status_code==401
