"""Shared fixtures for the NN encoder tests.

``mid_game_adapter`` mirrors ``test_observation_completeness._mid_game_state``;
``pending_gauth_session`` reuses ``make_card_test_session`` so the pending-op
block can be exercised deterministically.
"""

from __future__ import annotations

import numpy as np
import pyspiel
import pytest

import openspiel_pyrants  # noqa: F401
from engine_c.bindings.c_adapter import CEngineAdapter
from tests.c_engine.card_test_helpers import _make_engine, make_card_test_session


def _load_c_game(num_players: int = 2):
    return pyspiel.load_game("python_pyrants_c", {"num_players": str(num_players)})


def _mid_game_state(game, shuffle_seed: int = 42, n_moves: int = 40):
    state = game.new_initial_state()
    state.apply_action(shuffle_seed)
    rng = np.random.RandomState(shuffle_seed)
    for _ in range(n_moves):
        if state.is_terminal():
            break
        cp = state.current_player()
        if cp < 0:
            break
        legal = state.legal_actions()
        if not legal:
            break
        state.apply_action(int(rng.choice(legal)))
    return state


_KEEPALIVE: list = []


@pytest.fixture
def mid_game_adapter():
    def factory(num_players: int = 2, seed: int = 42, n_moves: int = 40):
        game = _load_c_game(num_players)
        state = _mid_game_state(game, shuffle_seed=seed, n_moves=n_moves)
        # The OpenSpiel state owns the C adapter and destroys it in __del__;
        # keep it alive for the adapter's lifetime.
        _KEEPALIVE.append(state)
        return state._adapter

    return factory


@pytest.fixture
def adapter_from_session():
    def factory(session):
        return CEngineAdapter(
            session._state, session._engine, session._player_ids, session._seed
        )

    return factory


@pytest.fixture
def pending_gauth_session():
    engine = _make_engine()
    session = make_card_test_session(
        engine, ["p1", "p2"], hand={"p1": ["gauth"]}, current_player="p1"
    )
    for move in session.legal_moves():
        if move.move_type == "play_card" and move.data.get("card_id") == "gauth":
            session.submit_move(move)
            break
    return session
