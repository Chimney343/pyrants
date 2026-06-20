"""Generic structured-card interpreter tests."""

from __future__ import annotations

import pytest

from engine.errors import IllegalMoveError, MissingRuleImplementationError
from engine.moves import PlayCardMove, ResolveGenericChoiceMove
from engine.rules import apply, legal_moves
from engine.state import build_initial_game_state
from game_setup.loaders import build_game_definition_from_dicts
from tests.scenario_helpers import advance_past_setup

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
                "control_vp": 0,
                "initial_vp_tokens": 0,
            },
            {
                "node_id": "site_b",
                "kind": "site",
                "adjacent_to": ["site_a"],
                "troop_capacity": 2,
                "control_vp": 0,
                "initial_vp_tokens": 0,
            },
        ],
    }
    card_data = {"catalog_id": "generic_test_catalog", "version": "1.0.0", "cards": cards}
    setup_data = {
        "setup_id": "generic_test_setup",
        "starter_deck": {"deck_id": "starter", "entries": starter_entries},
        "market_deck": {"deck_id": "market", "entries": []},
        "market_row_size": 1,
    }
    definition = build_game_definition_from_dicts(board_data, card_data, setup_data)
    return advance_past_setup(build_initial_game_state(definition, ["p1", "p2"], shuffle_seed=0))


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
                "devour",
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


# ---------------------------------------------------------------------------
# Batch A — draw_cards, grant_vp, recruit_card, return_spy
# ---------------------------------------------------------------------------


def test_generic_draw_cards_from_deck() -> None:
    card = _sequence_card("drawer", [_action("draw", "draw_cards")])
    state = _state_for_cards([card], [{"card_id": "drawer", "count": 3}])
    state.players["p1"].hand = ["drawer"]
    state.players["p1"].deck = ["drawer", "drawer"]

    updated = apply(state, PlayCardMove(player_id="p1", card_id="drawer", hand_index=0))
    # count defaults to 1; played card moves from hand to played_cards
    assert len(updated.players["p1"].hand) == 1
    assert len(updated.players["p1"].deck) == 1


def test_generic_draw_cards_shuffles_discard_when_deck_empty() -> None:
    card = _sequence_card("drawer", [_action("draw", "draw_cards")])
    state = _state_for_cards([card], [{"card_id": "drawer", "count": 2}])
    state.players["p1"].hand = ["drawer"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = ["drawer"]

    updated = apply(state, PlayCardMove(player_id="p1", card_id="drawer", hand_index=0))

    assert len(updated.players["p1"].hand) == 1


def test_generic_draw_cards_stops_when_deck_and_discard_empty() -> None:
    card = _sequence_card("drawer", [_action("draw", "draw_cards")])
    state = _state_for_cards([card], [{"card_id": "drawer", "count": 1}])
    state.players["p1"].hand = ["drawer"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []

    updated = apply(state, PlayCardMove(player_id="p1", card_id="drawer", hand_index=0))

    assert updated.players["p1"].hand == []


def test_generic_grant_vp_fixed_count() -> None:
    card = _sequence_card("vp_giver", [_action("vp", "grant_vp")])
    state = _state_for_cards([card], [{"card_id": "vp_giver", "count": 1}])
    state.players["p1"].hand = ["vp_giver"]
    before_score = state.players["p1"].score

    updated = apply(state, PlayCardMove(player_id="p1", card_id="vp_giver", hand_index=0))

    assert updated.players["p1"].score == before_score + 1


def test_generic_grant_vp_scaled_by_inner_circle_cards() -> None:
    fodder = _sequence_card("fodder1", [_action("noop", "gain_resource", metadata={"resource": "power"})])
    fodder2 = _sequence_card("fodder2", [_action("noop", "gain_resource", metadata={"resource": "power"})])
    card = _sequence_card(
        "vp_scaled",
        [_action(
            "vp", "grant_vp",
            source_fragment="scaled_vp",
            metadata={"count_from": "inner_circle_cards", "per": 1},
        )],
    )
    state = _state_for_cards(
        [card, fodder, fodder2],
        [{"card_id": "vp_scaled", "count": 1}, {"card_id": "fodder1", "count": 1}, {"card_id": "fodder2", "count": 1}],
    )
    state.players["p1"].hand = ["vp_scaled"]
    state.players["p1"].inner_circle = ["fodder1", "fodder2"]
    before_score = state.players["p1"].score

    updated = apply(state, PlayCardMove(player_id="p1", card_id="vp_scaled", hand_index=0))

    assert updated.players["p1"].score == before_score + 2


def test_generic_recruit_card_from_market() -> None:
    recruiter = _sequence_card("recruiter", [_action("recruit", "recruit_card")])
    target = _sequence_card("target_card", [_action("noop", "gain_resource", metadata={"resource": "power"})])
    state = _state_for_cards(
        [recruiter, target],
        [{"card_id": "recruiter", "count": 1}, {"card_id": "target_card", "count": 1}],
    )
    state.players["p1"].hand = ["recruiter"]
    state.market.row = ["target_card"]
    state.resource_pool.influence = 10
    before_discard = len(state.players["p1"].discard_pile)

    played = apply(state, PlayCardMove(player_id="p1", card_id="recruiter", hand_index=0))
    updated = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="recruiter",
            selection={"market_slot": 0},
        ),
    )

    assert len(updated.players["p1"].discard_pile) == before_discard + 1
    assert "target_card" in updated.players["p1"].discard_pile


def test_generic_recruit_card_rejects_invalid_market_slot() -> None:
    recruiter = _sequence_card("recruiter", [_action("recruit", "recruit_card")])
    state = _state_for_cards([recruiter], [{"card_id": "recruiter", "count": 1}])
    state.players["p1"].hand = ["recruiter"]
    state.market.row = []

    played = apply(state, PlayCardMove(player_id="p1", card_id="recruiter", hand_index=0))

    with pytest.raises(IllegalMoveError):
        apply(
            played,
            ResolveGenericChoiceMove(
                player_id="p1",
                source_card_id="recruiter",
                selection={"market_slot": 0},
            ),
        )


def test_generic_return_spy_self_to_supply() -> None:
    card = _sequence_card(
        "return_my_spy",
        [_action("ret", "return_spy", metadata={"spy_owner": "self"})],
    )
    state = _state_for_cards([card], [{"card_id": "return_my_spy", "count": 1}])
    state.players["p1"].hand = ["return_my_spy"]
    state.board.nodes["site_a"].spies.add("p1")
    before_spies = state.players["p1"].spies_available

    played = apply(state, PlayCardMove(player_id="p1", card_id="return_my_spy", hand_index=0))
    updated = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="return_my_spy",
            selection={"node_id": "site_a", "spy_owner_id": "p1"},
        ),
    )

    assert "p1" not in updated.board.nodes["site_a"].spies
    assert updated.players["p1"].spies_available == before_spies + 1


def test_generic_return_spy_opponent_with_presence_free() -> None:
    card = _sequence_card(
        "return_their_spy",
        [_action("ret", "return_spy", metadata={"spy_owner": "opponent", "free_enemy_return": True})],
    )
    state = _state_for_cards([card], [{"card_id": "return_their_spy", "count": 1}])
    state.players["p1"].hand = ["return_their_spy"]
    state.board.nodes["site_a"].spies.add("p2")
    state.board.nodes["site_a"].troop_slots = ["p1", None]
    before_spies = state.players["p2"].spies_available

    played = apply(state, PlayCardMove(player_id="p1", card_id="return_their_spy", hand_index=0))
    updated = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="return_their_spy",
            selection={"node_id": "site_a", "spy_owner_id": "p2"},
        ),
    )

    assert "p2" not in updated.board.nodes["site_a"].spies
    assert updated.players["p2"].spies_available == before_spies + 1


# ---------------------------------------------------------------------------
# Batch B — conditional_bonus
# ---------------------------------------------------------------------------


def test_generic_conditional_bonus_node_has_other_troop_matched() -> None:
    card = _sequence_card(
        "bonus_card",
        [
            _action("prep", "deploy_troops", target_scope="board_site"),
            _action(
                "bonus", "conditional_bonus",
                metadata={"condition": "selected_node_has_other_player_troop", "resource": "power", "amount": 3},
            ),
        ],
    )
    state = _state_for_cards([card], [{"card_id": "bonus_card", "count": 1}])
    state.players["p1"].hand = ["bonus_card"]
    state.board.nodes["site_a"].troop_slots = ["p2", None]

    played = apply(state, PlayCardMove(player_id="p1", card_id="bonus_card", hand_index=0))
    updated = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="bonus_card",
            selection={"target_node_id": "site_a"},
        ),
    )

    assert updated.resource_pool.power == 3
    assert updated.pending_generic_choice is None


def test_generic_conditional_bonus_node_has_other_troop_noop() -> None:
    card = _sequence_card(
        "bonus_card",
        [
            _action("prep", "deploy_troops", target_scope="board_site"),
            _action(
                "bonus", "conditional_bonus",
                metadata={"condition": "selected_node_has_other_player_troop", "resource": "power", "amount": 3},
            ),
        ],
    )
    state = _state_for_cards([card], [{"card_id": "bonus_card", "count": 1}])
    state.players["p1"].hand = ["bonus_card"]
    state.board.nodes["site_a"].troop_slots = ["p1", None]

    played = apply(state, PlayCardMove(player_id="p1", card_id="bonus_card", hand_index=0))
    updated = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="bonus_card",
            selection={"target_node_id": "site_a"},
        ),
    )

    assert updated.resource_pool.power == 0


def test_generic_conditional_bonus_spies_at_least_matched() -> None:
    card = _sequence_card(
        "bonus_spy",
        [
            _action("prep", "deploy_troops", target_scope="board_site"),
            _action(
                "bonus", "conditional_bonus",
                metadata={"condition": "selected_node_total_spies_at_least", "resource": "influence", "amount": 2, "min_spies": 1},
            ),
        ],
    )
    state = _state_for_cards([card], [{"card_id": "bonus_spy", "count": 1}])
    state.players["p1"].hand = ["bonus_spy"]
    state.board.nodes["site_a"].spies.add("p1")

    played = apply(state, PlayCardMove(player_id="p1", card_id="bonus_spy", hand_index=0))
    updated = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="bonus_spy",
            selection={"target_node_id": "site_a"},
        ),
    )

    assert updated.resource_pool.influence == 2


def test_generic_conditional_bonus_spies_at_least_noop() -> None:
    card = _sequence_card(
        "bonus_spy",
        [
            _action("prep", "deploy_troops", target_scope="board_site"),
            _action(
                "bonus", "conditional_bonus",
                metadata={"condition": "selected_node_total_spies_at_least", "resource": "influence", "amount": 2, "min_spies": 2},
            ),
        ],
    )
    state = _state_for_cards([card], [{"card_id": "bonus_spy", "count": 1}])
    state.players["p1"].hand = ["bonus_spy"]
    state.board.nodes["site_a"].spies.add("p1")

    played = apply(state, PlayCardMove(player_id="p1", card_id="bonus_spy", hand_index=0))
    updated = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="bonus_spy",
            selection={"target_node_id": "site_a"},
        ),
    )

    assert updated.resource_pool.influence == 0


def test_generic_conditional_bonus_focus_aspect_present_matched() -> None:
    card = _sequence_card(
        "bonus_focus",
        [_action(
            "bonus", "conditional_bonus",
            metadata={"condition": "focus_aspect_present", "resource": "influence", "amount": 4, "focus_aspect": "none"},
        )],
    )
    other = _sequence_card("other_card", [_action("noop", "gain_resource", metadata={"resource": "power"})])
    state = _state_for_cards(
        [card, other],
        [{"card_id": "bonus_focus", "count": 1}, {"card_id": "other_card", "count": 1}],
    )
    state.players["p1"].hand = ["bonus_focus", "other_card"]

    updated = apply(state, PlayCardMove(player_id="p1", card_id="bonus_focus", hand_index=0))

    assert updated.resource_pool.influence == 4


def test_generic_conditional_bonus_focus_aspect_present_noop() -> None:
    card = _sequence_card(
        "bonus_focus",
        [_action(
            "bonus", "conditional_bonus",
            metadata={"condition": "focus_aspect_present", "resource": "influence", "amount": 4, "focus_aspect": "ambition"},
        )],
    )
    state = _state_for_cards([card], [{"card_id": "bonus_focus", "count": 1}])
    state.players["p1"].hand = ["bonus_focus"]

    updated = apply(state, PlayCardMove(player_id="p1", card_id="bonus_focus", hand_index=0))

    assert updated.resource_pool.influence == 0


def test_generic_conditional_bonus_trophy_hall_at_least_matched() -> None:
    card = _sequence_card(
        "bonus_trophy",
        [_action(
            "bonus", "conditional_bonus",
            metadata={"condition": "player_trophy_hall_non_white_at_least", "resource": "power", "amount": 5, "min_trophies": 2},
        )],
    )
    state = _state_for_cards([card], [{"card_id": "bonus_trophy", "count": 1}])
    state.players["p1"].hand = ["bonus_trophy"]
    state.players["p1"].trophy_hall = ["p2", "p2"]

    updated = apply(state, PlayCardMove(player_id="p1", card_id="bonus_trophy", hand_index=0))

    assert updated.resource_pool.power == 5


def test_generic_conditional_bonus_trophy_hall_at_least_noop() -> None:
    card = _sequence_card(
        "bonus_trophy",
        [_action(
            "bonus", "conditional_bonus",
            metadata={"condition": "player_trophy_hall_non_white_at_least", "resource": "power", "amount": 5, "min_trophies": 3},
        )],
    )
    state = _state_for_cards([card], [{"card_id": "bonus_trophy", "count": 1}])
    state.players["p1"].hand = ["bonus_trophy"]
    state.players["p1"].trophy_hall = ["p2", "p2"]

    updated = apply(state, PlayCardMove(player_id="p1", card_id="bonus_trophy", hand_index=0))

    assert updated.resource_pool.power == 0


def test_generic_conditional_bonus_inner_circle_at_least_matched() -> None:
    card = _sequence_card(
        "bonus_ic",
        [_action(
            "bonus", "conditional_bonus",
            metadata={"condition": "player_inner_circle_at_least", "resource": "influence", "amount": 3, "min_cards": 2},
        )],
    )
    state = _state_for_cards([card], [{"card_id": "bonus_ic", "count": 1}])
    state.players["p1"].hand = ["bonus_ic"]
    state.players["p1"].inner_circle = ["a", "b"]

    updated = apply(state, PlayCardMove(player_id="p1", card_id="bonus_ic", hand_index=0))

    assert updated.resource_pool.influence == 3


def test_generic_conditional_bonus_inner_circle_at_least_noop() -> None:
    card = _sequence_card(
        "bonus_ic",
        [_action(
            "bonus", "conditional_bonus",
            metadata={"condition": "player_inner_circle_at_least", "resource": "influence", "amount": 3, "min_cards": 3},
        )],
    )
    state = _state_for_cards([card], [{"card_id": "bonus_ic", "count": 1}])
    state.players["p1"].hand = ["bonus_ic"]
    state.players["p1"].inner_circle = ["a", "b"]

    updated = apply(state, PlayCardMove(player_id="p1", card_id="bonus_ic", hand_index=0))

    assert updated.resource_pool.influence == 0


# ---------------------------------------------------------------------------
# Batch C — custom_effect
# ---------------------------------------------------------------------------


def test_generic_custom_effect_scaled_resource_from_trophy_hall() -> None:
    card = _sequence_card(
        "custom_card",
        [_action(
            "custom", "custom_effect",
            metadata={"effect_kind": "scaled_resource_from_player_zone", "source_zone": "trophy_hall", "per": 2, "resource": "power"},
        )],
    )
    state = _state_for_cards([card], [{"card_id": "custom_card", "count": 1}])
    state.players["p1"].hand = ["custom_card"]
    state.players["p1"].trophy_hall = ["p2", "p2", "p2", "p2", "p2"]

    updated = apply(state, PlayCardMove(player_id="p1", card_id="custom_card", hand_index=0))

    assert updated.resource_pool.power == 2  # 5 // 2


def test_generic_custom_effect_scaled_resource_from_hand() -> None:
    card = _sequence_card(
        "custom_card",
        [_action(
            "custom", "custom_effect",
            metadata={"effect_kind": "scaled_resource_from_player_zone", "source_zone": "hand", "per": 1, "resource": "power"},
        )],
    )
    state = _state_for_cards([card], [{"card_id": "custom_card", "count": 1}])
    state.players["p1"].hand = ["custom_card"]

    updated = apply(state, PlayCardMove(player_id="p1", card_id="custom_card", hand_index=0))

    assert updated.resource_pool.power == 0  # hand is empty after playing


def test_generic_custom_effect_give_insane_outcast_with_presence() -> None:
    card = _sequence_card(
        "outcast_giver",
        [
            _action("prep", "deploy_troops", target_scope="board_site"),
            _action(
                "gift", "custom_effect",
                metadata={"effect_kind": "give_insane_outcast_to_player_with_presence_on_last_selected_node"},
            ),
        ],
    )
    state = _state_for_cards([card], [{"card_id": "outcast_giver", "count": 1}])
    state.players["p1"].hand = ["outcast_giver"]
    state.board.nodes["site_a"].troop_slots = ["p2", None]

    played = apply(state, PlayCardMove(player_id="p1", card_id="outcast_giver", hand_index=0))
    # First ResolveGenericChoice sets last_selection["target_node_id"]
    # Then auto-resolve hits custom_effect which requires selection
    after_deploy = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="outcast_giver",
            selection={"target_node_id": "site_a"},
        ),
    )
    updated = apply(
        after_deploy,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="outcast_giver",
            selection={"target_player_id": "p2", "selected_node_id": "site_a"},
        ),
    )

    assert "insane_outcast" in updated.players["p2"].discard_pile


def test_generic_custom_effect_give_insane_outcast_to_selected_player() -> None:
    card = _sequence_card(
        "outcast_giver",
        [_action(
            "gift", "custom_effect",
            metadata={"effect_kind": "give_insane_outcast_to_selected_player"},
        )],
    )
    state = _state_for_cards([card], [{"card_id": "outcast_giver", "count": 1}])
    state.players["p1"].hand = ["outcast_giver"]

    played = apply(state, PlayCardMove(player_id="p1", card_id="outcast_giver", hand_index=0))
    updated = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="outcast_giver",
            selection={"target_player_id": "p2"},
        ),
    )

    assert "insane_outcast" in updated.players["p2"].discard_pile


def test_generic_custom_effect_give_insane_outcast_to_each_opponent() -> None:
    card = _sequence_card(
        "outcast_giver",
        [_action(
            "gift", "custom_effect",
            metadata={"effect_kind": "give_insane_outcast_to_each_opponent"},
        )],
    )
    state = _state_for_cards([card], [{"card_id": "outcast_giver", "count": 1}])
    state.players["p1"].hand = ["outcast_giver"]

    updated = apply(state, PlayCardMove(player_id="p1", card_id="outcast_giver", hand_index=0))

    assert "insane_outcast" in updated.players["p2"].discard_pile


def test_generic_custom_effect_mill_deck_to_discard() -> None:
    card = _sequence_card(
        "miller",
        [_action("mill", "custom_effect", metadata={"effect_kind": "mill_deck_to_discard"})],
    )
    state = _state_for_cards([card], [{"card_id": "miller", "count": 3}])
    state.players["p1"].hand = ["miller"]
    state.players["p1"].deck = ["miller", "miller"]

    updated = apply(state, PlayCardMove(player_id="p1", card_id="miller", hand_index=0))

    assert updated.players["p1"].deck == []
    assert "miller" in updated.players["p1"].discard_pile


def test_generic_custom_effect_discard_selected_hand_card_from_self() -> None:
    card = _sequence_card(
        "discarder",
        [
            _action(
                "discard", "custom_effect",
                metadata={"effect_kind": "discard_selected_hand_card_from_self"},
            ),
        ],
    )
    state = _state_for_cards([card], [{"card_id": "discarder", "count": 1}])
    state.players["p1"].hand = ["discarder", "fodder_a", "fodder_b"]

    played = apply(state, PlayCardMove(player_id="p1", card_id="discarder", hand_index=0))

    assert played.pending_generic_choice is not None
    assert played.players["p1"].hand == ["fodder_a", "fodder_b"]

    choice_moves = [
        move for move in legal_moves(played)
        if isinstance(move, ResolveGenericChoiceMove) and move.source_card_id == "discarder"
    ]
    assert len(choice_moves) == 2
    hand_indices = {int(move.selection["hand_index"]) for move in choice_moves}
    assert hand_indices == {0, 1}

    resolved = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="discarder",
            selection={"hand_index": 0},
        ),
    )

    assert resolved.players["p1"].hand == ["fodder_b"]
    assert "fodder_a" in resolved.players["p1"].discard_pile


def test_generic_custom_effect_return_source_card_to_recruit_deck() -> None:
    card = _sequence_card(
        "returner",
        [
            _action(
                "return", "custom_effect",
                metadata={"effect_kind": "return_source_card_to_recruit_deck"},
            ),
        ],
    )
    state = _state_for_cards([card], [{"card_id": "returner", "count": 1}])
    state.players["p1"].hand = ["returner"]

    updated = apply(state, PlayCardMove(player_id="p1", card_id="returner", hand_index=0))

    assert "returner" not in updated.players["p1"].played_cards
    assert "returner" not in updated.players["p1"].hand
    assert "returner" not in updated.players["p1"].discard_pile


# ---------------------------------------------------------------------------
# Batch D — promote_card sub-modes
# ---------------------------------------------------------------------------


def test_generic_promote_from_played_cards() -> None:
    promoter = _sequence_card(
        "promoter",
        [_action("promo", "promote_card", source_fragment="single_promote_from_multiple_zones")],
    )
    target = _sequence_card("fodder", [_action("noop", "gain_resource", metadata={"resource": "power"})])
    state = _state_for_cards(
        [promoter, target],
        [{"card_id": "promoter", "count": 1}, {"card_id": "fodder", "count": 1}],
    )
    state.players["p1"].hand = ["promoter"]
    state.players["p1"].played_cards = ["fodder"]

    played = apply(state, PlayCardMove(player_id="p1", card_id="promoter", hand_index=0))
    updated = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="promoter",
            selection={"source_zone": "played", "target_card_id": "fodder"},
        ),
    )

    assert "fodder" in updated.players["p1"].inner_circle
    assert "fodder" not in updated.players["p1"].played_cards


def test_generic_promote_from_hand() -> None:
    promoter = _sequence_card(
        "promoter",
        [_action("promo", "promote_card", source_fragment="single_promote_from_multiple_zones")],
    )
    target = _sequence_card("fodder", [_action("noop", "gain_resource", metadata={"resource": "power"})])
    state = _state_for_cards(
        [promoter, target],
        [{"card_id": "promoter", "count": 1}, {"card_id": "fodder", "count": 1}],
    )
    state.players["p1"].hand = ["promoter", "fodder"]

    played = apply(state, PlayCardMove(player_id="p1", card_id="promoter", hand_index=0))
    updated = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="promoter",
            selection={"source_zone": "hand", "hand_index": 0},
        ),
    )

    assert "fodder" in updated.players["p1"].inner_circle
    assert "fodder" not in updated.players["p1"].hand


def test_generic_promote_from_discard_specific() -> None:
    promoter = _sequence_card(
        "promoter",
        [_action("promo", "promote_card", source_fragment="promote_from_discard")],
    )
    target = _sequence_card("fodder", [_action("noop", "gain_resource", metadata={"resource": "power"})])
    state = _state_for_cards(
        [promoter, target],
        [{"card_id": "promoter", "count": 1}, {"card_id": "fodder", "count": 1}],
    )
    state.players["p1"].hand = ["promoter"]
    state.players["p1"].discard_pile = ["fodder"]

    played = apply(state, PlayCardMove(player_id="p1", card_id="promoter", hand_index=0))
    updated = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="promoter",
            selection={"discard_index": 0},
        ),
    )

    assert "fodder" in updated.players["p1"].inner_circle
    assert "fodder" not in updated.players["p1"].discard_pile


def test_generic_promote_threshold_self_when_enabled() -> None:
    promoter = _sequence_card(
        "promoter",
        [_action("promo", "promote_card", source_fragment="threshold_self_promote", metadata={"min_trophies": 0})],
    )
    state = _state_for_cards([promoter], [{"card_id": "promoter", "count": 1}])
    state.players["p1"].hand = ["promoter"]
    state.players["p1"].discard_pile = []

    updated = apply(state, PlayCardMove(player_id="p1", card_id="promoter", hand_index=0))

    assert "promoter" in updated.players["p1"].inner_circle


def test_generic_promote_threshold_self_noop_when_disabled() -> None:
    promoter = _sequence_card(
        "promoter",
        [_action("promo", "promote_card", source_fragment="threshold_self_promote", metadata={"min_trophies": 99})],
    )
    state = _state_for_cards([promoter], [{"card_id": "promoter", "count": 1}])
    state.players["p1"].hand = ["promoter"]

    updated = apply(state, PlayCardMove(player_id="p1", card_id="promoter", hand_index=0))

    assert "promoter" not in updated.players["p1"].inner_circle


def test_generic_promote_end_of_turn_queues_pending() -> None:
    promoter = _sequence_card(
        "promoter",
        [
            {
                "action_id": "promo",
                "op": "promote_card",
                "target_scope": "self",
                "timing": "end_of_turn",
                "optional": False,
                "quantity": {"kind": "unspecified", "value": None},
                "filters": [],
                "source_fragment": "test_fragment",
                "metadata": {},
            }
        ],
    )
    state = _state_for_cards([promoter], [{"card_id": "promoter", "count": 1}])
    state.players["p1"].hand = ["promoter"]
    before_pending = len(state.pending_end_of_turn_promotions)

    updated = apply(state, PlayCardMove(player_id="p1", card_id="promoter", hand_index=0))

    assert len(updated.pending_end_of_turn_promotions) == before_pending + 1
    assert updated.pending_end_of_turn_promotions[-1].card_id == "promoter"


# ---------------------------------------------------------------------------
# Batch E — edge cases
# ---------------------------------------------------------------------------


def test_generic_play_card_skips_nested_card_requiring_choices() -> None:
    """When a play_card action resolves a nested card that requires
    further player choices, the action is silently skipped (the nested
    card's effect is not applied). This is consistent with how
    _auto_resolve_pending_generic skips actions without selectable
    targets. Full nested-pending support will be added later.
    """
    source = _sequence_card(
        "nested_player",
        [
            _action(
                "play", "play_card",
                target_scope="inner_circle_or_market",
                source_fragment="play_from_inner_circle_without_removal",
            ),
        ],
    )
    nested = _sequence_card(
        "inner_needs_selection",
        [_action("deploy", "deploy_troops", target_scope="board_site")],
    )
    state = _state_for_cards(
        [source, nested],
        [{"card_id": "nested_player", "count": 1}, {"card_id": "inner_needs_selection", "count": 1}],
    )
    state.players["p1"].hand = ["nested_player"]
    state.players["p1"].inner_circle = ["inner_needs_selection"]

    played = apply(state, PlayCardMove(player_id="p1", card_id="nested_player", hand_index=0))

    # The nested card (inner_needs_selection) requires a deployment choice.
    # The play_card action skips it gracefully rather than raising.
    updated = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="nested_player",
            selection={"source_zone": "inner_circle", "inner_circle_index": 0},
        ),
    )
    # After skipping, the outer pending advances (only one action, so it clears).
    assert updated.pending_generic_choice is None


def test_generic_play_card_from_market_with_max_cost() -> None:
    cheap = _sequence_card("cheap_card", [_action("noop", "gain_resource", metadata={"resource": "power"})])
    cheap_dict = cheap.copy()
    cheap_dict["card_id"] = "cheap_card"
    cheap_dict["cost"] = 0
    expensive = cheap.copy()
    expensive["card_id"] = "expensive_card"
    expensive["cost"] = 5

    source = _sequence_card(
        "market_player",
        [
            _action(
                "play", "play_card",
                target_scope="inner_circle_or_market",
                source_fragment="play",
                metadata={"max_cost": 3},
            ),
        ],
    )
    state = _state_for_cards(
        [source, cheap_dict, expensive],
        [{"card_id": "market_player", "count": 1}, {"card_id": "cheap_card", "count": 1}, {"card_id": "expensive_card", "count": 1}],
    )
    state.players["p1"].hand = ["market_player"]
    state.market.row = ["cheap_card"]
    state.resource_pool.influence = 10

    played = apply(state, PlayCardMove(player_id="p1", card_id="market_player", hand_index=0))
    updated = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="market_player",
            selection={"source_zone": "market", "market_slot": 0},
        ),
    )

    assert updated.resource_pool.power == 1
    assert updated.pending_generic_choice is None


def test_generic_gain_resource_rejects_unknown_resource() -> None:
    card = _sequence_card(
        "bad_gain",
        [_action("gain", "gain_resource", metadata={"resource": "unknown_resource"})],
    )
    state = _state_for_cards([card], [{"card_id": "bad_gain", "count": 1}])
    state.players["p1"].hand = ["bad_gain"]

    with pytest.raises(MissingRuleImplementationError, match="unknown resource"):
        apply(state, PlayCardMove(player_id="p1", card_id="bad_gain", hand_index=0))
