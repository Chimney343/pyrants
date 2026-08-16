"""Blue Dragon card behavior tests: promote 2, VP per 3 inner circle."""

from __future__ import annotations

from engine_c.bindings.engine_bindings import MAX_ZONE_SIZE, _lib
from engine_c.bindings.session import CSession
from tests.c_engine.card_test_helpers import (
    _make_engine,
    _player_vp_tokens,
    _session_player_index,
    _sptr,
    make_card_test_session,
)

_P1 = "p1"
_P2 = "p2"


def _player_inner_circle_count(session: CSession, pid: str) -> int:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].inner_circle_count


def _player_score(session: CSession, pid: str) -> int:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].score


def _build_blue_dragon_session(
    inner_circle_cards: list[str] | None = None,
    played_cards: list[str] | None = None,
) -> CSession:
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: ["blue_dragon"]},
        current_player=_P1,
    )
    s = _sptr(session).contents
    pi = _session_player_index(session, _P1)
    ps = s.players[pi]
    if inner_circle_cards:
        for cid in inner_circle_cards:
            if ps.inner_circle_count < MAX_ZONE_SIZE:
                ps.inner_circle[ps.inner_circle_count] = _lib.intern(cid.encode())
                ps.inner_circle_count += 1
    if played_cards:
        for cid in played_cards:
            if ps.played_cards_count < MAX_ZONE_SIZE:
                ps.played_cards[ps.played_cards_count] = _lib.intern(cid.encode())
                ps.played_cards_count += 1
    return session


def _play_blue_dragon_and_promote_two(session: CSession) -> CSession:
    playable = [m for m in session.legal_moves()
                if getattr(m, "move_type", "") == "play_card"
                and m.data.get("card_id") == "blue_dragon"]
    assert playable, "Blue Dragon not in legal play_card moves"
    session.submit_move(playable[0])

    end_main = [m for m in session.legal_moves()
                if getattr(m, "move_type", "") == "end_main_phase"]
    assert end_main, "No end_main_phase move after playing Blue Dragon"
    session.submit_move(end_main[0])

    promote_moves = [m for m in session.legal_moves()
                     if getattr(m, "move_type", "") == "promote_card"]
    assert len(promote_moves) >= 1, (
        f"Expected promote_card moves, got: "
        f"{[getattr(m, 'move_type', '') for m in session.legal_moves()]}"
    )
    session.submit_move(promote_moves[0])

    promote_moves2 = [m for m in session.legal_moves()
                      if getattr(m, "move_type", "") == "promote_card"]
    assert len(promote_moves2) >= 1, (
        f"Expected second promote_card, got: "
        f"{[getattr(m, 'move_type', '') for m in session.legal_moves()]}"
    )
    session.submit_move(promote_moves2[0])

    resolve_eot = [m for m in session.legal_moves()
                   if getattr(m, "move_type", "") == "resolve_end_of_turn"]
    assert resolve_eot, (
        f"No resolve_end_of_turn after 2 promotions, got: "
        f"{[getattr(m, 'move_type', '') for m in session.legal_moves()]}"
    )
    session.submit_move(resolve_eot[0])
    return session


# ── VP tests ────────────────────────────────────────────────────────────────

def test_blue_dragon_vp_awarded_per_three_inner_circle():
    """3 inner circle cards after promotions → 1 VP token."""
    session = _build_blue_dragon_session(
        inner_circle_cards=["priestess_of_lolth"],
        played_cards=["noble", "soldier"],
    )

    before_tokens = _player_vp_tokens(session, _P1)
    before_score = _player_score(session, _P1)
    _play_blue_dragon_and_promote_two(session)

    tokens_after = _player_vp_tokens(session, _P1)
    ic_count = _player_inner_circle_count(session, _P1)

    expected_vp = ic_count // 3
    assert ic_count == 3, f"Expected 3 inner circle cards, got {ic_count}"
    assert tokens_after == before_tokens + expected_vp, (
        f"Expected {expected_vp} VP token(s) ({ic_count} inner circle // 3), "
        f"got vp_tokens={tokens_after} (was {before_tokens})"
    )
    assert _player_score(session, _P1) == before_score, (
        f"Score must not change (VP goes to vp_tokens), "
        f"was {before_score}, now {_player_score(session, _P1)}"
    )

    session.destroy()


def test_blue_dragon_zero_vp_when_under_three_inner_circle():
    """2 inner circle cards after promotions → 0 VP tokens (rounds down)."""
    session = _build_blue_dragon_session(
        inner_circle_cards=[],
        played_cards=["noble", "soldier"],
    )

    before_tokens = _player_vp_tokens(session, _P1)
    _play_blue_dragon_and_promote_two(session)

    ic_count = _player_inner_circle_count(session, _P1)
    tokens_after = _player_vp_tokens(session, _P1)

    assert ic_count == 2, f"Expected 2 inner circle cards, got {ic_count}"
    expected_vp = ic_count // 3
    assert expected_vp == 0, f"2 // 3 should be 0, got {expected_vp}"
    assert tokens_after == before_tokens, (
        f"Expected 0 VP tokens (2 inner circle // 3 = 0), "
        f"got vp_tokens={tokens_after}"
    )

    session.destroy()


def test_blue_dragon_vp_four_inner_circle_rounds_down():
    """4 inner circle cards → still 1 VP (rounds down)."""
    session = _build_blue_dragon_session(
        inner_circle_cards=["priestess_of_lolth", "noble"],
        played_cards=["noble", "soldier"],
    )

    before_tokens = _player_vp_tokens(session, _P1)
    _play_blue_dragon_and_promote_two(session)

    ic_count = _player_inner_circle_count(session, _P1)
    tokens_after = _player_vp_tokens(session, _P1)

    assert ic_count == 4, f"Expected 4 inner circle cards, got {ic_count}"
    assert tokens_after == before_tokens + 1, (
        f"Expected 1 VP token (4 inner circle // 3 = 1), "
        f"got vp_tokens={tokens_after}"
    )

    session.destroy()


def test_blue_dragon_nine_inner_circle_three_vp_tokens():
    """9+ inner circle cards after promotions → 3 VP tokens (043 scenario)."""
    session = _build_blue_dragon_session(
        inner_circle_cards=[
            "priestess_of_lolth", "kobold", "noble", "house_guard",
            "watcher_of_thay", "noble", "umber_hulk",
        ],
        played_cards=["noble", "soldier"],
    )

    before_tokens = _player_vp_tokens(session, _P1)
    before_score = _player_score(session, _P1)
    _play_blue_dragon_and_promote_two(session)

    ic_count = _player_inner_circle_count(session, _P1)
    tokens_after = _player_vp_tokens(session, _P1)

    assert ic_count == 9, f"Expected 9 inner circle cards, got {ic_count}"
    assert tokens_after == before_tokens + 3, (
        f"Expected 3 VP tokens (9 inner circle // 3 = 3), "
        f"got vp_tokens={tokens_after}"
    )
    assert _player_score(session, _P1) == before_score, (
        f"Score must not change (VP goes to vp_tokens), "
        f"was {before_score}, now {_player_score(session, _P1)}"
    )

    session.destroy()


# ── Promote regression tests ────────────────────────────────────────────────

def test_blue_dragon_promote_exactly_two_cards():
    """Promotion should fire exactly twice, then offer resolve_end_of_turn."""
    session = _build_blue_dragon_session(
        played_cards=["noble", "soldier"],
    )

    playable = [m for m in session.legal_moves()
                if getattr(m, "move_type", "") == "play_card"
                and m.data.get("card_id") == "blue_dragon"]
    session.submit_move(playable[0])

    end_main = [m for m in session.legal_moves()
                if getattr(m, "move_type", "") == "end_main_phase"]
    session.submit_move(end_main[0])

    moves1 = session.legal_moves()
    types1 = {getattr(m, "move_type", "") for m in moves1}
    assert "promote_card" in types1, f"First EOT: expected promote_card, got {types1}"

    pm = [m for m in moves1 if getattr(m, "move_type", "") == "promote_card"]
    session.submit_move(pm[0])

    moves2 = session.legal_moves()
    types2 = {getattr(m, "move_type", "") for m in moves2}
    assert "promote_card" in types2, f"Second EOT: expected promote_card again, got {types2}"

    pm2 = [m for m in moves2 if getattr(m, "move_type", "") == "promote_card"]
    session.submit_move(pm2[0])

    moves3 = session.legal_moves()
    types3 = {getattr(m, "move_type", "") for m in moves3}
    assert "promote_card" not in types3, (
        f"Third EOT: expected NO promote_card (capped at 2), got {types3}"
    )
    assert "resolve_end_of_turn" in types3, (
        f"Third EOT: expected resolve_end_of_turn, got {types3}"
    )

    session.destroy()
