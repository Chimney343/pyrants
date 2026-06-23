"""Wyrmspeaker: Gain 1 influence. At end of turn, promote a different played card (cannot skip)."""

from __future__ import annotations

from engine_c.bindings.engine_bindings import PHASE_END_OF_TURN, _lib
from engine_c.bindings.session import CSession
from tests.c_engine.card_test_helpers import _make_engine, make_card_test_session


def _played_ids(session: CSession, pid: str) -> list[str]:
    s = session._state._ptr.contents
    for i in range(s.player_count):
        if _lib.intern_str(s.players[i].player_id).decode() == pid:
            return [_lib.intern_str(s.players[i].played_cards[j]).decode() for j in range(s.players[i].played_cards_count)]
    return []


def _inner_circle_ids(session: CSession, pid: str) -> list[str]:
    s = session._state._ptr.contents
    for i in range(s.player_count):
        if _lib.intern_str(s.players[i].player_id).decode() == pid:
            return [_lib.intern_str(s.players[i].inner_circle[j]).decode() for j in range(s.players[i].inner_circle_count)]
    return []


def _influence(session: CSession) -> int:
    return session._state._ptr.contents.resource_pool.influence


def test_wyrmspeaker_gain_influence_on_play():
    """Playing Wyrmspeaker should grant 1 influence."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["wyrmspeaker"]},
        current_player="p1",
    )

    inf_before = _influence(session)

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "wyrmspeaker":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Wyrmspeaker not playable")

    assert _influence(session) == inf_before + 1, "Should gain 1 influence"
    session.destroy()


def test_wyrmspeaker_eot_promote_mandatory_no_skip():
    """End-of-turn promote should be mandatory (no skip) and clean up after exhaustion."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["wyrmspeaker", "noble"]},
        current_player="p1",
    )

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "wyrmspeaker":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Wyrmspeaker not playable")

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "noble":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Noble not playable")

    # End main phase
    for m in session.legal_moves():
        if m._move_type == "end_main_phase":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("No end_main_phase")

    s = session._state._ptr.contents
    assert s.phase == PHASE_END_OF_TURN, f"Expected END_OF_TURN phase, got {s.phase}"

    moves = session.legal_moves()
    move_types = {m._move_type for m in moves}

    # Should have promote_card move(s), but NOT skip_promote (it's mandatory)
    assert "promote_card" in move_types, f"Should have promote_card move, got: {move_types}"
    assert "skip_promote" not in move_types, f"Should NOT have skip_promote for mandatory promotion, got: {move_types}"

    promote_moves = [m for m in moves if m._move_type == "promote_card"]
    promote_targets = {m.data.get("card_id") for m in promote_moves}

    # Wyrmspeaker must promote a DIFFERENT card
    assert "wyrmspeaker" not in promote_targets, f"Wyrmspeaker should not target itself: {promote_targets}"
    assert "noble" in promote_targets, "Noble should be a promote target"

    # Promote noble
    noble_promote = [m for m in promote_moves if m.data.get("card_id") == "noble"]
    assert len(noble_promote) == 1
    session.submit_move(noble_promote[0])

    # After promotion, noble should be in inner_circle, no longer in played_cards
    assert "noble" in _inner_circle_ids(session, "p1"), "Noble should be promoted to inner_circle"
    assert "noble" not in _played_ids(session, "p1"), "Noble should be removed from played_cards"

    # CRITICAL: After mandatory promotion with no more valid targets,
    # there should be NO skip_promote. The entry should be cleaned up.
    moves2 = session.legal_moves()
    move_types2 = {m._move_type for m in moves2}

    assert "skip_promote" not in move_types2, (
        f"After forced promotion with no remaining targets, skip_promote should NOT appear. "
        f"Got: {move_types2}"
    )
    assert "resolve_end_of_turn" in move_types2, (
        f"Expected resolve_end_of_turn after promotion, got: {move_types2}"
    )

    session.destroy()


def test_wyrmspeaker_eot_no_other_played_card_skip_allowed():
    """If Wyrmspeaker is the only played card, skip should be allowed
    (no valid other target to promote)."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["wyrmspeaker"]},
        current_player="p1",
    )

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "wyrmspeaker":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Wyrmspeaker not playable")

    # End main phase
    for m in session.legal_moves():
        if m._move_type == "end_main_phase":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("No end_main_phase")

    moves = session.legal_moves()
    move_types = {m._move_type for m in moves}

    # No other played card → no promote target, but skip should be available
    # because deferred_promotion_target_ids returns 0 targets
    assert "promote_card" not in move_types, f"No other played card, should not have promote, got: {move_types}"
    assert "skip_promote" in move_types, f"Should have skip_promote when no targets, got: {move_types}"

    # Skip should resolve cleanly
    skip = [m for m in moves if m._move_type == "skip_promote"][0]
    session.submit_move(skip)

    moves2 = session.legal_moves()
    move_types2 = {m._move_type for m in moves2}
    assert "resolve_end_of_turn" in move_types2, f"After skip, should have resolve_end_of_turn, got: {move_types2}"

    session.destroy()
