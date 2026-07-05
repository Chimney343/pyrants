"""Vampire Spawn card behavior tests.

Verifies:
- Playing Vampire Spawn grants 1 influence.
- The return_unit action targets only opponent troops and spies (not own).
- Returning an opponent troop increments that opponent's barracks.
- Returning an opponent spy increments that opponent's spies_available.
- The card resolves cleanly when no opponent units are on the board.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from engine_c.bindings.ce_api import CEngine
from engine_c.bindings.engine_bindings import _lib
from engine_c.bindings.session import CSession
from tests.c_engine.card_test_helpers import make_card_test_session

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

CARD_ID = "vampire_spawn"
_P1 = "p1"
_P2 = "p2"
_P3 = "p3"
_SITE = "site_gauntlgrym"


def _play_card(session: CSession, card_id: str = CARD_ID) -> None:
    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == card_id:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"{card_id} not in hand")


def _influence(session: CSession) -> int:
    return session._state._ptr.contents.resource_pool.influence


def _resolve_move_for_target(legal_moves, node_id, target_id):
    for m in legal_moves:
        d = m.data
        if m._move_type == "resolve_generic" and d.get("action_id") == node_id and d.get("target_id") == target_id:
            return m
    return None


def _barracks(session: CSession, pid: str) -> int:
    s = session._state._ptr.contents
    name_bytes = pid.encode()
    for i in range(s.player_count):
        pname = _lib.intern_str(s.player_ids[i])
        if pname and pname == name_bytes:
            return s.players[i].barracks
    return -1


def _spies_available(session: CSession, pid: str) -> int:
    s = session._state._ptr.contents
    name_bytes = pid.encode()
    for i in range(s.player_count):
        pname = _lib.intern_str(s.player_ids[i])
        if pname and pname == name_bytes:
            return s.players[i].spies_available
    return -1


def _has_pending_generic(session: CSession) -> bool:
    return bool(session._state._ptr.contents.pending_generic)


# ── Tests ──────────────────────────────────────────────────────────────────


def test_vampire_spawn_gains_influence() -> None:
    """Playing Vampire Spawn grants 1 influence."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards" / "catalog.json"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [CARD_ID]},
        troops={_P2: {_SITE: [_P2, None]}},
        current_player=_P1,
    )

    inf_before = _influence(session)
    _play_card(session)

    assert _influence(session) == inf_before + 1, (
        f"Expected {inf_before + 1} influence, got {_influence(session)}"
    )

    session.destroy()


def test_vampire_spawn_return_opponent_troop_increments_barracks() -> None:
    """Returning an opponent troop increments that opponent's barracks by 1."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards" / "catalog.json"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [CARD_ID]},
        troops={_P2: {_SITE: [_P2, None]}},
        current_player=_P1,
    )

    barracks_before = _barracks(session, _P2)
    _play_card(session)

    assert _has_pending_generic(session), "Expected pending generic choice after playing Vampire Spawn"

    move = _resolve_move_for_target(session.legal_moves(), _SITE, "troop:0")
    assert move is not None, f"troop:0 at {_SITE} should be selectable as opponent troop"
    session.submit_move(move)

    assert not _has_pending_generic(session), "Should have no pending generic choices after resolution"
    assert _barracks(session, _P2) == barracks_before + 1, (
        f"Opponent barracks should increase: {barracks_before} -> {_barracks(session, _P2)}"
    )

    session.destroy()


def test_vampire_spawn_return_opponent_spy_increments_spies_available() -> None:
    """Returning an opponent spy increments that opponent's spies_available by 1."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards" / "catalog.json"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [CARD_ID]},
        spies={_SITE: [_P2]},
        current_player=_P1,
    )

    spies_before = _spies_available(session, _P2)
    _play_card(session)

    assert _has_pending_generic(session), "Expected pending generic choice after playing Vampire Spawn"

    move = _resolve_move_for_target(session.legal_moves(), _SITE, f"spy:{_P2}")
    assert move is not None, f"spy:{_P2} at {_SITE} should be selectable as opponent spy"
    session.submit_move(move)

    assert not _has_pending_generic(session), "Should have no pending generic choices after resolution"
    assert _spies_available(session, _P2) == spies_before + 1, (
        f"Opponent spies_available should increase: {spies_before} -> {_spies_available(session, _P2)}"
    )

    session.destroy()


def test_vampire_spawn_only_targets_opponent_units() -> None:
    """return_unit with opponent_unit scope must only target opponent units, never own."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards" / "catalog.json"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [CARD_ID]},
        troops={
            _P1: {_SITE: [_P1, None]},
            _P2: {_SITE: [_P2, None]},
        },
        spies={_SITE: [_P1, _P2]},
        current_player=_P1,
    )

    _play_card(session)

    targets = [
        (m.data["action_id"], m.data["target_id"])
        for m in session.legal_moves()
        if m._move_type == "resolve_generic" and m.data.get("target_id") is not None
    ]

    for (_action_id, target_id) in targets:
        assert _P1 not in (target_id or ""), f"Own unit should not be targetable: {target_id}"

    p2_targets = [(a, t) for (a, t) in targets if _P2 in (t or "")]
    assert len(p2_targets) >= 1, f"Expected at least one opponent target, got {targets}"

    session.destroy()


def test_vampire_spawn_no_opponent_units_resolves() -> None:
    """With no opponent units on the board, the card should still resolve cleanly and grant influence."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards" / "catalog.json"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [CARD_ID]},
        current_player=_P1,
    )

    inf_before = _influence(session)
    _play_card(session)

    assert _influence(session) == inf_before + 1, (
        f"Expected influence gain even with no return target, got {_influence(session)}"
    )

    session.destroy()
