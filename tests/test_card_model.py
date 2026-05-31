"""Tests for the richer per-card runtime model in the generated catalog."""

from __future__ import annotations

import json
from pathlib import Path

from engine.state import CardCatalog
from scripts.catalog_audit import (
    EXPECTED_UNSUPPORTED_GENERIC_ACTIONS,
    unsupported_generic_action_reason,
)

BASE_DIR = Path(__file__).resolve().parents[1]
CARD_PATH = BASE_DIR / "data" / "cards" / "catalog.json"
LEGACY_CARD_IDS: set[str] = set()


def _load_catalog_payload() -> dict[str, object]:
    return json.loads(CARD_PATH.read_text(encoding="utf-8"))


def test_generated_catalog_loads_with_structured_card_fields() -> None:
    catalog = CardCatalog.model_validate(_load_catalog_payload())

    generic_cards = [card for card in catalog.cards if card.card_id not in LEGACY_CARD_IDS]
    assert generic_cards

    for card in generic_cards:
        assert card.effect_key == "generic_card"
        assert card.rules_text
        assert card.execution_model is not None
        assert card.actions
        assert all(action.action_id for action in card.actions)
        assert card.state_contract.reads or card.state_contract.writes


def test_generated_generic_cards_do_not_depend_on_family_ids() -> None:
    payload = _load_catalog_payload()
    cards = payload["cards"]
    assert isinstance(cards, list)

    generic_cards = [card for card in cards if card["card_id"] not in LEGACY_CARD_IDS]
    assert generic_cards

    for card in generic_cards:
        assert card["effect_key"] == "generic_card"
        assert "family_id" not in card["effect_payload"]
        assert "rules_text" in card
        assert "execution_model" in card
        assert "actions" in card
        assert "global_conditions" in card
        assert "state_contract" in card


def test_generated_generic_cards_only_use_known_runtime_gap_signatures() -> None:
    payload = _load_catalog_payload()
    cards = payload["cards"]
    assert isinstance(cards, list)

    actual_unsupported: set[tuple[str, str, str]] = set()
    for card in cards:
        assert isinstance(card, dict)
        card_id = str(card["card_id"])
        if card_id in LEGACY_CARD_IDS:
            continue

        actions = card.get("actions", [])
        assert isinstance(actions, list)
        for action in actions:
            assert isinstance(action, dict)
            reason = unsupported_generic_action_reason(action)
            if reason is None:
                continue
            actual_unsupported.add((card_id, str(action["action_id"]), reason))

    assert actual_unsupported == EXPECTED_UNSUPPORTED_GENERIC_ACTIONS
