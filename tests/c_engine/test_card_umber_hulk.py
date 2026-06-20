"""Umber Hulk card behavior tests."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from engine_c.bindings.engine_bindings import _lib
from engine_c.bindings.session import CSession
from engine_c.bindings.view import build_c_game_view

SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data" / "scenarios" / "batch_card_generation" / "020_seed_4_umber_hulk.json"
)


def _player_state(session: CSession, player_id: str):
    s = session._state._ptr.contents
    for i in range(s.player_count):
        pid = _lib.intern_str(s.player_ids[i]).decode()
        if pid == player_id:
            ps = s.players[i]
            return {"barracks": ps.barracks, "hand_count": ps.hand_count}
    return None


def _play_card_and_deploy(session: CSession) -> None:
    """Play Umber Hulk and resolve all deploy choices (3 troops)."""
    for m in session.legal_moves():
        if getattr(m, "move_type", "") == "play_card" and m.data.get("card_id") == "umber_hulk":
            session.submit_move(m)
            break
    else:
        pytest.fail("Umber Hulk not in hand")

    # Deploy 3 troops — each resolve_generic deploys one troop
    deployments = 0
    while deployments < 3:
        view = build_c_game_view(session)
        resolve_moves = [m for m in view.legal_moves if m.move_type == "resolve_generic"]
        if not resolve_moves:
            break
        session.submit_move(resolve_moves[0].move)
        deployments += 1


def test_umber_hulk_deploys_three_troops() -> None:
    """Playing Umber Hulk deploys 3 troops and resolves cleanly."""
    session = CSession.load(str(SCENARIO_PATH))
    before = _player_state(session, "p2")

    _play_card_and_deploy(session)

    after = _player_state(session, "p2")
    assert before["barracks"] == after["barracks"] + 3, (
        f"Barracks should decrease by 3: {before['barracks']} -> {after['barracks']}"
    )

    s = session._state._ptr.contents
    assert not s.pending_generic, (
        "Card must resolve cleanly — conditional force_discard should be skipped"
    )

    session.destroy()


def test_umber_hulk_no_force_discard_after_full_resolution() -> None:
    """After resolving all 3 deploys, card finishes without pending state."""
    session = CSession.load(str(SCENARIO_PATH))

    _play_card_and_deploy(session)

    s = session._state._ptr.contents
    assert not s.pending_generic, (
        "After 3 deploys, card must fully resolve — no pending generic state"
    )

    session.destroy()
