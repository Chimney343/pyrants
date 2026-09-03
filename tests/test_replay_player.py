"""Tests for ``interface.replay_player`` — headless C-engine re-simulation.

Guarded by the presence of ``artifacts/ismcts/game_0000`` so the suite still
passes after ``artifacts/`` is pruned. The full-replay regression test here is
the guard that would have caught the engine-seed-mixer trap.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interface.replay_loader import load_replay
from interface.replay_player import ReplayDesyncError, ReplayPlayer

ROOT = Path(__file__).resolve().parents[1]
GAME_DIR = ROOT / "artifacts" / "ismcts" / "game_0000"
FOUR_PLAYER_DIR = (
    ROOT
    / "artifacts"
    / "ismcts"
    / "experiments"
    / "sims_vs_wins"
    / "20260902T215139Z_65cdce971bcf"
    / "game_0000"
)

pytestmark = pytest.mark.skipif(
    not GAME_DIR.exists(), reason="C engine replay artifacts not present"
)


def _capture(player: ReplayPlayer) -> tuple:
    state = player.session.state
    return (
        state.round_number,
        state.phase,
        state.current_player_id,
        tuple(state.player_score(state.player_index(pid)) for pid in state.turn_order),
    )


def test_full_replay_is_deterministic() -> None:
    bundle = load_replay(GAME_DIR)
    player = ReplayPlayer(bundle)

    while player.step_forward():
        pass

    assert player.index == 517
    assert player.is_terminal
    assert player.session.final_scores() == {"p1": 64, "p2": 93}
    assert player.session.winner_id() == "p2"


def test_total_steps_excludes_terminal_sentinel() -> None:
    bundle = load_replay(GAME_DIR)
    player = ReplayPlayer(bundle)

    assert player.total_steps == 517
    assert player.entry_at(player.total_steps) is None
    assert player.entry_at(516) is not None


def test_seek_round_trips() -> None:
    bundle = load_replay(GAME_DIR)
    player = ReplayPlayer(bundle)

    player.seek(300)
    snap1 = _capture(player)
    assert player.index == 300

    player.seek(50)
    player.seek(300)

    assert _capture(player) == snap1


def test_seek_clamps_to_bounds() -> None:
    bundle = load_replay(GAME_DIR)
    player = ReplayPlayer(bundle)

    player.seek(-5)
    assert player.index == 0

    player.seek(10_000)
    assert player.index == player.total_steps


def test_step_back() -> None:
    bundle = load_replay(GAME_DIR)
    player = ReplayPlayer(bundle)

    player.seek(10)
    player.step_back()

    assert player.index == 9
    back_state = _capture(player)

    other = ReplayPlayer(load_replay(GAME_DIR))
    other.seek(9)
    assert _capture(other) == back_state


def test_step_forward_returns_false_at_end() -> None:
    bundle = load_replay(GAME_DIR)
    player = ReplayPlayer(bundle)

    player.seek(player.total_steps)
    assert not player.step_forward()


def test_desync_raises_and_session_stays_usable() -> None:
    bundle = load_replay(GAME_DIR)
    original = bundle.replay["replay_log"][5]["payload"]
    bundle.replay["replay_log"][5]["payload"] = {"move_type": "not_a_real_move"}

    player = ReplayPlayer(bundle)
    player.seek(5)

    with pytest.raises(ReplayDesyncError) as exc:
        player.step_forward()

    assert exc.value.step_index == 5
    assert exc.value.expected == {"move_type": "not_a_real_move"}
    assert isinstance(exc.value.legal, list) and exc.value.legal

    assert player.index == 5  # left at last good state

    # Session remains usable once the log is trustworthy again.
    bundle.replay["replay_log"][5]["payload"] = original
    player.seek(5)
    while player.step_forward():
        pass
    assert player.is_terminal


def test_decision_at_matches_step() -> None:
    bundle = load_replay(GAME_DIR)
    player = ReplayPlayer(bundle)

    decision = player.decision_at(0)
    entry = player.entry_at(0)

    assert decision["node"] == 0
    assert decision["chosen_move"] == entry["label"]
    assert decision["sims_requested"] >= 1
    assert player.next_entry()["step_index"] == 0


def test_four_player_replay() -> None:
    if not FOUR_PLAYER_DIR.exists():
        pytest.skip("4-player experiment replay absent")
    bundle = load_replay(FOUR_PLAYER_DIR)
    player = ReplayPlayer(bundle)

    while player.step_forward():
        pass

    assert player.index == bundle.replay["step_count"]
    assert player.is_terminal
    assert player.session.final_scores() == bundle.replay["final_scores"]
    assert player.session.winner_id() == bundle.replay["winner_id"]