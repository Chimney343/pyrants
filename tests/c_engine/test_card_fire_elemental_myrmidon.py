"""Fire Elemental Myrmidon card behavior tests.

Sequence (non-modal): Gain 2 power immediately, then at end of turn
promote an Obedience card played this turn. Mandatory when valid targets
exist; self is excluded via aspect filtering (malice != obedience).
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
_CARD = "fire_elemental_myrmidon"


def _power(session):
    return _sptr(session).contents.resource_pool.power


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


def test_gains_2_power_immediately():
    """Playing Fire Elemental Myrmidon grants 2 power immediately with no deferred choice."""
    session = _build_session()
    power_before = _power(session)

    _play_card(session)

    assert _power(session) == power_before + 2, (
        f"Should gain 2 power. Before: {power_before}, After: {_power(session)}"
    )
    session.destroy()


def test_no_modal_choice_after_play():
    """Fire Elemental Myrmidon is a sequence, not modal — no resolve_generic choices appear."""
    session = _build_session()

    _play_card(session)

    assert not _has_pending_generic(session), (
        "Sequence card with only immediate + deferred actions should have no pending generic"
    )

    gen_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert len(gen_moves) == 0, f"No resolve_generic moves expected, got: {[m.data for m in gen_moves]}"

    session.destroy()


def test_eot_promotes_obedience_card():
    """At end of turn, must promote an Obedience card in played_cards.

    Fire Elemental Myrmidon is malice, so self is excluded via aspect filter.
    Noble (obedience) should be the sole valid target; promotion is mandatory.
    """
    session = _build_session(hand={_P1: [_CARD, "noble"]})

    _play_card(session)
    assert _CARD in _played_ids(session, _P1)

    _play_card(session, "noble")
    assert "noble" in _played_ids(session, _P1)

    _end_main_phase(session)

    s = _sptr(session).contents
    assert s.phase == PHASE_END_OF_TURN, f"Expected END_OF_TURN, got {s.phase}"

    moves = session.legal_moves()
    move_types = {m.move_type for m in moves}
    assert "promote_card" in move_types, f"Should have promote_card, got: {move_types}"
    assert "skip_promote" not in move_types, (
        f"Mandatory promotion should not offer skip_promote when targets exist, got: {move_types}"
    )

    promote_moves = [m for m in moves if m.move_type == "promote_card"]
    promote_targets = {m.data.get("card_id") for m in promote_moves}
    assert _CARD not in promote_targets, (
        f"Self (malice) should not be a promote target (required_aspect=obedience): {promote_targets}"
    )
    assert "noble" in promote_targets, "Noble (obedience) should be a promote target"

    noble_promote = [m for m in promote_moves if m.data.get("card_id") == "noble"]
    assert len(noble_promote) == 1
    session.submit_move(noble_promote[0])

    assert "noble" in _inner_circle_ids(session, _P1), "Noble should be promoted"
    assert "noble" not in _played_ids(session, _P1), "Noble removed from played_cards"

    moves2 = session.legal_moves()
    move_types2 = {m.move_type for m in moves2}
    assert "resolve_end_of_turn" in move_types2, (
        f"After single promotion, should resolve EOT. Got: {move_types2}"
    )

    session.destroy()


def test_no_obedience_card_offers_skip():
    """With no Obedience cards in played_cards, skip_promote is offered at EOT."""
    session = _build_session(hand={_P1: [_CARD]})

    _play_card(session)
    assert not _has_pending_generic(session)

    _end_main_phase(session)

    s = _sptr(session).contents
    assert s.phase == PHASE_END_OF_TURN

    moves = session.legal_moves()
    move_types = {m.move_type for m in moves}
    assert "promote_card" not in move_types, (
        f"No Obedience cards, should not have promote_card, got: {move_types}"
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


def test_self_not_promotable():
    """Fire Elemental Myrmidon (malice) should not appear as a promotion target
    when it is the only card played (required_aspect=obedience)."""
    session = _build_session(hand={_P1: [_CARD]})

    _play_card(session)
    _end_main_phase(session)

    s = _sptr(session).contents
    assert s.phase == PHASE_END_OF_TURN

    moves = session.legal_moves()
    promote_moves = [m for m in moves if m.move_type == "promote_card"]
    assert len(promote_moves) == 0, (
        f"Self (malice) should not be promotable with required_aspect=obedience: "
        f"{[m.data for m in promote_moves]}"
    )

    session.destroy()


def test_multiple_obedience_cards_player_chooses():
    """With two Obedience cards + self played: pick one Obedience card to promote,
    self excluded by aspect."""
    session = _build_session(hand={_P1: [_CARD, "noble", "soldier"]})

    _play_card(session)
    _play_card(session, "noble")
    _play_card(session, "soldier")
    _end_main_phase(session)

    s = _sptr(session).contents
    assert s.phase == PHASE_END_OF_TURN

    moves = session.legal_moves()
    move_types = {m.move_type for m in moves}
    assert "promote_card" in move_types, f"Should have promote_card, got: {move_types}"
    assert "skip_promote" not in move_types, (
        f"Mandatory promotion should not offer skip when targets exist, got: {move_types}"
    )

    promote_moves = [m for m in moves if m.move_type == "promote_card"]
    promote_targets = {m.data.get("card_id") for m in promote_moves}
    assert _CARD not in promote_targets, "Self (malice) should not be promotable"
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


def test_non_obedience_card_not_promotable():
    """A non-Obedience card (e.g. soldier is Obedience, but if another malice/guile/etc
    card is played alongside an Obedience card, only the Obedience card appears."""
    # "bounty_hunter" is conquest, not obedience — should not appear as target.
    # "noble" is obedience — should appear.
    session = _build_session(hand={_P1: [_CARD, "noble", "bounty_hunter"]})

    _play_card(session)
    _play_card(session, "noble")
    _play_card(session, "bounty_hunter")
    _end_main_phase(session)

    s = _sptr(session).contents
    assert s.phase == PHASE_END_OF_TURN

    moves = session.legal_moves()
    promote_moves = [m for m in moves if m.move_type == "promote_card"]
    promote_targets = {m.data.get("card_id") for m in promote_moves}

    assert "noble" in promote_targets, "Noble (obedience) should be targetable"
    assert "bounty_hunter" not in promote_targets, (
        f"Bounty Hunter (conquest) should NOT be targetable: {promote_targets}"
    )
    assert _CARD not in promote_targets, "Self (malice) should not be targetable"

    session.destroy()


def test_sequential_play_order_matters():
    """Playing Obedience card after Fire Elemental Myrmidon still makes it a valid
    promote target at EOT.
    """
    session = _build_session(hand={_P1: [_CARD, "noble"]})

    _play_card(session)
    assert not _has_pending_generic(session)

    _play_card(session, "noble")
    _end_main_phase(session)

    s = _sptr(session).contents
    assert s.phase == PHASE_END_OF_TURN

    moves = session.legal_moves()
    promote_moves = [m for m in moves if m.move_type == "promote_card"]
    promote_targets = {m.data.get("card_id") for m in promote_moves}
    assert "noble" in promote_targets, "Noble should be target regardless of play order"
    assert _CARD not in promote_targets

    session.destroy()


def test_gain_does_not_affect_influence():
    """Fire Elemental Myrmidon grants power, not influence. Influence should remain unchanged."""
    session = _build_session()
    influence_before = _sptr(session).contents.resource_pool.influence

    _play_card(session)

    assert _sptr(session).contents.resource_pool.influence == influence_before, (
        "Influence should be unchanged (gain is power only)"
    )
    session.destroy()
