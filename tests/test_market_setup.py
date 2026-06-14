"""Unit tests for united market-setup module."""

from __future__ import annotations

import json
from pathlib import Path
from random import Random

from engine.helpers import _is_aberrations_enabled
from engine.state import GameDefinition, build_initial_game_state
from game_setup.loaders import build_game_definition_from_dicts
from game_setup.market_setup import (
    ABERRATIONS_DECK_ID,
    SPECIAL_RECRUIT_IDS,
    DeckProfile,
    combine_two_deck_market_setup,
    compute_special_stacks,
    discover_full_deck_profiles,
    is_aberrations_in_market,
    pick_pair_for_target,
    pick_random_pair,
)

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
DECKS_DIR = DATA_DIR / "decks"
BOARD_PATH = DATA_DIR / "boards" / "tyrants_of_the_underdark.json"
CARD_PATH = DATA_DIR / "cards" / "catalog.json"
SETUP_PATH = DATA_DIR / "decks" / "base_setup.json"


def _base_setup() -> dict:
    return json.loads(SETUP_PATH.read_text(encoding="utf-8"))


def test_discover_full_deck_profiles_returns_40_card_rosters() -> None:
    profiles = discover_full_deck_profiles(DECKS_DIR)
    assert len(profiles) >= 2
    for profile in profiles:
        assert profile.total_cards == 40
        assert profile.deck_id not in SPECIAL_RECRUIT_IDS


def test_discover_full_deck_profiles_excludes_single_card_stacks() -> None:
    profiles = discover_full_deck_profiles(DECKS_DIR)
    deck_ids = {p.deck_id for p in profiles}
    assert "house_guard" not in deck_ids
    assert "priestess_of_lolth" not in deck_ids
    assert "insane_outcast" not in deck_ids


def test_discover_full_deck_profiles_sorted_by_deck_id() -> None:
    profiles = discover_full_deck_profiles(DECKS_DIR)
    deck_ids = [p.deck_id for p in profiles]
    assert deck_ids == sorted(deck_ids)


def test_is_aberrations_in_market() -> None:
    assert is_aberrations_in_market("aberrations", "drow")
    assert is_aberrations_in_market("drow", "aberrations")
    assert not is_aberrations_in_market("drow", "dragon")
    assert not is_aberrations_in_market("", "")


def test_compute_special_stacks_all_combinations() -> None:
    no_ab = compute_special_stacks("drow", "dragon")
    assert no_ab == ("house_guard", "priestess_of_lolth")

    ab_a = compute_special_stacks("aberrations", "drow")
    assert ab_a == ("house_guard", "priestess_of_lolth", "insane_outcast")

    ab_b = compute_special_stacks("drow", "aberrations")
    assert ab_b == ("house_guard", "priestess_of_lolth", "insane_outcast")

    both_ab = compute_special_stacks("aberrations", "aberrations")
    assert both_ab == ("house_guard", "priestess_of_lolth", "insane_outcast")


def test_combine_two_deck_market_setup_80_total_cards() -> None:
    base_setup = _base_setup()
    profiles = discover_full_deck_profiles(DECKS_DIR)
    deck_a = next(p for p in profiles if p.deck_id == "drow")
    deck_b = next(p for p in profiles if p.deck_id == "dragon")

    market_setup = combine_two_deck_market_setup(base_setup, deck_a, deck_b)
    total = sum(count for _, count in market_setup.market_deck_entries)
    assert total == 80


def test_combine_two_deck_market_setup_correct_ids() -> None:
    base_setup = _base_setup()
    profiles = discover_full_deck_profiles(DECKS_DIR)
    deck_a = next(p for p in profiles if p.deck_id == "drow")
    deck_b = next(p for p in profiles if p.deck_id == "dragon")

    market_setup = combine_two_deck_market_setup(base_setup, deck_a, deck_b)
    assert market_setup.setup_id == "drow_dragon"
    assert market_setup.market_deck_id == "market_drow_dragon"
    assert market_setup.market_row_size == 6


def test_combine_two_deck_market_setup_same_deck_twice() -> None:
    base_setup = _base_setup()
    profiles = discover_full_deck_profiles(DECKS_DIR)
    deck_a = next(p for p in profiles if p.deck_id == "drow")

    market_setup = combine_two_deck_market_setup(base_setup, deck_a, deck_a)
    total = sum(count for _, count in market_setup.market_deck_entries)
    assert total == 80


def test_combine_two_deck_market_setup_aberrations_special_stacks() -> None:
    base_setup = _base_setup()
    profiles = discover_full_deck_profiles(DECKS_DIR)
    deck_a = next(p for p in profiles if p.deck_id == ABERRATIONS_DECK_ID)
    deck_b = next(p for p in profiles if p.deck_id not in {ABERRATIONS_DECK_ID, "drow"})

    market_setup = combine_two_deck_market_setup(base_setup, deck_a, deck_b)
    assert "insane_outcast" in market_setup.special_stacks


def test_market_setup_to_setup_data_shape() -> None:
    base_setup = _base_setup()
    profiles = discover_full_deck_profiles(DECKS_DIR)
    deck_a = profiles[0]
    deck_b = profiles[1]

    market_setup = combine_two_deck_market_setup(base_setup, deck_a, deck_b)
    setup_data = market_setup.to_setup_data()

    assert setup_data["setup_id"] == market_setup.setup_id
    assert isinstance(setup_data["starter_deck"], dict)
    assert isinstance(setup_data["market_deck"], dict)
    assert setup_data["market_deck"]["deck_id"] == market_setup.market_deck_id
    assert setup_data["market_row_size"] == market_setup.market_row_size


def test_market_setup_to_setup_data_roundtrip() -> None:
    base_setup = _base_setup()
    profiles = discover_full_deck_profiles(DECKS_DIR)
    deck_a = profiles[0]
    deck_b = profiles[1]

    market_setup = combine_two_deck_market_setup(base_setup, deck_a, deck_b)
    setup_data = market_setup.to_setup_data()

    board_data = json.loads(BOARD_PATH.read_text(encoding="utf-8"))
    card_data = json.loads(CARD_PATH.read_text(encoding="utf-8"))

    definition = build_game_definition_from_dicts(board_data, card_data, setup_data)
    assert isinstance(definition, GameDefinition)
    assert definition.setup.market_deck.deck_id == market_setup.market_deck_id


def test_market_setup_to_setup_data_aberrations_triggers_engine_check() -> None:
    base_setup = _base_setup()
    profiles = discover_full_deck_profiles(DECKS_DIR)
    deck_a = next(p for p in profiles if p.deck_id == ABERRATIONS_DECK_ID)
    deck_b = next(p for p in profiles if p.deck_id not in {ABERRATIONS_DECK_ID, "drow"})

    market_setup = combine_two_deck_market_setup(base_setup, deck_a, deck_b)
    setup_data = market_setup.to_setup_data()

    board_data = json.loads(BOARD_PATH.read_text(encoding="utf-8"))
    card_data = json.loads(CARD_PATH.read_text(encoding="utf-8"))

    definition = build_game_definition_from_dicts(board_data, card_data, setup_data)
    initial_state = build_initial_game_state(definition, ["p1", "p2"], shuffle_seed=42)

    assert _is_aberrations_enabled(initial_state)


def test_market_setup_to_setup_data_no_aberrations_does_not_trigger() -> None:
    base_setup = _base_setup()
    profiles = discover_full_deck_profiles(DECKS_DIR)
    non_ab = [p for p in profiles if p.deck_id != ABERRATIONS_DECK_ID]
    deck_a = non_ab[0]
    deck_b = non_ab[1]

    market_setup = combine_two_deck_market_setup(base_setup, deck_a, deck_b)
    setup_data = market_setup.to_setup_data()

    board_data = json.loads(BOARD_PATH.read_text(encoding="utf-8"))
    card_data = json.loads(CARD_PATH.read_text(encoding="utf-8"))

    definition = build_game_definition_from_dicts(board_data, card_data, setup_data)
    initial_state = build_initial_game_state(definition, ["p1", "p2"], shuffle_seed=42)

    assert not _is_aberrations_enabled(initial_state)


def test_pick_random_pair_deterministic() -> None:
    profiles = discover_full_deck_profiles(DECKS_DIR)
    rng1 = Random(42)
    rng2 = Random(42)

    a1, b1 = pick_random_pair(profiles, rng1)
    a2, b2 = pick_random_pair(profiles, rng2)
    assert a1 == a2
    assert b1 == b2


def test_pick_random_pair_distinct_decks() -> None:
    profiles = discover_full_deck_profiles(DECKS_DIR)
    rng = Random(99)
    a, b = pick_random_pair(profiles, rng)
    assert a.deck_id != b.deck_id


def test_pick_random_pair_single_profile_returns_same_twice() -> None:
    single = [DeckProfile("test", "Test", 40, (("noble", 40),))]
    a, b = pick_random_pair(single, Random(0))
    assert a.deck_id == b.deck_id == "test"


def test_pick_random_pair_empty_raises() -> None:
    try:
        pick_random_pair([], Random(0))
        raise AssertionError("Expected ValueError")
    except ValueError:
        pass


def test_pick_pair_for_target_finds_containing_deck() -> None:
    profiles = discover_full_deck_profiles(DECKS_DIR)
    rng = Random(42)
    deck_a, deck_b = pick_pair_for_target(profiles, "aboleth", rng)
    entry_ids = {e[0] for e in deck_a.entries}
    assert "aboleth" in entry_ids
    assert deck_a.deck_id != deck_b.deck_id


def test_pick_pair_for_target_special_recruit_fallback() -> None:
    profiles = discover_full_deck_profiles(DECKS_DIR)
    rng = Random(42)
    deck_a, deck_b = pick_pair_for_target(profiles, "priestess_of_lolth", rng)
    assert deck_a.deck_id not in SPECIAL_RECRUIT_IDS
    assert deck_b.deck_id not in SPECIAL_RECRUIT_IDS


def test_pick_pair_for_target_single_profile_fallback_same() -> None:
    single = [DeckProfile("only", "Only", 40, (("aboleth", 40),))]
    a, b = pick_pair_for_target(single, "aboleth", Random(0))
    assert a.deck_id == b.deck_id == "only"


def test_special_recruit_ids_constant() -> None:
    assert "house_guard" in SPECIAL_RECRUIT_IDS
    assert "priestess_of_lolth" in SPECIAL_RECRUIT_IDS
    assert "insane_outcast" in SPECIAL_RECRUIT_IDS
    assert "drow" not in SPECIAL_RECRUIT_IDS


def test_aberrations_deck_id_constant() -> None:
    assert ABERRATIONS_DECK_ID == "aberrations"
