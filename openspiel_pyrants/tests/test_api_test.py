"""OpenSpiel built-in API consistency test (random_sim_test)."""

from __future__ import annotations

import pyspiel


def test_api_random_sim_test():
    game = pyspiel.load_game("python_pyrants")
    pyspiel.random_sim_test(game, num_sims=5, serialize=False, verbose=True)
