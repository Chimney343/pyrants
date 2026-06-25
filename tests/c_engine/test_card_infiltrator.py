"""Infiltrator card behavior tests.

Verifies:
- Place a spy with normal legality
- If another player has a troop at the target site, gain 1 power
- Own troop at the site does NOT trigger power gain
- Card fully resolves after spy placement (no pending)
"""

from __future__ import annotations

from engine_c.bindings.engine_bindings import PHASE_MAIN, _lib
from tests.c_engine.card_test_helpers import (
    _make_engine,
    _session_player_index,
    _sptr,
    make_card_test_session,
)

_SITE = "site_gauntlgrym"
_SITE2 = "site_chaulssin"
_P1 = "p1"
_P2 = "p2"
_P3 = "p3"


def _spies_at_node(session, node_id):
    s = _sptr(session).contents
    nid = _lib.intern(node_id.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            return [_lib.intern_str(s.nodes[ni].spies[i]).decode() for i in range(s.nodes[ni].spy_count)]
    return []


def _spies_available(session, pid):
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].spies_available


def _resource_power(session):
    return _sptr(session).contents.resource_pool.power


def _has_pending_generic(session):
    return bool(_sptr(session).contents.pending_generic)


def _clear_troops(session, node_id):
    s = _sptr(session).contents
    nid = _lib.intern(node_id.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            ns = s.nodes[ni]
            for i in range(ns.troop_slot_count):
                ns.troop_slots[i] = 0
            ns.troop_slot_count = 0
            return


def _build_infiltrator_session(**kwargs):
    defaults = {
        "player_ids": [_P1, _P2],
        "hand": {_P1: ["infiltrator"]},
        "current_player": _P1,
    }
    defaults.update(kwargs)
    eng = _make_engine()
    session = make_card_test_session(eng, defaults.pop("player_ids"), **defaults)
    s = session._state._ptr.contents
    s.phase = PHASE_MAIN
    return session


def _play_infiltrator(session):
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == "infiltrator":
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError("Infiltrator not playable")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_infiltrator_place_spy_no_troop_no_power():
    """Place spy at a site with no other player's troop → no power gained."""
    session = _build_infiltrator_session()
    _clear_troops(session, _SITE)
    spies_before = _spies_available(session, _P1)
    power_before = _resource_power(session)

    _play_infiltrator(session)

    assert _has_pending_generic(session)

    spy_move = None
    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == _SITE:
            spy_move = m
            break
    assert spy_move is not None, f"Place-spy move for {_SITE} not found"
    session.submit_move(spy_move)

    assert not _has_pending_generic(session)
    assert _P1 in _spies_at_node(session, _SITE)
    assert _spies_available(session, _P1) == spies_before - 1
    assert _resource_power(session) == power_before, "Should not gain power without other player's troop"

    session.destroy()


def test_infiltrator_place_spy_with_other_troop_gains_power():
    """Place spy at a site where another player has a troop → gain 1 power."""
    session = _build_infiltrator_session(
        troops={_P2: {_SITE: [_P2]}},
    )
    _clear_troops(session, _SITE)
    s = _sptr(session).contents
    nid = _lib.intern(_SITE.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            s.nodes[ni].troop_slots[0] = _lib.intern(_P2.encode())
            s.nodes[ni].troop_slot_count = 1
            break
    spies_before = _spies_available(session, _P1)
    power_before = _resource_power(session)

    _play_infiltrator(session)

    assert _has_pending_generic(session)

    spy_move = None
    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == _SITE:
            spy_move = m
            break
    assert spy_move is not None, f"Place-spy move for {_SITE} not found"
    session.submit_move(spy_move)

    assert not _has_pending_generic(session)
    assert _P1 in _spies_at_node(session, _SITE)
    assert _spies_available(session, _P1) == spies_before - 1
    assert _resource_power(session) == power_before + 1, "Should gain 1 power when other player has troop at site"

    session.destroy()


def test_infiltrator_own_troop_does_not_trigger_power():
    """Place spy at a site with only own troop → no power gained."""
    session = _build_infiltrator_session(
        troops={_P1: {_SITE2: [_P1]}},
    )
    _clear_troops(session, _SITE2)
    s = _sptr(session).contents
    nid = _lib.intern(_SITE2.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            s.nodes[ni].troop_slots[0] = _lib.intern(_P1.encode())
            s.nodes[ni].troop_slot_count = 1
            break
    spies_before = _spies_available(session, _P1)
    power_before = _resource_power(session)

    _play_infiltrator(session)

    assert _has_pending_generic(session)

    spy_move = None
    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == _SITE2:
            spy_move = m
            break
    assert spy_move is not None, f"Place-spy move for {_SITE2} not found"
    session.submit_move(spy_move)

    assert not _has_pending_generic(session)
    assert _P1 in _spies_at_node(session, _SITE2)
    assert _spies_available(session, _P1) == spies_before - 1
    assert _resource_power(session) == power_before, "Own troop should not trigger power gain"

    session.destroy()


def test_infiltrator_one_of_multiple_other_troops_gains_power():
    """Place spy at a site with multiple players' troops → gain 1 power (once)."""
    session = _build_infiltrator_session(
        player_ids=[_P1, _P2, _P3],
        troops={
            _P2: {_SITE: [_P2, _P3]},
        },
    )
    _clear_troops(session, _SITE)
    s = _sptr(session).contents
    nid = _lib.intern(_SITE.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            s.nodes[ni].troop_slots[0] = _lib.intern(_P2.encode())
            s.nodes[ni].troop_slots[1] = _lib.intern(_P3.encode())
            s.nodes[ni].troop_slot_count = 2
            break
    spies_before = _spies_available(session, _P1)
    power_before = _resource_power(session)

    _play_infiltrator(session)

    assert _has_pending_generic(session)

    spy_move = None
    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == _SITE:
            spy_move = m
            break
    assert spy_move is not None, f"Place-spy move for {_SITE} not found"
    session.submit_move(spy_move)

    assert not _has_pending_generic(session)
    assert _P1 in _spies_at_node(session, _SITE)
    assert _spies_available(session, _P1) == spies_before - 1
    assert _resource_power(session) == power_before + 1, "Should gain exactly 1 power regardless of troop count"

    session.destroy()
