"""Core rules behavior tests for known implemented surfaces."""

from __future__ import annotations

from pathlib import Path

from engine.moves import (
    ActivateCardAbilityMove,
    DeclineCardAbilityMove,
    PlayCardMove,
)
from engine.rules import apply, legal_moves
from engine.state import build_initial_game_state
from game_setup.loaders import build_game_definition_from_dicts, create_game_state_from_files

BASE_DIR = Path(__file__).resolve().parents[1]
BOARD_PATH = BASE_DIR / "data" / "boards" / "tyrants_of_the_underdark.json"
CARD_PATH = BASE_DIR / "data" / "cards" / "catalog.json"
SETUP_PATH = BASE_DIR / "data" / "decks" / "base_setup.json"


def _base_state(seed: int = 11):
    return create_game_state_from_files(BOARD_PATH, CARD_PATH, SETUP_PATH, ["p1", "p2"], seed=seed)


def _ability_state(cards: list[dict[str, object]], starter_entries: list[dict[str, object]]) -> object:
    board_data = {
        "board_id": "ability_test_board",
        "nodes": [
            {
                "node_id": "site_a",
                "kind": "site",
                "adjacent_to": [],
                "troop_capacity": 3,
                "vp_value": 0,
                "initial_vp_tokens": 0,
            }
        ],
    }
    card_data = {"catalog_id": "ability_test_catalog", "version": "1.0.0", "cards": cards}
    setup_data = {
        "setup_id": "ability_test_setup",
        "starter_deck": {"deck_id": "starter", "entries": starter_entries},
        "market_deck": {"deck_id": "market", "entries": []},
        "market_row_size": 1,
    }

    definition = build_game_definition_from_dicts(board_data, card_data, setup_data, definition_id="ability_test")
    return build_initial_game_state(definition, ["p1", "p2"], shuffle_seed=0)


def test_paid_ability_must_be_activated_or_declined_before_playing_another_card() -> None:
    cards = [
        {
            "card_id": "paid_power",
            "name": "Paid Power",
            "cost": 0,
            "aspect": "none",
            "deck_vp": 0,
            "inner_circle_vp": 0,
            "effect_key": "noop",
            "effect_payload": {
                "paid_ability": {
                    "ability_key": "gain_power_ability",
                    "effect_key": "gain_power",
                    "effect_payload": {"power": 2},
                    "cost": {"power": 1},
                }
            },
        },
        {
            "card_id": "filler",
            "name": "Filler",
            "cost": 0,
            "aspect": "none",
            "deck_vp": 0,
            "inner_circle_vp": 0,
            "effect_key": "noop",
            "effect_payload": {},
        },
    ]
    state = _ability_state(cards, [{"card_id": "paid_power", "count": 1}, {"card_id": "filler", "count": 1}])
    state.players["p1"].hand = ["paid_power", "filler"]
    state.players["p1"].deck = []
    state.resource_pool.power = 1

    played = apply(
        state,
        PlayCardMove(player_id="p1", card_id="paid_power", hand_index=0),
    )

    assert played.pending_ability is not None
    assert all(not isinstance(move, PlayCardMove) for move in legal_moves(played))

    declined = apply(
        played,
        DeclineCardAbilityMove(
            player_id="p1",
            card_id="paid_power",
            ability_key="gain_power_ability",
        ),
    )

    assert declined.pending_ability is None
    assert any(isinstance(move, PlayCardMove) for move in legal_moves(declined))



def test_paid_ability_checks_costs_and_discards_before_effect() -> None:
    cards = [
        {
            "card_id": "paid_influence",
            "name": "Paid Influence",
            "cost": 0,
            "aspect": "none",
            "deck_vp": 0,
            "inner_circle_vp": 0,
            "effect_key": "noop",
            "effect_payload": {
                "paid_ability": {
                    "ability_key": "gain_influence_ability",
                    "effect_key": "gain_influence",
                    "effect_payload": {"influence": 2},
                    "cost": {"power": 1, "discard_count": 1},
                }
            },
        },
        {
            "card_id": "discard_me",
            "name": "Discard Me",
            "cost": 0,
            "aspect": "none",
            "deck_vp": 0,
            "inner_circle_vp": 0,
            "effect_key": "noop",
            "effect_payload": {},
        },
    ]
    state = _ability_state(cards, [{"card_id": "paid_influence", "count": 1}, {"card_id": "discard_me", "count": 1}])
    state.players["p1"].hand = ["paid_influence", "discard_me"]
    state.players["p1"].deck = []
    state.resource_pool.power = 1

    played = apply(
        state,
        PlayCardMove(player_id="p1", card_id="paid_influence", hand_index=0),
    )
    activated = apply(
        played,
        ActivateCardAbilityMove(
            player_id="p1",
            card_id="paid_influence",
            ability_key="gain_influence_ability",
            discard_hand_indices=[0],
        ),
    )

    assert activated.pending_ability is None
    assert activated.resource_pool.power == 0
    assert activated.resource_pool.influence == 2
    assert activated.players["p1"].discard_pile[-1] == "discard_me"
    assert activated.players["p1"].hand == []


