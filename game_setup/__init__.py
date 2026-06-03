"""Setup helpers for loading external board and deck definitions."""

from game_setup.loaders import (
    build_board_package_from_dicts,
    build_board_package_from_files,
    build_game_definition_from_dicts,
    build_game_definition_from_files,
    create_game_state_from_files,
    save_board_package_to_files,
)
from game_setup.scenarios import (
    Scenario,
    ScenarioMetadata,
    load_game_state_from_scenario,
    load_scenario,
    save_game_state,
    save_scenario,
)
from game_setup.random_state_search import (
    find_state,
    find_state_and_save,
    generate_states,
    has_card_in_hand,
    has_card_in_market,
    has_enemy_troop_at_site,
)
from game_setup.scenario_generation.card_scenarios import (
    FORCED_INJECTIONS_FILENAME,
    CardScenarioGenerator,
    ensure_card_scenario,
    find_card_scenario,
    generate_card_scenarios,
    iter_roster_card_ids,
    write_forced_injection_notes,
)

__all__ = [
    "CardScenarioGenerator",
    "FORCED_INJECTIONS_FILENAME",
    "Scenario",
    "ScenarioMetadata",
    "build_board_package_from_dicts",
    "build_board_package_from_files",
    "build_game_definition_from_dicts",
    "build_game_definition_from_files",
    "create_game_state_from_files",
    "ensure_card_scenario",
    "find_card_scenario",
    "find_state",
    "find_state_and_save",
    "generate_card_scenarios",
    "generate_states",
    "has_card_in_hand",
    "has_card_in_market",
    "has_enemy_troop_at_site",
    "iter_roster_card_ids",
    "load_game_state_from_scenario",
    "load_scenario",
    "save_board_package_to_files",
    "save_game_state",
    "save_scenario",
    "write_forced_injection_notes",
]