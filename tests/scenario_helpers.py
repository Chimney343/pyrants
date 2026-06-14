"""Reusable state-building helpers for card behavior and scenario tests."""

from __future__ import annotations

from pathlib import Path

from engine.state import GameState, TurnPhase
from game_setup.loaders import create_game_state_from_files

BASE_DIR = Path(__file__).resolve().parents[1]
BOARD_PATH = BASE_DIR / "data" / "boards" / "tyrants_of_the_underdark.json"
CARD_PATH = BASE_DIR / "data" / "cards" / "catalog.json"
SETUP_PATH = BASE_DIR / "data" / "decks" / "base_setup.json"


def base_state(
    player_ids: list[str] | None = None,
    seed: int = 13,
) -> GameState:
    """Build a seeded base state for two-player tests."""
    player_ids = player_ids or ["p1", "p2"]
    return create_game_state_from_files(
        board_path=BOARD_PATH,
        card_path=CARD_PATH,
        setup_path=SETUP_PATH,
        player_ids=player_ids,
        seed=seed,
    )


def clear_player_zones(state: GameState, player_id: str) -> None:
    """Empty hand, deck, discard, and played zones in place."""
    player = state.players[player_id]
    player.deck.clear()
    player.hand.clear()
    player.discard_pile.clear()
    player.played_cards.clear()


def set_only_hand_card(state: GameState, player_id: str, card_id: str) -> None:
    """Replace the player's hand with exactly the given card id."""
    state.players[player_id].hand = [card_id]


def zero_resources(state: GameState) -> None:
    """Reset the transient resource pool to zero."""
    state.resource_pool.power = 0
    state.resource_pool.influence = 0


def add_spy(state: GameState, node_id: str, player_id: str) -> None:
    """Add a player spy to a board node in place."""
    state.board.nodes[node_id].spies.add(player_id)


def remove_spy(state: GameState, node_id: str, player_id: str) -> None:
    """Remove a player spy from a board node in place."""
    state.board.nodes[node_id].spies.discard(player_id)


def set_troop_slots(state: GameState, node_id: str, slots: list[str | None]) -> None:
    """Replace troop slots on a board node."""
    state.board.nodes[node_id].troop_slots = list(slots)


def fill_trophy_hall(state: GameState, player_id: str, count: int) -> None:
    """Set trophy hall to `count` generic entries."""
    state.players[player_id].trophy_hall = ["dummy_trophy"] * count


def fill_inner_circle(state: GameState, player_id: str, card_ids: list[str]) -> None:
    """Replace inner circle with given card ids."""
    state.players[player_id].inner_circle = list(card_ids)


def set_barracks(state: GameState, player_id: str, count: int) -> None:
    """Set remaining troop count in barracks."""
    state.players[player_id].barracks = count


def set_spies_available(state: GameState, player_id: str, count: int) -> None:
    """Set available spy count."""
    state.players[player_id].spies_available = count


def card_test_state(card_id: str, *, seed: int = 13, player_id: str = "p1") -> GameState:
    """Return a focused state for testing a single card.

    The returned state is a mutated deep copy of a fresh base state:
    - player zones are emptied
    - only the target card is in hand
    - resources are zeroed
    """
    state = base_state(["p1", "p2"], seed=seed).model_copy(deep=True)
    state.phase = TurnPhase.MAIN
    clear_player_zones(state, player_id)
    set_only_hand_card(state, player_id, card_id)
    zero_resources(state)
    return state


def resolve_setup(state: GameState) -> GameState:
    """Advance through SETUP and DRAW to reach MAIN.

    Places each player's initial troop on the first available site node
    and then draws 5 cards for every player. Returns a new state in MAIN.
    """
    from engine.helpers import _legal_initial_placement_node_ids
    from engine.moves import InitialPlacementMove
    from engine.rules import apply

    current = state.model_copy(deep=True)
    while current.phase == TurnPhase.SETUP:
        node_ids = _legal_initial_placement_node_ids(current)
        if not node_ids:
            raise ValueError("No legal site nodes for initial placement")
        move = InitialPlacementMove(
            player_id=current.current_player_id,
            target_node_id=node_ids[0],
        )
        current = apply(current, move)
    return current


def advance_past_setup(state: GameState) -> GameState:
    """Advance to MAIN and draw hands without placing initial troops.

    Marks all players as having completed setup, then advances through
    DRAW which draws 5 cards per player. Board state is left untouched.
    """
    from engine.phases import advance_phase

    current = state.model_copy(deep=True)
    for player_id in current.turn_order:
        current.setup_complete.add(player_id)
    return advance_phase(current)
