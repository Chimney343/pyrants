"""PyrantsCObserver — per-player observation for the C engine backend.

Produces a JSON serialization of the player's private view as the observation
string. Mirrors ``observer.py`` but delegates to ``CEngineAdapter.private_view_json``.
"""

from __future__ import annotations


class PyrantsCObserver:
    """Observer that extracts private-view observations from ``PyrantsCState``."""

    def __init__(self, params=None):
        del params
        self.tensor = None
        self.dict = {}

    def set_from(self, state, player):
        pass

    def string_from(self, state, player):
        if state._adapter is None:
            return "{}"
        player_id = state._game.get_player_ids()[player]
        return state._adapter.private_view_json(player_id)
