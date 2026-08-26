"""Tests that face-up zones (inner circle, trophy hall, played cards) are
exposed for every player in the C-backend public view and information-state
string (Item 4a)."""

from __future__ import annotations

import os

import pyspiel
import pytest

import openspiel_pyrants  # noqa: F401
from engine_c.bindings.engine_bindings import _lib


def _load_c_game(num_players: int = 2):
    return pyspiel.load_game("python_pyrants_c", {"num_players": str(num_players)})


@pytest.mark.skipif(
    os.environ.get("PYRANTS_SKIP_ISMCTS") == "1",
    reason="PYRANTS_SKIP_ISMCTS=1 set",
)
class TestPublicViewFaceUpZones:
    def test_information_state_includes_opponent_face_up_zones(self, requires_c_engine):
        game = _load_c_game(2)
        state = game.new_initial_state()
        state.apply_action(42)

        pids = game.get_player_ids()
        opp_pid = pids[1]
        opp_idx = state._adapter.player_index(opp_pid)

        s = state._adapter._state._s
        p = s.players[opp_idx]
        p.inner_circle_count = 1
        p.inner_circle[0] = _lib.intern(b"noble")
        p.trophy_hall_count = 1
        p.trophy_hall[0] = _lib.intern(b"white")
        p.played_cards_count = 1
        p.played_cards[0] = _lib.intern(b"advance_scout")

        pub = state._adapter._build_public_dict()
        summaries = pub["public_player_summaries"][opp_pid]

        assert summaries["inner_circle"] == ["noble"]
        assert summaries["trophy_hall"] == ["white"]
        assert summaries["played_cards"] == ["advance_scout"]

        info = state.information_state_string(0)
        assert '"noble"' in info
        assert '"white"' in info
        assert '"advance_scout"' in info
