"""Run random move walks and save final game states as scenarios."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from random import Random

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.state import build_initial_game_state  # noqa: E402
from game_session import GameSession  # noqa: E402
from game_setup.loaders import build_game_definition_from_dicts  # noqa: E402
from game_setup.market_setup import (  # noqa: E402
    combine_two_deck_market_setup,
    discover_full_deck_profiles,
    pick_random_pair,
)
from game_setup.scenarios import save_game_state  # noqa: E402
from game_view import build_game_view  # noqa: E402

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_BOARD_PATH = ROOT_DIR / "data" / "boards" / "tyrants_of_the_underdark.json"
DEFAULT_CARD_PATH = ROOT_DIR / "data" / "cards" / "catalog.json"
DEFAULT_SETUP_PATH = ROOT_DIR / "data" / "decks" / "base_setup.json"
DECKS_DIR = ROOT_DIR / "data" / "decks"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "data" / "scenarios" / "random_walks"


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _build_roster_market_setup(
    setup_path: Path,
    decks_dir: Path | None,
    rng: Random,
    deck_a_id: str | None = None,
    deck_b_id: str | None = None,
) -> tuple[dict, str, str]:
    """Build a setup dict with two randomly selected full-deck rosters.

    Returns ``(setup_data, deck_a_id, deck_b_id)``.  When *decks_dir* is
    ``None`` or contains no usable full decks, returns the bare
    ``base_setup`` payload unchanged.
    """
    base_setup = _load_json(setup_path)

    if decks_dir is None or not decks_dir.is_dir():
        return base_setup, "", ""

    profiles = discover_full_deck_profiles(decks_dir)
    if len(profiles) < 2:
        return base_setup, "", ""

    if deck_a_id is not None and deck_b_id is not None:
        selected_a = next((p for p in profiles if p.deck_id == deck_a_id), None)
        selected_b = next((p for p in profiles if p.deck_id == deck_b_id and p.deck_id != deck_a_id), None)
        if selected_a is None or selected_b is None:
            raise ValueError(f"Invalid deck selection: {deck_a_id} / {deck_b_id}")
    else:
        selected_a, selected_b = pick_random_pair(profiles, rng)

    deck_a_id = selected_a.deck_id
    deck_b_id = selected_b.deck_id

    market_setup = combine_two_deck_market_setup(base_setup, selected_a, selected_b)
    setup_data = market_setup.to_setup_data()
    setup_data["setup_id"] = f"random_walk_{deck_a_id}_{deck_b_id}"
    return setup_data, deck_a_id, deck_b_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Run random walk simulation and save final game state")
    parser.add_argument("--players", default="p1,p2,p3,p4", help="Comma-separated player ids")
    parser.add_argument("--seed", type=int, default=1, help="RNG seed for game setup")
    parser.add_argument("--policy-seed", type=int, default=1, help="RNG seed for random move choice")
    parser.add_argument("--max-steps", type=int, default=1000, help="Maximum number of steps to walk")
    parser.add_argument("--board-path", type=Path, default=DEFAULT_BOARD_PATH)
    parser.add_argument("--card-path", type=Path, default=DEFAULT_CARD_PATH)
    parser.add_argument("--setup-path", type=Path, default=DEFAULT_SETUP_PATH)
    parser.add_argument("--decks-dir", type=Path, default=DECKS_DIR)
    parser.add_argument("--deck-a", type=str, default=None, help="Force a specific full deck (e.g. dragon)")
    parser.add_argument("--deck-b", type=str, default=None, help="Force a specific full deck (e.g. drow)")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--run-id", type=str, default="", help="Identifier for this run (defaults to seed)")
    args = parser.parse_args()

    if (args.deck_a is None) != (args.deck_b is None):
        parser.error("--deck-a and --deck-b must be used together or not at all")

    player_ids = [pid.strip() for pid in args.players.split(",") if pid.strip()]

    rng = Random(args.seed)
    setup_data, deck_a_id, deck_b_id = _build_roster_market_setup(
        args.setup_path, args.decks_dir, rng,
        deck_a_id=args.deck_a,
        deck_b_id=args.deck_b,
    )

    if deck_a_id and deck_b_id:
        print(f"Decks: {deck_a_id} + {deck_b_id}")

    definition = build_game_definition_from_dicts(
        board_data=_load_json(args.board_path),
        card_data=_load_json(args.card_path),
        setup_data=setup_data,
        definition_id="random_walk",
    )

    state = build_initial_game_state(
        definition,
        player_ids=player_ids,
        shuffle_seed=args.seed,
    )

    session = GameSession(state)

    move_rng = Random(args.policy_seed)

    try:
        from tqdm import tqdm as _tqdm
    except ImportError:
        _tqdm = None

    if _tqdm is not None:
        progress = _tqdm(total=args.max_steps, desc="Walking", unit="step")
    else:
        progress = None

    for step in range(args.max_steps):
        view = build_game_view(session)
        if view.is_terminal or not view.legal_moves:
            break
        move = move_rng.choice(view.legal_moves).move
        session.submit_move(move)
        if progress is not None:
            progress.update(1)

    if progress is not None:
        progress.close()

    run_id = args.run_id or f"seed_{args.seed}"
    output_path = Path(args.output_dir) / f"{run_id}.json"
    args.output_dir.mkdir(parents=True, exist_ok=True)

    final_view = build_game_view(session)

    save_game_state(
        session.state,
        output_path,
        scenario_id=run_id,
        description=f"Random walk with {len(player_ids)} players, {session.move_count} steps, seed={args.seed}, decks={deck_a_id}+{deck_b_id}",
        tags=["random_walk"],
        move_count=session.move_count,
        is_terminal=final_view.is_terminal,
    )

    print(f"Run '{run_id}': {session.move_count} steps, terminal={final_view.is_terminal}")
    if final_view.winner_id:
        print(f"  Winner: {final_view.winner_id}")
    print(f"  Saved: {output_path}")


if __name__ == "__main__":
    main()
