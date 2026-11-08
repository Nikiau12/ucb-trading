import json

import pytest

from evaluation.group_expansion_scan import contract_ticks


def test_current_contract_precision_is_diagnostic_only(tmp_path):
    path = tmp_path / "contracts.json"
    path.write_text(json.dumps({"response": {"code": 0, "data": [
        {"symbol": "BTC-USDT", "status": 1, "pricePrecision": 1},
        {"symbol": "OP-USDT", "status": 1, "pricePrecision": 4},
    ]}}))
    assert contract_ticks(path, ["BTC_USDT", "OP_USDT"]) == {
        "BTC_USDT": .1, "OP_USDT": .0001}


@pytest.mark.parametrize("status,precision", [(0, 2), (1, -1), (1, "2"), (1, 19)])
def test_invalid_current_contract_cannot_be_screened(tmp_path, status, precision):
    path = tmp_path / "contracts.json"
    path.write_text(json.dumps({"response": {"code": 0, "data": [
        {"symbol": "OP-USDT", "status": status, "pricePrecision": precision},
    ]}}))
    with pytest.raises(ValueError, match="Invalid current contract tick"):
        contract_ticks(path, ["OP_USDT"])
