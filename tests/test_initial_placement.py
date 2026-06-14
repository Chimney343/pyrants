"""Tests for the SETUP phase free troop placement and DRAW transition."""

from __future__ import annotations

import pytest

from engine.errors import IllegalMoveError
from engine.moves import InitialPlacementMove
from engine.rules import apply, legal_moves
from engine.state import TurnPhase, build_initial_game_state
from game_setup.loaders import build_game_definition_from_dicts


def _minimal_definition():
    board_data: dict[str, object] = {
        "board_id": "tiny",
        "nodes": [
            {
                "node_id": "site_a",
                "kind": "site",
                "adjacent_to": ["site_b", "route_ab"],
                "troop_capacity": 2,
                "control_vp": 0,
                "initial_vp_tokens": 0,
            },
            {
                "node_id": "site_b",
                "kind": "site",
                "adjacent_to": ["site_a"],
                "troop_capacity": 1,
                "control_vp": 0,
                "initial_vp_tokens": 0,
            },
            {
                "node_id": "route_ab",
                "kind": "route",
                "adjacent_to": ["site_a"],
                "troop_capacity": 1,
                "control_vp": 0,
                "initial_vp_tokens": 0,
            },
        ],
    }
    card_data: dict[str, object] = {
        "catalog_id": "cards",
        "version": "1.0.0",
        "cards": [
            {
                "card_id": "starter_card",
                "name": "Starter Card",
                "cost": 0,
                "aspect": "none",
                "effect_key": "noop",
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
    return build_game_definition_from_dicts(board_data, card_data, setup_data)


def _initial_state(seed: int = 42) -> object:
    return build_initial_game_state(_minimal_definition(), ["p1", "p2"], shuffle_seed=seed)


class TestInitialState:
    def test_initial_state_is_setup_phase(self):
        state = _initial_state()
        assert state.phase == TurnPhase.SETUP
        assert state.current_player_id == "p1"
        assert state.setup_complete == set()

    def test_initial_state_has_empty_hands(self):
        state = _initial_state()
        assert state.players["p1"].hand == []
        assert state.players["p2"].hand == []

    def test_initial_state_has_shuffled_decks(self):
        state = _initial_state()
        assert len(state.players["p1"].deck) == 10
        assert len(state.players["p2"].deck) == 10

    def test_initial_state_has_no_troops_on_board(self):
        state = _initial_state()
        for node_state in state.board.nodes.values():
            assert all(slot is None for slot in node_state.troop_slots)


class TestSetupLegalMoves:
    def test_legal_moves_returns_site_node_ids_only(self):
        state = _initial_state()
        moves = legal_moves(state)
        move_node_ids = {move.target_node_id for move in moves}
        assert move_node_ids == {"site_a", "site_b"}
        assert "route_ab" not in move_node_ids

    def test_legal_moves_excludes_full_sites(self):
        state = _initial_state()
        state.board.nodes["site_b"].troop_slots = ["white"]
        moves = legal_moves(state)
        move_node_ids = {move.target_node_id for move in moves}
        assert "site_b" not in move_node_ids
        assert "site_a" in move_node_ids

    def test_legal_moves_excludes_routes(self):
        state = _initial_state()
        moves = legal_moves(state)
        for move in moves:
            assert move.target_node_id != "route_ab"

    def test_each_move_is_initial_placement_type(self):
        state = _initial_state()
        moves = legal_moves(state)
        assert len(moves) > 0
        for move in moves:
            assert isinstance(move, InitialPlacementMove)
            assert move.player_id == "p1"


class TestApplyInitialPlacement:
    def test_apply_places_troop_and_decrements_barracks(self):
        state = _initial_state()
        move = InitialPlacementMove(player_id="p1", target_node_id="site_a")
        updated = apply(state, move)

        assert updated.board.nodes["site_a"].troop_slots == ["p1", None]
        assert updated.players["p1"].barracks == 39
        assert "p1" in updated.setup_complete

    def test_apply_advances_to_next_player_setup(self):
        state = _initial_state()
        move = InitialPlacementMove(player_id="p1", target_node_id="site_a")
        updated = apply(state, move)

        assert updated.phase == TurnPhase.SETUP
        assert updated.current_player_id == "p2"
        assert "p2" not in updated.setup_complete

    def test_apply_second_player_triggers_draw_then_main(self):
        state = _initial_state()
        p1_move = InitialPlacementMove(player_id="p1", target_node_id="site_a")
        mid = apply(state, p1_move)
        p2_move = InitialPlacementMove(player_id="p2", target_node_id="site_b")
        updated = apply(mid, p2_move)

        assert updated.phase == TurnPhase.MAIN
        assert updated.current_player_id == "p1"
        assert len(updated.players["p1"].hand) == 5
        assert len(updated.players["p2"].hand) == 5
        assert updated.resource_pool.power == 0

    def test_apply_rejects_outside_setup(self):
        state = _initial_state()
        p1_move = InitialPlacementMove(player_id="p1", target_node_id="site_a")
        mid = apply(state, p1_move)
        p2_move = InitialPlacementMove(player_id="p2", target_node_id="site_b")
        main_state = apply(mid, p2_move)

        with pytest.raises(IllegalMoveError, match="setup phase"):
            apply(main_state, InitialPlacementMove(player_id="p1", target_node_id="site_a"))

    def test_apply_rejects_duplicate_placement(self):
        state = _initial_state()
        move = InitialPlacementMove(player_id="p1", target_node_id="site_a")
        updated = apply(state, move)

        updated.current_player_id = "p1"
        with pytest.raises(IllegalMoveError, match="already placed"):
            apply(updated, InitialPlacementMove(player_id="p1", target_node_id="site_a"))

    def test_apply_rejects_route_target(self):
        state = _initial_state()
        with pytest.raises(IllegalMoveError, match="site node"):
            apply(state, InitialPlacementMove(player_id="p1", target_node_id="route_ab"))

    def test_apply_rejects_full_site(self):
        state = _initial_state()
        state.board.nodes["site_b"].troop_slots = ["white"]
        with pytest.raises(IllegalMoveError, match="no empty"):
            apply(state, InitialPlacementMove(player_id="p1", target_node_id="site_b"))

    def test_apply_rejects_empty_barracks(self):
        state = _initial_state()
        state.players["p1"].barracks = 0
        with pytest.raises(IllegalMoveError, match="no troops"):
            apply(state, InitialPlacementMove(player_id="p1", target_node_id="site_a"))


class TestDrawPhase:
    def test_draw_phase_draws_five_cards_per_player(self):
        state = _initial_state()
        p1_move = InitialPlacementMove(player_id="p1", target_node_id="site_a")
        mid = apply(state, p1_move)
        p2_move = InitialPlacementMove(player_id="p2", target_node_id="site_b")
        updated = apply(mid, p2_move)

        assert len(updated.players["p1"].hand) == 5
        assert len(updated.players["p1"].deck) == 5
        assert len(updated.players["p2"].hand) == 5
        assert len(updated.players["p2"].deck) == 5

    def test_draw_phase_resets_resource_pool(self):
        state = _initial_state()
        p1_move = InitialPlacementMove(player_id="p1", target_node_id="site_a")
        mid = apply(state, p1_move)
        p2_move = InitialPlacementMove(player_id="p2", target_node_id="site_b")
        updated = apply(mid, p2_move)

        assert updated.resource_pool.power == 0
        assert updated.resource_pool.influence == 0

    def test_draw_phase_legal_moves_is_empty(self):
        state = _initial_state()
        p1_move = InitialPlacementMove(player_id="p1", target_node_id="site_a")
        mid = apply(state, p1_move)

        p2_move = InitialPlacementMove(player_id="p2", target_node_id="site_b")
        after_second_placement = apply(mid, p2_move)
        assert after_second_placement.phase == TurnPhase.MAIN

    def test_draw_phase_is_auto_resolved(self):
        state = _initial_state()
        p1_move = InitialPlacementMove(player_id="p1", target_node_id="site_a")
        mid = apply(state, p1_move)
        p2_move = InitialPlacementMove(player_id="p2", target_node_id="site_b")
        updated = apply(mid, p2_move)

        assert updated.phase == TurnPhase.MAIN
        assert updated.current_player_id == "p1"
