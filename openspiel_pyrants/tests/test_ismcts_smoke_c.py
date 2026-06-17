"""IS-MCTS smoke test for the C engine backend.

Runs a single game with low sims/move against ``python_pyrants_c``.
Skipped if ``PYRANTS_SKIP_ISMCTS=1`` or if the C engine DLL is missing.
"""

from __future__ import annotations

import os
import numpy as np
import pyspiel
import pytest

import openspiel_pyrants  # noqa: F401


def _load_c_game(num_players: int = 2):
    return pyspiel.load_game("python_pyrants_c", {"num_players": str(num_players)})


@pytest.mark.skipif(
    os.environ.get("PYRANTS_SKIP_ISMCTS") == "1",
    reason="PYRANTS_SKIP_ISMCTS=1 set",
)
class TestISMCTSSmokeC:
    @pytest.mark.parametrize("num_players", [2, 3, 4])
    def test_one_game_low_sims(self, requires_c_engine, num_players):
        from open_spiel.python.algorithms.ismcts import ISMCTSBot, ISMCTSFinalPolicyType
        from open_spiel.python.algorithms.mcts import RandomRolloutEvaluator

        game = _load_c_game(num_players)
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
            )
            for _ in range(num_players)
        ]

        state = game.new_initial_state()
        state.apply_action(42)

        decisions = []
        while not state.is_terminal():
            cp = state.current_player()
            if cp < 0 or cp >= num_players:
                break
            bot = bots[cp]
            legal_ids = state.legal_actions()
            policy, chosen = bot.step_with_policy(state)

            action_probs = {aid: float(prob) for aid, prob in policy}
            prob_sum = sum(action_probs.values())
            assert abs(prob_sum - 1.0) < 1e-6, f"Policy sums to {prob_sum}"

            assert chosen in legal_ids, f"Chosen {chosen} not in legal actions"

            decisions.append({
                "node": len(decisions),
                "legal_action_ids": legal_ids,
                "policy": action_probs,
                "chosen_action_id": chosen,
            })
            state.apply_action(chosen)

        assert len(decisions) > 0, "No decisions made"
        ret = state.returns()
        assert len(ret) == num_players
        if num_players == 2:
            assert abs(sum(ret)) < 1e-9, f"Returns not zero-sum: {ret}"
