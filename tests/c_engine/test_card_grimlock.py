"""Grimlock card behavior tests via the C engine bindings.

Verifies:
- Playing Grimlock deploys 1 troop (normal action fires).
- The draw-2-when-opponent-discards action is skipped during normal play
  (it is a reactive trigger gated by conditional_gate).
- When an opponent forces the owner to discard Grimlock, the reactive draw-2
  fires: Grimlock is discarded, then 2 cards are drawn from the draw deck.
"""

from __future__ import annotations

from engine_c.bindings.engine_bindings import _lib
from tests.c_engine.card_test_helpers import (
    _make_engine,
    _session_player_index,
    _sptr,
    make_card_test_session,
)

_P1 = "p1"
_P2 = "p2"
_GRIMLOCK = "grimlock"
_SITE_A = "site_gauntlgrym"


def _hand_count(session, pid):
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].hand_count


def _deck_count(session, pid):
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].deck_count


def _discard_count(session, pid):
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].discard_pile_count


def _barracks(session, pid):
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].barracks


def _has_pending_generic(session):
    return bool(session._state._ptr.contents.pending_generic)


def _played_count(session, pid):
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].played_cards_count


def _discard_contains(session, pid, card_id):
    pi = _session_player_index(session, pid)
    if pi < 0:
        return False
    ps = _sptr(session).contents.players[pi]
    target = _lib.intern(card_id.encode())
    return any(ps.discard_pile[i] == target for i in range(ps.discard_pile_count))


def _play_card(session, card_id=_GRIMLOCK):
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == card_id:
            session.submit_move(m)
            return
    raise AssertionError(f"{card_id} not playable; legal: {[(m.move_type, m.data) for m in session.legal_moves()]}")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_grimlock_deploys_one_troop_no_draw():
    """Playing Grimlock deploys 1 troop; the reactive draw-2 is skipped."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: ["grimlock", "noble"]},
        current_player=_P1,
    )

    hand_before = _hand_count(session, _P1)
    barracks_before = _barracks(session, _P1)

    _play_card(session)

    assert _has_pending_generic(session), "Should await site selection for deploy"

    for m in session.legal_moves():
        if m.move_type == "resolve_generic":
            session.submit_move(m)
            break

    assert _barracks(session, _P1) == barracks_before - 1, "1 troop deployed"
    assert _hand_count(session, _P1) == hand_before - 1, "Grimlock consumed, no extra cards drawn"
    assert _played_count(session, _P1) >= 1, "Grimlock was played"

    session.destroy()


def test_grimlock_reactive_draw_when_opponent_forces_discard():
    """When an opponent forces you to discard Grimlock, discard it then draw 2 cards.

    Uses Chuul (local_discard) to force the discard on an opponent at the spy site.
    P2 has 3 Grimlock cards in hand so the random discard always hits one.
    After discard, P2 should draw 2 cards from deck.
    """
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={
            _P1: ["chuul"],
            _P2: ["grimlock", "grimlock", "grimlock"],
        },
        deck={
            _P2: ["noble", "noble", "noble", "noble", "noble"],
        },
        troops={
            _P2: {_SITE_A: [_P2, _P2]},
        },
        current_player=_P1,
    )

    hand_before = _hand_count(session, _P2)
    deck_before = _deck_count(session, _P2)
    discard_before = _discard_count(session, _P2)
    assert hand_before == 3, "P2 starts with 3 Grimlock cards"
    assert deck_before >= 2, "P2 needs at least 2 cards in deck to draw"

    _play_card(session, "chuul")
    assert _has_pending_generic(session), "Should await spy placement"

    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == _SITE_A:
            session.submit_move(m)
            break

    assert not _has_pending_generic(session), "Chuul should fully resolve (discard auto-applies)"

    hand_after = _hand_count(session, _P2)
    deck_after = _deck_count(session, _P2)
    discard_after = _discard_count(session, _P2)

    assert discard_after == discard_before + 1, "One Grimlock was discarded"
    assert _discard_contains(session, _P2, "grimlock"), "Discard pile should contain Grimlock"
    assert deck_after == deck_before - 2, "P2 should have drawn 2 cards from deck"
    assert hand_after == 4, (
        f"P2 hand: was {hand_before}, discarded 1, drew 2 — expected 4, got {hand_after}"
    )

    session.destroy()
