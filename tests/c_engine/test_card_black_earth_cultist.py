"""Black Earth Cultist: At EOT promote another played card. If Ambition focus, gain 2 influence."""

from __future__ import annotations

from engine_c.bindings.engine_bindings import PHASE_END_OF_TURN, _lib
from engine_c.bindings.session import CSession
from tests.c_engine.card_test_helpers import _make_engine, _sptr, make_card_test_session


def _inner_circle_ids(session: CSession, pid: str) -> list[str]:
    s = _sptr(session).contents
    for i in range(s.player_count):
        if _lib.intern_str(s.players[i].player_id).decode() == pid:
            return [_lib.intern_str(s.players[i].inner_circle[j]).decode()
                    for j in range(s.players[i].inner_circle_count)]
    return []


def _played_ids(session: CSession, pid: str) -> list[str]:
    s = _sptr(session).contents
    for i in range(s.player_count):
        if _lib.intern_str(s.players[i].player_id).decode() == pid:
            return [_lib.intern_str(s.players[i].played_cards[j]).decode()
                    for j in range(s.players[i].played_cards_count)]
    return []


def _influence(session: CSession) -> int:
    return _sptr(session).contents.resource_pool.influence


def test_eot_promote_another_card_excludes_self():
    """EOT promote targets another played card, not Black Earth Cultist itself."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["black_earth_cultist", "noble"]},
        current_player="p1",
    )

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "black_earth_cultist":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Black Earth Cultist not playable")

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "noble":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Noble not playable")

    for m in session.legal_moves():
        if m._move_type == "end_main_phase":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("No end_main_phase")

    s = _sptr(session).contents
    assert s.phase == PHASE_END_OF_TURN, f"Expected END_OF_TURN phase, got {s.phase}"

    moves = session.legal_moves()
    move_types = {m._move_type for m in moves}
    assert "promote_card" in move_types, f"Should have promote_card move, got: {move_types}"

    promote_moves = [m for m in moves if m._move_type == "promote_card"]
    promote_targets = {m.data.get("card_id") for m in promote_moves}
    assert "black_earth_cultist" not in promote_targets, f"Should not self-promote: {promote_targets}"
    assert "noble" in promote_targets, "Noble should be a promote target"

    noble_promote = [m for m in promote_moves if m.data.get("card_id") == "noble"]
    assert len(noble_promote) == 1
    session.submit_move(noble_promote[0])

    assert "noble" in _inner_circle_ids(session, "p1"), "Noble should be promoted to inner_circle"
    assert "noble" not in _played_ids(session, "p1"), "Noble should be removed from played_cards"

    moves2 = session.legal_moves()
    move_types2 = {m._move_type for m in moves2}
    assert "promote_card" not in move_types2, f"Only one promotion allowed, got: {move_types2}"
    assert "resolve_end_of_turn" in move_types2, f"Should resolve EOT after single promotion, got: {move_types2}"

    resolve = [m for m in moves2 if m._move_type == "resolve_end_of_turn"][0]
    session.submit_move(resolve)
    session.destroy()


def test_eot_no_other_card_skip():
    """If Black Earth Cultist is the only played card, skip should be available."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["black_earth_cultist"]},
        current_player="p1",
    )

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "black_earth_cultist":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Black Earth Cultist not playable")

    for m in session.legal_moves():
        if m._move_type == "end_main_phase":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("No end_main_phase")

    s = _sptr(session).contents
    assert s.phase == PHASE_END_OF_TURN

    moves = session.legal_moves()
    move_types = {m._move_type for m in moves}
    assert "promote_card" not in move_types, f"No other played card, should not have promote, got: {move_types}"
    assert "skip_promote" in move_types, f"Should have skip_promote when no targets, got: {move_types}"

    skip = [m for m in moves if m._move_type == "skip_promote"][0]
    session.submit_move(skip)

    moves2 = session.legal_moves()
    move_types2 = {m._move_type for m in moves2}
    assert "resolve_end_of_turn" in move_types2, f"After skip, should have resolve_end_of_turn, got: {move_types2}"
    session.destroy()


def test_ambition_focus_gains_2_influence():
    """When Ambition focus is met, playing Black Earth Cultist grants 2 influence."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["black_earth_cultist", "advocate"]},
        current_player="p1",
    )
    inf_before = _influence(session)

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "black_earth_cultist":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Black Earth Cultist not playable")

    assert _influence(session) == inf_before + 2, (
        f"Should gain 2 influence from Ambition focus. "
        f"Before: {inf_before}, After: {_influence(session)}"
    )
    session.destroy()


def test_no_ambition_focus_no_influence():
    """Without another Ambition card in hand or played, no influence is gained."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["black_earth_cultist", "noble"]},
        current_player="p1",
    )
    inf_before = _influence(session)

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "black_earth_cultist":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Black Earth Cultist not playable")

    assert _influence(session) == inf_before, (
        "Should not gain influence without Ambition focus"
    )
    session.destroy()
