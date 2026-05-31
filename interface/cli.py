"""Command-line interface for running a local Tyrants game session."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Callable, Sequence

from engine.errors import RuleViolationError
from game_session import GameSession
from interface.display import render_legal_moves, render_state
from interface.parser import CommandKind, help_text, parse_command

InputFn = Callable[[str], str]
OutputFn = Callable[[str], None]

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_BOARD_PATH = ROOT_DIR / "data" / "boards" / "base_game.json"
DEFAULT_CARD_PATH = ROOT_DIR / "data" / "cards" / "catalog.json"
DEFAULT_SETUP_PATH = ROOT_DIR / "data" / "decks" / "base_setup.json"


def run_cli(
    player_ids: Sequence[str],
    seed: int = 1,
    board_path: Path = DEFAULT_BOARD_PATH,
    card_path: Path = DEFAULT_CARD_PATH,
    setup_path: Path = DEFAULT_SETUP_PATH,
    input_fn: InputFn = input,
    output_fn: OutputFn = print,
    max_steps: int | None = None,
) -> None:
    """Run an interactive CLI session using external board and deck definitions."""

    session = GameSession.from_files(
        board_path=board_path,
        card_path=card_path,
        setup_path=setup_path,
        player_ids=player_ids,
        seed=seed,
    )

    steps = 0
    while True:
        output_fn("")
        output_fn(render_state(session.state))

        if session.is_terminal():
            totals = session.final_scores() or {}
            victor = session.winner_id()
            output_fn("")
            output_fn("Game over")
            for player_id, score in sorted(totals.items()):
                output_fn(f"  {player_id}: {score}")
            output_fn(f"Winner: {victor if victor is not None else 'tie'}")
            return

        if max_steps is not None and steps >= max_steps:
            output_fn("Stopping after max_steps limit.")
            return

        raw_command = input_fn("command> ")
        try:
            parsed = parse_command(raw_command, session.state)
        except ValueError as error:
            output_fn(f"Invalid command: {error}")
            continue

        if parsed.kind == CommandKind.HELP:
            output_fn(help_text(session.state.phase))
            continue

        if parsed.kind == CommandKind.LEGAL:
            output_fn(render_legal_moves(session.state))
            continue

        if parsed.kind == CommandKind.QUIT:
            output_fn("Exiting game.")
            return

        if parsed.move is None:
            output_fn("Invalid command: move payload is missing")
            continue

        try:
            session.submit_move(parsed.move)
        except RuleViolationError as error:
            output_fn(f"Move rejected: {error}")
            continue

        steps += 1


def _parse_player_ids(raw_player_ids: str) -> list[str]:
    player_ids = [player_id.strip() for player_id in raw_player_ids.split(",") if player_id.strip()]
    if not player_ids:
        raise ValueError("At least one player id is required")
    return player_ids


def main() -> None:
    """Parse CLI args and launch a game session."""

    parser = argparse.ArgumentParser(description="Run the Tyrants of the Underdark CLI")
    parser.add_argument("--players", default="p1,p2", help="Comma-separated player ids")
    parser.add_argument("--seed", type=int, default=1, help="RNG seed for shuffling")
    parser.add_argument("--board-path", type=Path, default=DEFAULT_BOARD_PATH)
    parser.add_argument("--card-path", type=Path, default=DEFAULT_CARD_PATH)
    parser.add_argument("--setup-path", type=Path, default=DEFAULT_SETUP_PATH)
    args = parser.parse_args()

    run_cli(
        player_ids=_parse_player_ids(args.players),
        seed=args.seed,
        board_path=args.board_path,
        card_path=args.card_path,
        setup_path=args.setup_path,
    )


if __name__ == "__main__":
    main()
