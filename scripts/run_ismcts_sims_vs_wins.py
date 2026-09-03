"""IS-MCTS sims-vs-wins experiment: does a bigger budget win more games?

Seats get a rotating ladder of simulation budgets (default 50/100/200/400 sims
per move). The ladder rotates across seats between games so seat order (seat 0
always moves first) is deconfounded from budget strength. Every game records
which seat had which budget (``num_sims_per_seat``), and the run writes a
statistical ``analysis.json``/``analysis.md``: win rate per budget and per seat
with Wilson 95% CIs, mean final VP / mean rank per budget, and a seeded
within-game permutation trend test.

WARNING: pyrants engine clone costs ~10 ms per state. With the default
``random-c`` evaluator (the whole rollout in one C call, ~19x faster than
``random-py``) a 4-player game at 50/100/200/400 sims is on the order of a few
minutes per game; ``random-py`` would be roughly 19x slower and is not a sane
default here. ALWAYS run the 8-game pilot first to calibrate wall-time and
confirm zero crashes before committing to the 120-game main run:

    just ismcts-sims-vs-wins-pilot
    just ismcts-sims-vs-wins
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import structlog
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts._obs import RunMetrics, configure_logging, new_run_id  # noqa: E402
from scripts._sims_vs_wins import (  # noqa: E402
    analyze,
    parse_sims_spec,
    seat_budgets_for_game,
)
from scripts.run_ismcts import (  # noqa: E402
    POLICY_CHOICES,
    GameRunFailedError,
    _build_ismcts_setup_json,
    _run_one_game_standalone,
    write_summaries,
)

DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "ismcts" / "experiments" / "sims_vs_wins"
_GAME_NAME = "python_pyrants_c"


def _experiment_dir(base: Path, run_id: str) -> Path:
    """Return the per-run directory, keyed by a UTC timestamp + run id."""
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return base / f"{ts}_{run_id}"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the IS-MCTS sims-vs-wins experiment (rotating budget ladder)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--num-sims-per-seat",
        type=str,
        default="50,100,200,400",
        help="Comma-separated per-seat sims per move (default: 50,100,200,400)",
    )
    parser.add_argument(
        "--num-players",
        type=int,
        default=4,
        help="Number of players; must equal --num-sims-per-seat length (default: 4)",
    )
    parser.add_argument("--num-games", type=int, default=120)
    rotation = parser.add_mutually_exclusive_group()
    rotation.add_argument(
        "--rotate-seats",
        dest="rotate_seats",
        action="store_true",
        default=True,
        help="Rotate the budget ladder across seats per game (default)",
    )
    rotation.add_argument(
        "--no-rotate-seats",
        dest="rotate_seats",
        action="store_false",
        help="Keep a fixed P1=first-budget … mapping (no rotation)",
    )
    parser.add_argument(
        "--evaluator",
        choices=["random-py", "random-c"],
        default="random-c",
        help="Rollout evaluator backend (default: random-c, ~19x faster)",
    )
    parser.add_argument("--uct-c", type=float, default=1.4)
    parser.add_argument(
        "--max-world-samples",
        type=int,
        default=-1,
        help="Max determinizations to pool before reusing (default: -1 = unlimited)",
    )
    parser.add_argument("--final-policy", choices=list(POLICY_CHOICES), default="visited")
    parser.add_argument("--rollout-count", type=int, default=1)
    parser.add_argument("--rollout-max-length", type=int, default=0)
    parser.add_argument("--max-rounds", type=int, default=0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--shuffle-seed", type=int, default=0)
    parser.add_argument("--workers", type=int, default=0,
                        help="Number of parallel games (0 = auto = CPU count)")
    parser.add_argument("--log-level", type=str, default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    parser.add_argument("--json-logs", action="store_true")
    parser.add_argument("--worker-log-level", type=str, default="WARNING",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)

    args = parser.parse_args()
    if args.num_players < 2 or args.num_players > 4:
        parser.error(f"--num-players must be 2–4, got {args.num_players}")
    try:
        args.num_sims_per_seat = parse_sims_spec(args.num_sims_per_seat, args.num_players)
    except ValueError as exc:
        parser.error(str(exc))
    return args


def _render_analysis_md(analysis: dict) -> str:
    lines = ["# Sims-vs-Wins Analysis\n"]
    lines.append(
        f"- **Games:** {analysis['n_games']} "
        f"(decided {analysis['n_decided']}, ties {analysis['n_ties']}, "
        f"round_cap {analysis['n_round_cap']}, errors {analysis['n_errors']})"
    )
    if analysis["low_effective_n"]:
        lines.append(
            f"- **WARNING: low effective N** — only {analysis['effective_n_frac']:.0%} "
            "of games were decided (below the 80% threshold)."
        )
    trend = analysis["trend"]
    lines.append(
        f"- **Trend test:** p={trend['p_value']} "
        f"(statistic {trend['statistic']}, {trend['n_permutations']} permutations, "
        f"{trend['n_games_used']} games used)"
    )
    lines.append("")
    lines.append("## Wins by budget\n")
    lines.append("| budget | wins | games | win% | 95% CI | mean VP | mean rank |")
    lines.append("|--------|------|-------|------|--------|---------|-----------|")
    for b in analysis["budgets"]:
        d = analysis["by_budget"][b]
        ci = f"{d['ci95_low']:.3f}–{d['ci95_high']:.3f}"
        mean_vp = "-" if d["mean_vp"] is None else f"{d['mean_vp']:.2f}"
        mean_rank = "-" if d["mean_rank"] is None else f"{d['mean_rank']:.2f}"
        lines.append(
            f"| {b} | {d['wins']} | {d['decided']} | {d['win_rate']:.3f} | "
            f"{ci} | {mean_vp} | {mean_rank} |"
        )
    lines.append("")
    lines.append("## Wins by seat (confound check)\n")
    lines.append("| seat | wins | games | win% | 95% CI |")
    lines.append("|------|------|-------|------|--------|")
    for s in sorted(analysis["by_seat"]):
        d = analysis["by_seat"][s]
        ci = f"{d['ci95_low']:.3f}–{d['ci95_high']:.3f}"
        lines.append(
            f"| {s} | {d['wins']} | {d['decided']} | {d['win_rate']:.3f} | {ci} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    args = _parse_args()
    base_budgets: list[int] = args.num_sims_per_seat

    run_id = new_run_id()
    configure_logging(level=args.log_level, json_logs=args.json_logs, run_id=run_id)
    logger = structlog.get_logger()

    out_dir = _experiment_dir(args.output_dir, run_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    workers = args.workers if args.workers > 0 else os.cpu_count() or 1

    if args.rotate_seats and args.num_games % args.num_players != 0:
        logger.warning(
            "non_multiple_games",
            num_games=args.num_games,
            num_players=args.num_players,
            help="rotation is only fully balanced when num_games is a multiple of num_players",
        )

    logger.info(
        "experiment_start",
        run_id=run_id,
        output_dir=str(out_dir),
        num_players=args.num_players,
        num_games=args.num_games,
        num_sims_per_seat=base_budgets,
        rotate_seats=args.rotate_seats,
        evaluator=args.evaluator,
        workers=workers,
    )

    summaries: list[dict] = []
    metrics = RunMetrics()
    rollout_max_len = args.rollout_max_length if args.rollout_max_length > 0 else None

    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {}
        for gi in range(args.num_games):
            seat_budgets = seat_budgets_for_game(base_budgets, gi, args.rotate_seats)
            setup_json, deck_a_id, deck_b_id = _build_ismcts_setup_json(
                base_seed=args.seed,
                game_index=gi,
            )
            futures[
                executor.submit(
                    _run_one_game_standalone,
                    game_index=gi,
                    num_sims=seat_budgets,
                    uct_c=args.uct_c,
                    max_world_samples=args.max_world_samples,
                    final_policy_name=args.final_policy,
                    seed=args.seed,
                    shuffle_seed=args.shuffle_seed if args.shuffle_seed != 0 else args.seed + gi,
                    output_dir=str(out_dir),
                    setup_data_json=setup_json,
                    deck_a_id=deck_a_id,
                    deck_b_id=deck_b_id,
                    run_id=run_id,
                    log_level=args.worker_log_level,
                    json_logs=args.json_logs,
                    game_name=_GAME_NAME,
                    num_players=args.num_players,
                    rollout_count=args.rollout_count,
                    rollout_max_length=rollout_max_len,
                    max_rounds=args.max_rounds,
                    evaluator_name=args.evaluator,
                )
            ] = gi

        with tqdm(total=args.num_games, desc="Games", unit="game") as pbar:
            for future in as_completed(futures):
                gi = futures[future]
                try:
                    summary = future.result()
                    summaries.append(summary)
                    metrics.games_completed += 1
                    if summary.get("stopped_reason") == "round_cap":
                        metrics.record_game_truncated()
                    metrics.record_game_wall(summary["wall_time_sec"])
                    for wall_ms in summary.get("_move_latencies", []):
                        metrics.record_move_latency(wall_ms, "")
                    pbar.set_postfix_str(
                        f"g{summary['game_index']} "
                        f"d={summary['decision_count']} "
                        f"w={summary['winner']} "
                        f"{summary['wall_time_sec']:.0f}s"
                    )
                except GameRunFailedError as exc:
                    summaries.append(exc.game_summary)
                    metrics.games_failed += 1
                    pbar.set_postfix_str(f"g{gi} FAILED")
                except Exception:
                    logger.exception("worker_failed", game_index=gi)
                    metrics.games_failed += 1
                    metrics.worker_exceptions += 1
                    pbar.set_postfix_str(f"g{gi} FAILED")
                pbar.update(1)

    metrics_doc = metrics.to_jsonable()
    with (out_dir / "metrics.json").open("w", encoding="utf-8") as f:
        json.dump(metrics_doc, f, indent=2)
        f.write("\n")

    write_summaries(out_dir, summaries, run_id)

    analysis = analyze(summaries, n_players=args.num_players)
    with (out_dir / "analysis.json").open("w", encoding="utf-8") as f:
        json.dump(analysis, f, indent=2)
        f.write("\n")
    with (out_dir / "analysis.md").open("w", encoding="utf-8") as f:
        f.write(_render_analysis_md(analysis))

    config = {
        "run_id": run_id,
        "num_players": args.num_players,
        "num_games": args.num_games,
        "num_sims_per_seat": base_budgets,
        "rotate_seats": args.rotate_seats,
        "seed": args.seed,
        "shuffle_seed": args.shuffle_seed,
        "uct_c": args.uct_c,
        "max_world_samples": args.max_world_samples,
        "final_policy": args.final_policy,
        "evaluator": args.evaluator,
        "rollout_count": args.rollout_count,
        "rollout_max_length": args.rollout_max_length,
        "max_rounds": args.max_rounds,
        "workers": args.workers,
        "output_dir": str(args.output_dir),
        "seat_budgets_by_game": {
            gi: seat_budgets_for_game(base_budgets, gi, args.rotate_seats)
            for gi in range(args.num_games)
        },
    }
    with (out_dir / "experiment_config.json").open("w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
        f.write("\n")

    logger.info(
        "experiment_end",
        run_id=run_id,
        games_completed=metrics.games_completed,
        games_failed=metrics.games_failed,
        output_dir=str(out_dir),
    )
    print(f"Experiment complete. Results in {out_dir}")


if __name__ == "__main__":
    main()
