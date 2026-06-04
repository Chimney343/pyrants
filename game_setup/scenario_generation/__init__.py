"""Scenario-generation package for card-scenario discovery and injection."""

from game_setup.scenario_generation.card_scenarios import (
    DEFAULT_BOARD_PATH,
    DEFAULT_CARD_PATH,
    DEFAULT_ROSTERS_PATH,
    DEFAULT_SETUP_PATH,
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
    "DEFAULT_BOARD_PATH",
    "DEFAULT_CARD_PATH",
    "DEFAULT_ROSTERS_PATH",
    "DEFAULT_SETUP_PATH",
    "FORCED_INJECTIONS_FILENAME",
    "ensure_card_scenario",
    "find_card_scenario",
    "generate_card_scenarios",
    "iter_roster_card_ids",
    "write_forced_injection_notes",
]
