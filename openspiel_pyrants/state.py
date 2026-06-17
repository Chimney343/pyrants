"""PyrantsState(pyspiel.State) — adapts pyrants engine to the OpenSpiel state interface.

Holds a reference to ``engine.state.GameState`` (self._engine).  The initial
chance node selects a shuffle seed; after that the engine is fully initialized
and all further state transitions are deterministic.
"""

from __future__ import annotations

import pyspiel

from engine.rules import apply as apply_move
from engine.rules import is_terminal as engine_is_terminal
from engine.scoring import compute_final_scores
from engine.state import GameState, build_initial_game_state
from openspiel_pyrants.action_encoding import compute_action_map

_SEED_MIXER_MULTIPLIER = 2654435761
_SEED_MIXER_MASK = 0x7FFFFFFF


def _public_to_seed(action_id: int) -> int:
    """Map a public chance outcome id to an internal shuffle seed.

    Uses a Knuth multiplicative hash that is a bijection mod 2^31,
    so the mapping preserves the uniform-probability contract of
    ``chance_outcomes()`` while preventing trivial recovery of the
    seed from the public action history.
    """
    return (action_id * _SEED_MIXER_MULTIPLIER) & _SEED_MIXER_MASK


class PyrantsState(pyspiel.State):
    def __init__(self, game):
        super().__init__(game)
        self._game = game
        self._engine: GameState | None = None
        self._pending_initial_chance = True
        self._cached_indexed_moves: list | None = None

    def _player_index(self, player_id: str) -> int:
        return self._game.get_player_ids().index(player_id)

    def __deepcopy__(self, memo):
        new = PyrantsState.__new__(PyrantsState)
        pyspiel.State.__init__(new, self._game)
        new._game = self._game
        new._pending_initial_chance = self._pending_initial_chance
        new._cached_indexed_moves = None
        new._engine = self._engine.clone_fast() if self._engine is not None else None
        memo[id(self)] = new
        return new

    def current_player(self):
        if self._engine is not None and engine_is_terminal(self._engine):
            return pyspiel.PlayerId.TERMINAL
        if self._pending_initial_chance:
            return pyspiel.PlayerId.CHANCE
        return self._player_index(self._engine.current_player_id)

    def _legal_actions(self, player):
        if self._pending_initial_chance:
            return list(range(self._game.get_shuffle_seed_count()))
        if self._cached_indexed_moves is None:
            self._cached_indexed_moves = compute_action_map(self._engine)
        return list(range(len(self._cached_indexed_moves)))

    def _apply_action(self, action):
        if self._pending_initial_chance:
            self._cached_indexed_moves = None
            seed = _public_to_seed(int(action))
            self._engine = build_initial_game_state(
                self._game.get_definition(),
                self._game.get_player_ids(),
                shuffle_seed=seed,
            )
            self._pending_initial_chance = False
        else:
            indexed = self._cached_indexed_moves
            if indexed is None:
                indexed = compute_action_map(self._engine)
            move = indexed[int(action)][1]
            self._engine = apply_move(self._engine, move)
            self._cached_indexed_moves = None

    def _action_to_string(self, player, action):
        if self._pending_initial_chance:
            return f"shuffle_seed={action}"
        indexed = self._cached_indexed_moves
        if indexed is None:
            indexed = compute_action_map(self._engine)
        move = indexed[int(action)][1]
        return str(move)

    def is_terminal(self):
        return self._engine is not None and engine_is_terminal(self._engine)

    def returns(self):
        player_ids = self._game.get_player_ids()
        n = len(player_ids)
        if self._engine is None:
            return [0.0] * n
        if engine_is_terminal(self._engine):
            scores = compute_final_scores(self._engine)
        else:
            scores = {pid: self._engine.players[pid].score for pid in player_ids}
        if n == 2:
            s0 = scores.get(player_ids[0], 0)
            s1 = scores.get(player_ids[1], 0)
            return [float(s0 - s1), float(s1 - s0)]
        return [float(scores.get(pid, 0)) for pid in player_ids]

    def __str__(self):
        if self._engine is None:
            return "PyrantsState(empty — chance node pending)"
        phase = self._engine.phase.value
        player = self._engine.current_player_id
        round_num = self._engine.round_number
        lines = [f"Round {round_num} | Phase: {phase} | Current: {player}"]
        for pid in self._game.get_player_ids():
            p = self._engine.players[pid]
            lines.append(
                f"  {p.player_id}: score={p.score} hand={len(p.hand)} "
                f"deck={len(p.deck)} barracks={p.barracks}"
            )
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
        if self._engine is None:
            return ""

        player_id = self._game.get_player_ids()[player]
        from engine.player_view import private_view

        pv = private_view(self._engine, player_id)
        pv_json = pv.model_dump_json()

        history = self.history_str()
        if history:
            return f"{history}||{pv_json}"
        return pv_json

    def observation_string(self, player=None):
        if player is None:
            player = self.current_player()
        return self.information_state_string(player)

    def resample_from_infostate(self, player, rng):
        if self._engine is None:
            return self

        player_id = self._game.get_player_ids()[player]
        from openspiel_pyrants.determinization import determinize_opponent_hidden_zones

        new_engine = determinize_opponent_hidden_zones(self._engine, player_id, rng)

        sampled = self.clone()
        sampled._engine = new_engine
        sampled._cached_indexed_moves = None
        return sampled
