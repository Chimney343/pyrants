"""Tests for CRolloutEvaluator — the C-accelerated IS-MCTS rollout evaluator
(one ctypes call per whole rollout via engine_random_rollout, instead of
OpenSpiel's RandomRolloutEvaluator driving legal_actions()/apply_action() one
step at a time from Python). See the IS-MCTS rollout speedup plan.
"""

from __future__ import annotations

import math
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
class TestCRolloutEvaluator:
    def test_evaluate_returns_finite_per_player_array(self, requires_c_engine):
        from openspiel_pyrants.c_rollout_evaluator import CRolloutEvaluator

        game = _load_c_game(2)
        state = game.new_initial_state()
        state.apply_action(42)

        evaluator = CRolloutEvaluator(max_length=20, random_state=np.random.RandomState(1))
        result = evaluator.evaluate(state)

        assert len(result) == 2
        assert all(math.isfinite(float(v)) for v in result)

    def test_prior_matches_uniform_over_legal_actions(self, requires_c_engine):
        from openspiel_pyrants.c_rollout_evaluator import CRolloutEvaluator

        game = _load_c_game(2)
        state = game.new_initial_state()
        state.apply_action(42)

        evaluator = CRolloutEvaluator(max_length=20, random_state=np.random.RandomState(1))
        legal = set(state.legal_actions())
        prior = evaluator.prior(state)

        prior_actions = {a for a, _ in prior}
        assert prior_actions == legal
        probs = [p for _, p in prior]
        assert abs(sum(probs) - 1.0) < 1e-9
        assert all(abs(p - 1.0 / len(legal)) < 1e-9 for p in probs)

    def test_ismcts_bot_runs_with_c_rollout_evaluator(self, requires_c_engine):
        from open_spiel.python.algorithms.ismcts import ISMCTSBot, ISMCTSFinalPolicyType

        from openspiel_pyrants.c_rollout_evaluator import CRolloutEvaluator

        game = _load_c_game(2)
        rng = np.random.RandomState(42)

        bots = [
            ISMCTSBot(
                game=game,
                evaluator=CRolloutEvaluator(max_length=20, random_state=rng),
                uct_c=1.4,
                max_simulations=5,
                max_world_samples=100,
                random_state=rng,
                final_policy_type=ISMCTSFinalPolicyType.NORMALIZED_VISITED_COUNT,
            )
            for _ in range(2)
        ]

        state = game.new_initial_state()
        state.apply_action(42)

        cp = state.current_player()
        assert 0 <= cp < 2
        legal_ids = state.legal_actions()
        policy, chosen = bots[cp].step_with_policy(state)

        prob_sum = sum(float(p) for _, p in policy)
        assert abs(prob_sum - 1.0) < 1e-6
        assert chosen in legal_ids
