"""Run IS-MCTS (Information Set Monte Carlo Tree Search) against python_pyrants.

Drives the stock ``open_spiel.python.algorithms.ismcts.ISMCTSBot`` against the
existing ``python_pyrants`` OpenSpiel wrapper, capturing per-game decision traces
and a cross-run summary.

WARNING: pyrants engine clone costs ~10 ms per state.  With --num-sims 200 and
a ~4000-decision game, that is roughly 200 × 4000 × 10 ms ≈ 2.2 hours per game
on a single core, plus the actual game-tree exploration.  For the first run use
``--num-sims 50 --num-games 2`` to prove the pipeline before scaling up.

Usage:
    python -m scripts.run_ismcts --num-sims 50 --num-games 2 --seed 42
    just ismcts num_sims=50 num_games=2
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from random import Random

import numpy as np
import pyspiel
import structlog
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import openspiel_pyrants  # noqa: E402, F401 — registers python_pyrants
from game_setup.market_setup import (  # noqa: E402
    combine_two_deck_market_setup,
    discover_full_deck_profiles,
    pick_random_pair,
)
from scripts._obs import (  # noqa: E402
    RunMetrics,
    bind_worker_context,
    compute_percentiles,
    configure_logging,
    new_run_id,
)
from scripts._replay_payload import (  # noqa: E402
    build_replay_payload,
    compute_final_scores,
    resolve_winner_id,
)

DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "ismcts"
_BASE_SETUP_PATH = ROOT / "data" / "decks" / "base_setup.json"
_DECKS_DIR = ROOT / "data" / "decks"

POLICY_CHOICES = {
    "visited": "NORMALIZED_VISITED_COUNT",
    "max_value": "MAX_VALUE",
    "max_visit": "MAX_VISIT_COUNT",
}

_BASE_SETUP_CACHE: dict | None = None


def _base_setup() -> dict:
    global _BASE_SETUP_CACHE
    if _BASE_SETUP_CACHE is None:
        _BASE_SETUP_CACHE = json.loads(_BASE_SETUP_PATH.read_text(encoding="utf-8"))
    return _BASE_SETUP_CACHE


def _build_ismcts_setup_json(
    *,
    base_seed: int,
    game_index: int,
) -> tuple[str, str, str]:
    """Return (setup_data_json, deck_a_id, deck_b_id) for a given IS-MCTS game."""
    logger = structlog.get_logger()
    profiles = discover_full_deck_profiles(_DECKS_DIR)
    if len(profiles) < 2:
        logger.warning(
            "few_deck_profiles",
            profile_count=len(profiles),
            help="IS-MCTS will fall back to base_setup.json (10×priestess_of_lolth); "
            "games may end prematurely after 4 recruits.",
        )
        return "", "", ""

    pair_rng = Random(base_seed + game_index)
    deck_a, deck_b = pick_random_pair(profiles, pair_rng)
    market_setup = combine_two_deck_market_setup(_base_setup(), deck_a, deck_b)
    setup_json = json.dumps(market_setup.to_setup_data())
    return setup_json, deck_a.deck_id, deck_b.deck_id


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run IS-MCTS against python_pyrants",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--num-sims", type=int, default=200)
    parser.add_argument("--uct-c", type=float, default=1.4)
    parser.add_argument(
        "--max-world-samples",
        type=int,
        default=-1,
        help="Max determinizations to pool before reusing (default: -1 = unlimited, "
        "fresh determinization every iteration). A positive value opts into capped-pool reuse.",
    )
    parser.add_argument("--final-policy", choices=list(POLICY_CHOICES), default="visited")
    parser.add_argument("--num-games", type=int, default=4)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--num-players", type=int, default=2,
                        help="Number of players (2–4, default: 2)")
    parser.add_argument("--game", type=str, default="python_pyrants_c",
                        choices=["python_pyrants_c"],
                        help="OpenSpiel game name (default: python_pyrants_c)")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--shuffle-seed", type=int, default=0)
    parser.add_argument("--workers", type=int, default=0,
                        help="Number of parallel games (0 = auto = CPU count)")
    parser.add_argument("--no-plots", action="store_true")
    parser.add_argument("--log-level", type=str, default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="Log level for the main process (default: INFO)")
    parser.add_argument("--json-logs", action="store_true",
                        help="Emit structured JSON log lines")
    parser.add_argument("--worker-log-level", type=str, default="WARNING",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="Log level for worker processes (default: WARNING)")
    parser.add_argument("--rollout-count", type=int, default=1,
                        help="Random rollouts per leaf node (default: 1)")
    parser.add_argument("--rollout-max-length", type=int, default=0,
                        help="Max steps per rollout (0 = unbounded, roll to terminal)")
    parser.add_argument("--max-rounds", type=int, default=0,
                        help="Cap engine round_number; 0 = unlimited. "
                             "When the cap is hit the game is recorded with "
                             "stopped_reason='round_cap'.")
    args = parser.parse_args()
    if args.num_players < 2 or args.num_players > 4:
        parser.error(f"--num-players must be 2–4, got {args.num_players}")
    return args


def _load_game_or_die(name: str, params: dict) -> pyspiel.Game:
    """Load a pyspiel game, with a clear error if the C DLL is missing."""
    try:
        return pyspiel.load_game(name, params)
    except (pyspiel.GameNotFoundError, ValueError) as e:
        if name == "python_pyrants_c":
            dll = ROOT / "engine_c" / "engine_c.dll"
            if not dll.exists():
                raise RuntimeError(
                    f"C engine DLL not found at {dll} — run `just build-c` to build it"
                ) from e
        raise


def _resolve_policy(name: str):
    from open_spiel.python.algorithms.ismcts import ISMCTSFinalPolicyType

    return getattr(ISMCTSFinalPolicyType, POLICY_CHOICES[name])


def _summary_csv_path(out_dir: Path) -> Path:
    return out_dir / "summary.csv"


def _summary_md_path(out_dir: Path) -> Path:
    return out_dir / "summary.md"


def _game_dir(out_dir: Path, game_index: int) -> Path:
    return out_dir / f"game_{game_index:04d}"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _legal_moves_strings(state, action_ids: list[int]) -> list[str]:
    result: list[str] = []
    for aid in action_ids:
        try:
            move = state.decode_action(aid)
            result.append(state.move_to_str(move))
        except (IndexError, Exception):
            result.append(f"<action_{aid}>")
    return result


def run_one_game(
    game: pyspiel.Game,
    game_index: int,
    num_sims: int,
    uct_c: float,
    max_world_samples: int,
    final_policy_type,
    final_policy_name: str,
    seed: int,
    shuffle_seed: int,
    out_dir: Path,
    deck_a_id: str = "",
    deck_b_id: str = "",
    show_progress: bool = False,
    run_id: str = "",
    metrics: RunMetrics | None = None,
    *,
    rollout_count: int = 1,
    rollout_max_length: int | None = None,
    max_rounds: int = 0,
    setup_data_json: str = "",
    num_players: int = 2,
) -> dict:
    logger = structlog.get_logger().bind(
        game_index=game_index,
        shuffle_seed=shuffle_seed,
    )
    game_out = _game_dir(out_dir, game_index)
    game_out.mkdir(parents=True, exist_ok=True)

    from open_spiel.python.algorithms.ismcts import ISMCTSBot
    from open_spiel.python.algorithms.mcts import RandomRolloutEvaluator

    bots = []
    for i in range(num_players):
        rng_i = np.random.RandomState(seed + game_index * num_players + i)
        bots.append(
            ISMCTSBot(
                game=game,
                evaluator=RandomRolloutEvaluator(n_rollouts=rollout_count, max_length=rollout_max_length, random_state=rng_i),
                uct_c=uct_c,
                max_simulations=num_sims,
                max_world_samples=max_world_samples,
                random_state=rng_i,
                final_policy_type=final_policy_type,
            )
        )

    state = game.new_initial_state()
    state.apply_action(shuffle_seed)

    setup_data_sha256 = _sha256(setup_data_json) if setup_data_json else ""
    initial_state_sha256 = _sha256(state.information_state_string(0))

    decision_count = 0
    decisions: list[dict] = []
    replay_log: list[dict] = []
    move_latencies: list[float] = []
    wall_start = time.perf_counter()

    inner_bar: tqdm | None = None
    if show_progress:
        inner_bar = tqdm(
            desc=f"  Game {game_index}",
            unit="move",
            bar_format="{desc}: {n_fmt} moves [{elapsed}] {postfix}",
            leave=False,
        )
        inner_bar.set_postfix_str("initialising...")
        inner_bar.update(0)

    while not state.is_terminal():
        if max_rounds > 0 and state._engine.round_number > max_rounds:
            break
        cp = state.current_player()
        if cp < 0 or cp >= num_players:
            break

        bot = bots[cp]
        legal_ids = state.legal_actions()
        legal_moves = _legal_moves_strings(state, legal_ids)

        if inner_bar is not None:
            inner_bar.set_postfix_str("simulating...")
            inner_bar.refresh()

        t0 = time.perf_counter()
        policy, chosen = bot.step_with_policy(state)
        wall_ms = (time.perf_counter() - t0) * 1000.0

        chosen_move_obj = state.decode_action(int(chosen))
        chosen_move_str = state.move_to_str(chosen_move_obj)
        phase = state._engine.phase.value
        round_number = state._engine.round_number
        player_id = state._game.get_player_ids()[cp]

        logger.debug(
            "move_decided",
            round=state._engine.round_number,
            player=player_id,
            phase=phase,
            action=chosen_move_str,
            wall_ms=round(wall_ms, 3),
        )

        if metrics is not None:
            metrics.record_move_latency(wall_ms, phase)
        move_latencies.append(round(wall_ms, 3))

        action_probs: dict[int, float] = {}
        for aid, prob in policy:
            action_probs[int(aid)] = float(prob)

        decisions.append({
            "run_id": run_id,
            "node": decision_count,
            "round": state._engine.round_number,
            "phase": state._engine.phase.value,
            "current_player": player_id,
            "info_state_sha256": _sha256(state.information_state_string(cp)),
            "legal_action_ids": [int(a) for a in legal_ids],
            "legal_moves": legal_moves,
            "policy": action_probs,
            "visit_counts": {int(chosen): 1},
            "chosen_action_id": int(chosen),
            "chosen_move": chosen_move_str,
            "wall_time_ms": round(wall_ms, 3),
            "sims_requested": num_sims,
        })

        state.apply_action(int(chosen))

        replay_log.append({
            "run_id": run_id,
            "step_index": decision_count,
            "player_id": player_id,
            "round_number": round_number,
            "phase": phase,
            "prompts": [],
            "move_type": chosen_move_obj.move_type,
            "label": chosen_move_str,
            "payload": state.move_to_payload(chosen_move_obj),
        })
        decision_count += 1
        if inner_bar is not None:
            sims_per_sec_rate = num_sims / (wall_ms / 1000.0) if wall_ms > 0 else 0.0
            inner_bar.set_postfix_str(
                f"r{state._engine.round_number} {state._engine.phase.value} "
                f"sims/s={sims_per_sec_rate:.0f}"
            )
            inner_bar.update(1)

    if inner_bar is not None:
        inner_bar.set_postfix_str("")
        inner_bar.close()

    wall_sec = time.perf_counter() - wall_start

    stopped_reason: str = (
        "terminal" if state.is_terminal()
        else ("round_cap" if max_rounds > 0 else "unknown")
    )

    ret = state.returns()
    winner = None
    if num_players == 2:
        if abs(ret[0] - ret[1]) > 1e-6:
            winner = 0 if ret[0] > ret[1] else 1
    else:
        max_ret = max(ret)
        best_indices = [i for i, v in enumerate(ret) if abs(v - max_ret) <= 1e-6]
        if len(best_indices) == 1:
            winner = best_indices[0]

    sims_per_sec = (num_sims * decision_count) / wall_sec if wall_sec > 0 else 0.0

    move_latency_ms: dict = {"count": 0, "mean": 0.0, "max": 0.0}
    if move_latencies:
        move_latency_ms["count"] = len(move_latencies)
        move_latency_ms["mean"] = round(sum(move_latencies) / len(move_latencies), 3)
        move_latency_ms["max"] = round(max(move_latencies), 3)
        move_latency_ms.update(compute_percentiles(move_latencies))

    moves_per_sec = decision_count / wall_sec if wall_sec > 0 else 0.0

    phase_breakdown: dict[str, dict] = {}
    info_states: set[str] = set()
    entropies: list[float] = []
    chosen_probs: list[float] = []
    for d in decisions:
        phase = d["phase"]
        if phase not in phase_breakdown:
            phase_breakdown[phase] = {"decisions": 0}
        phase_breakdown[phase]["decisions"] += 1

        is_hash: str = d.get("info_state_sha256", "")
        if is_hash:
            info_states.add(is_hash)

        policy: dict = d.get("policy", {})
        if policy:
            pos = [p for p in policy.values() if p > 0]
            if pos and abs(sum(pos) - 1.0) < 0.01:
                entropies.append(round(-sum(p * math.log(p) for p in pos), 6))

        chosen_aid = d.get("chosen_action_id")
        if chosen_aid is not None and policy and chosen_aid in policy:
            chosen_probs.append(policy[chosen_aid])

    total_dec = decision_count or 1
    for p in phase_breakdown.values():
        p["pct"] = round(p["decisions"] / total_dec, 3)

    move_type_counts: dict[str, int] = {}
    for step in replay_log:
        mt: str = step.get("move_type", "")
        if mt:
            move_type_counts[mt] = move_type_counts.get(mt, 0) + 1

    top_move_types = sorted(move_type_counts.items(), key=lambda kv: kv[1], reverse=True)[:5]

    unique_info_states = len(info_states)
    info_state_repeat_rate = round(1.0 - unique_info_states / total_dec, 3) if total_dec else 0.0

    policy_entropy_mean = round(sum(entropies) / len(entropies), 6) if entropies else 0.0
    policy_entropy_max = round(max(entropies), 6) if entropies else 0.0

    chosen_action_prob_mean = round(sum(chosen_probs) / len(chosen_probs), 6) if chosen_probs else 0.0
    chosen_action_prob_pct = compute_percentiles(chosen_probs) if chosen_probs else {}
    chosen_action_prob_p50 = chosen_action_prob_pct.get("p50", 0.0)
    chosen_action_prob_p90 = chosen_action_prob_pct.get("p90", 0.0)

    final_phase = state._engine.phase.value
    final_round_num = state._engine.round_number
    final_scores = compute_final_scores(state)

    if stopped_reason == "round_cap":
        outcome = "truncated"
    elif winner is None:
        outcome = "tie"
    else:
        outcome = f"p{winner}_win"

    logger.info(
        "game_end",
        decision_count=decision_count,
        wall_time_sec=round(wall_sec, 3),
        sims_per_sec_avg=round(sims_per_sec, 1),
        winner=winner,
        num_players=num_players,
        stopped_reason=stopped_reason,
    )

    game_summary = {
        "run_id": run_id,
        "game_index": game_index,
        "shuffle_seed": shuffle_seed,
        "deck_a_id": deck_a_id,
        "deck_b_id": deck_b_id,
        "num_players": num_players,
        "num_sims_per_move": num_sims,
        "uct_c": uct_c,
        "rollout_count": rollout_count,
        "rollout_max_length": rollout_max_length,
        "policy_type": final_policy_name,
        "decision_count": decision_count,
        "wall_time_sec": round(wall_sec, 3),
        "sims_per_sec_avg": round(sims_per_sec, 1),
        "moves_per_sec_avg": round(moves_per_sec, 2),
        "returns": [round(float(ret[i]), 3) for i in range(num_players)],
        "winner": winner,
        "outcome": outcome,
        "stopped_reason": stopped_reason,
        "max_rounds": max_rounds,
        "move_latency_ms": move_latency_ms,
        "phase_breakdown": phase_breakdown,
        "move_type_counts": move_type_counts,
        "top_move_types": top_move_types,
        "unique_info_states": unique_info_states,
        "info_state_repeat_rate": info_state_repeat_rate,
        "policy_entropy_mean": policy_entropy_mean,
        "policy_entropy_max": policy_entropy_max,
        "chosen_action_prob_mean": chosen_action_prob_mean,
        "chosen_action_prob_p50": chosen_action_prob_p50,
        "chosen_action_prob_p90": chosen_action_prob_p90,
        "final_round": final_round_num,
        "final_phase": final_phase,
        "final_scores_per_player": final_scores,
        "setup_data_sha256": setup_data_sha256,
        "initial_state_sha256": initial_state_sha256,
        "_move_latencies": move_latencies,
    }

    player_ids = list(state._game.get_player_ids())
    winner_id = resolve_winner_id(state, winner, num_players)

    replay_payload = build_replay_payload(
        run_id=run_id,
        stopped_reason=stopped_reason,
        max_rounds=max_rounds,
        step_count=decision_count,
        is_terminal=state.is_terminal(),
        winner_id=winner_id,
        final_scores=final_scores,
        replay_log=replay_log,
        shuffle_seed=shuffle_seed,
        deck_a_id=deck_a_id,
        deck_b_id=deck_b_id,
        board_path=str(ROOT / "data" / "boards" / "tyrants_of_the_underdark.json"),
        card_path=str(ROOT / "data" / "cards"),
        setup_path=str(ROOT / "data" / "decks" / "base_setup.json"),
        player_ids=player_ids,
        final_round_num=final_round_num,
        final_phase=final_phase,
    )

    with (game_out / "replay.json").open("w", encoding="utf-8") as f:
        json.dump(replay_payload, f, indent=2)
        f.write("\n")

    with (game_out / "decisions.jsonl").open("w", encoding="utf-8") as f:
        for d in decisions:
            f.write(json.dumps(d) + "\n")

    with (game_out / "summary.json").open("w", encoding="utf-8") as f:
        summary_out = {k: v for k, v in game_summary.items() if not k.startswith("_")}
        json.dump(summary_out, f, indent=2)
        f.write("\n")

    return game_summary


def write_summaries(out_dir: Path, summaries: list[dict], run_id: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    if not summaries:
        return

    csv_path = _summary_csv_path(out_dir)
    fieldnames = [
        "run_id", "game_index", "shuffle_seed", "deck_a_id", "deck_b_id",
        "num_sims_per_move", "uct_c", "rollout_count", "rollout_max_length",
        "decision_count", "wall_time_sec", "sims_per_sec_avg", "moves_per_sec_avg",
        "winner", "outcome", "stopped_reason", "max_rounds",
        "policy_entropy_mean", "chosen_action_prob_mean",
        "unique_info_states", "info_state_repeat_rate",
        "final_round", "final_phase",
        "setup_data_sha256", "initial_state_sha256",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore", restval="")
        writer.writeheader()
        for s in summaries:
            writer.writerow(s)

    md_path = _summary_md_path(out_dir)
    total_wall = sum(s["wall_time_sec"] for s in summaries)
    total_decisions = sum(s["decision_count"] for s in summaries)
    total_sims = sum(s["num_sims_per_move"] * s["decision_count"] for s in summaries)
    total_sims_per_sec = total_sims / total_wall if total_wall > 0 else 0.0
    wins_by_player = {}
    for s in summaries:
        w = s.get("winner")
        if w is not None:
            wins_by_player[w] = wins_by_player.get(w, 0) + 1
    win_split_parts = "/".join(str(wins_by_player.get(i, 0)) for i in range(max(wins_by_player.keys() or [1]) + 1))

    with md_path.open("w", encoding="utf-8") as f:
        f.write("# IS-MCTS Run Summary\n\n")
        f.write(f"- **Run ID:** {run_id}\n")
        f.write(f"- **Games:** {len(summaries)}\n")
        f.write(f"- **Total wall time:** {total_wall:.1f}s\n")
        f.write(f"- **Total decisions:** {total_decisions}\n")
        f.write(f"- **Overall sims/sec:** {total_sims_per_sec:.1f}\n")
        f.write(f"- **Win split:** {win_split_parts}\n")
        f.write(f"- **Mean decisions/game:** {total_decisions / len(summaries):.0f}\n")
        cols = "| game | seed | deck_a | deck_b | sims | uct_c | decisions | wall_s | moves/s | outcome | entropy | info_states | repeat_rate |"
        f.write(f"\n{cols}\n")
        f.write("|------|------|--------|--------|------|-------|-----------|--------|--------|---------|--------|-------------|-------------|\n")
        for s in summaries:
            w = s.get("winner")
            outcome_str = s.get("outcome", f"p{w}_win" if w is not None else "tie")
            entropy_str = f"{s.get('policy_entropy_mean', 0):.2f}" if s.get("policy_entropy_mean") is not None else "-"
            info_states_str = str(s.get("unique_info_states", "-"))
            repeat_str = f"{s.get('info_state_repeat_rate', 0):.3f}" if s.get("info_state_repeat_rate") is not None else "-"
            f.write(
                f"| {s['game_index']} | {s['shuffle_seed']} "
                f"| {s.get('deck_a_id', '')} | {s.get('deck_b_id', '')} "
                f"| {s['num_sims_per_move']} "
                f"| {s['uct_c']} "
                f"| {s['decision_count']} "
                f"| {s['wall_time_sec']:.1f} | {s.get('moves_per_sec_avg', 0):.2f} "
                f"| {outcome_str} "
                f"| {entropy_str} "
                f"| {info_states_str} "
                f"| {repeat_str} |\n"
            )

    print(f"Wrote {csv_path}")
    print(f"Wrote {md_path}")


def _log_game_done(index: int, total: int, summary: dict, t0_start: float) -> None:
    elapsed = time.perf_counter() - t0_start
    sims_done = summary["num_sims_per_move"] * summary["decision_count"]
    rate = sims_done / elapsed if elapsed > 0 else 0
    tqdm.write(
        f"Game {index}/{total}: decisions={summary['decision_count']} "
        f"winner={summary['winner']} "
        f"wall={elapsed:.1f}s sims/s={rate:.0f}"
    )


def _run_one_game_standalone(
    game_index: int,
    num_sims: int,
    uct_c: float,
    max_world_samples: int,
    final_policy_name: str,
    seed: int,
    shuffle_seed: int,
    output_dir: str,
    setup_data_json: str = "",
    deck_a_id: str = "",
    deck_b_id: str = "",
    *,
    run_id: str = "",
    log_level: str = "WARNING",
    json_logs: bool = False,
    game_name: str = "python_pyrants_c",
    num_players: int = 2,
    rollout_count: int = 1,
    rollout_max_length: int | None = None,
    max_rounds: int = 0,
) -> dict:
    """Load game and run one game in a worker process.

    ``pyspiel.Game`` is not picklable, so each worker loads the game
    independently.
    """
    configure_logging(level=log_level, json_logs=json_logs, run_id=run_id)
    bind_worker_context(game_index=game_index, worker_pid=os.getpid())

    try:
        load_params: dict[str, str] = {"num_players": str(num_players)}
        if setup_data_json:
            load_params["setup_data_json"] = setup_data_json
        game = _load_game_or_die(game_name, load_params)
        final_policy_type = _resolve_policy(final_policy_name)
        out_path = Path(output_dir)

        return run_one_game(
            game=game,
            game_index=game_index,
            num_sims=num_sims,
            uct_c=uct_c,
            max_world_samples=max_world_samples,
            final_policy_type=final_policy_type,
            final_policy_name=final_policy_name,
            seed=seed,
            shuffle_seed=shuffle_seed,
            out_dir=out_path,
            deck_a_id=deck_a_id,
            deck_b_id=deck_b_id,
            run_id=run_id,
            rollout_count=rollout_count,
            rollout_max_length=rollout_max_length,
            max_rounds=max_rounds,
            setup_data_json=setup_data_json,
            num_players=num_players,
        )
    except Exception:
        logger = structlog.get_logger()
        logger.exception("worker_game_failed", game_index=game_index)
        failures_path = Path(output_dir) / "failures.jsonl"
        with failures_path.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps({
                    "run_id": run_id,
                    "game_index": game_index,
                    "worker_pid": os.getpid(),
                    "error": traceback.format_exc(),
                })
                + "\n"
            )
        raise


def main() -> None:
    args = _parse_args()

    run_id = new_run_id()
    configure_logging(level=args.log_level, json_logs=args.json_logs, run_id=run_id)
    logger = structlog.get_logger()

    workers = args.workers if args.workers > 0 else os.cpu_count() or 1

    logger.info(
        "run_start",
        game=args.game,
        num_players=args.num_players,
        num_sims=args.num_sims,
        uct_c=args.uct_c,
        policy=args.final_policy,
        num_games=args.num_games,
        seed=args.seed,
        workers=workers,
        output_dir=str(args.output_dir),
        log_level=args.log_level,
        rollout_count=args.rollout_count,
        rollout_max_length=args.rollout_max_length,
    )

    summaries: list[dict] = []
    metrics = RunMetrics()
    rollout_max_len = args.rollout_max_length if args.rollout_max_length > 0 else None

    if workers == 1:
        policy_type = _resolve_policy(args.final_policy)

        for gi in tqdm(range(args.num_games), desc="Games", unit="game"):
            setup_json, deck_a_id, deck_b_id = _build_ismcts_setup_json(
                base_seed=args.seed,
                game_index=gi,
            )
            shuffle_seed = args.shuffle_seed if args.shuffle_seed != 0 else args.seed + gi

            load_params: dict[str, str] = {"num_players": str(args.num_players)}
            if setup_json:
                load_params["setup_data_json"] = setup_json
            game = _load_game_or_die(args.game, load_params)

            t0 = time.perf_counter()
            summary = run_one_game(
                game=game,
                game_index=gi,
                num_sims=args.num_sims,
                uct_c=args.uct_c,
                max_world_samples=args.max_world_samples,
                final_policy_type=policy_type,
                final_policy_name=args.final_policy,
                seed=args.seed,
                shuffle_seed=shuffle_seed,
                out_dir=args.output_dir,
                deck_a_id=deck_a_id,
                deck_b_id=deck_b_id,
                show_progress=True,
                run_id=run_id,
                metrics=metrics,
                rollout_count=args.rollout_count,
                rollout_max_length=rollout_max_len,
                max_rounds=args.max_rounds,
                setup_data_json=setup_json,
                num_players=args.num_players,
            )
            summaries.append(summary)
            metrics.games_completed += 1
            if summary.get("stopped_reason") == "round_cap":
                metrics.record_game_truncated()
            metrics.record_game_wall(summary["wall_time_sec"])
            _log_game_done(gi + 1, args.num_games, summary, t0)
    else:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = {}
            for gi in range(args.num_games):
                setup_json, deck_a_id, deck_b_id = _build_ismcts_setup_json(
                    base_seed=args.seed,
                    game_index=gi,
                )
                futures[
                    executor.submit(
                        _run_one_game_standalone,
                        game_index=gi,
                        num_sims=args.num_sims,
                        uct_c=args.uct_c,
                        max_world_samples=args.max_world_samples,
                        final_policy_name=args.final_policy,
                        seed=args.seed,
                        shuffle_seed=args.shuffle_seed if args.shuffle_seed != 0 else args.seed + gi,
                        output_dir=str(args.output_dir),
                        setup_data_json=setup_json,
                        deck_a_id=deck_a_id,
                        deck_b_id=deck_b_id,
                        run_id=run_id,
                        log_level=args.worker_log_level,
                        json_logs=args.json_logs,
                        game_name=args.game,
                        num_players=args.num_players,
                        rollout_count=args.rollout_count,
                        rollout_max_length=rollout_max_len,
                        max_rounds=args.max_rounds,
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
                            phase = ""  # phase not available in cross-process summary
                            metrics.record_move_latency(wall_ms, phase)
                        pbar.set_postfix_str(
                            f"g{summary['game_index']} "
                            f"d={summary['decision_count']} "
                            f"w={summary['winner']} "
                            f"{summary['wall_time_sec']:.0f}s"
                        )
                    except Exception:
                        logger.exception("worker_failed", game_index=gi)
                        metrics.games_failed += 1
                        metrics.worker_exceptions += 1
                        pbar.set_postfix_str(f"g{gi} FAILED")
                    pbar.update(1)

    metrics_doc = metrics.to_jsonable()

    logger.info(
        "run_end",
        games_completed=metrics.games_completed,
        games_failed=metrics.games_failed,
        moves_total=metrics.moves_total,
        sims_per_sec_avg_overall=metrics_doc["latency"]["sims_per_sec_avg_overall"],
    )

    metrics_path = args.output_dir / "metrics.json"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with metrics_path.open("w", encoding="utf-8") as f:
        json.dump(metrics_doc, f, indent=2)
        f.write("\n")
    print(f"Wrote {metrics_path}")

    write_summaries(args.output_dir, summaries, run_id)


if __name__ == "__main__":
    main()
