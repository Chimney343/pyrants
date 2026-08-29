"""Integration tests: steps.jsonl step lines carry Tier-1 state snapshots, and
board (Tier-2) snapshots fire only on round changes or board-mutating moves.

Phase 2 of the IS-MCTS observability work (per-step game-state snapshots).

The board-snapshot condition is the interesting part: ``"state"`` is always
attached (Tier 1), but ``"state"."board"`` (Tier 2) is only attached when
``_is_board_mutating(move_type, payload)`` is true or when the move crosses a
round boundary.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import openspiel_pyrants  # noqa: F401
from scripts._obs import new_run_id
from scripts._state_snapshot import _BOARD_MUTATING_GENERIC_ACTIONS, _BOARD_MUTATING_MOVE_TYPES
from scripts.run_ismcts import (
    _game_dir,
    _load_game_or_die,
    _resolve_policy,
    run_one_game,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _quick_params(tmp_path, game_index=0, **overrides) -> dict:
    params = {
        "game": _load_game_or_die("python_pyrants_c", {"num_players": "2"}),
        "game_index": game_index,
        "num_sims": 2,
        "uct_c": 1.4,
        "max_world_samples": 10,
        "final_policy_type": _resolve_policy("visited"),
        "final_policy_name": "visited",
        "seed": 42,
        "shuffle_seed": 42 + game_index,
        "out_dir": tmp_path,
        "deck_a_id": "deck_a",
        "deck_b_id": "deck_b",
        "show_progress": False,
        "run_id": new_run_id(),
        "rollout_count": 1,
        "rollout_max_length": None,
        "max_rounds": 15,
        "setup_data_json": "",
        "num_players": 2,
    }
    params.update(overrides)
    return params


def _steps_lines(game_out) -> list[dict]:
    steps_path = game_out / "steps.jsonl"
    if not steps_path.exists():
        return []
    return [json.loads(line) for line in steps_path.open(encoding="utf-8")]


def _step_events(steps) -> list[dict]:
    """Return the step lines (event == 'step') only."""
    return [s for s in steps if s["event"] == "step"]


class _ScriptedBot:
    """Picks a move of a requested move_type when available, else the first legal move.

    ``preferences`` is a rotating list of move_type strings.  This lets a test
    force the sequence of applied moves to include a ``play_card`` (not
    board-mutating), a ``deploy`` (board-mutating), and enough moves to cross
    a round boundary.
    """

    def __init__(self, preferences):
        self._preferences = list(preferences)
        self._counter = 0

    def step_with_policy(self, state):
        legal_ids = state.legal_actions()
        indexed = []
        for aid in legal_ids:
            try:
                move = state.decode_action(aid)
            except Exception:
                move = None
            indexed.append((aid, move))

        preferred = self._preferences[self._counter % len(self._preferences)]
        self._counter += 1

        chosen_id = None
        for aid, move in indexed:
            if move is not None and move.move_type == preferred:
                chosen_id = aid
                break
        if chosen_id is None:
            chosen_id = legal_ids[0]

        policy = [(aid, 1.0 / len(legal_ids)) for aid in legal_ids]
        return policy, chosen_id


def _install_scripted_bot(monkeypatch, preferences):
    from open_spiel.python.algorithms.ismcts import ISMCTSBot

    bot = _ScriptedBot(preferences)

    def fake_step_with_policy(self, state):
        return bot.step_with_policy(state)

    monkeypatch.setattr(ISMCTSBot, "step_with_policy", fake_step_with_policy)


class TestStepStateSnapshots:
    def test_every_step_has_tier1_state_and_board_only_when_expected(
        self, requires_c_engine, tmp_path, monkeypatch
    ):
        """Force a play_card, then a deploy, then run to round end.

        Assert: every "step" line has a "state" key with Tier-1 fields;
        "board" appears in "state" only for board-mutating moves (deploy) and
        for steps that changed the round.
        """
        _install_scripted_bot(
            monkeypatch,
            # Force play_card first, deploy second, then rotate play_card/deploy.
            preferences=["play_card", "deploy", "play_card", "deploy"],
        )

        params = _quick_params(tmp_path, max_rounds=15)
        summary = run_one_game(**params)
        assert summary["decision_count"] > 0

        game_out = _game_dir(tmp_path, 0)
        steps = _step_events(_steps_lines(game_out))

        assert steps, "no step lines written"
        deploy_steps = [s for s in steps if s["move_type"] == "deploy"]
        play_card_steps = [s for s in steps if s["move_type"] == "play_card"]
        assert deploy_steps, "scripted bot should force at least one deploy"
        assert play_card_steps, "scripted bot should force at least one play_card"

        for i, step in enumerate(steps):
            # Tier 1 always present.
            assert "state" in step, f"step {i} missing 'state'"
            state = step["state"]
            for key in (
                "resource_power",
                "resource_influence",
                "market_row",
                "public_player_summaries",
            ):
                assert key in state, f"step {i} state missing {key}"

            # The step line's "round" is captured before apply; a step whose
            # apply crosses a round boundary is the one where this step's
            # round differs from the *next* step's round.
            next_round = steps[i + 1]["round"] if i + 1 < len(steps) else step["round"]
            round_changed = next_round != step["round"]
            expected_board = (
                step["move_type"] in _BOARD_MUTATING_MOVE_TYPES
                or (
                    step["move_type"] == "resolve_generic"
                    and any(
                        f"action_id='{a}'" in step["chosen_move"]
                        for a in _BOARD_MUTATING_GENERIC_ACTIONS
                    )
                )
                or round_changed
            )
            if expected_board:
                assert "board" in state, (
                    f"step {i} (move_type={step['move_type']}, round_changed={round_changed}) "
                    f"should have a board snapshot, got keys={list(state.keys())}"
                )
            else:
                assert "board" not in state, (
                    f"step {i} (move_type={step['move_type']}, round_changed={round_changed}) "
                    f"should NOT have a board snapshot"
                )

        # The deploy step must have the board snapshot.
        deploy_step = deploy_steps[0]
        assert "board" in deploy_step["state"]

        # A play_card step must not.
        play_card_step = play_card_steps[0]
        assert "board" not in play_card_step["state"]

        # Board snapshot fields.
        board = deploy_step["state"]["board"]
        assert "board_nodes" in board
        assert len(board["board_nodes"]) > 0
        for node in board["board_nodes"]:
            assert "node_id" in node
            assert "controller" in node
            assert "total_control" in node
            assert "troop_slots" in node
            assert "spies" in node
        for key in (
            "current_player_controlled_sites",
            "current_player_total_control_sites",
            "current_player_control_vp",
            "current_player_total_control_vp",
        ):
            assert key in board


class TestBoardSnapshotOnRoundBoundary:
    def test_round_boundary_attaches_board_snapshot(
        self, requires_c_engine, tmp_path, monkeypatch
    ):
        """Force only non-board-mutating moves (initial_placement / play_card /
        end_main_phase / resolve_*) so the game crosses rounds without any
        assassinate/deploy/return_spy: every board snapshot present must be a
        round-boundary step.
        """
        _install_scripted_bot(
            monkeypatch,
            preferences=[
                "initial_placement",
                "end_main_phase",
                "resolve_end_of_turn",
                "resolve_cleanup",
                "play_card",
                "end_main_phase",
            ],
        )

        params = _quick_params(tmp_path, max_rounds=8)
        summary = run_one_game(**params)
        assert summary["decision_count"] > 0

        game_out = _game_dir(tmp_path, 0)
        steps = _step_events(_steps_lines(game_out))

        board_steps = [s for s in steps if "board" in s.get("state", {})]
        assert board_steps, "expected at least one round-boundary board snapshot"

        for i, step in enumerate(steps):
            next_round = steps[i + 1]["round"] if i + 1 < len(steps) else step["round"]
            round_changed = next_round != step["round"]
            if round_changed:
                assert "board" in step["state"], (
                    f"round boundary step (round {step['round']} -> {next_round}) "
                    f"missing board snapshot"
                )
