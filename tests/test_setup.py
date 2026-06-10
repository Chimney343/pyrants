"""Setup and external-data validation tests."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from engine.state import build_initial_game_state
from game_setup.loaders import (
    build_game_definition_from_dicts,
    build_game_definition_from_files,
    create_game_state_from_files,
)

BASE_DIR = Path(__file__).resolve().parents[1]
BOARD_PATH = BASE_DIR / "data" / "boards" / "tyrants_of_the_underdark.json"
CARD_PATH = BASE_DIR / "data" / "cards" / "catalog.json"
SETUP_PATH = BASE_DIR / "data" / "decks" / "base_setup.json"


def test_build_game_definition_from_files() -> None:
    definition = build_game_definition_from_files(BOARD_PATH, CARD_PATH, SETUP_PATH)
    card_ids = {card.card_id for card in definition.catalog.cards}

    assert definition.definition_id == "base_game"
    assert definition.board.board_id == "Tyrants of the Underdark"
    assert len(definition.board.nodes) == 81
    assert {"starter_power", "starter_influence", "placeholder_assassinate"}.isdisjoint(card_ids)
    assert any(card.effect_key == "generic_card" for card in definition.catalog.cards)


def test_create_game_state_from_files() -> None:
    state = create_game_state_from_files(
        board_path=BOARD_PATH,
        card_path=CARD_PATH,
        setup_path=SETUP_PATH,
        player_ids=["p1", "p2"],
        seed=7,
    )

    assert state.current_player_id == "p1"
    assert state.phase.value == "main"
    assert len(state.players["p1"].hand) == 5
    assert len(state.players["p2"].hand) == 5
    assert len(state.market.row) == 6
    assert len(state.market.deck) == 4


def test_create_game_state_uses_noble_soldier_starter_deck() -> None:
    state = create_game_state_from_files(
        board_path=BOARD_PATH,
        card_path=CARD_PATH,
        setup_path=SETUP_PATH,
        player_ids=["p1", "p2"],
        seed=7,
    )

    for player_id in ["p1", "p2"]:
        player = state.players[player_id]
        starter_counts = Counter(player.hand + player.deck)
        assert starter_counts["noble"] == 7
        assert starter_counts["soldier"] == 3


def test_rejects_unknown_card_reference() -> None:
    board_data = {
        "board_id": "tiny",
        "nodes": [
            {
                "node_id": "site",
                "kind": "site",
                "adjacent_to": [],
                "troop_capacity": 2,
                "vp_value": 1,
            }
        ],
    }
    card_data = {"catalog_id": "cards", "version": "1.0.0", "cards": []}
    setup_data = {
        "setup_id": "setup",
        "starter_deck": {
            "deck_id": "starter",
            "entries": [{"card_id": "missing", "count": 1}],
        },
        "market_deck": {
            "deck_id": "market",
            "entries": [],
        },
        "market_row_size": 3,
    }

    with pytest.raises(ValueError, match="unknown card id"):
        build_game_definition_from_dicts(board_data, card_data, setup_data)


def test_create_game_state_rejects_duplicate_player_ids() -> None:
    with pytest.raises(ValueError, match="player ids must be unique"):
        create_game_state_from_files(
            board_path=BOARD_PATH,
            card_path=CARD_PATH,
            setup_path=SETUP_PATH,
            player_ids=["p1", "p1"],
            seed=7,
        )


def _minimal_card_and_setup_payload() -> tuple[dict[str, object], dict[str, object]]:
    card_data: dict[str, object] = {
        "catalog_id": "cards",
        "version": "1.0.0",
        "cards": [
            {
                "card_id": "starter_card",
                "name": "Starter Card",
                "cost": 0,
                "aspect": "none",
                "effect_key": "generic_card",
            }
        ],
    }
    setup_data: dict[str, object] = {
        "setup_id": "setup",
        "starter_deck": {
            "deck_id": "starter",
            "entries": [{"card_id": "starter_card", "count": 10}],
        },
        "market_deck": {
            "deck_id": "market",
            "entries": [{"card_id": "starter_card", "count": 6}],
        },
        "market_row_size": 6,
    }
    return card_data, setup_data


def test_build_initial_state_applies_initial_white_troop_slots() -> None:
    board_data: dict[str, object] = {
        "board_id": "tiny",
        "nodes": [
            {
                "node_id": "site_a",
                "kind": "site",
                "adjacent_to": ["route_ab"],
                "troop_capacity": 2,
                "vp_value": 1,
                "initial_troop_slots": ["white", None],
            },
            {
                "node_id": "route_ab",
                "kind": "route",
                "adjacent_to": ["site_a"],
                "troop_capacity": 1,
                "vp_value": 0,
                "initial_troop_slots": ["white"],
            },
        ],
    }
    card_data, setup_data = _minimal_card_and_setup_payload()

    definition = build_game_definition_from_dicts(board_data, card_data, setup_data)
    state = build_initial_game_state(definition, player_ids=["p1"], shuffle_seed=7)

    assert state.board.nodes["site_a"].troop_slots == ["white", None]
    assert state.board.nodes["route_ab"].troop_slots == ["white"]


def test_rejects_initial_troop_slot_length_mismatch() -> None:
    board_data: dict[str, object] = {
        "board_id": "tiny",
        "nodes": [
            {
                "node_id": "site_a",
                "kind": "site",
                "adjacent_to": [],
                "troop_capacity": 2,
                "vp_value": 1,
                "initial_troop_slots": ["white"],
            }
        ],
    }
    card_data, setup_data = _minimal_card_and_setup_payload()

    with pytest.raises(ValueError, match="initial_troop_slots length must match troop_capacity"):
        build_game_definition_from_dicts(board_data, card_data, setup_data)


def test_rejects_non_white_initial_troop_slots() -> None:
    board_data: dict[str, object] = {
        "board_id": "tiny",
        "nodes": [
            {
                "node_id": "site_a",
                "kind": "site",
                "adjacent_to": [],
                "troop_capacity": 2,
                "vp_value": 1,
                "initial_troop_slots": ["p1", None],
            }
        ],
    }
    card_data, setup_data = _minimal_card_and_setup_payload()

    with pytest.raises(ValueError, match="initial_troop_slots currently supports only 'white' occupants"):
        build_game_definition_from_dicts(board_data, card_data, setup_data)
