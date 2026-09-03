"""Headless replay verifier: replay every IS-MCTS artifact through the C engine.

Walks ``artifacts/ismcts`` for ``replay.json`` files and re-simulates each one
via :mod:`interface.replay_player`. Cheap (~80 ms/game) and the tool that
proves an engine change broke replay compatibility.

Usage:
    python scripts/verify_replays.py [--root artifacts/ismcts]

Exit code 0 when every replay replays cleanly; non-zero otherwise.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from interface.replay_loader import discover_replays, load_replay  # noqa: E402
from interface.replay_player import ReplayDesyncError, ReplayPlayer  # noqa: E402


def _verify_one(game_dir: Path) -> tuple[str, str]:
    """Return (status, detail) for one replay directory."""
    bundle = load_replay(game_dir)
    player = ReplayPlayer(bundle)
    try:
        while player.step_forward():
            pass
    except ReplayDesyncError as exc:
        player.close()
        return ("DESYNC", f"step {exc.step_index}: {exc.expected!r}")
    except Exception as exc:
        player.close()
        return ("ERROR", f"{type(exc).__name__}: {exc}")

    reached_end = player.index == player.total_steps
    terminal = player.is_terminal
    expected_final = bundle.replay.get("final_scores")
    actual_final = player.session.final_scores() if terminal else {}
    stopped = bundle.replay.get("stopped_reason", "")

    player.close()

    if not reached_end:
        return ("INTERRUPTED", f"index {player.index}/{player.total_steps}")
    if terminal and expected_final is not None and actual_final != expected_final:
        return ("SCORE-MISMATCH", f"{actual_final} != {expected_final}")
    if stopped and stopped != "terminal":
        return ("OK", f"(partial: {stopped})")
    return ("OK", "")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify IS-MCTS replay artifacts replay faithfully.")
    parser.add_argument("--root", type=Path, default=ROOT / "artifacts" / "ismcts")
    args = parser.parse_args()

    metas = discover_replays(args.root)
    if not metas:
        print(f"No replay.json files found under {args.root}")
        return 0

    failures = 0
    print(f"{'STATUS':<18} {'MOVES':>6}  GAME")
    print("-" * 78)
    for meta in metas:
        status, detail = _verify_one(meta.game_dir)
        line = f"{status:<18} {meta.step_count:>6}  {meta.game_dir.relative_to(args.root)}"
        if detail:
            line += f"  {detail}"
        print(line)
        if status != "OK":
            failures += 1

    print("-" * 78)
    print(f"{len(metas) - failures}/{len(metas)} replays OK")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())