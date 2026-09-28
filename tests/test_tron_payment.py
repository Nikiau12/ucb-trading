import time

from core.tron_payment import TronPaymentVerifier, USDT_TRC20_CONTRACT


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        return None

    def json(self):
        return {"data": self._data}


def _transfer(tx_hash, wallet, value="29990000"):
    return {
        "transaction_id": tx_hash,
        "to": wallet,
        "from": "TFromWallet",
        "value": value,
        "block_timestamp": int(time.time() * 1000),
        "token_info": {
            "address": USDT_TRC20_CONTRACT,
            "decimals": 6,
        },
    }


def test_invalid_transaction_hash_is_rejected_without_network_call(monkeypatch):
    verifier = TronPaymentVerifier("TReceivingWallet", "29.99")

    def unexpected_request(*args, **kwargs):
        raise AssertionError("Network must not be called for an invalid hash")

    monkeypatch.setattr("core.tron_payment.requests.get", unexpected_request)

    assert verifier.verify("not-a-hash") == {"ok": False, "reason": "invalid_hash"}


def test_confirmed_usdt_transfer_activates_verification(monkeypatch):
    wallet = "TReceivingWallet"
    tx_hash = "a" * 64
    verifier = TronPaymentVerifier(wallet, "29.99")
    monkeypatch.setattr(
        "core.tron_payment.requests.get",
        lambda *args, **kwargs: FakeResponse([_transfer(tx_hash, wallet)]),
    )

    result = verifier.verify(tx_hash)

    assert result["ok"] is True
    assert result["paid_amount"] == "29.99"
    assert result["tx_hash"] == tx_hash


def test_transfer_to_wrong_wallet_is_rejected(monkeypatch):
    tx_hash = "b" * 64
    verifier = TronPaymentVerifier("TExpectedWallet", "29.99")
    monkeypatch.setattr(
        "core.tron_payment.requests.get",
        lambda *args, **kwargs: FakeResponse(
            [_transfer(tx_hash, "TDifferentWallet")]
        ),
    )

    assert verifier.verify(tx_hash) == {"ok": False, "reason": "wrong_recipient"}


def test_underpayment_is_rejected(monkeypatch):
    wallet = "TReceivingWallet"
    tx_hash = "c" * 64
    verifier = TronPaymentVerifier(wallet, "29.99")
    monkeypatch.setattr(
        "core.tron_payment.requests.get",
        lambda *args, **kwargs: FakeResponse(
            [_transfer(tx_hash, wallet, value="10000000")]
        ),
    )

    result = verifier.verify(tx_hash)

    assert result["ok"] is False
    assert result["reason"] == "amount_too_low"
    assert result["paid_amount"] == "10"


def test_old_transaction_cannot_activate_access(monkeypatch):
    wallet = "TReceivingWallet"
    tx_hash = "d" * 64
    transfer = _transfer(tx_hash, wallet)
    transfer["block_timestamp"] = int((time.time() - 73 * 60 * 60) * 1000)
    verifier = TronPaymentVerifier(wallet, "29.99", max_age_hours=72)
    monkeypatch.setattr(
        "core.tron_payment.requests.get",
        lambda *args, **kwargs: FakeResponse([transfer]),
    )

    assert verifier.verify(tx_hash) == {"ok": False, "reason": "transaction_expired"}
