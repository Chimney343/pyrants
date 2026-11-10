"""The legal-move capacity has one source and truncation is visible (F-038).

The old contract: ``ce_api`` sized its buffers from a hard-coded 1024,
``openspiel_pyrants`` declared a second 1024 as ``NUM_DISTINCT_ACTIONS``, and C
stopped at the cap without saying so. Two constants could drift, and a state
with more moves than the buffer lost the extras with no error.

The new contract has three parts, one test file:

- C owns the capacity (``engine_move_capacity``); both Python sides read it.
- The move queries report how many moves exist, even past the buffer.
- ``CEngine.legal_moves``/``display_moves`` raise when a state needs more moves
  than the frozen action space can hold, instead of returning a short list.

The Python side is exercised with a fake ``_lib`` so it can simulate a state
above the capacity without building one, and against the real DLL to prove the
number is wired through.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from engine_c.bindings import ce_api  # noqa: E402
from engine_c.bindings.ce_api import CEngine, MoveCapacityError, move_capacity  # noqa: E402

_requires_dll = pytest.mark.skipif(ce_api._lib is None, reason="engine_c DLL not available")


@_requires_dll
def test_capacity_has_one_source():
    """The engine exports the capacity and the binding reads that value."""
    assert move_capacity() == ce_api._lib.engine_move_capacity()
    assert move_capacity() > 0


@_requires_dll
def test_num_distinct_actions_agrees_with_the_engine():
    """The frozen action space and the engine's capacity are the same number."""
    import openspiel_pyrants  # noqa: F401  (registers, and runs the import check)
    from openspiel_pyrants.game_c import NUM_DISTINCT_ACTIONS

    assert NUM_DISTINCT_ACTIONS == move_capacity() == 1024


class _OverflowingLib:
    """Stand-in for the ctypes library whose move query overflows the buffer."""

    def __init__(self, needed: int):
        self.needed = needed
        self.asked = []

    def engine_move_capacity(self):
        return 1024

    def engine_legal_moves(self, ptr, buf, cap):
        self.asked.append(cap)
        return self.needed

    def engine_display_moves(self, ptr, buf, applicable, cap):
        self.asked.append(cap)
        return self.needed


def test_legal_moves_raise_when_the_query_exceeds_the_capacity(monkeypatch):
    fake = _OverflowingLib(needed=1025)
    monkeypatch.setattr(ce_api, "_lib", fake)

    class _State:
        ptr = "state"

    with pytest.raises(MoveCapacityError) as excinfo:
        CEngine.legal_moves(None, _State())  # the method reads only _lib
    assert excinfo.value.needed == 1025
    assert excinfo.value.capacity == 1024
    assert fake.asked == [1024]


def test_display_moves_raise_when_the_query_exceeds_the_capacity(monkeypatch):
    fake = _OverflowingLib(needed=2048)
    monkeypatch.setattr(ce_api, "_lib", fake)

    class _State:
        ptr = "state"

    with pytest.raises(MoveCapacityError) as excinfo:
        CEngine.display_moves(None, _State())  # the method reads only _lib
    assert "display" in str(excinfo.value)
    assert fake.asked == [1024]


def test_python_buffers_are_sized_from_the_engine_capacity(monkeypatch):
    """The binding must not carry a second 1024: buffer size = exported value."""
    fake = _OverflowingLib(needed=3)
    monkeypatch.setattr(ce_api, "_lib", fake)

    class _State:
        ptr = "state"

    CEngine.legal_moves(None, _State())
    CEngine.display_moves(None, _State())
    assert fake.asked == [1024, 1024]


@_requires_dll
def test_a_real_state_reports_the_same_count_at_every_capacity():
    """The honest count does not depend on how big a buffer the caller offers."""
    from engine_c.bindings.engine_bindings import Move

    engine = CEngine()
    engine.initialize()
    state = engine.create_game(["p1", "p2"], seed=42)
    try:
        cap = move_capacity()
        full = (Move * cap)()
        need = ce_api._lib.engine_legal_moves(state.ptr, full, cap)
        assert need > 0
        for probe in (0, 1, need - 1):
            if probe < 0:
                continue
            buf = (Move * cap)()
            assert ce_api._lib.engine_legal_moves(state.ptr, buf, probe) == need
    finally:
        engine.destroy(state)
