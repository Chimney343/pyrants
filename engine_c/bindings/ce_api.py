"""Pythonic API wrapper for the engine_c DLL.

Provides functions that mirror engine.rules and engine.state APIs so
consumers (game_session, game_simulation) can swap between Python and C
engines via an environment variable: PYRANTS_ENGINE=c

Usage:
    from engine_c.bindings.ce_api import CEngine
    eng = CEngine()
    state = eng.create_game(["player_1", "player_2"])
    moves = eng.legal_moves(state)
    next_state = eng.apply(state, moves[0])
"""

import ctypes
from pathlib import Path

from game_setup.loaders import assemble_catalog_text

from .engine_bindings import (
    MAX_PLAYERS,
    MOVE_ACTIVATE_ABILITY,
    MOVE_ASSASSINATE,
    MOVE_DECLINE_ABILITY,
    MOVE_DEPLOY,
    MOVE_END_MAIN_PHASE,
    MOVE_INITIAL_PLACEMENT,
    MOVE_PLAY_CARD,
    MOVE_PROMOTE_CARD,
    MOVE_RECRUIT,
    MOVE_RESOLVE_CLEANUP,
    MOVE_RESOLVE_END_OF_TURN,
    MOVE_RESOLVE_GENERIC,
    MOVE_RETURN_SPY,
    MOVE_SKIP_PROMOTE,
    PHASE_CLEANUP,
    PHASE_DRAW,
    PHASE_END_OF_TURN,
    PHASE_GAME_OVER,
    PHASE_MAIN,
    PHASE_SETUP,
    _lib,
)
from .engine_bindings import (
    Move as CMove,
)

_PHASE_MAP = {
    PHASE_SETUP: "setup",
    PHASE_DRAW: "draw",
    PHASE_MAIN: "main",
    PHASE_END_OF_TURN: "end_of_turn",
    PHASE_CLEANUP: "cleanup",
    PHASE_GAME_OVER: "game_over",
}

_MOVE_TYPE_MAP = {
    MOVE_PLAY_CARD: "play_card",
    MOVE_END_MAIN_PHASE: "end_main_phase",
    MOVE_RESOLVE_END_OF_TURN: "resolve_end_of_turn",
    MOVE_RESOLVE_CLEANUP: "resolve_cleanup",
    MOVE_ASSASSINATE: "assassinate",
    MOVE_DEPLOY: "deploy",
    MOVE_RECRUIT: "recruit",
    MOVE_RETURN_SPY: "return_spy",
    MOVE_ACTIVATE_ABILITY: "activate_ability",
    MOVE_DECLINE_ABILITY: "decline_ability",
    MOVE_PROMOTE_CARD: "promote_card",
    MOVE_SKIP_PROMOTE: "skip_promote",
    MOVE_RESOLVE_GENERIC: "resolve_generic",
    MOVE_INITIAL_PLACEMENT: "initial_placement",
}


def _sym_str(sym) -> str | None:
    if sym == 0:
        return None
    return _lib.intern_str(sym).decode()


def _data_dir():
    """Return the data/ directory relative to the project root."""
    return Path(__file__).parent.parent.parent / "data"


class CMoveWrapper:
    """Pythonic wrapper around a C Move struct.

    Extracts the ``data`` dict lazily — ctypes calls are only made when
    ``data`` is first accessed, not during construction.
    """

    __slots__ = ("_c_move", "_move_type", "_data")

    _NAME_NORMALIZE = {
        "activate_ability": "activate_card_ability",
        "decline_ability": "decline_card_ability",
        "resolve_generic": "resolve_generic_choice",
    }

    def __init__(self, c_move: CMove):
        self._c_move = c_move
        self._move_type = _MOVE_TYPE_MAP.get(c_move.type, "unknown")
        self._data = None

    def _extract_data(self):
        if self._data is not None:
            return
        m = self._c_move
        mt = self._move_type
        if mt == "play_card":
            self._data = {"card_id": _sym_str(m.data.play_card.card_id), "hand_index": m.data.play_card.hand_index}
        elif mt == "initial_placement":
            self._data = {"target_node_id": _sym_str(m.data.initial_placement.node_id)}
        elif mt == "assassinate":
            self._data = {
                "target_node_id": _sym_str(m.data.assassinate.target_node_id),
                "target_slot_index": m.data.assassinate.slot_index,
            }
        elif mt == "deploy":
            self._data = {
                "target_node_id": _sym_str(m.data.deploy.node_id),
                "troop_count": 1,
            }
        elif mt == "recruit":
            self._data = {"card_id": _sym_str(m.data.recruit.card_id)}
        elif mt == "return_spy":
            self._data = {
                "node_id": _sym_str(m.data.return_spy.node_id),
                "spy_owner_id": _sym_str(m.data.return_spy.spy_owner_id),
            }
        elif mt == "activate_ability":
            self._data = {
                "card_id": _sym_str(m.data.activate_ability.card_id),
                "ability_key": _sym_str(m.data.activate_ability.ability_key),
            }
        elif mt == "decline_ability":
            self._data = {
                "card_id": _sym_str(m.data.decline_ability.card_id),
                "ability_key": _sym_str(m.data.decline_ability.ability_key),
            }
        elif mt == "promote_card":
            self._data = {"card_id": _sym_str(m.data.promote_card.card_id)}
        elif mt == "skip_promote":
            self._data = {"source_card_id": _sym_str(m.data.skip_promote.source_card_id)}
        elif mt == "resolve_generic":
            self._data = {
                "action_id": _sym_str(m.data.resolve_generic.action_id),
                "target_id": _sym_str(m.data.resolve_generic.target_id),
                "selection_index": m.data.resolve_generic.selection_index,
            }
        else:
            self._data = {}

    @property
    def move_type(self) -> str:
        return self._move_type

    @property
    def data(self) -> dict:
        if self._data is None:
            self._extract_data()
        return self._data

    def __deepcopy__(self, memo):
        return self

    def __str__(self) -> str:
        data = self.data
        if data:
            return f"{self._move_type}({', '.join(f'{k}={v!r}' for k, v in data.items())})"
        return self._move_type

    def __repr__(self) -> str:
        return f"CMove({self._move_type}, {self.data})"

    def to_payload(self) -> dict:
        normalized = self._NAME_NORMALIZE.get(self._move_type, self._move_type)
        return {"move_type": normalized, **self.data}


class CState:
    """Pythonic wrapper around a C GameState pointer.

    Owns the underlying C state; call destroy() to free it.
    Provides read-only access to common state fields.
    """

    __slots__ = ("_ptr",)

    def __init__(self, ptr):
        self._ptr = ptr

    @property
    def ptr(self):
        return self._ptr

    @property
    def _s(self):
        return self._ptr.contents

    @property
    def definition(self):
        return self._s.definition

    @property
    def phase(self) -> str:
        return _PHASE_MAP.get(self._s.phase, "unknown")

    @property
    def current_player_id(self) -> str:
        return _sym_str(self._s.current_player_id) or ""

    @property
    def round_number(self) -> int:
        return self._s.round_number

    @property
    def player_count(self) -> int:
        return self._s.player_count

    @property
    def resource_power(self) -> int:
        return self._s.resource_pool.power

    @property
    def resource_influence(self) -> int:
        return self._s.resource_pool.influence

    def player_hand(self, index: int) -> list:
        p = self._s.players[index]
        return [_sym_str(p.hand[i]) for i in range(p.hand_count)]

    def player_deck(self, index: int) -> list:
        p = self._s.players[index]
        return [_sym_str(p.deck[i]) for i in range(p.deck_count)]

    def market_deck(self) -> list:
        """Return list of card ID strings in the (hidden) market deck."""
        m = self._s.market
        return [_sym_str(m.deck[i]) for i in range(m.deck_count)]

    def market_row(self) -> list:
        """Return list of card ID strings in the face-up market row."""
        m = self._s.market
        return [_sym_str(m.row[i]) for i in range(m.row_count)]

    def player_played(self, index: int) -> list:
        p = self._s.players[index]
        return [_sym_str(p.played_cards[i]) for i in range(p.played_cards_count)]

    def player_barracks(self, index: int) -> int:
        return self._s.players[index].barracks

    def player_score(self, index: int) -> int:
        return self._s.players[index].score

    def player_discard(self, index: int) -> list:
        """Return list of card ID strings in the player's discard pile."""
        p = self._s.players[index]
        return [_sym_str(p.discard_pile[i]) for i in range(p.discard_pile_count)]

    def player_inner_circle(self, index: int) -> list:
        """Return list of card ID strings in the player's inner circle."""
        p = self._s.players[index]
        return [_sym_str(p.inner_circle[i]) for i in range(p.inner_circle_count)]

    def player_trophy_hall(self, index: int) -> list:
        """Return list of owner ID strings in the player's trophy hall."""
        p = self._s.players[index]
        return [_sym_str(p.trophy_hall[i]) for i in range(p.trophy_hall_count)]

    @property
    def player_ids(self) -> list:
        """Return list of player ID strings in turn order."""
        return [_sym_str(self._s.player_ids[i]) for i in range(self._s.player_id_count)]

    @property
    def turn_order(self) -> list:
        """Return list of player ID strings in turn order."""
        return self.player_ids

    def player_index(self, player_id: str) -> int:
        """Return the index for a given player_id string."""
        return self.player_ids.index(player_id)

    @property
    def devour_pile(self) -> list:
        """Return list of card ID strings in the devour pile."""
        s = self._s
        return [_sym_str(s.devour_pile[i]) for i in range(s.devour_pile_count)]

    def __del__(self):
        if self._ptr:
            _lib.engine_destroy(self._ptr)
            self._ptr = None

    def destroy(self):
        if self._ptr:
            _lib.engine_destroy(self._ptr)
            self._ptr = None


class CEngine:
    """Pythonic C engine interface matching engine.rules + engine.state APIs.

    Usage:
        eng = CEngine()
        eng.initialize("data/cards", "data/boards/...", "data/decks/...")
        state = eng.create_game(["p1", "p2"], seed=42)
        moves = eng.legal_moves(state)
        state2 = eng.apply(state, moves[0])
        eng.destroy(state)
    """

    _globally_initialized = False
    _global_lock = __import__("threading").Lock()

    def __init__(self):
        self._definition = None
        self._arena = None
        self._initialized = False
        self._catalog_path = None
        self._catalog_json = None
        self._board_path = None
        self._setup_path = None

    def __del__(self):
        if self._arena:
            _lib.arena_destroy(self._arena)
            self._arena = None
        self._definition = None
        self._initialized = False

    def initialize(
        self,
        catalog_path: str | None = None,
        board_path: str | None = None,
        setup_path: str | None = None,
        setup_data_json: str = "",
    ) -> None:
        """Initialize the C engine: intern table, effect registry, game definition.

        If *setup_data_json* is a non-empty JSON string it replaces the setup
        loaded from *setup_path*, matching the Python engine's
        ``setup_data_json`` parameter.
        """
        if self._initialized:
            return

        with CEngine._global_lock:
            if not CEngine._globally_initialized:
                _lib.intern_init(4096)
                _lib.register_default_effects()
                CEngine._globally_initialized = True

        catalog_path = catalog_path or str(_data_dir() / "cards")
        board_path = board_path or str(_data_dir() / "boards" / "tyrants_of_the_underdark.json")
        setup_path = setup_path or str(_data_dir() / "decks" / "base_setup.json")

        self._catalog_path = catalog_path
        self._board_path = board_path
        self._setup_path = setup_path

        catalog_json = assemble_catalog_text(Path(catalog_path))

        self._arena = _lib.arena_create(16 * 1024 * 1024)
        self._definition = _lib.engine_load_definition_json(
            catalog_json.encode(), board_path.encode(), setup_path.encode(), self._arena
        )
        if not self._definition:
            raise RuntimeError("Failed to load game definition in C engine")

        self._catalog_json = catalog_json

        if setup_data_json:
            ret = _lib.engine_apply_setup_json(
                self._definition, setup_data_json.encode(), self._arena
            )
            if ret != 0:
                raise RuntimeError("Failed to apply setup_data_json in C engine")

        self._initialized = True

    def create_game(self, player_ids: list, seed: int = 0) -> CState:
        """Create a new game state. Mirrors build_initial_game_state()."""
        if not self._initialized:
            self.initialize()
        arr = (ctypes.c_char_p * len(player_ids))()
        for i, pid in enumerate(player_ids):
            arr[i] = pid.encode()
        gs = _lib.engine_create_game_definition(
            self._definition, arr, len(player_ids), seed
        )
        if not gs:
            raise RuntimeError("Failed to create game state in C engine")
        return CState(gs)

    def legal_moves(self, state: CState) -> list:
        """Return legal moves. Mirrors engine.rules.legal_moves()."""
        moves = (CMove * 1024)()
        n = _lib.engine_legal_moves(state.ptr, moves, 1024)
        return [CMoveWrapper(moves[i]) for i in range(n)]

    def apply(self, state: CState, move: CMoveWrapper) -> CState | None:
        """Apply a move. Mirrors engine.rules.apply(). Returns None on failure."""
        c_move = move._c_move
        result = _lib.engine_apply(state.ptr, ctypes.byref(c_move))
        if not result:
            return None
        return CState(result)

    def is_terminal(self, state: CState) -> bool:
        """Check if state is terminal. Mirrors engine.rules.is_terminal()."""
        return bool(_lib.engine_is_terminal(state.ptr))

    def winner(self, state: CState) -> str | None:
        """Return winner player id or None. Mirrors engine.rules.winner()."""
        score = ctypes.c_int()
        sym = _lib.engine_winner(state.ptr, ctypes.byref(score))
        return _sym_str(sym)

    def compute_final_scores(self, state: CState) -> dict:
        """Compute final scores. Mirrors engine.scoring.compute_final_scores()."""
        scores_arr = (ctypes.c_int * MAX_PLAYERS)()
        _lib.compute_final_scores(state.ptr, scores_arr)
        result = {}
        for i in range(state.player_count):
            pid = _sym_str(state._s.player_ids[i])
            result[pid] = scores_arr[i]
        return result

    def random_rollout(self, state: CState, seed: int, max_length: int) -> tuple[bool, dict]:
        """Run a whole random rollout to terminal (or max_length cutoff) in C.

        Mirrors PyrantsCState.returns(): the returned scores are always
        compute_final_scores(), the real tally at a terminal state and a
        score-the-game-as-if-it-ended-here estimate at a cut-off one.  The
        bool says which of the two it is; both are usable leaf values.
        """
        scores_arr = (ctypes.c_int * MAX_PLAYERS)()
        terminal = _lib.engine_random_rollout(
            state.ptr, ctypes.c_uint64(seed), ctypes.c_int(max_length), scores_arr
        )
        result = {}
        for i in range(state.player_count):
            pid = _sym_str(state._s.player_ids[i])
            result[pid] = scores_arr[i]
        return bool(terminal), result

    def determinize(self, state: CState, observing_player_id: str, seed: int) -> CState:
        """Clone state with opponent hidden zones reshuffled for observing player."""
        obs_sym = _lib.intern(observing_player_id.encode())
        result = _lib.engine_determinize(state.ptr, obs_sym, seed)
        if not result:
            return None
        return CState(result)

    def destroy(self, state: CState) -> None:
        """Free a C game state."""
        state.destroy()

    @staticmethod
    def available() -> bool:
        """Check if the engine_c DLL is loadable."""
        try:
            if not CEngine._globally_initialized:
                with CEngine._global_lock:
                    if not CEngine._globally_initialized:
                        _lib.intern_init(4096)
                        CEngine._globally_initialized = True
            return True
        except Exception:
            return False
