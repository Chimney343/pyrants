"""Build sharded NN training data from IS-MCTS replay runs (layer 2b).

Replays every accepted game through the C engine, encodes the acting player's
observation at each decision node, joins it with the logged search policy and
final scores, and writes ``.npz`` shards plus a dataset manifest.

Usage:
    python -m scripts.build_nn_dataset --runs artifacts/ismcts/runs/<ts>_<id> --out datasets/x
    python -m scripts.build_nn_dataset --report datasets/x
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from interface.replay_loader import load_replay  # noqa: E402
from interface.replay_player import ReplayDesyncError  # noqa: E402
from openspiel_pyrants.nn.dataset import write_shards  # noqa: E402
from scripts._nn_dataset import (  # noqa: E402
    AlignmentError,
    iter_samples,
    report_metrics,
    validate_game_dir,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build NN training shards from IS-MCTS replays.")
    parser.add_argument("--runs", nargs="*", type=Path, default=[],
                        help="Run directories (or bases containing them).")
    parser.add_argument("--out", type=Path, default=None,
                        help="Output dataset directory.")
    parser.add_argument("--shard-size", type=int, default=20000)
    parser.add_argument("--allow-legacy-schema", action="store_true",
                        help="Accept pre-v2 games and recover visits from policy.")
    parser.add_argument("--keep-forced", action="store_true",
                        help="Keep forced decisions (default: drop them).")
    parser.add_argument("--leak-check", type=int, default=0,
                        help="Re-encode N random nodes after determinize (per game).")
    parser.add_argument("--strict", action="store_true",
                        help="Raise on a desync/alignment failure instead of skipping the game.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dataset-id", type=str, default="")
    parser.add_argument("--report", type=Path, default=None,
                        help="Print label-sanity metrics for an existing dataset and exit.")
    return parser.parse_args()


def _game_dirs(run_path: Path) -> list[Path]:
    run_path = Path(run_path)
    if not run_path.exists():
        return []
    if (run_path / "manifest.json").exists():
        return sorted(p for p in run_path.glob("game_*") if p.is_dir())
    return sorted(p.parent for p in run_path.rglob("replay.json"))


def _run_source(run_path: Path) -> dict:
    run_path = Path(run_path)
    manifest = None
    try:
        manifest = json.loads((run_path / "manifest.json").read_text(encoding="utf-8"))
    except Exception:
        manifest = None
    return {
        "path": str(run_path),
        "run_id": (manifest or {}).get("run_id"),
        "engine_git_sha": (manifest or {}).get("engine_git_sha"),
        "engine_dll_sha256": (manifest or {}).get("engine_dll_sha256"),
    }


def main() -> int:
    args = _parse_args()

    if args.report is not None:
        print(json.dumps(report_metrics(args.report), indent=2))
        return 0

    if not args.runs:
        print("--runs is required (or use --report)", file=sys.stderr)
        return 2
    if args.out is None:
        print("--out is required", file=sys.stderr)
        return 2

    game_dirs: list[Path] = []
    for run in args.runs:
        game_dirs.extend(_game_dirs(run))

    rng = random.Random(args.seed) if args.leak_check > 0 else None
    samples = []
    accepted: list[dict] = []
    rejected: list[dict] = []

    for game_idx, game_dir in enumerate(game_dirs):
        check = validate_game_dir(game_dir, allow_legacy=args.allow_legacy_schema)
        if not check.ok:
            rejected.append({
                "game_dir": str(game_dir),
                "run_id": check.run_id,
                "schema_version": check.schema_version,
                "reasons": check.reasons,
            })
            continue
        bundle = load_replay(game_dir)
        try:
            game_samples = list(iter_samples(
                bundle,
                allow_legacy=args.allow_legacy_schema,
                keep_forced=args.keep_forced,
                leak_check_rng=rng,
                leak_check_limit=args.leak_check,
                game_idx=game_idx,
            ))
        except (ReplayDesyncError, AlignmentError, ValueError) as exc:
            if args.strict:
                raise
            rejected.append({
                "game_dir": str(game_dir),
                "run_id": check.run_id,
                "schema_version": check.schema_version,
                "reasons": [f"{type(exc).__name__}: {exc}"],
            })
            continue
        accepted.append({
            "game_dir": str(game_dir),
            "run_id": check.run_id,
            "samples": len(game_samples),
        })
        samples.extend(game_samples)

    dataset_id = args.dataset_id or args.out.name or datetime.now(UTC).strftime(
        "%Y%m%dT%H%M%SZ"
    )
    manifest = write_shards(
        samples,
        args.out,
        dataset_id=dataset_id,
        shard_size=args.shard_size,
        sources={
            "runs": [_run_source(run) for run in args.runs],
            "accepted": accepted,
            "rejected": rejected,
        },
    )

    if rejected:
        rejected_path = Path(args.out) / "rejected.jsonl"
        with rejected_path.open("w", encoding="utf-8") as fh:
            for row in rejected:
                fh.write(json.dumps(row) + "\n")

    print(
        f"dataset {dataset_id}: games accepted={len(accepted)} rejected={len(rejected)} "
        f"samples={manifest['counts']['samples']} shards={len(manifest['shards'])}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
