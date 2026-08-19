"""Lock in Neogi card behavior: deploy 4 troops, end-of-turn random mass discard."""

from __future__ import annotations

from pathlib import Path

from game_setup.loaders import assemble_catalog_payload

CATALOG_PATH = Path(__file__).resolve().parents[1] / "data" / "cards"


def test_neogi_execution_model_deploys_four_and_random_mass_discard() -> None:
    catalog = assemble_catalog_payload(CATALOG_PATH)
    cards = catalog if isinstance(catalog, list) else catalog.get("cards", catalog)
    neogi = next(c for c in cards if c.get("card_id") == "neogi")

    actions = neogi["execution_model"]["actions"]
    deploy = actions[0]
    discard = actions[1]

    assert deploy["op"] == "deploy_troops"
    assert deploy["quantity"] == {"kind": "fixed", "value": 4}
    assert deploy["target_scope"] == "board_site"
    assert deploy["timing"] == "immediate"
    assert deploy["optional"] is False

    assert discard["op"] == "force_discard"
    assert discard["target_scope"] == "opponent"
    assert discard["timing"] == "immediate"
    assert discard["source_fragment"] == "end_of_turn_mass_discard"

    assert "Deploy 4 troops" in neogi["rules_text"]
    assert "random card" in neogi["rules_text"]
    assert "four" in neogi["notes"]
    assert "random" in neogi["notes"]
