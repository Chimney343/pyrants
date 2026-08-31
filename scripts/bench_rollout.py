"""Benchmark IS-MCTS random-rollout throughput.

Times the rollout evaluator IS-MCTS uses to score newly expanded tree leaves.
``--engine py`` measures the current path (OpenSpiel's Python-level
``RandomRolloutEvaluator``, one ctypes round trip per game step). ``--engine c``
measures the C-accelerated path (``engine_random_rollout``, one ctypes call per
whole rollout) once it exists — see the IS-MCTS rollout speedup plan.

Usage:
    python -m scripts.bench_rollout --engine py --num-rollouts 200
    just bench-rollout
    just bench-rollout c
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pyspiel

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import openspiel_pyrants  # noqa: E402, F401 — registers python_pyrants_c


def _build_state(seed: int, warmup_steps: int):
    """Load python_pyrants_c and advance past the initial chance node plus
    a few real moves, so the benchmark isn't measuring the trivial empty-board
    state (which has few legal moves and isn't representative of a mid-tree
    IS-MCTS leaf)."""
    game = pyspiel.load_game("python_pyrants_c", {"num_players": "2"})
    state = game.new_initial_state()
    rng = np.random.RandomState(seed)

    while state.is_chance_node():
        outcomes = state.chance_outcomes()
        actions, probs = zip(*outcomes)
        state.apply_action(int(rng.choice(actions, p=probs)))

    for _ in range(warmup_steps):
        if state.is_terminal():
            break
        legal = state.legal_actions()
        if not legal:
            break
        state.apply_action(legal[rng.randint(len(legal))])

    return state


def _measure_avg_depth(state, rng: np.random.RandomState, samples: int = 20) -> float:
    """Untimed diagnostic: average steps-to-terminal for a random rollout from
    ``state``. Reported separately from the timed loop so the hot path being
    benchmarked isn't polluted with extra bookkeeping."""
    total = 0
    for _ in range(samples):
        working = state.clone()
        depth = 0
        while not working.is_terminal():
            legal = working.legal_actions()
            if not legal:
                break
            working.apply_action(legal[rng.randint(len(legal))])
            depth += 1
        total += depth
    return total / samples


def bench_python(state, num_rollouts: int, seed: int) -> dict:
    from open_spiel.python.algorithms.mcts import RandomRolloutEvaluator

    evaluator = RandomRolloutEvaluator(
        n_rollouts=1, random_state=np.random.RandomState(seed)
    )
    t0 = time.perf_counter()
    for _ in range(num_rollouts):
        evaluator.evaluate(state)
    elapsed = time.perf_counter() - t0
    return {
        "rollouts": num_rollouts,
        "elapsed_s": elapsed,
        "rollouts_per_s": num_rollouts / elapsed if elapsed > 0 else float("inf"),
    }


def bench_c(state, num_rollouts: int, seed: int) -> dict:
    from openspiel_pyrants.c_rollout_evaluator import CRolloutEvaluator

    evaluator = CRolloutEvaluator(max_length=0, random_state=np.random.RandomState(seed))
    t0 = time.perf_counter()
    for _ in range(num_rollouts):
        evaluator.evaluate(state)
    elapsed = time.perf_counter() - t0
    return {
        "rollouts": num_rollouts,
        "elapsed_s": elapsed,
        "rollouts_per_s": num_rollouts / elapsed if elapsed > 0 else float("inf"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=["py", "c"], default="py")
    parser.add_argument("--num-rollouts", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--warmup-steps", type=int, default=10,
        help="Real moves applied before benchmarking, to reach a non-trivial state",
    )
    args = parser.parse_args()

    state = _build_state(args.seed, args.warmup_steps)
    print(f"Benchmark state: terminal={state.is_terminal()}")

    diag_rng = np.random.RandomState(args.seed + 1)
    avg_depth = _measure_avg_depth(state, diag_rng)
    print(f"Diagnostic: avg rollout depth over 20 untimed samples = {avg_depth:.1f} steps")

    bench_fn = bench_python if args.engine == "py" else bench_c
    result = bench_fn(state, args.num_rollouts, args.seed)

    print(
        f"engine={args.engine} rollouts={result['rollouts']} "
        f"elapsed={result['elapsed_s']:.3f}s "
        f"rollouts/s={result['rollouts_per_s']:.1f} "
        f"steps/s(approx)={result['rollouts_per_s'] * avg_depth:.0f}"
    )


if __name__ == "__main__":
    main()
