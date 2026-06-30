"""Ghost card behavior tests.

Verifies:
- Option 1: place a spy on a board site
- Option 2: return a spy, then take the top card from the devour pile
  into the player's discard pile for free
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from engine_c.bindings.engine_bindings import MAX_ZONE_SIZE, _lib
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

CARD_ID = "ghost"


def _devour_pile_ids(session: CSession) -> list[str]:
    s = _sptr(session).contents
    return [_lib.intern_str(s.devour_pile[i]).decode() for i in range(s.devour_pile_count)]


def _player_discard(session: CSession, pid: str) -> list[str]:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return []
    ps = _sptr(session).contents.players[pi]
    result = []
    for i in range(ps.discard_pile_count):
        result.append(_lib.intern_str(ps.discard_pile[i]).decode())
    return result


def _spies_at_node(session: CSession, node_id: str) -> list[str]:
    s = _sptr(session).contents
    nid = _lib.intern(node_id.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            ns = s.nodes[ni]
            return [_lib.intern_str(ns.spies[j]).decode() for j in range(ns.spy_count)]
    return []


def _player_spies_available(session: CSession, pid: str) -> int:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].spies_available


def _has_pending_generic(session: CSession) -> bool:
    return bool(_sptr(session).contents.pending_generic)


def _set_devour_pile(session: CSession, card_ids: list[str]) -> None:
    s = _sptr(session).contents
    s.devour_pile_count = min(len(card_ids), MAX_ZONE_SIZE)
    for j, cid in enumerate(card_ids[:MAX_ZONE_SIZE]):
        s.devour_pile[j] = _lib.intern(cid.encode())


def test_ghost_option_1_place_spy() -> None:
    """Ghost option 1 places a spy on a chosen board site."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [CARD_ID]},
        current_player=_P1,
    )

    play_move = next(
        m for m in session.legal_moves()
        if m.move_type == "play_card" and m.data.get("card_id") == CARD_ID
    )
    session.submit_move(play_move)

    gen = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    opt1 = next(m for m in gen if m.data.get("action_id") == "option_1")
    session.submit_move(opt1)

    gen = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    place_moves = [m for m in gen if m.data.get("action_id") is not None]
    assert place_moves, "Expected spy placement target moves"
    session.submit_move(place_moves[0])

    spy_list = _spies_at_node(session, place_moves[0].data["action_id"])
    assert _P1 in spy_list, f"Spy should be at target node, got: {spy_list}"

    assert not _has_pending_generic(session), "No pending generic after option 1 completes"
    session.destroy()


def test_ghost_option_2_return_spy_and_take_from_devour() -> None:
    """Ghost option 2 returns a spy, then takes the top devour card into discard."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [CARD_ID]},
        spies={_SITE_A: [_P1]},
        current_player=_P1,
    )

    _set_devour_pile(session, ["soldier", "noble", "priestess_of_lolth"])
    assert _devour_pile_ids(session) == ["soldier", "noble", "priestess_of_lolth"]

    spies_avail_before = _player_spies_available(session, _P1)

    play_move = next(
        m for m in session.legal_moves()
        if m.move_type == "play_card" and m.data.get("card_id") == CARD_ID
    )
    session.submit_move(play_move)

    gen = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    opt2 = next(m for m in gen if m.data.get("action_id") == "option_2")
    session.submit_move(opt2)

    gen = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    return_move = next(
        m for m in gen if m.data.get("action_id") == _SITE_A
    )
    session.submit_move(return_move)

    assert _P1 not in _spies_at_node(session, _SITE_A), (
        "Spy should be returned, still found on board"
    )
    assert _player_spies_available(session, _P1) == spies_avail_before + 1, (
        f"Spy should be returned to supply, spies_avail: "
        f"{_player_spies_available(session, _P1)}, was {spies_avail_before}"
    )

    assert _devour_pile_ids(session) == ["soldier", "noble"], (
        f"Top card (priestess_of_lolth) should be removed from devour, got: "
        f"{_devour_pile_ids(session)}"
    )

    discard = _player_discard(session, _P1)
    assert "priestess_of_lolth" in discard, (
        f"Top devour card should be in player discard, got: {discard}"
    )

    assert not _has_pending_generic(session), "No pending generic after option 2 completes"
    session.destroy()


def test_ghost_take_from_empty_devour_does_nothing() -> None:
    """Ghost option 2 with empty devour pile still returns the spy cleanly."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [CARD_ID]},
        spies={_SITE_A: [_P1]},
        current_player=_P1,
    )

    assert _devour_pile_ids(session) == []

    spies_avail_before = _player_spies_available(session, _P1)

    play_move = next(
        m for m in session.legal_moves()
        if m.move_type == "play_card" and m.data.get("card_id") == CARD_ID
    )
    session.submit_move(play_move)

    gen = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    opt2 = next(m for m in gen if m.data.get("action_id") == "option_2")
    session.submit_move(opt2)

    gen = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    return_move = next(
        m for m in gen if m.data.get("action_id") == _SITE_A
    )
    session.submit_move(return_move)

    assert _P1 not in _spies_at_node(session, _SITE_A)
    assert _player_spies_available(session, _P1) == spies_avail_before + 1
    assert _devour_pile_ids(session) == []
    assert not _has_pending_generic(session)
    session.destroy()


def test_ghost_devour_pile_order_top_is_last() -> None:
    """The top card taken from devour pile is the last-added (LIFO top)."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [CARD_ID]},
        spies={_SITE_A: [_P1]},
        current_player=_P1,
    )

    _set_devour_pile(session, ["soldier", "noble", "house_guard"])
    assert _devour_pile_ids(session) == ["soldier", "noble", "house_guard"]

    play_move = next(
        m for m in session.legal_moves()
        if m.move_type == "play_card" and m.data.get("card_id") == CARD_ID
    )
    session.submit_move(play_move)

    gen = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    opt2 = next(m for m in gen if m.data.get("action_id") == "option_2")
    session.submit_move(opt2)

    gen = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    return_move = next(
        m for m in gen if m.data.get("action_id") == _SITE_A
    )
    session.submit_move(return_move)

    assert _devour_pile_ids(session) == ["soldier", "noble"], (
        f"Top (last) card house_guard should be removed, got: {_devour_pile_ids(session)}"
    )

    discard = _player_discard(session, _P1)
    assert "house_guard" in discard, (
        f"Top card house_guard should be in discard, got: {discard}"
    )
    assert "soldier" not in discard, (
        f"Oldest devour card soldier should NOT be taken, got: {discard}"
    )
    session.destroy()
