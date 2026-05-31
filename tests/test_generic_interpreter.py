"""Generic structured-card interpreter tests."""

from __future__ import annotations

from random import Random

from engine.moves import PlayCardMove, ResolveGenericChoiceMove
from engine.rules import apply, legal_moves
from engine.state import build_initial_game_state
from game_setup.loaders import build_game_definition_from_dicts


WHITE_TROOP_OWNER = "white"


def _action(
    action_id: str,
    op: str,
    *,
    target_scope: str = "self",
    source_fragment: str = "test_fragment",
    filters: list[str] | None = None,
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "action_id": action_id,
        "op": op,
        "target_scope": target_scope,
        "timing": "immediate",
        "optional": False,
        "quantity": {"kind": "unspecified", "value": None},
        "filters": filters or [],
        "source_fragment": source_fragment,
        "metadata": metadata or {},
    }


def _sequence_card(card_id: str, actions: list[dict[str, object]]) -> dict[str, object]:
    return {
        "card_id": card_id,
        "name": card_id.replace("_", " ").title(),
        "cost": 0,
        "aspect": "none",
        "deck_vp": 0,
        "inner_circle_vp": 0,
        "rules_text": "",
        "notes": "",
        "execution_model": {"kind": "sequence", "actions": actions},
        "actions": actions,
        "global_conditions": [],
        "state_contract": {"reads": [], "writes": []},
        "effect_key": "generic_card",
        "effect_payload": {},
    }


def _modal_card(card_id: str, options: list[list[dict[str, object]]]) -> dict[str, object]:
    flattened = [action for option in options for action in option]
    option_payload = [
        {"option_id": f"option_{index + 1}", "actions": option}
        for index, option in enumerate(options)
    ]
    return {
        "card_id": card_id,
        "name": card_id.replace("_", " ").title(),
        "cost": 0,
        "aspect": "none",
        "deck_vp": 0,
        "inner_circle_vp": 0,
        "rules_text": "",
        "notes": "",
        "execution_model": {
            "kind": "modal_choice",
            "selection": "exactly_one",
            "options": option_payload,
        },
        "actions": flattened,
        "global_conditions": [],
        "state_contract": {"reads": [], "writes": []},
        "effect_key": "generic_card",
        "effect_payload": {},
    }


def _repeat_card(card_id: str, options: list[list[dict[str, object]]], *, repeat_count: int) -> dict[str, object]:
    flattened = [action for option in options for action in option]
    option_payload = [
        {"option_id": f"option_{index + 1}", "actions": option}
        for index, option in enumerate(options)
    ]
    return {
        "card_id": card_id,
        "name": card_id.replace("_", " ").title(),
        "cost": 0,
        "aspect": "none",
        "deck_vp": 0,
        "inner_circle_vp": 0,
        "rules_text": "",
        "notes": "",
        "execution_model": {
            "kind": "repeat_choice",
            "repeat_count": repeat_count,
            "allow_repeat": False,
            "options": option_payload,
        },
        "actions": flattened,
        "global_conditions": [],
        "state_contract": {"reads": [], "writes": []},
        "effect_key": "generic_card",
        "effect_payload": {},
    }


def _state_for_cards(cards: list[dict[str, object]], starter_entries: list[dict[str, object]]):
    board_data = {
        "board_id": "generic_test_board",
        "nodes": [
            {
                "node_id": "site_a",
                "kind": "site",
                "adjacent_to": ["site_b"],
                "troop_capacity": 2,
                "vp_value": 0,
                "initial_control_marker": None,
                "initial_vp_tokens": 0,
            },
            {
                "node_id": "site_b",
                "kind": "site",
                "adjacent_to": ["site_a"],
                "troop_capacity": 2,
                "vp_value": 0,
                "initial_control_marker": None,
                "initial_vp_tokens": 0,
            },
        ],
    }
    card_data = {"catalog_id": "generic_test_catalog", "cards": cards}
    setup_data = {
        "setup_id": "generic_test_setup",
        "starter_deck": {"deck_id": "starter", "entries": starter_entries},
        "market_deck": {"deck_id": "market", "entries": []},
        "market_row_size": 1,
    }
    definition = build_game_definition_from_dicts(board_data, card_data, setup_data)
    return build_initial_game_state(definition, ["p1", "p2"], Random(0), shuffle_seed=0)


def test_generic_sequence_requires_explicit_target_selection() -> None:
    card = _sequence_card(
        "generic_gain_and_deploy",
        [
            _action("a1", "gain_resource", metadata={"resource": "power"}),
            _action("a2", "deploy_troops", target_scope="board_site"),
        ],
    )
    state = _state_for_cards([card], [{"card_id": "generic_gain_and_deploy", "count": 1}])
    state.players["p1"].hand = ["generic_gain_and_deploy"]
    state.players["p1"].deck = []

    played = apply(state, PlayCardMove(player_id="p1", card_id="generic_gain_and_deploy", hand_index=0))
    updated = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="generic_gain_and_deploy",
            selection={"target_node_id": "site_a"},
        ),
    )

    assert updated.board.nodes["site_a"].troop_slots.count("p1") == 1
    assert updated.players["p1"].barracks == state.players["p1"].barracks - 1
    assert updated.resource_pool.power == 1


def test_generic_modal_choice_is_player_selected() -> None:
    card = _modal_card(
        "generic_modal",
        [
            [_action("opt1", "gain_resource", metadata={"resource": "power"})],
            [_action("opt2", "gain_resource", metadata={"resource": "influence"})],
        ],
    )
    state = _state_for_cards([card], [{"card_id": "generic_modal", "count": 1}])
    state.players["p1"].hand = ["generic_modal"]
    state.players["p1"].deck = []

    played = apply(state, PlayCardMove(player_id="p1", card_id="generic_modal", hand_index=0))
    option_moves = [move for move in legal_moves(played) if isinstance(move, ResolveGenericChoiceMove)]
    assert {move.option_id for move in option_moves} == {"option_1", "option_2"}

    updated = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="generic_modal",
            option_id="option_2",
        ),
    )

    assert updated.resource_pool.power == 0
    assert updated.resource_pool.influence == 1
    assert updated.pending_generic_choice is None


def test_generic_repeat_choice_requires_explicit_option_per_repeat() -> None:
    card = _repeat_card(
        "generic_repeat",
        [
            [_action("opt1", "gain_resource", metadata={"resource": "power"})],
            [_action("opt2", "gain_resource", metadata={"resource": "influence"})],
        ],
        repeat_count=2,
    )
    state = _state_for_cards([card], [{"card_id": "generic_repeat", "count": 1}])
    state.players["p1"].hand = ["generic_repeat"]
    state.players["p1"].deck = []

    played = apply(state, PlayCardMove(player_id="p1", card_id="generic_repeat", hand_index=0))
    first_resolution = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="generic_repeat",
            option_id="option_2",
        ),
    )

    second_option_moves = [move for move in legal_moves(first_resolution) if isinstance(move, ResolveGenericChoiceMove)]
    assert {move.option_id for move in second_option_moves} == {"option_1"}

    updated = apply(
        first_resolution,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="generic_repeat",
            option_id="option_1",
        ),
    )

    assert updated.resource_pool.power == 1
    assert updated.resource_pool.influence == 1
    assert updated.pending_generic_choice is None


def test_generic_devour_moves_card_to_devour_pile() -> None:
    devourer = _sequence_card(
        "generic_devour",
        [
            _action(
                "devour",
                "devour_cost",
                target_scope="hand",
                source_fragment="devour_hand",
                metadata={"source_zone": "hand", "self_replace": False},
            )
        ],
    )
    fodder = _sequence_card("fodder_card", [_action("noop_action", "gain_resource", metadata={"resource": "power"})])
    state = _state_for_cards(
        [devourer, fodder],
        [{"card_id": "generic_devour", "count": 1}, {"card_id": "fodder_card", "count": 1}],
    )
    state.players["p1"].hand = ["generic_devour", "fodder_card"]
    state.players["p1"].deck = []

    played = apply(state, PlayCardMove(player_id="p1", card_id="generic_devour", hand_index=0))
    updated = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="generic_devour",
            selection={"source_zone": "hand", "hand_index": 0},
        ),
    )

    assert updated.players["p1"].hand == []
    assert updated.devour_pile == ["fodder_card"]


def test_generic_supplant_handles_white_troop_targets() -> None:
    card = _sequence_card(
        "generic_supplant_white",
        [_action("supplant", "supplant_troop", target_scope="board_site", filters=["white_troop_only"])],
    )
    state = _state_for_cards([card], [{"card_id": "generic_supplant_white", "count": 1}])
    state.players["p1"].hand = ["generic_supplant_white"]
    state.players["p1"].deck = []
    state.board.nodes["site_a"].spies.add("p1")
    state.board.nodes["site_a"].troop_slots = [WHITE_TROOP_OWNER, None]

    played = apply(state, PlayCardMove(player_id="p1", card_id="generic_supplant_white", hand_index=0))
    updated = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="generic_supplant_white",
            selection={"target_node_id": "site_a", "target_slot_index": 0},
        ),
    )

    assert updated.board.nodes["site_a"].troop_slots[0] == "p1"
    assert updated.players["p1"].barracks == state.players["p1"].barracks - 1


def test_generic_assassinate_records_enemy_trophy() -> None:
    card = _sequence_card(
        "generic_assassinate",
        [_action("assassinate", "assassinate_troop", target_scope="board_site")],
    )
    state = _state_for_cards([card], [{"card_id": "generic_assassinate", "count": 1}])
    state.players["p1"].hand = ["generic_assassinate"]
    state.players["p1"].deck = []
    state.board.nodes["site_a"].troop_slots = ["p1", "p2"]

    played = apply(state, PlayCardMove(player_id="p1", card_id="generic_assassinate", hand_index=0))
    updated = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="generic_assassinate",
            selection={"target_node_id": "site_a", "target_slot_index": 1},
        ),
    )

    assert updated.board.nodes["site_a"].troop_slots == ["p1", None]
    assert updated.players["p1"].trophy_hall == ["p2"]


def test_generic_place_spy_repositions_when_supply_is_empty() -> None:
    card = _sequence_card(
        "generic_spy",
        [_action("spy", "place_spy", target_scope="board_site")],
    )
    state = _state_for_cards([card], [{"card_id": "generic_spy", "count": 1}])
    state.players["p1"].hand = ["generic_spy"]
    state.players["p1"].deck = []
    state.players["p1"].spies_available = 0
    state.board.nodes["site_a"].spies.add("p1")

    played = apply(state, PlayCardMove(player_id="p1", card_id="generic_spy", hand_index=0))
    updated = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="generic_spy",
            selection={"target_node_id": "site_b", "source_node_id": "site_a"},
        ),
    )

    assert "p1" not in updated.board.nodes["site_a"].spies
    assert "p1" in updated.board.nodes["site_b"].spies


def test_generic_return_unit_sends_enemy_troop_back_to_barracks() -> None:
    card = _sequence_card(
        "generic_return_unit",
        [_action("return", "return_unit", target_scope="opponent_unit")],
    )
    state = _state_for_cards([card], [{"card_id": "generic_return_unit", "count": 1}])
    state.players["p1"].hand = ["generic_return_unit"]
    state.players["p1"].deck = []
    state.board.nodes["site_a"].troop_slots = ["p2", None]
    before_barracks = state.players["p2"].barracks

    played = apply(state, PlayCardMove(player_id="p1", card_id="generic_return_unit", hand_index=0))
    updated = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="generic_return_unit",
            selection={"unit_type": "troop", "node_id": "site_a", "target_slot_index": 0},
        ),
    )

    assert updated.board.nodes["site_a"].troop_slots == [None, None]
    assert updated.players["p2"].barracks == before_barracks + 1


def test_generic_move_troop_moves_enemy_between_adjacent_sites() -> None:
    card = _sequence_card(
        "generic_move_troop",
        [_action("move", "move_troop", target_scope="board_site")],
    )
    state = _state_for_cards([card], [{"card_id": "generic_move_troop", "count": 1}])
    state.players["p1"].hand = ["generic_move_troop"]
    state.players["p1"].deck = []
    state.board.nodes["site_a"].troop_slots = ["p2", None]
    state.board.nodes["site_b"].troop_slots = [None, None]

    played = apply(state, PlayCardMove(player_id="p1", card_id="generic_move_troop", hand_index=0))
    updated = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="generic_move_troop",
            selection={
                "source_node_id": "site_a",
                "source_slot_index": 0,
                "target_node_id": "site_b",
                "target_slot_index": 0,
            },
        ),
    )

    assert updated.board.nodes["site_a"].troop_slots == [None, None]
    assert updated.board.nodes["site_b"].troop_slots[0] == "p2"


def test_generic_force_discard_skips_when_no_legal_targets() -> None:
    card = _sequence_card(
        "generic_force_discard_then_gain",
        [
            _action("discard", "force_discard", target_scope="opponent_hand"),
            _action("gain", "gain_resource", metadata={"resource": "power"}),
        ],
    )
    state = _state_for_cards([card], [{"card_id": "generic_force_discard_then_gain", "count": 1}])
    state.players["p1"].hand = ["generic_force_discard_then_gain"]
    state.players["p1"].deck = []
    state.players["p2"].hand = []
    state.players["p2"].deck = []
    state.players["p2"].discard_pile = []

    updated = apply(
        state,
        PlayCardMove(player_id="p1", card_id="generic_force_discard_then_gain", hand_index=0),
    )

    assert updated.pending_generic_choice is None
    assert updated.resource_pool.power == 1
    assert legal_moves(updated)


def test_generic_promote_top_of_deck_uses_shuffle_refill_rules() -> None:
    promoter = _sequence_card(
        "generic_promote_top",
        [_action("promote", "promote_card", source_fragment="promote_top_of_deck")],
    )
    fodder = _sequence_card("fodder_card", [_action("noop", "gain_resource", metadata={"resource": "power"})])
    state = _state_for_cards(
        [promoter, fodder],
        [{"card_id": "generic_promote_top", "count": 1}, {"card_id": "fodder_card", "count": 1}],
    )
    state.players["p1"].hand = ["generic_promote_top"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = ["fodder_card"]

    updated = apply(
        state,
        PlayCardMove(player_id="p1", card_id="generic_promote_top", hand_index=0),
    )

    assert updated.pending_generic_choice is None
    assert updated.players["p1"].inner_circle == ["fodder_card"]
    assert updated.players["p1"].deck == []
    assert updated.players["p1"].discard_pile == []


def test_generic_play_card_from_inner_circle_without_removal() -> None:
    source = _sequence_card(
        "generic_play_inner_circle",
        [
            _action(
                "play",
                "play_card",
                target_scope="inner_circle_or_market",
                source_fragment="play_from_inner_circle_without_removal",
            )
        ],
    )
    nested = _sequence_card(
        "inner_gain_power",
        [_action("gain", "gain_resource", metadata={"resource": "power"})],
    )
    state = _state_for_cards(
        [source, nested],
        [{"card_id": "generic_play_inner_circle", "count": 1}, {"card_id": "inner_gain_power", "count": 1}],
    )
    state.players["p1"].hand = ["generic_play_inner_circle"]
    state.players["p1"].deck = []
    state.players["p1"].inner_circle = ["inner_gain_power"]

    played = apply(
        state,
        PlayCardMove(player_id="p1", card_id="generic_play_inner_circle", hand_index=0),
    )
    resolved = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="generic_play_inner_circle",
            selection={"source_zone": "inner_circle", "inner_circle_index": 0},
        ),
    )

    assert resolved.pending_generic_choice is None
    assert resolved.resource_pool.power == 1
    assert resolved.players["p1"].inner_circle == ["inner_gain_power"]
    assert "generic_play_inner_circle" in resolved.players["p1"].played_cards
