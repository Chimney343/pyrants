"""Empty-barracks deploy → "Gain 1 VP token" behaviour.

Rulebook 319/589: taking the Deploy action (paid or card-driven) while the
barracks are empty grants 1 VP token instead of placing a troop. The VP grant
scales with the number of deploys requested, and is carried as ``vp_tokens``
(not ``score``) on every path.
"""

from __future__ import annotations

import ctypes

from engine_c.bindings.engine_bindings import PHASE_MAIN, _lib
from engine_c.bindings.view import build_c_game_view
from tests.c_engine.card_test_helpers import (
    _make_engine,
    _player_vp_tokens,
    _session_player_index,
    _sptr,
    make_card_test_session,
)

_P1 = "p1"
_P2 = "p2"
_SITE = "site_gauntlgrym"
_VP_LABEL = "Barracks empty; gain 1 VP token instead of deploying a troop"


def _player_score(session, pid: str) -> int:
    pi = _session_player_index(session, pid)
    return _sptr(session).contents.players[pi].score if pi >= 0 else 0


def _player_power(session) -> int:
    return _sptr(session).contents.resource_pool.power


def _player_barracks(session, pid: str) -> int:
    pi = _session_player_index(session, pid)
    return _sptr(session).contents.players[pi].barracks if pi >= 0 else 0


def _set_barracks(session, pid: str, value: int) -> None:
    pi = _session_player_index(session, pid)
    _sptr(session).contents.players[pi].barracks = value


def _set_power(session, value: int) -> None:
    _sptr(session).contents.resource_pool.power = value


def _has_pending_generic(session) -> bool:
    return bool(_sptr(session).contents.pending_generic)


def _build_session(card: str, *, spies=None, troops=None):
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [card]},
        spies=spies,
        troops=troops,
        current_player=_P1,
    )
    s = _sptr(session).contents
    s.phase = PHASE_MAIN
    return session


def _play_card(session, card_id: str) -> None:
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == card_id:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"{card_id} not playable")


def _resolve_generic_moves(session):
    return [m for m in session.legal_moves() if m.move_type == "resolve_generic"]


def _sentinel_moves(session):
    return [m for m in _resolve_generic_moves(session) if m.data.get("action_id") is None]


def _pick_option(session, option_id: str) -> None:
    for m in _resolve_generic_moves(session):
        if m.data.get("action_id") == option_id:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"{option_id} not found in resolve_generic moves")


# ---------------------------------------------------------------------------
# Paid 1-Power Deploy action
# ---------------------------------------------------------------------------


def test_paid_deploy_empty_barracks_grants_vp_token() -> None:
    """Paid Deploy with empty barracks emits one sentinel move; applying it
    spends 1 Power and grants +1 vp_tokens (not score)."""
    eng = _make_engine()
    session = make_card_test_session(eng, [_P1, _P2], current_player=_P1)
    s = _sptr(session).contents
    s.phase = PHASE_MAIN
    _set_barracks(session, _P1, 0)
    _set_power(session, 1)

    deploy_moves = [m for m in session.legal_moves() if m.move_type == "deploy"]
    assert len(deploy_moves) == 1, f"Expected 1 deploy move, got {[m.data for m in deploy_moves]}"
    assert deploy_moves[0].data.get("target_node_id") is None, (
        "Empty-barracks deploy must not name a target node"
    )

    view = build_c_game_view(session)
    deploy_labels = [m.label for m in view.legal_moves if m.move_type == "deploy"]
    assert _VP_LABEL in deploy_labels, f"Expected VP label, got {deploy_labels}"

    vp_before = _player_vp_tokens(session, _P1)
    score_before = _player_score(session, _P1)

    session.submit_move(deploy_moves[0])

    assert _player_power(session) == 0, "Power should be spent to take the action"
    assert _player_vp_tokens(session, _P1) == vp_before + 1, (
        f"Expected +1 vp_tokens, got {_player_vp_tokens(session, _P1) - vp_before}"
    )
    assert _player_score(session, _P1) == score_before, "VP is a token, not score"

    session.destroy()


# ---------------------------------------------------------------------------
# Card-driven deploy (free)
# ---------------------------------------------------------------------------


def test_kobold_option_1_selectable_and_grants_vp_with_empty_barracks() -> None:
    """Kobold option_1 (deploy 1) stays selectable with empty barracks and
    grants +1 vp_tokens instead of stalling."""
    session = _build_session("kobold")
    _set_barracks(session, _P1, 0)

    _play_card(session, "kobold")
    assert _has_pending_generic(session)

    option_1 = [m for m in _resolve_generic_moves(session) if m.data.get("action_id") == "option_1"]
    assert option_1, "option_1 should be listed"
    assert option_1[0].data.get("target_id") != "unavailable", "option_1 should be selectable"

    session.submit_move(option_1[0])

    vp_before = _player_vp_tokens(session, _P1)

    sentinels = _sentinel_moves(session)
    assert len(sentinels) == 1, (
        f"Expected 1 VP sentinel move, got {[m.data for m in _resolve_generic_moves(session)]}"
    )

    view = build_c_game_view(session)
    sentinel_labels = [m.label for m in view.legal_moves if _VP_LABEL in m.label]
    assert sentinel_labels, "Sentinel deploy move must carry the VP label in the GUI"

    session.submit_move(sentinels[0])

    assert not _has_pending_generic(session), "Kobold should fully resolve"
    assert _player_vp_tokens(session, _P1) == vp_before + 1
    assert _player_barracks(session, _P1) == 0

    session.destroy()


def test_air_elemental_option_2_three_deploys_grant_three_vp() -> None:
    """Air Elemental option_2 (three qty-1 deploys) grants +3 vp_tokens total."""
    session = _build_session(
        "air_elemental",
        spies={_SITE: [_P1]},
        troops={_P1: {_SITE: [None, None, None]}},
    )
    _set_barracks(session, _P1, 0)

    _play_card(session, "air_elemental")
    _pick_option(session, "option_2")

    return_moves = [m for m in _resolve_generic_moves(session) if m.data.get("action_id") == _SITE]
    assert return_moves, "return_spy move expected"
    session.submit_move(return_moves[0])

    vp_before = _player_vp_tokens(session, _P1)

    deploys = 0
    while True:
        sentinels = _sentinel_moves(session)
        if not sentinels:
            break
        session.submit_move(sentinels[0])
        deploys += 1
        assert deploys <= 3, "Option 2 should deploy at most 3 times"

    assert deploys == 3, f"Expected 3 deploy selections, got {deploys}"
    assert not _has_pending_generic(session)
    assert _player_vp_tokens(session, _P1) == vp_before + 3, (
        f"Expected +3 vp_tokens, got {_player_vp_tokens(session, _P1) - vp_before}"
    )

    session.destroy()


def test_ettin_option_1_single_qty3_deploy_grants_three_vp() -> None:
    """Ettin option_1 (one qty-3 deploy) grants +3 vp_tokens total.

    This guards quantity scaling: a flat +1 would under-award Ettin by 2.
    """
    session = _build_session("ettin")
    _set_barracks(session, _P1, 0)

    _play_card(session, "ettin")
    option_1 = [m for m in _resolve_generic_moves(session) if m.data.get("action_id") == "option_1"]
    assert option_1, "option_1 should be listed"
    assert option_1[0].data.get("target_id") != "unavailable", "option_1 should be selectable"
    session.submit_move(option_1[0])

    vp_before = _player_vp_tokens(session, _P1)

    deploys = 0
    while True:
        sentinels = _sentinel_moves(session)
        if not sentinels:
            break
        session.submit_move(sentinels[0])
        deploys += 1
        assert deploys <= 3, "Option 1 should deploy at most 3 times"

    assert deploys == 3, f"Expected 3 deploy selections, got {deploys}"
    assert not _has_pending_generic(session)
    assert _player_vp_tokens(session, _P1) == vp_before + 3, (
        f"Expected +3 vp_tokens (qty 3), got {_player_vp_tokens(session, _P1) - vp_before}"
    )

    session.destroy()


# ---------------------------------------------------------------------------
# Regression guards
# ---------------------------------------------------------------------------


def test_nonempty_barracks_deploys_normally() -> None:
    """With troops in barracks, deploy still offers per-node targets (no sentinel)."""
    session = _build_session("kobold")

    _play_card(session, "kobold")
    _pick_option(session, "option_1")

    deploy_moves = [
        m for m in _resolve_generic_moves(session)
        if m.data.get("action_id") is not None and m.data.get("target_id") is None
    ]
    assert deploy_moves, "Deploy should present site targets with troops available"

    sentinels = _sentinel_moves(session)
    assert not sentinels, "No VP sentinel move when barracks are non-empty"

    session.destroy()


def test_final_score_counts_vp_tokens_equivalently_to_score() -> None:
    """N vp_tokens raise the final score by exactly N, same as N added to score."""
    session = _build_session("kobold")
    pi = _session_player_index(session, _P1)
    s = _sptr(session).contents
    scores = (ctypes.c_int * 4)()

    _lib.compute_final_scores(_sptr(session), scores)
    baseline = scores[pi]

    s.players[pi].vp_tokens = 5
    _lib.compute_final_scores(_sptr(session), scores)
    token_score = scores[pi]
    assert token_score == baseline + 5, f"vp_tokens should add 5: {baseline} -> {token_score}"

    s.players[pi].vp_tokens = 0
    s.players[pi].score += 5
    _lib.compute_final_scores(_sptr(session), scores)
    score_score = scores[pi]
    assert score_score == token_score, (
        f"score += 5 and vp_tokens += 5 must score identically: {score_score} vs {token_score}"
    )

    session.destroy()
