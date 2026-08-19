"""Per-state action encoding tests for the C engine backend."""

from __future__ import annotations

import pyspiel

import openspiel_pyrants  # noqa: F401
from openspiel_pyrants.action_encoding_c import NUM_DISTINCT_ACTIONS, compute_c_action_map


def _state_after_chance(seed: int = 42):
    game = pyspiel.load_game("python_pyrants_c")
    state = game.new_initial_state()
    state.apply_action(seed)
    return state


def test_num_distinct_actions() -> None:
    assert NUM_DISTINCT_ACTIONS == 1024


def test_compute_c_action_map_is_ordered(requires_c_engine) -> None:
    state = _state_after_chance()
    pairs = compute_c_action_map(state._adapter)
    assert len(pairs) > 0
    for index, pair in enumerate(pairs):
        assert pair[0] == index
        assert pair[1].move_type


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
