"""PyrantsCState(pyspiel.State) — adapts the C engine to the OpenSpiel state interface.

Holds a ``CEngineAdapter`` wrapping a C ``GameState*``. The initial chance node
selects a shuffle seed; after that the engine is fully initialized and all
further transitions are deterministic.
"""

from __future__ import annotations

import pyspiel

from engine_c.bindings.ce_api import CMoveWrapper
from engine_c.bindings.c_adapter import CEngineAdapter
from openspiel_pyrants.action_encoding_c import compute_c_action_map

_SEED_MIXER_MULTIPLIER = 2654435761
_SEED_MIXER_MASK = 0x7FFFFFFF


def _public_to_seed(action_id: int) -> int:
    return (action_id * _SEED_MIXER_MULTIPLIER) & _SEED_MIXER_MASK


class _EngineShim:
    """Minimal compatibility shim so ``PyrantsCState._engine`` mirrors
    ``PyrantsState._engine`` for the IS-MCTS runner script.

    Only exposes the attributes the runner actually accesses:
    ``round_number`` (int), ``phase`` (object with ``.value`` str), and
    ``players`` (dict-like with ``.items()`` and per-player ``.score``).
    """

    __slots__ = ("_adapter", "_game")

    def __init__(self, adapter: CEngineAdapter, game):
        self._adapter = adapter
        self._game = game

    @property
    def round_number(self) -> int:
        return self._adapter.round_number()

    @property
    def phase(self) -> _PhaseShim:
        return _PhaseShim(self._adapter.phase())

    @property
    def players(self) -> dict:
        pids = self._game.get_player_ids()
        return {pid: _PlayerShim(self._adapter.player_score(self._adapter.player_index(pid))) for pid in pids}


class _PhaseShim:
    __slots__ = ("value",)
    def __init__(self, value: str):
        self.value = value


class _PlayerShim:
    __slots__ = ("score",)
    def __init__(self, score: int):
        self.score = score


class PyrantsCState(pyspiel.State):
    def __init__(self, game):
        super().__init__(game)
        self._game = game
        self._adapter: CEngineAdapter | None = None
        self._pending_initial_chance = True
        self._cached_indexed_moves: list | None = None
        self._shuffle_seed: int = 0
        self._move_log: list[CMoveWrapper] = []
        self._history_actions: list[str] = []  # action-id strings for history_str()

    def __del__(self):
        """Destroy the underlying C state when this Python object is collected.

        Without this, every IS-MCTS cloned state leaks a 512 KB arena.
        With 200 sims × ~40 decisions × ~10 clones/rollout, that is ~40 GB
        of unreclaimed C memory per game.
        """
        adapter = getattr(self, "_adapter", None)
        if adapter is not None:
            try:
                adapter.destroy()
            except Exception:
                pass
            self._adapter = None

    @property
    def _engine(self):
        """Compatibility shim matching PyrantsState._engine (Pydantic GameState).

        The runner script accesses ``state._engine.round_number`` and
        ``state._engine.phase.value``.  Returns None when no adapter exists.
        """
        if self._adapter is None:
            return None
        return _EngineShim(self._adapter, self._game)

    def _player_index(self, player_id: str) -> int:
        return self._game.get_player_ids().index(player_id)

    def __deepcopy__(self, memo):
        new = PyrantsCState.__new__(PyrantsCState)
        pyspiel.State.__init__(new, self._game)
        new._game = self._game
        new._pending_initial_chance = self._pending_initial_chance
        new._cached_indexed_moves = None
        new._shuffle_seed = self._shuffle_seed
        new._move_log = list(self._move_log)
        new._history_actions = list(self._history_actions)
        if self._adapter is not None:
            new._adapter = self._adapter.clone_via_replay(self._move_log)
        else:
            new._adapter = None
        memo[id(self)] = new
        return new

    def current_player(self):
        if self._adapter is not None and self._adapter.is_terminal():
            return pyspiel.PlayerId.TERMINAL
        if self._pending_initial_chance:
            return pyspiel.PlayerId.CHANCE
        return self._player_index(self._adapter.current_player_id())

    def _legal_actions(self, player):
        if self._pending_initial_chance:
            return list(range(self._game.get_shuffle_seed_count()))
        if self._cached_indexed_moves is None:
            self._cached_indexed_moves = compute_c_action_map(self._adapter)
        return list(range(len(self._cached_indexed_moves)))

    def _apply_action(self, action):
        self._history_actions.append(str(int(action)))
        if self._pending_initial_chance:
            self._cached_indexed_moves = None
            seed = _public_to_seed(int(action))
            self._shuffle_seed = seed
            self._adapter = CEngineAdapter(
                self._game._c_engine.create_game(
                    self._game.get_player_ids(), seed
                ),
                self._game._c_engine,
                self._game.get_player_ids(),
                seed,
            )
            self._pending_initial_chance = False
        else:
            indexed = self._cached_indexed_moves
            if indexed is None:
                indexed = compute_c_action_map(self._adapter)
            move = indexed[int(action)][1]
            self._move_log.append(move)
            self._adapter.apply(move)
            self._cached_indexed_moves = None

    def _action_to_string(self, player, action):
        if self._pending_initial_chance:
            return f"shuffle_seed={action}"
        indexed = self._cached_indexed_moves
        if indexed is None:
            indexed = compute_c_action_map(self._adapter)
        move = indexed[int(action)][1]
        return str(move)

    def is_terminal(self):
        return self._adapter is not None and self._adapter.is_terminal()

    def returns(self):
        player_ids = self._game.get_player_ids()
        n = len(player_ids)
        if self._adapter is None:
            return [0.0] * n
        if self._adapter.is_terminal():
            scores = self._adapter.final_scores()
        else:
            scores = {}
            for pid in player_ids:
                idx = self._player_index(pid)
                scores[pid] = self._adapter.player_score(idx)
        if n == 2:
            s0 = scores.get(player_ids[0], 0)
            s1 = scores.get(player_ids[1], 0)
            return [float(s0 - s1), float(s1 - s0)]
        return [float(scores.get(pid, 0)) for pid in player_ids]

    def __str__(self):
        if self._adapter is None:
            return "PyrantsCState(empty — chance node pending)"
        phase = self._adapter.phase()
        player = self._adapter.current_player_id()
        round_num = self._adapter.round_number()
        lines = [f"Round {round_num} | Phase: {phase} | Current: {player}"]
        for pid in self._game.get_player_ids():
            idx = self._player_index(pid)
            score = self._adapter.player_score(idx)
            lines.append(f"  {pid}: score={score}")
        return "\n".join(lines)

    def chance_outcomes(self):
        if not self._pending_initial_chance:
            return []
        n = self._game.get_shuffle_seed_count()
        p = 1.0 / n
        return [(i, p) for i in range(n)]

    def is_chance_node(self):
        return self._pending_initial_chance and not self.is_terminal()

    def information_state_string(self, player=None):
        if player is None:
            player = self.current_player()
        if self._adapter is None:
            return ""
        pids = self._game.get_player_ids()
        if player < 0 or player >= len(pids):
            return ""

        player_id = pids[player]
        pv_json = self._adapter.private_view_json(player_id)

        history = self.history_str()
        if history:
            return f"{history}||{pv_json}"
        return pv_json

    def observation_string(self, player=None):
        if player is None:
            player = self.current_player()
        return self.information_state_string(player)

    def history_str(self) -> str:
        """Return the action history string, preserved across clone/deepcopy."""
        return ",".join(self._history_actions)

    def clone(self):
        """Override pyspiel.State.clone() to deep-copy the C engine state.

        The default pyspiel clone shares the CEngineAdapter reference, which
        causes IS-MCTS simulations to mutate the root state.  We create a
        fresh adapter backed by a C-level GameState clone (``engine_clone``),
        preserving the move log and history actions without a full replay.
        """
        import copy
        if self._adapter is None:
            new = PyrantsCState.__new__(PyrantsCState)
            pyspiel.State.__init__(new, self._game)
            new._game = self._game
            new._pending_initial_chance = self._pending_initial_chance
            new._cached_indexed_moves = None
            new._shuffle_seed = self._shuffle_seed
            new._move_log = list(self._move_log)
            new._history_actions = list(self._history_actions)
            new._adapter = None
            return new

        # Fast path: clone the C GameState via memcpy without replaying moves.
        from engine_c.bindings.engine_bindings import _lib
        cloned_ptr = _lib.engine_clone(self._adapter._state._ptr)
        if not cloned_ptr:
            return copy.deepcopy(self)  # fallback to replay-based clone

        from engine_c.bindings.ce_api import CState
        new_state = CState(cloned_ptr)
        new_adapter = CEngineAdapter(
            new_state,
            self._adapter._engine,
            self._adapter._player_ids,
            self._adapter._shuffle_seed,
        )
        new = PyrantsCState.__new__(PyrantsCState)
        pyspiel.State.__init__(new, self._game)
        new._game = self._game
        new._pending_initial_chance = False  # adapter exists → past chance node
        new._cached_indexed_moves = None
        new._shuffle_seed = self._shuffle_seed
        new._move_log = list(self._move_log)
        new._history_actions = list(self._history_actions)
        new._adapter = new_adapter
        return new

    def decode_action(self, aid: int):
        indexed = self._cached_indexed_moves
        if indexed is None:
            indexed = compute_c_action_map(self._adapter)
        return indexed[int(aid)][1]

    def move_to_str(self, move) -> str:
        return str(move)

    def move_to_payload(self, move) -> dict:
        return move.to_payload()

    def final_scores(self) -> dict:
        if self._adapter is None:
            return {}
        if self._adapter.is_terminal():
            return self._adapter.final_scores()
        result = {}
        for pid in self._game.get_player_ids():
            idx = self._player_index(pid)
            result[pid] = self._adapter.player_score(idx)
        return result

    def resample_from_infostate(self, player, rng):
        if self._adapter is None:
            return self

        player_id = self._game.get_player_ids()[player]

        if hasattr(rng, 'shuffle'):
            hi = rng.randint(0, 2**31 - 1)
            lo = rng.randint(0, 2**31 - 1)
            seed = (int(hi) << 31) | int(lo)
        elif callable(rng):
            seed = int(rng() * 2**63)
        else:
            seed = 0

        determinized_adapter = self._adapter.determinize(player_id, seed)
        if determinized_adapter is None:
            return self.clone()

        new = PyrantsCState.__new__(PyrantsCState)
        pyspiel.State.__init__(new, self._game)
        new._game = self._game
        new._pending_initial_chance = False
        new._cached_indexed_moves = None
        new._shuffle_seed = self._shuffle_seed
        new._move_log = list(self._move_log)
        new._history_actions = list(self._history_actions)
        new._adapter = determinized_adapter
        return new
