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
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from openspiel_pyrants.nn.dataset import write_shards  # noqa: E402
from scripts._nn_dataset import build_dataset_from_runs, report_metrics  # noqa: E402


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

    result = build_dataset_from_runs(
        args.runs,
        allow_legacy_schema=args.allow_legacy_schema,
        keep_forced=args.keep_forced,
        leak_check=args.leak_check,
        strict=args.strict,
        seed=args.seed,
    )

    dataset_id = args.dataset_id or args.out.name or datetime.now(UTC).strftime(
        "%Y%m%dT%H%M%SZ"
    )
    manifest = write_shards(
        result.samples,
        args.out,
        dataset_id=dataset_id,
        shard_size=args.shard_size,
        sources={
            "runs": [_run_source(run) for run in args.runs],
            "accepted": result.accepted,
            "rejected": result.rejected,
        },
    )

    if result.rejected:
        rejected_path = Path(args.out) / "rejected.jsonl"
        with rejected_path.open("w", encoding="utf-8") as fh:
            for row in result.rejected:
                fh.write(json.dumps(row) + "\n")

    print(
        f"dataset {dataset_id}: games accepted={len(result.accepted)} "
        f"rejected={len(result.rejected)} samples={manifest['counts']['samples']} "
        f"shards={len(manifest['shards'])}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
