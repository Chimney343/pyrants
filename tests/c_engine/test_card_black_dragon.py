"""Black Dragon card behavior tests: VP tokens via grant_vp with as:vp_tokens."""

from __future__ import annotations

from pathlib import Path

from engine_c.bindings.engine_bindings import _lib
from engine_c.bindings.session import CSession
from engine_c.bindings.view import build_c_game_view
from tests.c_engine.card_test_helpers import (
    _make_engine,
    _player_vp_tokens,
    _session_player_index,
    _sptr,
    make_card_test_session,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _player_score(session: CSession, pid: str) -> int:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].score


def _has_pending_generic(session: CSession) -> bool:
    return bool(_sptr(session).contents.pending_generic)


_P1 = "p1"
_P2 = "p2"


def _build_black_dragon_session(white_trophy_count: int = 3) -> CSession:
    """Session with Black Dragon in hand and white troops to supplant."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: ["black_dragon"]},
        troops={
            _P2: {
                "site_gauntlgrym": [_P2, None, None, None],
            }
        },
        current_player=_P1,
    )
    s = _sptr(session).contents
    pi = _session_player_index(session, _P1)
    ps = s.players[pi]
    for i in range(white_trophy_count):
        if ps.trophy_hall_count < 50:
            ps.trophy_hall[ps.trophy_hall_count] = _lib.intern(b"white")
            ps.trophy_hall_count += 1
    return session


def test_black_dragon_vp_awarded_as_tokens():
    """grant_vp with as:vp_tokens should write to vp_tokens, not score."""
    session = _build_black_dragon_session(white_trophy_count=5)

    before_tokens = _player_vp_tokens(session, _P1)
    before_score = _player_score(session, _P1)

    playable = [m for m in session.legal_moves()
                if getattr(m, "move_type", "") == "play_card"
                and m.data.get("card_id") == "black_dragon"]
    assert playable, "Black Dragon not playable"
    session.submit_move(playable[0])

    assert _has_pending_generic(session)

    view = build_c_game_view(session)
    supplant_moves = [m for m in view.legal_moves
                      if m.move_type == "resolve_generic"
                      and "supplant" in m.label.lower()]
    assert supplant_moves, f"No supplant moves, labels={[m.label for m in view.legal_moves]}"
    session.submit_move(supplant_moves[0].move)

    assert not _has_pending_generic(session)

    end_main = [m for m in session.legal_moves()
                if getattr(m, "move_type", "") == "end_main_phase"]
    assert end_main, "No end_main_phase move"
    session.submit_move(end_main[0])

    resolve_eot = [m for m in session.legal_moves()
                   if getattr(m, "move_type", "") == "resolve_end_of_turn"]
    assert resolve_eot, "No resolve_end_of_turn move"
    session.submit_move(resolve_eot[0])

    tokens_after = _player_vp_tokens(session, _P1)
    score_after = _player_score(session, _P1)

    expected_vp = 6 // 3  # 5 pre-existing + 1 supplanted white = 6
    assert tokens_after == before_tokens + expected_vp, (
        f"Expected {expected_vp} VP tokens (6 white trophies // 3), "
        f"got vp_tokens={tokens_after} (was {before_tokens})"
    )
    assert score_after == before_score, (
        f"Score should not change (VP goes to tokens), was {before_score}, now {score_after}"
    )

    session.destroy()


def test_black_dragon_zero_trophies_gives_zero_vp():
    """Zero white trophies should award zero VP tokens."""
    session = _build_black_dragon_session(white_trophy_count=0)

    before_tokens = _player_vp_tokens(session, _P1)

    playable = [m for m in session.legal_moves()
                if getattr(m, "move_type", "") == "play_card"
                and m.data.get("card_id") == "black_dragon"]
    assert playable, "Black Dragon not playable"
    session.submit_move(playable[0])

    view = build_c_game_view(session)
    supplant_moves = [m for m in view.legal_moves
                      if m.move_type == "resolve_generic"
                      and "supplant" in m.label.lower()]
    assert supplant_moves, f"No supplant moves, labels={[m.label for m in view.legal_moves]}"
    session.submit_move(supplant_moves[0].move)

    end_main = [m for m in session.legal_moves()
                if getattr(m, "move_type", "") == "end_main_phase"]
    session.submit_move(end_main[0])

    resolve_eot = [m for m in session.legal_moves()
                   if getattr(m, "move_type", "") == "resolve_end_of_turn"]
    session.submit_move(resolve_eot[0])

    assert _player_vp_tokens(session, _P1) == before_tokens, (
        "Expected zero VP tokens when no white trophies"
    )

    session.destroy()


def test_c_game_view_control_vp_fields():
    """CGameView should populate current_player_control_vp and total_control_vp."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        troops={
            _P1: {
                "site_gauntlgrym": [_P1, None, None, None],
                "site_jhachalkhyn": [_P1, None, None, None],
            }
        },
        current_player=_P1,
    )

    view = build_c_game_view(session)
    assert hasattr(view, "current_player_control_vp"), "CGameViewData missing current_player_control_vp"
    assert hasattr(view, "current_player_total_control_vp"), "CGameViewData missing current_player_total_control_vp"

    assert view.current_player_controlled_sites >= 1, (
        f"Expected p1 to control at least one site, got {view.current_player_controlled_sites}"
    )
    assert view.current_player_control_vp > 0, (
        f"Expected positive control_vp, got {view.current_player_control_vp}"
    )

    session.destroy()
