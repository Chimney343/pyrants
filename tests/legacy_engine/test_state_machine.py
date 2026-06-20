"""State-machine transitions through main, end-of-turn, and cleanup."""

from __future__ import annotations

from pathlib import Path

from engine.moves import EndMainPhaseMove, ResolveCleanupMove, ResolveEndOfTurnMove
from engine.rules import apply
from game_setup.loaders import create_game_state_from_files
from tests.scenario_helpers import advance_past_setup

BASE_DIR = Path(__file__).resolve().parents[2]
BOARD_PATH = BASE_DIR / "data" / "boards" / "tyrants_of_the_underdark.json"
CARD_PATH = BASE_DIR / "data" / "cards" / "catalog.json"
SETUP_PATH = BASE_DIR / "data" / "decks" / "base_setup.json"


def _base_state(seed: int = 23):
    return advance_past_setup(
        create_game_state_from_files(BOARD_PATH, CARD_PATH, SETUP_PATH, ["p1", "p2"], seed=seed)
    )


def test_turn_phases_advance_in_order() -> None:
    state = _base_state()

    state = apply(state, EndMainPhaseMove(player_id=state.current_player_id))
    assert state.phase.value == "end_of_turn"

    state = apply(state, ResolveEndOfTurnMove(player_id=state.current_player_id))
    assert state.phase.value == "cleanup"

    current_player = state.current_player_id
    state = apply(state, ResolveCleanupMove(player_id=state.current_player_id))
    assert state.phase.value == "main"
    assert state.current_player_id != current_player


def test_cleanup_draws_up_to_five_cards() -> None:
    state = _base_state(seed=29)

    state = apply(state, EndMainPhaseMove(player_id=state.current_player_id))
    state = apply(state, ResolveEndOfTurnMove(player_id=state.current_player_id))
    state = apply(state, ResolveCleanupMove(player_id=state.current_player_id))

    active = state.players[state.current_player_id]
    assert len(active.hand) <= 5
