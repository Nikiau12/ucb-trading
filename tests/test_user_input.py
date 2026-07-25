import pytest

from trading.user_input import is_deposit_input, parse_deposit_amount


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
