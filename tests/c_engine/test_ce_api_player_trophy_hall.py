"""Tests for the CState.player_trophy_hall accessor (Item 4a)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from engine_c.bindings.ce_api import CEngine
from engine_c.bindings.engine_bindings import _lib


def _make_engine() -> CEngine:
    eng = CEngine()
    eng.initialize()
    return eng


def _player_index(s, pid: str) -> int:
    for i in range(s.player_count):
        name = _lib.intern_str(s.player_ids[i])
        if name and name.decode() == pid:
            return i
    return -1


def test_player_trophy_hall_returns_owner_ids():
    engine = _make_engine()
    state = engine.create_game(["p1", "p2"], seed=0)
    s = state._s
    idx = _player_index(s, "p2")

    owners = ["white", "p1"]
    p = s.players[idx]
    p.trophy_hall_count = len(owners)
    for j, oid in enumerate(owners):
        p.trophy_hall[j] = _lib.intern(oid.encode())

    assert state.player_trophy_hall(idx) == owners
    engine.destroy(state)


def test_player_trophy_hall_empty_for_untouched_player():
    engine = _make_engine()
    state = engine.create_game(["p1", "p2"], seed=0)
    s = state._s
    idx = _player_index(s, "p2")
    s.players[idx].trophy_hall_count = 0

    assert state.player_trophy_hall(idx) == []
    engine.destroy(state)
