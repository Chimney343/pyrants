"""Core rules behavior tests for known implemented surfaces."""

from __future__ import annotations

from pathlib import Path

from engine.moves import (
    EndMainPhaseMove,
    PlayCardMove,
    ResolveGenericChoiceMove,
)
from engine.rules import apply, legal_moves
from engine.state import TurnPhase, build_initial_game_state
from game_setup.loaders import build_game_definition_from_dicts, create_game_state_from_files
from tests.scenario_helpers import advance_past_setup

BASE_DIR = Path(__file__).resolve().parents[2]
BOARD_PATH = BASE_DIR / "data" / "boards" / "tyrants_of_the_underdark.json"
CARD_PATH = BASE_DIR / "data" / "cards" / "catalog.json"
SETUP_PATH = BASE_DIR / "data" / "decks" / "base_setup.json"


def _base_state(seed: int = 11):
    return advance_past_setup(
        create_game_state_from_files(BOARD_PATH, CARD_PATH, SETUP_PATH, ["p1", "p2"], seed=seed)
    )


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
    return advance_past_setup(build_initial_game_state(definition, ["p1", "p2"], shuffle_seed=0))


def test_white_wyrmling_deploys_two_before_market_devour_choice() -> None:
    state = _base_state(seed=29).model_copy(deep=True)
    state.players["p1"].hand = ["white_wyrmling"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.board.nodes["site_gauntlgrym"].troop_slots = [None, None, None]
    barracks_before = state.players["p1"].barracks

    played = apply(state, PlayCardMove(player_id="p1", card_id="white_wyrmling", hand_index=0))
    deploy_move = next(
        move
        for move in legal_moves(played)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "white_wyrmling"
        and move.selection.get("target_node_id") == "site_gauntlgrym"
    )
    after_first_deploy = apply(played, deploy_move)
    second_deploy_move = next(
        move
        for move in legal_moves(after_first_deploy)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "white_wyrmling"
        and move.selection.get("target_node_id") == "site_gauntlgrym"
    )
    deployed = apply(after_first_deploy, second_deploy_move)

    assert deployed.board.nodes["site_gauntlgrym"].troop_slots.count("p1") == 2
    assert deployed.players["p1"].barracks == barracks_before - 2

    follow_up_moves = [
        move
        for move in legal_moves(deployed)
        if isinstance(move, ResolveGenericChoiceMove) and move.source_card_id == "white_wyrmling"
    ]
    assert follow_up_moves
    assert any("market_slot" in move.selection for move in follow_up_moves)



def test_red_dragon_returns_enemy_spy_after_supplant() -> None:
    state = _base_state(seed=622).model_copy(deep=True)
    state.players["p1"].hand = ["red_dragon"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.board.nodes["site_gauntlgrym"].troop_slots = ["p1", "p2", None]
    state.board.nodes["site_gauntlgrym"].spies = {"p1", "p2"}
    spies_available_before = state.players["p2"].spies_available

    played = apply(state, PlayCardMove(player_id="p1", card_id="red_dragon", hand_index=0))
    supplant_move = next(
        move
        for move in legal_moves(played)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "red_dragon"
        and move.selection.get("target_node_id") == "site_gauntlgrym"
        and move.selection.get("target_slot_index") == 1
    )
    after_supplant = apply(played, supplant_move)

    return_spy_moves = [
        move
        for move in legal_moves(after_supplant)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "red_dragon"
        and move.selection.get("node_id") == "site_gauntlgrym"
    ]

    assert {str(move.selection["spy_owner_id"]) for move in return_spy_moves} == {"p2"}

    resolved = apply(after_supplant, return_spy_moves[0])

    assert "p2" not in resolved.board.nodes["site_gauntlgrym"].spies
    assert resolved.players["p2"].spies_available == spies_available_before + 1



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
    assert discard_action.timing == "immediate"



def test_neogi_discard_is_immediate_not_end_of_turn() -> None:
    state = _base_state(seed=86)
    card = next(card for card in state.definition.catalog.cards if card.card_id == "neogi")
    discard_action = card.execution_model.actions[1]
    assert discard_action.op == "force_discard"
    assert discard_action.timing == "immediate"
    assert discard_action.target_scope == "opponent"
    assert discard_action.source_fragment == "end_of_turn_mass_discard"



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
    state.board.nodes["site_gauntlgrym"].spies = {"p1", "p2"}

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
        if move.selection.get("node_id") == "site_gauntlgrym" and move.selection.get("spy_owner_id") == "p1"
    )
    hand_before = len(option_two.players["p1"].hand)
    resolved = apply(option_two, return_spy_move)

    assert len(resolved.players["p1"].hand) == hand_before + 2
    assert "p1" not in resolved.board.nodes["site_gauntlgrym"].spies



def test_white_dragon_scales_vp_from_controlled_sites_not_markers_only() -> None:
    state = _base_state(seed=805).model_copy(deep=True)
    state.players["p1"].hand = ["white_dragon"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.players["p1"].score = 0
    state.players["p1"].barracks = 5

    state.board.nodes["site_gauntlgrym"].troop_slots = ["p1", None, None]
    state.board.nodes["site_blingdenfire"].troop_slots = ["p1", None, None]
    state.board.nodes["site_chasmleap_bridge"].troop_slots = ["p1", None, None]
    state.board.nodes["site_everfire"].troop_slots = [None, None, None]

    played = apply(state, PlayCardMove(player_id="p1", card_id="white_dragon", hand_index=0))
    current = played
    for target_node_id in ["site_gauntlgrym", "site_blingdenfire", "site_chasmleap_bridge"]:
        deploy_move = next(
            move
            for move in legal_moves(current)
            if isinstance(move, ResolveGenericChoiceMove)
            and move.source_card_id == "white_dragon"
            and move.selection.get("target_node_id") == target_node_id
        )
        current = apply(current, deploy_move)

    assert current.players["p1"].score == 1


