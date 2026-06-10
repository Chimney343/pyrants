"""OpenSpiel wrapper for pyrants: Tyrants of the Underdark.

Register via ``import openspiel_pyrants`` and then ``pyspiel.load_game("python_pyrants")``.

Usage:
    import openspiel_pyrants
    import pyspiel
    game = pyspiel.load_game("python_pyrants")
    state = game.new_initial_state()
"""

import pyspiel

from openspiel_pyrants.game import _GAME_TYPE, PyrantsGame

pyspiel.register_game(_GAME_TYPE, PyrantsGame)
