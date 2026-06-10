"""Round-trip tests for the per-state action encoding."""

from __future__ import annotations

from openspiel_pyrants.action_encoding import (
    action_to_move,
    enumerate_legal_actions,
    move_to_action_id,
)
from openspiel_pyrants.game import PyrantsGame


def _get_engine_state():
    game = PyrantsGame()
    from engine.state import build_initial_game_state
    return build_initial_game_state(
        game.get_definition(),
        game.get_player_ids(),
        shuffle_seed=42,
    )


def test_enumerate_returns_sorted_ids():
    state = _get_engine_state()
    ids = enumerate_legal_actions(state)
    assert len(ids) > 0
    assert ids == sorted(ids)
    assert ids[0] == 0
    assert ids[-1] == len(ids) - 1


def test_action_to_move_roundtrip():
    state = _get_engine_state()
    ids = enumerate_legal_actions(state)
    for action_id in ids:
        move = action_to_move(state, action_id)
        assert move is not None
        assert move.player_id in state.players


def test_move_to_action_id_roundtrip():
    state = _get_engine_state()
    ids = enumerate_legal_actions(state)
    for action_id in ids:
        move = action_to_move(state, action_id)
        back = move_to_action_id(state, move)
        assert back == action_id


def test_legal_actions_at_terminal_is_empty():
    import random
    game = PyrantsGame()
    pyspiel_state = game.new_initial_state()
    rng = random.Random(42)
    pyspiel_state._apply_action(0)
    while not pyspiel_state.is_terminal():
        actions = pyspiel_state.legal_actions()
        assert len(actions) > 0
        assert actions == sorted(actions)
        pyspiel_state._apply_action(rng.choice(actions))
    assert pyspiel_state.is_terminal()


def test_seed_hashing_hides_seed():
    from openspiel_pyrants.state import _public_to_seed

    game = PyrantsGame()
    n = game.get_shuffle_seed_count()
    internal_seeds = set()
    mismatches = 0

    for public_id in range(n):
        internal_seed = _public_to_seed(public_id)
        internal_seeds.add(internal_seed)
        if internal_seed != public_id:
            mismatches += 1

    assert len(internal_seeds) == n
    assert mismatches >= n - 1
