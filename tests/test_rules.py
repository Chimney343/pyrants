"""Core rules behavior tests for known implemented surfaces."""

from __future__ import annotations

from pathlib import Path
from random import Random

import pytest

from engine.errors import IllegalMoveError
from engine.moves import (
    ActivateCardAbilityMove,
    AssassinateMove,
    DeclineCardAbilityMove,
    DeployMove,
    EndMainPhaseMove,
    PlayCardMove,
    PromoteCardMove,
    RecruitMove,
    ResolveGenericChoiceMove,
    ReturnSpyMove,
    SkipPromoteMove,
)
from engine.rules import _action_requires_selection, apply, has_presence, legal_moves
from engine.state import PendingPromotionState, TurnPhase, build_initial_game_state
from game_setup.loaders import build_game_definition_from_dicts, create_game_state_from_files

BASE_DIR = Path(__file__).resolve().parents[1]
BOARD_PATH = BASE_DIR / "data" / "boards" / "base_game.json"
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
                "control_vp": 0,
                "initial_vp_tokens": 0,
            }
        ],
    }
    card_data = {"catalog_id": "ability_test_catalog", "cards": cards}
    setup_data = {
        "setup_id": "ability_test_setup",
        "starter_deck": {"deck_id": "starter", "entries": starter_entries},
        "market_deck": {"deck_id": "market", "entries": []},
        "market_row_size": 1,
    }

    definition = build_game_definition_from_dicts(board_data, card_data, setup_data, definition_id="ability_test")
    return build_initial_game_state(definition, ["p1", "p2"], Random(0), shuffle_seed=0)


def test_play_card_moves_card_to_played_and_grants_resources() -> None:
    state = _base_state(seed=13)
    player = state.players[state.current_player_id]
    card_id = player.hand[0]
    hand_size_before = len(player.hand)
    played_count_before = player.played_cards.count(card_id)

    before_power = state.resource_pool.power
    before_influence = state.resource_pool.influence

    updated = apply(
        state,
        PlayCardMove(
            player_id=state.current_player_id,
            card_id=card_id,
            hand_index=0,
        ),
    )

    assert len(updated.players[state.current_player_id].hand) == hand_size_before - 1
    assert updated.players[state.current_player_id].played_cards.count(card_id) == played_count_before + 1
    assert (
        updated.resource_pool.power > before_power
        or updated.resource_pool.influence > before_influence
    )


def test_bounty_hunter_grants_three_power() -> None:
    state = _base_state(seed=31).model_copy(deep=True)
    state.players["p1"].hand = ["bounty_hunter"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.power = 0

    played = apply(state, PlayCardMove(player_id="p1", card_id="bounty_hunter", hand_index=0))

    assert played.resource_pool.power == 3


def test_deathblade_resolves_two_separate_assassinations() -> None:
    state = _base_state(seed=33).model_copy(deep=True)
    state.players["p1"].hand = ["deathblade"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.board.nodes["site_a"].spies.add("p1")
    state.board.nodes["site_a"].troop_slots = ["p2", "p2", None]

    played = apply(state, PlayCardMove(player_id="p1", card_id="deathblade", hand_index=0))
    first = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="deathblade",
            selection={"target_node_id": "site_a", "target_slot_index": 0},
        ),
    )
    resolved = apply(
        first,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="deathblade",
            selection={"target_node_id": "site_a", "target_slot_index": 1},
        ),
    )

    assert resolved.board.nodes["site_a"].troop_slots == [None, None, None]
    assert len(resolved.players["p1"].trophy_hall) >= 2


def test_dragon_cultist_modal_influence_option_grants_two_influence() -> None:
    state = _base_state(seed=37).model_copy(deep=True)
    state.players["p1"].hand = ["dragon_cultist"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.power = 0
    state.resource_pool.influence = 0

    played = apply(state, PlayCardMove(player_id="p1", card_id="dragon_cultist", hand_index=0))
    resolved = apply(
        played,
        ResolveGenericChoiceMove(player_id="p1", source_card_id="dragon_cultist", option_id="option_2"),
    )

    assert resolved.resource_pool.power == 0
    assert resolved.resource_pool.influence == 2


def test_enchanter_of_thay_modal_place_spy_option_places_spy() -> None:
    state = _base_state(seed=39).model_copy(deep=True)
    state.players["p1"].hand = ["enchanter_of_thay"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []

    played = apply(state, PlayCardMove(player_id="p1", card_id="enchanter_of_thay", hand_index=0))
    chose_mode = apply(
        played,
        ResolveGenericChoiceMove(player_id="p1", source_card_id="enchanter_of_thay", option_id="option_1"),
    )
    resolved = apply(
        chose_mode,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="enchanter_of_thay",
            selection={"target_node_id": "site_a"},
        ),
    )

    assert "p1" in resolved.board.nodes["site_a"].spies


def test_enchanter_of_thay_modal_return_spy_option_grants_four_power() -> None:
    state = _base_state(seed=40).model_copy(deep=True)
    state.players["p1"].hand = ["enchanter_of_thay"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.power = 0
    state.board.nodes["site_a"].spies.add("p1")
    spies_available_before = state.players["p1"].spies_available

    played = apply(state, PlayCardMove(player_id="p1", card_id="enchanter_of_thay", hand_index=0))
    chose_mode = apply(
        played,
        ResolveGenericChoiceMove(player_id="p1", source_card_id="enchanter_of_thay", option_id="option_2"),
    )
    resolved = apply(
        chose_mode,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="enchanter_of_thay",
            selection={"node_id": "site_a", "spy_owner_id": "p1"},
        ),
    )

    assert "p1" not in resolved.board.nodes["site_a"].spies
    assert resolved.players["p1"].spies_available == spies_available_before + 1
    assert resolved.resource_pool.power == 4


def test_ettin_modal_deploy_option_deploys_three_troops() -> None:
    state = _base_state(seed=55).model_copy(deep=True)
    state.players["p1"].hand = ["ettin"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.board.nodes["site_a"].spies.add("p1")
    state.board.nodes["site_a"].troop_slots = [None, None, None]
    barracks_before = state.players["p1"].barracks

    played = apply(state, PlayCardMove(player_id="p1", card_id="ettin", hand_index=0))
    chose_mode = apply(played, ResolveGenericChoiceMove(player_id="p1", source_card_id="ettin", option_id="option_1"))
    current = chose_mode
    for _ in range(3):
        current = apply(
            current,
            ResolveGenericChoiceMove(player_id="p1", source_card_id="ettin", selection={"target_node_id": "site_a"}),
        )

    assert current.board.nodes["site_a"].troop_slots == ["p1", "p1", "p1"]
    assert current.players["p1"].barracks == barracks_before - 3


def test_ettin_modal_assassinate_option_removes_two_white_troops() -> None:
    state = _base_state(seed=56).model_copy(deep=True)
    state.players["p1"].hand = ["ettin"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.board.nodes["site_a"].spies.add("p1")
    state.board.nodes["site_a"].troop_slots = ["white", "white", None]

    played = apply(state, PlayCardMove(player_id="p1", card_id="ettin", hand_index=0))
    chose_mode = apply(played, ResolveGenericChoiceMove(player_id="p1", source_card_id="ettin", option_id="option_2"))
    after_first = apply(
        chose_mode,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="ettin",
            selection={"target_node_id": "site_a", "target_slot_index": 0},
        ),
    )
    resolved = apply(
        after_first,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="ettin",
            selection={"target_node_id": "site_a", "target_slot_index": 1},
        ),
    )

    assert resolved.board.nodes["site_a"].troop_slots == [None, None, None]
    assert resolved.players["p1"].trophy_hall == ["white", "white"]


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


def test_death_tyrant_gains_influence_per_troop_removed_by_effect() -> None:
    state = _base_state(seed=41).model_copy(deep=True)
    state.players["p1"].hand = ["death_tyrant"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.influence = 0
    state.board.nodes["site_a"].spies.add("p1")
    state.board.nodes["site_a"].troop_slots = ["p2", "p2", None]

    played = apply(state, PlayCardMove(player_id="p1", card_id="death_tyrant", hand_index=0))
    first = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="death_tyrant",
            selection={"target_node_id": "site_a", "target_slot_index": 0},
        ),
    )
    resolved = apply(
        first,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="death_tyrant",
            selection={"target_node_id": "site_a", "target_slot_index": 1},
        ),
    )

    assert resolved.board.nodes["site_a"].troop_slots == [None, None, None]
    assert resolved.resource_pool.influence == 2


def test_death_tyrant_can_stop_after_one_assassination() -> None:
    state = _base_state(seed=45).model_copy(deep=True)
    state.players["p1"].hand = ["death_tyrant"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.influence = 0
    state.board.nodes["site_a"].spies.add("p1")
    state.board.nodes["site_a"].troop_slots = ["p2", "p2", "p2"]

    played = apply(state, PlayCardMove(player_id="p1", card_id="death_tyrant", hand_index=0))
    after_first = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="death_tyrant",
            selection={"target_node_id": "site_a", "target_slot_index": 0},
        ),
    )

    first_skip = next(
        move
        for move in legal_moves(after_first)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "death_tyrant"
        and move.selection == {}
    )
    after_second = apply(after_first, first_skip)

    second_skip = next(
        move
        for move in legal_moves(after_second)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "death_tyrant"
        and move.selection == {}
    )
    resolved = apply(after_second, second_skip)

    assert resolved.board.nodes["site_a"].troop_slots == [None, "p2", "p2"]
    assert resolved.resource_pool.influence == 1


def test_death_tyrant_no_legal_targets_resolves_with_zero_influence() -> None:
    state = _base_state(seed=46).model_copy(deep=True)
    state.players["p1"].hand = ["death_tyrant"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.influence = 0
    state.board.nodes["site_a"].spies.add("p1")
    state.board.nodes["site_a"].troop_slots = [None, None, None]

    resolved = apply(state, PlayCardMove(player_id="p1", card_id="death_tyrant", hand_index=0))

    assert resolved.pending_generic_choice is None
    assert resolved.resource_pool.influence == 0


def test_death_tyrant_can_decline_all_assassinations_even_with_targets() -> None:
    state = _base_state(seed=49).model_copy(deep=True)
    state.players["p1"].hand = ["death_tyrant"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.influence = 0
    state.board.nodes["site_a"].spies.add("p1")
    state.board.nodes["site_a"].troop_slots = ["p2", "p2", "p2"]

    played = apply(state, PlayCardMove(player_id="p1", card_id="death_tyrant", hand_index=0))

    skip_first = next(
        move
        for move in legal_moves(played)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "death_tyrant"
        and move.selection == {}
    )
    after_first = apply(played, skip_first)

    skip_second = next(
        move
        for move in legal_moves(after_first)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "death_tyrant"
        and move.selection == {}
    )
    after_second = apply(after_first, skip_second)

    skip_third = next(
        move
        for move in legal_moves(after_second)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "death_tyrant"
        and move.selection == {}
    )
    resolved = apply(after_second, skip_third)

    assert resolved.board.nodes["site_a"].troop_slots == ["p2", "p2", "p2"]
    assert resolved.resource_pool.influence == 0


def test_earth_elemental_grants_one_influence_and_draws_with_ambition_focus() -> None:
    state = _base_state(seed=50).model_copy(deep=True)
    state.players["p1"].hand = ["earth_elemental", "black_earth_cultist"]
    state.players["p1"].deck = ["advance_scout"]
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.influence = 0
    state.board.nodes["site_a"].troop_slots = ["p2", None, None]
    state.board.nodes["site_a"].spies.add("p1")
    p2_barracks_before = state.players["p2"].barracks

    played = apply(state, PlayCardMove(player_id="p1", card_id="earth_elemental", hand_index=0))
    resolved = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="earth_elemental",
            selection={"unit_type": "troop", "node_id": "site_a", "target_slot_index": 0},
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
    state.board.nodes["site_a"].troop_slots = ["p2", None, None]
    state.board.nodes["site_a"].spies.add("p1")

    played = apply(state, PlayCardMove(player_id="p1", card_id="earth_elemental", hand_index=0))
    resolved = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="earth_elemental",
            selection={"unit_type": "troop", "node_id": "site_a", "target_slot_index": 0},
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
    state.board.nodes["site_a"].spies.add("p1")
    state.board.nodes["site_a"].troop_slots = ["p2", None, None]

    played = apply(state, PlayCardMove(player_id="p1", card_id="eternal_flame_cultist", hand_index=0))
    resolved = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="eternal_flame_cultist",
            selection={"target_node_id": "site_a", "target_slot_index": 0},
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
    state.board.nodes["site_a"].spies.add("p1")
    state.board.nodes["site_a"].troop_slots = ["p2", None, None]

    played = apply(state, PlayCardMove(player_id="p1", card_id="eternal_flame_cultist", hand_index=0))
    resolved = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="eternal_flame_cultist",
            selection={"target_node_id": "site_a", "target_slot_index": 0},
        ),
    )

    assert resolved.resource_pool.power == 0


def test_dragonclaw_grants_two_power_when_non_white_trophy_threshold_met() -> None:
    state = _base_state(seed=43).model_copy(deep=True)
    state.players["p1"].hand = ["dragonclaw"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.players["p1"].trophy_hall = ["p2", "p2", "p2", "p2", "p2"]
    state.resource_pool.power = 0
    state.board.nodes["site_a"].spies.add("p1")
    state.board.nodes["site_a"].troop_slots = ["p2", None, None]

    played = apply(state, PlayCardMove(player_id="p1", card_id="dragonclaw", hand_index=0))
    resolved = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="dragonclaw",
            selection={"target_node_id": "site_a", "target_slot_index": 0},
        ),
    )

    assert resolved.resource_pool.power == 2


def test_dragonclaw_does_not_count_white_trophies_toward_threshold() -> None:
    state = _base_state(seed=44).model_copy(deep=True)
    state.players["p1"].hand = ["dragonclaw"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.players["p1"].trophy_hall = ["p2", "p2", "p2", "white", "white"]
    state.resource_pool.power = 0
    state.board.nodes["site_a"].spies.add("p1")
    state.board.nodes["site_a"].troop_slots = ["p2", None, None]

    played = apply(state, PlayCardMove(player_id="p1", card_id="dragonclaw", hand_index=0))
    resolved = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="dragonclaw",
            selection={"target_node_id": "site_a", "target_slot_index": 0},
        ),
    )

    assert resolved.resource_pool.power == 0


def test_drow_negotiator_grants_three_influence_with_four_promoted_cards() -> None:
    state = _base_state(seed=47).model_copy(deep=True)
    state.players["p1"].hand = ["drow_negotiator"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.players["p1"].inner_circle = ["a", "b", "c", "d"]
    state.resource_pool.influence = 0

    resolved = apply(state, PlayCardMove(player_id="p1", card_id="drow_negotiator", hand_index=0))

    assert resolved.resource_pool.influence == 3
    assert resolved.pending_end_of_turn_promotions
    assert resolved.pending_end_of_turn_promotions[-1].requires_another_played_card is True


def test_drow_negotiator_no_influence_bonus_below_promoted_threshold() -> None:
    state = _base_state(seed=48).model_copy(deep=True)
    state.players["p1"].hand = ["drow_negotiator"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.players["p1"].inner_circle = ["a", "b", "c"]
    state.resource_pool.influence = 0

    resolved = apply(state, PlayCardMove(player_id="p1", card_id="drow_negotiator", hand_index=0))

    assert resolved.resource_pool.influence == 0


def test_white_wyrmling_deploys_two_before_market_devour_choice() -> None:
    state = _base_state(seed=29).model_copy(deep=True)
    state.players["p1"].hand = ["white_wyrmling"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.board.nodes["site_a"].troop_slots = [None, None, None]
    barracks_before = state.players["p1"].barracks

    played = apply(state, PlayCardMove(player_id="p1", card_id="white_wyrmling", hand_index=0))
    deploy_move = next(
        move
        for move in legal_moves(played)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "white_wyrmling"
        and move.selection.get("target_node_id") == "site_a"
    )
    after_first_deploy = apply(played, deploy_move)
    second_deploy_move = next(
        move
        for move in legal_moves(after_first_deploy)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "white_wyrmling"
        and move.selection.get("target_node_id") == "site_a"
    )
    deployed = apply(after_first_deploy, second_deploy_move)

    assert deployed.board.nodes["site_a"].troop_slots.count("p1") == 2
    assert deployed.players["p1"].barracks == barracks_before - 2

    follow_up_moves = [
        move
        for move in legal_moves(deployed)
        if isinstance(move, ResolveGenericChoiceMove) and move.source_card_id == "white_wyrmling"
    ]
    assert follow_up_moves
    assert any("market_slot" in move.selection for move in follow_up_moves)


def test_gar_shatterkeel_deploys_three_before_recruit_choice() -> None:
    state = _base_state(seed=60).model_copy(deep=True)
    state.players["p1"].hand = ["gar_shatterkeel"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.board.nodes["site_a"].troop_slots = [None, None, None]
    barracks_before = state.players["p1"].barracks

    played = apply(state, PlayCardMove(player_id="p1", card_id="gar_shatterkeel", hand_index=0))
    deploy_move = next(
        move
        for move in legal_moves(played)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "gar_shatterkeel"
        and move.selection.get("target_node_id") == "site_a"
    )
    deployed = played
    for _ in range(3):
        deployed = apply(deployed, deploy_move)

    assert deployed.board.nodes["site_a"].troop_slots.count("p1") == 3
    assert deployed.players["p1"].barracks == barracks_before - 3


def test_gar_shatterkeel_recruit_respects_aspect_and_cost_cap() -> None:
    state = _base_state(seed=61).model_copy(deep=True)
    state.players["p1"].hand = ["gar_shatterkeel"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.influence = 10
    state.market.row = ["advance_scout", "balor", "blackguard"]
    state.board.nodes["site_a"].troop_slots = [None, None, None]

    played = apply(state, PlayCardMove(player_id="p1", card_id="gar_shatterkeel", hand_index=0))
    deploy_move = next(
        move
        for move in legal_moves(played)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "gar_shatterkeel"
        and move.selection.get("target_node_id") == "site_a"
    )
    after_deploy = played
    for _ in range(3):
        after_deploy = apply(after_deploy, deploy_move)

    recruit_moves = [
        move
        for move in legal_moves(after_deploy)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "gar_shatterkeel"
        and "market_slot" in move.selection
    ]

    allowed_slots = {int(move.selection["market_slot"]) for move in recruit_moves}
    assert allowed_slots == {0}


def test_gibbering_mouther_targets_only_opponents_with_presence_and_adds_insane_outcast() -> None:
    state = create_game_state_from_files(BOARD_PATH, CARD_PATH, SETUP_PATH, ["p1", "p2", "p3"], seed=62).model_copy(deep=True)
    state.players["p1"].hand = ["gibbering_mouther"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.board.nodes["site_a"].troop_slots = [None, None, None]
    state.board.nodes["site_a"].spies = {"p2", "p3"}

    played = apply(state, PlayCardMove(player_id="p1", card_id="gibbering_mouther", hand_index=0))
    deploy_move = next(
        move
        for move in legal_moves(played)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "gibbering_mouther"
        and move.selection.get("target_node_id") == "site_a"
    )
    after_first_deploy = apply(played, deploy_move)
    second_deploy_move = next(
        move
        for move in legal_moves(after_first_deploy)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "gibbering_mouther"
        and move.selection.get("target_node_id") == "site_a"
    )
    after_deploy = apply(after_first_deploy, second_deploy_move)

    follow_up_moves = [
        move
        for move in legal_moves(after_deploy)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "gibbering_mouther"
        and "target_player_id" in move.selection
    ]
    target_player_ids = {str(move.selection["target_player_id"]) for move in follow_up_moves}
    assert target_player_ids == {"p2", "p3"}

    target_p2_move = next(move for move in follow_up_moves if move.selection.get("target_player_id") == "p2")
    resolved = apply(after_deploy, target_p2_move)

    assert resolved.players["p2"].discard_pile[-1] == "insane_outcast"
    assert "insane_outcast" not in resolved.players["p3"].discard_pile


def test_ghoul_gives_insane_outcast_to_each_opponent() -> None:
    state = create_game_state_from_files(BOARD_PATH, CARD_PATH, SETUP_PATH, ["p1", "p2", "p3"], seed=620).model_copy(deep=True)
    state.players["p1"].hand = ["ghoul"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.players["p2"].discard_pile = []
    state.players["p3"].discard_pile = []
    state.resource_pool.power = 0

    played = apply(state, PlayCardMove(player_id="p1", card_id="ghoul", hand_index=0))

    assert played.resource_pool.power == 2
    assert played.players["p2"].discard_pile[-1] == "insane_outcast"
    assert played.players["p3"].discard_pile[-1] == "insane_outcast"


def test_myconid_adult_targets_one_opponent_for_insane_outcast() -> None:
    state = create_game_state_from_files(BOARD_PATH, CARD_PATH, SETUP_PATH, ["p1", "p2", "p3"], seed=621).model_copy(deep=True)
    state.players["p1"].hand = ["myconid_adult"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.players["p2"].discard_pile = []
    state.players["p3"].discard_pile = []
    state.resource_pool.influence = 0

    played = apply(state, PlayCardMove(player_id="p1", card_id="myconid_adult", hand_index=0))
    target_moves = [
        move
        for move in legal_moves(played)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "myconid_adult"
        and "target_player_id" in move.selection
    ]

    assert played.resource_pool.influence == 2
    assert {str(move.selection["target_player_id"]) for move in target_moves} == {"p2", "p3"}

    target_p2_move = next(move for move in target_moves if move.selection.get("target_player_id") == "p2")
    resolved = apply(played, target_p2_move)

    assert resolved.players["p2"].discard_pile[-1] == "insane_outcast"
    assert "insane_outcast" not in resolved.players["p3"].discard_pile


def test_red_dragon_returns_enemy_spy_after_supplant() -> None:
    state = _base_state(seed=622).model_copy(deep=True)
    state.players["p1"].hand = ["red_dragon"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.board.nodes["site_a"].troop_slots = ["p1", "p2", None]
    state.board.nodes["site_a"].spies = {"p1", "p2"}
    spies_available_before = state.players["p2"].spies_available

    played = apply(state, PlayCardMove(player_id="p1", card_id="red_dragon", hand_index=0))
    supplant_move = next(
        move
        for move in legal_moves(played)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "red_dragon"
        and move.selection.get("target_node_id") == "site_a"
        and move.selection.get("target_slot_index") == 1
    )
    after_supplant = apply(played, supplant_move)

    return_spy_moves = [
        move
        for move in legal_moves(after_supplant)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "red_dragon"
        and move.selection.get("node_id") == "site_a"
    ]

    assert {str(move.selection["spy_owner_id"]) for move in return_spy_moves} == {"p2"}

    resolved = apply(after_supplant, return_spy_moves[0])

    assert "p2" not in resolved.board.nodes["site_a"].spies
    assert resolved.players["p2"].spies_available == spies_available_before + 1


def test_yan_c_bin_focus_adds_a_second_spy_action() -> None:
    state = _base_state(seed=623).model_copy(deep=True)
    state.players["p1"].hand = ["yan_c_bin", "infiltrator"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.board.nodes["site_a"].troop_slots = ["p2", None, None]

    played = apply(state, PlayCardMove(player_id="p1", card_id="yan_c_bin", hand_index=0))
    place_spy_move = next(
        move
        for move in legal_moves(played)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "yan_c_bin"
        and move.selection.get("target_node_id") == "site_a"
    )
    after_spy = apply(played, place_spy_move)
    assassinate_move = next(
        move
        for move in legal_moves(after_spy)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "yan_c_bin"
        and move.selection.get("target_node_id") == "site_a"
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


def test_matron_mother_mills_deck_then_promotes_from_discard() -> None:
    state = _base_state(seed=624).model_copy(deep=True)
    state.players["p1"].hand = ["matron_mother"]
    state.players["p1"].deck = ["noble"]
    state.players["p1"].discard_pile = ["soldier"]
    state.players["p1"].played_cards = []

    played = apply(state, PlayCardMove(player_id="p1", card_id="matron_mother", hand_index=0))
    promote_moves = [
        move
        for move in legal_moves(played)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "matron_mother"
        and "discard_index" in move.selection
    ]

    assert promote_moves

    promote_last = next(
        move
        for move in promote_moves
        if int(move.selection["discard_index"]) == len(played.players["p1"].discard_pile) - 1
    )
    resolved = apply(played, promote_last)

    assert "noble" in resolved.players["p1"].inner_circle


def test_orcus_devour_step_grants_five_power_before_follow_up_actions() -> None:
    state = _base_state(seed=625).model_copy(deep=True)
    state.players["p1"].hand = ["orcus", "noble"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.power = 0

    played = apply(state, PlayCardMove(player_id="p1", card_id="orcus", hand_index=0))
    devour_move = next(
        move
        for move in legal_moves(played)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "orcus"
        and move.selection.get("source_zone") == "hand"
    )
    resolved = apply(played, devour_move)

    assert resolved.resource_pool.power == 5
    follow_up_moves = [
        move
        for move in legal_moves(resolved)
        if isinstance(move, ResolveGenericChoiceMove) and move.source_card_id == "orcus"
    ]
    assert follow_up_moves


def test_insane_outcast_play_does_not_block_turn_resolution() -> None:
    state = _base_state(seed=626).model_copy(deep=True)
    state.players["p1"].hand = ["insane_outcast", "noble"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []

    played = apply(state, PlayCardMove(player_id="p1", card_id="insane_outcast", hand_index=0))

    assert played.pending_generic_choice is None


def test_ulitharid_plays_market_card_up_to_cost_cap_then_devours_same_slot() -> None:
    state = _base_state(seed=627).model_copy(deep=True)
    state.players["p1"].hand = ["ulitharid"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.market.row = ["noble", "balor", "soldier"]
    state.market.deck = []

    played = apply(state, PlayCardMove(player_id="p1", card_id="ulitharid", hand_index=0))
    market_play_moves = [
        move
        for move in legal_moves(played)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "ulitharid"
        and move.selection.get("source_zone") == "market"
        and "market_slot" in move.selection
    ]
    allowed_slots = {int(move.selection["market_slot"]) for move in market_play_moves}

    assert allowed_slots == {0, 2}

    play_slot_zero = next(move for move in market_play_moves if int(move.selection["market_slot"]) == 0)
    after_play = apply(played, play_slot_zero)

    devour_moves = [
        move
        for move in legal_moves(after_play)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "ulitharid"
        and move.selection.get("source_zone") == "market"
        and "market_slot" in move.selection
    ]
    assert {int(move.selection["market_slot"]) for move in devour_moves} == {0}

    resolved = apply(after_play, devour_moves[0])

    assert "noble" in resolved.devour_pile


def test_glabrezu_defines_two_single_assassination_actions() -> None:
    state = _base_state(seed=63)
    card = next(card for card in state.definition.catalog.cards if card.card_id == "glabrezu")

    execution_actions = card.execution_model.actions
    flattened_actions = card.actions

    assert [action.op for action in execution_actions] == ["devour", "assassinate_troop", "assassinate_troop"]
    assert [action.quantity.value for action in execution_actions[1:]] == [1, 1]
    assert [action.op for action in flattened_actions] == ["devour", "assassinate_troop", "assassinate_troop"]


def test_glabrezu_runtime_offers_second_assassination_after_first_target() -> None:
    state = _base_state(seed=163).model_copy(deep=True)
    state.players["p1"].hand = ["glabrezu", "advance_scout"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.board.nodes["site_a"].spies.add("p1")
    state.board.nodes["site_a"].troop_slots = ["p2", "p2", None]

    played = apply(state, PlayCardMove(player_id="p1", card_id="glabrezu", hand_index=0))
    devour_move = next(
        move
        for move in legal_moves(played)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "glabrezu"
        and move.selection.get("source_zone") == "hand"
    )
    after_devour = apply(played, devour_move)

    first_assassinate = next(
        move
        for move in legal_moves(after_devour)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "glabrezu"
        and move.selection.get("target_node_id") == "site_a"
        and move.selection.get("target_slot_index") == 0
    )
    after_first = apply(after_devour, first_assassinate)

    second_assassination_moves = [
        move
        for move in legal_moves(after_first)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "glabrezu"
        and move.selection.get("target_node_id") == "site_a"
    ]
    assert second_assassination_moves
    assert {int(move.selection["target_slot_index"]) for move in second_assassination_moves} == {1}


def test_grazzt_option_two_returns_own_spy_then_supplants_white_at_same_site() -> None:
    state = _base_state(seed=64).model_copy(deep=True)
    state.players["p1"].hand = ["grazzt"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.board.nodes["site_a"].spies = {"p1"}
    state.board.nodes["site_a"].troop_slots = ["white", None, None]

    played = apply(state, PlayCardMove(player_id="p1", card_id="grazzt", hand_index=0))
    option_two_move = next(
        move
        for move in legal_moves(played)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "grazzt"
        and move.option_id == "option_2"
    )
    after_option = apply(played, option_two_move)

    return_move = next(
        move
        for move in legal_moves(after_option)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "grazzt"
        and move.selection.get("node_id") == "site_a"
        and move.selection.get("spy_owner_id") == "p1"
    )
    after_return = apply(after_option, return_move)

    supplant_moves = [
        move
        for move in legal_moves(after_return)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "grazzt"
        and "target_node_id" in move.selection
    ]
    assert supplant_moves
    assert {str(move.selection["target_node_id"]) for move in supplant_moves} == {"site_a"}

    supplant_move = next(move for move in supplant_moves if int(move.selection["target_slot_index"]) == 0)
    resolved = apply(after_return, supplant_move)

    assert resolved.board.nodes["site_a"].troop_slots[0] == "p1"


def test_green_wyrmling_gains_two_influence_when_other_troop_present_at_spy_site() -> None:
    state = _base_state(seed=65).model_copy(deep=True)
    state.players["p1"].hand = ["green_wyrmling"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.influence = 0
    state.board.nodes["site_a"].troop_slots = ["p2", None, None]
    state.board.nodes["site_blingdenfire"].troop_slots = [None, None]

    played = apply(state, PlayCardMove(player_id="p1", card_id="green_wyrmling", hand_index=0))
    place_spy_move = next(
        move
        for move in legal_moves(played)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "green_wyrmling"
        and move.selection.get("target_node_id") == "site_a"
    )
    resolved = apply(played, place_spy_move)

    assert resolved.resource_pool.influence == 2


def test_green_wyrmling_does_not_gain_influence_without_other_troop_at_spy_site() -> None:
    state = _base_state(seed=66).model_copy(deep=True)
    state.players["p1"].hand = ["green_wyrmling"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.influence = 0
    state.board.nodes["site_a"].troop_slots = [None, None, None]

    played = apply(state, PlayCardMove(player_id="p1", card_id="green_wyrmling", hand_index=0))
    place_spy_move = next(
        move
        for move in legal_moves(played)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "green_wyrmling"
        and move.selection.get("target_node_id") == "site_a"
    )
    resolved = apply(played, place_spy_move)

    assert resolved.resource_pool.influence == 0


def test_grimlock_model_sets_draw_two_cards() -> None:
    state = _base_state(seed=67)
    card = next(card for card in state.definition.catalog.cards if card.card_id == "grimlock")

    execution_action = card.execution_model.actions[1]
    flattened_action = card.actions[1]

    assert execution_action.op == "draw_cards"
    assert execution_action.quantity.kind == "fixed"
    assert execution_action.quantity.value == 2

    assert flattened_action.op == "draw_cards"
    assert flattened_action.quantity.kind == "fixed"
    assert flattened_action.quantity.value == 2


def test_grimlock_deploys_one_troop_then_draws_two_cards() -> None:
    state = _base_state(seed=806).model_copy(deep=True)
    state.players["p1"].hand = ["grimlock"]
    state.players["p1"].deck = ["noble", "soldier"]
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []

    deploy_nodes = [node_id for node_id, node in state.board.nodes.items() if node.troop_slots]
    assert deploy_nodes
    target_node_id = deploy_nodes[0]

    for node_id, node in state.board.nodes.items():
        if node.troop_slots:
            node.troop_slots = ["p2"] * len(node.troop_slots)
        if node_id == target_node_id:
            node.troop_slots = [None]
            node.spies.add("p1")

    played = apply(state, PlayCardMove(player_id="p1", card_id="grimlock", hand_index=0))

    deploy_move = next(
        move
        for move in legal_moves(played)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "grimlock"
        and move.selection.get("target_node_id") == target_node_id
    )
    current = apply(played, deploy_move)

    assert current.pending_generic_choice is None
    assert len(current.players["p1"].hand) == 2
    assert current.board.nodes[target_node_id].troop_slots == ["p1"]


def test_howling_hatred_cultist_return_spy_mode_gains_three_influence_with_focus_bonus() -> None:
    state = _base_state(seed=68).model_copy(deep=True)
    state.players["p1"].hand = ["howling_hatred_cultist", "infiltrator"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.influence = 0
    state.resource_pool.power = 0
    state.board.nodes["site_a"].spies = {"p1"}

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
        and move.selection.get("node_id") == "site_a"
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
    state.board.nodes["site_a"].spies = {"p1"}

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
        and move.selection.get("node_id") == "site_a"
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
    state.board.nodes["site_a"].spies = {"p1", "p2"}
    state.board.nodes["site_a"].troop_slots = ["p1", None, None]

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


def test_infiltrator_gains_one_power_when_other_player_troop_present_at_spy_site() -> None:
    state = _base_state(seed=72).model_copy(deep=True)
    state.players["p1"].hand = ["infiltrator"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.power = 0
    state.board.nodes["site_a"].troop_slots = ["p2", None, None]

    played = apply(state, PlayCardMove(player_id="p1", card_id="infiltrator", hand_index=0))
    place_spy_move = next(
        move
        for move in legal_moves(played)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "infiltrator"
        and move.selection.get("target_node_id") == "site_a"
    )
    resolved = apply(played, place_spy_move)

    assert resolved.resource_pool.power == 1


def test_infiltrator_does_not_gain_power_without_other_player_troop_at_spy_site() -> None:
    state = _base_state(seed=73).model_copy(deep=True)
    state.players["p1"].hand = ["infiltrator"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.power = 0
    state.board.nodes["site_a"].troop_slots = [None, None, None]

    played = apply(state, PlayCardMove(player_id="p1", card_id="infiltrator", hand_index=0))
    place_spy_move = next(
        move
        for move in legal_moves(played)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "infiltrator"
        and move.selection.get("target_node_id") == "site_a"
    )
    resolved = apply(played, place_spy_move)

    assert resolved.resource_pool.power == 0


def test_information_broker_return_spy_mode_returns_own_spy_and_draws_three() -> None:
    state = _base_state(seed=74).model_copy(deep=True)
    state.players["p1"].hand = ["information_broker", "advance_scout", "advance_scout"]
    state.players["p1"].deck = ["blackguard", "drow_negotiator", "infiltrator", "kobold"]
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.board.nodes["site_a"].spies = {"p1", "p2"}

    played = apply(state, PlayCardMove(player_id="p1", card_id="information_broker", hand_index=0))
    option_two = apply(
        played,
        ResolveGenericChoiceMove(player_id="p1", source_card_id="information_broker", option_id="option_2"),
    )

    return_moves = [
        move
        for move in legal_moves(option_two)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "information_broker"
        and "spy_owner_id" in move.selection
    ]
    assert return_moves
    assert {str(move.selection["spy_owner_id"]) for move in return_moves} == {"p1"}

    return_spy_move = next(
        move
        for move in return_moves
        if move.selection.get("node_id") == "site_a" and move.selection.get("spy_owner_id") == "p1"
    )
    hand_before = len(option_two.players["p1"].hand)
    resolved = apply(option_two, return_spy_move)

    assert len(resolved.players["p1"].hand) == hand_before + 3
    assert "p1" not in resolved.board.nodes["site_a"].spies


def test_information_broker_model_includes_draw_three_on_option_two() -> None:
    state = _base_state(seed=75)
    card = next(card for card in state.definition.catalog.cards if card.card_id == "information_broker")

    option_two_draw = next(
        action
        for action in card.execution_model.options[1].actions
        if action.op == "draw_cards"
    )

    assert option_two_draw.quantity.kind == "fixed"
    assert option_two_draw.quantity.value == 3


def test_intellect_devourer_option_one_gains_three_influence() -> None:
    state = _base_state(seed=76).model_copy(deep=True)
    state.players["p1"].hand = ["intellect_devourer"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.influence = 0

    played = apply(state, PlayCardMove(player_id="p1", card_id="intellect_devourer", hand_index=0))
    resolved = apply(
        played,
        ResolveGenericChoiceMove(player_id="p1", source_card_id="intellect_devourer", option_id="option_1"),
    )

    assert resolved.resource_pool.influence == 3


def test_jackalwere_option_two_returns_own_spy_and_gains_power_and_influence() -> None:
    state = _base_state(seed=77).model_copy(deep=True)
    state.players["p1"].hand = ["jackalwere"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.power = 0
    state.resource_pool.influence = 0
    state.board.nodes["site_a"].spies = {"p1", "p2"}

    played = apply(state, PlayCardMove(player_id="p1", card_id="jackalwere", hand_index=0))
    option_two = apply(
        played,
        ResolveGenericChoiceMove(player_id="p1", source_card_id="jackalwere", option_id="option_2"),
    )

    return_moves = [
        move
        for move in legal_moves(option_two)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "jackalwere"
        and "spy_owner_id" in move.selection
    ]
    assert return_moves
    assert {str(move.selection["spy_owner_id"]) for move in return_moves} == {"p1"}

    return_spy_move = next(
        move
        for move in return_moves
        if move.selection.get("node_id") == "site_a" and move.selection.get("spy_owner_id") == "p1"
    )
    resolved = apply(option_two, return_spy_move)

    assert resolved.resource_pool.power == 2
    assert resolved.resource_pool.influence == 2


def test_intellect_devourer_option_two_returns_only_own_units_with_mixed_choices_up_to_two() -> None:
    state = _base_state(seed=176).model_copy(deep=True)
    state.players["p1"].hand = ["intellect_devourer"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.board.nodes["site_a"].troop_slots = ["p1", "p2", None]
    state.board.nodes["site_blingdenfire"].spies = {"p1", "p2"}
    barracks_before = state.players["p1"].barracks
    spies_before = state.players["p1"].spies_available

    played = apply(state, PlayCardMove(player_id="p1", card_id="intellect_devourer", hand_index=0))
    option_two = apply(
        played,
        ResolveGenericChoiceMove(player_id="p1", source_card_id="intellect_devourer", option_id="option_2"),
    )

    first_return_moves = [
        move
        for move in legal_moves(option_two)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "intellect_devourer"
        and "unit_type" in move.selection
    ]
    assert first_return_moves

    troop_moves = [move for move in first_return_moves if move.selection.get("unit_type") == "troop"]
    spy_moves = [move for move in first_return_moves if move.selection.get("unit_type") == "spy"]
    assert troop_moves and spy_moves
    assert all(
        option_two.board.nodes[str(move.selection["node_id"])].troop_slots[int(move.selection["target_slot_index"])] == "p1"
        for move in troop_moves
    )
    assert all(str(move.selection["spy_owner_id"]) == "p1" for move in spy_moves)

    return_troop_move = next(
        move
        for move in troop_moves
        if move.selection.get("node_id") == "site_a" and int(move.selection.get("target_slot_index", -1)) == 0
    )
    after_first = apply(option_two, return_troop_move)

    second_return_moves = [
        move
        for move in legal_moves(after_first)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "intellect_devourer"
        and "unit_type" in move.selection
    ]
    assert second_return_moves
    assert all(
        (
            str(move.selection.get("unit_type")) != "spy"
            or str(move.selection.get("spy_owner_id")) == "p1"
        )
        for move in second_return_moves
    )

    return_spy_move = next(
        move
        for move in second_return_moves
        if move.selection.get("unit_type") == "spy"
        and move.selection.get("node_id") == "site_blingdenfire"
        and move.selection.get("spy_owner_id") == "p1"
    )
    resolved = apply(after_first, return_spy_move)

    assert resolved.players["p1"].barracks == barracks_before + 1
    assert resolved.players["p1"].spies_available == spies_before + 1


def test_marilith_devours_hand_card_and_gains_five_power() -> None:
    state = _base_state(seed=78).model_copy(deep=True)
    state.players["p1"].hand = ["marilith", "advance_scout"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.power = 0

    played = apply(state, PlayCardMove(player_id="p1", card_id="marilith", hand_index=0))
    devour_move = next(
        move
        for move in legal_moves(played)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "marilith"
        and move.selection.get("source_zone") == "hand"
    )
    resolved = apply(played, devour_move)

    assert resolved.resource_pool.power == 5
    assert "advance_scout" in resolved.devour_pile


def test_marlos_urnrayle_grants_one_influence() -> None:
    state = _base_state(seed=79).model_copy(deep=True)
    state.players["p1"].hand = ["marlos_urnrayle"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.influence = 0

    played = apply(state, PlayCardMove(player_id="p1", card_id="marlos_urnrayle", hand_index=0))

    assert played.resource_pool.influence == 1


def test_marlos_urnrayle_recruit_mode_filters_ambition_up_to_cost_four() -> None:
    state = _base_state(seed=790).model_copy(deep=True)
    state.players["p1"].hand = ["marlos_urnrayle"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.influence = 10

    catalog = list(state.definition.catalog.cards)
    valid = next(card for card in catalog if card.card_id != "marlos_urnrayle" and card.aspect == "ambition" and card.cost <= 4)
    invalid_aspect = next(card for card in catalog if card.aspect != "ambition" and card.cost <= 4)
    invalid_cost = next(card for card in catalog if card.aspect == "ambition" and card.cost > 4)

    state.market.row[0] = valid.card_id
    state.market.row[1] = invalid_aspect.card_id
    state.market.row[2] = invalid_cost.card_id

    played = apply(state, PlayCardMove(player_id="p1", card_id="marlos_urnrayle", hand_index=0))
    recruit_moves = [
        move
        for move in legal_moves(played)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "marlos_urnrayle"
        and "market_slot" in move.selection
    ]
    slots = {int(move.selection["market_slot"]) for move in recruit_moves}

    assert 0 in slots
    assert 1 not in slots
    assert 2 not in slots


def test_master_of_melee_magthere_model_deploy_mode_is_four_troops() -> None:
    state = _base_state(seed=80)
    card = next(card for card in state.definition.catalog.cards if card.card_id == "master_of_melee_magthere")

    deploy_action = card.execution_model.options[0].actions[0]

    assert deploy_action.op == "deploy_troops"
    assert deploy_action.quantity.kind == "fixed"
    assert deploy_action.quantity.value == 4


def test_masters_of_sorcere_model_place_two_spies_mode_is_two_fixed_actions() -> None:
    state = _base_state(seed=81)
    card = next(card for card in state.definition.catalog.cards if card.card_id == "masters_of_sorcere")

    option_one_actions = card.execution_model.options[0].actions

    assert len(option_one_actions) == 2
    assert all(action.op == "place_spy" for action in option_one_actions)
    assert all(action.quantity.kind == "fixed" and action.quantity.value == 1 for action in option_one_actions)


def test_mind_flayer_option_one_devours_and_gains_three_influence() -> None:
    state = _base_state(seed=82).model_copy(deep=True)
    state.players["p1"].hand = ["mind_flayer", "advance_scout"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.influence = 0

    played = apply(state, PlayCardMove(player_id="p1", card_id="mind_flayer", hand_index=0))
    chose_option = apply(
        played,
        ResolveGenericChoiceMove(player_id="p1", source_card_id="mind_flayer", option_id="option_1"),
    )
    devour_move = next(
        move
        for move in legal_moves(chose_option)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "mind_flayer"
        and move.selection.get("source_zone") == "hand"
    )
    resolved = apply(chose_option, devour_move)

    assert resolved.resource_pool.influence == 3
    assert "advance_scout" in resolved.devour_pile


def test_minotaur_skeleton_model_deploy_mode_is_three_troops() -> None:
    state = _base_state(seed=83)
    card = next(card for card in state.definition.catalog.cards if card.card_id == "minotaur_skeleton")

    deploy_action = card.execution_model.options[0].actions[0]

    assert deploy_action.op == "deploy_troops"
    assert deploy_action.quantity.kind == "fixed"
    assert deploy_action.quantity.value == 3


def test_minotaur_skeleton_white_assassination_chain_stays_on_initial_site() -> None:
    state = _base_state(seed=791).model_copy(deep=True)
    state.players["p1"].hand = ["minotaur_skeleton"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.board.nodes["site_a"].spies.add("p1")
    state.board.nodes["site_blingdenfire"].spies.add("p1")
    state.board.nodes["site_a"].troop_slots = ["white", "white", "white"]
    state.board.nodes["site_blingdenfire"].troop_slots = ["white", None, None]

    played = apply(state, PlayCardMove(player_id="p1", card_id="minotaur_skeleton", hand_index=0))
    option_two = apply(
        played,
        ResolveGenericChoiceMove(player_id="p1", source_card_id="minotaur_skeleton", option_id="option_2"),
    )

    first_assassinate = next(
        move
        for move in legal_moves(option_two)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "minotaur_skeleton"
        and move.selection.get("target_node_id") == "site_a"
        and move.selection.get("target_slot_index") == 0
    )
    after_first = apply(option_two, first_assassinate)

    second_assassinate_moves = [
        move
        for move in legal_moves(after_first)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "minotaur_skeleton"
        and "target_node_id" in move.selection
    ]

    assert second_assassinate_moves
    assert {str(move.selection["target_node_id"]) for move in second_assassinate_moves} == {"site_a"}


def test_nalfeshnee_grants_three_influence() -> None:
    state = _base_state(seed=84).model_copy(deep=True)
    state.players["p1"].hand = ["nalfeshnee"]
    state.players["p1"].deck = ["advance_scout"]
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.influence = 0

    played = apply(state, PlayCardMove(player_id="p1", card_id="nalfeshnee", hand_index=0))

    assert played.resource_pool.influence == 3


def test_nalfeshnee_promotes_top_of_deck_card() -> None:
    state = _base_state(seed=792).model_copy(deep=True)
    state.players["p1"].hand = ["nalfeshnee"]
    state.players["p1"].deck = ["advance_scout", "soldier"]
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []

    played = apply(state, PlayCardMove(player_id="p1", card_id="nalfeshnee", hand_index=0))

    assert "soldier" in played.players["p1"].inner_circle
    assert played.players["p1"].deck == ["advance_scout"]


def test_necromancer_option_one_grants_three_influence() -> None:
    state = _base_state(seed=85).model_copy(deep=True)
    state.players["p1"].hand = ["necromancer"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.influence = 0

    played = apply(state, PlayCardMove(player_id="p1", card_id="necromancer", hand_index=0))
    resolved = apply(
        played,
        ResolveGenericChoiceMove(player_id="p1", source_card_id="necromancer", option_id="option_1"),
    )

    assert resolved.resource_pool.influence == 3


def test_necromancer_promote_mode_allows_single_choice_from_played_hand_or_discard() -> None:
    state = _base_state(seed=793).model_copy(deep=True)
    state.players["p1"].hand = ["necromancer", "advance_scout"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = ["soldier"]
    state.players["p1"].played_cards = []

    played = apply(state, PlayCardMove(player_id="p1", card_id="necromancer", hand_index=0))
    option_two = apply(
        played,
        ResolveGenericChoiceMove(player_id="p1", source_card_id="necromancer", option_id="option_2"),
    )

    promote_moves = [
        move
        for move in legal_moves(option_two)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "necromancer"
        and "source_zone" in move.selection
    ]
    zones = {str(move.selection["source_zone"]) for move in promote_moves}

    assert zones == {"played", "hand", "discard"}

    promote_from_hand = next(
        move
        for move in promote_moves
        if move.selection.get("source_zone") == "hand" and move.selection.get("hand_index") == 0
    )
    resolved = apply(option_two, promote_from_hand)

    assert "advance_scout" in resolved.players["p1"].inner_circle
    assert "advance_scout" not in resolved.players["p1"].hand


def test_neogi_model_has_deploy_four_and_end_of_turn_discard() -> None:
    state = _base_state(seed=86)
    card = next(card for card in state.definition.catalog.cards if card.card_id == "neogi")

    deploy_action = card.execution_model.actions[0]
    discard_action = card.execution_model.actions[1]

    assert deploy_action.op == "deploy_troops"
    assert deploy_action.quantity.kind == "fixed"
    assert deploy_action.quantity.value == 4
    assert discard_action.op == "force_discard"
    assert discard_action.timing == "end_of_turn"


def test_neogi_end_of_turn_forces_each_opponent_to_discard_one() -> None:
    state = _base_state(seed=794).model_copy(deep=True)
    state.phase = TurnPhase.MAIN
    state.players["p1"].played_cards = ["neogi"]
    state.players["p2"].hand = ["soldier", "advance_scout"]
    state.players["p2"].discard_pile = []

    ended_main = apply(state, EndMainPhaseMove(player_id="p1"))

    assert len(ended_main.players["p2"].hand) == 1
    assert ended_main.players["p2"].discard_pile == ["soldier"]


def test_noble_grants_one_influence() -> None:
    state = _base_state(seed=795).model_copy(deep=True)
    state.players["p1"].hand = ["noble"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.influence = 0

    played = apply(state, PlayCardMove(player_id="p1", card_id="noble", hand_index=0))

    assert played.resource_pool.influence == 1


def test_night_hag_option_two_returns_own_spy_and_draws_two() -> None:
    state = _base_state(seed=87).model_copy(deep=True)
    state.players["p1"].hand = ["night_hag"]
    state.players["p1"].deck = ["advance_scout", "soldier", "noble"]
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.board.nodes["site_a"].spies = {"p1", "p2"}

    played = apply(state, PlayCardMove(player_id="p1", card_id="night_hag", hand_index=0))
    option_two = apply(
        played,
        ResolveGenericChoiceMove(player_id="p1", source_card_id="night_hag", option_id="option_2"),
    )

    return_moves = [
        move
        for move in legal_moves(option_two)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "night_hag"
        and "spy_owner_id" in move.selection
    ]
    assert return_moves
    assert {str(move.selection["spy_owner_id"]) for move in return_moves} == {"p1"}

    return_spy_move = next(
        move
        for move in return_moves
        if move.selection.get("node_id") == "site_a" and move.selection.get("spy_owner_id") == "p1"
    )
    hand_before = len(option_two.players["p1"].hand)
    resolved = apply(option_two, return_spy_move)

    assert len(resolved.players["p1"].hand) == hand_before + 2
    assert "p1" not in resolved.board.nodes["site_a"].spies


def test_presence_includes_adjacent_troop() -> None:
    state = _base_state(seed=17)
    updated = state.model_copy(deep=True)
    updated.board.nodes["route_ab"].troop_slots[0] = "p1"

    assert has_presence(updated, "p1", "site_a")
    assert has_presence(updated, "p1", "site_blingdenfire")


def test_deploy_places_troop() -> None:
    state = _base_state(seed=19)
    updated = state.model_copy(deep=True)
    updated.resource_pool.power = 1

    deployed = apply(
        updated,
        DeployMove(
            player_id=updated.current_player_id,
            target_node_id="site_a",
            troop_count=1,
        ),
    )

    assert deployed.board.nodes["site_a"].troop_slots.count("p1") == 1
    assert deployed.players["p1"].barracks == updated.players["p1"].barracks - 1
    assert deployed.resource_pool.power == 0


def test_deploy_awards_score_when_barracks_are_empty() -> None:
    state = _base_state(seed=21)
    updated = state.model_copy(deep=True)
    updated.resource_pool.power = 1
    updated.players["p1"].barracks = 0

    deployed = apply(
        updated,
        DeployMove(
            player_id=updated.current_player_id,
            target_node_id="site_a",
            troop_count=1,
        ),
    )

    assert deployed.players["p1"].score == updated.players["p1"].score + 1
    assert deployed.board.nodes["site_a"].troop_slots == updated.board.nodes["site_a"].troop_slots


def test_deploy_can_place_troop_on_route() -> None:
    state = _base_state(seed=22)
    updated = state.model_copy(deep=True)
    updated.resource_pool.power = 1

    deployed = apply(
        updated,
        DeployMove(
            player_id=updated.current_player_id,
            target_node_id="route_ab",
            troop_count=1,
        ),
    )

    assert deployed.board.nodes["route_ab"].troop_slots == ["p1"]
    assert deployed.players["p1"].barracks == updated.players["p1"].barracks - 1
    assert deployed.resource_pool.power == 0


def test_deploy_rejects_targeting_full_route_slot() -> None:
    state = _base_state(seed=24)
    updated = state.model_copy(deep=True)
    updated.resource_pool.power = 1
    updated.board.nodes["route_ab"].troop_slots = ["p2"]

    with pytest.raises(IllegalMoveError, match="empty slot"):
        apply(
            updated,
            DeployMove(
                player_id=updated.current_player_id,
                target_node_id="route_ab",
                troop_count=1,
            ),
        )


def test_assassinate_removes_enemy_troop_and_records_trophy() -> None:
    state = _base_state(seed=23)
    updated = state.model_copy(deep=True)
    updated.resource_pool.power = 3
    updated.board.nodes["site_a"].troop_slots = ["p1", "p2", None]

    assassinated = apply(
        updated,
        AssassinateMove(
            player_id=updated.current_player_id,
            target_node_id="site_a",
            target_slot_index=1,
        ),
    )

    assert assassinated.board.nodes["site_a"].troop_slots == ["p1", None, None]
    assert assassinated.players["p1"].trophy_hall == ["p2"]
    assert assassinated.resource_pool.power == 0


def test_recruit_moves_market_card_to_discard_and_refills_slot() -> None:
    state = _base_state(seed=25)
    updated = state.model_copy(deep=True)
    updated.resource_pool.influence = 2
    recruited_card = updated.market.row[0]
    replacement_card = updated.market.deck[-1]

    recruited = apply(
        updated,
        RecruitMove(
            player_id=updated.current_player_id,
            market_slot=0,
        ),
    )

    assert recruited.players["p1"].discard_pile[-1] == recruited_card
    assert recruited.market.row[0] == replacement_card
    assert recruited.resource_pool.influence == 0


def test_return_spy_is_not_legal_without_card_effect() -> None:
    state = _base_state(seed=27)
    updated = state.model_copy(deep=True)
    updated.board.nodes["site_a"].spies.add("p1")
    updated.board.nodes["site_a"].spies.add("p2")
    updated.resource_pool.power = 3
    updated.board.nodes["site_a"].troop_slots = ["p1", None, None]

    moves = legal_moves(updated)

    assert all(not isinstance(move, ReturnSpyMove) for move in moves)


def test_apply_rejects_direct_return_spy_move() -> None:
    state = _base_state(seed=29)
    updated = state.model_copy(deep=True)
    updated.resource_pool.power = 3
    updated.board.nodes["site_a"].troop_slots = ["p1", None, None]
    updated.board.nodes["site_a"].spies.add("p2")

    with pytest.raises(IllegalMoveError, match="card effect"):
        apply(
            updated,
            ReturnSpyMove(
                player_id=updated.current_player_id,
                node_id="site_a",
                spy_owner_id="p2",
            ),
        )


def test_apply_rejects_direct_return_spy_move_on_route_nodes() -> None:
    state = _base_state(seed=30)
    updated = state.model_copy(deep=True)
    updated.board.nodes["route_ab"].spies.add("p1")

    with pytest.raises(IllegalMoveError, match="card effect"):
        apply(
            updated,
            ReturnSpyMove(
                player_id=updated.current_player_id,
                node_id="route_ab",
                spy_owner_id="p1",
            ),
        )


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


def test_immediate_optional_promote_blocks_further_play_until_resolved() -> None:
    cards = [
        {
            "card_id": "optional_promote",
            "name": "Optional Promote",
            "cost": 0,
            "aspect": "none",
            "deck_vp": 0,
            "inner_circle_vp": 1,
            "effect_key": "noop",
            "effect_payload": {"promote": {"timing": "immediate", "optional": True}},
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
    state = _ability_state(cards, [{"card_id": "optional_promote", "count": 1}, {"card_id": "filler", "count": 1}])
    state.players["p1"].hand = ["optional_promote", "filler"]
    state.players["p1"].deck = []

    played = apply(
        state,
        PlayCardMove(player_id="p1", card_id="optional_promote", hand_index=0),
    )

    assert len(played.pending_immediate_promotions) == 1
    assert all(not isinstance(move, PlayCardMove) for move in legal_moves(played))

    promoted = apply(
        played,
        PromoteCardMove(player_id="p1", card_id="optional_promote"),
    )

    assert promoted.pending_immediate_promotions == []
    assert promoted.players["p1"].inner_circle == ["optional_promote"]
    assert "optional_promote" not in promoted.players["p1"].played_cards


def test_end_of_turn_mandatory_promote_moves_card_to_inner_circle() -> None:
    cards = [
        {
            "card_id": "end_promote",
            "name": "End Promote",
            "cost": 0,
            "aspect": "none",
            "deck_vp": 0,
            "inner_circle_vp": 1,
            "effect_key": "noop",
            "effect_payload": {"promote": {"timing": "end_of_turn", "optional": False}},
        }
    ]
    state = _ability_state(cards, [{"card_id": "end_promote", "count": 1}])
    state.players["p1"].hand = ["end_promote"]
    state.players["p1"].deck = []

    played = apply(
        state,
        PlayCardMove(player_id="p1", card_id="end_promote", hand_index=0),
    )
    end_of_turn = apply(played, EndMainPhaseMove(player_id="p1"))

    assert end_of_turn.phase == TurnPhase.END_OF_TURN
    assert end_of_turn.players["p1"].inner_circle == ["end_promote"]
    assert "end_promote" not in end_of_turn.players["p1"].played_cards


def test_ambassador_with_no_other_played_card_does_not_soft_lock() -> None:
    state = _base_state(seed=31)
    updated = state.model_copy(deep=True)
    updated.players["p1"].hand = ["ambassador"]
    updated.players["p1"].played_cards = []
    updated.players["p1"].deck = []

    played = apply(
        updated,
        PlayCardMove(player_id="p1", card_id="ambassador", hand_index=0),
    )

    assert played.pending_generic_choice is None
    assert len(played.pending_end_of_turn_promotions) == 1
    assert played.pending_end_of_turn_promotions[0].deferred_choice
    assert any(isinstance(move, EndMainPhaseMove) for move in legal_moves(played))

    end_of_turn = apply(played, EndMainPhaseMove(player_id="p1"))
    end_moves = legal_moves(end_of_turn)
    assert any(isinstance(move, SkipPromoteMove) for move in end_moves)


def test_ambassador_promotion_target_is_chosen_in_end_of_turn_phase() -> None:
    state = _base_state(seed=41)
    updated = state.model_copy(deep=True)
    updated.players["p1"].hand = ["ambassador", "noble"]
    updated.players["p1"].played_cards = []
    updated.players["p1"].deck = []

    after_ambassador = apply(
        updated,
        PlayCardMove(player_id="p1", card_id="ambassador", hand_index=0),
    )

    assert after_ambassador.pending_generic_choice is None
    assert len(after_ambassador.pending_end_of_turn_promotions) == 1
    pending = after_ambassador.pending_end_of_turn_promotions[0]
    assert pending.deferred_choice
    assert pending.requires_another_played_card

    after_second_card = apply(
        after_ambassador,
        PlayCardMove(player_id="p1", card_id="noble", hand_index=0),
    )
    end_of_turn = apply(after_second_card, EndMainPhaseMove(player_id="p1"))

    assert end_of_turn.phase == TurnPhase.END_OF_TURN
    end_moves = legal_moves(end_of_turn)
    promote_targets = [move.card_id for move in end_moves if isinstance(move, PromoteCardMove)]
    assert "noble" in promote_targets
    assert "ambassador" not in promote_targets

    promoted = apply(end_of_turn, PromoteCardMove(player_id="p1", card_id="noble"))

    assert "noble" in promoted.players["p1"].inner_circle
    assert "noble" not in promoted.players["p1"].played_cards
    assert promoted.pending_end_of_turn_promotions == []
    assert any(move.move_type == "resolve_end_of_turn" for move in legal_moves(promoted))


def test_end_main_phase_skips_stale_mandatory_promotions() -> None:
    state = _base_state(seed=37)
    updated = state.model_copy(deep=True)
    updated.players["p1"].played_cards = []
    updated.pending_end_of_turn_promotions = [
        PendingPromotionState(card_id="noble", timing="end_of_turn", optional=False)
    ]

    end_of_turn = apply(updated, EndMainPhaseMove(player_id="p1"))

    assert end_of_turn.phase == TurnPhase.END_OF_TURN
    assert end_of_turn.pending_end_of_turn_promotions == []


def test_all_end_of_turn_promote_actions_use_deferred_target_selection_policy() -> None:
    state = _base_state(seed=43)
    actions = [
        action
        for card in state.definition.catalog.cards
        for action in card.actions
        if action.op == "promote_card" and action.timing == "end_of_turn"
    ]

    assert actions
    assert all(_action_requires_selection(action) is False for action in actions)


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


def test_ogre_zombie_can_supplant_white_without_presence() -> None:
    state = _base_state(seed=801).model_copy(deep=True)
    state.players["p1"].hand = ["ogre_zombie"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.players["p1"].barracks = 5
    state.board.nodes["site_a"].troop_slots = [None, None, None]
    state.board.nodes["site_blingdenfire"].troop_slots = ["white", None, None]
    state.board.nodes["site_a"].spies = set()
    state.board.nodes["site_blingdenfire"].spies = set()

    played = apply(state, PlayCardMove(player_id="p1", card_id="ogre_zombie", hand_index=0))
    supplant_move = next(
        move
        for move in legal_moves(played)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "ogre_zombie"
        and move.selection.get("target_node_id") == "site_blingdenfire"
        and move.selection.get("target_slot_index") == 0
    )

    resolved = apply(played, supplant_move)

    assert resolved.board.nodes["site_blingdenfire"].troop_slots[0] == "p1"
    assert resolved.players["p1"].trophy_hall == []


def test_master_of_melee_magthere_anywhere_mode_targets_white_without_presence() -> None:
    state = _base_state(seed=802).model_copy(deep=True)
    state.players["p1"].hand = ["master_of_melee_magthere"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.players["p1"].barracks = 5
    state.board.nodes["site_a"].troop_slots = [None, None, None]
    state.board.nodes["site_blingdenfire"].troop_slots = ["white", None, None]
    state.board.nodes["site_a"].spies = set()
    state.board.nodes["site_blingdenfire"].spies = set()

    played = apply(state, PlayCardMove(player_id="p1", card_id="master_of_melee_magthere", hand_index=0))
    chose_mode = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="master_of_melee_magthere",
            option_id="option_2",
        ),
    )
    supplant_move = next(
        move
        for move in legal_moves(chose_mode)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "master_of_melee_magthere"
        and move.selection.get("target_node_id") == "site_blingdenfire"
        and move.selection.get("target_slot_index") == 0
    )

    resolved = apply(chose_mode, supplant_move)

    assert resolved.board.nodes["site_blingdenfire"].troop_slots[0] == "p1"
    assert resolved.players["p1"].trophy_hall == []


def test_black_dragon_scales_vp_from_white_trophies_only() -> None:
    state = _base_state(seed=803).model_copy(deep=True)
    state.players["p1"].hand = ["black_dragon"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.players["p1"].trophy_hall = ["white", "white", "white", "p2"]
    state.players["p1"].score = 0
    state.players["p1"].barracks = 5
    state.board.nodes["site_blingdenfire"].troop_slots = ["white", None, None]
    state.board.nodes["site_a"].troop_slots = [None, None, None]
    state.board.nodes["site_a"].spies = set()
    state.board.nodes["site_blingdenfire"].spies = set()

    played = apply(state, PlayCardMove(player_id="p1", card_id="black_dragon", hand_index=0))
    supplant_move = next(
        move
        for move in legal_moves(played)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "black_dragon"
        and move.selection.get("target_node_id") == "site_blingdenfire"
        and move.selection.get("target_slot_index") == 0
    )
    resolved = apply(played, supplant_move)

    assert resolved.players["p1"].score == 1


def test_death_knight_scales_vp_from_non_white_trophies() -> None:
    state = _base_state(seed=804).model_copy(deep=True)
    state.players["p1"].hand = ["death_knight"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.players["p1"].trophy_hall = ["p2", "p2", "p2", "p2", "p2", "white", "white"]
    state.players["p1"].score = 0
    state.players["p1"].barracks = 5
    state.board.nodes["site_a"].troop_slots = ["p1", "p2", None]
    state.board.nodes["site_a"].spies = set()

    played = apply(state, PlayCardMove(player_id="p1", card_id="death_knight", hand_index=0))
    supplant_move = next(
        move
        for move in legal_moves(played)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "death_knight"
        and move.selection.get("target_node_id") == "site_a"
        and move.selection.get("target_slot_index") == 1
    )
    resolved = apply(played, supplant_move)

    assert resolved.players["p1"].score == 1


def test_white_dragon_scales_vp_from_controlled_sites_not_markers_only() -> None:
    state = _base_state(seed=805).model_copy(deep=True)
    state.players["p1"].hand = ["white_dragon"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.players["p1"].score = 0
    state.players["p1"].barracks = 5

    state.board.nodes["site_a"].troop_slots = ["p1", None, None]
    state.board.nodes["site_blingdenfire"].troop_slots = ["p1", None, None]
    state.board.nodes["site_chasmleap_bridge"].troop_slots = ["p1", None, None]
    state.board.nodes["site_everfire"].troop_slots = [None, None, None]

    played = apply(state, PlayCardMove(player_id="p1", card_id="white_dragon", hand_index=0))
    current = played
    for target_node_id in ["site_a", "site_blingdenfire", "site_chasmleap_bridge"]:
        deploy_move = next(
            move
            for move in legal_moves(current)
            if isinstance(move, ResolveGenericChoiceMove)
            and move.source_card_id == "white_dragon"
            and move.selection.get("target_node_id") == target_node_id
        )
        current = apply(current, deploy_move)

    assert current.players["p1"].score == 1


def test_revenant_threshold_self_promote_triggers_at_eight_trophies() -> None:
    state = _base_state(seed=806).model_copy(deep=True)
    state.players["p1"].hand = ["revenant"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.players["p1"].trophy_hall = ["white", "white", "white", "white", "p2", "p2", "p2", "p2"]
    state.players["p1"].barracks = 5
    state.board.nodes["site_a"].troop_slots = ["p1", "p2", "p2"]

    played = apply(state, PlayCardMove(player_id="p1", card_id="revenant", hand_index=0))
    first = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="revenant",
            selection={"target_node_id": "site_a", "target_slot_index": 1},
        ),
    )
    resolved = apply(
        first,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="revenant",
            selection={"target_node_id": "site_a", "target_slot_index": 2},
        ),
    )

    assert "revenant" in resolved.players["p1"].inner_circle
    assert "revenant" not in resolved.players["p1"].played_cards


def test_blue_dragon_awards_scaled_vp_after_end_of_turn_promotions() -> None:
    state = _base_state(seed=807).model_copy(deep=True)
    state.players["p1"].hand = ["blue_dragon", "noble", "soldier"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.players["p1"].inner_circle = ["noble", "soldier", "house_guard", "priestess_of_lolth"]
    state.players["p1"].score = 0

    after_dragon = apply(state, PlayCardMove(player_id="p1", card_id="blue_dragon", hand_index=0))
    after_noble = apply(after_dragon, PlayCardMove(player_id="p1", card_id="noble", hand_index=0))
    after_soldier = apply(after_noble, PlayCardMove(player_id="p1", card_id="soldier", hand_index=0))

    end_of_turn = apply(after_soldier, EndMainPhaseMove(player_id="p1"))
    first_promote = apply(end_of_turn, PromoteCardMove(player_id="p1", card_id="noble"))
    second_promote = apply(first_promote, PromoteCardMove(player_id="p1", card_id="soldier"))
    score_before_resolve = second_promote.players["p1"].score
    resolve_move = next(move for move in legal_moves(second_promote) if move.move_type == "resolve_end_of_turn")
    resolved = apply(second_promote, resolve_move)

    assert resolved.players["p1"].score >= score_before_resolve + 2


def test_high_priest_of_myrkul_promotes_any_number_of_undead_played_cards() -> None:
    state = _base_state(seed=808).model_copy(deep=True)
    state.players["p1"].hand = ["high_priest_of_myrkul", "ogre_zombie", "noble"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.players["p1"].barracks = 5
    state.board.nodes["site_a"].troop_slots = [None, None, None]
    state.board.nodes["site_blingdenfire"].troop_slots = ["p2", None, None]

    after_priest = apply(state, PlayCardMove(player_id="p1", card_id="high_priest_of_myrkul", hand_index=0))
    return_move = next(
        move
        for move in legal_moves(after_priest)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "high_priest_of_myrkul"
        and move.selection.get("unit_type") == "troop"
    )
    after_return = apply(after_priest, return_move)
    after_ogre = apply(after_return, PlayCardMove(player_id="p1", card_id="ogre_zombie", hand_index=0))
    ogre_supplant = next(
        move
        for move in legal_moves(after_ogre)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "ogre_zombie"
    )
    after_ogre_resolved = apply(after_ogre, ogre_supplant)
    after_noble = apply(after_ogre_resolved, PlayCardMove(player_id="p1", card_id="noble", hand_index=0))

    end_of_turn = apply(after_noble, EndMainPhaseMove(player_id="p1"))
    promote_moves = [move for move in legal_moves(end_of_turn) if isinstance(move, PromoteCardMove)]
    assert {move.card_id for move in promote_moves} == {"ogre_zombie"}

    promoted = apply(end_of_turn, PromoteCardMove(player_id="p1", card_id="ogre_zombie"))
    assert "ogre_zombie" in promoted.players["p1"].inner_circle
    assert "noble" in promoted.players["p1"].played_cards
    assert promoted.pending_end_of_turn_promotions == []


def test_ogremoch_grants_second_end_of_turn_promote_when_focus_met() -> None:
    state = _base_state(seed=809).model_copy(deep=True)
    state.players["p1"].hand = ["ogremoch", "ambassador", "noble", "soldier"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []

    after_ogremoch = apply(state, PlayCardMove(player_id="p1", card_id="ogremoch", hand_index=0))
    after_noble = apply(after_ogremoch, PlayCardMove(player_id="p1", card_id="noble", hand_index=1))
    after_soldier = apply(after_noble, PlayCardMove(player_id="p1", card_id="soldier", hand_index=1))

    end_of_turn = apply(after_soldier, EndMainPhaseMove(player_id="p1"))
    first = apply(end_of_turn, PromoteCardMove(player_id="p1", card_id="noble"))
    second = apply(first, PromoteCardMove(player_id="p1", card_id="soldier"))

    assert "noble" in second.players["p1"].inner_circle
    assert "soldier" in second.players["p1"].inner_circle


def test_mummy_lord_custom_effect_moves_white_trophy_to_board_slot() -> None:
    state = _base_state(seed=810).model_copy(deep=True)
    state.players["p1"].hand = ["mummy_lord"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.players["p2"].trophy_hall = ["white", "p1"]
    state.board.nodes["site_a"].troop_slots = [None, None, None]

    played = apply(state, PlayCardMove(player_id="p1", card_id="mummy_lord", hand_index=0))
    chose_custom_mode = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="mummy_lord",
            option_id="option_2",
        ),
    )
    custom_move = next(
        move
        for move in legal_moves(chose_custom_mode)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "mummy_lord"
        and move.selection.get("target_player_id") == "p2"
        and move.selection.get("target_node_id") == "site_a"
        and move.selection.get("target_slot_index") == 0
    )

    resolved = apply(chose_custom_mode, custom_move)

    assert "white" not in resolved.players["p2"].trophy_hall
    assert resolved.board.nodes["site_a"].troop_slots[0] == "white"


# ---------------------------------------------------------------------------
# _count_controlled_sites_by_troops
# ---------------------------------------------------------------------------


def test_count_controlled_sites_by_troops_unique_majority() -> None:
    from engine.rules import _count_controlled_sites_by_troops

    state = _base_state(seed=900).model_copy(deep=True)
    state.board.nodes["site_a"].troop_slots = ["p1", None, None]
    state.board.nodes["site_blingdenfire"].troop_slots = ["p1", "p1", None]

    count = _count_controlled_sites_by_troops(state, "p1")
    assert count == 2


def test_count_controlled_sites_by_troops_tie_not_controlled() -> None:
    from engine.rules import _count_controlled_sites_by_troops

    state = _base_state(seed=901).model_copy(deep=True)
    state.board.nodes["site_a"].troop_slots = ["p1", "p2", None]

    count = _count_controlled_sites_by_troops(state, "p1")
    assert count == 0


def test_count_controlled_sites_by_troops_white_not_controlled() -> None:
    from engine.rules import _count_controlled_sites_by_troops

    state = _base_state(seed=902).model_copy(deep=True)
    state.board.nodes["site_a"].troop_slots = ["white", "white", "white"]

    count = _count_controlled_sites_by_troops(state, "p1")
    assert count == 0


def test_count_controlled_sites_by_troops_empty_slot_is_controlled() -> None:
    from engine.rules import _count_controlled_sites_by_troops

    state = _base_state(seed=903).model_copy(deep=True)
    state.board.nodes["site_a"].troop_slots = ["p1", None, None]

    count = _count_controlled_sites_by_troops(state, "p1")
    assert count == 1


def test_count_controlled_sites_by_troops_ignores_routes() -> None:
    from engine.rules import _count_controlled_sites_by_troops

    state = _base_state(seed=904).model_copy(deep=True)
    state.board.nodes["route_ab"].troop_slots = ["p1"]

    count = _count_controlled_sites_by_troops(state, "p1")
    assert count == 0


def test_count_controlled_sites_by_troops_player_beats_white() -> None:
    from engine.rules import _count_controlled_sites_by_troops

    state = _base_state(seed=905).model_copy(deep=True)
    state.board.nodes["site_a"].troop_slots = ["p1", "p1", "white"]

    count = _count_controlled_sites_by_troops(state, "p1")
    assert count == 1


def test_count_controlled_sites_by_troops_multiple_players() -> None:
    from engine.rules import _count_controlled_sites_by_troops

    state = _base_state(seed=906).model_copy(deep=True)
    state.board.nodes["site_a"].troop_slots = ["p1", "p1", "p1"]
    state.board.nodes["site_blingdenfire"].troop_slots = ["p2", None]
    state.board.nodes["site_chasmleap_bridge"].troop_slots = ["p2", None]
    state.board.nodes["site_everfire"].troop_slots = []

    p1_count = _count_controlled_sites_by_troops(state, "p1")
    p2_count = _count_controlled_sites_by_troops(state, "p2")

    assert p1_count == 1
    assert p2_count == 2
