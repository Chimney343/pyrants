"""Assert that the same shuffle_seed always produces the same initial state."""

from __future__ import annotations

from pathlib import Path

from game_setup.loaders import build_game_definition_from_files

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
BOARD_PATH = DATA_DIR / "boards" / "tyrants_of_the_underdark.json"
CARD_PATH = DATA_DIR / "cards" / "catalog.json"
SETUP_PATH = DATA_DIR / "decks" / "base_setup.json"


def test_same_seed_produces_same_initial_state():
    definition = build_game_definition_from_files(
        board_path=BOARD_PATH,
        card_path=CARD_PATH,
        setup_path=SETUP_PATH,
    )
    from engine.state import build_initial_game_state

    state_a = build_initial_game_state(definition, ["p1", "p2"], shuffle_seed=42)
    state_b = build_initial_game_state(definition, ["p1", "p2"], shuffle_seed=42)

    assert state_a == state_b


def test_different_seed_produces_different_state():
    definition = build_game_definition_from_files(
        board_path=BOARD_PATH,
        card_path=CARD_PATH,
        setup_path=SETUP_PATH,
    )
    from engine.state import build_initial_game_state

    state_a = build_initial_game_state(definition, ["p1", "p2"], shuffle_seed=42)
    state_b = build_initial_game_state(definition, ["p1", "p2"], shuffle_seed=99)

    assert state_a != state_b
