"""Verify that python_pyrants registers and loads correctly in OpenSpiel."""

from __future__ import annotations


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


def test_direct_construction():
    from openspiel_pyrants.game import PyrantsGame

    game = PyrantsGame()
    state = game.new_initial_state()
    assert not state.is_terminal()
    assert state.is_chance_node()
