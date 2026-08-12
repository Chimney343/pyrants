"""Puppeteer: Gain 2 influence. At end of turn, promote another card you played this turn."""

from __future__ import annotations

from engine_c.bindings.engine_bindings import PHASE_END_OF_TURN, _lib
from engine_c.bindings.session import CSession
from tests.c_engine.card_test_helpers import _make_engine, _sptr, make_card_test_session


def _play_card(session: CSession, card_id: str) -> None:
    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == card_id:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"{card_id} not in hand")


def _end_main_phase(session: CSession) -> None:
    for m in session.legal_moves():
        if m._move_type == "end_main_phase":
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError("No end_main_phase move")


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


def test_puppeteer_gains_two_influence():
    """Playing Puppeteer grants 2 influence immediately with no pending choice."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["puppeteer"]},
        current_player="p1",
    )
    influence_before = _influence(session)

    _play_card(session, "puppeteer")

    assert _influence(session) == influence_before + 2, (
        f"Expected +2 influence, got {_influence(session) - influence_before}"
    )

    gen = [m for m in session.legal_moves() if m._move_type == "resolve_generic"]
    assert not gen, f"Expected no pending generic choice, got {len(gen)}"

    session.destroy()


def test_puppeteer_eot_promote_another_card_excludes_self():
    """At EOT Puppeteer promotes another played card, never itself."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["puppeteer", "noble"]},
        current_player="p1",
    )

    _play_card(session, "puppeteer")
    _play_card(session, "noble")

    _end_main_phase(session)

    s = _sptr(session).contents
    assert s.phase == PHASE_END_OF_TURN, f"Expected END_OF_TURN phase, got {s.phase}"

    moves = session.legal_moves()
    move_types = {m._move_type for m in moves}
    assert "promote_card" in move_types, f"Should have promote_card move, got: {move_types}"

    promote_moves = [m for m in moves if m._move_type == "promote_card"]
    promote_targets = {m.data.get("card_id") for m in promote_moves}
    assert "puppeteer" not in promote_targets, f"Should not self-promote: {promote_targets}"
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


def test_puppeteer_eot_with_no_other_card_skips():
    """When Puppeteer is the only played card, EOT offers skip rather than soft-locking."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["puppeteer"]},
        current_player="p1",
    )

    _play_card(session, "puppeteer")
    _end_main_phase(session)

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
