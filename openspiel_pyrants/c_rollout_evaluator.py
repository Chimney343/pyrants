"""CRolloutEvaluator — IS-MCTS leaf evaluator backed by ``engine_random_rollout``.

Runs the whole random rollout in a single C call (via
``CEngineAdapter.random_rollout``) instead of driving
``legal_actions()``/``apply_action()`` one Python/ctypes round trip per game
step, the way OpenSpiel's stock ``RandomRolloutEvaluator`` does. See the
IS-MCTS rollout speedup plan for the full rationale.
"""

from __future__ import annotations

import numpy as np
from open_spiel.python.algorithms.mcts import Evaluator


class CRolloutEvaluator(Evaluator):
    """Random-rollout evaluator whose rollout runs entirely in C.

    Produces the same value shape ``PyrantsCState.returns()`` does: a
    zero-sum ``[s0-s1, s1-s0]`` pair for 2 players, raw per-player scores
    otherwise — so UCT sees an identical value scale regardless of whether
    this evaluator or ``RandomRolloutEvaluator`` produced the leaf value.
    """

    def __init__(self, max_length: int = 0, random_state=None):
        self.max_length = max_length
        self._random_state = random_state or np.random.RandomState()

    def evaluate(self, state):
        adapter = state._adapter
        seed = int(self._random_state.randint(0, 2**31 - 1))
        _terminal, scores = adapter.random_rollout(seed, self.max_length)

        player_ids = adapter.player_ids
        if len(player_ids) == 2:
            s0 = scores.get(player_ids[0], 0)
            s1 = scores.get(player_ids[1], 0)
            return np.array([float(s0 - s1), float(s1 - s0)])
        return np.array([float(scores.get(pid, 0)) for pid in player_ids])

    def prior(self, state):
        if state.is_chance_node():
            return state.chance_outcomes()
        legal_actions = state.legal_actions(state.current_player())
        return [(action, 1.0 / len(legal_actions)) for action in legal_actions]
