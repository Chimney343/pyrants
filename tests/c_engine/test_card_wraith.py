"""Wraith card behavior tests.

Verifies:
- Place a spy at a chosen board site
- Optional devour of self (played_self)
- If devour skipped → no assassinate (skip_advance_to_index)
- If devour taken → assassinate a troop at the spy site only (requires_last_selected_node)
"""
from __future__ import annotations

from engine_c.bindings.engine_bindings import _lib
from engine_c.bindings.session import CSession
from tests.c_engine.card_test_helpers import (
    _make_engine,
    _session_player_index,
    _sptr,
    make_card_test_session,
)

_SITE_A = "site_gauntlgrym"
_SITE_B = "site_menzoberranzan"
_P1 = "p1"
_P2 = "p2"

CARD_ID = "wraith"


def _build_session() -> CSession:
    """Build a session with Wraith in hand.
    
    Two sites: SITE_A has p1 presence + enemy troop, SITE_B also has enemy troop.
    This way we can verify the assassinate is constrained to the spy site.
    """
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [CARD_ID]},
        troops={
            _P1: {_SITE_A: [_P2, None, None, None]},
            _P2: {_SITE_B: [_P1, _P2, None, None]},
        },
        current_player=_P1,
    )
    return session


def _has_pending_generic(session: CSession) -> bool:
    return bool(_sptr(session).contents.pending_generic)


def _spies_at_node(session: CSession, node_id: str) -> list[str]:
    s = _sptr(session).contents
    nid = _lib.intern(node_id.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            return [_lib.intern_str(s.nodes[ni].spies[i]).decode() for i in range(s.nodes[ni].spy_count)]
    return []


def _devour_pile(session: CSession) -> list[str]:
    s = _sptr(session).contents
    return [_lib.intern_str(s.devour_pile[i]).decode() for i in range(s.devour_pile_count)]


def _trophy_hall(session: CSession, pid: str) -> list[str]:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return []
    s = _sptr(session).contents
    ps = s.players[pi]
    return [_lib.intern_str(ps.trophy_hall[j]).decode() for j in range(ps.trophy_hall_count)]


def _play_card(session: CSession) -> None:
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == CARD_ID:
            session.submit_move(m)
            return
    raise AssertionError(f"{CARD_ID} not playable")


def test_wraith_place_spy() -> None:
    """Playing Wraith should first prompt for spy placement."""
    session = _build_session()
    _play_card(session)

    assert _has_pending_generic(session), "Should prompt for spy placement"

    # Find a spy placement move
    spy_move = None
    for m in session.legal_moves():
        if m.move_type == "resolve_generic":
            spy_move = m
            break
    assert spy_move is not None, "Should have spy placement move"

    session.submit_move(spy_move)

    # Spy should be placed at the chosen site
    target_site = spy_move.data.get("action_id")
    spies = _spies_at_node(session, target_site)
    assert _P1 in spies, f"Expected {_P1} spy at {target_site}, got {spies}"

    # Should now prompt for optional devour
    assert _has_pending_generic(session), "Should prompt for devour after spy placement"

    session.destroy()


def test_wraith_skip_devour_no_assassinate() -> None:
    """Skipping devour should NOT offer assassinate — skip_advance_to_index jumps past it."""
    session = _build_session()
    _play_card(session)

    # Place spy first
    spy_move = None
    for m in session.legal_moves():
        if m.move_type == "resolve_generic":
            spy_move = m
            break
    assert spy_move is not None, "Should have spy placement move"
    session.submit_move(spy_move)

    assert _has_pending_generic(session), "Should prompt for devour"

    # Find the skip move for the optional devour
    skip_move = None
    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") is None:
            skip_move = m
            break
    assert skip_move is not None, "Should have a skip/decline move for devour"

    session.submit_move(skip_move)

    # Card should be fully resolved after skipping devour
    assert not _has_pending_generic(session), (
        "Expected no pending generic after skipping devour; assassinate should be skipped"
    )

    # Wraith should NOT be in devour pile
    assert CARD_ID not in _devour_pile(session), "Wraith should not be devoured"

    session.destroy()


def test_wraith_devour_then_assassinate() -> None:
    """Devouring Wraith should offer assassinate, and execution works."""
    session = _build_session()
    _play_card(session)

    # Place spy at SITE_A (where p1 has presence)
    spy_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    spy_move_a = None
    for m in spy_moves:
        if m.data.get("action_id") == _SITE_A:
            spy_move_a = m
            break
    assert spy_move_a is not None, f"Should have spy move for {_SITE_A}"
    session.submit_move(spy_move_a)

    assert _has_pending_generic(session), "Should prompt for devour"

    # Find the devour self move
    devour_move = None
    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == CARD_ID:
            devour_move = m
            break
    assert devour_move is not None, f"Should have devour move for {CARD_ID}"

    session.submit_move(devour_move)

    # Wraith should be in devour pile
    assert CARD_ID in _devour_pile(session), "Wraith should be devoured"

    # Should now have assassinate prompt
    assert _has_pending_generic(session), "Should have assassinate after devour"

    assassinate_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert len(assassinate_moves) > 0, "Should have at least one assassination target"

    # Pick the first target and execute
    session.submit_move(assassinate_moves[0])

    # Card should be fully resolved
    assert not _has_pending_generic(session), "Expected no pending generic after full resolution"

    # p2 should be in p1's trophy hall (the troop at SITE_A was assassinated)
    trophy = _trophy_hall(session, _P1)
    assert _P2 in trophy, f"Expected {_P2} in p1 trophy hall after assassinate, got {trophy}"

    session.destroy()


def test_wraith_assassinate_constrained_to_spy_site() -> None:
    """Assassinate targets should be limited to the site where the spy was placed."""
    session = _build_session()
    _play_card(session)

    # Place spy at SITE_A
    spy_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    spy_move_a = None
    for m in spy_moves:
        if m.data.get("action_id") == _SITE_A:
            spy_move_a = m
            break
    assert spy_move_a is not None, f"Should have spy move for {_SITE_A}"
    session.submit_move(spy_move_a)

    # Devour Wraith
    devour_move = None
    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == CARD_ID:
            devour_move = m
            break
    assert devour_move is not None
    session.submit_move(devour_move)

    assert _has_pending_generic(session), "Should have assassinate prompt"

    # All assassination targets should be at SITE_A (the spy site), NOT SITE_B
    assassinate_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    site_ids = [m.data.get("action_id") for m in assassinate_moves]

    assert all(s == _SITE_A for s in site_ids), (
        f"All assassinate targets should be at spy site {_SITE_A}, got sites: {site_ids}"
    )
    assert _SITE_B not in site_ids, (
        f"{_SITE_B} should NOT be targetable for assassinate, but was found in sites: {site_ids}"
    )

    session.destroy()
