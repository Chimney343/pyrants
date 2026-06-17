"""OpenSpiel wrapper for pyrants: Tyrants of the Underdark.

Register via ``import openspiel_pyrants`` and then ``pyspiel.load_game("python_pyrants")``.

Usage:
    import openspiel_pyrants
    import pyspiel
    game = pyspiel.load_game("python_pyrants")
    state = game.new_initial_state()
"""

import pyspiel

from openspiel_pyrants.game import _build_game_type, PyrantsGame

pyspiel.register_game(_build_game_type(2), PyrantsGame)

try:
    from openspiel_pyrants.game_c import _build_c_game_type, PyrantsCGame
    pyspiel.register_game(_build_c_game_type(2), PyrantsCGame)
except (ImportError, OSError):
    pass
