"""Smoke test: ``pyspiel.load_game("python_pyrants_c")`` creates a working state."""

from __future__ import annotations

import pyspiel
import pytest

import openspiel_pyrants  # noqa: F401 — registers python_pyrants / python_pyrants_c


class TestPyrantsCRegister:
    def test_load_game_creates_state(self, requires_c_engine):
        game = pyspiel.load_game("python_pyrants_c")
        state = game.new_initial_state()
        assert state is not None

    def test_initial_chance_node(self, requires_c_engine):
        game = pyspiel.load_game("python_pyrants_c")
        state = game.new_initial_state()
        assert state.is_chance_node()
        assert not state.is_terminal()

    def test_chance_outcomes(self, requires_c_engine):
        game = pyspiel.load_game("python_pyrants_c")
        state = game.new_initial_state()
        outcomes = state.chance_outcomes()
        n = game.get_shuffle_seed_count()
        assert len(outcomes) == n
        total_p = sum(p for _, p in outcomes)
        assert abs(total_p - 1.0) < 1e-9

    def test_apply_chance_then_decide(self, requires_c_engine):
        game = pyspiel.load_game("python_pyrants_c")
        state = game.new_initial_state()
        assert state.is_chance_node()
        state.apply_action(42)
        assert not state.is_chance_node()
        cp = state.current_player()
        assert cp != pyspiel.PlayerId.CHANCE
        assert cp != pyspiel.PlayerId.TERMINAL

    def test_legal_actions_after_chance(self, requires_c_engine):
        game = pyspiel.load_game("python_pyrants_c")
        state = game.new_initial_state()
        state.apply_action(42)
        legal = state.legal_actions()
        assert len(legal) > 0

    def test_apply_several_moves(self, requires_c_engine):
        game = pyspiel.load_game("python_pyrants_c")
        state = game.new_initial_state()
        state.apply_action(42)
        for _ in range(20):
            if state.is_terminal():
                break
            legal = state.legal_actions()
            assert len(legal) > 0, f"No legal actions at step {_}"
            state.apply_action(legal[0])

    def test_str_representation(self, requires_c_engine):
        game = pyspiel.load_game("python_pyrants_c")
        state = game.new_initial_state()
        s = str(state)
        assert "chance node pending" in s
        state.apply_action(42)
        s2 = str(state)
        assert "Phase" in s2

    def test_returns_before_engine(self, requires_c_engine):
        game = pyspiel.load_game("python_pyrants_c")
        state = game.new_initial_state()
        ret = state.returns()
        assert ret == [0.0, 0.0]

    def test_returns_after_chance(self, requires_c_engine):
        game = pyspiel.load_game("python_pyrants_c")
        state = game.new_initial_state()
        state.apply_action(42)
        ret = state.returns()
        assert len(ret) == 2
        assert abs(sum(ret)) < 1e-9

    def test_game_type_short_name(self, requires_c_engine):
        game = pyspiel.load_game("python_pyrants_c")
        assert game.get_type().short_name == "python_pyrants_c"

    def test_game_info(self, requires_c_engine):
        game = pyspiel.load_game("python_pyrants_c")
        assert game.num_distinct_actions() == 1024
        assert game.max_chance_outcomes() == 1000
        assert game.num_players() == 2

    @pytest.mark.parametrize("num_players", [3, 4])
    def test_n_player_load(self, requires_c_engine, num_players):
        game = pyspiel.load_game("python_pyrants_c", {"num_players": str(num_players)})
        assert game.num_players() == num_players
        state = game.new_initial_state()
        state.apply_action(42)
        ret = state.returns()
        assert len(ret) == num_players
