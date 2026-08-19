"""Generate reachable card scenarios for the Tyrants board (C engine)."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine_c.bindings.scenario_search import (  # noqa: E402, I001
    ensure_card_scenario_c,
    generate_card_scenarios_c,
    save_c_scenario,
)
from game_setup.scenario_generation.rosters import (  # noqa: E402
    DEFAULT_BOARD_PATH,
    DEFAULT_CARD_PATH,
    DEFAULT_ROSTERS_PATH,
    DEFAULT_SETUP_PATH,
    FORCED_INJECTIONS_FILENAME,
    StopConditions,
    iter_roster_card_ids,
    write_forced_injection_notes,
)

logger = logging.getLogger("generate_card_scenarios")


def _configure_logging(quiet: bool = False) -> None:
    level = logging.WARNING if quiet else logging.INFO
    handler = logging.StreamHandler(sys.stderr)
    fmt = '{"ts": "%(asctime)s", "level": "%(levelname)s", "msg": "%(message)s"}'
    handler.setFormatter(logging.Formatter(fmt, datefmt="%Y-%m-%dT%H:%M:%S"))
    logging.basicConfig(level=level, handlers=[handler])


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
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
    parser.add_argument("--workers", type=int, default=1, help="Number of parallel workers (default: 1)")
    parser.add_argument("--pretty", action="store_true", help="Write pretty-printed JSON (indent=2)")
    parser.add_argument("--require-spy-on-board", action="store_true", help="Require current player to have a spy on the board")
    parser.add_argument("--require-aspect", type=str, default=None, help="Require N cards of ASPECT in hand (format: ASPECT:COUNT, e.g. guile:2)")
    return parser.parse_args(argv)


def _resolve_player_ids(players_arg: str) -> list[str]:
    player_ids = [pid.strip() for pid in players_arg.split(",") if pid.strip()]
    if not player_ids:
        raise ValueError("At least one player id is required")
    return player_ids


def _run_list_mode(rosters_path: Path) -> None:
    for cid in iter_roster_card_ids(rosters_path):
        print(cid)


def _build_stop_conditions(args: argparse.Namespace) -> StopConditions:
    require_aspect: str | None = None
    require_aspect_count: int = 0
    if args.require_aspect:
        parts = args.require_aspect.split(":")
        if len(parts) != 2:
            raise ValueError(f"Invalid --require-aspect format: {args.require_aspect!r}. Expected ASPECT:COUNT (e.g. guile:2)")
        require_aspect = parts[0].strip()
        try:
            require_aspect_count = int(parts[1])
        except ValueError:
            raise ValueError(f"Invalid count in --require-aspect: {args.require_aspect!r}. Count must be an integer.") from None
        if require_aspect_count <= 0:
            raise ValueError(f"Invalid count in --require-aspect: {args.require_aspect!r}. Count must be positive."    )
    return StopConditions(
        require_spy_on_board=args.require_spy_on_board,
        require_aspect=require_aspect,
        require_aspect_count=require_aspect_count,
    )


def _run_single_card_mode(args: argparse.Namespace, player_ids: list[str]) -> None:
    card_id = args.card_id
    conditions = _build_stop_conditions(args)
    logger.info("Searching for card scenario card_id=%s seed=%d", card_id, args.base_seed)

    state, injection_note, market_deck_ids, special_stacks_present = ensure_card_scenario_c(
        card_id,
        board_path=args.board_path,
        card_path=args.card_path,
        setup_path=args.setup_path,
        rosters_path=args.rosters_path,
        player_ids=player_ids,
        base_seed=args.base_seed,
        max_attempts=args.max_attempts,
        max_steps_per_attempt=args.max_steps,
        verbose=True,
        conditions=conditions,
    )

    filename = f"{card_id}_seed_{args.base_seed}.json"
    path = args.output_dir / filename
    forced_notes: list[dict[str, object]] = []

    if injection_note is not None:
        tags = ["generated", "cards", "forced_injection"]
        description = f"Forced-injection fallback scenario for {card_id} after reachable search exhaustion"
        forced_notes.append({**injection_note, "scenario_file": filename})
    else:
        tags = ["generated", "cards", "reachable", "playable_now"]
        description = f"Reachable 4-player Tyrants scenario for {card_id}"

    save_c_scenario(
        state,
        path,
        scenario_id=f"card_{card_id}",
        description=description,
        tags=tags,
        card_under_test=card_id,
        market_deck_ids=market_deck_ids,
        special_stacks_present=special_stacks_present,
        pretty=args.pretty,
    )
    state.destroy()
    notes_path = write_forced_injection_notes(args.output_dir, forced_notes)

    print(f"Saved: {path}")
    logger.info("Scenario saved card_id=%s path=%s seed=%d", card_id, path, args.base_seed)
    if forced_notes:
        print(f"Forced injections: {len(forced_notes)}")
        print(f"Notes: {notes_path}")
        logger.warning("Forced injection used card_id=%s count=%d seed=%d", card_id, len(forced_notes), args.base_seed)


def _run_batch_mode(args: argparse.Namespace, player_ids: list[str]) -> None:
    all_ids = iter_roster_card_ids(args.rosters_path)
    conditions = _build_stop_conditions(args)
    logger.info(
        "Starting batch generation cards=%d players=%d attempts=%d steps=%d",
        len(all_ids),
        len(player_ids),
        args.max_attempts,
        args.max_steps,
    )

    if not args.quiet:
        print(f"Generating {len(all_ids)} scenarios")
        print(f"  players={len(player_ids)}  attempts={args.max_attempts}  steps={args.max_steps}")
        print(f"  (starter cards ~1s, cheap market ~5s, expensive up to {args.max_attempts * args.max_steps * 0.035:.0f}s)")
        print(f"  output: {args.output_dir}")
        print()

    saved, missing = generate_card_scenarios_c(
        args.output_dir,
        board_path=args.board_path,
        card_path=args.card_path,
        setup_path=args.setup_path,
        rosters_path=args.rosters_path,
        player_ids=player_ids,
        base_seed=args.base_seed,
        max_attempts=args.max_attempts,
        max_steps_per_attempt=args.max_steps,
        workers=args.workers,
        pretty=args.pretty,
        conditions=conditions,
    )

    notes_path = args.output_dir / FORCED_INJECTIONS_FILENAME
    forced_notes = json.loads(notes_path.read_text(encoding="utf-8")) if notes_path.exists() else []

    print(f"Saved: {len(saved)}")
    print(f"Injected: {len(forced_notes)}")
    print(f"Missing: {len(missing)}")
    print(f"Notes: {notes_path}")

    logger.info(
        "Batch generation complete saved=%d injected=%d missing=%d",
        len(saved),
        len(forced_notes),
        len(missing),
    )

    if missing:
        print(f"Missing cards: {', '.join(missing)}")
        logger.error("Missing cards %s", missing)
        sys.exit(1)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    _configure_logging(quiet=args.quiet)

    player_ids = _resolve_player_ids(args.players)

    if args.list_ids:
        _run_list_mode(args.rosters_path)
        return

    args.output_dir.mkdir(parents=True, exist_ok=True)

    if args.card_id is not None:
        _run_single_card_mode(args, player_ids)
        return

    _run_batch_mode(args, player_ids)


if __name__ == "__main__":
    main()
