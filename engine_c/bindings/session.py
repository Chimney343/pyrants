"""C-engine session wrapper — mirrors GameSession API but uses the C engine DLL.

Provides the same interface as game_session.GameSession so consumers
(game_view, game_simulation) can swap engines transparently.

Usage:
    from engine_c.bindings.session import CSession
    from engine_c.bindings.ce_api import CEngine

    eng = CEngine()
    eng.initialize()
    session = CSession(eng, ["p1", "p2"], seed=42)

    for move in session.legal_moves():
        session.submit_move(move)
        break

    print(session.is_terminal())
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .ce_api import CEngine, CMoveWrapper, CState


@dataclass(frozen=True)
class CSessionSnapshot:
    """View of the current C-engine session state."""

    phase: str
    current_player_id: str
    round_number: int
    legal_move_count: int
    is_terminal: bool
    winner_id: str | None
    final_scores: dict
    resource_power: int
    resource_influence: int


class CSession:
    """Own the current C-engine state and move history for one game session.

    Mirrors game_session.GameSession API.
    """

    def __init__(
        self,
        engine: CEngine,
        player_ids: Sequence[str],
        seed: int = 0,
    ) -> None:
        self._engine = engine
        self._player_ids = list(player_ids)
        self._seed = seed
        self._state: CState = engine.create_game(player_ids, seed)
        self._move_count = 0

    @classmethod
    def from_files(
        cls,
        *,
        board_path: Path,
        card_path: Path,
        setup_path: Path,
        player_ids: Sequence[str],
        seed: int | None = None,
    ) -> CSession:
        """Create a session by loading definitions from JSON files."""
        eng = CEngine()
        eng.initialize(
            catalog_path=str(card_path),
            board_path=str(board_path),
            setup_path=str(setup_path),
        )
        return cls(eng, list(player_ids), seed=seed or 0)

    @property
    def state(self) -> CState:
        return self._state

    @property
    def move_count(self) -> int:
        return self._move_count

    def legal_moves(self) -> list[CMoveWrapper]:
        if self.is_terminal():
            return []
        return self._engine.legal_moves(self._state)

    def is_terminal(self) -> bool:
        return self._engine.is_terminal(self._state)

    def winner_id(self) -> str | None:
        if not self.is_terminal():
            return None
        return self._engine.winner(self._state)

    def final_scores(self) -> dict:
        if not self.is_terminal():
            return {}
        return self._engine.compute_final_scores(self._state)

    def snapshot(self) -> CSessionSnapshot:
        terminal = self.is_terminal()
        return CSessionSnapshot(
            phase=self._state.phase,
            current_player_id=self._state.current_player_id,
            round_number=self._state.round_number,
            legal_move_count=len(self.legal_moves()) if not terminal else 0,
            is_terminal=terminal,
            winner_id=self.winner_id() if terminal else None,
            final_scores=self.final_scores() if terminal else {},
            resource_power=self._state.resource_power,
            resource_influence=self._state.resource_influence,
        )

    def submit_move(self, move: CMoveWrapper) -> CState | None:
        new_state = self._engine.apply(self._state, move)
        if new_state is None:
            return None
        self._engine.destroy(self._state)
        self._state = new_state
        self._move_count += 1
        return self._state

    def destroy(self):
        if self._state:
            self._engine.destroy(self._state)
            self._state = None

    @staticmethod
    def save_to_string(
        state: CState,
        *,
        move_count: int = 0,
        is_terminal: bool = False,
        catalog_path: str = "data/cards/catalog.json",
        board_path: str = "data/boards/tyrants_of_the_underdark.json",
        setup_path: str = "data/decks/base_setup.json",
    ) -> str:
        """Serialize a CState to a JSON scenario string."""
        import ctypes

        from .engine_bindings import _lib

        buf_size = 256 * 1024
        buf = ctypes.create_string_buffer(buf_size)
        _lib.engine_serialize_state(
            state._ptr,
            catalog_path.encode(), board_path.encode(), setup_path.encode(),
            move_count, 1 if is_terminal else 0,
            buf, buf_size,
        )
        return buf.value.decode()

    def save(self, path: str) -> None:
        """Serialize the current game state to a JSON scenario file."""
        catalog_path = self._engine._catalog_path or "data/cards/catalog.json"
        board_path = self._engine._board_path or "data/boards/tyrants_of_the_underdark.json"
        setup_path = self._engine._setup_path or "data/decks/base_setup.json"

        raw = self.save_to_string(
            self._state,
            move_count=self._move_count,
            is_terminal=self.is_terminal(),
            catalog_path=catalog_path,
            board_path=board_path,
            setup_path=setup_path,
        )
        with open(path, "w", encoding="utf-8") as f:
            f.write(raw)

    @classmethod
    def load(cls, path: str, engine: CEngine = None) -> CSession:
        """Deserialize a JSON scenario file into a new CSession."""
        import ctypes

        from .ce_api import CState
        from .engine_bindings import _lib, c_int

        with open(path, encoding="utf-8") as f:
            json_text = f.read()

        if engine is None:
            engine = CEngine()
            engine.initialize()

        arena = engine._arena
        move_count = c_int(0)
        state_ptr = _lib.engine_deserialize_state(
            json_text.encode(), None, arena, ctypes.byref(move_count),
        )
        if not state_ptr:
            raise RuntimeError(f"Failed to deserialize scenario from {path}")

        session = cls.__new__(cls)
        session._engine = engine
        session._player_ids = []
        session._seed = 0
        session._state = CState(state_ptr)
        session._move_count = move_count.value
        return session


def run_c_simulation(
    player_ids: Sequence[str],
    seed: int = 0,
    max_steps: int = 500,
    verbose: bool = False,
    engine: CEngine | None = None,
) -> dict:
    """Run a headless simulation using the C engine. Returns summary dict."""
    if engine is None:
        engine = CEngine()
        engine.initialize()

    session = CSession(engine, list(player_ids), seed)
    step = 0

    while step < max_steps:
        if session.is_terminal():
            break

        moves = session.legal_moves()
        if not moves:
            break

        move = moves[0]
        result = session.submit_move(move)
        if result is None:
            # Try the end_main_phase move which should always work
            for m in moves:
                if m.move_type == "end_main_phase":
                    result = session.submit_move(m)
                    if result is not None:
                        if verbose:
                            print(f"  step {step}: end_main_phase (fallback)")
                        step += 1
                    break
            if result is None:
                if verbose:
                    print(f"  step {step}: {move.move_type} FAILED, stopping")
                break
        else:
            step += 1

        if verbose and step % 50 == 0:
            print(f"  step {step}: {move.move_type}")

    winner = session.winner_id()
    terminal = session.is_terminal()
    scores = session.final_scores() if terminal else {}
    session.destroy()

    return {
        "steps": step,
        "terminal": terminal,
        "winner": winner,
        "scores": scores,
        "stopped_reason": "terminal" if terminal else ("max_steps" if step >= max_steps else "no_moves"),
    }
