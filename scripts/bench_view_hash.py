"""Micro-benchmark ``engine_player_view_json`` and ``engine_infostate_hash``.

Both run on the IS-MCTS hot path: the hash is the tree key, and the JSON view
is rendered for every observed node. Brief A2 adds fields to the view (every
opponent's discard list and the devour pile), so the view grows; this script
measures the cost of each function per call on the same playout states A1 used
for ``bench_determinize``.

The two functions are timed straight through the C DLL, so the numbers compare
across builds (a git worktree built with ``just build-c`` loads its own
``engine_c/engine_c.dll``). Record both in ADR-0008.

Usage:
    python -m scripts.bench_view_hash
    python -m scripts.bench_view_hash --states 118 --calls 3000 --players 4
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
from engine_c.bindings.engine_bindings import _lib  # noqa: E402

_VIEW_CAP = 512 * 1024


def _walk_to_state(game, seed: int, depth: int):
    state = game.new_initial_state()
    state.apply_action(seed)
    rng = np.random.RandomState(seed)
    for _ in range(depth):
        if state.is_terminal() or state.current_player() < 0:
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
        if state.is_terminal() or state.current_player() < 0 or state._adapter is None:
            continue
        states.append(state)
    return states


def _time_view(states, calls: int) -> list[float]:
    import ctypes

    buf = ctypes.create_string_buffer(_VIEW_CAP)
    samples = []
    for i in range(calls):
        state = states[i % len(states)]
        p = state.current_player()
        if p < 0:
            continue
        pid = state._game.get_player_ids()[p]
        psym = _lib.intern(pid.encode())
        t0 = time.perf_counter()
        _lib.engine_player_view_json(state._adapter._state._ptr, psym, buf, _VIEW_CAP)
        samples.append(time.perf_counter() - t0)
    return samples


def _time_hash(states, calls: int) -> list[float]:
    import ctypes

    out = (ctypes.c_uint64 * 2)()
    samples = []
    for i in range(calls):
        state = states[i % len(states)]
        p = state.current_player()
        if p < 0:
            continue
        pid = state._game.get_player_ids()[p]
        psym = _lib.intern(pid.encode())
        t0 = time.perf_counter()
        _lib.engine_infostate_hash(state._adapter._state._ptr, psym, out)
        samples.append(time.perf_counter() - t0)
    return samples


def _report(name: str, samples: list[float]) -> None:
    us = sorted(s * 1e6 for s in samples)
    mean = statistics.fmean(us)
    median = statistics.median(us)
    p95 = us[min(len(us) - 1, int(round(0.95 * (len(us) - 1))))]
    print(
        f"{name}: mean={mean:.3f} us  median={median:.3f} us  p95={p95:.3f} us  "
        f"calls/s={1e6 / mean:.0f}"
    )


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

    # Warm the DLL path and the intern table, then time.
    _time_view(states, min(50, args.calls))
    _time_hash(states, min(50, args.calls))

    _report("engine_player_view_json", _time_view(states, args.calls))
    _report("engine_infostate_hash", _time_hash(states, args.calls))
    print(f"players={args.players} states={len(states)}")


if __name__ == "__main__":
    main()
