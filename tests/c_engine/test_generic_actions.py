"""Generic runtime action tests: draw_cards.

draw_cards is an auto-resolved action (no player selection needed) so
it is applied immediately when the card's generic execution begins.
"""
from __future__ import annotations

from engine_c.bindings.engine_bindings import PHASE_MAIN, _lib
from engine_c.bindings.session import CSession
from tests.c_engine.card_test_helpers import (
    _make_engine,
    _session_player_index,
    _sptr,
    make_card_test_session,
)


def _hand_count(session: CSession, pid: str) -> int:
    pi = _session_player_index(session, pid)
    return _sptr(session).contents.players[pi].hand_count


def _deck_count(session: CSession, pid: str) -> int:
    pi = _session_player_index(session, pid)
    return _sptr(session).contents.players[pi].deck_count


def _discard_pile_count(session: CSession, pid: str) -> int:
    pi = _session_player_index(session, pid)
    return _sptr(session).contents.players[pi].discard_pile_count


def _play_rath_modar(session: CSession) -> None:
    """Play rath_modar from p1's hand.  Does NOT resolve any generics."""
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == "rath_modar":
            session.submit_move(m)
            return


# ---------------------------------------------------------------------------
# draw_cards: normal (deck has cards)
# ---------------------------------------------------------------------------


def test_draw_cards_from_deck() -> None:
    """draw_cards auto-applies when the card is played — draws from deck."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["rath_modar"]},
        deck={"p1": ["soldier", "noble", "priestess_of_lolth"]},
        troops={"p1": {"site_gauntlgrym": [None, None]}},
        current_player="p1",
    )
    s = _sptr(session).contents
    s.phase = PHASE_MAIN

    assert _hand_count(session, "p1") == 1  # rath_modar
    assert _deck_count(session, "p1") == 3

    _play_rath_modar(session)

    assert _hand_count(session, "p1") == 2  # rath_modar consumed, 2 drawn
    assert _deck_count(session, "p1") == 1  # 3 - 2 = 1

    # place_spy action should still be pending
    spy_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert len(spy_moves) >= 1, "place_spy should still be pending after auto-draw"

    session.destroy()


# ---------------------------------------------------------------------------
# draw_cards: deck empty, discard has cards → reshuffle
# ---------------------------------------------------------------------------


def test_draw_cards_shuffles_discard_when_deck_empty() -> None:
    """When deck is empty but discard has cards, reshuffle discard into
    deck then draw the expected number."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["rath_modar"]},
        troops={"p1": {"site_gauntlgrym": [None, None]}},
        current_player="p1",
    )
    s = _sptr(session).contents
    s.phase = PHASE_MAIN

    p1s = s.players[0]
    p1s.deck_count = 0
    p1s.discard_pile_count = 2
    p1s.discard_pile[0] = _lib.intern(b"soldier")
    p1s.discard_pile[1] = _lib.intern(b"noble")

    assert _hand_count(session, "p1") == 1
    assert _deck_count(session, "p1") == 0
    assert _discard_pile_count(session, "p1") == 2

    _play_rath_modar(session)

    assert _hand_count(session, "p1") == 2  # rath_modar consumed, 2 from reshuffled discard
    assert _discard_pile_count(session, "p1") == 0  # discard was reshuffled into deck then drawn
    # deck may have 0 or leftover count depending on shuffle, but hand got 2

    # place_spy should still be pending
    spy_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert len(spy_moves) >= 1, "place_spy should still be pending after reshuffle-draw"

    session.destroy()


# ---------------------------------------------------------------------------
# draw_cards: both deck and discard empty → draw silently stops
# ---------------------------------------------------------------------------


def test_draw_cards_stops_when_deck_and_discard_empty() -> None:
    """When both deck and discard are empty, draw_cards draws nothing
    (no crash, no error) and the next action still runs."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["rath_modar"]},
        troops={"p1": {"site_gauntlgrym": [None, None]}},
        current_player="p1",
    )
    s = _sptr(session).contents
    s.phase = PHASE_MAIN

    p1s = s.players[0]
    p1s.deck_count = 0
    p1s.discard_pile_count = 0

    assert _hand_count(session, "p1") == 1
    assert _deck_count(session, "p1") == 0
    assert _discard_pile_count(session, "p1") == 0

    _play_rath_modar(session)

    assert _hand_count(session, "p1") == 0  # rath_modar consumed, 0 drawn
    assert _deck_count(session, "p1") == 0
    assert _discard_pile_count(session, "p1") == 0

    # place_spy should still be pending after the empty draw
    spy_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert len(spy_moves) >= 1, "place_spy should still be pending after empty draw"

    session.destroy()
