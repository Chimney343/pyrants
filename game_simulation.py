"""Headless game simulation helpers built on the shared session layer."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from random import Random

from pydantic import TypeAdapter

from engine.moves import Move
from engine.moves import move_type as _move_type
from engine.rules import apply as apply_move
from engine.rules import is_terminal as state_is_terminal
from engine.rules import legal_moves as get_legal_moves
from engine.rules import winner as get_winner
from engine.scoring import compute_final_scores
from engine.state import GameState
from game_session import GameSession
from game_view import GameView, LegalMoveView, build_game_view

ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_BOARD_PATH = ROOT_DIR / "data" / "boards" / "tyrants_of_the_underdark.json"
DEFAULT_CARD_PATH = ROOT_DIR / "data" / "cards" / "catalog.json"
DEFAULT_SETUP_PATH = ROOT_DIR / "data" / "decks" / "base_setup.json"

MoveChooser = Callable[[GameSession, GameView], Move]
EngineMoveChooser = Callable[[GameState, list[Move]], Move]
MOVE_ADAPTER = TypeAdapter(Move)


@dataclass(frozen=True)
class ReplayContext:
    """Inputs required to reconstruct a replayed game session."""

    board_path: str
    card_path: str
    setup_path: str
    player_ids: tuple[str, ...]
    seed: int | None


@dataclass(frozen=True)
class SimulationStep:
    """One applied move in a headless simulation run."""

    step_index: int
    player_id: str
    round_number: int
    phase: str
    prompts: tuple[str, ...]
    move_type: str
    label: str
    payload: dict[str, object]


@dataclass(frozen=True)
class SimulationResult:
    """Final outcome plus replayable step log for a simulation run."""

    stopped_reason: str
    step_count: int
    is_terminal: bool
    winner_id: str | None
    final_scores: dict[str, int] | None
    replay_log: tuple[SimulationStep, ...]
    replay_context: ReplayContext | None = None


def choose_first_legal_move(_session: GameSession, view: GameView) -> Move:
    """Choose the first legal move in engine order."""

    if not view.legal_moves:
        raise ValueError("Cannot choose a move when no legal moves are available")
    return view.legal_moves[0].move


def make_random_legal_move_chooser(seed: int) -> MoveChooser:
    """Return a deterministic random chooser for legal moves."""

    rng = Random(seed)

    def _choose(_session: GameSession, view: GameView) -> Move:
        if not view.legal_moves:
            raise ValueError("Cannot choose a move when no legal moves are available")
        return rng.choice(view.legal_moves).move

    return _choose


def choose_first_legal_move_engine(_state: GameState, moves: list[Move]) -> Move:
    """Choose the first legal move in engine order (fast-path variant)."""

    if not moves:
        raise ValueError("Cannot choose a move when no legal moves are available")
    return moves[0]


def make_random_legal_move_chooser_engine(seed: int) -> EngineMoveChooser:
    """Return a deterministic random chooser for legal moves (fast-path variant)."""

    rng = Random(seed)

    def _choose(_state: GameState, moves: list[Move]) -> Move:
        if not moves:
            raise ValueError("Cannot choose a move when no legal moves are available")
        return rng.choice(moves)

    return _choose


@dataclass(frozen=True)
class FastSimulationStep:
    """Minimal step record for fast simulation runs."""

    step_index: int
    player_id: str
    phase: str
    move_type: str


@dataclass
class FastSimulationResult:
    """Final outcome for a fast simulation run with optional move log."""

    stopped_reason: str
    step_count: int
    is_terminal: bool
    winner_id: str | None
    final_scores: dict[str, int] | None
    move_log: tuple[FastSimulationStep, ...] = ()
    final_state: GameState | None = None


def run_fast_simulation(
    state: GameState,
    chooser: EngineMoveChooser = choose_first_legal_move_engine,
    *,
    max_steps: int = 500,
    record_moves: bool = False,
) -> FastSimulationResult:
    """Advance a state headlessly without building GameView projections.

    Returns a ``FastSimulationResult``.  When ``record_moves`` is True the
    ``move_log`` field is populated with lightweight step records.
    """

    move_log: list[FastSimulationStep] = []

    for step_index in range(max_steps):
        if state_is_terminal(state):
            return FastSimulationResult(
                stopped_reason="terminal",
                step_count=step_index,
                is_terminal=True,
                winner_id=get_winner(state),
                final_scores=compute_final_scores(state),
                move_log=tuple(move_log) if record_moves else (),
                final_state=state,
            )

        moves = get_legal_moves(state)
        if not moves:
            return FastSimulationResult(
                stopped_reason="no_legal_moves",
                step_count=step_index,
                is_terminal=False,
                winner_id=None,
                final_scores=None,
                move_log=tuple(move_log) if record_moves else (),
                final_state=state,
            )

        move = chooser(state, moves)
        if record_moves:
            move_log.append(
                FastSimulationStep(
                    step_index=step_index,
                    player_id=state.current_player_id,
                    phase=state.phase.value,
                    move_type=_move_type(move),
                )
            )
        state = apply_move(state, move)

    return FastSimulationResult(
        stopped_reason="max_steps",
        step_count=max_steps,
        is_terminal=state_is_terminal(state),
        winner_id=get_winner(state),
        final_scores=compute_final_scores(state) if state_is_terminal(state) else None,
        move_log=tuple(move_log) if record_moves else (),
        final_state=state,
    )


def run_simulation(
    session: GameSession,
    chooser: MoveChooser = choose_first_legal_move,
    *,
    max_steps: int = 500,
) -> SimulationResult:
    """Advance a session headlessly until terminal state or a stop condition."""

    replay_log: list[SimulationStep] = []

    while len(replay_log) < max_steps:
        view = build_game_view(session)
        if view.is_terminal:
            return SimulationResult(
                stopped_reason="terminal",
                step_count=len(replay_log),
                is_terminal=True,
                winner_id=view.winner_id,
                final_scores=view.final_scores,
                replay_log=tuple(replay_log),
                replay_context=None,
            )
        if not view.legal_moves:
            return SimulationResult(
                stopped_reason="no_legal_moves",
                step_count=len(replay_log),
                is_terminal=False,
                winner_id=None,
                final_scores=None,
                replay_log=tuple(replay_log),
                replay_context=None,
            )

        move = chooser(session, view)
        move_view = _match_legal_move(view.legal_moves, move)
        replay_log.append(
            SimulationStep(
                step_index=len(replay_log),
                player_id=session.state.current_player_id,
                round_number=session.state.round_number,
                phase=session.state.phase.value,
                prompts=view.prompts,
                move_type=move_view.move_type,
                label=move_view.label,
                payload=move_view.payload,
            )
        )
        session.submit_move(move)

    final_view = build_game_view(session)
    return SimulationResult(
        stopped_reason="max_steps",
        step_count=len(replay_log),
        is_terminal=final_view.is_terminal,
        winner_id=final_view.winner_id,
        final_scores=final_view.final_scores,
        replay_log=tuple(replay_log),
        replay_context=None,
    )


def run_simulation_from_files(
    *,
    board_path: Path,
    card_path: Path,
    setup_path: Path,
    player_ids: Sequence[str],
    seed: int | None = None,
    chooser: MoveChooser = choose_first_legal_move,
    max_steps: int = 500,
) -> SimulationResult:
    """Create a session from files and run a headless simulation."""

    session = GameSession.from_files(
        board_path=board_path,
        card_path=card_path,
        setup_path=setup_path,
        player_ids=player_ids,
        seed=seed,
    )
    result = run_simulation(session, chooser, max_steps=max_steps)
    return SimulationResult(
        stopped_reason=result.stopped_reason,
        step_count=result.step_count,
        is_terminal=result.is_terminal,
        winner_id=result.winner_id,
        final_scores=result.final_scores,
        replay_log=result.replay_log,
        replay_context=ReplayContext(
            board_path=str(board_path),
            card_path=str(card_path),
            setup_path=str(setup_path),
            player_ids=tuple(player_ids),
            seed=seed,
        ),
    )


def replay_payload(result: SimulationResult) -> dict[str, object]:
    """Return a JSON-serializable replay payload."""

    payload: dict[str, object] = {
        "stopped_reason": result.stopped_reason,
        "step_count": result.step_count,
        "is_terminal": result.is_terminal,
        "winner_id": result.winner_id,
        "final_scores": result.final_scores,
        "replay_log": [asdict(step) for step in result.replay_log],
    }
    if result.replay_context is not None:
        payload["replay_context"] = asdict(result.replay_context)
    return payload


def write_replay_log(path: Path, result: SimulationResult) -> None:
    """Write a simulation replay log to disk as JSON."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(replay_payload(result), handle, indent=2)
        handle.write("\n")


def replay_views_from_payload(
    payload: dict[str, object],
    *,
    board_path: Path | None = None,
    card_path: Path | None = None,
    setup_path: Path | None = None,
    player_ids: Sequence[str] | None = None,
    seed: int | None = None,
) -> tuple[GameView, ...]:
    """Rebuild ordered game views from a serialized replay payload."""

    resolved = _resolve_replay_context(
        payload,
        board_path=board_path,
        card_path=card_path,
        setup_path=setup_path,
        player_ids=player_ids,
        seed=seed,
    )
    session = GameSession.from_files(
        board_path=Path(resolved.board_path),
        card_path=Path(resolved.card_path),
        setup_path=Path(resolved.setup_path),
        player_ids=resolved.player_ids,
        seed=resolved.seed,
    )

    replay_entries = payload.get("replay_log")
    if not isinstance(replay_entries, list):
        raise ValueError("Replay payload must include replay_log as a list")

    views: list[GameView] = [build_game_view(session)]
    for entry in replay_entries:
        if not isinstance(entry, dict):
            raise ValueError("Replay log entry must be an object")
        step_payload = entry.get("payload")
        if not isinstance(step_payload, dict):
            raise ValueError("Replay step payload must be an object")
        move = MOVE_ADAPTER.validate_python(step_payload)
        session.submit_move(move)
        views.append(build_game_view(session))
    return tuple(views)


def _match_legal_move(legal_moves: tuple[LegalMoveView, ...], move: Move) -> LegalMoveView:
    for legal_move in legal_moves:
        if legal_move.move == move:
            return legal_move
    raise ValueError("Move chooser returned a move that is not currently legal")


def _resolve_replay_context(
    payload: dict[str, object],
    *,
    board_path: Path | None,
    card_path: Path | None,
    setup_path: Path | None,
    player_ids: Sequence[str] | None,
    seed: int | None,
) -> ReplayContext:
    context_payload = payload.get("replay_context")
    if isinstance(context_payload, dict):
        payload_player_ids = context_payload.get("player_ids")
        parsed_player_ids = ()
        if isinstance(payload_player_ids, list):
            parsed_player_ids = tuple(str(player_id) for player_id in payload_player_ids)

        payload_seed = context_payload.get("seed")
        parsed_seed = int(payload_seed) if isinstance(payload_seed, int) else None

        payload_board = context_payload.get("board_path")
        payload_card = context_payload.get("card_path")
        payload_setup = context_payload.get("setup_path")
        if isinstance(payload_board, str) and isinstance(payload_card, str) and isinstance(payload_setup, str):
            return ReplayContext(
                board_path=payload_board,
                card_path=payload_card,
                setup_path=payload_setup,
                player_ids=parsed_player_ids,
                seed=parsed_seed,
            )

    if board_path is None or card_path is None or setup_path is None or player_ids is None:
        raise ValueError(
            "Replay payload is missing replay_context; provide board_path, card_path, setup_path, and player_ids"
        )

    return ReplayContext(
        board_path=str(board_path),
        card_path=str(card_path),
        setup_path=str(setup_path),
        player_ids=tuple(player_ids),
        seed=seed,
    )


def _parse_player_ids(raw_player_ids: str) -> list[str]:
    player_ids = [player_id.strip() for player_id in raw_player_ids.split(",") if player_id.strip()]
    if not player_ids:
        raise ValueError("At least one player id is required")
    return player_ids


def main() -> None:
    """Run a headless simulation from JSON files."""

    parser = argparse.ArgumentParser(description="Run a headless Tyrants simulation")
    parser.add_argument("--players", default="p1,p2", help="Comma-separated player ids")
    parser.add_argument("--seed", type=int, default=1, help="RNG seed for game setup")
    parser.add_argument("--policy", choices=["first", "random"], default="first")
    parser.add_argument("--policy-seed", type=int, default=1, help="RNG seed for random move choice")
    parser.add_argument("--max-steps", type=int, default=200)
    parser.add_argument("--board-path", type=Path, default=DEFAULT_BOARD_PATH)
    parser.add_argument("--card-path", type=Path, default=DEFAULT_CARD_PATH)
    parser.add_argument("--setup-path", type=Path, default=DEFAULT_SETUP_PATH)
    parser.add_argument("--replay-log-path", type=Path)
    args = parser.parse_args()

    chooser = choose_first_legal_move
    if args.policy == "random":
        chooser = make_random_legal_move_chooser(args.policy_seed)

    result = run_simulation_from_files(
        board_path=args.board_path,
        card_path=args.card_path,
        setup_path=args.setup_path,
        player_ids=_parse_player_ids(args.players),
        seed=args.seed,
        chooser=chooser,
        max_steps=args.max_steps,
    )

    print(f"Stopped: {result.stopped_reason}")
    print(f"Steps: {result.step_count}")
    if result.final_scores is not None:
        for player_id, score in sorted(result.final_scores.items()):
            print(f"  {player_id}: {score}")
    print(f"Winner: {result.winner_id if result.winner_id is not None else 'tie'}")

    if args.replay_log_path is not None:
        write_replay_log(args.replay_log_path, result)
        print(f"Replay log written to {args.replay_log_path}")


if __name__ == "__main__":
    main()
