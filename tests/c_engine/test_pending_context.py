"""Tests for ``engine_c.bindings.pending_context.read_pending_generic_context``.

The pending-generic reader is the shared single source of truth for the
pre-``apply_action`` window of ``resolve_generic`` decisions: it decodes the C
``GameState.pending_generic`` struct (plus the active ``CardAction``) into a
JSON-ready dict for label enrichment and IS-MCTS decision telemetry.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.c_engine.card_test_helpers import (  # noqa: E402
    _make_engine,
    _sptr,
    make_card_test_session,
)


def _play_card(session, card_id: str) -> None:
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == card_id:
            session.submit_move(m)
            return
    raise AssertionError(f"{card_id} not playable")


def _pick_resolve_move(session, action_id: str):
    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == action_id:
            return m
    available = [
        m.data for m in session.legal_moves() if m.move_type == "resolve_generic"
    ]
    raise AssertionError(f"{action_id} not offered; available: {available}")


def test_gauth_awaiting_option_context(requires_c_engine) -> None:
    """After playing Gauth the reader reports an awaiting-option choice."""
    session = make_card_test_session(
        _make_engine(),
        ["p1", "p2"],
        hand={"p1": ["gauth"]},
        current_player="p1",
    )
    try:
        _play_card(session, "gauth")

        from engine_c.bindings.pending_context import read_pending_generic_context

        ctx = read_pending_generic_context(_sptr(session))
        assert ctx is not None, "Gauth modal choice must be pending after play"
        assert ctx["awaiting_option"] is True
        assert ctx["source_card_id"] == "gauth"
        assert ctx["op"] is None, "no CardAction executes while awaiting an option"
        assert ctx["card_action_id"] is None
        assert ctx["current_option_id"] is None
        assert ctx["optional"] is False
    finally:
        session.destroy()


def test_no_pending_returns_none(requires_c_engine) -> None:
    """A state with no pending generic choice reads as None."""
    session = make_card_test_session(
        _make_engine(),
        ["p1", "p2"],
        hand={"p1": ["noble"]},
        current_player="p1",
    )
    try:
        from engine_c.bindings.pending_context import read_pending_generic_context

        ctx = read_pending_generic_context(_sptr(session))
        assert ctx is None
    finally:
        session.destroy()


def test_gauth_after_option_choice_clears_pending(requires_c_engine) -> None:
    """Choosing option_1 (gain 2 influence) fully resolves: reader returns None."""
    session = make_card_test_session(
        _make_engine(),
        ["p1", "p2"],
        hand={"p1": ["gauth"]},
        current_player="p1",
    )
    try:
        _play_card(session, "gauth")

        from engine_c.bindings.pending_context import read_pending_generic_context

        ctx = read_pending_generic_context(_sptr(session))
        assert ctx is not None and ctx["awaiting_option"] is True

        session.submit_move(_pick_resolve_move(session, "option_1"))

        assert read_pending_generic_context(_sptr(session)) is None
    finally:
        session.destroy()


def test_gauth_target_selection_context(requires_c_engine) -> None:
    """After picking option_2 the reader reports the active force_discard action."""
    session = make_card_test_session(
        _make_engine(),
        ["p1", "p2"],
        hand={"p1": ["gauth"], "p2": ["soldier", "soldier", "soldier", "soldier"]},
        deck={"p1": ["noble", "noble", "noble", "noble", "noble"]},
        current_player="p1",
    )
    try:
        _play_card(session, "gauth")
        session.submit_move(_pick_resolve_move(session, "option_2"))

        from engine_c.bindings.pending_context import read_pending_generic_context

        ctx = read_pending_generic_context(_sptr(session))
        assert ctx is not None, "force_discard target selection must be pending"
        assert ctx["awaiting_option"] is False
        assert ctx["source_card_id"] == "gauth"
        assert ctx["op"] == "force_discard"
        assert ctx["card_action_id"] == "option_2_action_2"
        assert ctx["optional"] is False
    finally:
        session.destroy()


def test_death_knight_supplant_context(requires_c_engine) -> None:
    """A sequence card mid-selection exposes its CardAction op + action_id."""
    session = make_card_test_session(
        _make_engine(),
        ["p1", "p2"],
        hand={"p1": ["death_knight"]},
        troops={"p1": {"route_6": ["p1"]}, "p2": {"site_gauntlgrym": ["p2", "p1"]}},
        current_player="p1",
    )
    try:
        _play_card(session, "death_knight")

        from engine_c.bindings.pending_context import read_pending_generic_context

        ctx = read_pending_generic_context(_sptr(session))
        assert ctx is not None, "supplant_troop selection must be pending"
        assert ctx["source_card_id"] == "death_knight"
        assert ctx["awaiting_option"] is False
        assert ctx["op"] == "supplant_troop"
        assert ctx["card_action_id"] == "action_1"
        assert ctx["optional"] is False
    finally:
        session.destroy()
