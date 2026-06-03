"""Compatibility shim — re-exports from new homes.

Generic random-state search lives in `game_setup.random_state_search`.
Card-scenario generation lives in `game_setup.scenario_generation.card_scenarios`.
"""

from __future__ import annotations

from game_setup.random_state_search import (
    find_state,
    find_state_and_save,
    generate_states,
    has_card_in_hand,
    has_card_in_market,
    has_enemy_troop_at_site,
)
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
    "find_state",
    "find_state_and_save",
    "generate_card_scenarios",
    "generate_states",
    "has_card_in_hand",
    "has_card_in_market",
    "has_enemy_troop_at_site",
    "iter_roster_card_ids",
    "write_forced_injection_notes",
]
