"""Revenant card behavior tests.

Verifies:
- Two assassinate (player or white) targets at board site
- After assassinations, if trophy hall has >= 8 trophies, Revenant is promoted to inner circle
- If trophy hall has < 8 trophies, Revenant is NOT promoted
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

CARD_ID = "revenant"
_SITE = "site_gauntlgrym"
_P1 = "p1"
_P2 = "p2"


def _has_pending_generic(session: CSession) -> bool:
    return bool(_sptr(session).contents.pending_generic)


def _trophy_hall(session: CSession, pid: str) -> list[str]:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return []
    ps = _sptr(session).contents.players[pi]
    return [_lib.intern_str(ps.trophy_hall[j]).decode() for j in range(ps.trophy_hall_count)]


def _inner_circle(session: CSession, pid: str) -> list[str]:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return []
    ps = _sptr(session).contents.players[pi]
    return [_lib.intern_str(ps.inner_circle[j]).decode() for j in range(ps.inner_circle_count)]


def _played_cards(session: CSession, pid: str) -> list[str]:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return []
    ps = _sptr(session).contents.players[pi]
    return [_lib.intern_str(ps.played_cards[j]).decode() for j in range(ps.played_cards_count)]


def _set_trophy_hall(session: CSession, pid: str, trophies: list[str]) -> None:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return
    ps = _sptr(session).contents.players[pi]
    ps.trophy_hall_count = min(len(trophies), 30)
    for i, t in enumerate(trophies[:30]):
        ps.trophy_hall[i] = _lib.intern(t.encode())


def _play_card(session: CSession, card_id: str = CARD_ID) -> None:
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == card_id:
            session.submit_move(m)
            return
    raise AssertionError(f"{card_id} not playable")


def _resolve_generic_moves(session: CSession) -> list:
    return [m for m in session.legal_moves() if m.move_type == "resolve_generic"]


def _pick_target(session: CSession, target_id: str) -> None:
    moves = _resolve_generic_moves(session)
    for m in moves:
        if m.data.get("target_id") == target_id:
            session.submit_move(m)
            return
    raise AssertionError(f"Target '{target_id}' not found in {[m.data.get('target_id') for m in moves]}")


def test_revenant_below_threshold_not_promoted():
    """When trophy hall has < 8 trophies, Revenant stays in played cards after resolution."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [CARD_ID, "noble"]},
        troops={_P1: {_SITE: [_P1, _P2, "white", None]}},
        current_player=_P1,
    )
    _set_trophy_hall(session, _P1, ["white"])
    assert len(_trophy_hall(session, _P1)) == 1

    _play_card(session)

    # First assassinate
    assert _has_pending_generic(session)
    moves = _resolve_generic_moves(session)
    assert len(moves) >= 1
    session.submit_move(moves[0])

    # Second assassinate
    assert _has_pending_generic(session)
    moves = _resolve_generic_moves(session)
    assert len(moves) >= 1
    session.submit_move(moves[0])

    assert not _has_pending_generic(session)
    assert CARD_ID in _played_cards(session, _P1), "Revenant should remain in played cards (< 8 trophies)"
    assert CARD_ID not in _inner_circle(session, _P1), "Revenant should NOT be in inner circle (< 8 trophies)"

    session.destroy()


def test_revenant_above_threshold_promoted():
    """When trophy hall has >= 8 trophies, Revenant is promoted to inner circle after assassinations."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [CARD_ID, "noble"]},
        troops={_P1: {_SITE: [_P1, _P2, "white", None]}},
        current_player=_P1,
    )
    _set_trophy_hall(session, _P1, ["white"] * 8)
    assert len(_trophy_hall(session, _P1)) == 8

    _play_card(session)

    # First assassinate
    assert _has_pending_generic(session)
    moves = _resolve_generic_moves(session)
    assert len(moves) >= 1
    session.submit_move(moves[0])

    # Second assassinate
    assert _has_pending_generic(session)
    moves = _resolve_generic_moves(session)
    assert len(moves) >= 1
    session.submit_move(moves[0])

    assert not _has_pending_generic(session)
    assert CARD_ID not in _played_cards(session, _P1), "Revenant should NOT be in played cards (>= 8 trophies, promoted)"
    assert CARD_ID in _inner_circle(session, _P1), "Revenant should be in inner circle (>= 8 trophies)"

    session.destroy()


def test_revenant_assassinate_targets_player_and_white():
    """Assassinate should allow targeting player troops and white troops at the board site."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [CARD_ID, "noble"]},
        troops={_P1: {_SITE: [_P1, _P2, "white", None]}},
        current_player=_P1,
    )
    _set_trophy_hall(session, _P1, ["white"])

    _play_card(session)

    moves = _resolve_generic_moves(session)
    target_ids = {m.data.get("target_id") for m in moves}

    assert len(moves) >= 1, "Should have at least one assassinate target"
    assert "0" in target_ids or "1" in target_ids or "2" in target_ids, (
        f"Expected at least one assassinate target among player/white troops, got {target_ids}"
    )

    session.destroy()
