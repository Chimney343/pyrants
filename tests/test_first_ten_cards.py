"""Behavior coverage for the first ten generic cards in catalog order."""

from __future__ import annotations

from pathlib import Path

from engine.moves import PlayCardMove, ResolveGenericChoiceMove
from engine.rules import apply, legal_moves
from game_setup.loaders import create_game_state_from_files

BASE_DIR = Path(__file__).resolve().parents[1]
BOARD_PATH = BASE_DIR / "data" / "boards" / "base_game.json"
CARD_PATH = BASE_DIR / "data" / "cards" / "catalog.json"
SETUP_PATH = BASE_DIR / "data" / "decks" / "base_setup.json"


def _fresh_state(seed: int = 13):
    state = create_game_state_from_files(
        board_path=BOARD_PATH,
        card_path=CARD_PATH,
        setup_path=SETUP_PATH,
        player_ids=["p1", "p2"],
        seed=seed,
    )
    state.players["p1"].hand = []
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.power = 0
    state.resource_pool.influence = 0
    return state


def _generic_moves(state):
    return [move for move in legal_moves(state) if isinstance(move, ResolveGenericChoiceMove)]


def test_aboleth_option_one_places_two_spies() -> None:
    state = _fresh_state()
    state.players["p1"].hand = ["aboleth"]

    played = apply(state, PlayCardMove(player_id="p1", card_id="aboleth", hand_index=0))
    with_option = apply(
        played,
        ResolveGenericChoiceMove(player_id="p1", source_card_id="aboleth", option_id="option_1"),
    )
    first_placement = apply(
        with_option,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="aboleth",
            selection={"target_node_id": "site_a"},
        ),
    )
    resolved = apply(
        first_placement,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="aboleth",
            selection={"target_node_id": "site_blingdenfire"},
        ),
    )

    assert "p1" in resolved.board.nodes["site_a"].spies
    assert "p1" in resolved.board.nodes["site_blingdenfire"].spies
    assert resolved.pending_generic_choice is None


def test_advocate_modal_gain_influence_grants_two() -> None:
    state = _fresh_state()
    state.players["p1"].hand = ["advocate"]

    played = apply(state, PlayCardMove(player_id="p1", card_id="advocate", hand_index=0))
    option_ids = {move.option_id for move in _generic_moves(played)}

    assert option_ids == {"gain_influence", "promote_end_of_turn"}

    resolved = apply(
        played,
        ResolveGenericChoiceMove(player_id="p1", source_card_id="advocate", option_id="gain_influence"),
    )

    assert resolved.resource_pool.influence == 2
    assert resolved.pending_generic_choice is None


def test_banshee_conditional_bonus_uses_selected_site() -> None:
    state = _fresh_state()
    state.players["p1"].hand = ["banshee"]
    state.board.nodes["site_a"].spies.add("p2")

    played = apply(state, PlayCardMove(player_id="p1", card_id="banshee", hand_index=0))
    resolved = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="banshee",
            selection={"target_node_id": "site_a"},
        ),
    )

    assert resolved.resource_pool.power == 3
    assert "p1" in resolved.board.nodes["site_a"].spies


def test_beholder_scaled_power_from_trophy_hall() -> None:
    state = _fresh_state()
    state.players["p1"].hand = ["beholder"]
    state.players["p1"].trophy_hall = ["x", "x", "x", "x", "x"]
    state.board.nodes["site_a"].spies.add("p1")
    state.board.nodes["site_a"].troop_slots = ["p2", None, None]

    played = apply(state, PlayCardMove(player_id="p1", card_id="beholder", hand_index=0))
    resolved = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="beholder",
            selection={"target_node_id": "site_a", "target_slot_index": 0},
        ),
    )

    assert resolved.board.nodes["site_a"].troop_slots[0] is None
    assert resolved.resource_pool.power == 2


def test_beholder_scaled_power_counts_assassinated_troop_before_dividing_by_three() -> None:
    state = _fresh_state()
    state.players["p1"].hand = ["beholder"]
    state.players["p1"].trophy_hall = ["x", "x"]
    state.board.nodes["site_a"].spies.add("p1")
    state.board.nodes["site_a"].troop_slots = ["p2", None, None]

    played = apply(state, PlayCardMove(player_id="p1", card_id="beholder", hand_index=0))
    resolved = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="beholder",
            selection={"target_node_id": "site_a", "target_slot_index": 0},
        ),
    )

    assert len(resolved.players["p1"].trophy_hall) == 3
    assert resolved.resource_pool.power == 1


def test_black_wyrmling_gains_one_influence_and_assassinates_white_troop() -> None:
    state = _fresh_state()
    state.players["p1"].hand = ["black_wyrmling"]
    state.board.nodes["site_a"].spies.add("p1")
    state.board.nodes["site_a"].troop_slots = ["white", None, None]

    played = apply(state, PlayCardMove(player_id="p1", card_id="black_wyrmling", hand_index=0))
    resolved = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="black_wyrmling",
            selection={"target_node_id": "site_a", "target_slot_index": 0},
        ),
    )

    assert resolved.resource_pool.influence == 1
    assert resolved.board.nodes["site_a"].troop_slots[0] is None


def test_blue_wyrmling_gains_three_influence_and_returns_opponent_troop() -> None:
    state = _fresh_state()
    state.players["p1"].hand = ["blue_wyrmling"]
    state.board.nodes["site_a"].spies.add("p1")
    state.board.nodes["site_a"].troop_slots = ["p2", None, None]
    p2_barracks_before = state.players["p2"].barracks

    played = apply(state, PlayCardMove(player_id="p1", card_id="blue_wyrmling", hand_index=0))
    resolved = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="blue_wyrmling",
            selection={
                "unit_type": "troop",
                "node_id": "site_a",
                "target_slot_index": 0,
            },
        ),
    )

    assert resolved.resource_pool.influence == 3
    assert resolved.board.nodes["site_a"].troop_slots[0] is None
    assert resolved.players["p2"].barracks == p2_barracks_before + 1


def test_brainwashed_slave_option_two_returns_spy_and_grants_power_and_influence() -> None:
    state = _fresh_state()
    state.players["p1"].hand = ["brainwashed_slave"]
    state.board.nodes["site_a"].spies.add("p1")
    state.players["p1"].spies_available -= 1

    played = apply(state, PlayCardMove(player_id="p1", card_id="brainwashed_slave", hand_index=0))
    with_option = apply(
        played,
        ResolveGenericChoiceMove(player_id="p1", source_card_id="brainwashed_slave", option_id="option_2"),
    )
    resolved = apply(
        with_option,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="brainwashed_slave",
            selection={"node_id": "site_a", "spy_owner_id": "p1"},
        ),
    )

    assert "p1" not in resolved.board.nodes["site_a"].spies
    assert resolved.resource_pool.power == 2
    assert resolved.resource_pool.influence == 2


def test_carrion_crawler_gains_three_power_before_market_devour_choice() -> None:
    state = _fresh_state()
    state.players["p1"].hand = ["carrion_crawler"]
    state.market.row = ["advance_scout", "air_elemental", "balor", "beholder", "house_guard", "priestess_of_lolth"]
    state.market.deck = []

    played = apply(state, PlayCardMove(player_id="p1", card_id="carrion_crawler", hand_index=0))

    assert played.resource_pool.power == 3
    assert played.pending_generic_choice is not None
    assert played.pending_generic_choice.source_card_id == "carrion_crawler"


def test_crushing_wave_cultist_assassinates_white_troop_without_focus_bonus() -> None:
    state = _fresh_state()
    state.players["p1"].hand = ["crushing_wave_cultist"]
    state.board.nodes["site_a"].spies.add("p1")
    state.board.nodes["site_a"].troop_slots = ["white", None, None]
    barracks_before = state.players["p1"].barracks

    played = apply(state, PlayCardMove(player_id="p1", card_id="crushing_wave_cultist", hand_index=0))
    resolved = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="crushing_wave_cultist",
            selection={"target_node_id": "site_a", "target_slot_index": 0},
        ),
    )

    assert resolved.board.nodes["site_a"].troop_slots[0] is None
    assert resolved.players["p1"].barracks == barracks_before


def test_crushing_wave_cultist_focus_bonus_deploys_two_troops() -> None:
    state = _fresh_state()
    state.players["p1"].hand = ["crushing_wave_cultist", "black_wyrmling"]
    state.board.nodes["site_a"].spies.add("p1")
    state.board.nodes["site_a"].troop_slots = ["white", None, None]
    barracks_before = state.players["p1"].barracks

    played = apply(state, PlayCardMove(player_id="p1", card_id="crushing_wave_cultist", hand_index=0))
    after_assassinate = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="crushing_wave_cultist",
            selection={"target_node_id": "site_a", "target_slot_index": 0},
        ),
    )
    after_first_deploy = apply(
        after_assassinate,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="crushing_wave_cultist",
            selection={"target_node_id": "site_a"},
        ),
    )
    resolved = apply(
        after_first_deploy,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="crushing_wave_cultist",
            selection={"target_node_id": "site_a"},
        ),
    )

    assert resolved.board.nodes["site_a"].troop_slots.count("p1") == 2
    assert resolved.players["p1"].barracks == barracks_before - 2


def test_aerisi_kalinoth_recruit_is_filtered_to_guile_cost_four_or_less() -> None:
    state = _fresh_state()
    state.players["p1"].hand = ["aerisi_kalinoth"]
    state.resource_pool.influence = 10
    state.market.row = ["advance_scout", "air_elemental", "balor", "beholder", "house_guard", "priestess_of_lolth"]
    state.market.deck = []

    played = apply(state, PlayCardMove(player_id="p1", card_id="aerisi_kalinoth", hand_index=0))
    assert played.resource_pool.power == 1
    after_spy = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="aerisi_kalinoth",
            selection={"target_node_id": "site_a"},
        ),
    )

    recruit_moves = _generic_moves(after_spy)
    recruit_slots = {move.selection.get("market_slot") for move in recruit_moves}
    assert recruit_slots == {1}

    resolved = apply(
        after_spy,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="aerisi_kalinoth",
            selection={"market_slot": 1},
        ),
    )

    assert "air_elemental" in resolved.players["p1"].discard_pile


def test_air_elemental_option_two_is_unavailable_without_self_spy_to_return() -> None:
    state = _fresh_state()
    state.players["p1"].hand = ["air_elemental"]

    played = apply(state, PlayCardMove(player_id="p1", card_id="air_elemental", hand_index=0))
    option_ids = {move.option_id for move in _generic_moves(played)}

    assert option_ids == {"option_1"}


def test_air_elemental_option_two_returns_spy_and_draws_with_focus() -> None:
    state = _fresh_state()
    state.players["p1"].hand = ["air_elemental", "banshee"]
    state.players["p1"].deck = ["noble"]
    state.board.nodes["site_a"].spies.add("p1")
    state.players["p1"].spies_available -= 1
    state.board.nodes["route_ab"].troop_slots = ["p1"]
    state.players["p1"].barracks -= 1

    played = apply(state, PlayCardMove(player_id="p1", card_id="air_elemental", hand_index=0))
    with_option = apply(
        played,
        ResolveGenericChoiceMove(player_id="p1", source_card_id="air_elemental", option_id="option_2"),
    )

    step_one = apply(
        with_option,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="air_elemental",
            selection={"node_id": "site_a", "spy_owner_id": "p1"},
        ),
    )
    step_two = apply(
        step_one,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="air_elemental",
            selection={"target_node_id": "site_a"},
        ),
    )
    resolved = apply(
        step_two,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="air_elemental",
            selection={"target_node_id": "site_a"},
        ),
    )
    resolved = apply(
        resolved,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="air_elemental",
            selection={"target_node_id": "site_a"},
        ),
    )

    assert "p1" not in resolved.board.nodes["site_a"].spies
    assert resolved.board.nodes["site_a"].troop_slots.count("p1") == 3
    assert "noble" in resolved.players["p1"].hand
