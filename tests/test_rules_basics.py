"""Core rules behavior tests for known implemented surfaces."""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.errors import IllegalMoveError
from engine.moves import (
    AssassinateMove,
    DeployMove,
    PlayCardMove,
    RecruitMove,
    ResolveGenericChoiceMove,
    ReturnSpyMove,
)
from engine.rules import apply, has_presence, legal_moves
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



def test_presence_includes_adjacent_troop() -> None:
    state = _base_state(seed=17)
    updated = state.model_copy(deep=True)
    updated.board.nodes["route_1"].troop_slots[0] = "p1"

    assert has_presence(updated, "p1", "site_gauntlgrym")
    assert has_presence(updated, "p1", "site_the_wormwrithings")



def test_deploy_places_troop_and_updates_control_marker() -> None:
    state = _base_state(seed=19)
    updated = state.model_copy(deep=True)
    updated.resource_pool.power = 1

    deployed = apply(
        updated,
        DeployMove(
            player_id=updated.current_player_id,
            target_node_id="site_gauntlgrym",
            troop_count=1,
        ),
    )

    assert deployed.board.nodes["site_gauntlgrym"].troop_slots.count("p1") == 1
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
            target_node_id="site_gauntlgrym",
            troop_count=1,
        ),
    )

    assert deployed.players["p1"].score == updated.players["p1"].score + 1
    assert deployed.board.nodes["site_gauntlgrym"].troop_slots == updated.board.nodes["site_gauntlgrym"].troop_slots



def test_deploy_can_place_troop_on_route() -> None:
    state = _base_state(seed=22)
    updated = state.model_copy(deep=True)
    updated.resource_pool.power = 1

    deployed = apply(
        updated,
        DeployMove(
            player_id=updated.current_player_id,
            target_node_id="route_1",
            troop_count=1,
        ),
    )

    assert deployed.board.nodes["route_1"].troop_slots == ["p1"]
    assert deployed.players["p1"].barracks == updated.players["p1"].barracks - 1
    assert deployed.resource_pool.power == 0



def test_deploy_rejects_targeting_full_route_slot() -> None:
    state = _base_state(seed=24)
    updated = state.model_copy(deep=True)
    updated.resource_pool.power = 1
    updated.board.nodes["route_1"].troop_slots = ["p2"]

    with pytest.raises(IllegalMoveError, match="empty slot"):
        apply(
            updated,
            DeployMove(
                player_id=updated.current_player_id,
                target_node_id="route_1",
                troop_count=1,
            ),
        )



def test_assassinate_removes_enemy_troop_and_records_trophy() -> None:
    state = _base_state(seed=23)
    updated = state.model_copy(deep=True)
    updated.resource_pool.power = 3
    updated.board.nodes["site_gauntlgrym"].troop_slots = ["p1", "p2", None]

    assassinated = apply(
        updated,
        AssassinateMove(
            player_id=updated.current_player_id,
            target_node_id="site_gauntlgrym",
            target_slot_index=1,
        ),
    )

    assert assassinated.board.nodes["site_gauntlgrym"].troop_slots == ["p1", None, None]
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



def test_enemy_spy_return_is_legal_with_power_and_presence() -> None:
    state = _base_state(seed=27)
    updated = state.model_copy(deep=True)
    updated.board.nodes["site_gauntlgrym"].spies.add("p1")
    updated.board.nodes["site_gauntlgrym"].spies.add("p2")
    updated.resource_pool.power = 3
    updated.board.nodes["site_gauntlgrym"].troop_slots = ["p1", None, None]

    moves = legal_moves(updated)
    return_moves = [m for m in moves if isinstance(m, ReturnSpyMove)]

    assert len(return_moves) == 1
    assert return_moves[0].spy_owner_id == "p2"



def test_return_own_spy_is_not_legal_without_card() -> None:
    state = _base_state(seed=27)
    updated = state.model_copy(deep=True)
    updated.board.nodes["site_gauntlgrym"].spies.add("p1")
    updated.resource_pool.power = 3
    updated.board.nodes["site_gauntlgrym"].troop_slots = ["p1", None, None]

    moves = legal_moves(updated)
    return_moves = [m for m in moves if isinstance(m, ReturnSpyMove)]

    assert len(return_moves) == 0



def test_apply_enemy_spy_return_deducts_power_and_returns_spy() -> None:
    state = _base_state(seed=29)
    updated = state.model_copy(deep=True)
    updated.resource_pool.power = 3
    updated.board.nodes["site_gauntlgrym"].troop_slots = ["p1", None, None]
    updated.board.nodes["site_gauntlgrym"].spies.add("p2")
    spies_before = updated.players["p2"].spies_available

    resolved = apply(
        updated,
        ReturnSpyMove(
            player_id=updated.current_player_id,
            node_id="site_gauntlgrym",
            spy_owner_id="p2",
        ),
    )

    assert "p2" not in resolved.board.nodes["site_gauntlgrym"].spies
    assert resolved.players["p2"].spies_available == spies_before + 1
    assert resolved.resource_pool.power == 0



def test_apply_rejects_enemy_spy_return_insufficient_power() -> None:
    state = _base_state(seed=30)
    updated = state.model_copy(deep=True)
    updated.resource_pool.power = 2
    updated.board.nodes["site_gauntlgrym"].troop_slots = ["p1", None, None]
    updated.board.nodes["site_gauntlgrym"].spies.add("p2")

    with pytest.raises(IllegalMoveError, match="requires 3 power"):
        apply(
            updated,
            ReturnSpyMove(
                player_id=updated.current_player_id,
                node_id="site_gauntlgrym",
                spy_owner_id="p2",
            ),
        )



def test_apply_rejects_enemy_spy_return_without_presence() -> None:
    state = _base_state(seed=31)
    updated = state.model_copy(deep=True)
    updated.resource_pool.power = 3
    updated.board.nodes["site_gauntlgrym"].troop_slots = [None, None, None]
    updated.board.nodes["site_gauntlgrym"].spies.add("p2")

    with pytest.raises(IllegalMoveError, match="presence"):
        apply(
            updated,
            ReturnSpyMove(
                player_id=updated.current_player_id,
                node_id="site_gauntlgrym",
                spy_owner_id="p2",
            ),
        )



def test_apply_rejects_own_spy_return_without_card() -> None:
    state = _base_state(seed=32)
    updated = state.model_copy(deep=True)
    updated.resource_pool.power = 3
    updated.board.nodes["site_gauntlgrym"].troop_slots = ["p1", None, None]
    updated.board.nodes["site_gauntlgrym"].spies.add("p1")

    with pytest.raises(IllegalMoveError, match="own spy can only be done through a card effect"):
        apply(
            updated,
            ReturnSpyMove(
                player_id=updated.current_player_id,
                node_id="site_gauntlgrym",
                spy_owner_id="p1",
            ),
        )



def test_apply_rejects_return_spy_on_route_nodes() -> None:
    state = _base_state(seed=33)
    updated = state.model_copy(deep=True)
    updated.board.nodes["route_1"].spies.add("p1")

    with pytest.raises(IllegalMoveError, match="own spy can only be done through a card effect"):
        apply(
            updated,
            ReturnSpyMove(
                player_id=updated.current_player_id,
                node_id="route_1",
                spy_owner_id="p1",
            ),
        )



def test_ogre_zombie_can_supplant_white_without_presence() -> None:
    state = _base_state(seed=801).model_copy(deep=True)
    state.players["p1"].hand = ["ogre_zombie"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.players["p1"].barracks = 5
    state.board.nodes["site_gauntlgrym"].troop_slots = [None, None, None]
    state.board.nodes["site_blingdenfire"].troop_slots = ["white", None, None]
    state.board.nodes["site_gauntlgrym"].spies = set()
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
    state.board.nodes["site_gauntlgrym"].troop_slots = [None, None, None]
    state.board.nodes["site_blingdenfire"].troop_slots = ["white", None, None]
    state.board.nodes["site_gauntlgrym"].spies = set()
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


