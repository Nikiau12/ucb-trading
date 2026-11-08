import json
from unittest.mock import patch

import pytest

from evaluation import group_history_expansion as expansion


def write(path, value):
    path.write_text(json.dumps(value))
    return path


def snapshot(symbol, group, *, volume=2_000_000, launch=None,
             flags=None, books=3, active=True, status="complete"):
    return {"symbol": symbol, "group": group, "active_contract": active,
            "data_status": status, "flags": flags or [], "books_valid": books,
            "quote_volume_24h_usdt": volume,
            "contract_launch_time_ms": launch or expansion.DATA_START * 1000 - 1}


def test_group_round_robin_covers_groups_before_second_instrument():
    rows = [snapshot("A_USDT", "ai", volume=5),
            snapshot("B_USDT", "ai", volume=10),
            snapshot("C_USDT", "l1", volume=1)]
    assert [row["symbol"] for row in expansion.round_robin_by_group(rows)] == [
        "B_USDT", "C_USDT", "A_USDT"]


def test_selection_is_predeclared_and_not_historical_liquidity_proof(tmp_path):
    rows = [snapshot("BTC_USDT", "core_btc"),
            snapshot("ONE_USDT", "l1"),
            snapshot("TWO_USDT", "l1", flags=["spread_above_10bps"]),
            snapshot("NEW_USDT", "meme", launch=expansion.DATA_START * 1000 + 1)]
    contracts = {"response": {"code": 0, "data": [
        {"symbol": row["symbol"].replace("_", "-"), "status": 1,
         "launchTime": row["contract_launch_time_ms"]} for row in rows]}}
    liquidity = write(tmp_path / "liquidity.json", rows)
    shortlist = write(tmp_path / "shortlist.json", {"selected": [
        {"symbol": "BTC_USDT", "group": "core_btc"}]})
    contracts_path = write(tmp_path / "contracts.json", contracts)
    fake_catalog = {"mapping": {row["symbol"]: row["group"] for row in rows},
                    "sha256": "catalog-hash"}
    with patch.object(expansion, "registry", return_value=fake_catalog):
        result = expansion.select_inputs(liquidity, shortlist, contracts_path)
    assert result["additional_count"] == 1
    assert [row["symbol"] for row in result["selected"]] == ["ONE_USDT"]
    assert result["historical_liquidity_verified"] is False
    assert result["historical_universe_point_in_time_verified"] is False
    reasons = {row["symbol"]: row["reason"] for row in result["excluded"]}
    assert reasons["BTC_USDT"] == "already_in_original_27"
    assert reasons["TWO_USDT"] == "current_liquidity_or_depth_flag"
    assert reasons["NEW_USDT"] == "contract_launched_after_history_start"


def test_changed_manifest_cannot_resume_into_same_capture_root(tmp_path):
    root = tmp_path / "capture"
    root.mkdir()
    write(root / "selection-manifest.json", {"version": "old"})
    with pytest.raises(ValueError, match="manifest changed"):
        expansion.collect({"version": "new", "selected": [{"symbol": "BTC_USDT"}]},
                          root, 1)
