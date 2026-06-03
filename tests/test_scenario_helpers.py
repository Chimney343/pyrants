"""Tests for the scenario helper state-building utilities."""

from __future__ import annotations

from engine.moves import PlayCardMove
from engine.rules import apply
from tests.scenario_helpers import (
    add_spy,
    card_test_state,
    clear_player_zones,
    fill_inner_circle,
    fill_trophy_hall,
    remove_spy,
    set_barracks,
    set_only_hand_card,
    set_spies_available,
    set_troop_slots,
    zero_resources,
)


def test_card_test_state_provides_clean_slate() -> None:
    state = card_test_state("bounty_hunter")

    assert state.players["p1"].hand == ["bounty_hunter"]
    assert state.players["p1"].deck == []
    assert state.players["p1"].discard_pile == []
    assert state.players["p1"].played_cards == []
    assert state.resource_pool.power == 0
    assert state.resource_pool.influence == 0


def test_card_test_state_bounty_hunter_grants_three_power() -> None:
    state = card_test_state("bounty_hunter")

    played = apply(state, PlayCardMove(player_id="p1", card_id="bounty_hunter", hand_index=0))

    assert played.resource_pool.power == 3


def test_clear_player_zones_empties_all() -> None:
    state = card_test_state("aboleth")
    state.players["p1"].deck = ["noble"]
    state.players["p1"].discard_pile = ["soldier"]
    state.players["p1"].played_cards = ["bounty_hunter"]

    clear_player_zones(state, "p1")

    assert state.players["p1"].deck == []
    assert state.players["p1"].hand == []
    assert state.players["p1"].discard_pile == []
    assert state.players["p1"].played_cards == []


def test_set_only_hand_card() -> None:
    state = card_test_state("x")
    set_only_hand_card(state, "p1", "aboleth")

    assert state.players["p1"].hand == ["aboleth"]


def test_add_and_remove_spy() -> None:
    state = card_test_state("x")

    add_spy(state, "site_a", "p1")
    assert "p1" in state.board.nodes["site_a"].spies

    remove_spy(state, "site_a", "p1")
    assert "p1" not in state.board.nodes["site_a"].spies


def test_set_troop_slots() -> None:
    state = card_test_state("x")
    set_troop_slots(state, "site_a", ["p1", None, "p2"])

    assert state.board.nodes["site_a"].troop_slots == ["p1", None, "p2"]


def test_fill_trophy_hall() -> None:
    state = card_test_state("x")
    fill_trophy_hall(state, "p1", 5)

    assert len(state.players["p1"].trophy_hall) == 5
    assert state.players["p1"].trophy_hall == ["dummy_trophy"] * 5


def test_fill_inner_circle() -> None:
    state = card_test_state("x")
    fill_inner_circle(state, "p1", ["noble", "soldier", "noble"])

    assert state.players["p1"].inner_circle == ["noble", "soldier", "noble"]


def test_set_barracks() -> None:
    state = card_test_state("x")
    set_barracks(state, "p1", 25)

    assert state.players["p1"].barracks == 25


def test_set_spies_available() -> None:
    state = card_test_state("x")
    set_spies_available(state, "p1", 3)

    assert state.players["p1"].spies_available == 3


def test_zero_resources() -> None:
    state = card_test_state("x")
    state.resource_pool.power = 10
    state.resource_pool.influence = 5

    zero_resources(state)

    assert state.resource_pool.power == 0
    assert state.resource_pool.influence == 0
