"""Drow Negotiator: If 4+ promoted cards, gain 3 influence. At EOT, promote another played card."""

from __future__ import annotations

from engine_c.bindings.engine_bindings import PHASE_END_OF_TURN, _lib
from engine_c.bindings.session import CSession
from tests.c_engine.card_test_helpers import _make_engine, make_card_test_session


def _inner_circle_count(session: CSession, pid: str) -> int:
    s = session._state._ptr.contents
    for i in range(s.player_count):
        if _lib.intern_str(s.players[i].player_id).decode() == pid:
            return s.players[i].inner_circle_count
    return 0


def _inner_circle_ids(session: CSession, pid: str) -> list[str]:
    s = session._state._ptr.contents
    for i in range(s.player_count):
        if _lib.intern_str(s.players[i].player_id).decode() == pid:
            return [_lib.intern_str(s.players[i].inner_circle[j]).decode()
                    for j in range(s.players[i].inner_circle_count)]
    return []


def _played_ids(session: CSession, pid: str) -> list[str]:
    s = session._state._ptr.contents
    for i in range(s.player_count):
        if _lib.intern_str(s.players[i].player_id).decode() == pid:
            return [_lib.intern_str(s.players[i].played_cards[j]).decode()
                    for j in range(s.players[i].played_cards_count)]
    return []


def _influence(session: CSession) -> int:
    return session._state._ptr.contents.resource_pool.influence


def _add_inner_circle_cards(session: CSession, pid: str, card_ids: list[str]) -> None:
    s = session._state._ptr.contents
    for i in range(s.player_count):
        if _lib.intern_str(s.players[i].player_id).decode() == pid:
            ps = s.players[i]
            for cid in card_ids:
                if ps.inner_circle_count < 20:
                    ps.inner_circle[ps.inner_circle_count] = _lib.intern(cid.encode())
                    ps.inner_circle_count += 1
            return


def test_drow_negotiator_no_influence_below_threshold():
    """With <4 promoted cards, no influence is gained."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["drow_negotiator"]},
        current_player="p1",
    )
    inf_before = _influence(session)

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "drow_negotiator":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Drow Negotiator not playable")

    assert _influence(session) == inf_before, "Should not gain influence with <4 promoted cards"
    session.destroy()


def test_drow_negotiator_gain_influence_above_threshold():
    """With 4+ promoted cards, gain 3 influence."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["drow_negotiator"]},
        current_player="p1",
    )
    _add_inner_circle_cards(session, "p1", ["noble", "noble", "priestess_of_lolth", "house_guard"])
    inf_before = _influence(session)

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "drow_negotiator":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Drow Negotiator not playable")

    assert _influence(session) == inf_before + 3, "Should gain 3 influence with 4+ promoted cards"
    session.destroy()


def test_drow_negotiator_eot_promote_another_card():
    """End-of-turn promote targets another played card, not Drow Negotiator itself."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["drow_negotiator", "noble"]},
        current_player="p1",
    )

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "drow_negotiator":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Drow Negotiator not playable")

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

    s = session._state._ptr.contents
    assert s.phase == PHASE_END_OF_TURN, f"Expected END_OF_TURN phase, got {s.phase}"

    moves = session.legal_moves()
    move_types = {m._move_type for m in moves}

    assert "promote_card" in move_types, f"Should have promote_card move, got: {move_types}"

    promote_moves = [m for m in moves if m._move_type == "promote_card"]
    promote_targets = {m.data.get("card_id") for m in promote_moves}

    assert "drow_negotiator" not in promote_targets, f"Drow Negotiator should not target itself: {promote_targets}"
    assert "noble" in promote_targets, "Noble should be a promote target"

    noble_promote = [m for m in promote_moves if m.data.get("card_id") == "noble"]
    assert len(noble_promote) == 1
    session.submit_move(noble_promote[0])

    assert "noble" in _inner_circle_ids(session, "p1"), "Noble should be promoted to inner_circle"
    assert "noble" not in _played_ids(session, "p1"), "Noble should be removed from played_cards"

    session.destroy()


def test_drow_negotiator_eot_no_other_card_skip():
    """If Drow Negotiator is the only played card, skip should be available."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["drow_negotiator"]},
        current_player="p1",
    )

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "drow_negotiator":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Drow Negotiator not playable")

    for m in session.legal_moves():
        if m._move_type == "end_main_phase":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("No end_main_phase")

    s = session._state._ptr.contents
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
