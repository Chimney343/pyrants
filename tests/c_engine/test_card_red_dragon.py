"""Red Dragon card behavior tests: supplant → return spy → VP per controlled site."""

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


def _build_red_dragon_session() -> CSession:
    """Session with:
    - p1 has Red Dragon in hand
    - p1 controls 2 sites (site_jhachalkhyn, site_gracklstugh)
    - site_gauntlgrym has p1 + p2 troops (p1 has presence, p2 troop to supplant)
    - site_gauntlgrym has a p2 spy (to return)
    After supplant + spy return, p1 will also control site_gauntlgrym
    (3 total → 3 VP).
    """
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: ["red_dragon"]},
        troops={
            _P1: {
                _SITE_GAUNTLGRYM: [_P1, _P2, None, None],
                _SITE_JHACHALKHYN: [_P1, None, None, None],
                _SITE_GRACKLSTUGH: [_P1, None, None, None],
            },
        },
        spies={_SITE_GAUNTLGRYM: [_P2]},
        current_player=_P1,
    )
    return session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_red_dragon_full_sequence():
    """Play Red Dragon end-to-end: supplant → return spy → VP per controlled site."""
    session = _build_red_dragon_session()

    score_before = _player_score(session, _P1)
    vp_tokens_before = _player_vp_tokens(session, _P1)
    barracks_before = _barracks(session, _P1)

    # --- Play Red Dragon ---
    play_move = None
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == "red_dragon":
            play_move = m
            break
    assert play_move is not None, "Red Dragon not found in hand"
    session.submit_move(play_move)

    assert _has_pending_generic(session), "Expected pending generic after playing Red Dragon"

    # --- Step 1: Supplant a troop at site_gauntlgrym ---
    supplant_moves = [
        m for m in session.legal_moves()
        if m.move_type == "resolve_generic"
        and m.data.get("action_id") == _SITE_GAUNTLGRYM
    ]
    assert supplant_moves, (
        f"No supplant moves for {_SITE_GAUNTLGRYM}; "
        f"legal: {[(m.move_type, m.data) for m in session.legal_moves()]}"
    )

    # With allow_white_troop filter, both player and white troops are targetable.
    # Pick a player target (slot 1 in our setup is p2).
    p2_supplant = None
    for sm in supplant_moves:
        if sm.data.get("target_id") == "1":
            p2_supplant = sm
            break
    if p2_supplant is None:
        # Fall back to first available
        p2_supplant = supplant_moves[0]

    session.submit_move(p2_supplant)
    assert _has_pending_generic(session), "Expected pending generic after supplant"
    assert _barracks(session, _P1) == barracks_before - 1, (
        f"Barracks should decrease by 1: {barracks_before} → {_barracks(session, _P1)}"
    )

    # --- Step 2: Return enemy spy ---
    spy_return_moves = [
        m for m in session.legal_moves()
        if m.move_type == "resolve_generic"
    ]
    assert spy_return_moves, (
        f"No return spy moves; legal: {[(m.move_type, m.data) for m in session.legal_moves()]}"
    )
    session.submit_move(spy_return_moves[0])

    # Card should be fully resolved (grant_vp auto-resolves)
    assert not _has_pending_generic(session), (
        "Expected no pending generic after full resolution"
    )

    # --- Verify VP awarded ---
    # 3 controlled sites → 3 vp_tokens
    score_after = _player_score(session, _P1)
    assert score_after == score_before, (
        f"Score should not change (VP goes to vp_tokens), "
        f"score went from {score_before} to {score_after}"
    )
    vp_tokens_after = _player_vp_tokens(session, _P1)
    assert vp_tokens_after == vp_tokens_before + 3, (
        f"Expected 3 vp_tokens for 3 controlled sites, "
        f"vp_tokens went from {vp_tokens_before} to {vp_tokens_after} (delta={vp_tokens_after - vp_tokens_before})"
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
                _SITE_GAUNTLGRYM: [_P1, "white", None, None],
            },
        },
        spies={},
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
        f"Barracks should decrease: {barracks_before} → {_barracks(session, _P1)}"
    )

    # Return spy (may have no targets — resolve if any)
    spy_moves = [m for m in session.legal_moves()
                 if m.move_type == "resolve_generic"]
    if spy_moves:
        session.submit_move(spy_moves[0])

    # 1 controlled site (site_gauntlgrym) → 1 vp_tokens
    assert _player_score(session, _P1) == score_before, (
        f"Score should not change (VP goes to vp_tokens), got {_player_score(session, _P1)}"
    )
    assert _player_vp_tokens(session, _P1) == vp_before + 1, (
        f"Expected 1 vp_tokens for 1 controlled site, got {_player_vp_tokens(session, _P1)}"
    )

    session.destroy()


def test_red_dragon_vp_scales_with_controlled_sites():
    """VP awarded should equal the number of sites p1 controls after resolution."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: ["red_dragon"]},
        troops={
            _P1: {
                _SITE_GAUNTLGRYM: [_P1, _P2, None, None],
                _SITE_JHACHALKHYN: [_P1, None, None, None],
            },
        },
        spies={_SITE_GAUNTLGRYM: [_P2]},
        current_player=_P1,
    )

    score_before = _player_score(session, _P1)
    vp_before = _player_vp_tokens(session, _P1)

    # Play Red Dragon
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == "red_dragon":
            session.submit_move(m)
            break

    # Supplant p2
    supplant = [m for m in session.legal_moves()
                if m.move_type == "resolve_generic"
                and m.data.get("action_id") == _SITE_GAUNTLGRYM]
    session.submit_move(supplant[0])

    # Return spy
    spy_return = [m for m in session.legal_moves()
                  if m.move_type == "resolve_generic"]
    session.submit_move(spy_return[0])

    # 2 controlled sites → 2 vp_tokens
    assert _player_score(session, _P1) == score_before, (
        f"Score should not change (VP goes to vp_tokens), "
        f"got {_player_score(session, _P1)} (was {score_before})"
    )
    assert _player_vp_tokens(session, _P1) == vp_before + 2, (
        f"Expected 2 vp_tokens for 2 controlled sites, "
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

    # Play Red Dragon
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == "red_dragon":
            session.submit_move(m)
            break

    # No supplant targets, no spy targets: card should auto-resolve
    assert not _has_pending_generic(session), (
        "Card should auto-resolve when no actions have valid targets"
    )

    # VP should be 0 (no controlled sites)
    assert _player_score(session, _P1) == score_before, (
        f"Expected 0 VP with no controlled sites, "
        f"got {_player_score(session, _P1)} (was {score_before})"
    )
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
