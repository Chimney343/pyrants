"""Core rules behavior tests for known implemented surfaces."""

from __future__ import annotations

from pathlib import Path
from random import Random

from engine.moves import (
    PlayCardMove,
    ResolveGenericChoiceMove,
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
    return build_initial_game_state(definition, ["p1", "p2"], Random(0), shuffle_seed=0)


def test_fire_elemental_power_mode_with_focus_draws_one_card() -> None:
    state = _base_state(seed=57).model_copy(deep=True)
    state.players["p1"].hand = ["fire_elemental", "blackguard"]
    state.players["p1"].deck = ["advance_scout"]
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.power = 0

    played = apply(state, PlayCardMove(player_id="p1", card_id="fire_elemental", hand_index=0))
    resolved = apply(
        played,
        ResolveGenericChoiceMove(player_id="p1", source_card_id="fire_elemental", option_id="option_1"),
    )

    assert resolved.resource_pool.power == 2
    assert len(resolved.players["p1"].hand) == 2



def test_fire_elemental_influence_mode_with_focus_draws_one_card() -> None:
    state = _base_state(seed=58).model_copy(deep=True)
    state.players["p1"].hand = ["fire_elemental", "blackguard"]
    state.players["p1"].deck = ["advance_scout"]
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.influence = 0

    played = apply(state, PlayCardMove(player_id="p1", card_id="fire_elemental", hand_index=0))
    resolved = apply(
        played,
        ResolveGenericChoiceMove(player_id="p1", source_card_id="fire_elemental", option_id="option_2"),
    )

    assert resolved.resource_pool.influence == 2
    assert len(resolved.players["p1"].hand) == 2



def test_fire_elemental_influence_mode_without_focus_does_not_draw() -> None:
    state = _base_state(seed=59).model_copy(deep=True)
    state.players["p1"].hand = ["fire_elemental"]
    state.players["p1"].deck = ["advance_scout"]
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.influence = 0

    played = apply(state, PlayCardMove(player_id="p1", card_id="fire_elemental", hand_index=0))
    resolved = apply(
        played,
        ResolveGenericChoiceMove(player_id="p1", source_card_id="fire_elemental", option_id="option_2"),
    )

    assert resolved.resource_pool.influence == 2
    assert len(resolved.players["p1"].hand) == 0



def test_earth_elemental_grants_one_influence_and_draws_with_ambition_focus() -> None:
    state = _base_state(seed=50).model_copy(deep=True)
    state.players["p1"].hand = ["earth_elemental", "black_earth_cultist"]
    state.players["p1"].deck = ["advance_scout"]
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.influence = 0
    state.board.nodes["site_gauntlgrym"].troop_slots = ["p2", None, None]
    state.board.nodes["site_gauntlgrym"].spies.add("p1")
    p2_barracks_before = state.players["p2"].barracks

    played = apply(state, PlayCardMove(player_id="p1", card_id="earth_elemental", hand_index=0))
    resolved = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="earth_elemental",
            selection={"unit_type": "troop", "node_id": "site_gauntlgrym", "target_slot_index": 0},
        ),
    )

    assert resolved.resource_pool.influence == 1
    assert len(resolved.players["p1"].hand) == 2
    assert resolved.players["p2"].barracks == p2_barracks_before + 1



def test_earth_elemental_does_not_draw_without_ambition_focus() -> None:
    state = _base_state(seed=51).model_copy(deep=True)
    state.players["p1"].hand = ["earth_elemental"]
    state.players["p1"].deck = ["advance_scout"]
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.influence = 0
    state.board.nodes["site_gauntlgrym"].troop_slots = ["p2", None, None]
    state.board.nodes["site_gauntlgrym"].spies.add("p1")

    played = apply(state, PlayCardMove(player_id="p1", card_id="earth_elemental", hand_index=0))
    resolved = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="earth_elemental",
            selection={"unit_type": "troop", "node_id": "site_gauntlgrym", "target_slot_index": 0},
        ),
    )

    assert resolved.resource_pool.influence == 1
    assert len(resolved.players["p1"].hand) == 0



def test_eternal_flame_cultist_focus_bonus_grants_two_power() -> None:
    state = _base_state(seed=53).model_copy(deep=True)
    state.players["p1"].hand = ["eternal_flame_cultist", "blackguard"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.power = 0
    state.board.nodes["site_gauntlgrym"].spies.add("p1")
    state.board.nodes["site_gauntlgrym"].troop_slots = ["p2", None, None]

    played = apply(state, PlayCardMove(player_id="p1", card_id="eternal_flame_cultist", hand_index=0))
    resolved = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="eternal_flame_cultist",
            selection={"target_node_id": "site_gauntlgrym", "target_slot_index": 0},
        ),
    )

    assert resolved.resource_pool.power == 2



def test_eternal_flame_cultist_without_focus_grants_no_bonus_power() -> None:
    state = _base_state(seed=54).model_copy(deep=True)
    state.players["p1"].hand = ["eternal_flame_cultist"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.power = 0
    state.board.nodes["site_gauntlgrym"].spies.add("p1")
    state.board.nodes["site_gauntlgrym"].troop_slots = ["p2", None, None]

    played = apply(state, PlayCardMove(player_id="p1", card_id="eternal_flame_cultist", hand_index=0))
    resolved = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="eternal_flame_cultist",
            selection={"target_node_id": "site_gauntlgrym", "target_slot_index": 0},
        ),
    )

    assert resolved.resource_pool.power == 0



def test_imix_gains_four_power_plus_two_with_malice_focus() -> None:
    state = _base_state(seed=70).model_copy(deep=True)
    state.players["p1"].hand = ["imix", "blackguard"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.power = 0

    resolved = apply(state, PlayCardMove(player_id="p1", card_id="imix", hand_index=0))

    assert resolved.resource_pool.power == 6



def test_imix_without_malice_focus_gains_only_four_power() -> None:
    state = _base_state(seed=71).model_copy(deep=True)
    state.players["p1"].hand = ["imix"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.power = 0

    resolved = apply(state, PlayCardMove(player_id="p1", card_id="imix", hand_index=0))

    assert resolved.resource_pool.power == 4



def test_howling_hatred_cultist_return_spy_mode_gains_three_influence_with_focus_bonus() -> None:
    state = _base_state(seed=68).model_copy(deep=True)
    state.players["p1"].hand = ["howling_hatred_cultist", "infiltrator"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.influence = 0
    state.resource_pool.power = 0
    state.board.nodes["site_gauntlgrym"].spies = {"p1"}

    played = apply(state, PlayCardMove(player_id="p1", card_id="howling_hatred_cultist", hand_index=0))
    option_two = apply(
        played,
        ResolveGenericChoiceMove(player_id="p1", source_card_id="howling_hatred_cultist", option_id="option_2"),
    )
    return_spy = next(
        move
        for move in legal_moves(option_two)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "howling_hatred_cultist"
        and move.selection.get("node_id") == "site_gauntlgrym"
        and move.selection.get("spy_owner_id") == "p1"
    )
    resolved = apply(option_two, return_spy)

    assert resolved.resource_pool.influence == 3
    assert resolved.resource_pool.power == 1



def test_howling_hatred_cultist_return_spy_mode_without_focus_gains_only_influence() -> None:
    state = _base_state(seed=69).model_copy(deep=True)
    state.players["p1"].hand = ["howling_hatred_cultist"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.influence = 0
    state.resource_pool.power = 0
    state.board.nodes["site_gauntlgrym"].spies = {"p1"}

    played = apply(state, PlayCardMove(player_id="p1", card_id="howling_hatred_cultist", hand_index=0))
    option_two = apply(
        played,
        ResolveGenericChoiceMove(player_id="p1", source_card_id="howling_hatred_cultist", option_id="option_2"),
    )
    return_spy = next(
        move
        for move in legal_moves(option_two)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "howling_hatred_cultist"
        and move.selection.get("node_id") == "site_gauntlgrym"
        and move.selection.get("spy_owner_id") == "p1"
    )
    resolved = apply(option_two, return_spy)

    assert resolved.resource_pool.influence == 3
    assert resolved.resource_pool.power == 0



def test_howling_hatred_cultist_return_spy_mode_only_allows_own_spies() -> None:
    state = _base_state(seed=167).model_copy(deep=True)
    state.players["p1"].hand = ["howling_hatred_cultist"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.power = 10
    state.board.nodes["site_gauntlgrym"].spies = {"p1", "p2"}
    state.board.nodes["site_gauntlgrym"].troop_slots = ["p1", None, None]

    played = apply(state, PlayCardMove(player_id="p1", card_id="howling_hatred_cultist", hand_index=0))
    option_two = apply(
        played,
        ResolveGenericChoiceMove(player_id="p1", source_card_id="howling_hatred_cultist", option_id="option_2"),
    )

    return_moves = [
        move
        for move in legal_moves(option_two)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "howling_hatred_cultist"
        and "spy_owner_id" in move.selection
    ]
    assert return_moves
    assert {str(move.selection["spy_owner_id"]) for move in return_moves} == {"p1"}



def test_black_earth_cultist_focus_bonus_grants_influence_when_ambition_focus_met() -> None:
    state = _base_state(seed=47).model_copy(deep=True)
    state.players["p1"].hand = ["black_earth_cultist", "ambassador"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.influence = 0

    played = apply(state, PlayCardMove(player_id="p1", card_id="black_earth_cultist", hand_index=0))

    assert played.resource_pool.influence == 2



def test_black_earth_cultist_focus_bonus_does_not_grant_influence_without_ambition_focus() -> None:
    state = _base_state(seed=53).model_copy(deep=True)
    state.players["p1"].hand = ["black_earth_cultist", "soldier"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.influence = 0

    played = apply(state, PlayCardMove(player_id="p1", card_id="black_earth_cultist", hand_index=0))

    assert played.resource_pool.influence == 0



def test_focus_requires_a_different_matching_aspect_card() -> None:
    cards = [
        {
            "card_id": "focus_power",
            "name": "Focus Power",
            "cost": 0,
            "aspect": "ambition",
            "deck_vp": 0,
            "inner_circle_vp": 0,
            "effect_key": "gain_power",
            "effect_payload": {"power": 2, "focus_required": True},
        },
        {
            "card_id": "ambition_helper",
            "name": "Ambition Helper",
            "cost": 0,
            "aspect": "ambition",
            "deck_vp": 0,
            "inner_circle_vp": 0,
            "effect_key": "noop",
            "effect_payload": {},
        },
    ]
    no_focus_state = _ability_state(cards, [{"card_id": "focus_power", "count": 1}])
    no_focus_state.players["p1"].hand = ["focus_power"]
    no_focus_state.players["p1"].deck = []

    without_focus = apply(
        no_focus_state,
        PlayCardMove(player_id="p1", card_id="focus_power", hand_index=0),
    )

    assert without_focus.resource_pool.power == 0

    with_focus_state = _ability_state(
        cards,
        [{"card_id": "focus_power", "count": 1}, {"card_id": "ambition_helper", "count": 1}],
    )
    with_focus_state.players["p1"].hand = ["focus_power", "ambition_helper"]
    with_focus_state.players["p1"].deck = []

    with_focus = apply(
        with_focus_state,
        PlayCardMove(player_id="p1", card_id="focus_power", hand_index=0),
    )

    assert with_focus.resource_pool.power == 2



def test_promoted_card_cannot_satisfy_focus() -> None:
    cards = [
        {
            "card_id": "focus_power",
            "name": "Focus Power",
            "cost": 0,
            "aspect": "ambition",
            "deck_vp": 0,
            "inner_circle_vp": 0,
            "effect_key": "gain_power",
            "effect_payload": {"power": 2, "focus_required": True},
        },
        {
            "card_id": "ambition_helper",
            "name": "Ambition Helper",
            "cost": 0,
            "aspect": "ambition",
            "deck_vp": 0,
            "inner_circle_vp": 0,
            "effect_key": "noop",
            "effect_payload": {},
        },
    ]
    state = _ability_state(cards, [{"card_id": "focus_power", "count": 1}, {"card_id": "ambition_helper", "count": 1}])
    state.players["p1"].hand = ["focus_power"]
    state.players["p1"].played_cards = []
    state.players["p1"].inner_circle = ["ambition_helper"]

    updated = apply(
        state,
        PlayCardMove(player_id="p1", card_id="focus_power", hand_index=0),
    )

    assert updated.resource_pool.power == 0



def test_yan_c_bin_focus_adds_a_second_spy_action() -> None:
    state = _base_state(seed=623).model_copy(deep=True)
    state.players["p1"].hand = ["yan_c_bin", "infiltrator"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.board.nodes["site_gauntlgrym"].troop_slots = ["p2", None, None]

    played = apply(state, PlayCardMove(player_id="p1", card_id="yan_c_bin", hand_index=0))
    place_spy_move = next(
        move
        for move in legal_moves(played)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "yan_c_bin"
        and move.selection.get("target_node_id") == "site_gauntlgrym"
    )
    after_spy = apply(played, place_spy_move)
    assassinate_move = next(
        move
        for move in legal_moves(after_spy)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "yan_c_bin"
        and move.selection.get("target_node_id") == "site_gauntlgrym"
        and move.selection.get("target_slot_index") == 0
    )
    after_assassinate = apply(after_spy, assassinate_move)

    focus_spy_moves = [
        move
        for move in legal_moves(after_assassinate)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "yan_c_bin"
        and "target_node_id" in move.selection
    ]

    assert focus_spy_moves

    resolved = apply(after_assassinate, focus_spy_moves[0])
    total_spies = sum(1 for node in resolved.board.nodes.values() if "p1" in node.spies)

    assert total_spies == 2


