"""Scenario-generation package for card-scenario discovery and injection."""

from game_setup.scenario_generation.rosters import (
    DEFAULT_BOARD_PATH,
    DEFAULT_CARD_PATH,
    DEFAULT_ROSTERS_PATH,
    DEFAULT_SETUP_PATH,
    FORCED_INJECTIONS_FILENAME,
    StopConditions,
    iter_roster_card_ids,
    write_forced_injection_notes,
)

__all__ = [
    "DEFAULT_BOARD_PATH",
    "DEFAULT_CARD_PATH",
    "DEFAULT_ROSTERS_PATH",
    "DEFAULT_SETUP_PATH",
    "FORCED_INJECTIONS_FILENAME",
    "StopConditions",
    "iter_roster_card_ids",
    "write_forced_injection_notes",
]
