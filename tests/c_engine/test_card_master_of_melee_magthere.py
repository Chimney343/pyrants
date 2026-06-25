"""Master of Melee-Magthere card behavior tests: modal deploy 4 troops OR supplant white troop anywhere."""

from __future__ import annotations

from engine_c.bindings.session import CSession
from tests.c_engine.card_test_helpers import (
    _make_engine,
    _session_player_index,
    _sptr,
    make_card_test_session,
)

_SITE_A = "site_gauntlgrym"
_SITE_B = "site_jhachalkhyn"
_SITE_C = "site_gracklstugh"
_P1 = "p1"
_P2 = "p2"


def _has_pending_generic(session: CSession) -> bool:
    return bool(_sptr(session).contents.pending_generic)


def _barracks(session: CSession, pid: str) -> int:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].barracks


def _player_trophy_count(session: CSession, pid: str) -> int:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].trophy_hall_count


def _play_card(session: CSession, card_id: str) -> None:
    playable = [m for m in session.legal_moves()
                if getattr(m, "move_type", "") == "play_card"
                and m.data.get("card_id") == card_id]
    assert playable, f"{card_id} not playable"
    session.submit_move(playable[0])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_both_modal_options_available() -> None:
    """After playing, both option_1 (deploy 4 troops) and option_2 (supplant white) must be available."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: ["master_of_melee_magthere"]},
        troops={
            _P1: {
                _SITE_A: [_P1, None],
            },
            _P2: {
                _SITE_B: [None, "white"],
            },
        },
        current_player=_P1,
    )

    _play_card(session, "master_of_melee_magthere")
    assert _has_pending_generic(session)

    generic_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]

    option_1_moves = [m for m in generic_moves if m.data.get("action_id") == "option_1"]
    option_2_moves = [m for m in generic_moves if m.data.get("action_id") == "option_2"]

    assert option_1_moves, "option_1 (deploy 4 troops) should be available"
    assert option_2_moves, "option_2 (supplant white anywhere) should be available"

    opt1 = option_1_moves[0]
    assert opt1.data.get("target_id") != "unavailable", "option_1 should not be marked unavailable"

    opt2 = option_2_moves[0]
    assert opt2.data.get("target_id") != "unavailable", "option_2 should not be marked unavailable"

    session.destroy()


def test_deploy_mode_deploys_four_troops() -> None:
    """Option 1 deploys 4 troops to a chosen site, barracks decreases by 4."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: ["master_of_melee_magthere"]},
        troops={
            _P1: {
                _SITE_A: [_P1, None, None, None, None],
            },
        },
        current_player=_P1,
    )

    before_barracks = _barracks(session, _P1)

    _play_card(session, "master_of_melee_magthere")

    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == "option_1":
            session.submit_move(m)
            break
    else:
        raise AssertionError("option_1 not found in resolve_generic moves")

    assert _has_pending_generic(session), "Should await site selection for deploy"

    for _ in range(4):
        assert _has_pending_generic(session), "Should still await site selection for deploy"
        site_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
        deploy_move = next(
            (m for m in site_moves if m.data.get("action_id") == _SITE_A),
            None,
        )
        assert deploy_move is not None, f"No deploy move targeting {_SITE_A} on iteration"
        session.submit_move(deploy_move)

    assert not _has_pending_generic(session)
    assert _barracks(session, _P1) == before_barracks - 4, (
        f"Barracks should decrease by 4: was {before_barracks}, now {_barracks(session, _P1)}"
    )

    session.destroy()


def test_supplant_mode_anywhere_supplants_white_troop_without_presence() -> None:
    """Option 2 supplants a white troop anywhere — no troop presence required at the target site."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: ["master_of_melee_magthere"]},
        troops={
            _P2: {
                _SITE_B: ["white", None, None],
            },
        },
        current_player=_P1,
    )

    before_barracks = _barracks(session, _P1)
    before_trophies = _player_trophy_count(session, _P1)

    _play_card(session, "master_of_melee_magthere")

    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == "option_2":
            session.submit_move(m)
            break
    else:
        raise AssertionError("option_2 not found in resolve_generic moves")

    assert _has_pending_generic(session), "Should await supplant target selection"

    supplant_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    white_slot = next(
        (m for m in supplant_moves if m.data.get("action_id") == _SITE_B and m.data.get("target_id") == "0"),
        None,
    )
    assert white_slot is not None, (
        f"No supplant move for white troop at {_SITE_B} slot 0; "
        f"moves: {[(m.data.get('action_id'), m.data.get('target_id')) for m in supplant_moves]}"
    )
    session.submit_move(white_slot)

    assert not _has_pending_generic(session)
    assert _barracks(session, _P1) == before_barracks - 1, (
        f"Supplant should cost 1 troop from barracks: was {before_barracks}, now {_barracks(session, _P1)}"
    )
    assert _player_trophy_count(session, _P1) == before_trophies + 1, (
        "Supplant should add displaced white troop to trophy hall"
    )

    session.destroy()


def test_supplant_mode_cannot_target_player_troop() -> None:
    """Option 2 with white_troop_only filter should not offer player troops as supplant targets."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: ["master_of_melee_magthere"]},
        troops={
            # p1 has presence at site_A via own troops, site_B has only p2 troops (no white)
            _P1: {
                _SITE_A: [_P1, None, None],
            },
            _P2: {
                _SITE_B: [_P2, _P2],
            },
        },
        current_player=_P1,
    )

    _play_card(session, "master_of_melee_magthere")

    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == "option_2":
            session.submit_move(m)
            break
    else:
        raise AssertionError("option_2 not found in resolve_generic moves")

    supplant_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    p2_targets = [
        m for m in supplant_moves
        if m.data.get("action_id") == _SITE_B and m.data.get("target_id") in ("0", "1")
    ]
    assert not p2_targets, (
        f"Should not offer p2 troops as supplant targets; "
        f"got: {[(m.data.get('action_id'), m.data.get('target_id')) for m in p2_targets]}"
    )

    session.destroy()


def test_supplant_mode_available_at_distant_site_without_presence() -> None:
    """Option 2 should list a white troop at a site where p1 has zero troops/spies as a valid target."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: ["master_of_melee_magthere"]},
        troops={
            # p1 has troops only at site_A; white troop is at distant site_C
            _P1: {
                _SITE_A: [_P1, None],
            },
            _P2: {
                _SITE_B: ["white", None, None],
            },
        },
        current_player=_P1,
    )

    _play_card(session, "master_of_melee_magthere")

    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == "option_2":
            session.submit_move(m)
            break
    else:
        raise AssertionError("option_2 not found in resolve_generic moves")

    supplant_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    white_target = next(
        (m for m in supplant_moves if m.data.get("action_id") == _SITE_B and m.data.get("target_id") == "0"),
        None,
    )
    assert white_target is not None, (
        f"White troop at distant site {_SITE_B} slot 0 should be a valid supplant target "
        f"(anywhere rule). Moves: {[(m.data.get('action_id'), m.data.get('target_id')) for m in supplant_moves]}"
    )

    session.destroy()


def test_option_2_unavailable_without_white_troops_on_board() -> None:
    """Option 2 should be marked unavailable when no white troops exist on the board."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: ["master_of_melee_magthere"]},
        troops={
            _P1: {
                _SITE_A: [_P1, None],
            },
            _P2: {
                _SITE_B: [_P2, None],
            },
        },
        current_player=_P1,
    )

    _play_card(session, "master_of_melee_magthere")

    option_2_moves = [
        m for m in session.legal_moves()
        if m.move_type == "resolve_generic" and m.data.get("action_id") == "option_2"
    ]
    assert option_2_moves, "option_2 should appear in legal moves"
    assert option_2_moves[0].data.get("target_id") is None, (
        f"option_2 should be marked unavailable when no white troops exist, "
        f"got target_id={option_2_moves[0].data.get('target_id')!r}"
    )

    session.destroy()
