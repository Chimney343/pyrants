"""Elder Brain card behavior tests."""

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
    / "data" / "scenarios" / "batch_card_generation" / "009_seed_4_elder_brain.json"
)


def _inner_circle_ids(session: CSession, player_id: str) -> list[str]:
    s = session._state._ptr.contents
    for i in range(s.player_count):
        pid = _lib.intern_str(s.player_ids[i]).decode()
        if pid == player_id:
            ps = s.players[i]
            return [
                _lib.intern_str(ps.inner_circle[j]).decode()
                for j in range(ps.inner_circle_count)
            ]
    return []


def test_elder_brain_promotes_top_deck() -> None:
    """Elder Brain promotes the top card of deck to inner circle."""
    session = CSession.load(str(SCENARIO_PATH))
    ic_before = _inner_circle_ids(session, "p2")

    for m in session.legal_moves():
        if getattr(m, "move_type", "") == "play_card" and m.data.get("card_id") == "elder_brain":
            session.submit_move(m)
            break
    else:
        session.destroy()
        pytest.fail("Elder Brain not in hand")

    # Promote is auto-resolved; inner circle should grow by 1
    ic_after = _inner_circle_ids(session, "p2")
    assert len(ic_after) == len(ic_before) + 1, (
        f"Inner circle should grow by 1: {len(ic_before)} -> {len(ic_after)}"
    )
    assert ic_after[0] == "noble", (
        f"Top deck card should be noble, got {ic_after[0]}"
    )

    session.destroy()


def test_elder_brain_inner_circle_card_is_playable() -> None:
    """After promotion, inner circle cards appear as selectable targets for nested play."""
    session = CSession.load(str(SCENARIO_PATH))

    for m in session.legal_moves():
        if getattr(m, "move_type", "") == "play_card" and m.data.get("card_id") == "elder_brain":
            session.submit_move(m)
            break

    view = build_c_game_view(session)
    play_moves = [m for m in view.legal_moves if m.move_type == "resolve_generic"]
    assert play_moves, "No inner circle card selection moves generated"

    action_ids = {m.move.data["action_id"] for m in play_moves}
    assert "noble" in action_ids, (
        f"noble should be selectable from inner circle, got targets: {action_ids}"
    )

    noble_move = next(m for m in play_moves if m.move.data["action_id"] == "noble")
    session.submit_move(noble_move.move)

    ic_after = _inner_circle_ids(session, "p2")
    assert "noble" in ic_after, (
        "noble must remain in inner circle after nested play"
    )

    s = session._state._ptr.contents
    assert not s.pending_generic, (
        "Elder Brain should fully resolve after nested card is played"
    )

    session.destroy()
