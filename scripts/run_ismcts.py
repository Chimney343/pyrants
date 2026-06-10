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
import sys
import time
from pathlib import Path

import numpy as np
import pyspiel

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import openspiel_pyrants  # noqa: E402, F401 — registers python_pyrants
from openspiel_pyrants.action_encoding import action_to_move  # noqa: E402

DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "ismcts"

POLICY_CHOICES = {
    "visited": "NORMALIZED_VISITED_COUNT",
    "max_value": "MAX_VALUE",
    "max_visit": "MAX_VISIT_COUNT",
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run IS-MCTS against python_pyrants",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--num-sims", type=int, default=200)
    parser.add_argument("--uct-c", type=float, default=1.4)
    parser.add_argument("--max-world-samples", type=int, default=1000)
    parser.add_argument("--final-policy", choices=list(POLICY_CHOICES), default="visited")
    parser.add_argument("--num-games", type=int, default=4)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--shuffle-seed", type=int, default=0)
    parser.add_argument("--no-plots", action="store_true")
    return parser.parse_args()


def _resolve_policy(name: str):
    from open_spiel.python.algorithms.ismcts import ISMCTSFinalPolicyType

    return getattr(ISMCTSFinalPolicyType, POLICY_CHOICES[name])


def _summary_csv_path(out_dir: Path) -> Path:
    return out_dir / "summary.csv"


def _summary_md_path(out_dir: Path) -> Path:
    return out_dir / "summary.md"


def _game_dir(out_dir: Path, game_index: int) -> Path:
    return out_dir / f"game_{game_index:04d}"


def _move_to_payload(move) -> dict[str, object]:
    return move.model_dump(mode="json")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _legal_moves_strings(engine_state, action_ids: list[int]) -> list[str]:
    result: list[str] = []
    for aid in action_ids:
        try:
            move = action_to_move(engine_state, aid)
            result.append(str(move))
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
) -> dict:
    game_out = _game_dir(out_dir, game_index)
    game_out.mkdir(parents=True, exist_ok=True)

    rng0 = np.random.RandomState(seed + game_index * 2)
    rng1 = np.random.RandomState(seed + game_index * 2 + 1)

    from open_spiel.python.algorithms.ismcts import ISMCTSBot
    from open_spiel.python.algorithms.mcts import RandomRolloutEvaluator

    bots = [
        ISMCTSBot(
            game=game,
            evaluator=RandomRolloutEvaluator(n_rollouts=1, random_state=rng0),
            uct_c=uct_c,
            max_simulations=num_sims,
            max_world_samples=max_world_samples,
            random_state=rng0,
            final_policy_type=final_policy_type,
        ),
        ISMCTSBot(
            game=game,
            evaluator=RandomRolloutEvaluator(n_rollouts=1, random_state=rng1),
            uct_c=uct_c,
            max_simulations=num_sims,
            max_world_samples=max_world_samples,
            random_state=rng1,
            final_policy_type=final_policy_type,
        ),
    ]

    state = game.new_initial_state()
    state.apply_action(shuffle_seed)

    decision_count = 0
    decisions: list[dict] = []
    replay_log: list[dict] = []
    wall_start = time.perf_counter()

    while not state.is_terminal():
        cp = state.current_player()
        if cp < 0 or cp >= 2:
            break

        bot = bots[cp]
        legal_ids = state.legal_actions()
        legal_moves = _legal_moves_strings(state._engine, legal_ids)

        t0 = time.perf_counter()
        policy, chosen = bot.step_with_policy(state)
        wall_ms = (time.perf_counter() - t0) * 1000.0

        action_probs: dict[int, float] = {}
        for aid, prob in policy:
            action_probs[int(aid)] = float(prob)

        chosen_move_obj = action_to_move(state._engine, int(chosen))
        chosen_move_str = str(chosen_move_obj)

        player_id = state._game.get_player_ids()[cp]

        decisions.append({
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

        replay_log.append({
            "step_index": decision_count,
            "player_id": player_id,
            "round_number": state._engine.round_number,
            "phase": state._engine.phase.value,
            "prompts": [],
            "move_type": chosen_move_obj.move_type,
            "label": chosen_move_str,
            "payload": _move_to_payload(chosen_move_obj),
        })

        state.apply_action(int(chosen))
        decision_count += 1

    wall_sec = time.perf_counter() - wall_start

    ret = state.returns()
    winner = None
    if abs(ret[0] - ret[1]) > 1e-6:
        winner = 0 if ret[0] > ret[1] else 1

    sims_per_sec = (num_sims * decision_count) / wall_sec if wall_sec > 0 else 0.0

    game_summary = {
        "game_index": game_index,
        "shuffle_seed": shuffle_seed,
        "num_sims_per_move": num_sims,
        "uct_c": uct_c,
        "policy_type": final_policy_name,
        "decision_count": decision_count,
        "wall_time_sec": round(wall_sec, 3),
        "sims_per_sec_avg": round(sims_per_sec, 1),
        "returns": [round(float(ret[0]), 3), round(float(ret[1]), 3)],
        "winner": winner,
        "score_diff": round(abs(float(ret[0])), 3),
    }

    replay_payload = {
        "stopped_reason": "terminal" if state.is_terminal() else "unknown",
        "step_count": decision_count,
        "is_terminal": state.is_terminal(),
        "winner_id": state._game.get_player_ids()[winner] if winner is not None else None,
        "final_scores": {},
        "replay_log": replay_log,
        "replay_context": {
            "board_path": str(ROOT / "data" / "boards" / "tyrants_of_the_underdark.json"),
            "card_path": str(ROOT / "data" / "cards" / "catalog.json"),
            "setup_path": str(ROOT / "data" / "decks" / "base_setup.json"),
            "player_ids": list(state._game.get_player_ids()),
            "seed": shuffle_seed,
        },
    }
    with (game_out / "replay.json").open("w", encoding="utf-8") as f:
        json.dump(replay_payload, f, indent=2)
        f.write("\n")

    with (game_out / "decisions.jsonl").open("w", encoding="utf-8") as f:
        for d in decisions:
            f.write(json.dumps(d) + "\n")

    with (game_out / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(game_summary, f, indent=2)
        f.write("\n")

    return game_summary


def write_summaries(out_dir: Path, summaries: list[dict]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = _summary_csv_path(out_dir)
    fieldnames = [
        "game_index", "shuffle_seed", "num_sims_per_move", "uct_c",
        "decision_count", "wall_time_sec", "sims_per_sec_avg",
        "winner", "score_diff",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for s in summaries:
            writer.writerow(s)

    md_path = _summary_md_path(out_dir)
    total_wall = sum(s["wall_time_sec"] for s in summaries)
    total_decisions = sum(s["decision_count"] for s in summaries)
    total_sims = sum(s["num_sims_per_move"] * s["decision_count"] for s in summaries)
    total_sims_per_sec = total_sims / total_wall if total_wall > 0 else 0.0
    wins = [s["winner"] for s in summaries if s["winner"] is not None]

    with md_path.open("w", encoding="utf-8") as f:
        f.write("# IS-MCTS Run Summary\n\n")
        f.write(f"- **Games:** {len(summaries)}\n")
        f.write(f"- **Total wall time:** {total_wall:.1f}s\n")
        f.write(f"- **Total decisions:** {total_decisions}\n")
        f.write(f"- **Overall sims/sec:** {total_sims_per_sec:.1f}\n")
        f.write(f"- **Win split (p0/p1):** {wins.count(0)}/{wins.count(1)}\n")
        f.write(f"- **Mean decisions/game:** {total_decisions / len(summaries):.0f}\n")
        f.write("\n| game | seed | sims | uct_c | decisions | wall_s | sims/s | winner | score_diff |\n")
        f.write("|------|------|------|-------|-----------|--------|--------|--------|------------|\n")
        for s in summaries:
            winner_str = {0: "p0", 1: "p1", None: "tie"}.get(s["winner"], "?")
            f.write(
                f"| {s['game_index']} | {s['shuffle_seed']} | {s['num_sims_per_move']} "
                f"| {s['uct_c']} | {s['decision_count']} "
                f"| {s['wall_time_sec']:.1f} | {s['sims_per_sec_avg']:.0f} "
                f"| {winner_str} | {s['score_diff']:.1f} |\n"
            )

    print(f"Wrote {csv_path}")
    print(f"Wrote {md_path}")


def main() -> None:
    args = _parse_args()

    policy_type = _resolve_policy(args.final_policy)

    game = pyspiel.load_game("python_pyrants")

    print(f"IS-MCTS: {args.num_sims} sims/move, uct_c={args.uct_c}, "
          f"policy={args.final_policy}, {args.num_games} games, seed={args.seed}")
    print(f"Output: {args.output_dir}")
    print()

    summaries: list[dict] = []
    for gi in range(args.num_games):
        print(f"Game {gi + 1}/{args.num_games}...", end=" ", flush=True)
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
            shuffle_seed=args.shuffle_seed if args.shuffle_seed != 0 else args.seed + gi,
            out_dir=args.output_dir,
        )
        summaries.append(summary)

        elapsed = time.perf_counter() - t0
        sims_done = args.num_sims * summary["decision_count"]
        rate = sims_done / elapsed if elapsed > 0 else 0
        print(f"decisions={summary['decision_count']} "
              f"winner={summary['winner']} "
              f"wall={elapsed:.1f}s sims/s={rate:.0f}")

    write_summaries(args.output_dir, summaries)


if __name__ == "__main__":
    main()
