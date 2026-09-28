import pytest

from trading.user_input import (
    asks_for_plan_scan,
    bare_plan_symbol,
    is_deposit_input,
    is_greeting,
    parse_deposit_amount,
)


@pytest.mark.parametrize(
    "command",
    ["/start", "/help", "/plan", "/plan BTC_USDT", "/scan", "   /settings"],
)
def test_commands_are_not_consumed_by_deposit_onboarding(command):
    assert is_deposit_input(command) is False


@pytest.mark.parametrize("value", ["5000", "5 000", "5000,50", " 250.25 "])
def test_regular_text_reaches_deposit_onboarding(value):
    assert is_deposit_input(value) is True


@pytest.mark.parametrize(
    ("value", "expected"),
    [("5000", 5000.0), ("5 000", 5000.0), ("5000,50", 5000.5)],
)
def test_deposit_amount_is_normalized(value, expected):
    assert parse_deposit_amount(value) == expected


@pytest.mark.parametrize("value", ["0", "-1", "1000000001", "not-a-number", ""])
def test_invalid_deposit_amount_is_rejected(value):
    with pytest.raises((TypeError, ValueError)):
        parse_deposit_amount(value)


@pytest.mark.parametrize("value", ["hello", "Hello!", "привет", "добрый день", "hola", "bonjour", "hallo"])
def test_a_greeting_is_recognized_on_its_own(value):
    assert is_greeting(value) is True
    assert bare_plan_symbol(value) != "BTC"


@pytest.mark.parametrize("value", ["btc plan", "сканер", "/plan", ""])
def test_other_text_is_not_a_greeting(value):
    assert is_greeting(value) is False


@pytest.mark.parametrize("value", ["btc", "BTC_USDT", "eth/usdt", "sol-usdt"])
def test_a_bare_symbol_is_one_plan_target(value):
    assert bare_plan_symbol(value) in {"BTC", "ETH", "SOL"}


@pytest.mark.parametrize("value", ["btc eth", "hello there", "usdt", "сканер"])
def test_phrases_are_not_a_bare_symbol(value):
    assert bare_plan_symbol(value) is None


@pytest.mark.parametrize("value", ["сканер", "Запусти сканер", "scanner"])
def test_scanner_word_asks_for_the_plan_scan(value):
    assert asks_for_plan_scan(value) is True


@pytest.mark.parametrize("value", ["spike", "памп", "btc"])
def test_spike_words_do_not_ask_for_the_plan_scan(value):
    assert asks_for_plan_scan(value) is False
