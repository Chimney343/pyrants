"""One pyspiel-free handle for every Python caller (ADR-0011).

``GameHandle`` owns one game: the loaded definition, the current C state, the
player ids and the shuffle seed. Every value crossing its interface is a Python
value or a ``Move`` value object -- no ``CState``, no ctypes struct, no raw
pointer -- so a future C-side handle can replace the body without a caller
moving (ADR-0011, condition 1).

Failures are raised, never returned, from one ``RuntimeError`` family in
:mod:`engine_c.bindings.errors`.

Nothing delegates to the handle yet: brief F1 builds it and its tests only.
"""

from __future__ import annotations

import ctypes
from collections.abc import Sequence
from pathlib import Path

from . import engine_bindings
from .ce_api import CEngine, CMoveWrapper, CState
from .errors import (
    EngineApplyRejected,
    EngineCloneFailed,
    EngineDestroyedError,
    EngineDeterminizeFailed,
    EngineSetupFailed,
    MoveCapacityError,
)

__all__ = [
    "Definition",
    "GameHandle",
    "Move",
    "MoveCapacityError",
    "EngineApplyRejected",
    "EngineCloneFailed",
    "EngineDeterminizeFailed",
    "EngineDestroyedError",
    "EngineSetupFailed",
]

# ``Move`` is today's wrapper, not a second object: ``legal_moves`` sits on the
# search's hot path, and every public value a caller needs (``move_type``,
# ``data``, ``to_payload``) already lives there. The ctypes struct keeps its own
# name, ``engine_bindings.Move``, and never crosses this interface.
Move = CMoveWrapper

_VIEW_BUFFER_BYTES = 32 * 1024
_SAVE_BUFFER_BYTES = 256 * 1024

_DEFAULT_DEFINITION: Definition | None = None


class Definition:
    """A loaded game definition: catalog, board and setup, and their arena.

    One definition can start many games, which is what keeps the ten existing
    ``CEngine`` setup sites from turning into ten definition loads once F2 moves
    them. The C definition and its arena stay inside ``CEngine``; this value is
    only the Python owner.
    """

    __slots__ = ("_engine", "catalog_path", "board_path", "setup_path", "setup_data_json")

    def __init__(
        self,
        engine: CEngine,
        *,
        catalog_path: str,
        board_path: str,
        setup_path: str,
        setup_data_json: str,
    ) -> None:
        self._engine = engine
        self.catalog_path = catalog_path
        self.board_path = board_path
        self.setup_path = setup_path
        self.setup_data_json = setup_data_json

    @classmethod
    def load(
        cls,
        *,
        board_path: str | Path,
        card_path: str | Path,
        setup_path: str | Path,
        setup_data_json: str = "",
    ) -> Definition:
        """Load a definition, or raise :class:`EngineSetupFailed`."""
        engine = CEngine()
        try:
            engine.initialize(
                catalog_path=str(card_path),
                board_path=str(board_path),
                setup_path=str(setup_path),
                setup_data_json=setup_data_json,
            )
        except Exception as exc:  # the C loader reports a bare RuntimeError
            raise EngineSetupFailed(
                f"could not load the game definition from {board_path} / "
                f"{card_path} / {setup_path}: {exc}"
            ) from exc
        return cls(
            engine,
            catalog_path=str(card_path),
            board_path=str(board_path),
            setup_path=str(setup_path),
            setup_data_json=setup_data_json,
        )


def default_definition() -> Definition:
    """The process-wide definition for the packaged data set, loaded once."""
    global _DEFAULT_DEFINITION
    if _DEFAULT_DEFINITION is None:
        engine = CEngine()
        try:
            engine.initialize()
        except Exception as exc:
            raise EngineSetupFailed(f"could not load the default game definition: {exc}") from exc
        _DEFAULT_DEFINITION = Definition(
            engine,
            catalog_path=str(engine._catalog_path),
            board_path=str(engine._board_path),
            setup_path=str(engine._setup_path),
            setup_data_json="",
        )
    return _DEFAULT_DEFINITION


class GameHandle:
    """One game, driven entirely through Python values (ADR-0011)."""

    __slots__ = ("_definition", "_engine", "_state", "_player_ids", "_seed", "_destroyed")

    def __init__(
        self,
        definition: Definition,
        state: CState,
        player_ids: Sequence[str],
        seed: int,
    ) -> None:
        self._definition = definition
        self._engine = definition._engine
        self._state: CState | None = state
        self._player_ids = tuple(player_ids)
        self._seed = seed
        self._destroyed = False

    # -- setup ------------------------------------------------------------

    @classmethod
    def new(
        cls,
        player_ids: Sequence[str],
        seed: int = 0,
        *,
        definition: Definition | None = None,
    ) -> GameHandle:
        """Start a game from a definition (the default one when *definition* is None)."""
        definition = definition if definition is not None else default_definition()
        players = tuple(player_ids)
        if not players:
            raise EngineSetupFailed("a game needs at least one player")
        try:
            state = definition._engine.create_game(list(players), seed)
        except Exception as exc:
            raise EngineSetupFailed(f"could not start a game: {exc}") from exc
        return cls(definition, state, players, seed)

    @classmethod
    def from_files(
        cls,
        *,
        board_path: str | Path,
        card_path: str | Path,
        setup_path: str | Path,
        setup_data_json: str = "",
        player_ids: Sequence[str],
        seed: int = 0,
    ) -> GameHandle:
        """Load a definition from JSON files and start a game from it."""
        definition = Definition.load(
            board_path=board_path,
            card_path=card_path,
            setup_path=setup_path,
            setup_data_json=setup_data_json,
        )
        return cls.new(player_ids, seed, definition=definition)

    # -- lifetime ---------------------------------------------------------

    @property
    def destroyed(self) -> bool:
        return self._destroyed

    def destroy(self) -> None:
        """Free the C state. Safe to call twice."""
        if self._destroyed:
            return
        self._destroyed = True
        state, self._state = self._state, None
        if state is not None:
            self._engine.destroy(state)

    def __enter__(self) -> GameHandle:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.destroy()

    def _require_live(self) -> CState:
        if self._destroyed or self._state is None:
            raise EngineDestroyedError("this GameHandle was destroyed")
        return self._state

    # -- identity ---------------------------------------------------------

    @property
    def player_ids(self) -> tuple[str, ...]:
        return self._player_ids

    @property
    def seed(self) -> int:
        return self._seed

    # -- apply ------------------------------------------------------------

    def apply(self, move: Move) -> None:
        """Apply *move*, mutating this handle, or raise :class:`EngineApplyRejected`."""
        state = self._require_live()
        if not isinstance(move, CMoveWrapper):
            raise TypeError(f"apply expects a Move, got {type(move).__name__}")
        new_state = self._engine.apply(state, move)
        if new_state is None:
            raise EngineApplyRejected(
                f"move rejected in phase {state.phase}, round {state.round_number}, "
                f"player {state.current_player_id}: {move}"
            )
        # ``engine_apply`` clones internally and returns the successor, so the
        # predecessor is ours to free. ``CSession.submit_move`` and
        # ``CEngineAdapter.apply`` do the same; skipping it leaks one arena per
        # move, which is the whole reason PyRantsCState grew a __del__.
        self._engine.destroy(state)
        self._state = new_state

    # -- clone and determinize -------------------------------------------

    def clone(self) -> GameHandle:
        """A copy that shares the definition, never the state (F-042)."""
        state = self._require_live()
        cloned_ptr = engine_bindings._lib.engine_clone(state.ptr)
        if not cloned_ptr:
            raise EngineCloneFailed("engine_clone returned NULL")
        return GameHandle(
            self._definition, CState(cloned_ptr), self._player_ids, self._seed
        )

    def determinize(self, observing_player_id: str, seed: int) -> GameHandle:
        """A world where the observer's hidden knowledge is one resampling."""
        state = self._require_live()
        world = self._engine.determinize(state, observing_player_id, seed)
        if world is None:
            raise EngineDeterminizeFailed(
                f"engine_determinize returned NULL for {observing_player_id!r}"
            )
        return GameHandle(self._definition, world, self._player_ids, self._seed)

    # -- moves ------------------------------------------------------------

    def legal_moves(self) -> list[Move]:
        """Applicable moves; raises :class:`MoveCapacityError` above the capacity."""
        return self._engine.legal_moves(self._require_live())

    def display_moves(self) -> list[tuple[Move, bool]]:
        """Viewer-facing moves, including greyed-out display-only entries."""
        return self._engine.display_moves(self._require_live())

    # -- views and queries ------------------------------------------------

    def player_view(self, player_id: str) -> str:
        """*player_id*'s view as JSON; ``KeyError`` for an unknown player."""
        return self._engine.player_view_json(self._require_live(), player_id)

    def infostate_key(self, player_id: str) -> tuple[int, int]:
        """128-bit fingerprint of *player_id*'s information state."""
        state = self._require_live()
        if player_id not in self._player_ids:
            raise KeyError(player_id)
        out = (ctypes.c_uint64 * 2)()
        player_sym = engine_bindings._lib.intern(player_id.encode())
        engine_bindings._lib.engine_infostate_hash(state.ptr, player_sym, out)
        return int(out[0]), int(out[1])

    def phase(self) -> str:
        return self._require_live().phase

    def round_number(self) -> int:
        return self._require_live().round_number

    def current_player_id(self) -> str:
        return self._require_live().current_player_id

    def is_terminal(self) -> bool:
        return self._engine.is_terminal(self._require_live())

    def scores(self) -> dict[str, int]:
        """Every player's score as the engine tallies it right now."""
        return self._engine.compute_final_scores(self._require_live())

    def winner(self) -> str | None:
        """The winner, or ``None`` while the game runs or on a tie."""
        state = self._require_live()
        if not self._engine.is_terminal(state):
            return None
        return self._engine.winner(state)

    def rollout(self, seed: int, max_length: int) -> tuple[bool, dict[str, int]]:
        """A whole random game from this state, without mutating it."""
        return self._engine.random_rollout(self._require_live(), seed, max_length)

    # -- scenario documents ----------------------------------------------

    def save_scenario(self, path: str | Path) -> None:
        """Write the engine's own scenario document (``saveload.c``)."""
        state = self._require_live()
        raw = self._serialize(state)
        Path(path).write_text(raw, encoding="utf-8")

    @classmethod
    def load_scenario(cls, path: str | Path, *, seed: int | None = None) -> GameHandle:
        """Read a scenario document back into a handle, or raise ``EngineSetupFailed``."""
        try:
            document = Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            raise EngineSetupFailed(f"could not read scenario {path}: {exc}") from exc

        definition_block = _definition_block(document)
        definition = Definition.load(
            board_path=definition_block["board_path"],
            card_path=definition_block["catalog_path"],
            setup_path=definition_block["setup_path"],
        )
        engine = definition._engine
        move_count = ctypes.c_int(0)
        state_ptr = engine_bindings._lib.engine_deserialize_state(
            document.encode(),
            engine._catalog_json.encode(),
            engine._arena,
            ctypes.byref(move_count),
        )
        if not state_ptr:
            raise EngineSetupFailed(f"could not deserialize scenario {path}")
        state = CState(state_ptr)
        player_ids = tuple(state.player_ids)
        game_seed = seed if seed is not None else int(state._s.shuffle_seed)
        return cls(definition, state, player_ids, game_seed)

    def _serialize(self, state: CState) -> str:
        engine = self._engine
        catalog_path = self._definition.catalog_path
        board_path = self._definition.board_path
        setup_path = self._definition.setup_path

        def call(cap: int) -> tuple[int, bytes]:
            buf = ctypes.create_string_buffer(cap)
            needed = engine_bindings._lib.engine_serialize_state(
                state.ptr,
                catalog_path.encode(),
                board_path.encode(),
                setup_path.encode(),
                0,
                1 if engine.is_terminal(state) else 0,
                buf,
                cap,
            )
            return needed, buf.raw

        needed, raw = call(_SAVE_BUFFER_BYTES)
        if needed > _SAVE_BUFFER_BYTES:
            needed, raw = call(needed)
        return raw.split(b"\0", 1)[0].decode("utf-8")


def _definition_block(document: str) -> dict[str, str]:
    """The ``definition`` block of a scenario document, validated."""
    import json

    try:
        parsed = json.loads(document)
    except json.JSONDecodeError as exc:
        raise EngineSetupFailed(f"scenario is not valid JSON: {exc}") from exc
    block = parsed.get("definition") if isinstance(parsed, dict) else None
    if not isinstance(block, dict):
        raise EngineSetupFailed("scenario has no definition block")
    missing = [key for key in ("catalog_path", "board_path", "setup_path") if key not in block]
    if missing:
        raise EngineSetupFailed(f"scenario definition is missing {missing}")
    return {key: str(block[key]) for key in ("catalog_path", "board_path", "setup_path")}
