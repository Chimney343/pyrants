"""Aboleth card behavior tests via the C engine bindings.

Verifies:
- Modal choice: option_1 (place 2 spies) | option_2 (draw cards per spies on board)
- Option 1 places two spies sequentially on any board sites
- Option 2 draws cards equal to spy count and resolves immediately (no target)
- Both options available with or without spies
- Spy counts and hand counts update correctly
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
_SITE_C = "site_chaulssin"


def _hand_count(session, pid):
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].hand_count


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
        "hand": {_P1: ["aboleth"]},
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
        if m.move_type == "play_card" and m.data.get("card_id") == "aboleth":
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError("Aboleth not playable")


def _resolve_option(session, option_id):
    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == option_id:
            session.submit_move(m)
            return
    available = [m.data for m in session.legal_moves() if m.move_type == "resolve_generic"]
    session.destroy()
    raise AssertionError(f"{option_id} not found in resolve_generic moves, available: {available}")


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
# Option 1 — place two spies
# ---------------------------------------------------------------------------


def test_aboleth_option_1_places_two_spies():
    """Choose option_1, place 2 spies at different sites. Both sites have p1 spy."""
    session = _build_session()
    spies_avail = _spies_available(session, _P1)

    _play_card(session)
    assert _has_pending_generic(session), "Modal choice should be pending"

    _resolve_option(session, "option_1")
    assert _has_pending_generic(session), "First spy placement should be pending"

    _resolve_spy_placement(session, _SITE_A)
    assert _has_pending_generic(session), "Second spy placement should be pending"

    _resolve_spy_placement(session, _SITE_B)

    assert not _has_pending_generic(session)
    assert _P1 in _spies_at_node(session, _SITE_A)
    assert _P1 in _spies_at_node(session, _SITE_B)
    assert _spies_available(session, _P1) == spies_avail - 2

    session.destroy()


def test_aboleth_option_1_cannot_place_two_spies_on_same_node():
    """Engine enforces at-most-one-spy-per-node per the card rules_text."""
    session = _build_session()
    spies_avail = _spies_available(session, _P1)

    _play_card(session)
    _resolve_option(session, "option_1")
    _resolve_spy_placement(session, _SITE_A)

    assert _has_pending_generic(session), "Second spy placement should be pending"
    assert _P1 in _spies_at_node(session, _SITE_A), "First spy should be placed"

    legal_nodes = [m.data.get("action_id") for m in session.legal_moves()
                   if m.move_type == "resolve_generic"]

    assert _SITE_A not in legal_nodes, (
        f"SITE_A should be excluded (already has p1 spy); got {legal_nodes}"
    )

    _resolve_spy_placement(session, _SITE_B)

    assert not _has_pending_generic(session)
    assert _spies_available(session, _P1) == spies_avail - 2

    session.destroy()


# ---------------------------------------------------------------------------
# Option 2 — draw cards per spy on board
# ---------------------------------------------------------------------------


def test_aboleth_option_2_draws_cards_per_spy_on_board():
    """2 spies on board → draw 2 cards. Resolves immediately (no target selection)."""
    session = _build_session(
        spies={_SITE_A: [_P1], _SITE_B: [_P1]},
    )
    _set_deck(session, _P1, ["noble"] * 10)
    hand_before = _hand_count(session, _P1)

    _play_card(session)
    assert _has_pending_generic(session)

    _resolve_option(session, "option_2")

    assert not _has_pending_generic(session), "Draw resolves immediately (no targets)"
    assert _hand_count(session, _P1) == hand_before - 1 + 2, "Aboleth consumed, 2 cards drawn"

    session.destroy()


def test_aboleth_option_2_draws_zero_cards_when_no_spies():
    """No spies on board → option_2 draws 0 cards."""
    session = _build_session()
    _set_deck(session, _P1, ["noble"] * 5)
    hand_before = _hand_count(session, _P1)

    _play_card(session)
    _resolve_option(session, "option_2")

    assert not _has_pending_generic(session)
    assert _hand_count(session, _P1) == hand_before - 1, "Aboleth consumed, 0 drawn"

    session.destroy()


def test_aboleth_option_2_draws_exactly_one_per_spy():
    """3 spies → exactly 3 cards drawn, no extra."""
    session = _build_session(
        spies={_SITE_A: [_P1], _SITE_B: [_P1], _SITE_C: [_P1]},
    )
    _set_deck(session, _P1, ["noble"] * 10)
    hand_before = _hand_count(session, _P1)

    _play_card(session)
    _resolve_option(session, "option_2")

    assert not _has_pending_generic(session)
    assert _hand_count(session, _P1) == hand_before - 1 + 3, "Drew exactly 3 cards for 3 spies"

    session.destroy()


# ---------------------------------------------------------------------------
# Modal choice availability
# ---------------------------------------------------------------------------


def test_aboleth_both_options_available():
    """Modal choice offers both option_1 and option_2."""
    session = _build_session(spies={_SITE_A: [_P1]})

    _play_card(session)
    assert _has_pending_generic(session)

    options = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    option_ids = {m.data.get("action_id") for m in options}

    assert "option_1" in option_ids, f"option_1 missing; got {option_ids}"
    assert "option_2" in option_ids, f"option_2 missing; got {option_ids}"

    session.destroy()


def test_aboleth_option_2_available_without_spies():
    """Without any board spies, option_2 is still available (just draws 0)."""
    session = _build_session()

    _play_card(session)
    assert _has_pending_generic(session)

    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == "option_2":
            assert m.data.get("target_id") != "unavailable", \
                "option_2 should be viable even with zero spies"
            break
    else:
        session.destroy()
        raise AssertionError("option_2 not found in resolve_generic moves")

    session.destroy()
