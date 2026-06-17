"""Resample determinization tests for the C engine backend."""

from __future__ import annotations

import copy
import pyspiel
import pytest

import openspiel_pyrants  # noqa: F401


def _state_after_n_moves(game_name, seed=42, n=3):
    game = pyspiel.load_game(game_name)
    state = game.new_initial_state()
    state.apply_action(seed)
    for _ in range(n):
        if state.is_terminal():
            break
        legal = state.legal_actions()
        state.apply_action(legal[0])
    return state


class TestResampleC:
    def test_resample_returns_state(self, requires_c_engine):
        state = _state_after_n_moves("python_pyrants_c", seed=42, n=3)
        cp = state.current_player()
        if cp == pyspiel.PlayerId.TERMINAL:
            pytest.skip("Game ended too early")
        import numpy as np
        rng = np.random.RandomState(123)
        sampled = state.resample_from_infostate(cp, rng)
        assert sampled is not None

    def test_resample_preserves_current_player(self, requires_c_engine):
        state = _state_after_n_moves("python_pyrants_c", seed=42, n=3)
        cp = state.current_player()
        if cp == pyspiel.PlayerId.TERMINAL:
            pytest.skip("Game ended too early")
        import numpy as np
        rng = np.random.RandomState(123)
        sampled = state.resample_from_infostate(cp, rng)
        assert sampled.current_player() == cp

    def test_resample_legal_actions_count(self, requires_c_engine):
        state = _state_after_n_moves("python_pyrants_c", seed=42, n=3)
        cp = state.current_player()
        if cp == pyspiel.PlayerId.TERMINAL:
            pytest.skip("Game ended too early")
        import numpy as np
        rng = np.random.RandomState(123)
        sampled = state.resample_from_infostate(cp, rng)
        original_legal = len(state.legal_actions())
        sampled_legal = len(sampled.legal_actions())
        assert original_legal == sampled_legal, \
            f"Legal actions differ: original={original_legal}, sampled={sampled_legal}"

    def test_resample_information_state_string(self, requires_c_engine):
        state = _state_after_n_moves("python_pyrants_c", seed=42, n=5)
        cp = state.current_player()
        if cp == pyspiel.PlayerId.TERMINAL:
            pytest.skip("Game ended too early")
        import numpy as np
        rng = np.random.RandomState(123)
        sampled = state.resample_from_infostate(cp, rng)
        original_info = state.information_state_string(cp)
        sampled_info = sampled.information_state_string(cp)
        assert original_info is not None
        assert sampled_info is not None
        assert len(sampled_info) > 0

    def test_resample_before_engine_is_noop(self, requires_c_engine):
        game = pyspiel.load_game("python_pyrants_c")
        state = game.new_initial_state()
        import numpy as np
        rng = np.random.RandomState(123)
        sampled = state.resample_from_infostate(0, rng)
        assert sampled is state

    def test_resample_from_deepcopy_state(self, requires_c_engine):
        state = _state_after_n_moves("python_pyrants_c", seed=42, n=3)
        cp = state.current_player()
        if cp == pyspiel.PlayerId.TERMINAL:
            pytest.skip("Game ended too early")
        cloned = copy.deepcopy(state)
        import numpy as np
        rng = np.random.RandomState(123)
        sampled = cloned.resample_from_infostate(cp, rng)
        assert sampled.current_player() == cp
