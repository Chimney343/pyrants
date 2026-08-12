"""Rath Modar card behavior tests via the C engine bindings.

Execution model: draw 2 cards (self, auto-applied), then place a spy on a
board site (requires selection). Verifies:
- The full sequence draws two cards and then places one spy, then resolves.
- draw_cards reshuffles the discard pile into the deck when the deck is empty.
- draw_cards draws nothing (and still resolves) when deck and discard are empty.
- place_spy excludes sites where the player already has a spy.
- place_spy is skipped (card still resolves) when the player has no spies
  available.
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
_SITE_A = "site_gauntlgrym"
_SITE_B = "site_blingdenfire"


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


def _has_pending_generic(session):
    return bool(_sptr(session).contents.pending_generic)


def _build_session(**kwargs):
    defaults = {
        "player_ids": [_P1, _P2],
        "hand": {_P1: ["rath_modar"]},
        "current_player": _P1,
    }
    defaults.update(kwargs)
    eng = _make_engine()
    session = make_card_test_session(eng, defaults.pop("player_ids"), **defaults)
    s = session._state._ptr.contents
    s.phase = PHASE_MAIN
    return session


def _play_card(session):
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == "rath_modar":
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError("Rath Modar not playable")


def _resolve_spy_placement(session, node_id):
    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == node_id:
            session.submit_move(m)
            return
    available = [m.data for m in session.legal_moves() if m.move_type == "resolve_generic"]
    session.destroy()
    raise AssertionError(f"Place-spy move for {node_id} not found, available: {available}")


def _set_deck(session, pid, card_ids):
    s = _sptr(session).contents
    for i in range(s.player_count):
        if _lib.intern_str(s.players[i].player_id).decode() == pid:
            ps = s.players[i]
            ps.deck_count = min(len(card_ids), 40)
            for j, cid in enumerate(card_ids[:40]):
                ps.deck[j] = _lib.intern(cid.encode())
            return


# ---------------------------------------------------------------------------
# Full sequence
# ---------------------------------------------------------------------------


def test_rath_modar_full_sequence_draws_two_and_places_spy():
    """Play Rath Modar: draw 2 cards auto-applies, then place 1 spy, then resolves."""
    session = _build_session()
    _set_deck(session, _P1, ["soldier", "noble", "priestess_of_lolth"])
    hand_before = _hand_count(session, _P1)
    deck_before = _deck_count(session, _P1)
    spies_before = _spies_available(session, _P1)

    _play_card(session)

    # draw_cards auto-applied; place_spy should still be pending.
    assert _hand_count(session, _P1) == hand_before - 1 + 2
    assert _deck_count(session, _P1) == deck_before - 2
    assert _has_pending_generic(session), "place_spy should be pending after auto-draw"

    _resolve_spy_placement(session, _SITE_A)

    assert not _has_pending_generic(session), "Rath Modar should fully resolve after spy placement"
    assert _P1 in _spies_at_node(session, _SITE_A)
    assert _spies_available(session, _P1) == spies_before - 1

    session.destroy()


def test_rath_modar_draw_reshuffles_discard_when_deck_empty():
    """When the deck is empty, draw_cards reshuffles the discard pile first."""
    session = _build_session()
    s = _sptr(session).contents
    p1s = s.players[0]
    p1s.deck_count = 0
    p1s.discard_pile_count = 2
    p1s.discard_pile[0] = _lib.intern(b"soldier")
    p1s.discard_pile[1] = _lib.intern(b"noble")

    _play_card(session)

    # rath_modar consumed, 2 drawn from the reshuffled discard.
    assert _hand_count(session, _P1) == 2
    assert _discard_count(session, _P1) == 0
    assert _has_pending_generic(session), "place_spy should be pending after reshuffle-draw"

    _resolve_spy_placement(session, _SITE_A)
    assert not _has_pending_generic(session)
    assert _P1 in _spies_at_node(session, _SITE_A)

    session.destroy()


def test_rath_modar_draws_nothing_when_deck_and_discard_empty():
    """Empty deck and discard: draw 0, but place_spy still resolves normally."""
    session = _build_session()
    s = _sptr(session).contents
    p1s = s.players[0]
    p1s.deck_count = 0
    p1s.discard_pile_count = 0

    _play_card(session)

    assert _hand_count(session, _P1) == 0  # rath_modar consumed, 0 drawn
    assert _has_pending_generic(session), "place_spy should still be pending after empty draw"

    _resolve_spy_placement(session, _SITE_A)
    assert not _has_pending_generic(session)
    assert _P1 in _spies_at_node(session, _SITE_A)

    session.destroy()


# ---------------------------------------------------------------------------
# place_spy targeting
# ---------------------------------------------------------------------------


def test_rath_modar_place_spy_excludes_site_with_own_spy():
    """Sites already carrying one of the player's spies are not valid targets."""
    session = _build_session(spies={_SITE_A: [_P1]})
    _set_deck(session, _P1, ["soldier", "noble", "priestess_of_lolth"])

    _play_card(session)
    assert _has_pending_generic(session)

    legal_nodes = [m.data.get("action_id") for m in session.legal_moves()
                   if m.move_type == "resolve_generic"]
    assert _SITE_A not in legal_nodes, (
        f"{_SITE_A} should be excluded (already has p1 spy); got {legal_nodes}"
    )
    assert _SITE_B in legal_nodes, f"{_SITE_B} should be a legal target; got {legal_nodes}"

    _resolve_spy_placement(session, _SITE_B)
    assert not _has_pending_generic(session)
    assert _P1 in _spies_at_node(session, _SITE_B)

    session.destroy()


def test_rath_modar_skips_placement_when_no_spies_available():
    """With zero available spies, place_spy has no targets and the card still resolves."""
    session = _build_session()
    _set_deck(session, _P1, ["soldier", "noble", "priestess_of_lolth"])
    s = _sptr(session).contents
    s.players[0].spies_available = 0

    _play_card(session)

    # draw_cards applied; place_spy had no legal targets and was auto-skipped.
    assert _hand_count(session, _P1) == 2
    assert not _has_pending_generic(session), "card should resolve when no spy can be placed"
    assert _spies_at_node(session, _SITE_A) == []

    session.destroy()
