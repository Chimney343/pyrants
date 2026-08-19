"""Green Dragon card behavior tests: owned_control_markers count for grant_vp."""

from __future__ import annotations

from pathlib import Path

from engine_c.bindings.session import CSession
from engine_c.bindings.view import build_c_game_view
from tests.c_engine.card_test_helpers import (
    _make_engine,
    _session_player_index,
    _sptr,
    make_card_test_session,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

_P1 = "p1"
_P2 = "p2"


def _player_score(session: CSession, pid: str) -> int:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].score


def _has_pending_generic(session: CSession) -> bool:
    return bool(_sptr(session).contents.pending_generic)


def _build_green_dragon_session(control_marker_site: str, include_extra_controlled: bool = False) -> CSession:
    eng = _make_engine()
    troops: dict[str, dict[str, list[str | None]]] = {
        _P1: {
            control_marker_site: [_P1, _P1, _P1, _P2, _P2, None],
        },
    }
    if include_extra_controlled:
        extra_site = None
        for sid in ["site_gauntlgrym", "site_jhachalkhyn"]:
            if sid == control_marker_site:
                continue
            extra_site = sid
            break
        if extra_site:
            troops[_P1][extra_site] = [_P1, _P1, None, None, None, None]

    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: ["green_dragon"]},
        troops=troops,
        spies={control_marker_site: [_P1]},
        current_player=_P1,
    )
    return session


def test_green_dragon_vp_equals_one_when_controlling_marker_site():
    """p1 controls site_menzoberranzan (per-turn VP > 0) → 1 VP from grant_vp."""
    session = _build_green_dragon_session("site_menzoberranzan")
    before_score = _player_score(session, _P1)

    playable = [m for m in session.legal_moves()
                if getattr(m, "move_type", "") == "play_card"
                and m.data.get("card_id") == "green_dragon"]
    assert playable, "Green Dragon not playable"
    session.submit_move(playable[0])

    assert _has_pending_generic(session)

    opt2 = [m for m in session.legal_moves()
            if getattr(m, "move_type", "") == "resolve_generic"
            and m.data.get("action_id") == "option_2"]
    assert opt2, f"option_2 not available, moves: {[m.data for m in session.legal_moves()]}"
    session.submit_move(opt2[0])

    assert _has_pending_generic(session)

    view = build_c_game_view(session)
    return_spy_moves = [m for m in view.legal_moves
                        if m.move_type == "resolve_generic"
                        and "Return spy" in m.label]
    assert return_spy_moves, f"No return_spy moves, labels: {[m.label for m in view.legal_moves]}"
    session.submit_move(return_spy_moves[0].move)

    assert _has_pending_generic(session)

    view = build_c_game_view(session)
    supplant_moves = [m for m in view.legal_moves
                      if m.move_type == "resolve_generic"
                      and "supplant" in m.label.lower()]
    assert supplant_moves, f"No supplant moves, labels: {[m.label for m in view.legal_moves]}"
    session.submit_move(supplant_moves[0].move)

    assert not _has_pending_generic(session), "Expected card to fully resolve"

    after_score = _player_score(session, _P1)
    assert after_score == before_score + 1, (
        f"Expected 1 VP for controlling one marker site, "
        f"score went from {before_score} to {after_score}"
    )

    session.destroy()


def test_green_dragon_zero_markers_gives_zero_vp():
    """p1 controls only zero-VP-per-turn sites → 0 VP from grant_vp."""
    session = _build_green_dragon_session("site_gauntlgrym")
    before_score = _player_score(session, _P1)

    playable = [m for m in session.legal_moves()
                if getattr(m, "move_type", "") == "play_card"
                and m.data.get("card_id") == "green_dragon"]
    assert playable, "Green Dragon not playable"
    session.submit_move(playable[0])

    opt2 = [m for m in session.legal_moves()
            if getattr(m, "move_type", "") == "resolve_generic"
            and m.data.get("action_id") == "option_2"]
    assert opt2, f"option_2 not available, moves: {[m.data for m in session.legal_moves()]}"
    session.submit_move(opt2[0])

    view = build_c_game_view(session)
    return_spy_moves = [m for m in view.legal_moves
                        if m.move_type == "resolve_generic"
                        and "Return spy" in m.label]
    assert return_spy_moves, f"No return_spy moves, labels: {[m.label for m in view.legal_moves]}"
    session.submit_move(return_spy_moves[0].move)

    view = build_c_game_view(session)
    supplant_moves = [m for m in view.legal_moves
                      if m.move_type == "resolve_generic"
                      and "supplant" in m.label.lower()]
    assert supplant_moves, f"No supplant moves, labels: {[m.label for m in view.legal_moves]}"
    session.submit_move(supplant_moves[0].move)

    assert not _has_pending_generic(session), "Expected card to fully resolve"

    after_score = _player_score(session, _P1)
    assert after_score == before_score, (
        f"Expected 0 VP (no marker sites controlled), "
        f"score went from {before_score} to {after_score}"
    )

    session.destroy()


def test_green_dragon_controlled_site_without_per_turn_vp_does_not_count():
    """A majority-controlled site with total_control_vp_per_turn == 0 is NOT counted."""
    session = _build_green_dragon_session("site_menzoberranzan", include_extra_controlled=True)
    before_score = _player_score(session, _P1)

    playable = [m for m in session.legal_moves()
                if getattr(m, "move_type", "") == "play_card"
                and m.data.get("card_id") == "green_dragon"]
    assert playable, "Green Dragon not playable"
    session.submit_move(playable[0])

    opt2 = [m for m in session.legal_moves()
            if getattr(m, "move_type", "") == "resolve_generic"
            and m.data.get("action_id") == "option_2"]
    assert opt2, f"option_2 not available, moves: {[m.data for m in session.legal_moves()]}"
    session.submit_move(opt2[0])

    view = build_c_game_view(session)
    return_spy_moves = [m for m in view.legal_moves
                        if m.move_type == "resolve_generic"
                        and "Return spy" in m.label]
    assert return_spy_moves, f"No return_spy moves, labels: {[m.label for m in view.legal_moves]}"
    session.submit_move(return_spy_moves[0].move)

    view = build_c_game_view(session)
    supplant_moves = [m for m in view.legal_moves
                      if m.move_type == "resolve_generic"
                      and "supplant" in m.label.lower()]
    assert supplant_moves, f"No supplant moves, labels: {[m.label for m in view.legal_moves]}"
    session.submit_move(supplant_moves[0].move)

    assert not _has_pending_generic(session), "Expected card to fully resolve"

    after_score = _player_score(session, _P1)
    assert after_score == before_score + 1, (
        f"Expected 1 VP (only the marker site counts, not extra controlled sites), "
        f"score went from {before_score} to {after_score}"
    )

    session.destroy()


def _build_green_dragon_option1_session() -> CSession:
    """Session with p1 holding green_dragon, p2 troop at site_menzoberranzan."""
    eng = _make_engine()
    troops = {
        _P1: {"site_menzoberranzan": [_P1, _P2, None, None, None, None]},
    }
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: ["green_dragon"]},
        troops=troops,
        current_player=_P1,
    )
    return session


def test_green_dragon_option1_place_spy_and_supplant():
    """Option 1: place a spy, then supplant a troop at that same site."""
    session = _build_green_dragon_option1_session()

    playable = [m for m in session.legal_moves()
                if getattr(m, "move_type", "") == "play_card"
                and m.data.get("card_id") == "green_dragon"]
    assert playable, "Green Dragon not playable"
    session.submit_move(playable[0])

    opt1 = [m for m in session.legal_moves()
            if getattr(m, "move_type", "") == "resolve_generic"
            and m.data.get("action_id") == "option_1"]
    assert opt1, f"option_1 not available, moves: {[m.data for m in session.legal_moves()]}"
    session.submit_move(opt1[0])

    assert _has_pending_generic(session)

    view = build_c_game_view(session)
    place_spy_moves = [m for m in view.legal_moves
                       if m.move_type == "resolve_generic"
                       and "Place spy" in m.label]
    assert place_spy_moves, f"No place_spy moves, labels: {[m.label for m in view.legal_moves]}"
    menzo_place = [m for m in place_spy_moves if "menzoberranzan" in m.label.lower()]
    assert menzo_place, f"No menzoberranzan place spy move, labels: {[m.label for m in place_spy_moves]}"
    session.submit_move(menzo_place[0].move)

    assert _has_pending_generic(session)

    view = build_c_game_view(session)
    supplant_moves = [m for m in view.legal_moves
                      if m.move_type == "resolve_generic"
                      and "supplant" in m.label.lower()]
    assert supplant_moves, f"No supplant moves, labels: {[m.label for m in view.legal_moves]}"
    session.submit_move(supplant_moves[0].move)

    assert not _has_pending_generic(session), "Expected card to fully resolve after option_1"

    p1_barracks = _sptr(session).contents.players[_session_player_index(session, _P1)].barracks
    assert p1_barracks < 40, "Expected p1 to have deployed a troop (barracks decreased)"
    session.destroy()


def test_green_dragon_option1_supplant_constrained_to_spy_site():
    """After placing a spy at site_A, supplant moves must only target site_A."""
    eng = _make_engine()
    troops = {
        _P1: {
            "site_menzoberranzan": [_P1, _P2, None, None, None, None],
            "site_gauntlgrym": [_P1, _P2, None, None, None, None],
        },
    }
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: ["green_dragon"]},
        troops=troops,
        current_player=_P1,
    )

    playable = [m for m in session.legal_moves()
                if getattr(m, "move_type", "") == "play_card"
                and m.data.get("card_id") == "green_dragon"]
    session.submit_move(playable[0])

    opt1 = [m for m in session.legal_moves()
            if getattr(m, "move_type", "") == "resolve_generic"
            and m.data.get("action_id") == "option_1"]
    session.submit_move(opt1[0])

    view = build_c_game_view(session)
    place_moves = [m for m in view.legal_moves
                   if m.move_type == "resolve_generic"
                   and "Place spy" in m.label]
    menzo_place = [m for m in place_moves if "menzoberranzan" in m.label.lower()]
    assert menzo_place, f"No menzoberranzan place spy move, labels: {[m.label for m in place_moves]}"
    session.submit_move(menzo_place[0].move)

    view = build_c_game_view(session)
    supplant_moves = [m for m in view.legal_moves
                      if m.move_type == "resolve_generic"
                      and "supplant" in m.label.lower()]
    assert supplant_moves, "No supplant moves"

    for m in supplant_moves:
        assert "menzoberranzan" in m.label.lower(), (
            f"Supplant must target menzoberranzan (spy site), got: {m.label}"
        )
        assert "gauntlgrym" not in m.label.lower(), (
            f"Supplant must NOT target gauntlgrym (wrong site), got: {m.label}"
        )

    session.destroy()


def test_green_dragon_option2_site_linking():
    """After returning a spy from site_A, supplant moves only target site_A."""
    eng = _make_engine()
    troops = {
        _P1: {
            "site_menzoberranzan": [_P1, _P2, None, None, None, None],
            "site_gauntlgrym": [_P1, _P2, None, None, None, None],
        },
    }
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: ["green_dragon"]},
        troops=troops,
        spies={
            "site_menzoberranzan": [_P1],
            "site_gauntlgrym": [_P1],
        },
        current_player=_P1,
    )

    playable = [m for m in session.legal_moves()
                if getattr(m, "move_type", "") == "play_card"
                and m.data.get("card_id") == "green_dragon"]
    session.submit_move(playable[0])

    opt2 = [m for m in session.legal_moves()
            if getattr(m, "move_type", "") == "resolve_generic"
            and m.data.get("action_id") == "option_2"]
    assert opt2, "option_2 not available"
    session.submit_move(opt2[0])

    view = build_c_game_view(session)
    return_moves = [m for m in view.legal_moves
                    if m.move_type == "resolve_generic"
                    and "Return spy" in m.label]
    menzo_return = [m for m in return_moves if "menzoberranzan" in m.label.lower()]
    assert menzo_return, f"No Menzoberranzan return spy, labels: {[m.label for m in return_moves]}"
    session.submit_move(menzo_return[0].move)

    view = build_c_game_view(session)
    supplant_moves = [m for m in view.legal_moves
                      if m.move_type == "resolve_generic"
                      and "supplant" in m.label.lower()]
    assert supplant_moves, "No supplant moves"

    for m in supplant_moves:
        assert "menzoberranzan" in m.label.lower(), (
            f"Supplant must target menzoberranzan (returned spy site), got: {m.label}"
        )
        assert "gauntlgrym" not in m.label.lower(), (
            f"Supplant must NOT target gauntlgrym (wrong site), got: {m.label}"
        )

    session.destroy()


def test_green_dragon_option2_return_spy_only_own():
    """Option 2's return_spy must only offer the player's own spies, never enemy spies."""
    eng = _make_engine()
    troops = {
        _P1: {
            "site_menzoberranzan": [_P1, _P2, None, None, None, None],
            "site_gauntlgrym": [_P1, _P2, None, None, None, None],
        },
    }
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: ["green_dragon"]},
        troops=troops,
        spies={
            "site_menzoberranzan": [_P1],
            "site_gauntlgrym": [_P2],
        },
        current_player=_P1,
    )

    playable = [m for m in session.legal_moves()
                if getattr(m, "move_type", "") == "play_card"
                and m.data.get("card_id") == "green_dragon"]
    session.submit_move(playable[0])

    opt2 = [m for m in session.legal_moves()
            if getattr(m, "move_type", "") == "resolve_generic"
            and m.data.get("action_id") == "option_2"]
    assert opt2, "option_2 not available"
    session.submit_move(opt2[0])

    view = build_c_game_view(session)
    rg_moves = [m for m in view.legal_moves if m.move_type == "resolve_generic"]
    assert rg_moves, f"No resolve_generic moves, labels: {[m.label for m in view.legal_moves]}"

    target_ids = {m.move.data.get("action_id") for m in rg_moves}
    assert "site_menzoberranzan" in target_ids, f"Own spy site not offered, targets: {target_ids}"
    assert "site_gauntlgrym" not in target_ids, f"Enemy spy site offered, targets: {target_ids}"

    session.destroy()


def test_green_dragon_option2_not_available_without_spies():
    """option_2 must be marked unavailable when the player has no spies on the board."""
    session = _build_green_dragon_option1_session()

    playable = [m for m in session.legal_moves()
                if getattr(m, "move_type", "") == "play_card"
                and m.data.get("card_id") == "green_dragon"]
    session.submit_move(playable[0])

    option_moves = [m for m in session.legal_moves()
                    if getattr(m, "move_type", "") == "resolve_generic"]
    opts_by_id = {m.data.get("action_id"): m.data for m in option_moves}
    assert "option_1" in opts_by_id, f"option_1 should be available, got: {list(opts_by_id)}"
    assert "option_2" in opts_by_id, "option_2 should be in the list"
    assert opts_by_id["option_2"].get("target_id") == "unavailable", (
        f"option_2 should be unavailable (no spies on board), got: {opts_by_id['option_2']}"
    )

    session.destroy()
