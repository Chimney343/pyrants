"""Shared session controller for local clients and simulations."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from engine.moves import Move
from engine.rules import apply as apply_move
from engine.rules import is_terminal as state_is_terminal
from engine.rules import legal_moves as get_legal_moves
from engine.rules import winner as get_winner
from engine.scoring import compute_final_scores
from engine.state import GameState
from game_setup.loaders import create_game_state_from_files, default_catalog_registry
from game_setup.scenarios import load_game_state_from_scenario


@dataclass(frozen=True)
class GameSessionSnapshot:
    """View of the current session state for UI or simulation consumers."""

    state: GameState
    legal_moves: tuple[Move, ...]
    move_count: int
    is_terminal: bool
    winner_id: str | None
    final_scores: dict[str, int] | None


class GameSession:
    """Own the current state and move history for one game session."""

    def __init__(self, initial_state: GameState) -> None:
        self._state = initial_state
        self._move_log: list[Move] = []

    @classmethod
    def from_files(
        cls,
        *,
        board_path: Path,
        card_path: Path,
        setup_path: Path,
        player_ids: Sequence[str] | Iterable[str],
        seed: int | None = None,
    ) -> GameSession:
        """Create a session by loading definitions from the standard JSON files."""

        return cls(
            create_game_state_from_files(
                board_path=board_path,
                card_path=card_path,
                setup_path=setup_path,
                player_ids=player_ids,
                seed=seed,
            )
        )

    @classmethod
    def from_scenario_file(cls, path: Path, *, force: bool = False) -> GameSession:
        """Create a session from a saved scenario JSON file. Pass force=True to override catalog version mismatch."""

        return cls(load_game_state_from_scenario(path, catalog_registry=default_catalog_registry(), force=force))

    @property
    def state(self) -> GameState:
        """Return the current immutable engine state."""

        return self._state

    @property
    def move_count(self) -> int:
        """Return how many engine moves have been applied in this session."""

        return len(self._move_log)

    @property
    def move_log(self) -> tuple[Move, ...]:
        """Return the applied moves in order."""

        return tuple(self._move_log)

    def legal_moves(self) -> tuple[Move, ...]:
        """Return the current engine-validated legal moves."""

        if self.is_terminal():
            return ()
        return tuple(get_legal_moves(self._state))

    def is_terminal(self) -> bool:
        """Return whether the current state has reached the game end."""

        return state_is_terminal(self._state)

    def winner_id(self) -> str | None:
        """Return the winning player id if the session is terminal."""

        if not self.is_terminal():
            return None
        return get_winner(self._state)

    def final_scores(self) -> dict[str, int] | None:
        """Return final scores once the session has ended."""

        if not self.is_terminal():
            return None
        return dict(compute_final_scores(self._state))

    def snapshot(self) -> GameSessionSnapshot:
        """Return a structured view of the current session state."""

        is_terminal = self.is_terminal()
        final_scores = self.final_scores() if is_terminal else None
        return GameSessionSnapshot(
            state=self._state,
            legal_moves=self.legal_moves() if not is_terminal else (),
            move_count=self.move_count,
            is_terminal=is_terminal,
            winner_id=self.winner_id() if is_terminal else None,
            final_scores=final_scores,
        )

    def submit_move(self, move: Move) -> GameState:
        """Apply one engine move and make the resulting state current."""

        self._state = apply_move(self._state, move)
        self._move_log.append(move)
        return self._state
