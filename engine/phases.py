"""Turn-phase transition helpers for the game state machine."""

from __future__ import annotations

from engine.errors import RuleViolationError
from engine.state import GameState, ResourcePool, TurnPhase, draw_cards


def next_player_id(turn_order: list[str], current_player_id: str) -> str:
    """Return the player id that acts after the current player."""

    if current_player_id not in turn_order:
        raise RuleViolationError("Current player is not part of turn order")

    current_index = turn_order.index(current_player_id)
    return turn_order[(current_index + 1) % len(turn_order)]


def advance_phase(state: GameState) -> GameState:
    """Advance to the next phase in the fixed runtime phase order."""

    updated = state._cow_clone()

    if updated.phase == TurnPhase.SETUP:
        if len(updated.setup_complete) >= len(updated.turn_order):
            updated.phase = TurnPhase.DRAW
            updated.current_player_id = updated.turn_order[0]
        else:
            next_player = next_player_id(updated.turn_order, updated.current_player_id)
            updated.current_player_id = next_player
            return updated

    if updated.phase == TurnPhase.DRAW:
        for player_id in updated.turn_order:
            player = updated.players[player_id]
            updated_player, new_counter = draw_cards(
                player,
                count=5,
                shuffle_seed=updated.shuffle_seed,
                shuffle_counter=updated.shuffle_count,
            )
            updated.players[player_id] = updated_player
            updated.shuffle_count = new_counter
        updated.phase = TurnPhase.MAIN
        updated.resource_pool = ResourcePool()
        return updated

    if updated.phase == TurnPhase.MAIN:
        updated.phase = TurnPhase.END_OF_TURN
        updated.resource_pool = ResourcePool()
        return updated

    if updated.phase == TurnPhase.END_OF_TURN:
        updated.phase = TurnPhase.CLEANUP
        updated.resource_pool = ResourcePool()
        return updated

    if updated.phase == TurnPhase.CLEANUP:
        next_player = next_player_id(updated.turn_order, updated.current_player_id)
        wrapped_round = next_player == updated.turn_order[0]

        updated.phase = TurnPhase.MAIN
        updated.current_player_id = next_player
        updated.resource_pool = ResourcePool()
        if wrapped_round:
            # Round boundary — check kill switches
            kill = (
                not updated.market.deck
                or any(ps.barracks == 0 for ps in updated.players.values())
            )
            if kill:
                return set_game_over(updated, {})
            updated.round_number += 1
        return updated

    raise RuleViolationError(f"Cannot advance phase from '{updated.phase}'")


def set_game_over(state: GameState, final_scores: dict[str, int]) -> GameState:
    """Return a copy of state marked as terminal with frozen final scores."""

    updated = state._cow_clone()
    updated.phase = TurnPhase.GAME_OVER
    updated.final_scores = dict(final_scores)
    updated.resource_pool = ResourcePool()
    return updated
