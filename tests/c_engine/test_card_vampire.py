"""Vampire card — comprehensive behavior tests.

Verifies the full pipeline for option_2 ("promote a card from your discard
pile and then gain 1 VP for every 3 promoted cards"):
1. Catalog: execution_model encodes the VP grant as a score award
   (grant_vp with count_from=inner_circle_cards, per=3; no vp_tokens).
2. Engine state: score increments by floor(inner_circle / 3); vp_tokens untouched.
3. View: build_c_game_view projects score and vp_tokens faithfully.
4. Integration: scenario file loaded and played end-to-end.
5. Edge cases: integer-division scaling at boundaries (0..10 cards).
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from engine_c.bindings.ce_api import CEngine
from engine_c.bindings.engine_bindings import MAX_ZONE_SIZE, _lib
from engine_c.bindings.session import CSession
from engine_c.bindings.view import build_c_game_view
from tests.c_engine.card_test_helpers import (
    _player_vp_tokens,
    _session_player_index,
    _sptr,
    make_card_test_session,
)

CARD_ID = "vampire"
_P1 = "p1"

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
SCENARIO_PATH = DATA_DIR / "scenarios" / "batch_card_generation" / "122_seed_4_vampire.json"


# ── helpers ──────────────────────────────────────────────────────────────────

def _set_discard(session: CSession, pid: str, card_ids: list[str]) -> None:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return
    ps = _sptr(session).contents.players[pi]
    ps.discard_pile_count = min(len(card_ids), MAX_ZONE_SIZE)
    for j, cid in enumerate(card_ids[:MAX_ZONE_SIZE]):
        ps.discard_pile[j] = _lib.intern(cid.encode())


def _player_score(session: CSession, pid: str) -> int:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].score


def _inner_circle_count(session: CSession, pid: str) -> int:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].inner_circle_count


def _play_vampire(session: CSession) -> None:
    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == CARD_ID:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"{CARD_ID} not playable")


def _select_option_2(session: CSession) -> None:
    for m in session.legal_moves():
        d = m.data
        if m._move_type == "resolve_generic" and d.get("action_id") == "option_2":
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError("option_2 not in legal moves")


def _submit_first_resolve_generic(session: CSession) -> None:
    for m in session.legal_moves():
        if m._move_type == "resolve_generic":
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError("no resolve_generic move available")


def _build_session(inner_circle_size: int, *, seed: int = 42) -> CSession:
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards" / "catalog.json"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    inner = ["noble"] * inner_circle_size
    session = make_card_test_session(
        eng, [_P1],
        hand={_P1: [CARD_ID]},
        inner_circle={_P1: inner[:MAX_ZONE_SIZE]},
        current_player=_P1,
        seed=seed,
    )
    _set_discard(session, _P1, ["noble"])
    return session


def _play_and_resolve_option_2(session: CSession) -> None:
    _play_vampire(session)
    _select_option_2(session)
    _submit_first_resolve_generic(session)


# ── catalog tests ────────────────────────────────────────────────────────────

def test_catalog_grant_vp_scores_by_inner_circle() -> None:
    """grant_vp in option_2 and flat actions must scale on inner_circle_cards / 3
    and land in score (no 'as': 'vp_tokens' metadata)."""
    catalog = json.loads((DATA_DIR / "cards" / "catalog.json").read_text(encoding="utf-8"))
    cards = catalog if isinstance(catalog, list) else catalog.get("cards", catalog)
    vamp = next(c for c in cards if c.get("card_id") == CARD_ID)

    opt2_acts = vamp["execution_model"]["options"][1]["actions"]
    grant_vp = [a for a in opt2_acts if a["op"] == "grant_vp"]
    assert len(grant_vp) == 1
    meta = grant_vp[0]["metadata"]
    assert meta.get("count_from") == "inner_circle_cards", f"count_from wrong: {meta}"
    assert meta.get("per") == 3, f"per wrong: {meta}"
    assert "as" not in meta, f"Vampire VP must land in score, not vp_tokens: {meta}"

    flat = [a for a in vamp["actions"] if a["op"] == "grant_vp"]
    assert len(flat) == 1
    flat_meta = flat[0]["metadata"]
    assert flat_meta.get("count_from") == "inner_circle_cards", f"flat count_from wrong: {flat_meta}"
    assert flat_meta.get("per") == 3, f"flat per wrong: {flat_meta}"
    assert "as" not in flat_meta, f"flat Vampire VP must land in score, not vp_tokens: {flat_meta}"


# ── engine state: calculation tests ──────────────────────────────────────────

@dataclass(frozen=True)
class _VPExpectation:
    inner_circle_before: int  # cards in inner circle before promoting
    inner_circle_after: int   # after promotion (+1)
    expected_vp: int          # integer division floor(after / 3)


_VP_CASES: tuple[_VPExpectation, ...] = (
    _VPExpectation(0,  1,  0),
    _VPExpectation(1,  2,  0),
    _VPExpectation(2,  3,  1),
    _VPExpectation(3,  4,  1),
    _VPExpectation(4,  5,  1),
    _VPExpectation(5,  6,  2),
    _VPExpectation(6,  7,  2),
    _VPExpectation(7,  8,  2),
    _VPExpectation(8,  9,  3),
    _VPExpectation(9, 10,  3),
)


def test_vp_calculation_boundary_cases() -> None:
    """VP = floor((inner_circle_after_promotion) / 3) added to score."""
    for case in _VP_CASES:
        session = _build_session(case.inner_circle_before)
        assert _inner_circle_count(session, _P1) == case.inner_circle_before
        assert _player_score(session, _P1) == 0

        _play_and_resolve_option_2(session)

        assert _inner_circle_count(session, _P1) == case.inner_circle_after, \
            f"before={case.inner_circle_before}: expected {case.inner_circle_after} inner circle after promote"
        assert _player_score(session, _P1) == case.expected_vp, \
            f"{case.inner_circle_after} inner circle / 3 = {case.expected_vp}, got score={_player_score(session, _P1)}"
        session.destroy()


# ── engine state: score guard ────────────────────────────────────────────────

def test_grant_vp_increments_score_not_vp_tokens() -> None:
    """VP is added to score; vp_tokens must stay at 0."""
    session = _build_session(inner_circle_size=8)
    assert _player_score(session, _P1) == 0
    assert _player_vp_tokens(session, _P1) == 0

    _play_and_resolve_option_2(session)

    assert _player_score(session, _P1) == 3, \
        f"Expected score=3 (9/3 after promote), got score={_player_score(session, _P1)}"
    assert _player_vp_tokens(session, _P1) == 0, \
        f"vp_tokens must stay 0; VP awarded to score. Got vp_tokens={_player_vp_tokens(session, _P1)}"
    session.destroy()


# ── view projection tests ────────────────────────────────────────────────────

def test_view_projection_shows_score() -> None:
    """build_c_game_view must project the VP award into score, not vp_tokens."""
    session = _build_session(inner_circle_size=4)
    _play_and_resolve_option_2(session)

    view = build_c_game_view(session)
    for ps in view.player_summaries:
        if ps.player_id == _P1:
            assert ps.score == 1, \
                f"View should show score=1 (5/3=1 after promote), got {ps.score}"
            assert ps.vp_tokens == 0, \
                f"View vp_tokens should be 0, got {ps.vp_tokens}"
            break
    else:
        raise AssertionError(f"Player {_P1} not found in view player_summaries")
    session.destroy()


def test_view_projection_zero_vp() -> None:
    """View shows score=0 when 1 inner circle card (1/3=0)."""
    session = _build_session(inner_circle_size=0)
    _play_and_resolve_option_2(session)

    view = build_c_game_view(session)
    for ps in view.player_summaries:
        if ps.player_id == _P1:
            assert ps.score == 0, \
                f"View should show score=0 (1/3=0), got {ps.score}"
            break
    session.destroy()


def test_view_before_and_after_consistent() -> None:
    """View built before and after card play must be consistent with engine state."""
    session = _build_session(inner_circle_size=4)

    view_before = build_c_game_view(session)
    score_before = next(ps.score for ps in view_before.player_summaries if ps.player_id == _P1)
    assert score_before == 0

    _play_and_resolve_option_2(session)

    view_after = build_c_game_view(session)
    score_after = next(ps.score for ps in view_after.player_summaries if ps.player_id == _P1)
    assert score_after == 1, f"View score should be 1 after play (4+1=5/3=1), got {score_after}"

    actual_score = _player_score(session, _P1)
    assert score_after == actual_score, \
        f"View score ({score_after}) must match engine state ({actual_score})"
    session.destroy()


# ── integration: scenario file ───────────────────────────────────────────────

def test_scenario_file_loads_and_plays_end_to_end() -> None:
    """Load 122_seed_4_vampire.json and verify VP is added to score in engine state."""
    raw = SCENARIO_PATH.read_text(encoding="utf-8")
    scenario = json.loads(raw)
    sc = scenario.get("definition", {})

    eng = CEngine()
    eng.initialize(
        catalog_path=sc.get("catalog_path", str(DATA_DIR / "cards" / "catalog.json")),
        board_path=sc.get("board_path", str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json")),
        setup_path=sc.get("setup_path", str(DATA_DIR / "decks" / "base_setup.json")),
    )
    session = CSession.load(str(SCENARIO_PATH), eng)

    current = _lib.intern_str(_sptr(session).contents.current_player_id).decode()
    assert "vampire" in [m.data.get("card_id", "") for m in session.legal_moves()
                         if m._move_type == "play_card"], \
        f"Vampire not in hand of {current}"

    _play_vampire(session)

    option_moves = [m for m in session.legal_moves() if m._move_type == "resolve_generic"]
    assert any(m.data.get("action_id") == "option_2" for m in option_moves), \
        "option_2 should be available"

    _select_option_2(session)

    promote_moves = [m for m in session.legal_moves() if m._move_type == "resolve_generic"]
    assert promote_moves, "No promote target moves after selecting option_2"
    _submit_first_resolve_generic(session)

    ic = _inner_circle_count(session, current)
    score = _player_score(session, current)
    vp_tokens = _player_vp_tokens(session, current)

    expected = ic // 3
    assert score == expected, (
        f"{ic} inner circle cards / 3 = {expected}, but got score={score}"
    )
    assert vp_tokens == 0, (
        f"VP goes to score, not vp_tokens; got vp_tokens={vp_tokens}"
    )

    session.destroy()
