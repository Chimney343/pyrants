"""Behavioral test for Conjurer mode 2: return spy + free recruit up to 2 cards costing ≤3."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from engine_c.bindings.engine_bindings import _lib
from engine_c.bindings.session import CSession
from tests.c_engine.card_test_helpers import (
    _make_engine,
    _session_player_index,
    _sptr,
    make_card_test_session,
)

_SITE_GAUNTLGRYM = "site_gauntlgrym"
_P1 = "p1"
_P2 = "p2"


def _player_discard(session: CSession, pid: str) -> list[str]:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return []
    ps = _sptr(session).contents.players[pi]
    result = []
    for i in range(ps.discard_pile_count):
        result.append(_lib.intern_str(ps.discard_pile[i]).decode())
    return result


def _current_action_id(session: CSession) -> str | None:
    pg_ptr = _sptr(session).contents.pending_generic
    if not pg_ptr:
        return None
    pg = pg_ptr.contents
    if pg.awaiting_option:
        return None
    idx = pg.next_action_index
    if 0 <= idx < pg.current_action_count:
        aid = pg.current_actions[idx].action_id
        return _lib.intern_str(aid).decode() if aid else None
    return None


def test_conjurer_mode_2_return_spy_then_optional_recruit_age() -> None:
    """Play Conjurer mode 2: return spy, verify both optional recruit stages appear."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: ["conjurer", "noble", "soldier", "priestess_of_lolth", "house_guard"]},
        spies={_SITE_GAUNTLGRYM: [_P1]},
        current_player=_P1,
    )

    p1_idx = _session_player_index(session, _P1)
    s = _sptr(session).contents
    spies_before = s.players[p1_idx].spies_available

    play_conjurer = next(
        m for m in session.legal_moves()
        if m.move_type == "play_card" and m.data.get("card_id") == "conjurer"
    )
    session.submit_move(play_conjurer)

    gen = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    opt2 = next(m for m in gen if m.data.get("action_id") == "option_2")
    session.submit_move(opt2)

    gen = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    return_move = next(m for m in gen if m.data.get("action_id") is not None)
    assert return_move.data.get("action_id") == _SITE_GAUNTLGRYM
    session.submit_move(return_move)

    s = _sptr(session).contents
    spies_after_return = s.players[p1_idx].spies_available
    assert spies_after_return == spies_before + 1, \
        f"Spy should be returned (+1 available), was {spies_before}, now {spies_after_return}"

    gen = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert _current_action_id(session) == "option_2_action_2", \
        f"Expected option_2_action_2, got {_current_action_id(session)}"
    skip_count = sum(1 for m in gen if m.data.get("action_id") is None)
    target_count = sum(1 for m in gen if m.data.get("action_id") is not None)
    assert skip_count == 1, "Expected 1 skip move for optional recruit #1"
    assert target_count > 0, "Expected recruit targets for optional recruit #1"

    skip1 = next(m for m in gen if m.data.get("action_id") is None)
    session.submit_move(skip1)

    gen = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert _current_action_id(session) == "option_2_action_3", \
        f"Expected option_2_action_3, got {_current_action_id(session)}"
    skip_count2 = sum(1 for m in gen if m.data.get("action_id") is None)
    target_count2 = sum(1 for m in gen if m.data.get("action_id") is not None)
    assert skip_count2 == 1, "Expected 1 skip move for optional recruit #2"
    assert target_count2 > 0, "Expected recruit targets for optional recruit #2"

    session.destroy()


def test_conjurer_mode_2_recruit_filtered_by_cost_3_or_less() -> None:
    """Recruit targets must exclude cards costing >3."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: ["conjurer"]},
        spies={_SITE_GAUNTLGRYM: [_P1]},
        current_player=_P1,
    )

    s = _sptr(session).contents
    s.market.row_count = 4
    s.market.row[0] = _lib.intern(b"soldier")
    s.market.row[1] = _lib.intern(b"noble")
    s.market.row[2] = _lib.intern(b"aboleth")
    s.market.row[3] = _lib.intern(b"council_member")

    play_conjurer = next(
        m for m in session.legal_moves()
        if m.move_type == "play_card" and m.data.get("card_id") == "conjurer"
    )
    session.submit_move(play_conjurer)

    gen = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    opt2 = next(m for m in gen if m.data.get("action_id") == "option_2")
    session.submit_move(opt2)

    gen = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    return_move = next(m for m in gen if m.data.get("action_id") is not None)
    session.submit_move(return_move)

    gen = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    rec_targets = [m.data.get("action_id") for m in gen if m.data.get("action_id") is not None]
    assert "soldier" in rec_targets, "Soldier (cost 0, ≤3) should be a recruit target"
    assert "noble" in rec_targets, "Noble (cost 1, ≤3) should be a recruit target"
    assert "aboleth" not in rec_targets, "Aboleth (cost 7, >3) must NOT be a recruit target"
    assert "council_member" not in rec_targets, "Council Member (cost 6, >3) must NOT be a recruit target"

    session.destroy()


def test_conjurer_mode_2_free_recruit_no_influence_deduction() -> None:
    """Free recruit must not deduct influence, recruited card goes to discard."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: ["conjurer"]},
        spies={_SITE_GAUNTLGRYM: [_P1]},
        current_player=_P1,
    )

    s = _sptr(session).contents
    s.market.row_count = 1
    s.market.row[0] = _lib.intern(b"noble")

    p1_idx = _session_player_index(session, _P1)
    s.players[p1_idx].discard_pile_count = 0
    s.resource_pool.influence = 10

    play_conjurer = next(
        m for m in session.legal_moves()
        if m.move_type == "play_card" and m.data.get("card_id") == "conjurer"
    )
    session.submit_move(play_conjurer)

    gen = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    opt2 = next(m for m in gen if m.data.get("action_id") == "option_2")
    session.submit_move(opt2)

    gen = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    return_move = next(m for m in gen if m.data.get("action_id") is not None)
    session.submit_move(return_move)

    gen = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    noble_move = next(m for m in gen if m.data.get("action_id") == "noble")
    session.submit_move(noble_move)

    s = _sptr(session).contents
    assert s.resource_pool.influence == 10, \
        f"Free recruit must not deduct influence: still {s.resource_pool.influence}"
    assert s.players[p1_idx].discard_pile_count == 1, \
        "Recruited noble should be in discard"

    session.destroy()


def test_conjurer_mode_2_return_spy_offers_only_own_spies() -> None:
    """Return-spy selection must only offer the player's own spies, never an
    enemy spy at a site the player occupies."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: ["conjurer"]},
        spies={_SITE_GAUNTLGRYM: [_P1], "route_1": [_P2]},
        troops={_P1: {"route_1": [_P1, None, None]}},
        current_player=_P1,
    )

    play_conjurer = next(
        m for m in session.legal_moves()
        if m.move_type == "play_card" and m.data.get("card_id") == "conjurer"
    )
    session.submit_move(play_conjurer)

    gen = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    opt2 = next(m for m in gen if m.data.get("action_id") == "option_2")
    session.submit_move(opt2)

    gen = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    return_targets = {m.data.get("action_id") for m in gen if m.data.get("action_id") is not None}
    assert _SITE_GAUNTLGRYM in return_targets, "Own spy site must be a return target"
    assert "route_1" not in return_targets, "Enemy spy site must NOT be a return target"

    session.destroy()
