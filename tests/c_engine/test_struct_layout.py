"""The Python ctypes mirrors must match the C engine's memory layout.

The C side exports ``engine_layout_size`` / ``engine_layout_offset``; these
tests exercise that interface directly, including the failure modes, and pin
the ``PendingGenericChoiceState`` tail fields that C added in 69cd2a2.
"""

from __future__ import annotations

import ctypes
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from engine_c.bindings import engine_bindings as eb  # noqa: E402
from engine_c.bindings.layout_probe import LayoutMismatch, assert_layout  # noqa: E402


def test_every_mirrored_struct_matches_c():
    assert_layout(eb._lib, eb._MIRRORED_STRUCTS)


def test_pending_generic_tail_fields_are_mirrored():
    fields = dict(eb.PendingGenericChoiceState._fields_)
    assert "parent" in fields
    assert "last_played_card_id" in fields
    assert (
        eb.PendingGenericChoiceState.parent.offset
        < eb.PendingGenericChoiceState.last_played_card_id.offset
    )


def test_probe_reports_unknown_type_and_field():
    assert eb._lib.engine_layout_size(b"NotAStruct") == ctypes.c_size_t(-1).value
    assert eb._lib.engine_layout_offset(b"GameState", b"not_a_field") == -1


def test_assert_layout_rejects_a_wrong_size():
    class WrongGameState(ctypes.Structure):
        _fields_ = [("definition", ctypes.c_void_p)]

    with pytest.raises(LayoutMismatch):
        assert_layout(eb._lib, {"GameState": WrongGameState})
