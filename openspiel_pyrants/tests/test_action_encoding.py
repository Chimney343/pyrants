"""Per-state action encoding tests for the C engine backend."""

from __future__ import annotations

import pyspiel

import openspiel_pyrants  # noqa: F401
from openspiel_pyrants.game_c import NUM_DISTINCT_ACTIONS


def _state_after_chance(seed: int = 42):
    game = pyspiel.load_game("python_pyrants_c")
    state = game.new_initial_state()
    state.apply_action(seed)
    return state


def test_num_distinct_actions() -> None:
    assert NUM_DISTINCT_ACTIONS == 1024


def test_legal_move_indexing_is_ordered(requires_c_engine) -> None:
    state = _state_after_chance()
    moves = state._adapter.legal_moves()
    assert len(moves) > 0
    assert state.legal_actions() == list(range(len(moves)))
    for index, move in enumerate(moves):
        decoded = state.decode_action(index)
        assert decoded is not None
        assert decoded.move_type == move.move_type
        assert decoded.to_payload() == move.to_payload()


def test_legal_actions_roundtrip_via_decode(requires_c_engine) -> None:
    state = _state_after_chance()
    legal = state.legal_actions()
    assert legal == sorted(legal)
    assert legal[0] == 0
    assert legal[-1] == len(legal) - 1
    for action_id in legal:
        move = state.decode_action(action_id)
        assert move is not None
        assert move.move_type
