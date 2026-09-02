"""Data-level tests for JSON-driven special stacks and demons gating.

These tests run without the engine DLL — they exercise the roster-derived
special-stack specs, ``compute_special_stacks`` demons gating, the
``MarketSetup.to_setup_data()`` emission, and the ``base_setup.json`` fixture.
"""

from __future__ import annotations

import json
from pathlib import Path

from game_setup.market_setup import (
    HOUSE_GUARD_RECRUIT_SLOT,
    INSANE_OUTCAST_RECRUIT_SLOT,
    PRIESTESS_RECRUIT_SLOT,
    combine_two_deck_market_setup,
    compute_special_stacks,
    discover_full_deck_profiles,
    load_special_stack_counts,
)
from game_setup.scenario_generation.rosters import DEFAULT_ROSTERS_PATH

BASE_DIR = Path(__file__).resolve().parents[1]
BASE_SETUP_PATH = BASE_DIR / "data" / "decks" / "base_setup.json"


def _specs_by_card(specs):
    return {spec.card_id: spec for spec in specs}


def test_load_special_stack_counts_matches_roster_files() -> None:
    counts = load_special_stack_counts(DEFAULT_ROSTERS_PATH)
    assert counts == {
        "house_guard": 15,
        "priestess_of_lolth": 15,
        "insane_outcast": 30,
    }


def test_compute_special_stacks_demons_gating() -> None:
    demons_specs = compute_special_stacks("demons", "elementals", decks_dir=DEFAULT_ROSTERS_PATH)
    by_card = _specs_by_card(demons_specs)
    assert set(by_card) == {"house_guard", "priestess_of_lolth", "insane_outcast"}
    assert by_card["house_guard"].market_slot == HOUSE_GUARD_RECRUIT_SLOT
    assert by_card["house_guard"].stack_total == 15
    assert by_card["priestess_of_lolth"].market_slot == PRIESTESS_RECRUIT_SLOT
    assert by_card["priestess_of_lolth"].stack_total == 15
    assert by_card["insane_outcast"].market_slot == INSANE_OUTCAST_RECRUIT_SLOT
    assert by_card["insane_outcast"].stack_total == 30

    aberrations_specs = compute_special_stacks("aberrations", "drow", decks_dir=DEFAULT_ROSTERS_PATH)
    by_card = _specs_by_card(aberrations_specs)
    assert set(by_card) == {"house_guard", "priestess_of_lolth"}
    assert "insane_outcast" not in by_card


def test_to_setup_data_emits_special_stacks() -> None:
    profiles = discover_full_deck_profiles(DEFAULT_ROSTERS_PATH)
    by_id = {p.deck_id: p for p in profiles}
    base = json.loads(BASE_SETUP_PATH.read_text(encoding="utf-8"))
    market_setup = combine_two_deck_market_setup(base, by_id["demons"], by_id["elementals"])
    data = market_setup.to_setup_data()
    assert "special_stacks" in data
    assert data["special_stacks"] == [
        {"market_slot": 100, "card_id": "house_guard", "stack_total": 15},
        {"market_slot": 101, "card_id": "priestess_of_lolth", "stack_total": 15},
        {"market_slot": 102, "card_id": "insane_outcast", "stack_total": 30},
    ]

    non_demons = combine_two_deck_market_setup(base, by_id["aberrations"], by_id["drow"])
    non_demons_specs = non_demons.to_setup_data()["special_stacks"]
    assert isinstance(non_demons_specs, list)
    assert {spec["card_id"] for spec in non_demons_specs} == {"house_guard", "priestess_of_lolth"}


def test_base_setup_declares_all_three_stacks_matching_rosters() -> None:
    base = json.loads(BASE_SETUP_PATH.read_text(encoding="utf-8"))
    stacks = base["special_stacks"]
    assert isinstance(stacks, list)
    assert len(stacks) == 3

    by_slot = {spec["market_slot"]: spec for spec in stacks}
    assert by_slot[HOUSE_GUARD_RECRUIT_SLOT] == {
        "market_slot": 100, "card_id": "house_guard", "stack_total": 15,
    }
    assert by_slot[PRIESTESS_RECRUIT_SLOT] == {
        "market_slot": 101, "card_id": "priestess_of_lolth", "stack_total": 15,
    }
    assert by_slot[INSANE_OUTCAST_RECRUIT_SLOT] == {
        "market_slot": 102, "card_id": "insane_outcast", "stack_total": 30,
    }

    roster_counts = load_special_stack_counts(DEFAULT_ROSTERS_PATH)
    for spec in stacks:
        assert spec["stack_total"] == roster_counts[spec["card_id"]]
