"""Tests for CEngine.random_rollout / CEngineAdapter.random_rollout — the
Python binding for the C-accelerated whole-rollout loop (engine_random_rollout)
that backs CRolloutEvaluator. See the IS-MCTS rollout speedup plan for context.

Note: player.score is a final-tally field written only at genuine terminal
(distinct from vp_tokens, which tracks running progress) — see the file-level
note in engine_c/tests/test_rollout.c. A fresh game does not reach terminal
within any practical rollout step budget, so short/`max_length`-capped
rollouts from a fresh session always report score 0 for every player; tests
below assert accordingly rather than expecting a nonzero signal.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from engine_c.bindings.c_adapter import CEngineAdapter  # noqa: E402
from engine_c.bindings.ce_api import CEngine  # noqa: E402
from engine_c.bindings.session import CSession  # noqa: E402


def _new_session(seed: int = 42) -> CSession:
    engine = CEngine()
    engine.initialize()
    return CSession(engine, ["p1", "p2"], seed)


def test_random_rollout_returns_scores_for_all_players():
    session = _new_session()
    terminal, scores = session._engine.random_rollout(session.state, seed=1, max_length=20)
    assert isinstance(terminal, bool)
    assert set(scores.keys()) == {"p1", "p2"}
    assert all(isinstance(v, int) for v in scores.values())
    session.destroy()


def test_random_rollout_is_deterministic_for_same_seed():
    session = _new_session()
    result_a = session._engine.random_rollout(session.state, seed=777, max_length=20)
    result_b = session._engine.random_rollout(session.state, seed=777, max_length=20)
    assert result_a == result_b
    session.destroy()


def test_random_rollout_does_not_mutate_input_state():
    session = _new_session()
    round_before = session.state.round_number
    terminal_before = session.is_terminal()

    session._engine.random_rollout(session.state, seed=55, max_length=20)

    assert session.state.round_number == round_before
    assert session.is_terminal() == terminal_before
    session.destroy()


def test_random_rollout_short_cutoff_scores_current_state():
    session = _new_session()
    terminal, scores = session._engine.random_rollout(session.state, seed=5, max_length=1)
    assert terminal is False
    assert scores == {"p1": 0, "p2": 0}
    session.destroy()


def test_adapter_random_rollout_passthrough():
    engine = CEngine()
    engine.initialize()
    player_ids = ["p1", "p2"]
    c_state = engine.create_game(player_ids, seed=42)
    adapter = CEngineAdapter(c_state, engine, player_ids, shuffle_seed=42)

    terminal, scores = adapter.random_rollout(seed=1, max_length=20)
    assert isinstance(terminal, bool)
    assert set(scores.keys()) == {"p1", "p2"}
    engine.destroy(c_state)
