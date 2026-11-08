"""Offline rollout contract: the same group rules reach storage and both UIs."""
import asyncio
import copy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from trading import group_plan as group
from trading import signal_updates as lifecycle
from trading import state
from trading.group_labels import strategy_notice
from trading.setup_text import render_setup, render_scan_card, render_alert_block
from trading.telegram_render import render_telegram_plan

AS_OF = 120000 * group.FOUR_HOURS
NOW = AS_OF + 300


def snapshot(symbol="BTC_USDT"):
    return {"symbol":symbol, "ts":NOW*1000, "exchange":"bingx",
            "contract":{"symbol":symbol,"active":True,"priceUnit":.01,
                        "contractSize":1,"volUnit":.001,"minVol":.001,
                        "maxLeverage":5,"raw":{"takerFeeRate":.0005}},
            "ticker":{"data":{"lastPrice":99,"quoteVolume":10_000_000}}}


def raw_plan(symbol="BTC_USDT", side="long"):
    config, mapping, _ = group.catalog()
    binding = config["groups"][mapping[symbol]]
    family = binding[side].replace("TR","T")
    return {"symbol":symbol,"group":mapping[symbol],"side":side,"family":family,
            "entry":100.,"stop":95. if side=="long" else 105.,
            "tp1":108. if side=="long" else 92.,"tp2":112. if side=="long" else 88.,
            "signal_time":AS_OF,"entry_expiry_seconds":8*3600,
            "max_holding_seconds":binding["max_hours"]*3600,"risk_price":5,
            "daily_regime":"up" if side=="long" else "down",
            "decision_key":symbol+side+str(AS_OF),"status":"technical_candidate_not_admitted"}


class PublicFixture:
    def __init__(self):
        self.mutation = None
        self.calls = []

    def futures_kline(self, symbol, interval, limit):
        self.calls.append((symbol, interval, limit))
        rows = [{"time":t,"open":99,"high":99.5,"low":98.5,"close":99,"volume":100}
                for t in range(AS_OF, NOW+1, 60)]
        if self.mutation=="gap": rows.pop(1)
        if self.mutation=="entry": rows[1]["high"]=100
        if self.mutation=="stop": rows[1]["low"]=95
        if self.mutation=="forming": rows.pop()
        return {"data": rows}

    def futures_ticker(self, symbol):
        return snapshot(symbol)["ticker"]

    def http_get(self, path, params):
        assert path=="/openApi/swap/v2/quote/depth"
        self.calls.append((path,params))
        return {"code":0, "data":{"T":NOW*1000,
                "bidsCoin":[[98.99,100000]], "asksCoin":[[99.01,100000]]}}


@pytest.fixture
def market(monkeypatch):
    public = PublicFixture()
    monkeypatch.setattr(group,"_public",lambda: public)
    monkeypatch.setattr(group,"history",lambda *_args: [])
    monkeypatch.setattr(group.time,"time",lambda: NOW)
    monkeypatch.setattr(group,"candidate",lambda symbol,side,*args,**kwargs:
                        raw_plan(symbol,side) if side=="long" else {"status":"no_setup","reason":"direction"})
    return public


@pytest.mark.parametrize("symbol", [next(s for s,g in group.catalog()[1].items() if g==key)
                                   for key in group.catalog()[0]["groups"]])
def test_every_group_routes_with_its_own_policy_and_contract_sizing(market, symbol):
    result = group.make_plan(snapshot(symbol),300,2,10,"cross",now=NOW)
    assert "primary" in result, result
    meta = result["strategy"]
    assert meta["group"]==group.catalog()[1][symbol]
    assert meta["family"]==raw_plan(symbol)["family"]
    assert meta["entry_type"]=="stop" and meta["timeframes"]==["4h","1d"]
    assert meta["experimental"] and not meta["profitability_validated"]
    assert meta["entry_expires_at"]==AS_OF+8*3600
    assert meta["max_holding_seconds"] in (72*3600,96*3600)
    assert result["primary"]["effective_leverage"]==5
    assert result["primary"]["risk_usdt"]<=6
    assert not group.plan_payload_errors(result)


@pytest.mark.parametrize("mutation", ["gap","entry","stop","forming"])
def test_used_or_unknown_trigger_path_is_never_published(market, mutation):
    market.mutation=mutation
    result=group.make_plan(snapshot(),300,2,10,"cross",now=NOW)
    assert result["side"]=="skip"
    assert result["strategy"]["experimental"]


@pytest.mark.parametrize("change", ["stale","wrong_contract","low_volume","fee","bad_deposit","unclassified"])
def test_invalid_or_unclassified_market_never_falls_back_to_generic_plan(market, change):
    data=snapshot()
    deposit=300
    if change=="stale": data["stale"]=True
    if change=="wrong_contract": data["contract"]["symbol"]="ETH_USDT"
    if change=="low_volume": data["ticker"]["data"]["quoteVolume"]=1
    if change=="fee": data["contract"]["raw"]["takerFeeRate"]=None
    if change=="bad_deposit": deposit=float("nan")
    if change=="unclassified": data["symbol"]="UNKNOWN_USDT"
    assert group.make_plan(data,deposit,2,10,"cross",now=NOW)["side"]=="skip"


def test_publication_rechecks_trigger_after_scanner_batch(market):
    plan=group.make_plan(snapshot(),300,2,10,"cross",now=NOW)
    assert group.prepare_for_publication(plan)["strategy"]["verified_at"]==NOW
    market.mutation="entry"
    assert group.prepare_for_publication(plan) is None


@pytest.mark.parametrize("side", ["LONG","SHORT"])
def test_stop_trigger_is_opt_in_and_legacy_trades_keep_limit_behavior(side):
    now=datetime.now(timezone.utc).replace(microsecond=0)
    sign=1 if side=="LONG" else -1
    old={"side":side,"entry":100,"stop":100-sign*5,"tp1":100+sign*8,"tp2":100+sign*12,
         "status":"waiting_entry","created_at":now-timedelta(minutes=5),
         "entry_expires_at":now+timedelta(hours=1),"max_holding_seconds":96*3600}
    new={**old,"strategy":{"entry_type":"stop"}}
    assert lifecycle.advance_lifecycle(old,100-sign,now)["status"]=="active"
    assert lifecycle.advance_lifecycle(new,100-sign,now)["status"]=="waiting_entry"
    assert lifecycle.advance_lifecycle(new,100,now)["status"]=="active"
    assert lifecycle.advance_lifecycle(new,old["stop"],now)["status"]=="cancelled_before_entry"
    active={**new,"status":"active"}
    assert lifecycle.advance_lifecycle(active,old["stop"],now)["status"]=="stopped"
    assert lifecycle.advance_lifecycle(active,old["tp1"],now)["status"]=="tp1_reached"
    assert lifecycle.advance_lifecycle({**new,"status":"tp1_reached"},100,now)["status"]=="stopped"
    assert lifecycle.advance_lifecycle(active,old["tp2"],now)["status"]=="tp2_reached"
    prices=[100-sign,100,old["tp1"],old["tp2"]]
    candles=[{"time":int(old["created_at"].timestamp())+i*60,"high":v,"low":v}
             for i,v in enumerate(prices)]
    replay=lifecycle.replay_lifecycle(new,candles,now,candle_seconds=60)
    assert replay["status"]=="tp2_reached" and replay["entry_hit_at"]
    ambiguous=[{"time":candles[0]["time"],"high":max(100,old["tp1"]),"low":min(100,old["tp1"])}]
    assert lifecycle.replay_lifecycle(new,ambiguous,now,candle_seconds=60)["status"]=="cancelled_before_entry"


@pytest.mark.parametrize("lang",["ru","en","de","fr","es"])
def test_disclosure_and_stop_entry_are_present_in_all_telegram_formats(market, lang):
    plan=group.make_plan(snapshot(),300,2,10,"cross",now=NOW)
    notice=strategy_notice(plan,lang)
    assert "STOP" in notice and "UTC" in notice
    for render in (render_setup,render_alert_block):
        text=render(plan,"BTC_USDT","LONG",1,300,2,5,lang=lang)
        assert notice in text and "100%" not in text
    assert notice in render_scan_card(plan,"BTC_USDT","LONG",300,2,5,lang=lang)
    legacy=copy.deepcopy(plan); legacy.pop("strategy")
    assert strategy_notice(legacy,lang)==""


@pytest.mark.parametrize("symbol", ["BTC_USDT", "AVAX_USDT", "1000SHIB_USDT"])
def test_scanner_and_manual_command_use_same_adapter(market, monkeypatch, symbol):
    import test_user_journey_e2e as journey
    bot=journey.bot
    assert bot.core_plan is group and bot.sc.core is group
    monkeypatch.setattr(bot.snap,"top_symbols_by_market_cap",lambda *_:[symbol])
    monkeypatch.setattr(bot.st,"user_accepts_symbol",lambda *_:True)
    monkeypatch.setattr(bot.snap,"build_group_snapshot",lambda symbol: snapshot(symbol))
    scan=bot.sc.scan_symbol(symbol,300,2,10,"cross")
    saved=[]
    async def access(_message): return "paid"
    monkeypatch.setattr(bot,"require_deposit",access)
    monkeypatch.setattr(bot,"gate_access",access)
    monkeypatch.setattr(bot,"is_admin",lambda *_:False)
    monkeypatch.setattr(bot,"get_lang",lambda *_:"ru")
    monkeypatch.setattr(bot.st,"get_user_settings",lambda *_:{"deposit":300,"risk_pct":2,"lev":10,"margin":"cross"})
    monkeypatch.setattr(bot.st,"save_signal",lambda plan,*args,**kwargs: saved.append(copy.deepcopy(plan)) or 700)
    monkeypatch.setattr(bot.st,"grant_signal_access",lambda *_:None)
    monkeypatch.setattr(bot,"debit_trial",lambda *_:None)
    monkeypatch.setattr(bot,"MINI_APP_URL","https://example.test")
    message=journey.FakeMessage("/plan " + symbol)
    asyncio.run(bot.cmd_plan(message))
    assert saved and saved[0]["strategy"]==scan["strategy"]
    assert "Экспериментальная стратегия" in message.replies[0].text
    assert "#700" in message.replies[0].text


def test_failed_group_persistence_does_not_issue_an_untracked_plan_or_debit_trial(market, monkeypatch):
    import test_user_journey_e2e as journey
    bot=journey.bot
    monkeypatch.setattr(bot.snap,"top_symbols_by_market_cap",lambda *_:["BTC_USDT"])
    monkeypatch.setattr(bot.st,"user_accepts_symbol",lambda *_:True)
    async def access(_message): return "paid"
    monkeypatch.setattr(bot,"require_deposit",access)
    monkeypatch.setattr(bot,"gate_access",access)
    monkeypatch.setattr(bot,"is_admin",lambda *_:False)
    monkeypatch.setattr(bot,"get_lang",lambda *_:"ru")
    monkeypatch.setattr(bot.st,"get_user_settings",lambda *_:{"deposit":300,"risk_pct":2,"lev":10,"margin":"cross"})
    monkeypatch.setattr(bot.snap,"build_group_snapshot",lambda symbol:snapshot(symbol))
    monkeypatch.setattr(bot.st,"save_signal",lambda *_args,**_kwargs:None)
    monkeypatch.setattr(bot,"debit_trial",lambda *_:pytest.fail("Unstored plan consumed trial"))
    message=journey.FakeMessage("/plan BTC_USDT")
    asyncio.run(bot.cmd_plan(message))
    assert "TP1:" not in message.replies[0].text
    assert "100%" not in message.replies[0].text


@pytest.mark.parametrize("lang,first,second", [
    ("ru", "Лонг: 1Д: рыночный режим не подходит", "Шорт: 4Ч: вход и уровни не прошли проверку"),
    ("en", "Long: 1D: market regime does not qualify", "Short: 4H: entry and levels did not qualify"),
    ("de", "Long: 1D: Marktregime passt nicht", "Short: 4H: Einstieg und Levels erfüllen die Regeln nicht"),
    ("fr", "Long: 1J : régime de marché non conforme", "Short: 4H : entrée et niveaux non validés"),
    ("es", "Long: 1D: el régimen de mercado no cumple las reglas", "Short: 4H: la entrada y los niveles no cumplen las reglas"),
])
def test_group_skip_explains_both_directions_without_raw_codes(lang, first, second):
    plan = {"symbol": "BTC_USDT", "side": "skip", "strategy": {"experimental": True},
            "reasons": ["group_no_setup:daily_regime/price_confirmation"],
            "direction_decisions": [
                {"side": "long", "status": "no_setup", "reason": "daily_regime"},
                {"side": "short", "status": "no_setup", "reason": "price_confirmation"},
            ]}
    text = render_telegram_plan(plan, deposit=300, risk_pct=2, lang=lang)
    assert first in text and second in text
    assert "daily_regime" not in text and "price_confirmation" not in text
    assert "TP1:" not in text


def test_group_skip_distinguishes_missing_history_and_unavailable_data():
    base = {"symbol": "BTC_USDT", "side": "skip", "strategy": {"experimental": True}}
    history = render_telegram_plan({**base, "reasons": ["group_data_rejected:insufficient_group_history"]},
                                   deposit=300, risk_pct=2, lang="ru")
    unavailable = render_telegram_plan({**base, "reasons": ["group_market_unavailable"]},
                                       deposit=300, risk_pct=2, lang="ru")
    assert "мало полной истории 4Ч/1Д" in history
    assert "Не удалось проверить рыночные данные" in unavailable
    assert "group_data" not in history and "group_market" not in unavailable


def test_group_engine_no_setup_reaches_telegram_with_specific_reasons(market, monkeypatch):
    def no_setup(_symbol, side, *_args, **_kwargs):
        return {"status": "no_setup", "reason": "daily_regime" if side == "long" else "price_confirmation"}

    monkeypatch.setattr(group, "candidate", no_setup)
    plan = group.make_plan(snapshot(), 300, 2, 10, "cross", now=NOW)
    assert plan["side"] == "skip"
    assert [item["status"] for item in plan["direction_decisions"]] == ["no_setup", "no_setup"]
    text = render_telegram_plan(plan, deposit=300, risk_pct=2, lang="ru")
    assert "Лонг: 1Д: рыночный режим не подходит" in text
    assert "Шорт: 4Ч: вход и уровни не прошли проверку" in text
    assert "Попробуй другую монету" not in text


def test_plan_command_explains_rejected_group_setup_without_saving_or_debiting(market, monkeypatch):
    import test_user_journey_e2e as journey

    bot = journey.bot
    monkeypatch.setattr(group, "candidate", lambda _symbol, side, *_args, **_kwargs:
                        {"status": "no_setup", "reason": "daily_regime" if side == "long" else "price_confirmation"})
    monkeypatch.setattr(bot.snap, "top_symbols_by_market_cap", lambda *_: ["BTC_USDT"])
    monkeypatch.setattr(bot.snap, "build_group_snapshot", lambda _symbol: snapshot())
    monkeypatch.setattr(bot.st, "user_accepts_symbol", lambda *_: True)
    monkeypatch.setattr(bot.st, "get_user_settings", lambda *_: {"deposit": 300, "risk_pct": 2, "lev": 10, "margin": "cross"})
    monkeypatch.setattr(bot.st, "save_signal", lambda *_args, **_kwargs: pytest.fail("Rejected setup saved"))
    monkeypatch.setattr(bot, "debit_trial", lambda *_args: pytest.fail("Rejected setup debited"))
    monkeypatch.setattr(bot, "require_deposit", lambda _message: asyncio.sleep(0, result=True))
    monkeypatch.setattr(bot, "gate_access", lambda _message: asyncio.sleep(0, result="paid"))
    monkeypatch.setattr(bot, "is_admin", lambda *_: False)
    monkeypatch.setattr(bot, "get_lang", lambda *_: "ru")
    monkeypatch.setattr(bot, "MINI_APP_URL", "https://example.test")
    message = journey.FakeMessage("/plan BTC_USDT")
    asyncio.run(bot.cmd_plan(message))
    assert "Лонг: 1Д: рыночный режим не подходит" in message.replies[0].text
    assert "Шорт: 4Ч: вход и уровни не прошли проверку" in message.replies[0].text
