"""CEngineAdapter — wraps CState + CEngine for use by the OpenSpiel C backend.

Provides clone-via-replay, legal move enumeration, move application, terminal
checks, and public/private view serialization for information_state_string.

Views are built from CState properties rather than the C engine_public_view /
engine_private_view functions, which have struct-layout mismatches with the
Python ctypes definitions.
"""

from __future__ import annotations

import json
from typing import Optional, Sequence

from .ce_api import CEngine, CState, CMoveWrapper, _sym_str
from .engine_bindings import _lib, MAX_PLAYERS

_PHASE_NAMES = {0: "setup", 1: "draw", 2: "main", 3: "end_of_turn", 4: "cleanup", 5: "game_over"}


class CEngineAdapter:
    """Wraps a CState + CEngine for OpenSpiel integration.

    Tracks player_ids and shuffle_seed for clone-via-replay.
    The adapter owns the CState and provides mutation operations.
    """

    __slots__ = ("_state", "_engine", "_player_ids", "_shuffle_seed", "_player_id_to_index")

    def __init__(
        self,
        c_state: CState,
        c_engine: CEngine,
        player_ids: Sequence[str],
        shuffle_seed: int,
    ):
        self._state = c_state
        self._engine = c_engine
        self._player_ids = list(player_ids)
        self._shuffle_seed = shuffle_seed
        self._player_id_to_index = {pid: i for i, pid in enumerate(player_ids)}

    def __deepcopy__(self, memo):
        cloned_ptr = _lib.engine_clone(self._state._ptr)
        if not cloned_ptr:
            return self
        new_adapter = CEngineAdapter(
            CState(cloned_ptr), self._engine, self._player_ids, self._shuffle_seed
        )
        memo[id(self)] = new_adapter
        return new_adapter

    @property
    def state(self) -> CState:
        return self._state

    @property
    def engine(self) -> CEngine:
        return self._engine

    @property
    def player_ids(self) -> list[str]:
        return self._player_ids

    @property
    def shuffle_seed(self) -> int:
        return self._shuffle_seed

    def determinize(self, observing_player_id: str, seed: int) -> CEngineAdapter:
        """Return a new adapter with opponent hidden zones reshuffled.

        The original state is not mutated — engine_determinize clones internally.
        Returns None if the C function fails (out of memory).
        """
        new_state = self._engine.determinize(self._state, observing_player_id, seed)
        if new_state is None:
            return None
        return CEngineAdapter(new_state, self._engine, self._player_ids, self._shuffle_seed)

    def clone_via_replay(self, move_history: list[CMoveWrapper]) -> CEngineAdapter:
        """Create a new adapter by replaying move_history from the same seed."""
        new_state = self._engine.create_game(self._player_ids, self._shuffle_seed)
        new_adapter = CEngineAdapter(new_state, self._engine, self._player_ids, self._shuffle_seed)
        for move in move_history:
            new_adapter.apply(move)
        return new_adapter

    def legal_moves(self) -> list[CMoveWrapper]:
        return self._engine.legal_moves(self._state)

    def apply(self, move: CMoveWrapper) -> None:
        """Apply a move, mutating this adapter's state. Raises RuntimeError on failure."""
        new_state = self._engine.apply(self._state, move)
        if new_state is None:
            # Capture diagnostic context before raising
            legal = self.legal_moves()
            legal_strs = [str(m) for m in legal]
            pg = self._state._ptr.contents.pending_generic
            pending_card_id = _sym_str(pg.contents.source_card_id) if pg else None
            raise RuntimeError(
                f"Failed to apply move: {move} | "
                f"pending_card_id={pending_card_id!r} "
                f"phase={self.phase()} round={self.round_number()} "
                f"current_player={self.current_player_id()} "
                f"is_terminal={self.is_terminal()} "
                f"legal_moves_count={len(legal)} "
                f"legal_moves={legal_strs[:10]}{'...' if len(legal) > 10 else ''}"
            )
        self._engine.destroy(self._state)
        self._state = new_state

    def pending_generic_op(self) -> Optional[str]:
        """Return the op of the currently active pending-generic action, if any.

        Mirrors ``pending_generic_active_action()`` (``engine_c/generic_runtime.c``):
        the *op* (e.g. ``"deploy_troops"``) of
        ``pending_generic.current_actions[next_action_index]`` — not the
        ``resolve_generic`` move's own ``action_id`` field, which holds the
        selected target (a site/route/troop/player id), never the action verb.
        Must be read before the move answering this choice is applied —
        ``next_action_index`` advances (or ``pending_generic`` is cleared)
        once it is.
        """
        pg = self._state._ptr.contents.pending_generic
        if not pg:
            return None
        p = pg.contents
        idx = p.next_action_index
        if idx < 0 or idx >= p.current_action_count:
            return None
        return _sym_str(p.current_actions[idx].op)

    def is_terminal(self) -> bool:
        return self._engine.is_terminal(self._state)

    def phase(self) -> str:
        return self._state.phase

    def current_player_id(self) -> str:
        return self._state.current_player_id

    def round_number(self) -> int:
        return self._state.round_number

    def player_index(self, player_id: str) -> int:
        return self._player_id_to_index[player_id]

    def player_score(self, index: int) -> int:
        return self._state.player_score(index)

    def final_scores(self) -> dict[str, int]:
        return self._engine.compute_final_scores(self._state)

    def random_rollout(self, seed: int, max_length: int) -> tuple[bool, dict[str, int]]:
        return self._engine.random_rollout(self._state, seed, max_length)

    def _build_public_dict(self) -> dict:
        """Build a JSON-serialisable public-view dict from CState properties."""
        s = self._state._s
        player_ids = self._player_ids

        summaries = {}
        for i, pid in enumerate(player_ids):
            p = s.players[i]
            summaries[pid] = {
                "hand_size": p.hand_count,
                "deck_size": p.deck_count,
                "discard_size": p.discard_pile_count,
                "devour_size": s.devour_pile_count,
                "played_size": p.played_cards_count,
                "inner_circle_size": p.inner_circle_count,
                "trophy_hall_size": p.trophy_hall_count,
                "inner_circle": [_sym_str(p.inner_circle[i]) for i in range(p.inner_circle_count)],
                "trophy_hall": [_sym_str(p.trophy_hall[i]) for i in range(p.trophy_hall_count)],
                "played_cards": [_sym_str(p.played_cards[i]) for i in range(p.played_cards_count)],
                "barracks": p.barracks,
                "spies_available": p.spies_available,
                "vp_tokens": p.vp_tokens,
                "score": p.score,
            }

        market_row = [
            _sym_str(s.market.row[i]) for i in range(s.market.row_count)
        ]

        return {
            "round_number": s.round_number,
            "phase": _PHASE_NAMES.get(s.phase, "unknown"),
            "current_player_id": self.current_player_id(),
            "turn_order": player_ids,
            "market_row": market_row,
            "market_deck_size": s.market.deck_count,
            "market_discard_size": s.market.discard_pile_count,
            "resource_power": s.resource_pool.power,
            "resource_influence": s.resource_pool.influence,
            "public_player_summaries": summaries,
        }

    def private_view_json(self, player_id: str) -> str:
        """Return a JSON string of the private view for *player_id*."""
        pub = self._build_public_dict()
        idx = self.player_index(player_id)
        p = self._state._s.players[idx]

        hand = [_sym_str(p.hand[i]) for i in range(p.hand_count)]

        result = {
            "public": pub,
            "hand": hand,
            "deck_size": p.deck_count,
            "discard_size": p.discard_pile_count,
            "devour_size": self._state._s.devour_pile_count,
            "played_cards": [_sym_str(p.played_cards[i]) for i in range(p.played_cards_count)],
            "inner_circle": [_sym_str(p.inner_circle[i]) for i in range(p.inner_circle_count)],
            "trophy_hall": [_sym_str(p.trophy_hall[i]) for i in range(p.trophy_hall_count)],
            "barracks": p.barracks,
            "spies_available": p.spies_available,
            "vp_tokens": p.vp_tokens,
            "score": p.score,
        }
        return json.dumps(result, sort_keys=True)

    def destroy(self):
        if self._state:
            self._engine.destroy(self._state)
            self._state = None


def _sym_str(sym) -> Optional[str]:
    if sym == 0:
        return None
    return _lib.intern_str(sym).decode()
