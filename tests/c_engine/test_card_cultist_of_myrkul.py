"""Cultist of Myrkul card behavior tests.

Modal choice: choose exactly one mode.
- Option 1: Gain 2 influence (immediate).
- Option 2: Devour this card, then at end of turn promote up to 2 other played cards.
  Promotions are individually skippable (optional) and exclude the source card.
"""

from __future__ import annotations

from engine_c.bindings.engine_bindings import PHASE_END_OF_TURN, _lib
from tests.c_engine.card_test_helpers import (
    _make_engine,
    _sptr,
    make_card_test_session,
)

_P1 = "p1"
_P2 = "p2"
_CARD = "cultist_of_myrkul"


def _influence(session):
    return _sptr(session).contents.resource_pool.influence


def _played_ids(session, pid: str) -> list[str]:
    s = _sptr(session).contents
    for i in range(s.player_count):
        if _lib.intern_str(s.players[i].player_id).decode() == pid:
            return [_lib.intern_str(s.players[i].played_cards[j]).decode()
                    for j in range(s.players[i].played_cards_count)]
    return []


def _inner_circle_ids(session, pid: str) -> list[str]:
    s = _sptr(session).contents
    for i in range(s.player_count):
        if _lib.intern_str(s.players[i].player_id).decode() == pid:
            return [_lib.intern_str(s.players[i].inner_circle[j]).decode()
                    for j in range(s.players[i].inner_circle_count)]
    return []


def _has_pending_generic(session):
    return bool(_sptr(session).contents.pending_generic)


def _build_session(**kwargs):
    defaults = {
        "player_ids": [_P1, _P2],
        "hand": {_P1: [_CARD, "noble"]},
        "current_player": _P1,
    }
    defaults.update(kwargs)
    eng = _make_engine()
    session = make_card_test_session(eng, defaults.pop("player_ids"), **defaults)
    return session


def _play_card(session, card_id=_CARD):
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == card_id:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"{card_id} not playable")


def _end_main_phase(session):
    for m in session.legal_moves():
        if m.move_type == "end_main_phase":
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError("No end_main_phase move")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_option_1_gains_2_influence():
    """Choose option 1: gain 2 influence immediately."""
    session = _build_session()
    influence_before = _influence(session)

    _play_card(session)

    assert _has_pending_generic(session), "Modal choice should be pending after play"

    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == "option_1":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("option_1 not found in resolve_generic moves")

    assert _influence(session) == influence_before + 2, (
        f"Should gain 2 influence. Before: {influence_before}, After: {_influence(session)}"
    )
    assert not _has_pending_generic(session), "No pending generic after immediate action"

    session.destroy()


def _select_devour_self(session):
    """Select the played cultist as the devour_cost target."""
    assert _has_pending_generic(session), "Should await devour target selection"
    devour_moves = [m for m in session.legal_moves()
                    if m.move_type == "resolve_generic" and m.data.get("action_id") == _CARD]
    if not devour_moves:
        devour_moves = [m for m in session.legal_moves()
                        if m.move_type == "resolve_generic"
                        and m.data.get("action_id") is not None
                        and "option" not in str(m.data.get("action_id"))]
    assert devour_moves, f"No devour target moves, legal: {[(m.move_type, m.data) for m in session.legal_moves()]}"
    session.submit_move(devour_moves[0])


def test_option_2_devour_then_eot_promotes_one_other_card():
    """Option 2 with one other played card: devour cultist, get 1 promotion at EOT.

    The promotion is skippable and the cultist itself is not a valid target.
    """
    session = _build_session(hand={_P1: [_CARD, "noble"]})

    _play_card(session)
    assert _has_pending_generic(session)

    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == "option_2":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("option_2 not found in resolve_generic moves")

    _select_devour_self(session)

    assert not _has_pending_generic(session), "Devour complete, no pending generic"
    assert _CARD not in _played_ids(session, _P1), "Cultist should be devoured from played zone"

    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == "noble":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Noble not playable")

    _end_main_phase(session)

    s = _sptr(session).contents
    assert s.phase == PHASE_END_OF_TURN, f"Expected END_OF_TURN, got {s.phase}"

    moves = session.legal_moves()
    move_types = {m.move_type for m in moves}
    assert "promote_card" in move_types, f"Should have promote_card, got: {move_types}"
    assert "skip_promote" in move_types, f"Should have skip_promote (optional=true), got: {move_types}"

    promote_moves = [m for m in moves if m.move_type == "promote_card"]
    promote_targets = {m.data.get("card_id") for m in promote_moves}
    assert _CARD not in promote_targets, f"Should not self-promote: {promote_targets}"
    assert "noble" in promote_targets, "Noble should be a promote target"

    noble_promote = [m for m in promote_moves if m.data.get("card_id") == "noble"]
    assert len(noble_promote) == 1
    session.submit_move(noble_promote[0])

    assert "noble" in _inner_circle_ids(session, _P1), "Noble should be promoted"
    assert "noble" not in _played_ids(session, _P1), "Noble removed from played_cards"

    moves2 = session.legal_moves()
    move_types2 = {m.move_type for m in moves2}
    assert "resolve_end_of_turn" in move_types2, (
        f"After single promotion (2 remaining→1→0), should resolve EOT. Got: {move_types2}"
    )

    session.destroy()


def test_option_2_promotes_up_to_two_other_cards():
    """Option 2 with two other played cards: get 2 promotion opportunities at EOT.

    Each promotion is individually skippable.
    """
    session = _build_session(hand={_P1: [_CARD, "noble", "soldier"]})

    _play_card(session)
    assert _has_pending_generic(session)

    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == "option_2":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("option_2 not found")

    _select_devour_self(session)

    assert not _has_pending_generic(session)

    for card in ["noble", "soldier"]:
        for m in session.legal_moves():
            if m.move_type == "play_card" and m.data.get("card_id") == card:
                session.submit_move(m)
                break
    _end_main_phase(session)

    s = _sptr(session).contents
    assert s.phase == PHASE_END_OF_TURN

    moves = session.legal_moves()
    move_types = {m.move_type for m in moves}
    assert "promote_card" in move_types, f"First promotion should offer promote_card, got: {move_types}"
    assert "skip_promote" in move_types, f"First promotion should be skippable, got: {move_types}"

    promote_moves = [m for m in moves if m.move_type == "promote_card"]
    promote_targets = {m.data.get("card_id") for m in promote_moves}
    assert _CARD not in promote_targets, f"Cultist should not be a target: {promote_targets}"
    assert len(promote_targets) >= 2, f"Both noble and soldier should be targets: {promote_targets}"

    noble_promote = [m for m in promote_moves if m.data.get("card_id") == "noble"]
    session.submit_move(noble_promote[0])
    assert "noble" in _inner_circle_ids(session, _P1)

    moves2 = session.legal_moves()
    move_types2 = {m.move_type for m in moves2}
    assert "promote_card" in move_types2, f"Second promotion should offer promote_card, got: {move_types2}"
    assert "skip_promote" in move_types2, f"Second promotion should be skippable, got: {move_types2}"

    promote_moves2 = [m for m in moves2 if m.move_type == "promote_card"]
    targets2 = {m.data.get("card_id") for m in promote_moves2}
    assert "noble" not in targets2, "Noble already promoted, should not appear again"
    assert "soldier" in targets2, "Soldier should still be available"

    skip2 = [m for m in moves2 if m.move_type == "skip_promote"][0]
    session.submit_move(skip2)

    moves3 = session.legal_moves()
    move_types3 = {m.move_type for m in moves3}
    assert "resolve_end_of_turn" in move_types3, (
        f"After second promotion skipped, should resolve EOT. Got: {move_types3}"
    )

    session.destroy()


def test_option_2_skip_both_promotions():
    """Option 2: both promotion opportunities can be skipped."""
    session = _build_session(hand={_P1: [_CARD, "noble"]})

    _play_card(session)
    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == "option_2":
            session.submit_move(m)
            break

    _select_devour_self(session)

    _play_card(session, "noble")
    _end_main_phase(session)

    s = _sptr(session).contents
    assert s.phase == PHASE_END_OF_TURN

    moves = session.legal_moves()
    skip_moves = [m for m in moves if m.move_type == "skip_promote"]
    assert len(skip_moves) == 1, f"Should have skip_promote, got: {[m.move_type for m in moves]}"
    session.submit_move(skip_moves[0])

    moves2 = session.legal_moves()
    move_types2 = {m.move_type for m in moves2}
    assert "resolve_end_of_turn" in move_types2, (
        f"Skipping the only promotion should resolve EOT. Got: {move_types2}"
    )
    assert "noble" not in _inner_circle_ids(session, _P1), "Noble should not be promoted after skip"

    session.destroy()


def test_option_2_no_other_played_card_still_skippable():
    """Option 2 with no other played cards: no promote targets, skip should auto-remove.

    When the cultist is the only played card and gets devoured, there are
    no other played cards to promote. The pending EOT entry should be
    resolvable (either via skip or auto-cleanup).
    """
    session = _build_session(hand={_P1: [_CARD]})

    _play_card(session)
    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == "option_2":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("option_2 not found")

    _select_devour_self(session)

    assert not _has_pending_generic(session)

    _end_main_phase(session)

    s = _sptr(session).contents
    assert s.phase == PHASE_END_OF_TURN

    moves = session.legal_moves()
    move_types = {m.move_type for m in moves}

    if "resolve_end_of_turn" in move_types:
        session.submit_move([m for m in moves if m.move_type == "resolve_end_of_turn"][0])
    elif "skip_promote" in move_types:
        session.submit_move([m for m in moves if m.move_type == "skip_promote"][0])
    else:
        session.destroy()
        raise AssertionError(f"EOT should be resolvable, got: {move_types}")

    session.destroy()
