"""Nothic card behavior tests.

Verifies:
- Modal choice offers two options: place a spy, or return a spy
- Option 1 places a spy from the barracks onto any site
- Option 2 returns one of your own spies to the barracks, draws 1 card,
  then each opponent with 3+ cards in hand discards 1 random card
- Opponents with fewer than 3 cards are unaffected, and the current
  player is never forced to discard
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
_P3 = "p3"
_SITE = "site_gauntlgrym"


def _spies_at_node(session, node_id: str) -> list[str]:
    s = _sptr(session).contents
    nid = _lib.intern(node_id.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            return [
                _lib.intern_str(s.nodes[ni].spies[i]).decode()
                for i in range(s.nodes[ni].spy_count)
            ]
    return []


def _spies_available(session, pid: str) -> int:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].spies_available


def _hand_count(session, pid: str) -> int:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].hand_count


def _deck_count(session, pid: str) -> int:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].deck_count


def _discard_count(session, pid: str) -> int:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].discard_pile_count


def _has_pending_generic(session) -> bool:
    return bool(_sptr(session).contents.pending_generic)


def _play_card(session, card_id: str) -> None:
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == card_id:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"{card_id} not playable")


def _resolve_target(session, action_id: str) -> None:
    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == action_id:
            session.submit_move(m)
            return
    available = [m.data for m in session.legal_moves() if m.move_type == "resolve_generic"]
    session.destroy()
    raise AssertionError(f"resolve_generic move for {action_id} not found; available: {available}")


def _make_session(**kwargs):
    eng = _make_engine()
    session = make_card_test_session(eng, [_P1, _P2, _P3], current_player=_P1, **kwargs)
    return session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_nothic_both_options_offered():
    """Playing Nothic offers both option_1 (place spy) and option_2 (return spy)."""
    session = _make_session(hand={_P1: ["nothic"]})

    _play_card(session, "nothic")
    assert _has_pending_generic(session), "Modal choice should be pending after play"

    option_ids = {
        m.data.get("action_id")
        for m in session.legal_moves()
        if m.move_type == "resolve_generic"
    }
    assert "option_1" in option_ids, f"option_1 missing; got {option_ids}"
    assert "option_2" in option_ids, f"option_2 missing; got {option_ids}"

    session.destroy()


def test_nothic_option_1_places_spy():
    """Choose option_1: place a spy from the barracks onto a chosen site."""
    session = _make_session(hand={_P1: ["nothic"]})
    spies_before = _spies_available(session, _P1)
    assert spies_before >= 1

    _play_card(session, "nothic")
    _resolve_target(session, "option_1")

    assert _has_pending_generic(session), "place_spy should require a target site"
    _resolve_target(session, _SITE)

    assert not _has_pending_generic(session), "Nothic should fully resolve after spy placement"
    assert _P1 in _spies_at_node(session, _SITE), "P1 spy should be placed at the site"
    assert _spies_available(session, _P1) == spies_before - 1, (
        f"Spies available should drop by 1 ({spies_before} -> {spies_before - 1})"
    )

    session.destroy()


def test_nothic_option_2_return_spy_draw_and_mass_discard():
    """Choose option_2: return own spy, draw 1, opponents with 3+ cards discard 1."""
    session = _make_session(
        hand={
            _P1: ["nothic"],
            _P2: ["noble", "noble", "noble", "noble"],
            _P3: ["noble", "noble"],
        },
        deck={_P1: ["soldier"]},
        spies={_SITE: [_P1]},
    )

    spies_before = _spies_available(session, _P1)
    p1_deck_before = _deck_count(session, _P1)
    p2_hand_before = _hand_count(session, _P2)
    p2_discard_before = _discard_count(session, _P2)
    p3_hand_before = _hand_count(session, _P3)
    p3_discard_before = _discard_count(session, _P3)

    _play_card(session, "nothic")
    _resolve_target(session, "option_2")

    assert _has_pending_generic(session), "return_spy should require a target spy"
    _resolve_target(session, _SITE)

    assert not _has_pending_generic(session), (
        "Nothic should fully resolve after returning the spy (draw + discard auto-apply)"
    )

    # Own spy returned to barracks.
    assert _P1 not in _spies_at_node(session, _SITE), "P1 spy should be removed from the site"
    assert _spies_available(session, _P1) == spies_before + 1, (
        f"Returned spy should be back in barracks ({spies_before} -> {spies_before + 1})"
    )

    # Drew exactly one card (nothic was consumed by play, so hand is the drawn card).
    assert _hand_count(session, _P1) == 1, "P1 should have drawn exactly 1 card"
    assert _deck_count(session, _P1) == p1_deck_before - 1, "P1 deck should shrink by 1"

    # P2 had 4 cards (>= 3) -> discards 1.
    assert _hand_count(session, _P2) == p2_hand_before - 1, (
        f"P2 should discard 1 card (had {p2_hand_before} >= 3)"
    )
    assert _discard_count(session, _P2) == p2_discard_before + 1

    # P3 had 2 cards (< 3) -> unaffected.
    assert _hand_count(session, _P3) == p3_hand_before, (
        f"P3 should not discard (had {p3_hand_before} < 3)"
    )
    assert _discard_count(session, _P3) == p3_discard_before

    session.destroy()


def test_nothic_option_2_opponent_with_exactly_three_cards_discards():
    """An opponent with exactly 3 cards is at the threshold and still discards 1."""
    session = _make_session(
        hand={
            _P1: ["nothic"],
            _P2: ["noble", "noble", "noble"],
        },
        deck={_P1: ["soldier"]},
        spies={_SITE: [_P1]},
    )

    p2_hand_before = _hand_count(session, _P2)
    assert p2_hand_before == 3

    _play_card(session, "nothic")
    _resolve_target(session, "option_2")
    _resolve_target(session, _SITE)

    assert not _has_pending_generic(session)
    assert _hand_count(session, _P2) == p2_hand_before - 1, (
        "P2 with exactly 3 cards should still discard 1"
    )

    session.destroy()


def test_nothic_option_2_self_not_forced_to_discard():
    """The current player is never forced to discard, even with 3+ cards after drawing."""
    session = _make_session(
        hand={
            _P1: ["nothic", "noble", "noble", "noble"],
            _P2: ["noble", "noble", "noble", "noble"],
        },
        deck={_P1: ["soldier"]},
        spies={_SITE: [_P1]},
    )

    _play_card(session, "nothic")
    _resolve_target(session, "option_2")
    _resolve_target(session, _SITE)

    assert not _has_pending_generic(session)

    # P1 played Nothic (4 -> 3) then drew 1 (3 -> 4): still 4, no forced discard.
    assert _hand_count(session, _P1) == 4, "P1 should not be forced to discard"
    assert _discard_count(session, _P1) == 0, "P1 discard pile should be untouched"

    # P2 still discards 1.
    assert _hand_count(session, _P2) == 3, "P2 should still discard 1"

    session.destroy()
