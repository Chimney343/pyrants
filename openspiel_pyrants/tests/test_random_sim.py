"""100-iteration random simulation verifying key OpenSpiel invariants."""

from __future__ import annotations

import random

import pyspiel


def test_random_simulation():
    game = pyspiel.load_game("python_pyrants")
    rng = random.Random(42)

    for _sim_i in range(100):
        state = game.new_initial_state()

        decision_count = 0
        seed = rng.randrange(game.get_shuffle_seed_count())
        state._apply_action(seed)

        while not state.is_terminal():
            assert not state.is_chance_node()
            actions = state.legal_actions()
            assert len(actions) > 0
            assert actions == sorted(actions)
            action = rng.choice(actions)
            state._apply_action(action)
            decision_count += 1

        assert decision_count < game.max_game_length()
        ret = state.returns()
        assert len(ret) == 2
        assert all(isinstance(v, float) for v in ret)
        assert abs(sum(ret)) < 1e-9
        assert all(game.min_utility() <= v <= game.max_utility() for v in ret)


def test_chance_outcomes():
    game = pyspiel.load_game("python_pyrants")
    state = game.new_initial_state()
    assert state.is_chance_node()

    outcomes = state.chance_outcomes()
    assert len(outcomes) == game.get_shuffle_seed_count()
    probs = [p for _, p in outcomes]
    assert abs(sum(probs) - 1.0) < 1e-9

    assert state.legal_actions() == list(range(game.get_shuffle_seed_count()))


def test_two_states_same_seed_produce_same_result():
    game = pyspiel.load_game("python_pyrants")
    state_a = game.new_initial_state()
    state_b = game.new_initial_state()

    state_a._apply_action(7)
    state_b._apply_action(7)

    assert str(state_a) == str(state_b)
