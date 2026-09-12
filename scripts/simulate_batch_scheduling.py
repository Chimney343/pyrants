"""Project A2's claimed games/h gain from real, already-measured per-game wall times.

A2 (``docs/ismcts-walltime-plan.md`` § A2) replaces today's practice of playing
the corpus as repeated small invocations (e.g. 32 games each) with one
continuous stream of the seed range, or large offset-sharded chunks. Its
claimed gain comes from diluting each invocation's *wave tail* -- a fresh
16-worker pool must fully drain (wait for its own slowest game) before the run
-- and the next invocation's pool -- can finish, and that idle tail is a much
bigger fraction of the total when a pool only gets ~2 games per worker (32
games / 16 workers) than when it gets ~60 (1,000 / 16).

Re-running real games at corpus scale just to observe this would take many
hours. Instead this script reuses the per-game ``wall_time_sec`` already
recorded in a landed run's ``game_*/summary.json`` files and simulates the
*same* scheduling policy ``scripts/run_ismcts.py`` actually uses --
``ProcessPoolExecutor.submit`` for every game up front, so a worker takes the
next queued game the instant it frees up -- via greedy earliest-free-worker
assignment (a min-heap over worker free-times). That reproduces the measured
run wall to within simulation noise (printed as the calibration check below);
once calibrated, the same simulator is cheap to run at any corpus size.

Two policies are compared for a target corpus size:

* **batched**  -- the corpus split into repeated ``--batch-size``-game
  invocations (today's practice: a fresh pool per invocation, each paying its
  own wave tail plus one process-startup overhead).
* **streamed** -- the same total games as one invocation (or, equivalently,
  offset-sharded invocations large enough that the per-invocation overhead is
  negligible), paying the wave tail once.

Usage:
    python scripts/simulate_batch_scheduling.py --run-dir <run_dir> --workers 16 \
        --batch-size 32 --target-games 1000 [--invocation-overhead-sec 0.65]

The calibration line must be within a few percent of the source run's own
measured wall (``manifest.created_utc`` to the newest file) -- if it isn't,
the source run's game count/worker count don't match ``--batch-size``/
``--workers``, or the projection shouldn't be trusted.
"""

from __future__ import annotations

import argparse
import heapq
import json
from datetime import UTC, datetime
from pathlib import Path


def _load_game_walls(run_dir: Path) -> list[float]:
    walls: list[float] = []
    for p in sorted(run_dir.glob("game_*/summary.json")):
        summary = json.loads(p.read_text(encoding="utf-8"))
        wall = summary.get("wall_time_sec")
        if wall is not None:
            walls.append(float(wall))
    if not walls:
        raise SystemExit(f"no per-game wall_time_sec found under {run_dir}")
    return walls


def _measured_run_wall_sec(run_dir: Path) -> float | None:
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        return None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    created = manifest.get("created_utc")
    if not created:
        return None
    created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
    mtimes = [p.stat().st_mtime for p in run_dir.rglob("*") if p.is_file()]
    if not mtimes:
        return None
    last_dt = datetime.fromtimestamp(max(mtimes), tz=UTC)
    return (last_dt - created_dt).total_seconds()


def greedy_makespan(durations: list[float], workers: int) -> float:
    """Earliest-free-worker assignment: as soon as a worker frees up, it takes
    the next queued game in submission order. This is what
    ``ProcessPoolExecutor`` does when every future is submitted up front, as
    ``run_ismcts.py`` does."""
    free_at = [0.0] * workers
    heapq.heapify(free_at)
    for d in durations:
        t = heapq.heappop(free_at)
        heapq.heappush(free_at, t + d)
    return max(free_at)


def project(
    durations: list[float],
    workers: int,
    batch_size: int,
    target_games: int,
    overhead_sec: float,
) -> tuple[float, float, int]:
    reps = -(-target_games // len(durations))  # ceil
    extended = (durations * reps)[:target_games]

    batched_wall = 0.0
    n_invocations = 0
    for i in range(0, target_games, batch_size):
        chunk = extended[i : i + batch_size]
        batched_wall += greedy_makespan(chunk, workers) + overhead_sec
        n_invocations += 1

    streamed_wall = greedy_makespan(extended, workers) + overhead_sec

    return batched_wall, streamed_wall, n_invocations


def _games_per_hour(games: int, wall_sec: float) -> float:
    return games / (wall_sec / 3600.0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run-dir", type=Path, required=True, help="Source run to draw real per-game wall_time_sec from")
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--batch-size", type=int, default=32, help="Games per invocation under the 'batched' policy")
    parser.add_argument("--target-games", type=int, default=1000)
    parser.add_argument(
        "--invocation-overhead-sec",
        type=float,
        default=0.65,
        help="Fixed per-invocation wall cost (imports, catalog load, pool spin-up/teardown) "
        "paid once per invocation regardless of game count. Default from a measured "
        "--num-games 1 --workers 1 minimal invocation.",
    )
    args = parser.parse_args()

    durations = _load_game_walls(args.run_dir)
    n_source = len(durations)

    calibrated_wall = greedy_makespan(durations, args.workers) + args.invocation_overhead_sec
    measured_wall = _measured_run_wall_sec(args.run_dir)

    print(f"Source run: {args.run_dir} ({n_source} games)")
    print(f"Mean/max game wall: {sum(durations) / n_source:.1f}s / {max(durations):.1f}s")
    print()
    print("Calibration (simulate the source run's own size/workers vs. its measured wall):")
    print(f"  simulated wall : {calibrated_wall:.1f}s")
    if measured_wall is not None:
        err = (calibrated_wall - measured_wall) / measured_wall * 100
        print(f"  measured wall  : {measured_wall:.1f}s  (simulation error {err:+.1f}%)")
    else:
        print("  measured wall  : unavailable (no manifest.json / created_utc)")
    print()

    batched_wall, streamed_wall, n_invocations = project(
        durations, args.workers, args.batch_size, args.target_games, args.invocation_overhead_sec
    )
    batched_gph = _games_per_hour(args.target_games, batched_wall)
    streamed_gph = _games_per_hour(args.target_games, streamed_wall)

    print(f"Projection at {args.target_games} games, {args.workers} workers:")
    print(f"  batched  ({n_invocations} x {args.batch_size}-game invocations): "
          f"{batched_wall / 3600:.2f} h, {batched_gph:.1f} games/h")
    print(f"  streamed (1 invocation)                       : "
          f"{streamed_wall / 3600:.2f} h, {streamed_gph:.1f} games/h")
    print(f"  ratio (streamed / batched)                     : x{streamed_gph / batched_gph:.3f}")


if __name__ == "__main__":
    main()
