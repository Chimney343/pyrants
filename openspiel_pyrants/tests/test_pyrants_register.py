"""Verify that python_pyrants registers and loads correctly in OpenSpiel."""

from __future__ import annotations

import pytest


def test_game_registers_and_loads():
    import pyspiel

    game = pyspiel.load_game("python_pyrants")
    game_type = game.get_type()

    assert game_type.short_name == "python_pyrants"
    assert game_type.dynamics == pyspiel.GameType.Dynamics.SEQUENTIAL
    assert game_type.chance_mode == pyspiel.GameType.ChanceMode.EXPLICIT_STOCHASTIC
    assert game_type.information == pyspiel.GameType.Information.IMPERFECT_INFORMATION

    info = game
    assert info.num_distinct_actions() == 1024
    assert info.max_chance_outcomes() == 1000
    assert info.num_players() == 2
    assert info.min_utility() == -200.0
    assert info.max_utility() == 200.0
    assert info.utility_sum() == 0.0
    assert info.max_game_length() == 4096


@pytest.mark.parametrize("num_players,utility,min_util,max_util", [
    (2, "ZERO_SUM", -200.0, 200.0),
    (3, "GENERAL_SUM", -400.0, 400.0),
    (4, "GENERAL_SUM", -400.0, 400.0),
])
def test_game_registers_with_num_players(num_players, utility, min_util, max_util):
    import pyspiel

    game = pyspiel.load_game("python_pyrants", {"num_players": str(num_players)})
    game_type = game.get_type()

    assert game_type.utility == getattr(pyspiel.GameType.Utility, utility)
    info = game
    assert info.num_players() == num_players
    assert info.min_utility() == min_util
    assert info.max_utility() == max_util
    assert info.utility_sum() == 0.0

    state = game.new_initial_state()
    assert state.is_chance_node()
    state.apply_action(42)
    assert len(state.returns()) == num_players


def test_direct_construction():
    from openspiel_pyrants.game import PyrantsGame

    game = PyrantsGame()
    state = game.new_initial_state()
    assert not state.is_terminal()
    assert state.is_chance_node()


def test_direct_construction_4p():
    from openspiel_pyrants.game import PyrantsGame
    import pyspiel

    game = PyrantsGame({"num_players": "4"})
    assert game.get_type().utility == pyspiel.GameType.Utility.GENERAL_SUM
    state = game.new_initial_state()
    state.apply_action(42)
    assert len(state.returns()) == 4
