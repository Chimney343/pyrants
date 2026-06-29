"""Lock in Conjurer card behavior: place spy, or return spy + recruit up to 2 cards costing 3 or less."""

from __future__ import annotations

import json
from pathlib import Path

CATALOG_PATH = Path(__file__).resolve().parents[1] / "data" / "cards" / "catalog.json"


def test_conjurer_execution_model_modal_two_options() -> None:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    cards = catalog if isinstance(catalog, list) else catalog.get("cards", catalog)
    conjurer = next(c for c in cards if c.get("card_id") == "conjurer")

    em = conjurer["execution_model"]
    assert em["kind"] == "modal_choice"
    assert em["selection"] == "exactly_one"
    assert len(em["options"]) == 2

    assert "Choose exactly one mode" in conjurer["rules_text"]
    assert "place a spy" in conjurer["rules_text"]
    assert "return one of your spies" in conjurer["rules_text"]
    assert "recruit up to 2 cards" in conjurer["rules_text"]
    assert "cost 3 or less" in conjurer["rules_text"]


def test_conjurer_option_1_place_spy() -> None:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    cards = catalog if isinstance(catalog, list) else catalog.get("cards", catalog)
    conjurer = next(c for c in cards if c.get("card_id") == "conjurer")

    opt1 = conjurer["execution_model"]["options"][0]
    assert opt1["option_id"] == "option_1"
    actions = opt1["actions"]
    assert len(actions) == 1

    a = actions[0]
    assert a["op"] == "place_spy"
    assert a["target_scope"] == "board_site"
    assert a["timing"] == "immediate"
    assert a["optional"] is False


def test_conjurer_option_2_return_spy_then_recruit_up_to_2_cost_3_or_less() -> None:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    cards = catalog if isinstance(catalog, list) else catalog.get("cards", catalog)
    conjurer = next(c for c in cards if c.get("card_id") == "conjurer")

    opt2 = conjurer["execution_model"]["options"][1]
    assert opt2["option_id"] == "option_2"
    actions = opt2["actions"]
    assert len(actions) == 3, "option_2 should have return_spy + 2 optional recruit_card"

    ret = actions[0]
    assert ret["op"] == "return_spy"
    assert ret["target_scope"] == "board_site"
    assert ret["timing"] == "immediate"
    assert ret["optional"] is False

    rec1 = actions[1]
    assert rec1["op"] == "recruit_card"
    assert rec1["target_scope"] == "market"
    assert rec1["timing"] == "immediate"
    assert rec1["optional"] is True
    assert "max_cost_3" in rec1.get("filters", [])
    assert rec1.get("metadata", {}).get("max_cost") == 3

    rec2 = actions[2]
    assert rec2["op"] == "recruit_card"
    assert rec2["target_scope"] == "market"
    assert rec2["timing"] == "immediate"
    assert rec2["optional"] is True
    assert "max_cost_3" in rec2.get("filters", [])
    assert rec2.get("metadata", {}).get("max_cost") == 3


def test_conjurer_actions_array_matches_options() -> None:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    cards = catalog if isinstance(catalog, list) else catalog.get("cards", catalog)
    conjurer = next(c for c in cards if c.get("card_id") == "conjurer")

    actions = conjurer["actions"]
    action_ids = {a["action_id"] for a in actions}
    assert "option_1_action_1" in action_ids
    assert "option_2_action_1" in action_ids
    assert any(
        a["op"] == "recruit_card" and a["action_id"] == "option_2_action_2"
        for a in actions
    ), "actions array must include option_2_action_2 recruit_card"
    assert any(
        a["op"] == "recruit_card" and a["action_id"] == "option_2_action_3"
        for a in actions
    ), "actions array must include option_2_action_3 recruit_card"
