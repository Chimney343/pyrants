"""Smoke test for IS-MCTS bot against python_pyrants.

Runs a single game with low sims/move, asserts basic invariants.
Skipped automatically if ``PYRANTS_SKIP_ISMCTS=1`` is set
(full IS-MCTS is wall-clock expensive — not for every test run).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import numpy as np
import pyspiel
import pytest

import openspiel_pyrants  # noqa: F401 — registers python_pyrants


@pytest.mark.skipif(
    os.environ.get("PYRANTS_SKIP_ISMCTS") == "1",
    reason="PYRANTS_SKIP_ISMCTS=1 set — skipping expensive IS-MCTS smoke test",
)
class TestISMCTSSmoke:
    def test_one_game_low_sims(self):
        from open_spiel.python.algorithms.ismcts import ISMCTSBot, ISMCTSFinalPolicyType
        from open_spiel.python.algorithms.mcts import RandomRolloutEvaluator

        game = pyspiel.load_game("python_pyrants")
        rng = np.random.RandomState(42)

        bots = [
            ISMCTSBot(
                game=game,
                evaluator=RandomRolloutEvaluator(n_rollouts=1, random_state=rng),
                uct_c=1.4,
                max_simulations=5,
                max_world_samples=100,
                random_state=rng,
                final_policy_type=ISMCTSFinalPolicyType.NORMALIZED_VISITED_COUNT,
            ),
            ISMCTSBot(
                game=game,
                evaluator=RandomRolloutEvaluator(n_rollouts=1, random_state=rng),
                uct_c=1.4,
                max_simulations=5,
                max_world_samples=100,
                random_state=rng,
                final_policy_type=ISMCTSFinalPolicyType.NORMALIZED_VISITED_COUNT,
            ),
        ]

        state = game.new_initial_state()
        state.apply_action(42)

        decisions = []
        while not state.is_terminal():
            cp = state.current_player()
            if cp < 0 or cp >= 2:
                break
            bot = bots[cp]
            legal_ids = state.legal_actions()
            policy, chosen = bot.step_with_policy(state)

            action_probs = {}
            for aid, prob in policy:
                action_probs[aid] = float(prob)

            prob_sum = sum(action_probs.values())
            assert abs(prob_sum - 1.0) < 1e-6, f"Policy sums to {prob_sum}, not 1.0"

            assert chosen in legal_ids, f"Chosen action {chosen} not in legal actions"

            decisions.append({
                "node": len(decisions),
                "legal_action_ids": legal_ids,
                "policy": action_probs,
                "chosen_action_id": chosen,
            })

            state.apply_action(chosen)

        assert len(decisions) > 0
        ret = state.returns()
        assert len(ret) == 2
        assert abs(sum(ret)) < 1e-9

    def test_runner_script_outputs_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "ismcts_out"
            import subprocess
            import sys

            result = subprocess.run(
                [
                    sys.executable, "-m", "scripts.run_ismcts",
                    "--num-sims", "5",
                    "--num-games", "1",
                    "--seed", "123",
                    "--output-dir", str(out_dir),
                ],
                capture_output=True,
                text=True,
                timeout=300,
            )

            assert result.returncode == 0, f"Runner failed:\n{result.stderr}"

            assert (out_dir / "summary.csv").exists()
            assert (out_dir / "summary.md").exists()

            game_dir = out_dir / "game_0000"
            assert (game_dir / "decisions.jsonl").exists()
            assert (game_dir / "replay.json").exists()
            assert (game_dir / "summary.json").exists()

            with (game_dir / "decisions.jsonl").open() as f:
                lines = [json.loads(line) for line in f if line.strip()]
            assert len(lines) > 0

            for entry in lines:
                prob_sum = sum(entry["policy"].values())
                assert abs(prob_sum - 1.0) < 1e-6
                assert entry["chosen_action_id"] in entry["legal_action_ids"]

            with (game_dir / "replay.json").open() as f:
                replay = json.load(f)
            assert "replay_log" in replay
            assert len(replay["replay_log"]) == len(lines)

            with (game_dir / "summary.json").open() as f:
                summary = json.load(f)
            assert summary["decision_count"] == len(lines)

            with (out_dir / "summary.csv").open() as f:
                csv_lines = f.read().strip().split("\n")
            assert len(csv_lines) >= 2
