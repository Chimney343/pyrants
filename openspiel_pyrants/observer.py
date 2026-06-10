"""PyrantsObserver — per-player observation backed by ``engine.player_view``.

Produces a JSON serialization of the player's ``PrivateView`` as the
observation string.  Used by ``make_py_observer`` in ``game.py``.
"""

from __future__ import annotations

from engine.player_view import private_view


class PyrantsObserver:
    """Observer that extracts private-view observations from ``PyrantsState``.

    Implements the ``set_from`` / ``string_from`` contract expected by
    ``pyspiel._Observation`` (the C++ wrapper calls these methods directly).
    """

    def __init__(self, params=None):
        del params
        self.tensor = None
        self.dict = {}

    def set_from(self, state, player):
        pass

    def string_from(self, state, player):
        player_id = state._game.get_player_ids()[player]
        pv = private_view(state._engine, player_id)
        return pv.model_dump_json()
