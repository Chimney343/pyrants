"""Red Dragon card behavior tests: supplant -> return spy -> VP per TOTAL controlled site."""

from __future__ import annotations

from engine_c.bindings.session import CSession
from tests.c_engine.card_test_helpers import (
    _make_engine,
    _session_player_index,
    _sptr,
    make_card_test_session,
)

_SITE_GAUNTLGRYM = "site_gauntlgrym"
_SITE_JHACHALKHYN = "site_jhachalkhyn"
_SITE_GRACKLSTUGH = "site_gracklstugh"
_P1 = "p1"
_P2 = "p2"


def _player_score(session: CSession, pid: str) -> int:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].score


def _player_vp_tokens(session: CSession, pid: str) -> int:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].vp_tokens


def _has_pending_generic(session: CSession) -> bool:
    return bool(_sptr(session).contents.pending_generic)


def _barracks(session: CSession, pid: str) -> int:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].barracks


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_red_dragon_supplant_creates_total_control_one_vp():
    """After supplant + spy return, 1 site under total control -> 1 VP."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: ["red_dragon"]},
        troops={
            _P1: {
                _SITE_GAUNTLGRYM: [_P1, _P2],
            },
        },
        spies={_SITE_GAUNTLGRYM: [_P2]},
        current_player=_P1,
    )

    score_before = _player_score(session, _P1)
    vp_before = _player_vp_tokens(session, _P1)
    barracks_before = _barracks(session, _P1)

    # Play Red Dragon
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == "red_dragon":
            session.submit_move(m)
            break

    assert _has_pending_generic(session), "Expected pending generic after playing Red Dragon"

    # Supplant p2 at site_gauntlgrym (2-slot site)
    supplant = [m for m in session.legal_moves()
                if m.move_type == "resolve_generic"
                and m.data.get("action_id") == _SITE_GAUNTLGRYM]
    assert supplant, f"No supplant moves for {_SITE_GAUNTLGRYM}"
    # Target slot 1 = p2
    p2_move = [m for m in supplant if m.data.get("target_id") == "1"]
    assert p2_move, f"Slot 1 (p2) should be supplantable, targets: {[m.data for m in supplant]}"
    session.submit_move(p2_move[0])

    assert _barracks(session, _P1) == barracks_before - 1, (
        f"Barracks should decrease: {barracks_before} -> {_barracks(session, _P1)}"
    )

    # Return p2 spy
    spy_moves = [m for m in session.legal_moves()
                  if m.move_type == "resolve_generic"]
    assert spy_moves, "Expected return spy moves"
    session.submit_move(spy_moves[0])

    # Card fully resolved (grant_vp auto-resolves)
    assert not _has_pending_generic(session), "Expected no pending generic after full resolution"

    # site_gauntlgrym: [p1, p1], no spies -> total control -> 1 VP
    assert _player_score(session, _P1) == score_before, (
        "Score should not change (VP goes to vp_tokens)"
    )
    assert _player_vp_tokens(session, _P1) == vp_before + 1, (
        f"Expected 1 vp_tokens for 1 total controlled site, "
        f"got {_player_vp_tokens(session, _P1)} (was {vp_before})"
    )

    session.destroy()


def test_red_dragon_majority_not_total_control_zero_vp():
    """Majority control without total control -> 0 VP."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: ["red_dragon"]},
        troops={
            _P1: {
                _SITE_GAUNTLGRYM: [_P1, _P2, None],
            },
        },
        spies={_SITE_GAUNTLGRYM: [_P2]},
        current_player=_P1,
    )

    score_before = _player_score(session, _P1)
    vp_before = _player_vp_tokens(session, _P1)
    barracks_before = _barracks(session, _P1)

    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == "red_dragon":
            session.submit_move(m)
            break

    # Supplant p2
    supplant = [m for m in session.legal_moves()
                if m.move_type == "resolve_generic"
                and m.data.get("action_id") == _SITE_GAUNTLGRYM
                and m.data.get("target_id") == "1"]
    session.submit_move(supplant[0])

    assert _barracks(session, _P1) == barracks_before - 1

    # Return spy
    spy_moves = [m for m in session.legal_moves()
                  if m.move_type == "resolve_generic"]
    session.submit_move(spy_moves[0])

    assert not _has_pending_generic(session)

    # After supplant: [p1, p1, None] -> 3-slot site with 1 null -> NOT total control -> 0 VP
    assert _player_score(session, _P1) == score_before
    assert _player_vp_tokens(session, _P1) == vp_before, (
        f"Expected 0 vp_tokens (null slot prevents total control), "
        f"got {_player_vp_tokens(session, _P1)} (was {vp_before})"
    )

    session.destroy()


def test_red_dragon_supplant_white_troop():
    """Red Dragon supplant should target white troops when allow_white_troop filter is set."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: ["red_dragon"]},
        troops={
            _P1: {
                _SITE_GAUNTLGRYM: [_P1, "white", _P1],
            },
        },
        spies={},
        current_player=_P1,
    )

    score_before = _player_score(session, _P1)
    vp_before = _player_vp_tokens(session, _P1)
    barracks_before = _barracks(session, _P1)

    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == "red_dragon":
            session.submit_move(m)
            break

    supplant = [m for m in session.legal_moves()
                if m.move_type == "resolve_generic"
                and m.data.get("action_id") == _SITE_GAUNTLGRYM]
    assert supplant, f"No supplant moves for {_SITE_GAUNTLGRYM}"

    target_ids = [m.data.get("target_id") for m in supplant]
    assert "1" in target_ids, (
        f"White troop (slot 1) should be supplantable, targets: {target_ids}"
    )

    # Supplant the white troop
    white_move = [m for m in supplant if m.data.get("target_id") == "1"][0]
    session.submit_move(white_move)

    assert _barracks(session, _P1) == barracks_before - 1, (
        f"Barracks should decrease: {barracks_before} -> {_barracks(session, _P1)}"
    )

    # Return spy (may have no targets)
    spy_moves = [m for m in session.legal_moves()
                  if m.move_type == "resolve_generic"]
    if spy_moves:
        session.submit_move(spy_moves[0])

    # After supplant white: [p1, p1, p1] -> all 3 slots p1 -> total control -> 1 VP
    assert _player_score(session, _P1) == score_before
    assert _player_vp_tokens(session, _P1) == vp_before + 1, (
        f"Expected 1 vp_tokens for total control of fully-filled site, "
        f"got {_player_vp_tokens(session, _P1)} (was {vp_before})"
    )

    session.destroy()


def test_red_dragon_empty_board_zero_vp():
    """When no troops/spies are on board, card resolves with 0 VP."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: ["red_dragon"]},
        troops={},
        spies={},
        current_player=_P1,
    )

    score_before = _player_score(session, _P1)
    vp_before = _player_vp_tokens(session, _P1)

    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == "red_dragon":
            session.submit_move(m)
            break

    assert not _has_pending_generic(session), (
        "Card should auto-resolve when no actions have valid targets"
    )

    assert _player_score(session, _P1) == score_before
    assert _player_vp_tokens(session, _P1) == vp_before, (
        f"Expected 0 vp_tokens with no controlled sites, "
        f"got {_player_vp_tokens(session, _P1)} (was {vp_before})"
    )

    session.destroy()


def test_red_dragon_supplant_both_player_and_white():
    """Both player and white troops must appear as supplant targets."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: ["red_dragon"]},
        troops={
            _P1: {
                _SITE_GAUNTLGRYM: [_P1, _P2, "white", None],
            },
        },
        spies={},
        current_player=_P1,
    )

    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == "red_dragon":
            session.submit_move(m)
            break

    supplant = [m for m in session.legal_moves()
                if m.move_type == "resolve_generic"
                and m.data.get("action_id") == _SITE_GAUNTLGRYM]
    assert len(supplant) >= 2, (
        f"Expected at least 2 supplant targets (player + white), got {len(supplant)}"
    )

    target_ids = [m.data.get("target_id") for m in supplant]
    assert "1" in target_ids, f"p2 troop (slot 1) should be targetable, targets: {target_ids}"
    assert "2" in target_ids, f"white troop (slot 2) should be targetable, targets: {target_ids}"

    session.destroy()


def test_red_dragon_multiple_total_control_sites():
    """Two sites under total control -> 2 VP."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: ["red_dragon"]},
        troops={
            _P1: {
                _SITE_GAUNTLGRYM: [_P1, _P1, _P1],
                _SITE_JHACHALKHYN: [_P1, _P1, _P1, _P1],
            },
        },
        spies={},
        current_player=_P1,
    )

    score_before = _player_score(session, _P1)
    vp_before = _player_vp_tokens(session, _P1)

    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == "red_dragon":
            session.submit_move(m)
            break

    # No supplant targets (no enemy troops at p1's sites), no return spy targets
    # VP auto-resolves with total control count
    assert not _has_pending_generic(session), (
        "Card should auto-resolve when no actions have valid targets"
    )

    assert _player_score(session, _P1) == score_before
    assert _player_vp_tokens(session, _P1) == vp_before + 2, (
        f"Expected 2 vp_tokens for 2 total controlled sites, "
        f"got {_player_vp_tokens(session, _P1)} (was {vp_before})"
    )

    session.destroy()


def test_red_dragon_enemy_spy_blocks_total_control():
    """An enemy spy at a site prevents total control even if all troops are yours."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: ["red_dragon"]},
        troops={
            _P1: {
                _SITE_GAUNTLGRYM: [_P1, _P1, _P1],
            },
        },
        spies={_SITE_GAUNTLGRYM: [_P2]},
        current_player=_P1,
    )

    score_before = _player_score(session, _P1)
    vp_before = _player_vp_tokens(session, _P1)

    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == "red_dragon":
            session.submit_move(m)
            break

    # No supplant targets -> first action skips
    # Return spy: p2 spy at gauntlgrym should be targetable
    spy_moves = [m for m in session.legal_moves()
                  if m.move_type == "resolve_generic"]
    assert spy_moves, "Should have return spy target"
    session.submit_move(spy_moves[0])

    assert not _has_pending_generic(session)

    # After returning p2 spy: site_gauntlgrym [p1,p1,p1], no spies -> total control -> 1 VP
    assert _player_score(session, _P1) == score_before
    assert _player_vp_tokens(session, _P1) == vp_before + 1, (
        f"Expected 1 vp_tokens after spy returned, "
        f"got {_player_vp_tokens(session, _P1)} (was {vp_before})"
    )

    session.destroy()


def test_red_dragon_return_spy_only_offers_enemy_spies():
    """spy_owner:opponent → only enemy spies are legal return targets, not own spies."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: ["red_dragon"]},
        troops={
            _P1: {
                _SITE_GAUNTLGRYM: [_P1, _P2, _P1],
            },
        },
        spies={_SITE_GAUNTLGRYM: [_P1, _P2]},
        current_player=_P1,
    )

    # Play Red Dragon
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == "red_dragon":
            session.submit_move(m)
            break

    # Supplant p2 at slot 1
    supplant = [m for m in session.legal_moves()
                if m.move_type == "resolve_generic"
                and m.data.get("action_id") == _SITE_GAUNTLGRYM
                and m.data.get("target_id") == "1"]
    assert supplant, "Should have supplant target for p2 at slot 1"
    session.submit_move(supplant[0])

    # Now check return spy moves: only enemy (p2) spy should be offered, not own (p1) spy
    spy_moves = [m for m in session.legal_moves()
                  if m.move_type == "resolve_generic"]
    assert spy_moves, "Should have return spy targets"
    # All return spy moves should be for site_gauntlgrym (the only site with spies)
    action_ids = [m.data.get("action_id") for m in spy_moves]
    assert action_ids == [_SITE_GAUNTLGRYM], (
        f"Only site_gauntlgrym should have spy targets, got {action_ids}"
    )
    # Should be exactly 1 move (only p2 spy, not p1's own spy)
    assert len(spy_moves) == 1, (
        f"Expected exactly 1 return spy target (enemy p2 spy only), "
        f"got {len(spy_moves)} moves: {[m.data for m in spy_moves]}"
    )

    session.destroy()
