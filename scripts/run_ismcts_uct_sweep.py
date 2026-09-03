"""IS-MCTS UCT-sweep experiment: does the UCB1 constant (uct_c) shape outcomes?

Seats get a rotating ladder of UCB1 exploration constants (default
0.3/0.8/1.4/2.5; 1.4 is the engine default, 0.3/2.5 the extreme arms). The
ladder rotates across seats between games so seat order (seat 0 always moves
first) is deconfounded from uct strength. Every seat uses the same simulation
budget (``--num-sims``, default 200) with the ``random-c`` evaluator, so uct_c
is the only varying factor.

Each game records which seat had which uct (``uct_c_per_seat``), the seat-ordered
final VP (``final_vp_per_seat``), and full + recruited final-deck diversity
(``final_deck_metrics``). The run writes ``analysis.json`` / ``analysis.md``:
win rate per uct arm and per seat with Wilson 95% CIs, mean VP share / mean raw
VP / mean rank per arm, full + recruited deck-diversity mean±sd per arm, two
seeded within-game permutation trend tests (uct vs VP share, uct vs recruited
entropy), and a games-needed projection.

WARNING: pyrants engine clone costs ~10 ms per state. A 4-player game at 200
sims is on the order of minutes per game (the ``random-c`` evaluator is ~19x
faster than ``random-py``). ALWAYS run the 8-game pilot first to calibrate
wall-time and the decided fraction before the 240-game main run:

    just ismcts-uct-pilot
    just ismcts-uct
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
from scripts._sims_vs_wins import seat_budgets_for_game  # noqa: E402
from scripts._uct_sweep import analyze_uct, parse_uct_spec  # noqa: E402
from scripts.run_ismcts import (  # noqa: E402
    POLICY_CHOICES,
    GameRunFailedError,
    _build_ismcts_setup_json,
    _run_one_game_standalone,
    write_summaries,
)

DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "ismcts" / "experiments" / "uct_sweep"
_GAME_NAME = "python_pyrants_c"


def _experiment_dir(base: Path, run_id: str) -> Path:
    """Return the per-run directory, keyed by a UTC timestamp + run id."""
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return base / f"{ts}_{run_id}"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the IS-MCTS UCT-sweep experiment (rotating uct ladder)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--uct-per-seat",
        type=str,
        default="0.3,0.8,1.4,2.5",
        help="Comma-separated per-seat UCB1 constants (default: 0.3,0.8,1.4,2.5)",
    )
    parser.add_argument(
        "--num-players",
        type=int,
        default=4,
        help="Number of players; must equal --uct-per-seat length (default: 4)",
    )
    parser.add_argument("--num-sims", type=int, default=200,
                        help="Simulations per move for every seat (default: 200)")
    parser.add_argument("--num-games", type=int, default=240)
    rotation = parser.add_mutually_exclusive_group()
    rotation.add_argument(
        "--rotate-seats",
        dest="rotate_seats",
        action="store_true",
        default=True,
        help="Rotate the uct ladder across seats per game (default)",
    )
    rotation.add_argument(
        "--no-rotate-seats",
        dest="rotate_seats",
        action="store_false",
        help="Keep a fixed P1=first-uct … mapping (no rotation)",
    )
    parser.add_argument(
        "--evaluator",
        choices=["random-py", "random-c"],
        default="random-c",
        help="Rollout evaluator backend (default: random-c, ~19x faster)",
    )
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
    parser.add_argument(
        "--analyze-only",
        type=Path,
        nargs="+",
        default=None,
        help="Re-analyse existing run dir(s) without simulating; reads each "
             "dir's game_*/summary.json and writes analysis.json/md into the "
             "first dir. Enables merging an extension run with the original.",
    )

    args = parser.parse_args()
    if args.analyze_only:
        return args
    if args.num_players < 2 or args.num_players > 4:
        parser.error(f"--num-players must be 2–4, got {args.num_players}")
    try:
        args.uct_per_seat = parse_uct_spec(args.uct_per_seat, args.num_players)
    except ValueError as exc:
        parser.error(str(exc))
    if args.num_sims < 1:
        parser.error(f"--num-sims must be >= 1, got {args.num_sims}")
    return args


def _load_summaries_from_run_dir(run_dir: Path) -> list[dict]:
    summaries = []
    for summary_path in sorted(run_dir.glob("game_*/summary.json")):
        summaries.append(json.loads(summary_path.read_text(encoding="utf-8")))
    return summaries


def _render_analysis_md(analysis: dict) -> str:
    def fmt(v: float | None, spec: str = ".3f") -> str:
        return "-" if v is None else format(v, spec)

    lines = ["# UCT Sweep Analysis\n"]
    lines.append(
        f"- **Games:** {analysis['n_games']} "
        f"(decided {analysis['n_decided']}, ties {analysis['n_ties']}, "
        f"round_cap {analysis['n_round_cap']}, errors {analysis['n_errors']})"
    )
    lines.append(
        f"- **Arms (uct_c):** {', '.join(f'{a:g}' for a in analysis['arms'])}"
    )
    if analysis["low_effective_n"]:
        lines.append(
            f"- **WARNING: low effective N** — only {analysis['effective_n_frac']:.0%} "
            "of games were decided (below the 80% threshold)."
        )
    for key, label in (
        ("trend_vp_share", "Trend (uct → VP share)"),
        ("trend_entropy", "Trend (uct → recruited normalized entropy)"),
    ):
        t = analysis[key]
        lines.append(
            f"- **{label}:** p={t['p_value']} "
            f"(statistic {t['statistic']}, {t['n_permutations']} permutations, "
            f"{t['n_games_used']} games used)"
        )
    lines.append("")
    lines.append("## Win rate by uct arm\n")
    lines.append("| uct_c | wins | games | win% | 95% CI | mean VP share | mean VP | mean rank |")
    lines.append("|-------|------|-------|------|--------|---------------|---------|-----------|")
    for arm in analysis["arms"]:
        d = analysis["by_arm"][arm]
        ci = f"{d['ci95_low']:.3f}–{d['ci95_high']:.3f}"
        share = fmt(d["mean_vp_share"], ".3f")
        vp = fmt(d["mean_vp"], ".2f")
        rank = fmt(d["mean_rank"], ".2f")
        lines.append(
            f"| {arm:g} | {d['wins']} | {d['decided']} | {d['win_rate']:.3f} | "
            f"{ci} | {share} | {vp} | {rank} |"
        )
    lines.append("")
    lines.append("## Win rate by seat (confound check)\n")
    lines.append("| seat | wins | games | win% | 95% CI |")
    lines.append("|------|------|-------|------|--------|")
    for s in sorted(analysis["by_seat"]):
        d = analysis["by_seat"][s]
        ci = f"{d['ci95_low']:.3f}–{d['ci95_high']:.3f}"
        lines.append(f"| {s} | {d['wins']} | {d['decided']} | {d['win_rate']:.3f} | {ci} |")

    for mset_key, title in (("deck_full", "full"), ("deck_recruited", "recruited")):
        lines.append("")
        lines.append(f"## Deck diversity ({title}) — mean ± sd per arm\n")
        lines.append(
            "| uct_c | unique_count | deck_size | unique_ratio | shannon_entropy | "
            "normalized_entropy | simpson |"
        )
        lines.append(
            "|-------|--------------|-----------|--------------|-----------------|"
            "---------------------|---------|"
        )
        for arm in analysis["arms"]:
            agg = analysis["by_arm"][arm][mset_key]
            def cell(key, agg=agg):
                m, sd = agg[key]["mean"], agg[key]["sd"]
                return "-" if m is None else f"{m:.3f}±{sd:.3f}"

            lines.append(
                f"| {arm:g} | {cell('unique_count')} | {cell('deck_size')} | "
                f"{cell('unique_ratio')} | {cell('shannon_entropy')} | "
                f"{cell('normalized_entropy')} | {cell('simpson')} |"
            )

    lines.append("")
    lines.append("## Games needed\n")
    g = analysis["games_needed"]
    lines.append(f"- **Achieved decided N:** {g['achieved_n_decided']}")
    lines.append(f"- **Decided fraction:** {g['decided_fraction']:.0%}")
    for label, req_key, proj_key in (
        ("±10pp", "required_10pp", "projected_total_games_10pp"),
        ("±8pp", "required_8pp", "projected_total_games_8pp"),
        ("±5pp", "required_5pp", "projected_total_games_5pp"),
    ):
        proj = g[proj_key]
        proj_str = "-" if proj is None else str(proj)
        lines.append(
            f"- **Required decided N for {label}:** {g[req_key]} "
            f"(projected total games: {proj_str})"
        )
    return "\n".join(lines) + "\n"


def _analyze_only(run_dirs: list[Path]) -> None:
    summaries: list[dict] = []
    for d in run_dirs:
        loaded = _load_summaries_from_run_dir(d)
        if not loaded:
            raise SystemExit(f"no game_*/summary.json files in {d}")
        summaries.extend(loaded)

    n_players = summaries[0].get("num_players", 4)
    analysis = analyze_uct(summaries, n_players=n_players)

    out_dir = run_dirs[0]
    with (out_dir / "analysis.json").open("w", encoding="utf-8") as f:
        json.dump(analysis, f, indent=2)
        f.write("\n")
    with (out_dir / "analysis.md").open("w", encoding="utf-8") as f:
        f.write(_render_analysis_md(analysis))
    print(f"Merged {len(summaries)} summaries from {len(run_dirs)} run dir(s) -> {out_dir}")


def main() -> None:
    args = _parse_args()
    if args.analyze_only:
        _analyze_only(args.analyze_only)
        return

    base_ladder: list[float] = args.uct_per_seat

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
        num_sims=args.num_sims,
        uct_per_seat=base_ladder,
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
            seat_uct = seat_budgets_for_game(base_ladder, gi, args.rotate_seats)
            setup_json, deck_a_id, deck_b_id = _build_ismcts_setup_json(
                base_seed=args.seed,
                game_index=gi,
            )
            futures[
                executor.submit(
                    _run_one_game_standalone,
                    game_index=gi,
                    num_sims=args.num_sims,
                    uct_c=seat_uct,
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

    analysis = analyze_uct(summaries, n_players=args.num_players)
    with (out_dir / "analysis.json").open("w", encoding="utf-8") as f:
        json.dump(analysis, f, indent=2)
        f.write("\n")
    with (out_dir / "analysis.md").open("w", encoding="utf-8") as f:
        f.write(_render_analysis_md(analysis))

    config = {
        "run_id": run_id,
        "num_players": args.num_players,
        "num_games": args.num_games,
        "num_sims": args.num_sims,
        "uct_per_seat": base_ladder,
        "rotate_seats": args.rotate_seats,
        "seed": args.seed,
        "shuffle_seed": args.shuffle_seed,
        "max_world_samples": args.max_world_samples,
        "final_policy": args.final_policy,
        "evaluator": args.evaluator,
        "rollout_count": args.rollout_count,
        "rollout_max_length": args.rollout_max_length,
        "max_rounds": args.max_rounds,
        "workers": args.workers,
        "output_dir": str(args.output_dir),
        "uct_ladder_by_game": {
            gi: seat_budgets_for_game(base_ladder, gi, args.rotate_seats)
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
