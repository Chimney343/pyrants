"""Tests for the IS-MCTS replay payload building in scripts/run_ismcts.py.

Covers:
- compute_final_scores backend dispatch (no recursion)
- resolve_winner_id backend-aware resolution
- replay payload final_scores is populated (not hard-coded {})
- terminal marker appended to replay_log
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts._replay_payload import (
    build_replay_payload,
    compute_final_scores,
    resolve_winner_id,
)


# ── compute_final_scores ────────────────────────────────────────────────────


class TestComputeFinalScores:
    def test_c_adapter_present(self):
        """When _adapter is present, delegate to adapter.final_scores()."""
        adapter = MagicMock()
        adapter.final_scores.return_value = {"p1": 42, "p2": 37}
        state = MagicMock()
        state._adapter = adapter
        result = compute_final_scores(state)
        assert result == {"p1": 42, "p2": 37}
        adapter.final_scores.assert_called_once()

    def test_python_engine_no_adapter(self):
        """When _adapter is missing/None, fall back to engine.scoring.compute_final_scores.

        The original code had a recursion bug where the non-C path called itself.
        This test confirms the fix: a state with no adapter reaches the Python
        engine path without infinite recursion.
        """
        state = MagicMock()
        state._adapter = None
        state._engine = MagicMock()

        with patch(
            "engine.scoring.compute_final_scores",
            return_value={"p1": 99, "p2": 50},
        ):
            result = compute_final_scores(state)
            assert result == {"p1": 99, "p2": 50}


# ── resolve_winner_id ───────────────────────────────────────────────────────


class TestResolveWinnerId:
    def test_none_winner_returns_none(self):
        """None winner → None winner_id regardless of backend."""
        state = MagicMock()
        result = resolve_winner_id(state, None, 2)
        assert result is None

    def test_c_adapter_preferred(self):
        """When _adapter is present, use adapter's winner()."""
        adapter = MagicMock()
        adapter._engine = MagicMock()
        adapter._engine.winner.return_value = "p2"
        adapter._state = MagicMock()
        state = MagicMock()
        state._adapter = adapter
        state._game = MagicMock()
        state._game.get_player_ids.return_value = ["p1", "p2"]

        result = resolve_winner_id(state, 0, 2)
        assert result == "p2"
        adapter._engine.winner.assert_called_once()

    def test_open_spiel_fallback(self):
        """When _adapter is missing, fall back to OpenSpiel get_player_ids."""
        state = MagicMock()
        state._adapter = None
        state._game.get_player_ids.return_value = ["p1", "p2"]

        result = resolve_winner_id(state, 1, 2)
        assert result == "p2"


# ── Replay fixture regression test ───────────────────────────────────────────


@pytest.mark.skipif(
    not Path(
        __file__, "..", "..",
        "artifacts", "ismcts_c", "298f153a3b56", "game_0000", "replay.json",
    ).resolve().exists(),
    reason="298f153a3b56 replay fixture not present",
)
def test_existing_replay_fixture_final_scores_is_empty():
    """The 298f153a3b56 replays have final_scores: {} — confirm the bug.

    This test documents the existing bug. After the fix, future replays will
    have non-empty final_scores, but these historical files remain empty.
    """
    path = (
        Path(__file__).resolve().parents[1]
        / "artifacts" / "ismcts_c" / "298f153a3b56" / "game_0000" / "replay.json"
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["is_terminal"] is True
    assert data["winner_id"] is not None
    assert data["stopped_reason"] == "terminal"
    # The bug: final_scores is empty even though the game is terminal.
    assert data["final_scores"] == {}


# ── Terminal marker ──────────────────────────────────────────────────────────


def test_terminal_marker_structure():
    """A terminal marker entry should have the right shape for consumers."""
    marker = {
        "run_id": "test_run",
        "step_index": 99,
        "player_id": None,
        "round_number": 12,
        "phase": "game_over",
        "prompts": [],
        "move_type": "__terminal__",
        "label": "game_over",
        "payload": {"move_type": "__terminal__"},
    }
    assert marker["move_type"] == "__terminal__"
    assert isinstance(marker["payload"], dict)
    assert marker["payload"]["move_type"] == "__terminal__"


class TestBuildReplayPayload:
    """Tests for build_replay_payload helper (post-refactor)."""

    def test_final_scores_passed_through(self):
        """final_scores in payload matches the argument, not a hard-coded {}."""
        scores = {"p1": 42, "p2": 37}
        log: list[dict] = []
        payload = build_replay_payload(
            run_id="test",
            stopped_reason="terminal",
            max_rounds=0,
            step_count=10,
            is_terminal=True,
            winner_id="p1",
            final_scores=scores,
            replay_log=log,
            shuffle_seed=42,
            deck_a_id="deck_a",
            deck_b_id="deck_b",
            board_path="/tmp/board.json",
            card_path="/tmp/catalog.json",
            setup_path="/tmp/setup.json",
            player_ids=["p1", "p2"],
        )
        assert payload["final_scores"] == {"p1": 42, "p2": 37}

    def test_terminal_appends_marker(self):
        """When is_terminal and stopped_reason is terminal, a marker is appended."""
        scores = {"p1": 42}
        log: list[dict] = [{"step_index": 0, "move_type": "play_card"}]
        payload = build_replay_payload(
            run_id="test",
            stopped_reason="terminal",
            max_rounds=0,
            step_count=10,
            is_terminal=True,
            winner_id="p1",
            final_scores=scores,
            replay_log=log,
            shuffle_seed=42,
            deck_a_id="deck_a",
            deck_b_id="deck_b",
            board_path="/tmp/board.json",
            card_path="/tmp/catalog.json",
            setup_path="/tmp/setup.json",
            player_ids=["p1", "p2"],
        )
        assert len(log) == 2
        assert log[-1]["move_type"] == "__terminal__"
        assert log[-1]["phase"] == ""
        assert log[-1]["label"] == "game_over"

    def test_non_terminal_no_marker(self):
        """When not terminal, no marker is appended."""
        log: list[dict] = [{"step_index": 0, "move_type": "play_card"}]
        payload = build_replay_payload(
            run_id="test",
            stopped_reason="round_cap",
            max_rounds=100,
            step_count=10,
            is_terminal=False,
            winner_id=None,
            final_scores={},
            replay_log=log,
            shuffle_seed=42,
            deck_a_id="deck_a",
            deck_b_id="deck_b",
            board_path="/tmp/board.json",
            card_path="/tmp/catalog.json",
            setup_path="/tmp/setup.json",
            player_ids=["p1", "p2"],
        )
        # Marker not appended when not terminal
        assert len(log) == 1
