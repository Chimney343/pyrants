"""Advocate card behavior tests.

Modal choice: choose exactly one mode.
- Option 1: Gain 2 influence (immediate).
- Option 2: At end of turn, promote another card played this turn.
  Mandatory (no skip when targets exist), excludes self.
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
_CARD = "advocate"


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


def test_both_options_offered_as_modal_choice():
    """Playing Advocate presents both gain_influence and promote_end_of_turn as resolve_generic moves."""
    session = _build_session()

    _play_card(session)

    assert _has_pending_generic(session), "Modal choice should be pending after play"

    gen_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    action_ids = {m.data.get("action_id") for m in gen_moves}
    assert "gain_influence" in action_ids, f"gain_influence should be offered, got: {action_ids}"
    assert "promote_end_of_turn" in action_ids, f"promote_end_of_turn should be offered, got: {action_ids}"

    session.destroy()


def test_option_1_gains_2_influence():
    """Choose option 1: gain 2 influence immediately, no deferred effects."""
    session = _build_session()
    influence_before = _influence(session)

    _play_card(session)

    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == "gain_influence":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("gain_influence not found in resolve_generic moves")

    assert _influence(session) == influence_before + 2, (
        f"Should gain 2 influence. Before: {influence_before}, After: {_influence(session)}"
    )
    assert not _has_pending_generic(session), "No pending generic after immediate action"

    session.destroy()


def test_option_2_eot_promotes_one_other_card():
    """Option 2 with one other played card: must promote that card at EOT.

    The promotion is mandatory (no skip_promote when targets exist) and
    the Advocate itself is excluded by requires_another_played_card.
    """
    session = _build_session(hand={_P1: [_CARD, "noble"]})

    _play_card(session)

    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == "promote_end_of_turn":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("promote_end_of_turn not found in resolve_generic moves")

    assert not _has_pending_generic(session), "No pending generic after modal choice"

    _play_card(session, "noble")
    _end_main_phase(session)

    s = _sptr(session).contents
    assert s.phase == PHASE_END_OF_TURN, f"Expected END_OF_TURN, got {s.phase}"

    moves = session.legal_moves()
    move_types = {m.move_type for m in moves}
    assert "promote_card" in move_types, f"Should have promote_card, got: {move_types}"
    assert "skip_promote" not in move_types, (
        f"Mandatory promotion (optional=false) should NOT offer skip_promote when targets exist, got: {move_types}"
    )

    promote_moves = [m for m in moves if m.move_type == "promote_card"]
    promote_targets = {m.data.get("card_id") for m in promote_moves}
    assert _CARD not in promote_targets, f"Self should not be a promote target: {promote_targets}"
    assert "noble" in promote_targets, "Noble should be a promote target"

    noble_promote = [m for m in promote_moves if m.data.get("card_id") == "noble"]
    assert len(noble_promote) == 1
    session.submit_move(noble_promote[0])

    assert "noble" in _inner_circle_ids(session, _P1), "Noble should be promoted"
    assert "noble" not in _played_ids(session, _P1), "Noble removed from played_cards"

    moves2 = session.legal_moves()
    move_types2 = {m.move_type for m in moves2}
    assert "resolve_end_of_turn" in move_types2, (
        f"After single promotion (promotions_remaining=1→0), should resolve EOT. Got: {move_types2}"
    )

    session.destroy()


def test_option_2_no_other_card_offers_skip():
    """Option 2 with no other played cards: skip_promote offered at EOT.

    When requires_another_played_card removes self and no other cards exist,
    the engine falls back to skip_promote.
    """
    session = _build_session(hand={_P1: [_CARD]})

    _play_card(session)

    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == "promote_end_of_turn":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("promote_end_of_turn not found")

    assert not _has_pending_generic(session)

    _end_main_phase(session)

    s = _sptr(session).contents
    assert s.phase == PHASE_END_OF_TURN

    moves = session.legal_moves()
    move_types = {m.move_type for m in moves}
    assert "promote_card" not in move_types, (
        f"No other cards, should not have promote_card, got: {move_types}"
    )
    assert "skip_promote" in move_types, (
        f"Should have skip_promote when no valid targets, got: {move_types}"
    )

    skip = [m for m in moves if m.move_type == "skip_promote"][0]
    session.submit_move(skip)

    moves2 = session.legal_moves()
    move_types2 = {m.move_type for m in moves2}
    assert "resolve_end_of_turn" in move_types2

    session.destroy()


def test_option_2_with_multiple_other_cards_player_chooses():
    """Option 2 with two other played cards: player picks one to promote.

    The promotion is mandatory, so skip_promote is not offered as long
    as valid targets exist. Only one promotion is available.
    """
    session = _build_session(hand={_P1: [_CARD, "noble", "soldier"]})

    _play_card(session)

    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == "promote_end_of_turn":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("promote_end_of_turn not found")

    assert not _has_pending_generic(session)

    _play_card(session, "noble")
    _play_card(session, "soldier")
    _end_main_phase(session)

    s = _sptr(session).contents
    assert s.phase == PHASE_END_OF_TURN

    moves = session.legal_moves()
    move_types = {m.move_type for m in moves}
    assert "promote_card" in move_types, f"Should have promote_card, got: {move_types}"
    assert "skip_promote" not in move_types, (
        f"Mandatory promotion should not offer skip_promote when targets exist, got: {move_types}"
    )

    promote_moves = [m for m in moves if m.move_type == "promote_card"]
    promote_targets = {m.data.get("card_id") for m in promote_moves}
    assert _CARD not in promote_targets
    assert "noble" in promote_targets
    assert "soldier" in promote_targets

    # Promote soldier.
    soldier_move = [m for m in promote_moves if m.data.get("card_id") == "soldier"][0]
    session.submit_move(soldier_move)

    assert "soldier" in _inner_circle_ids(session, _P1)
    assert "noble" not in _inner_circle_ids(session, _P1), "Noble should not have been promoted"

    moves2 = session.legal_moves()
    move_types2 = {m.move_type for m in moves2}
    assert "resolve_end_of_turn" in move_types2, (
        f"After single promotion, should resolve EOT. Got: {move_types2}"
    )

    session.destroy()
