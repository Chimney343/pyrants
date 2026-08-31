"""OpenSpiel wrapper for pyrants: Tyrants of the Underdark.

Register via ``import openspiel_pyrants`` and then ``pyspiel.load_game("python_pyrants_c")``.

Usage:
    import openspiel_pyrants
    import pyspiel
    game = pyspiel.load_game("python_pyrants_c")
    state = game.new_initial_state()
"""

import pyspiel

from openspiel_pyrants.game_c import PyrantsCGame, _build_c_game_type
from openspiel_pyrants.ismcts_factory import make_ismcts_bot

pyspiel.register_game(_build_c_game_type(2), PyrantsCGame)

__all__ = ["make_ismcts_bot"]
