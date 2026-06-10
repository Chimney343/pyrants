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

    def current_player(self):
        if self._engine is not None and engine_is_terminal(self._engine):
            return pyspiel.PlayerId.TERMINAL
        if self._pending_initial_chance:
            return pyspiel.PlayerId.CHANCE
        return self._player_index(self._engine.current_player_id)

    def _legal_actions(self, player):
        if self._pending_initial_chance:
            return list(range(self._game.get_shuffle_seed_count()))
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
        if self._engine is None:
            return [0.0, 0.0]
        player_ids = self._game.get_player_ids()
        if engine_is_terminal(self._engine):
            scores = compute_final_scores(self._engine)
            p0_score = scores.get(player_ids[0], 0)
            p1_score = scores.get(player_ids[1], 0)
        else:
            p0_score = self._engine.players[player_ids[0]].score
            p1_score = self._engine.players[player_ids[1]].score
        return [float(p0_score - p1_score), float(p1_score - p0_score)]

    def __str__(self):
        if self._engine is None:
            return "PyrantsState(empty — chance node pending)"
        phase = self._engine.phase.value
        player = self._engine.current_player_id
        round_num = self._engine.round_number
        p0 = self._engine.players[self._game.get_player_ids()[0]]
        p1 = self._engine.players[self._game.get_player_ids()[1]]
        return (
            f"Round {round_num} | Phase: {phase} | Current: {player}\n"
            f"  {p0.player_id}: score={p0.score} hand={len(p0.hand)} "
            f"deck={len(p0.deck)} barracks={p0.barracks}\n"
            f"  {p1.player_id}: score={p1.score} hand={len(p1.hand)} "
            f"deck={len(p1.deck)} barracks={p1.barracks}"
        )

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
