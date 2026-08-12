"""Skeletal Horde card behavior tests.

Verifies:
- Deploy 2 troops (always happens)
- Optional devour of self (played_self)
- If devour skipped → no extra deploy (skip_advance_to_index)
- If devour taken → deploy 3 more troops (5 total), card to devour pile
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

_SITE = "site_gauntlgrym"
_P1 = "p1"
_P2 = "p2"

CARD_ID = "skeletal_horde"


def _build_session(*, empty_slots: int = 6) -> CSession:
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [CARD_ID]},
        troops={_P1: {_SITE: [None] * empty_slots}},
        current_player=_P1,
    )
    return session


def _has_pending(session: CSession) -> bool:
    return bool(_sptr(session).contents.pending_generic)


def _barracks(session: CSession, pid: str) -> int:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].barracks


def _devour_pile(session: CSession) -> list[str]:
    s = _sptr(session).contents
    return [_lib.intern_str(s.devour_pile[i]).decode() for i in range(s.devour_pile_count)]


def _resolve_moves(session: CSession):
    return [m for m in session.legal_moves() if m.move_type == "resolve_generic"]


def _skip_move(session: CSession):
    for m in _resolve_moves(session):
        if m.data.get("action_id") is None:
            return m
    return None


def _devour_self_move(session: CSession):
    for m in _resolve_moves(session):
        if m.data.get("action_id") == CARD_ID:
            return m
    return None


def _play_card(session: CSession) -> None:
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == CARD_ID:
            session.submit_move(m)
            return
    raise AssertionError(f"{CARD_ID} not playable")


def _deploy(session: CSession, count: int) -> None:
    for _ in range(count):
        moves = _resolve_moves(session)
        assert _skip_move(session) is None, (
            f"Unexpected skip move during deploy step; moves: {[m.data for m in moves]}"
        )
        targets = [m for m in moves if m.data.get("action_id")]
        assert targets, f"No deploy target available; moves: {[m.data for m in moves]}"
        session.submit_move(targets[0])


def test_skeletal_horde_deploys_2_troops_then_prompts_devour() -> None:
    """Playing Skeletal Horde deploys 2 troops, then prompts for optional devour."""
    session = _build_session()

    barracks_before = _barracks(session, _P1)
    _play_card(session)

    assert _has_pending(session), "Should enter deploy prompt after play"

    _deploy(session, 2)

    assert _barracks(session, _P1) == barracks_before - 2, (
        f"Expected 2 troops deployed, got {barracks_before - _barracks(session, _P1)}"
    )

    assert _has_pending(session), "Should prompt for optional devour"
    assert _skip_move(session) is not None, "Optional devour should offer a skip move"
    assert _devour_self_move(session) is not None, "Optional devour should offer self-devour"

    session.destroy()


def test_skeletal_horde_skip_devour_deploys_only_2() -> None:
    """Skipping the optional devour must NOT deploy the extra 3 troops."""
    session = _build_session()

    barracks_before = _barracks(session, _P1)
    _play_card(session)
    _deploy(session, 2)

    skip = _skip_move(session)
    assert skip is not None, "Optional devour should offer a skip move"
    session.submit_move(skip)

    assert not _has_pending(session), (
        "Expected no pending generic after skipping devour; extra deploy should be skipped"
    )
    assert _barracks(session, _P1) == barracks_before - 2, (
        f"Expected only 2 troops deployed, got {barracks_before - _barracks(session, _P1)}"
    )
    assert _devour_pile(session) == [], (
        f"Devour pile should be empty after skip, got {_devour_pile(session)}"
    )

    session.destroy()


def test_skeletal_horde_devour_deploys_5_total() -> None:
    """Devouring self deploys 3 more troops for a total of 5 and buries the card."""
    session = _build_session()

    barracks_before = _barracks(session, _P1)
    _play_card(session)
    _deploy(session, 2)

    devour = _devour_self_move(session)
    assert devour is not None, "Optional devour should offer self-devour"
    session.submit_move(devour)

    assert CARD_ID in _devour_pile(session), f"{CARD_ID} should be in devour pile"

    assert _has_pending(session), "Should prompt for the extra 3-troop deploy"
    _deploy(session, 3)

    assert not _has_pending(session), "Expected full resolution after devour deploy"
    assert _barracks(session, _P1) == barracks_before - 5, (
        f"Expected 5 troops deployed total, got {barracks_before - _barracks(session, _P1)}"
    )

    session.destroy()
