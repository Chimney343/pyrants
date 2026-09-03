"""CEngineAdapter — wraps CState + CEngine for use by the OpenSpiel C backend.

Provides clone-via-replay, legal move enumeration, move application, terminal
checks, and public/private view serialization for information_state_string.

Views are built from CState properties rather than the C engine_public_view /
engine_private_view functions, which have struct-layout mismatches with the
Python ctypes definitions.
"""

from __future__ import annotations

import copy
import ctypes
import json
from collections.abc import Sequence

from .ce_api import CEngine, CMoveWrapper, CState
from .engine_bindings import CGameView, _lib, sym_str

_PHASE_NAMES = {0: "setup", 1: "draw", 2: "main", 3: "end_of_turn", 4: "cleanup", 5: "game_over"}


class CEngineAdapter:
    """Wraps a CState + CEngine for OpenSpiel integration.

    Tracks player_ids and shuffle_seed for clone-via-replay.
    The adapter owns the CState and provides mutation operations.
    """

    __slots__ = (
        "_state",
        "_engine",
        "_player_ids",
        "_shuffle_seed",
        "_player_id_to_index",
        "_board_cache",
        "_board_static",
        "_view_cache",
    )

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
        self._board_cache = None
        self._board_static = None
        self._view_cache = {}

    def __deepcopy__(self, memo):
        cloned_ptr = _lib.engine_clone(self._state._ptr)
        if not cloned_ptr:
            return self
        new_adapter = CEngineAdapter(
            CState(cloned_ptr), self._engine, self._player_ids, self._shuffle_seed
        )
        self._inherit_projection(new_adapter)
        memo[id(self)] = new_adapter
        return new_adapter

    def _inherit_projection(self, child) -> None:
        """Hand a child clone/determinization the parent's board projection.

        ``engine_clone`` is a byte copy and ``engine_determinize`` touches only
        hand/deck/discard/market + shuffle scalars (never the board — see
        ``engine_c/state.c:271-318``), so the child's board occupancy is
        identical to the parent's and the parent's ``_board_cache`` /
        ``_board_static`` can be shared by reference.

        Sharing by reference is safe because (a) a projection is only ever
        *replaced* wholesale (``apply()`` resets ``_board_cache`` to ``None``;
        ``_project_board_nodes`` builds a fresh list), never mutated in place,
        and (b) ``_board_nodes_view`` returns a deep copy, so an external caller
        cannot mutate the shared structure through one family member. The L1
        string cache is deliberately NOT inherited: determinize changes
        hand/deck/discard, so a stale per-player string would be wrong.
        """
        child._board_cache = self._board_cache
        child._board_static = self._board_static

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
        new_adapter = CEngineAdapter(
            new_state, self._engine, self._player_ids, self._shuffle_seed
        )
        self._inherit_projection(new_adapter)
        return new_adapter

    def clone_via_replay(self, move_history: list[CMoveWrapper]) -> CEngineAdapter:
        """Create a new adapter by replaying move_history from the same seed.

        No projection is inherited: ``create_game`` may build a different board
        definition, and replay re-applies every move from scratch.
        """
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
        self._board_cache = None
        self._view_cache.clear()

    def pending_generic_op(self) -> str | None:
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
        """Return a JSON string of the private view for *player_id*.

        The finished string is cached per player and cleared on ``apply()``/
        ``destroy()`` — the only two sites that change (or end) the C state.
        The inner ``_board_cache`` is kept as the layer that clone/determinize
        propagate (Phase 4); this string cache cannot propagate because
        determinize changes hand/deck/discard.
        """
        cached = self._view_cache.get(player_id)
        if cached is not None:
            return cached

        pub = self._build_public_dict()
        idx = self.player_index(player_id)
        p = self._state._s.players[idx]

        hand = [_sym_str(p.hand[i]) for i in range(p.hand_count)]
        discard = [_sym_str(p.discard_pile[i]) for i in range(p.discard_pile_count)]

        result = {
            "public": {**pub, "board_nodes": self._ensure_board_nodes()},
            "hand": hand,
            "discard": discard,
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
        view = json.dumps(result, sort_keys=True)
        self._view_cache[player_id] = view
        return view

    def _build_board_static(self, c_view) -> list[dict]:
        """Hoist the board-static node fields into a per-adapter template.

        ``node_id``/``control_vp``/``total_control_vp_per_turn`` are read from
        ``state->definition->board`` (immutable — ``engine_c/view.c:74-76``),
        so they cannot change for the life of the adapter's definition. Stored
        on the adapter (never in a module-level dict): two boards can share a
        node count, and a definition pointer can be freed and reused.
        """
        static: list[dict] = []
        for i in range(c_view.node_count):
            nv = c_view.nodes[i]
            static.append(
                {
                    "node_id": _sym_str(nv.node_id) or f"node_{i}",
                    "control_vp": nv.control_vp,
                    "total_control_vp_per_turn": nv.total_control_vp_per_turn,
                }
            )
        return static

    def _project_board_nodes(self) -> list[dict]:
        """Project the C board occupancy straight into the six ``board_nodes``
        output fields, bypassing ``view.build_c_board_view``.

        ``view.build_c_board_view`` additionally projects ``adjacent_to`` (196
        sym decodes per projection that no consumer reads) and ``kind``, plus
        the four current-player aggregates on ``CBoardViewData`` — all
        discarded here. ``node_id``/``control_vp``/``total_control_vp_per_turn``
        come from ``_board_static`` once it has been hoisted.

        Semantics preserved exactly from the general-purpose path:
        ``spies`` filters falsy entries and sorts them (skip the loop entirely
        when ``spy_count == 0``, the common case); ``troop_slots`` keeps its
        ``None`` entries, unsorted and unfiltered. A fresh ``CGameView`` is
        allocated per call — reusing a module-level ~83 KB buffer would save
        under a microsecond and introduce shared mutable state.
        """
        state_ptr = self._state._ptr
        c_view = CGameView()
        _lib.engine_build_view(state_ptr, ctypes.byref(c_view))

        static = self._board_static
        if static is None or len(static) != c_view.node_count:
            static = self._build_board_static(c_view)
            self._board_static = static

        nodes: list[dict] = []
        for i in range(c_view.node_count):
            nv = c_view.nodes[i]
            troops = [_sym_str(nv.troop_slots[j]) for j in range(nv.troop_slot_count)]
            if nv.spy_count:
                spies = []
                for j in range(nv.spy_count):
                    s = _sym_str(nv.spies[j])
                    if s:
                        spies.append(s)
                spies.sort()
            else:
                spies = []
            nodes.append(
                {
                    "node_id": static[i]["node_id"],
                    "troop_slots": troops,
                    "spies": spies,
                    "control_vp": static[i]["control_vp"],
                    "total_control_vp_per_turn": static[i]["total_control_vp_per_turn"],
                    "vp_tokens": nv.vp_tokens,
                }
            )
        self._board_cache = nodes
        return nodes

    def _ensure_board_nodes(self) -> list[dict]:
        """Return the cached projection by reference (internal hot path).

        The cached structure is never mutated in place — ``apply()`` resets
        ``_board_cache`` to ``None`` and a fresh projection is built on the
        next read — so handing it to ``json.dumps`` by reference is safe and
        avoids a per-call copy on the ``private_view_json`` hot path.
        """
        if self._board_cache is None:
            self._project_board_nodes()
        return self._board_cache

    def _board_nodes_view(self) -> list[dict]:
        """Player-agnostic raw board occupancy. Only the per-node fields — never the
        current-player-scoped aggregates on CBoardViewData, which are relative to
        state->current_player_id, not whichever player_id is asking. See f011-fix-plan.md § 1.

        Returns a deep copy: the cached projection may be shared across a
        clone/determinize family (F-013 Part B Phase 4), so a caller mutating
        the returned list or its dicts must not corrupt the parent or siblings.
        """
        return copy.deepcopy(self._ensure_board_nodes())

    def destroy(self):
        if self._state:
            self._engine.destroy(self._state)
            self._state = None
        # A cached string must not outlive the state (T8): destroy() drops the
        # whole view cache so a stale read can never be served after teardown.
        self._view_cache.clear()
        self._board_cache = None


def _sym_str(sym) -> str | None:
    """Memoised sym→str (F-013 Part B); shared with ``engine_bindings.view``."""
    return sym_str(sym)
