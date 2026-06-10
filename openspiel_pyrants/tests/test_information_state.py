"""Tests for information_state_string and observation_string on PyrantsState."""

from __future__ import annotations

import random

import pyspiel


def _fresh_state():
    game = pyspiel.load_game("python_pyrants")
    state = game.new_initial_state()
    state.apply_action(42)
    return state


class TestInformationStateString:
    def test_returns_string_for_both_players(self):
        state = _fresh_state()
        s0 = state.information_state_string(0)
        s1 = state.information_state_string(1)
        assert isinstance(s0, str) and len(s0) > 0
        assert isinstance(s1, str) and len(s1) > 0
        assert s0 != s1

    def test_stable_across_clone(self):
        state = _fresh_state()
        s0 = state.information_state_string(0)
        cloned = state.clone()
        s1 = cloned.information_state_string(0)
        assert s0 == s1

    def test_identical_for_same_seed(self):
        game = pyspiel.load_game("python_pyrants")
        state_a = game.new_initial_state()
        state_b = game.new_initial_state()
        state_a.apply_action(7)
        state_b.apply_action(7)
        assert state_a.information_state_string(0) == state_b.information_state_string(0)
        assert state_a.information_state_string(1) == state_b.information_state_string(1)

    def test_different_for_different_seed(self):
        game = pyspiel.load_game("python_pyrants")
        state_a = game.new_initial_state()
        state_b = game.new_initial_state()
        state_a.apply_action(7)
        state_b.apply_action(42)
        assert state_a.information_state_string(0) != state_b.information_state_string(0)

    def test_different_for_different_state(self):
        game = pyspiel.load_game("python_pyrants")
        state_a = game.new_initial_state()
        state_b = game.new_initial_state()
        state_a.apply_action(7)
        state_b.apply_action(7)

        actions_a = state_a.legal_actions()
        actions_b = state_b.legal_actions()
        state_a.apply_action(actions_a[0])
        state_b.apply_action(actions_b[1])
        assert state_a.information_state_string(0) != state_b.information_state_string(0)

    def test_includes_history(self):
        state = _fresh_state()
        s_before = state.information_state_string(0)
        action = state.legal_actions()[0]
        state.apply_action(action)
        s_after = state.information_state_string(0)
        assert s_before != s_after
        assert "||" in s_after

    def test_observation_string_matches(self):
        state = _fresh_state()
        assert state.observation_string(0) == state.information_state_string(0)
        assert state.observation_string(1) == state.information_state_string(1)

    def test_chance_node_returns_empty(self):
        game = pyspiel.load_game("python_pyrants")
        state = game.new_initial_state()
        assert state.information_state_string(0) == ""


class TestInformationStateAfterActions:
    def test_keys_diverge_as_game_progresses(self):
        game = pyspiel.load_game("python_pyrants")
        rng = random.Random(42)
        state = game.new_initial_state()
        state.apply_action(rng.randrange(1000))

        keys_seen = set()
        for _ in range(20):
            if state.is_terminal():
                break
            actions = state.legal_actions()
            action = rng.choice(actions)
            state.apply_action(action)
            key0 = state.information_state_string(0)
            assert key0 not in keys_seen, f"Duplicate info-state key after action {action}"
            keys_seen.add(key0)
