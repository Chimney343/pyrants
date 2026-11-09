"""Micro-benchmark ``engine_determinize`` per call on playout states.

Determinization runs once per IS-MCTS simulation, so its per-call cost sits on
the hot path. This script times it on a set of mid-game states sampled the way
search reaches them: random legal moves from a seeded start, at the depths a
rollout actually visits.

Times only ``CEngineAdapter.determinize`` (the clone plus the resampling);
building the state and the loop overhead are outside the timer. Reports mean,
median, p95 and calls/s.

Usage:
    python -m scripts.bench_determinize
    python -m scripts.bench_determinize --states 118 --calls 200 --players 4

To compare two builds, run the same command from each tree (a git worktree
built with ``just build-c``); each run loads its own ``engine_c/engine_c.dll``.
Record both numbers in ADR-0007 (see A1).
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

import numpy as np
import pyspiel

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import openspiel_pyrants  # noqa: E402, F401 — registers python_pyrants_c


def _walk_to_state(game, seed: int, depth: int):
    """A state ``depth`` random-legal moves past the initial chance node."""
    state = game.new_initial_state()
    state.apply_action(seed)
    rng = np.random.RandomState(seed)
    for _ in range(depth):
        if state.is_terminal():
            break
        if state.current_player() < 0:
            break
        legal = state.legal_actions()
        if not legal:
            break
        state.apply_action(int(rng.choice(legal)))
    return state


def _sample_states(num_players: int, count: int):
    game = pyspiel.load_game("python_pyrants_c", {"num_players": str(num_players)})
    states = []
    for i in range(count):
        seed = 42 + i
        depth = 5 + (i % 26)
        state = _walk_to_state(game, seed, depth)
        if state.is_terminal() or state.current_player() < 0:
            continue
        if state._adapter is None:
            continue
        states.append(state)
    return states


def _timed_calls(states, calls: int) -> list[float]:
    samples = []
    i = 0
    for _ in range(calls):
        state = states[i % len(states)]
        i += 1
        player = state.current_player()
        if player < 0:
            continue
        player_id = state._game.get_player_ids()[player]
        seed = int(np.random.RandomState(1000 + i).randint(0, 2**31 - 1))
        adapter = state._adapter
        t0 = time.perf_counter()
        det = adapter.determinize(player_id, seed)
        elapsed = time.perf_counter() - t0
        if det is None:
            raise RuntimeError("determinize returned None")
        det.destroy()
        samples.append(elapsed)
    return samples


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--players", type=int, default=4)
    parser.add_argument("--states", type=int, default=118)
    parser.add_argument("--calls", type=int, default=3000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    np.random.seed(args.seed)
    states = _sample_states(args.players, args.states)
    if not states:
        raise SystemExit("no benchmarkable states")

    # Warm up: touch the DLL path and the intern table, then time.
    _timed_calls(states, min(50, args.calls))
    samples = _timed_calls(states, args.calls)

    us = sorted(s * 1e6 for s in samples)
    mean_us = statistics.fmean(us)
    median_us = statistics.median(us)
    p95_us = us[min(len(us) - 1, int(round(0.95 * (len(us) - 1))))]
    print(
        f"players={args.players} states={len(states)} calls={len(us)}\n"
        f"engine_determinize: mean={mean_us:.2f} us  median={median_us:.2f} us  "
        f"p95={p95_us:.2f} us  calls/s={1e6 / mean_us:.0f}"
    )


if __name__ == "__main__":
    main()
