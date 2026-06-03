"""Generate 125 reachable card scenarios for the Tyrants board."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from game_setup.scenarios import save_game_state  # noqa: E402
from game_setup.state_generator import (  # noqa: E402
    DEFAULT_BOARD_PATH,
    DEFAULT_CARD_PATH,
    DEFAULT_ROSTERS_PATH,
    DEFAULT_SETUP_PATH,
    FORCED_INJECTIONS_FILENAME,
    ensure_card_scenario,
    generate_card_scenarios,
    iter_roster_card_ids,
    write_forced_injection_notes,
)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Generate reachable card scenarios for the Tyrants board")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data" / "scenarios" / "cards")
    parser.add_argument("--board-path", type=Path, default=DEFAULT_BOARD_PATH)
    parser.add_argument("--card-path", type=Path, default=DEFAULT_CARD_PATH)
    parser.add_argument("--setup-path", type=Path, default=DEFAULT_SETUP_PATH)
    parser.add_argument("--rosters-path", type=Path, default=DEFAULT_ROSTERS_PATH)
    parser.add_argument("--players", type=str, default="p1,p2,p3,p4", help="Comma-separated player ids")
    parser.add_argument("--base-seed", type=int, default=0)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--max-steps", type=int, default=1500)
    parser.add_argument("--card-id", type=str, default=None, help="Generate only this card id (for debugging)")
    parser.add_argument("--list-ids", action="store_true", help="List all card ids and exit")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-card output")
    args = parser.parse_args()

    player_ids = [pid.strip() for pid in args.players.split(",") if pid.strip()]
    if not player_ids:
        raise ValueError("At least one player id is required")

    if args.list_ids:
        for cid in iter_roster_card_ids(args.rosters_path):
            print(cid)
        return

    args.output_dir.mkdir(parents=True, exist_ok=True)

    if args.card_id is not None:
        print(f"Searching for {args.card_id}...")
        state, injection_note = ensure_card_scenario(
            args.card_id,
            board_path=args.board_path,
            card_path=args.card_path,
            setup_path=args.setup_path,
            rosters_path=args.rosters_path,
            player_ids=player_ids,
            base_seed=args.base_seed,
            max_attempts=args.max_attempts,
            max_steps_per_attempt=args.max_steps,
            verbose=True,
        )

        path = args.output_dir / f"000_{args.card_id}.json"
        tags = ["generated", "cards", "reachable", "playable_now"]
        description = f"Reachable 4-player Tyrants scenario for {args.card_id}"
        forced_notes: list[dict[str, object]] = []
        if injection_note is not None:
            tags = ["generated", "cards", "forced_injection"]
            description = f"Forced-injection fallback scenario for {args.card_id} after reachable search exhaustion"
            forced_notes.append({**injection_note, "scenario_file": path.name})

        save_game_state(
            state,
            path,
            scenario_id=f"card_{args.card_id}",
            description=description,
            tags=tags,
            card_under_test=args.card_id,
        )
        notes_path = write_forced_injection_notes(args.output_dir, forced_notes)
        print(f"Saved: {path}")
        if forced_notes:
            print("Forced injections: 1")
            print(f"Notes: {notes_path}")
        return

    all_ids = iter_roster_card_ids(args.rosters_path)
    if not args.quiet:
        print(f"Generating {len(all_ids)} scenarios")
        print(f"  players={len(player_ids)}  attempts={args.max_attempts}  steps={args.max_steps}")
        print(f"  (starter cards ~1s, cheap market ~5s, expensive up to {args.max_attempts * args.max_steps * 0.035:.0f}s)")
        print(f"  output: {args.output_dir}")
        print()

    saved, missing = generate_card_scenarios(
        args.output_dir,
        board_path=args.board_path,
        card_path=args.card_path,
        setup_path=args.setup_path,
        rosters_path=args.rosters_path,
        player_ids=player_ids,
        base_seed=args.base_seed,
        max_attempts=args.max_attempts,
        max_steps_per_attempt=args.max_steps,
    )

    notes_path = args.output_dir / FORCED_INJECTIONS_FILENAME
    forced_notes = json.loads(notes_path.read_text(encoding="utf-8")) if notes_path.exists() else []

    print(f"\nSaved: {len(saved)}")
    print(f"Injected: {len(forced_notes)}")
    print(f"Missing: {len(missing)}")
    print(f"Notes: {notes_path}")
    if missing:
        print(f"Missing cards: {', '.join(missing)}")
        sys.exit(1)


if __name__ == "__main__":
    main()