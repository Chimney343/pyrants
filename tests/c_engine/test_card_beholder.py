"""Beholder card behavior tests.

Verifies:
- Assassinate targets both white and player troops
- Power gain scales with trophy hall count (1 per 3, rounds down)
- trophy_hall_count includes both player and white trophies
"""

from __future__ import annotations

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))
from engine_c.bindings.engine_bindings import PHASE_MAIN, _lib
from tests.c_engine.card_test_helpers import (
    _make_engine,
    _session_player_index,
    _sptr,
    make_card_test_session,
)

_SITE = "route_27"
_P2 = "p2"
_WHITE = "white"
_P1 = "p1"
_BEHOLDER = "beholder"


def _trophy_hall(session, pid):
    pi = _session_player_index(session, pid)
    if pi < 0:
        return []
    s = _sptr(session).contents
    ps = s.players[pi]
    return [_lib.intern_str(ps.trophy_hall[j]).decode() for j in range(ps.trophy_hall_count)]


def _trophy_hall_count(session, pid):
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].trophy_hall_count


def _resource_power(session):
    return _sptr(session).contents.resource_pool.power


def _has_pending_generic(session):
    return bool(_sptr(session).contents.pending_generic)


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


def _build_beholder_session(trophy_hall_entries=None):
    """Build a session with p2 holding beholder.

    Places a white troop at _SITE and a p2 spy for presence.
    Optionally pre-fills p2's trophy hall.
    """
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P2: [_BEHOLDER, "noble"]},
        spies={_SITE: [_P2]},
        current_player=_P2,
    )
    s = _sptr(session).contents
    s.phase = PHASE_MAIN

    nid = _lib.intern(_SITE.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            s.nodes[ni].troop_slots[0] = _lib.intern(_WHITE.encode())
            s.nodes[ni].troop_slot_count = 1
            break

    if trophy_hall_entries:
        pi = _session_player_index(session, _P2)
        ps = s.players[pi]
        for j, entry in enumerate(trophy_hall_entries):
            if j >= 39:
                break
            ps.trophy_hall[j] = _lib.intern(entry.encode())
        ps.trophy_hall_count = min(len(trophy_hall_entries), 39)

    return session


def _play_beholder(session):
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == _BEHOLDER:
            session.submit_move(m)
            return
    raise AssertionError("Beholder not playable")


def _resolve_assassinate(session, target_slot="0"):
    moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    for m in moves:
        if m.data.get("action_id") == _SITE and m.data.get("target_id") == target_slot:
            session.submit_move(m)
            return
    raise AssertionError(f"No assassinate move for slot {target_slot} at {_SITE}; moves: {[m.data for m in moves]}")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_beholder_assassinate_white_troop():
    """White troop at a site with presence should be a valid assassinate target."""
    session = _build_beholder_session()
    _play_beholder(session)
    assert _has_pending_generic(session)

    _resolve_assassinate(session, "0")

    assert not _has_pending_generic(session)
    trophy = _trophy_hall(session, _P2)
    assert _WHITE in trophy, f"White should be in p2 trophy hall, got {trophy}"

    troops = _troops_at_node(session, _SITE)
    assert troops[0] is None, f"White troop should be removed from {_SITE}, got {troops}"

    session.destroy()


def test_beholder_assassinate_player_troop():
    """Player troop at a site with presence should be a valid assassinate target."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P2: [_BEHOLDER, "noble"]},
        spies={_SITE: [_P2]},
        current_player=_P2,
    )
    s = _sptr(session).contents
    s.phase = PHASE_MAIN

    nid = _lib.intern(_SITE.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            s.nodes[ni].troop_slots[0] = _lib.intern(b"p1")
            s.nodes[ni].troop_slot_count = 1
            break

    _play_beholder(session)
    assert _has_pending_generic(session)

    _resolve_assassinate(session, "0")

    assert not _has_pending_generic(session)
    trophy = _trophy_hall(session, _P2)
    assert _P1 in trophy, f"p1 should be in p2 trophy hall, got {trophy}"

    session.destroy()


def test_beholder_assassinate_requires_presence():
    """Without presence at a site, assassinate should be unavailable."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P2: [_BEHOLDER, "noble"]},
        current_player=_P2,
    )
    s = _sptr(session).contents
    s.phase = PHASE_MAIN

    _play_beholder(session)

    moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert len(moves) == 0, f"Without presence, no assassinate targets should exist; got {[m.data for m in moves]}"

    session.destroy()


def test_beholder_power_gain_zero_trophies():
    """0 trophies → 0 power after assassinate."""
    session = _build_beholder_session()
    power_before = _resource_power(session)
    _play_beholder(session)
    _resolve_assassinate(session, "0")

    assert _trophy_hall_count(session, _P2) == 1, "Should have 1 trophy (just the assassinated white)"
    assert _resource_power(session) == power_before, f"0 extra power expected, got {_resource_power(session) - power_before}"

    session.destroy()


def test_beholder_power_gain_three_trophies():
    """3 trophies → 1 power after assassinate."""
    session = _build_beholder_session(trophy_hall_entries=[_P1, _WHITE])
    assert _trophy_hall_count(session, _P2) == 2, f"Should start with 2 trophies, got {_trophy_hall_count(session, _P2)}"

    power_before = _resource_power(session)
    _play_beholder(session)
    _resolve_assassinate(session, "0")

    assert _trophy_hall_count(session, _P2) == 3, "Should have 3 trophies after assassinate"
    assert _resource_power(session) == power_before + 1, f"Expected +1 power (3/3), got {_resource_power(session) - power_before}"

    session.destroy()


def test_beholder_power_gain_rounds_down():
    """5 trophies → 1 power (5/3 = 1, rounds down)."""
    session = _build_beholder_session(trophy_hall_entries=[_P1, _WHITE, _P1, _WHITE])
    assert _trophy_hall_count(session, _P2) == 4, f"Should start with 4 trophies, got {_trophy_hall_count(session, _P2)}"

    power_before = _resource_power(session)
    _play_beholder(session)
    _resolve_assassinate(session, "0")

    assert _trophy_hall_count(session, _P2) == 5
    assert _resource_power(session) == power_before + 1, f"Expected +1 power (5/3 rounds down), got {_resource_power(session) - power_before}"

    session.destroy()


def test_beholder_power_gain_six_trophies():
    """6 trophies → 2 power (6/3 = 2)."""
    session = _build_beholder_session(trophy_hall_entries=[_P1, _WHITE, _P1, _WHITE, _P1])
    assert _trophy_hall_count(session, _P2) == 5, f"Should start with 5 trophies, got {_trophy_hall_count(session, _P2)}"

    power_before = _resource_power(session)
    _play_beholder(session)
    _resolve_assassinate(session, "0")

    assert _trophy_hall_count(session, _P2) == 6
    assert _resource_power(session) == power_before + 2, f"Expected +2 power (6/3), got {_resource_power(session) - power_before}"

    session.destroy()


def test_beholder_power_gain_counts_white_trophies():
    """Trophy hall with white-only trophies should count them for power scaling."""
    session = _build_beholder_session(trophy_hall_entries=[_WHITE, _WHITE])
    assert _trophy_hall_count(session, _P2) == 2, "Should start with 2 white trophies"

    power_before = _resource_power(session)
    _play_beholder(session)
    _resolve_assassinate(session, "0")

    assert _trophy_hall_count(session, _P2) == 3
    assert _resource_power(session) == power_before + 1, f"White-only trophies should count; expected +1 power, got {_resource_power(session) - power_before}"

    session.destroy()


def test_beholder_no_legal_targets_auto_resolves():
    """With no troops anywhere on the board, assassinate is skipped; power still awarded."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P2: [_BEHOLDER, "noble"]},
        current_player=_P2,
    )
    s = _sptr(session).contents
    s.phase = PHASE_MAIN
    pi = _session_player_index(session, _P2)
    ps = s.players[pi]
    ps.trophy_hall[0] = _lib.intern(_P1.encode())
    ps.trophy_hall[1] = _lib.intern(_WHITE.encode())
    ps.trophy_hall[2] = _lib.intern(_P1.encode())
    ps.trophy_hall_count = 3

    power_before = _resource_power(session)
    _play_beholder(session)

    assert not _has_pending_generic(session), "Card should auto-resolve with no assassinate targets"
    assert _trophy_hall_count(session, _P2) == 3, "Trophy hall unchanged (no assassinate)"
    assert _resource_power(session) == power_before + 1, f"Expected +1 power from 3 existing trophies (3/3=1), got {_resource_power(session) - power_before}"

    session.destroy()


def test_beholder_assassinated_troop_counts_toward_power():
    """The just-assassinated troop is in trophy hall before power calculation."""
    session = _build_beholder_session(trophy_hall_entries=[_P1, _P1])
    assert _trophy_hall_count(session, _P2) == 2, "Start with 2 pre-existing trophies"

    power_before = _resource_power(session)
    _play_beholder(session)
    _resolve_assassinate(session, "0")

    assert _trophy_hall_count(session, _P2) == 3, "2 pre + 1 assassinated = 3"
    assert _resource_power(session) == power_before + 1, (
        f"Assassinated troop must count: 3/3 = 1 power, got {_resource_power(session) - power_before}"
    )

    session.destroy()
