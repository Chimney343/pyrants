"""Inquisitor card behavior tests.

Verifies:
- Modal choice: gain 2 influence OR assassinate
- Assassinate targets both white and player troops (default behavior)
- Assassinate requires presence at target site
"""

from __future__ import annotations

from engine_c.bindings.engine_bindings import PHASE_MAIN, _lib
from tests.c_engine.card_test_helpers import (
    _make_engine,
    _session_player_index,
    _sptr,
    make_card_test_session,
)

_SITE = "route_27"
_P1 = "p1"
_P2 = "p2"
_WHITE = "white"


def _build_inquisitor_session():
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: ["inquisitor", "noble"]},
        spies={_SITE: [_P1]},
        current_player=_P1,
    )
    s = session._state._ptr.contents
    s.phase = PHASE_MAIN

    nid = _lib.intern(_SITE.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            s.nodes[ni].troop_slots[0] = _lib.intern(_WHITE.encode())
            s.nodes[ni].troop_slot_count = 1
            break

    return session


def _trophy_hall(session, pid):
    pi = _session_player_index(session, pid)
    if pi < 0:
        return []
    s = _sptr(session).contents
    ps = s.players[pi]
    return [_lib.intern_str(ps.trophy_hall[j]).decode() for j in range(ps.trophy_hall_count)]


def _troops_at_node(session, node_id):
    s = _sptr(session).contents
    nid = _lib.intern(node_id.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            ns = s.nodes[ni]
            return [
                _lib.intern_str(ns.troop_slots[i]).decode()
                if ns.troop_slots[i] != 0
                else None
                for i in range(ns.troop_slot_count)
            ]
    return []


def _resource_influence(session):
    return _sptr(session).contents.resource_pool.influence


def _has_pending_generic(session):
    return bool(_sptr(session).contents.pending_generic)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_inquisitor_gain_influence():
    session = _build_inquisitor_session()

    influence_before = _resource_influence(session)

    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == "inquisitor":
            session.submit_move(m)
            break

    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == "option_1":
            session.submit_move(m)
            break

    assert not _has_pending_generic(session)
    assert _resource_influence(session) == influence_before + 2

    session.destroy()


def test_inquisitor_assassinate_white_troop():
    session = _build_inquisitor_session()

    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == "inquisitor":
            session.submit_move(m)
            break

    assert _has_pending_generic(session)

    options = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    option_2 = [m for m in options if m.data.get("action_id") == "option_2"]
    assert len(option_2) > 0, f"option_2 should be available; options: {[m.data for m in options]}"
    assert option_2[0].data.get("target_id") != "unavailable", (
        f"option_2 should be viable, got target_id={option_2[0].data.get('target_id')}"
    )

    session.submit_move(option_2[0])
    assert _has_pending_generic(session)

    assassinate_moves = [
        m for m in session.legal_moves()
        if m.move_type == "resolve_generic"
    ]
    assert len(assassinate_moves) > 0

    white_move = None
    for am in assassinate_moves:
        if am.data.get("action_id") == _SITE and am.data.get("target_id") == "0":
            white_move = am
            break
    assert white_move is not None, (
        f"White troop at {_SITE} should be targetable; moves: {[m.data for m in assassinate_moves]}"
    )

    session.submit_move(white_move)
    assert not _has_pending_generic(session)

    trophy = _trophy_hall(session, _P1)
    assert _WHITE in trophy, f"Expected white in p1 trophy hall, got {trophy}"

    troops = _troops_at_node(session, _SITE)
    assert troops[0] is None, f"White troop should be removed from {_SITE}, got {troops}"

    session.destroy()


def test_inquisitor_assassinate_player_troop():
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: ["inquisitor", "noble"]},
        spies={_SITE: [_P1]},
        current_player=_P1,
    )
    s = session._state._ptr.contents
    s.phase = PHASE_MAIN

    nid = _lib.intern(_SITE.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            s.nodes[ni].troop_slots[0] = _lib.intern(b"p2")
            s.nodes[ni].troop_slot_count = 1
            break

    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == "inquisitor":
            session.submit_move(m)
            break

    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == "option_2":
            assert m.data.get("target_id") != "unavailable", (
                f"option_2 should be viable, got target_id={m.data.get('target_id')}"
            )
            session.submit_move(m)
            break

    assassinate_moves = [
        m for m in session.legal_moves()
        if m.move_type == "resolve_generic"
    ]
    target_ids = [am.data.get("target_id") for am in assassinate_moves]
    has_p2 = any(t == "0" for t in target_ids if t is not None)
    assert has_p2, f"p2 troop (slot 0) should be targetable; targets: {target_ids}"

    p2_move = None
    for am in assassinate_moves:
        if am.data.get("action_id") == _SITE and am.data.get("target_id") == "0":
            p2_move = am
            break
    assert p2_move is not None
    session.submit_move(p2_move)

    trophy = _trophy_hall(session, _P1)
    assert "p2" in trophy, f"Expected p2 in p1 trophy hall, got {trophy}"

    session.destroy()


def test_inquisitor_assassinate_requires_presence():
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: ["inquisitor", "noble"]},
        current_player=_P1,
    )
    s = session._state._ptr.contents
    s.phase = PHASE_MAIN

    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == "inquisitor":
            session.submit_move(m)
            break

    options = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    option_2 = [m for m in options if m.data.get("action_id") == "option_2"]
    assert len(option_2) > 0
    assert option_2[0].data.get("target_id") == "unavailable", (
        "Without presence, option_2 should be unavailable"
    )

    session.destroy()
