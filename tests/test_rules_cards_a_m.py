"""Core rules behavior tests for known implemented surfaces."""

from __future__ import annotations

from pathlib import Path
from random import Random

from engine.moves import (
    PlayCardMove,
    ResolveGenericChoiceMove,
)
from engine.rules import apply, legal_moves
from engine.state import build_initial_game_state
from game_setup.loaders import build_game_definition_from_dicts, create_game_state_from_files

BASE_DIR = Path(__file__).resolve().parents[1]
BOARD_PATH = BASE_DIR / "data" / "boards" / "tyrants_of_the_underdark.json"
CARD_PATH = BASE_DIR / "data" / "cards" / "catalog.json"
SETUP_PATH = BASE_DIR / "data" / "decks" / "base_setup.json"


def _base_state(seed: int = 11):
    return create_game_state_from_files(BOARD_PATH, CARD_PATH, SETUP_PATH, ["p1", "p2"], seed=seed)


def _ability_state(cards: list[dict[str, object]], starter_entries: list[dict[str, object]]) -> object:
    board_data = {
        "board_id": "ability_test_board",
        "nodes": [
            {
                "node_id": "site_a",
                "kind": "site",
                "adjacent_to": [],
                "troop_capacity": 3,
                "vp_value": 0,
                "initial_vp_tokens": 0,
            }
        ],
    }
    card_data = {"catalog_id": "ability_test_catalog", "version": "1.0.0", "cards": cards}
    setup_data = {
        "setup_id": "ability_test_setup",
        "starter_deck": {"deck_id": "starter", "entries": starter_entries},
        "market_deck": {"deck_id": "market", "entries": []},
        "market_row_size": 1,
    }

    definition = build_game_definition_from_dicts(board_data, card_data, setup_data, definition_id="ability_test")
    return build_initial_game_state(definition, ["p1", "p2"], Random(0), shuffle_seed=0)


def test_bounty_hunter_grants_three_power() -> None:
    state = _base_state(seed=31).model_copy(deep=True)
    state.players["p1"].hand = ["bounty_hunter"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.power = 0

    played = apply(state, PlayCardMove(player_id="p1", card_id="bounty_hunter", hand_index=0))

    assert played.resource_pool.power == 3



def test_deathblade_resolves_two_separate_assassinations() -> None:
    state = _base_state(seed=33).model_copy(deep=True)
    state.players["p1"].hand = ["deathblade"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.board.nodes["site_gauntlgrym"].spies.add("p1")
    state.board.nodes["site_gauntlgrym"].troop_slots = ["p2", "p2", None]

    played = apply(state, PlayCardMove(player_id="p1", card_id="deathblade", hand_index=0))
    first = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="deathblade",
            selection={"target_node_id": "site_gauntlgrym", "target_slot_index": 0},
        ),
    )
    resolved = apply(
        first,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="deathblade",
            selection={"target_node_id": "site_gauntlgrym", "target_slot_index": 1},
        ),
    )

    assert resolved.board.nodes["site_gauntlgrym"].troop_slots == [None, None, None]
    assert len(resolved.players["p1"].trophy_hall) >= 2



def test_dragon_cultist_modal_influence_option_grants_two_influence() -> None:
    state = _base_state(seed=37).model_copy(deep=True)
    state.players["p1"].hand = ["dragon_cultist"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.power = 0
    state.resource_pool.influence = 0

    played = apply(state, PlayCardMove(player_id="p1", card_id="dragon_cultist", hand_index=0))
    resolved = apply(
        played,
        ResolveGenericChoiceMove(player_id="p1", source_card_id="dragon_cultist", option_id="option_2"),
    )

    assert resolved.resource_pool.power == 0
    assert resolved.resource_pool.influence == 2



def test_enchanter_of_thay_modal_place_spy_option_places_spy() -> None:
    state = _base_state(seed=39).model_copy(deep=True)
    state.players["p1"].hand = ["enchanter_of_thay"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []

    played = apply(state, PlayCardMove(player_id="p1", card_id="enchanter_of_thay", hand_index=0))
    chose_mode = apply(
        played,
        ResolveGenericChoiceMove(player_id="p1", source_card_id="enchanter_of_thay", option_id="option_1"),
    )
    resolved = apply(
        chose_mode,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="enchanter_of_thay",
            selection={"target_node_id": "site_gauntlgrym"},
        ),
    )

    assert "p1" in resolved.board.nodes["site_gauntlgrym"].spies



def test_enchanter_of_thay_modal_return_spy_option_grants_four_power() -> None:
    state = _base_state(seed=40).model_copy(deep=True)
    state.players["p1"].hand = ["enchanter_of_thay"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.power = 0
    state.board.nodes["site_gauntlgrym"].spies.add("p1")
    spies_available_before = state.players["p1"].spies_available

    played = apply(state, PlayCardMove(player_id="p1", card_id="enchanter_of_thay", hand_index=0))
    chose_mode = apply(
        played,
        ResolveGenericChoiceMove(player_id="p1", source_card_id="enchanter_of_thay", option_id="option_2"),
    )
    resolved = apply(
        chose_mode,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="enchanter_of_thay",
            selection={"node_id": "site_gauntlgrym", "spy_owner_id": "p1"},
        ),
    )

    assert "p1" not in resolved.board.nodes["site_gauntlgrym"].spies
    assert resolved.players["p1"].spies_available == spies_available_before + 1
    assert resolved.resource_pool.power == 4



def test_ettin_modal_deploy_option_deploys_three_troops() -> None:
    state = _base_state(seed=55).model_copy(deep=True)
    state.players["p1"].hand = ["ettin"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.board.nodes["site_gauntlgrym"].spies.add("p1")
    state.board.nodes["site_gauntlgrym"].troop_slots = [None, None, None]
    barracks_before = state.players["p1"].barracks

    played = apply(state, PlayCardMove(player_id="p1", card_id="ettin", hand_index=0))
    chose_mode = apply(played, ResolveGenericChoiceMove(player_id="p1", source_card_id="ettin", option_id="option_1"))
    current = chose_mode
    for _ in range(3):
        current = apply(
            current,
            ResolveGenericChoiceMove(player_id="p1", source_card_id="ettin", selection={"target_node_id": "site_gauntlgrym"}),
        )

    assert current.board.nodes["site_gauntlgrym"].troop_slots == ["p1", "p1", "p1"]
    assert current.players["p1"].barracks == barracks_before - 3



def test_ettin_modal_assassinate_option_removes_two_white_troops() -> None:
    state = _base_state(seed=56).model_copy(deep=True)
    state.players["p1"].hand = ["ettin"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.board.nodes["site_gauntlgrym"].spies.add("p1")
    state.board.nodes["site_gauntlgrym"].troop_slots = ["white", "white", None]

    played = apply(state, PlayCardMove(player_id="p1", card_id="ettin", hand_index=0))
    chose_mode = apply(played, ResolveGenericChoiceMove(player_id="p1", source_card_id="ettin", option_id="option_2"))
    after_first = apply(
        chose_mode,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="ettin",
            selection={"target_node_id": "site_gauntlgrym", "target_slot_index": 0},
        ),
    )
    resolved = apply(
        after_first,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="ettin",
            selection={"target_node_id": "site_gauntlgrym", "target_slot_index": 1},
        ),
    )

    assert resolved.board.nodes["site_gauntlgrym"].troop_slots == [None, None, None]
    assert resolved.players["p1"].trophy_hall == ["white", "white"]



def test_death_tyrant_gains_influence_per_troop_removed_by_effect() -> None:
    state = _base_state(seed=41).model_copy(deep=True)
    state.players["p1"].hand = ["death_tyrant"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.influence = 0
    state.board.nodes["site_gauntlgrym"].spies.add("p1")
    state.board.nodes["site_gauntlgrym"].troop_slots = ["p2", "p2", None]

    played = apply(state, PlayCardMove(player_id="p1", card_id="death_tyrant", hand_index=0))
    first = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="death_tyrant",
            selection={"target_node_id": "site_gauntlgrym", "target_slot_index": 0},
        ),
    )
    resolved = apply(
        first,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="death_tyrant",
            selection={"target_node_id": "site_gauntlgrym", "target_slot_index": 1},
        ),
    )

    assert resolved.board.nodes["site_gauntlgrym"].troop_slots == [None, None, None]
    assert resolved.resource_pool.influence == 2



def test_death_tyrant_can_stop_after_one_assassination() -> None:
    state = _base_state(seed=45).model_copy(deep=True)
    state.players["p1"].hand = ["death_tyrant"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.influence = 0
    state.board.nodes["site_gauntlgrym"].spies.add("p1")
    state.board.nodes["site_gauntlgrym"].troop_slots = ["p2", "p2", "p2"]

    played = apply(state, PlayCardMove(player_id="p1", card_id="death_tyrant", hand_index=0))
    after_first = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="death_tyrant",
            selection={"target_node_id": "site_gauntlgrym", "target_slot_index": 0},
        ),
    )

    first_skip = next(
        move
        for move in legal_moves(after_first)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "death_tyrant"
        and move.selection == {}
    )
    after_second = apply(after_first, first_skip)

    second_skip = next(
        move
        for move in legal_moves(after_second)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "death_tyrant"
        and move.selection == {}
    )
    resolved = apply(after_second, second_skip)

    assert resolved.board.nodes["site_gauntlgrym"].troop_slots == [None, "p2", "p2"]
    assert resolved.resource_pool.influence == 1



def test_death_tyrant_no_legal_targets_resolves_with_zero_influence() -> None:
    state = _base_state(seed=46).model_copy(deep=True)
    state.players["p1"].hand = ["death_tyrant"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.influence = 0
    state.board.nodes["site_gauntlgrym"].spies.add("p1")
    state.board.nodes["site_gauntlgrym"].troop_slots = [None, None, None]

    resolved = apply(state, PlayCardMove(player_id="p1", card_id="death_tyrant", hand_index=0))

    assert resolved.pending_generic_choice is None
    assert resolved.resource_pool.influence == 0



def test_death_tyrant_can_decline_all_assassinations_even_with_targets() -> None:
    state = _base_state(seed=49).model_copy(deep=True)
    state.players["p1"].hand = ["death_tyrant"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.influence = 0
    state.board.nodes["site_gauntlgrym"].spies.add("p1")
    state.board.nodes["site_gauntlgrym"].troop_slots = ["p2", "p2", "p2"]

    played = apply(state, PlayCardMove(player_id="p1", card_id="death_tyrant", hand_index=0))

    skip_first = next(
        move
        for move in legal_moves(played)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "death_tyrant"
        and move.selection == {}
    )
    after_first = apply(played, skip_first)

    skip_second = next(
        move
        for move in legal_moves(after_first)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "death_tyrant"
        and move.selection == {}
    )
    after_second = apply(after_first, skip_second)

    skip_third = next(
        move
        for move in legal_moves(after_second)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "death_tyrant"
        and move.selection == {}
    )
    resolved = apply(after_second, skip_third)

    assert resolved.board.nodes["site_gauntlgrym"].troop_slots == ["p2", "p2", "p2"]
    assert resolved.resource_pool.influence == 0



def test_dragonclaw_grants_two_power_when_non_white_trophy_threshold_met() -> None:
    state = _base_state(seed=43).model_copy(deep=True)
    state.players["p1"].hand = ["dragonclaw"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.players["p1"].trophy_hall = ["p2", "p2", "p2", "p2", "p2"]
    state.resource_pool.power = 0
    state.board.nodes["site_gauntlgrym"].spies.add("p1")
    state.board.nodes["site_gauntlgrym"].troop_slots = ["p2", None, None]

    played = apply(state, PlayCardMove(player_id="p1", card_id="dragonclaw", hand_index=0))
    resolved = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="dragonclaw",
            selection={"target_node_id": "site_gauntlgrym", "target_slot_index": 0},
        ),
    )

    assert resolved.resource_pool.power == 2



def test_dragonclaw_does_not_count_white_trophies_toward_threshold() -> None:
    state = _base_state(seed=44).model_copy(deep=True)
    state.players["p1"].hand = ["dragonclaw"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.players["p1"].trophy_hall = ["p2", "p2", "p2", "white", "white"]
    state.resource_pool.power = 0
    state.board.nodes["site_gauntlgrym"].spies.add("p1")
    state.board.nodes["site_gauntlgrym"].troop_slots = ["p2", None, None]

    played = apply(state, PlayCardMove(player_id="p1", card_id="dragonclaw", hand_index=0))
    resolved = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="dragonclaw",
            selection={"target_node_id": "site_gauntlgrym", "target_slot_index": 0},
        ),
    )

    assert resolved.resource_pool.power == 0



def test_drow_negotiator_grants_three_influence_with_four_promoted_cards() -> None:
    state = _base_state(seed=47).model_copy(deep=True)
    state.players["p1"].hand = ["drow_negotiator"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.players["p1"].inner_circle = ["a", "b", "c", "d"]
    state.resource_pool.influence = 0

    resolved = apply(state, PlayCardMove(player_id="p1", card_id="drow_negotiator", hand_index=0))

    assert resolved.resource_pool.influence == 3
    assert resolved.pending_end_of_turn_promotions
    assert resolved.pending_end_of_turn_promotions[-1].requires_another_played_card is True



def test_drow_negotiator_no_influence_bonus_below_promoted_threshold() -> None:
    state = _base_state(seed=48).model_copy(deep=True)
    state.players["p1"].hand = ["drow_negotiator"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.players["p1"].inner_circle = ["a", "b", "c"]
    state.resource_pool.influence = 0

    resolved = apply(state, PlayCardMove(player_id="p1", card_id="drow_negotiator", hand_index=0))

    assert resolved.resource_pool.influence == 0



def test_gar_shatterkeel_deploys_three_before_recruit_choice() -> None:
    state = _base_state(seed=60).model_copy(deep=True)
    state.players["p1"].hand = ["gar_shatterkeel"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.board.nodes["site_gauntlgrym"].troop_slots = [None, None, None]
    barracks_before = state.players["p1"].barracks

    played = apply(state, PlayCardMove(player_id="p1", card_id="gar_shatterkeel", hand_index=0))
    deploy_move = next(
        move
        for move in legal_moves(played)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "gar_shatterkeel"
        and move.selection.get("target_node_id") == "site_gauntlgrym"
    )
    deployed = played
    for _ in range(3):
        deployed = apply(deployed, deploy_move)

    assert deployed.board.nodes["site_gauntlgrym"].troop_slots.count("p1") == 3
    assert deployed.players["p1"].barracks == barracks_before - 3



def test_gar_shatterkeel_recruit_respects_aspect_and_cost_cap() -> None:
    state = _base_state(seed=61).model_copy(deep=True)
    state.players["p1"].hand = ["gar_shatterkeel"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.influence = 10
    state.market.row = ["advance_scout", "balor", "blackguard"]
    state.board.nodes["site_gauntlgrym"].troop_slots = [None, None, None]

    played = apply(state, PlayCardMove(player_id="p1", card_id="gar_shatterkeel", hand_index=0))
    deploy_move = next(
        move
        for move in legal_moves(played)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "gar_shatterkeel"
        and move.selection.get("target_node_id") == "site_gauntlgrym"
    )
    after_deploy = played
    for _ in range(3):
        after_deploy = apply(after_deploy, deploy_move)

    recruit_moves = [
        move
        for move in legal_moves(after_deploy)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "gar_shatterkeel"
        and "market_slot" in move.selection
    ]

    allowed_slots = {int(move.selection["market_slot"]) for move in recruit_moves}
    assert allowed_slots == {0}



def test_gibbering_mouther_targets_only_opponents_with_presence_and_adds_insane_outcast() -> None:
    state = create_game_state_from_files(BOARD_PATH, CARD_PATH, SETUP_PATH, ["p1", "p2", "p3"], seed=62).model_copy(deep=True)
    state.players["p1"].hand = ["gibbering_mouther"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.board.nodes["site_gauntlgrym"].troop_slots = [None, None, None]
    state.board.nodes["site_gauntlgrym"].spies = {"p2", "p3"}

    played = apply(state, PlayCardMove(player_id="p1", card_id="gibbering_mouther", hand_index=0))
    deploy_move = next(
        move
        for move in legal_moves(played)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "gibbering_mouther"
        and move.selection.get("target_node_id") == "site_gauntlgrym"
    )
    after_first_deploy = apply(played, deploy_move)
    second_deploy_move = next(
        move
        for move in legal_moves(after_first_deploy)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "gibbering_mouther"
        and move.selection.get("target_node_id") == "site_gauntlgrym"
    )
    after_deploy = apply(after_first_deploy, second_deploy_move)

    follow_up_moves = [
        move
        for move in legal_moves(after_deploy)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "gibbering_mouther"
        and "target_player_id" in move.selection
    ]
    target_player_ids = {str(move.selection["target_player_id"]) for move in follow_up_moves}
    assert target_player_ids == {"p2", "p3"}

    target_p2_move = next(move for move in follow_up_moves if move.selection.get("target_player_id") == "p2")
    resolved = apply(after_deploy, target_p2_move)

    assert resolved.players["p2"].discard_pile[-1] == "insane_outcast"
    assert "insane_outcast" not in resolved.players["p3"].discard_pile



def test_ghoul_gives_insane_outcast_to_each_opponent() -> None:
    state = create_game_state_from_files(BOARD_PATH, CARD_PATH, SETUP_PATH, ["p1", "p2", "p3"], seed=620).model_copy(deep=True)
    state.players["p1"].hand = ["ghoul"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.players["p2"].discard_pile = []
    state.players["p3"].discard_pile = []
    state.resource_pool.power = 0

    played = apply(state, PlayCardMove(player_id="p1", card_id="ghoul", hand_index=0))

    assert played.resource_pool.power == 2
    assert played.players["p2"].discard_pile[-1] == "insane_outcast"
    assert played.players["p3"].discard_pile[-1] == "insane_outcast"



def test_myconid_adult_targets_one_opponent_for_insane_outcast() -> None:
    state = create_game_state_from_files(BOARD_PATH, CARD_PATH, SETUP_PATH, ["p1", "p2", "p3"], seed=621).model_copy(deep=True)
    state.players["p1"].hand = ["myconid_adult"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.players["p2"].discard_pile = []
    state.players["p3"].discard_pile = []
    state.resource_pool.influence = 0

    played = apply(state, PlayCardMove(player_id="p1", card_id="myconid_adult", hand_index=0))
    target_moves = [
        move
        for move in legal_moves(played)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "myconid_adult"
        and "target_player_id" in move.selection
    ]

    assert played.resource_pool.influence == 2
    assert {str(move.selection["target_player_id"]) for move in target_moves} == {"p2", "p3"}

    target_p2_move = next(move for move in target_moves if move.selection.get("target_player_id") == "p2")
    resolved = apply(played, target_p2_move)

    assert resolved.players["p2"].discard_pile[-1] == "insane_outcast"
    assert "insane_outcast" not in resolved.players["p3"].discard_pile



def test_matron_mother_mills_deck_then_promotes_from_discard() -> None:
    state = _base_state(seed=624).model_copy(deep=True)
    state.players["p1"].hand = ["matron_mother"]
    state.players["p1"].deck = ["noble"]
    state.players["p1"].discard_pile = ["soldier"]
    state.players["p1"].played_cards = []

    played = apply(state, PlayCardMove(player_id="p1", card_id="matron_mother", hand_index=0))
    promote_moves = [
        move
        for move in legal_moves(played)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "matron_mother"
        and "discard_index" in move.selection
    ]

    assert promote_moves

    promote_last = next(
        move
        for move in promote_moves
        if int(move.selection["discard_index"]) == len(played.players["p1"].discard_pile) - 1
    )
    resolved = apply(played, promote_last)

    assert "noble" in resolved.players["p1"].inner_circle



def test_insane_outcast_play_does_not_block_turn_resolution() -> None:
    state = _base_state(seed=626).model_copy(deep=True)
    state.players["p1"].hand = ["insane_outcast", "noble"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []

    played = apply(state, PlayCardMove(player_id="p1", card_id="insane_outcast", hand_index=0))

    assert played.pending_generic_choice is None



def test_glabrezu_defines_two_single_assassination_actions() -> None:
    state = _base_state(seed=63)
    card = next(card for card in state.definition.catalog.cards if card.card_id == "glabrezu")

    execution_actions = card.execution_model.actions
    flattened_actions = card.actions

    assert [action.op for action in execution_actions] == ["devour_cost", "assassinate_troop", "assassinate_troop"]
    assert [action.quantity.value for action in execution_actions[1:]] == [1, 1]
    assert [action.op for action in flattened_actions] == ["devour_cost", "assassinate_troop", "assassinate_troop"]



def test_glabrezu_runtime_offers_second_assassination_after_first_target() -> None:
    state = _base_state(seed=163).model_copy(deep=True)
    state.players["p1"].hand = ["glabrezu", "advance_scout"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.board.nodes["site_gauntlgrym"].spies.add("p1")
    state.board.nodes["site_gauntlgrym"].troop_slots = ["p2", "p2", None]

    played = apply(state, PlayCardMove(player_id="p1", card_id="glabrezu", hand_index=0))
    devour_move = next(
        move
        for move in legal_moves(played)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "glabrezu"
        and move.selection.get("source_zone") == "hand"
    )
    after_devour = apply(played, devour_move)

    first_assassinate = next(
        move
        for move in legal_moves(after_devour)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "glabrezu"
        and move.selection.get("target_node_id") == "site_gauntlgrym"
        and move.selection.get("target_slot_index") == 0
    )
    after_first = apply(after_devour, first_assassinate)

    second_assassination_moves = [
        move
        for move in legal_moves(after_first)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "glabrezu"
        and move.selection.get("target_node_id") == "site_gauntlgrym"
    ]
    assert second_assassination_moves
    assert {int(move.selection["target_slot_index"]) for move in second_assassination_moves} == {1}



def test_grazzt_option_two_returns_own_spy_then_supplants_white_at_same_site() -> None:
    state = _base_state(seed=64).model_copy(deep=True)
    state.players["p1"].hand = ["grazzt"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.board.nodes["site_gauntlgrym"].spies = {"p1"}
    state.board.nodes["site_gauntlgrym"].troop_slots = ["white", None, None]

    played = apply(state, PlayCardMove(player_id="p1", card_id="grazzt", hand_index=0))
    option_two_move = next(
        move
        for move in legal_moves(played)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "grazzt"
        and move.option_id == "option_2"
    )
    after_option = apply(played, option_two_move)

    return_move = next(
        move
        for move in legal_moves(after_option)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "grazzt"
        and move.selection.get("node_id") == "site_gauntlgrym"
        and move.selection.get("spy_owner_id") == "p1"
    )
    after_return = apply(after_option, return_move)

    supplant_moves = [
        move
        for move in legal_moves(after_return)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "grazzt"
        and "target_node_id" in move.selection
    ]
    assert supplant_moves
    assert {str(move.selection["target_node_id"]) for move in supplant_moves} == {"site_gauntlgrym"}

    supplant_move = next(move for move in supplant_moves if int(move.selection["target_slot_index"]) == 0)
    resolved = apply(after_return, supplant_move)

    assert resolved.board.nodes["site_gauntlgrym"].troop_slots[0] == "p1"



def test_green_wyrmling_gains_two_influence_when_other_troop_present_at_spy_site() -> None:
    state = _base_state(seed=65).model_copy(deep=True)
    state.players["p1"].hand = ["green_wyrmling"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.influence = 0
    state.board.nodes["site_gauntlgrym"].troop_slots = ["p2", None, None]
    state.board.nodes["site_blingdenfire"].troop_slots = [None, None]

    played = apply(state, PlayCardMove(player_id="p1", card_id="green_wyrmling", hand_index=0))
    place_spy_move = next(
        move
        for move in legal_moves(played)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "green_wyrmling"
        and move.selection.get("target_node_id") == "site_gauntlgrym"
    )
    resolved = apply(played, place_spy_move)

    assert resolved.resource_pool.influence == 2



def test_green_wyrmling_does_not_gain_influence_without_other_troop_at_spy_site() -> None:
    state = _base_state(seed=66).model_copy(deep=True)
    state.players["p1"].hand = ["green_wyrmling"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.influence = 0
    state.board.nodes["site_gauntlgrym"].troop_slots = [None, None, None]

    played = apply(state, PlayCardMove(player_id="p1", card_id="green_wyrmling", hand_index=0))
    place_spy_move = next(
        move
        for move in legal_moves(played)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "green_wyrmling"
        and move.selection.get("target_node_id") == "site_gauntlgrym"
    )
    resolved = apply(played, place_spy_move)

    assert resolved.resource_pool.influence == 0



def test_grimlock_model_sets_draw_two_cards() -> None:
    state = _base_state(seed=67)
    card = next(card for card in state.definition.catalog.cards if card.card_id == "grimlock")

    execution_action = card.execution_model.actions[1]
    flattened_action = card.actions[1]

    assert execution_action.op == "draw_cards"
    assert execution_action.quantity.kind == "fixed"
    assert execution_action.quantity.value == 2

    assert flattened_action.op == "draw_cards"
    assert flattened_action.quantity.kind == "fixed"
    assert flattened_action.quantity.value == 2



def test_grimlock_deploys_one_troop_then_draws_two_cards() -> None:
    state = _base_state(seed=806).model_copy(deep=True)
    state.players["p1"].hand = ["grimlock"]
    state.players["p1"].deck = ["noble", "soldier"]
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []

    deploy_nodes = [node_id for node_id, node in state.board.nodes.items() if node.troop_slots]
    assert deploy_nodes
    target_node_id = deploy_nodes[0]

    for node_id, node in state.board.nodes.items():
        if node.troop_slots:
            node.troop_slots = ["p2"] * len(node.troop_slots)
        if node_id == target_node_id:
            node.troop_slots = [None]
            node.spies.add("p1")

    played = apply(state, PlayCardMove(player_id="p1", card_id="grimlock", hand_index=0))

    deploy_move = next(
        move
        for move in legal_moves(played)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "grimlock"
        and move.selection.get("target_node_id") == target_node_id
    )
    current = apply(played, deploy_move)

    assert current.pending_generic_choice is None
    assert len(current.players["p1"].hand) == 2
    assert current.board.nodes[target_node_id].troop_slots == ["p1"]



def test_infiltrator_gains_one_power_when_other_player_troop_present_at_spy_site() -> None:
    state = _base_state(seed=72).model_copy(deep=True)
    state.players["p1"].hand = ["infiltrator"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.power = 0
    state.board.nodes["site_gauntlgrym"].troop_slots = ["p2", None, None]

    played = apply(state, PlayCardMove(player_id="p1", card_id="infiltrator", hand_index=0))
    place_spy_move = next(
        move
        for move in legal_moves(played)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "infiltrator"
        and move.selection.get("target_node_id") == "site_gauntlgrym"
    )
    resolved = apply(played, place_spy_move)

    assert resolved.resource_pool.power == 1



def test_infiltrator_does_not_gain_power_without_other_player_troop_at_spy_site() -> None:
    state = _base_state(seed=73).model_copy(deep=True)
    state.players["p1"].hand = ["infiltrator"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.power = 0
    state.board.nodes["site_gauntlgrym"].troop_slots = [None, None, None]

    played = apply(state, PlayCardMove(player_id="p1", card_id="infiltrator", hand_index=0))
    place_spy_move = next(
        move
        for move in legal_moves(played)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "infiltrator"
        and move.selection.get("target_node_id") == "site_gauntlgrym"
    )
    resolved = apply(played, place_spy_move)

    assert resolved.resource_pool.power == 0



def test_information_broker_return_spy_mode_returns_own_spy_and_draws_three() -> None:
    state = _base_state(seed=74).model_copy(deep=True)
    state.players["p1"].hand = ["information_broker", "advance_scout", "advance_scout"]
    state.players["p1"].deck = ["blackguard", "drow_negotiator", "infiltrator", "kobold"]
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.board.nodes["site_gauntlgrym"].spies = {"p1", "p2"}

    played = apply(state, PlayCardMove(player_id="p1", card_id="information_broker", hand_index=0))
    option_two = apply(
        played,
        ResolveGenericChoiceMove(player_id="p1", source_card_id="information_broker", option_id="option_2"),
    )

    return_moves = [
        move
        for move in legal_moves(option_two)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "information_broker"
        and "spy_owner_id" in move.selection
    ]
    assert return_moves
    assert {str(move.selection["spy_owner_id"]) for move in return_moves} == {"p1"}

    return_spy_move = next(
        move
        for move in return_moves
        if move.selection.get("node_id") == "site_gauntlgrym" and move.selection.get("spy_owner_id") == "p1"
    )
    hand_before = len(option_two.players["p1"].hand)
    resolved = apply(option_two, return_spy_move)

    assert len(resolved.players["p1"].hand) == hand_before + 3
    assert "p1" not in resolved.board.nodes["site_gauntlgrym"].spies



def test_information_broker_model_includes_draw_three_on_option_two() -> None:
    state = _base_state(seed=75)
    card = next(card for card in state.definition.catalog.cards if card.card_id == "information_broker")

    option_two_draw = next(
        action
        for action in card.execution_model.options[1].actions
        if action.op == "draw_cards"
    )

    assert option_two_draw.quantity.kind == "fixed"
    assert option_two_draw.quantity.value == 3



def test_intellect_devourer_option_one_gains_three_influence() -> None:
    state = _base_state(seed=76).model_copy(deep=True)
    state.players["p1"].hand = ["intellect_devourer"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.influence = 0

    played = apply(state, PlayCardMove(player_id="p1", card_id="intellect_devourer", hand_index=0))
    resolved = apply(
        played,
        ResolveGenericChoiceMove(player_id="p1", source_card_id="intellect_devourer", option_id="option_1"),
    )

    assert resolved.resource_pool.influence == 3



def test_jackalwere_option_two_returns_own_spy_and_gains_power_and_influence() -> None:
    state = _base_state(seed=77).model_copy(deep=True)
    state.players["p1"].hand = ["jackalwere"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.power = 0
    state.resource_pool.influence = 0
    state.board.nodes["site_gauntlgrym"].spies = {"p1", "p2"}

    played = apply(state, PlayCardMove(player_id="p1", card_id="jackalwere", hand_index=0))
    option_two = apply(
        played,
        ResolveGenericChoiceMove(player_id="p1", source_card_id="jackalwere", option_id="option_2"),
    )

    return_moves = [
        move
        for move in legal_moves(option_two)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "jackalwere"
        and "spy_owner_id" in move.selection
    ]
    assert return_moves
    assert {str(move.selection["spy_owner_id"]) for move in return_moves} == {"p1"}

    return_spy_move = next(
        move
        for move in return_moves
        if move.selection.get("node_id") == "site_gauntlgrym" and move.selection.get("spy_owner_id") == "p1"
    )
    resolved = apply(option_two, return_spy_move)

    assert resolved.resource_pool.power == 2
    assert resolved.resource_pool.influence == 2



def test_intellect_devourer_option_two_returns_only_own_units_with_mixed_choices_up_to_two() -> None:
    state = _base_state(seed=176).model_copy(deep=True)
    state.players["p1"].hand = ["intellect_devourer"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.board.nodes["site_gauntlgrym"].troop_slots = ["p1", "p2", None]
    state.board.nodes["site_blingdenfire"].spies = {"p1", "p2"}
    barracks_before = state.players["p1"].barracks
    spies_before = state.players["p1"].spies_available

    played = apply(state, PlayCardMove(player_id="p1", card_id="intellect_devourer", hand_index=0))
    option_two = apply(
        played,
        ResolveGenericChoiceMove(player_id="p1", source_card_id="intellect_devourer", option_id="option_2"),
    )

    first_return_moves = [
        move
        for move in legal_moves(option_two)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "intellect_devourer"
        and "unit_type" in move.selection
    ]
    assert first_return_moves

    troop_moves = [move for move in first_return_moves if move.selection.get("unit_type") == "troop"]
    spy_moves = [move for move in first_return_moves if move.selection.get("unit_type") == "spy"]
    assert troop_moves and spy_moves
    assert all(
        option_two.board.nodes[str(move.selection["node_id"])].troop_slots[int(move.selection["target_slot_index"])] == "p1"
        for move in troop_moves
    )
    assert all(str(move.selection["spy_owner_id"]) == "p1" for move in spy_moves)

    return_troop_move = next(
        move
        for move in troop_moves
        if move.selection.get("node_id") == "site_gauntlgrym" and int(move.selection.get("target_slot_index", -1)) == 0
    )
    after_first = apply(option_two, return_troop_move)

    second_return_moves = [
        move
        for move in legal_moves(after_first)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "intellect_devourer"
        and "unit_type" in move.selection
    ]
    assert second_return_moves
    assert all(
        (
            str(move.selection.get("unit_type")) != "spy"
            or str(move.selection.get("spy_owner_id")) == "p1"
        )
        for move in second_return_moves
    )

    return_spy_move = next(
        move
        for move in second_return_moves
        if move.selection.get("unit_type") == "spy"
        and move.selection.get("node_id") == "site_blingdenfire"
        and move.selection.get("spy_owner_id") == "p1"
    )
    resolved = apply(after_first, return_spy_move)

    assert resolved.players["p1"].barracks == barracks_before + 1
    assert resolved.players["p1"].spies_available == spies_before + 1



def test_marilith_devours_hand_card_and_gains_five_power() -> None:
    state = _base_state(seed=78).model_copy(deep=True)
    state.players["p1"].hand = ["marilith", "advance_scout"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.power = 0

    played = apply(state, PlayCardMove(player_id="p1", card_id="marilith", hand_index=0))
    devour_move = next(
        move
        for move in legal_moves(played)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "marilith"
        and move.selection.get("source_zone") == "hand"
    )
    resolved = apply(played, devour_move)

    assert resolved.resource_pool.power == 5
    assert "advance_scout" in resolved.devour_pile



def test_marlos_urnrayle_grants_one_influence() -> None:
    state = _base_state(seed=79).model_copy(deep=True)
    state.players["p1"].hand = ["marlos_urnrayle"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.influence = 0

    played = apply(state, PlayCardMove(player_id="p1", card_id="marlos_urnrayle", hand_index=0))

    assert played.resource_pool.influence == 1



def test_marlos_urnrayle_recruit_mode_filters_ambition_up_to_cost_four() -> None:
    state = _base_state(seed=790).model_copy(deep=True)
    state.players["p1"].hand = ["marlos_urnrayle"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.influence = 10

    catalog = list(state.definition.catalog.cards)
    valid = next(card for card in catalog if card.card_id != "marlos_urnrayle" and card.aspect == "ambition" and card.cost <= 4)
    invalid_aspect = next(card for card in catalog if card.aspect != "ambition" and card.cost <= 4)
    invalid_cost = next(card for card in catalog if card.aspect == "ambition" and card.cost > 4)

    state.market.row[0] = valid.card_id
    state.market.row[1] = invalid_aspect.card_id
    state.market.row[2] = invalid_cost.card_id

    played = apply(state, PlayCardMove(player_id="p1", card_id="marlos_urnrayle", hand_index=0))
    recruit_moves = [
        move
        for move in legal_moves(played)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "marlos_urnrayle"
        and "market_slot" in move.selection
    ]
    slots = {int(move.selection["market_slot"]) for move in recruit_moves}

    assert 0 in slots
    assert 1 not in slots
    assert 2 not in slots



def test_master_of_melee_magthere_model_deploy_mode_is_four_troops() -> None:
    state = _base_state(seed=80)
    card = next(card for card in state.definition.catalog.cards if card.card_id == "master_of_melee_magthere")

    deploy_action = card.execution_model.options[0].actions[0]

    assert deploy_action.op == "deploy_troops"
    assert deploy_action.quantity.kind == "fixed"
    assert deploy_action.quantity.value == 4



def test_masters_of_sorcere_model_place_two_spies_mode_is_two_fixed_actions() -> None:
    state = _base_state(seed=81)
    card = next(card for card in state.definition.catalog.cards if card.card_id == "masters_of_sorcere")

    option_one_actions = card.execution_model.options[0].actions

    assert len(option_one_actions) == 2
    assert all(action.op == "place_spy" for action in option_one_actions)
    assert all(action.quantity.kind == "fixed" and action.quantity.value == 1 for action in option_one_actions)



def test_mind_flayer_option_one_devours_and_gains_three_influence() -> None:
    state = _base_state(seed=82).model_copy(deep=True)
    state.players["p1"].hand = ["mind_flayer", "advance_scout"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.resource_pool.influence = 0

    played = apply(state, PlayCardMove(player_id="p1", card_id="mind_flayer", hand_index=0))
    chose_option = apply(
        played,
        ResolveGenericChoiceMove(player_id="p1", source_card_id="mind_flayer", option_id="option_1"),
    )
    devour_move = next(
        move
        for move in legal_moves(chose_option)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "mind_flayer"
        and move.selection.get("source_zone") == "hand"
    )
    resolved = apply(chose_option, devour_move)

    assert resolved.resource_pool.influence == 3
    assert "advance_scout" in resolved.devour_pile



def test_minotaur_skeleton_model_deploy_mode_is_three_troops() -> None:
    state = _base_state(seed=83)
    card = next(card for card in state.definition.catalog.cards if card.card_id == "minotaur_skeleton")

    deploy_action = card.execution_model.options[0].actions[0]

    assert deploy_action.op == "deploy_troops"
    assert deploy_action.quantity.kind == "fixed"
    assert deploy_action.quantity.value == 3



def test_minotaur_skeleton_white_assassination_chain_stays_on_initial_site() -> None:
    state = _base_state(seed=791).model_copy(deep=True)
    state.players["p1"].hand = ["minotaur_skeleton"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.board.nodes["site_gauntlgrym"].spies.add("p1")
    state.board.nodes["site_blingdenfire"].spies.add("p1")
    state.board.nodes["site_gauntlgrym"].troop_slots = ["white", "white", "white"]
    state.board.nodes["site_blingdenfire"].troop_slots = ["white", None, None]

    played = apply(state, PlayCardMove(player_id="p1", card_id="minotaur_skeleton", hand_index=0))
    option_two = apply(
        played,
        ResolveGenericChoiceMove(player_id="p1", source_card_id="minotaur_skeleton", option_id="option_2"),
    )

    first_assassinate = next(
        move
        for move in legal_moves(option_two)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "minotaur_skeleton"
        and move.selection.get("target_node_id") == "site_gauntlgrym"
        and move.selection.get("target_slot_index") == 0
    )
    after_first = apply(option_two, first_assassinate)

    second_assassinate_moves = [
        move
        for move in legal_moves(after_first)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "minotaur_skeleton"
        and "target_node_id" in move.selection
    ]

    assert second_assassinate_moves
    assert {str(move.selection["target_node_id"]) for move in second_assassinate_moves} == {"site_gauntlgrym"}



def test_black_dragon_scales_vp_from_white_trophies_only() -> None:
    state = _base_state(seed=803).model_copy(deep=True)
    state.players["p1"].hand = ["black_dragon"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.players["p1"].trophy_hall = ["white", "white", "white", "p2"]
    state.players["p1"].score = 0
    state.players["p1"].barracks = 5
    state.board.nodes["site_blingdenfire"].troop_slots = ["white", None, None]
    state.board.nodes["site_gauntlgrym"].troop_slots = [None, None, None]
    state.board.nodes["site_gauntlgrym"].spies = set()
    state.board.nodes["site_blingdenfire"].spies = set()

    played = apply(state, PlayCardMove(player_id="p1", card_id="black_dragon", hand_index=0))
    supplant_move = next(
        move
        for move in legal_moves(played)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "black_dragon"
        and move.selection.get("target_node_id") == "site_blingdenfire"
        and move.selection.get("target_slot_index") == 0
    )
    resolved = apply(played, supplant_move)

    assert resolved.players["p1"].score == 1



def test_death_knight_scales_vp_from_non_white_trophies() -> None:
    state = _base_state(seed=804).model_copy(deep=True)
    state.players["p1"].hand = ["death_knight"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.players["p1"].trophy_hall = ["p2", "p2", "p2", "p2", "p2", "white", "white"]
    state.players["p1"].score = 0
    state.players["p1"].barracks = 5
    state.board.nodes["site_gauntlgrym"].troop_slots = ["p1", "p2", None]
    state.board.nodes["site_gauntlgrym"].spies = set()

    played = apply(state, PlayCardMove(player_id="p1", card_id="death_knight", hand_index=0))
    supplant_move = next(
        move
        for move in legal_moves(played)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "death_knight"
        and move.selection.get("target_node_id") == "site_gauntlgrym"
        and move.selection.get("target_slot_index") == 1
    )
    resolved = apply(played, supplant_move)

    assert resolved.players["p1"].score == 1



def test_mummy_lord_custom_effect_moves_white_trophy_to_board_slot() -> None:
    state = _base_state(seed=810).model_copy(deep=True)
    state.players["p1"].hand = ["mummy_lord"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.players["p2"].trophy_hall = ["white", "p1"]
    state.board.nodes["site_gauntlgrym"].troop_slots = [None, None, None]

    played = apply(state, PlayCardMove(player_id="p1", card_id="mummy_lord", hand_index=0))
    chose_custom_mode = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="mummy_lord",
            option_id="option_2",
        ),
    )
    custom_move = next(
        move
        for move in legal_moves(chose_custom_mode)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "mummy_lord"
        and move.selection.get("target_player_id") == "p2"
        and move.selection.get("target_node_id") == "site_gauntlgrym"
        and move.selection.get("target_slot_index") == 0
    )

    resolved = apply(chose_custom_mode, custom_move)

    assert "white" not in resolved.players["p2"].trophy_hall
    assert resolved.board.nodes["site_gauntlgrym"].troop_slots[0] == "white"
