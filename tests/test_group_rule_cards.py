import json
from pathlib import Path
import re

from evaluation.sector_entries import load_entries


ROOT = Path(__file__).resolve().parents[1]
CARD_PATH = ROOT / "evaluation" / "group_rule_cards.v1.json"
DOCUMENT_PATH = ROOT / "docs" / "GROUP_STRATEGY_CARDS_2026-11-08.md"
PROPOSALS = {
    "T": ["trend_flag"],
    "B": ["breakout_confirmation"],
    "R": ["structure_range"],
    "TR": ["trend_flag", "structure_range"],
}


def test_all_16_cards_match_current_group_bindings_without_live_promotion():
    cards = json.loads(CARD_PATH.read_text())
    profile, _ = load_entries()
    assert cards["mode"] == "design_only_not_scanner_configuration"
    assert cards["live_eligible"] is False
    assert cards["automatic_promotion"] is False
    assert cards["profitability_established"] is False
    assert cards["weekly_target_is_quota"] is False
    assert cards["timeframes"] == ["1d", "4h"]
    assert cards["base_entry_version"] == profile["version"]
    assert set(cards["groups"]) == set(profile["groups"])
    assert set(cards["templates"]) == {
        "trend_flag", "breakout_confirmation", "structure_range"}
    assert cards["research_limit"]["new_entry_templates"] == 3
    assert cards["research_limit"]["parameter_search_on_exposed_history"] is False
    for group, binding in profile["groups"].items():
        for side in ("long", "short"):
            expected = (["breakout_confirmation", "trend_flag"]
                        if group == "privacy" else PROPOSALS[binding[side]])
            assert cards["groups"][group][side] == expected
        expected_btc = {"none": "none", "same": "hard_same",
                        "not_opposite": "hard_not_opposite"}[binding["btc"]]
        if group == "privacy":
            expected_btc = "context_only"
        assert cards["groups"][group]["btc_policy"] == expected_btc
        assert cards["groups"][group]["to_verify"]
        assert binding["max_hours"] <= cards["shared_proposal"]["maximum_holding_hours"]


def test_readable_card_has_every_group_and_required_trade_fields():
    content = DOCUMENT_PATH.read_text()
    sections = re.findall(r"(?ms)^### \d{2}\. .*? — `([a-z0-9_]+)`\n\n(.*?)(?=^### |^## |\Z)", content)
    profile, _ = load_entries()
    assert len(sections) == len(profile["groups"]) == 16
    assert {group for group, _ in sections} == set(profile["groups"])
    for _, body in sections:
        for field in ("1Д и 4Ч сейчас", "Проба", "Отмена, стоп, цели, срок"):
            assert field in body
