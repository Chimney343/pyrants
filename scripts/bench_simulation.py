"""Repeatable simulation performance benchmarks.

Uses scenario files (which embed full definitions) to avoid dependency on
missing raw JSON board files.
"""
from __future__ import annotations

import cProfile
import sys
import time
from pathlib import Path
from random import Random

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.rules import apply, legal_moves
from engine.state import GameState
from game_session import GameSession
from game_setup.loaders import default_catalog_registry
from game_setup.scenarios import load_game_state_from_scenario
from game_simulation import (
    make_random_legal_move_chooser,
    make_random_legal_move_chooser_engine,
    run_fast_simulation,
    run_simulation,
)

SCENARIO_2P = ROOT / "data" / "scenarios" / "initial_two_player.json"


def _make_session_from_scenario(path: Path, player_ids: list[str] | None = None, seed: int = 1) -> GameSession:
    _ = player_ids
    _ = seed
    state = load_game_state_from_scenario(path, catalog_registry=default_catalog_registry())
    return GameSession(state)


def bench_engine_only(max_steps: int = 200, seed: int = 1) -> float:
    session = _make_session_from_scenario(SCENARIO_2P)
    state: GameState = session.state
    rng = Random(seed)
    t0 = time.perf_counter()
    for _ in range(max_steps):
        moves = legal_moves(state)
        if not moves:
            break
        state = apply(state, rng.choice(moves))
    return time.perf_counter() - t0


def bench_full_simulation(max_steps: int = 200, seed: int = 1) -> float:
    session = _make_session_from_scenario(SCENARIO_2P)
    chooser = make_random_legal_move_chooser(seed)
    t0 = time.perf_counter()
    run_simulation(session, chooser, max_steps=max_steps)
    return time.perf_counter() - t0


def bench_fast_simulation(max_steps: int = 200, seed: int = 1) -> float:
    session = _make_session_from_scenario(SCENARIO_2P)
    state = session.state
    chooser = make_random_legal_move_chooser_engine(seed)
    t0 = time.perf_counter()
    run_fast_simulation(state, chooser, max_steps=max_steps)
    return time.perf_counter() - t0


def profile_engine_only(output: str, max_steps: int = 200, seed: int = 1) -> None:
    session = _make_session_from_scenario(SCENARIO_2P)
    state: GameState = session.state
    rng = Random(seed)

    def _loop() -> None:
        nonlocal state
        for _ in range(max_steps):
            moves = legal_moves(state)
            if not moves:
                break
            state = apply(state, rng.choice(moves))

    cProfile.runctx("_loop()", {"_loop": _loop}, {}, output)


def profile_full_simulation(output: str, max_steps: int = 200, seed: int = 1) -> None:
    session = _make_session_from_scenario(SCENARIO_2P)
    chooser = make_random_legal_move_chooser(seed)

    def _loop() -> None:
        run_simulation(session, chooser, max_steps=max_steps)

    cProfile.runctx("_loop()", {"_loop": _loop, "run_simulation": run_simulation}, {}, output)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run simulation performance benchmarks")
    parser.add_argument("--profile", action="store_true", help="Write cProfile output files")
    parser.add_argument("--steps", type=int, default=200, help="Max steps per benchmark run")
    parser.add_argument("--repeat", type=int, default=3, help="Number of warm-up plus timed runs")
    args = parser.parse_args()

    Path("artifacts").mkdir(parents=True, exist_ok=True)

    print(f"=== Simulation Benchmark ({args.steps} steps, {args.repeat} repeats) ===\n")
    print(f"{'Benchmark':<28} {'Time (s)':>10} {'Steps/s':>12}")
    print("-" * 52)

    for _ in range(args.repeat):
        for name, fn in [
            ("engine-only (2p, random)", lambda: bench_engine_only(args.steps)),
            ("fast-sim (2p, random)", lambda: bench_fast_simulation(args.steps)),
            ("full-sim (2p, random)", lambda: bench_full_simulation(args.steps)),
        ]:
            elapsed = fn()
            rate = args.steps / elapsed if elapsed > 0 else float("inf")
            print(f"  {name:<26} {elapsed:10.4f} {rate:12.1f}")

    if args.profile:
        print("\nWriting cProfile outputs...")
        profile_engine_only("artifacts/bench_engine.prof", args.steps)
        profile_full_simulation("artifacts/bench_sim.prof", args.steps)
        print("  artifacts/bench_engine.prof")
        print("  artifacts/bench_sim.prof")


if __name__ == "__main__":
    main()
