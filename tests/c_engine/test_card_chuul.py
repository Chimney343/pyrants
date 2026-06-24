"""Chuul card behavior tests.

Verifies:
- Place a spy from your units onto the board
- Each opponent at the spy site with 3+ cards in hand discards 1 card (auto-applied)
- Opponents with fewer than 3 cards are unaffected
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

_P1 = "p1"
_P2 = "p2"
_P3 = "p3"
_SITE = "site_gauntlgrym"


def _hand_count(session, pid):
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].hand_count


def _discard_count(session, pid):
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].discard_pile_count


def _spies_at_node(session, node_id):
    s = _sptr(session).contents
    nid = _lib.intern(node_id.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            return [_lib.intern_str(s.nodes[ni].spies[i]).decode() for i in range(s.nodes[ni].spy_count)]
    return []


def _has_pending_generic(session):
    return bool(_sptr(session).contents.pending_generic)


def _spies_available(session, pid):
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].spies_available


def _make_chuul_session():
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2, _P3],
        hand={
            _P1: ["chuul"],
            _P2: ["noble", "noble", "noble", "noble"],
            _P3: ["noble", "noble"],
        },
        troops={
            _P2: {_SITE: [_P2, _P3]},
        },
        current_player=_P1,
    )
    s = session._state._ptr.contents
    s.phase = PHASE_MAIN
    return session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_chuul_full_sequence():
    """Play Chuul end-to-end: place spy, opponents at site with 3+ cards discard."""
    session = _make_chuul_session()

    spies_before = _spies_available(session, _P1)
    assert spies_before >= 1

    p2_hand_before = _hand_count(session, _P2)
    p3_hand_before = _hand_count(session, _P3)
    p2_discard_before = _discard_count(session, _P2)
    p3_discard_before = _discard_count(session, _P3)

    # Play Chuul
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == "chuul":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Chuul not playable")

    assert _has_pending_generic(session)

    # Place spy at the site
    spy_move = None
    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == _SITE:
            spy_move = m
            break
    assert spy_move is not None, f"Place-spy move for {_SITE} not found"
    session.submit_move(spy_move)

    # local_discard auto-applies without further selection
    assert not _has_pending_generic(session), "Chuul should fully resolve after spy placement"

    # P1's spy should be at the site
    assert _P1 in _spies_at_node(session, _SITE)
    assert _spies_available(session, _P1) == spies_before - 1

    # P2 had 4 cards → should have discarded 1
    assert _hand_count(session, _P2) == p2_hand_before - 1, (
        f"P2 should discard 1 card (had {p2_hand_before} >= 3)"
    )
    assert _discard_count(session, _P2) == p2_discard_before + 1

    # P3 had 2 cards (< 3) → should NOT have discarded
    assert _hand_count(session, _P3) == p3_hand_before, (
        f"P3 should not discard (had {p3_hand_before} < 3)"
    )
    assert _discard_count(session, _P3) == p3_discard_before

    session.destroy()


def test_chuul_opponent_needs_three_cards():
    """Opponents with exactly 3 cards in hand should discard."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={
            _P1: ["chuul"],
            _P2: ["noble", "noble", "noble"],
        },
        troops={
            _P2: {_SITE: [_P2]},
        },
        current_player=_P1,
    )
    s = session._state._ptr.contents
    s.phase = PHASE_MAIN

    p2_hand_before = _hand_count(session, _P2)

    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == "chuul":
            session.submit_move(m)
            break

    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == _SITE:
            session.submit_move(m)
            break

    assert not _has_pending_generic(session)
    assert _hand_count(session, _P2) == p2_hand_before - 1

    session.destroy()


def test_chuul_opponent_without_presence_unaffected():
    """Opponents without presence at the spy site are not forced to discard."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2, _P3],
        hand={
            _P1: ["chuul"],
            _P2: ["noble", "noble", "noble", "noble"],
            _P3: ["noble", "noble", "noble", "noble"],
        },
        troops={
            _P2: {_SITE: [_P2]},
        },
        current_player=_P1,
    )
    s = session._state._ptr.contents
    s.phase = PHASE_MAIN

    p3_hand_before = _hand_count(session, _P3)

    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == "chuul":
            session.submit_move(m)
            break

    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == _SITE:
            session.submit_move(m)
            break

    assert not _has_pending_generic(session)
    assert _hand_count(session, _P3) == p3_hand_before, (
        "P3 has no presence at the spy site and should not discard"
    )

    session.destroy()


def test_chuul_self_not_affected():
    """The current player should never be forced to discard their own cards."""
    session = _make_chuul_session()

    s = session._state._ptr.contents
    pi = _session_player_index(session, _P1)
    s.players[pi].hand_count = 5
    s.players[pi].hand[0] = _lib.intern(b"chuul")
    for i in range(1, 5):
        s.players[pi].hand[i] = _lib.intern(b"noble")

    p1_hand_before = _hand_count(session, _P1)
    assert p1_hand_before >= 3

    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == "chuul":
            session.submit_move(m)
            break

    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == _SITE:
            session.submit_move(m)
            break

    assert not _has_pending_generic(session)
    assert _hand_count(session, _P1) == p1_hand_before - 1, (
        "P1 should only lose Chuul from hand, not from discard"
    )

    session.destroy()
