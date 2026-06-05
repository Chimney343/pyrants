"""Generic structured-card interpreter — private runtime for data-driven card actions."""

from __future__ import annotations

from random import Random

from engine.errors import (
    IllegalMoveError,
    MissingRuleImplementationError,
    RuleViolationError,
    UnknownCardEffectError,
)
from engine.moves import (
    RecruitMove,
    ResolveGenericChoiceMove,
    ReturnSpyMove,
)
from engine.state import (
    CardAction,
    CardDefinition,
    GameState,
    ModalChoiceExecutionModel,
    NodeKind,
    PendingGenericChoiceState,
    PendingPromotionState,
    RepeatChoiceExecutionModel,
    SequenceExecutionModel,
    TurnPhase,
    board_index,
    card_index,
)

from engine.helpers import (
    WHITE_TROOP_OWNER,
    _EFFECT_REGISTRY,
    _action_targets_anywhere,
    _apply_free_assassinate,
    _apply_free_deploy,
    _apply_promote_instruction,
    _apply_recruit,
    _apply_return_spy,
    _can_deploy_to_node,
    _count_controlled_sites,
    _count_controlled_sites_by_troops,
    _focus_requirement_met,
    _focus_requirement_met_for_aspect,
    _grant_resource,
    _promote_card,
    _reshuffle_discard_into_deck,
    _scaled_vp_award_count,
    has_presence,
)

def _resolve_action_count(action: CardAction) -> int:
    if action.quantity.value is not None and action.quantity.value > 0:
        return action.quantity.value
    return 1


def _resolve_runtime_action_count(
    state: GameState,
    player_id: str,
    action: CardAction,
) -> int:
    count_from = str(action.metadata.get("count_from", "")).strip().lower()
    if not count_from:
        sf = action.source_fragment.strip().lower()
        if "by_controlled_sites" in sf or "from_controlled_sites" in sf:
            count_from = "controlled_sites"
    if count_from == "spies_on_board":
        return sum(
            1
            for node in state.board.nodes.values()
            if player_id in node.spies
        )

    if count_from == "assassinations_by_source_effect":
        pending = state.pending_generic_choice
        if pending is None:
            return 0
        prefix = "assassinate_troop:"
        return sum(
            count for key, count in pending.action_counters.items()
            if key.startswith(prefix)
        )

    if count_from == "controlled_sites":
        return _count_controlled_sites(state, player_id)

    if count_from == "owned_control_markers":
        return _count_controlled_sites_by_troops(state, player_id)

    return _resolve_action_count(action)


def _threshold_self_promote_enabled(state: GameState, player_id: str, action: CardAction) -> bool:
    minimum_raw = action.metadata.get("min_trophies", 8)
    try:
        minimum = int(minimum_raw)
    except (TypeError, ValueError) as error:
        raise RuleViolationError("threshold_self_promote min_trophies must be an integer") from error

    count_from = str(action.metadata.get("count_from", "trophy_hall_all")).strip().lower() or "trophy_hall_all"
    player = state.players[player_id]
    if count_from == "trophy_hall_non_white":
        current = sum(1 for owner in player.trophy_hall if owner != WHITE_TROOP_OWNER)
    elif count_from == "trophy_hall_white":
        current = sum(1 for owner in player.trophy_hall if owner == WHITE_TROOP_OWNER)
    else:
        current = len(player.trophy_hall)

    return current >= minimum


def _pending_action_counter_key(action: CardAction) -> str:
    return f"{action.op}:{action.action_id}"


def _pending_action_counter_value(
    pending: PendingGenericChoiceState | None,
    action: CardAction,
) -> int:
    if pending is None:
        return 0
    return int(pending.action_counters.get(_pending_action_counter_key(action), 0))


def _action_requires_additional_choice(
    state: GameState,
    player_id: str,
    action: CardAction,
) -> bool:
    pending = state.pending_generic_choice
    if pending is None:
        return False

    limit = pending.action_repeat_limits.get(_pending_action_counter_key(action))
    if limit is not None:
        return _pending_action_counter_value(pending, action) < limit

    count = _resolve_runtime_action_count(state, player_id, action)
    if count <= 1:
        return False

    return _pending_action_counter_value(pending, action) < count


def _promote_requires_other_card(action: CardAction) -> bool:
    metadata_value = action.metadata.get("requires_another_played_card")
    if isinstance(metadata_value, bool):
        return metadata_value

    if "another" in action.source_fragment:
        return True
    return False


def _promote_required_aspect(card: CardDefinition, action: CardAction) -> str | None:
    metadata_required = str(action.metadata.get("required_aspect", "")).strip().lower()
    if metadata_required:
        return metadata_required

    if "aspect_filtered" not in action.source_fragment:
        return None
    rules_text = card.rules_text.lower()
    if "obedience" in rules_text:
        return "obedience"
    if "malice" in rules_text:
        return "malice"
    if "ambition" in rules_text:
        return "ambition"
    if "guile" in rules_text:
        return "guile"
    return None


def _promote_required_secondary_aspect(action: CardAction) -> str | None:
    required_secondary = str(action.metadata.get("required_secondary_aspect", "")).strip().lower()
    return required_secondary or None


def _promote_from_deck_top(action: CardAction) -> bool:
    return action.source_fragment.strip().lower() == "promote_top_of_deck"


def _promote_from_multiple_zones(action: CardAction) -> bool:
    return action.source_fragment.strip().lower() == "single_promote_from_multiple_zones"


def _promote_from_discard(action: CardAction) -> bool:
    return action.source_fragment.strip().lower() == "promote_from_discard"


def _legal_recruit_card_for_action(candidate: CardDefinition, action: CardAction) -> bool:
    required_aspect = str(action.metadata.get("required_aspect", "")).strip().lower()
    if required_aspect and candidate.aspect != required_aspect:
        return False

    max_cost_raw = action.metadata.get("max_cost")
    if max_cost_raw is not None:
        try:
            max_cost = int(max_cost_raw)
        except (TypeError, ValueError) as error:
            raise RuleViolationError("recruit_card max_cost metadata must be an integer") from error
        if candidate.cost > max_cost:
            return False

    return True


def _resolve_card_option_actions(
    pending: PendingGenericChoiceState,
    execution_model: SequenceExecutionModel | ModalChoiceExecutionModel | RepeatChoiceExecutionModel,
    option_id: str,
) -> list[CardAction]:
    if pending.execution_kind == "modal_choice" and isinstance(execution_model, ModalChoiceExecutionModel):
        option = next((candidate for candidate in execution_model.options if candidate.option_id == option_id), None)
        if option is None:
            raise IllegalMoveError("selected option_id does not exist on execution model")
        return [action.model_copy(deep=True) for action in option.actions]

    if pending.execution_kind == "repeat_choice" and isinstance(execution_model, RepeatChoiceExecutionModel):
        option = next((candidate for candidate in execution_model.options if candidate.option_id == option_id), None)
        if option is None:
            raise IllegalMoveError("selected option_id does not exist on execution model")
        return [action.model_copy(deep=True) for action in option.actions]

    raise RuleViolationError("pending generic choice is inconsistent with card execution model")


def _action_requires_selection(action: CardAction) -> bool:
    if action.op == "promote_card":
        if _promote_from_deck_top(action):
            return False
        if action.source_fragment.strip().lower() == "threshold_self_promote":
            return False
        return action.timing != "end_of_turn"

    if action.op == "custom_effect":
        effect_kind = str(action.metadata.get("effect_kind", "")).strip().lower()
        if effect_kind == "give_insane_outcast_to_player_with_presence_on_last_selected_node":
            return True
        if effect_kind == "give_insane_outcast_to_selected_player":
            return True
        if effect_kind == "steal_white_trophy_to_board":
            return True
        if effect_kind == "discard_selected_hand_card_from_self":
            return True

    if (
        action.op == "force_discard"
        and action.timing == "end_of_turn"
        and action.source_fragment.strip().lower() == "end_of_turn_mass_discard"
    ):
        return False

    return action.op in {
        "deploy_troops",
        "assassinate_troop",
        "supplant_troop",
        "place_spy",
        "return_spy",
        "return_unit",
        "move_troop",
        "force_discard",
        "recruit_card",
        "devour",
        "devour_cost",
        "play_card",
    }


def _action_focus_requirement_met(
    state: GameState,
    player_id: str,
    card: CardDefinition,
    source_card_id: str,
    action: CardAction,
) -> bool:
    if not bool(action.metadata.get("requires_focus", False)):
        return True

    action_focus_aspect = str(action.metadata.get("focus_aspect", "")).strip().lower()
    if action_focus_aspect:
        return _focus_requirement_met_for_aspect(state, player_id, action_focus_aspect, source_card_id)

    return _focus_requirement_met(state, player_id, card, source_card_id)


def _pending_generic_card_definition(state: GameState, pending: PendingGenericChoiceState) -> CardDefinition:
    definition = card_index(state.definition.catalog).get(pending.source_card_id)
    if definition is None:
        raise RuleViolationError(f"Unknown source card for pending generic choice: {pending.source_card_id}")
    return definition


def _pending_generic_active_action(pending: PendingGenericChoiceState) -> CardAction | None:
    if pending.next_action_index < 0 or pending.next_action_index >= len(pending.current_actions):
        return None
    return pending.current_actions[pending.next_action_index]


def _available_repeat_option_ids(pending: PendingGenericChoiceState) -> list[str]:
    if pending.execution_kind != "repeat_choice" or pending.allow_repeat:
        return list(pending.option_ids)

    remaining = [option_id for option_id in pending.option_ids if option_id not in pending.selected_option_ids]
    return remaining or list(pending.option_ids)


def _generic_choice_move(
    player_id: str,
    pending: PendingGenericChoiceState,
    *,
    option_id: str | None = None,
    selection: dict[str, object] | None = None,
) -> ResolveGenericChoiceMove:
    return ResolveGenericChoiceMove(
        player_id=player_id,
        source_card_id=pending.source_card_id,
        option_id=option_id,
        selection=selection or {},
    )


def _option_is_currently_selectable(
    state: GameState,
    player_id: str,
    pending: PendingGenericChoiceState,
    card: CardDefinition,
    option_id: str,
) -> bool:
    execution_model = card.execution_model
    if not isinstance(execution_model, (ModalChoiceExecutionModel, RepeatChoiceExecutionModel)):
        return True

    option_actions = _resolve_card_option_actions(pending, execution_model, option_id)
    if not option_actions:
        return True

    first_action = option_actions[0]
    if first_action.op != "return_spy":
        return True

    probe_pending = pending.model_copy(deep=True)
    probe_pending.awaiting_option = False
    probe_pending.current_actions = option_actions
    probe_pending.next_action_index = 0
    selectable_moves = _legal_generic_target_selection_moves(
        state,
        player_id,
        probe_pending,
        card,
        first_action,
    )
    return bool(selectable_moves)


def _legal_pending_generic_choice_moves(state: GameState, player_id: str) -> list[Move]:
    pending = state.pending_generic_choice
    if pending is None:
        return []

    if pending.awaiting_option:
        if pending.execution_kind == "repeat_choice":
            option_ids = _available_repeat_option_ids(pending)
        else:
            option_ids = list(pending.option_ids)
        card = _pending_generic_card_definition(state, pending)
        option_ids = [
            option_id
            for option_id in option_ids
            if _option_is_currently_selectable(state, player_id, pending, card, option_id)
        ]
        return [_generic_choice_move(player_id, pending, option_id=option_id) for option_id in option_ids]

    card = _pending_generic_card_definition(state, pending)
    action = _pending_generic_active_action(pending)
    if action is None:
        return [_generic_choice_move(player_id, pending)]

    if not _action_focus_requirement_met(state, player_id, card, pending.source_card_id, action):
        return [_generic_choice_move(player_id, pending)]

    if not _action_requires_selection(action):
        return [_generic_choice_move(player_id, pending)]

    selectable_moves = _legal_generic_target_selection_moves(state, player_id, pending, card, action)
    if action.optional:
        return [_generic_choice_move(player_id, pending), *selectable_moves]

    return selectable_moves


def _legal_selection_deploy_troops(
    state: GameState,
    player_id: str,
    pending: PendingGenericChoiceState,
    card: CardDefinition,
    action: CardAction,
) -> list[Move]:
    return [
        _generic_choice_move(player_id, pending, selection={"target_node_id": node_id})
        for node_id in sorted(state.board.nodes)
        if _can_deploy_to_node(state, player_id, node_id)
    ]


def _legal_selection_assassinate_supplant(
    state: GameState,
    player_id: str,
    pending: PendingGenericChoiceState,
    card: CardDefinition,
    action: CardAction,
) -> list[Move]:
    moves: list[Move] = []
    white_only = "white_troop_only" in action.filters
    allow_white = "allow_white_troop" in action.filters
    target_anywhere = _action_targets_anywhere(action)
    requires_returned_spy_site = bool(action.metadata.get("requires_returned_spy_site", False))
    returned_spy_node_id = str(pending.last_selection.get("node_id", "")).strip()
    requires_last_selected_node = bool(action.metadata.get("requires_last_selected_node", False))
    last_selected_node_id = str(pending.last_selection.get("target_node_id", "")).strip()
    for node_id in sorted(state.board.nodes):
        if requires_returned_spy_site:
            if not returned_spy_node_id or node_id != returned_spy_node_id:
                continue
        elif requires_last_selected_node:
            if not last_selected_node_id or node_id != last_selected_node_id:
                continue
        elif not target_anywhere and not has_presence(state, player_id, node_id):
            continue
        node_state = state.board.nodes[node_id]
        for slot_index, occupant in enumerate(node_state.troop_slots):
            if occupant is None or occupant == player_id:
                continue
            if white_only and occupant != WHITE_TROOP_OWNER:
                continue
            if not white_only and not allow_white and occupant == WHITE_TROOP_OWNER:
                continue
            selection: dict[str, object] = {
                "target_node_id": node_id,
                "target_slot_index": slot_index,
            }
            if requires_returned_spy_site:
                selection["returned_node_id"] = returned_spy_node_id
            if requires_last_selected_node:
                selection["required_node_id"] = last_selected_node_id
            moves.append(_generic_choice_move(player_id, pending, selection=selection))
    return moves


def _legal_selection_custom_effect(
    state: GameState,
    player_id: str,
    pending: PendingGenericChoiceState,
    card: CardDefinition,
    action: CardAction,
) -> list[Move]:
    moves: list[Move] = []
    effect_kind = str(action.metadata.get("effect_kind", "")).strip().lower()
    if effect_kind == "give_insane_outcast_to_player_with_presence_on_last_selected_node":
        selected_node_id = str(pending.last_selection.get("target_node_id", "")).strip()
        if not selected_node_id or selected_node_id not in state.board.nodes:
            return moves
        for target_player_id in sorted(state.players):
            if target_player_id == player_id:
                continue
            if not has_presence(state, target_player_id, selected_node_id):
                continue
            moves.append(
                _generic_choice_move(
                    player_id,
                    pending,
                    selection={
                        "target_player_id": target_player_id,
                        "selected_node_id": selected_node_id,
                    },
                )
            )
        return moves
    if effect_kind == "steal_white_trophy_to_board":
        eligible_opponents = [
            target_player_id
            for target_player_id, target_player in state.players.items()
            if target_player_id != player_id and WHITE_TROOP_OWNER in target_player.trophy_hall
        ]
        for target_player_id in sorted(eligible_opponents):
            for node_id in sorted(state.board.nodes):
                node_state = state.board.nodes[node_id]
                for slot_index, occupant in enumerate(node_state.troop_slots):
                    if occupant is not None:
                        continue
                    moves.append(
                        _generic_choice_move(
                            player_id,
                            pending,
                            selection={
                                "target_player_id": target_player_id,
                                "target_node_id": node_id,
                                "target_slot_index": slot_index,
                            },
                        )
                    )
        return moves
    if effect_kind == "give_insane_outcast_to_selected_player":
        for target_player_id in sorted(state.players):
            if target_player_id == player_id:
                continue
            moves.append(
                _generic_choice_move(
                    player_id,
                    pending,
                    selection={"target_player_id": target_player_id},
                )
            )
        return moves
    if effect_kind == "discard_selected_hand_card_from_self":
        player = state.players[player_id]
        for hand_index in range(len(player.hand)):
            moves.append(
                _generic_choice_move(
                    player_id,
                    pending,
                    selection={"hand_index": hand_index},
                )
            )
        return moves
    return moves


def _legal_selection_devour_append_for_zone(
    state: GameState,
    player_id: str,
    pending: PendingGenericChoiceState,
    card: CardDefinition,
    action: CardAction,
    zone: str,
    moves: list[Move],
) -> None:
    if zone == "hand":
        for hand_index in range(len(state.players[player_id].hand)):
            if state.players[player_id].hand[hand_index] == card.card_id:
                continue
            moves.append(
                _generic_choice_move(
                    player_id, pending,
                    selection={"source_zone": zone, "hand_index": hand_index},
                )
            )
        return
    if zone == "inner_circle":
        for inner_circle_index in range(len(state.players[player_id].inner_circle)):
            moves.append(
                _generic_choice_move(
                    player_id, pending,
                    selection={"source_zone": zone, "inner_circle_index": inner_circle_index},
                )
            )
        return
    if zone == "played_self":
        moves.append(
            _generic_choice_move(
                player_id, pending,
                selection={"source_zone": zone, "target_card_id": pending.source_card_id},
            )
        )
        return
    if zone == "market":
        requires_last_selected_market_slot = bool(action.metadata.get("requires_last_selected_market_slot", False))
        if requires_last_selected_market_slot:
            market_slot_raw = pending.last_selection.get("market_slot")
            try:
                market_slot = int(market_slot_raw)
            except (TypeError, ValueError):
                return
            if 0 <= market_slot < len(state.market.row):
                moves.append(
                    _generic_choice_move(
                        player_id, pending,
                        selection={"source_zone": zone, "market_slot": market_slot},
                    )
                )
            return
        for market_slot in range(len(state.market.row)):
            moves.append(
                _generic_choice_move(
                    player_id, pending,
                    selection={"source_zone": zone, "market_slot": market_slot},
                )
            )


def _legal_selection_devour(
    state: GameState,
    player_id: str,
    pending: PendingGenericChoiceState,
    card: CardDefinition,
    action: CardAction,
) -> list[Move]:
    moves: list[Move] = []
    default_zone = str(action.metadata.get("source_zone", action.target_scope)).strip() or "unknown"
    if default_zone == "unknown":
        for zone in ("hand", "played_self", "market", "inner_circle"):
            _legal_selection_devour_append_for_zone(state, player_id, pending, card, action, zone, moves)
        return moves
    _legal_selection_devour_append_for_zone(state, player_id, pending, card, action, default_zone, moves)
    return moves


def _legal_selection_place_spy(
    state: GameState,
    player_id: str,
    pending: PendingGenericChoiceState,
    card: CardDefinition,
    action: CardAction,
) -> list[Move]:
    moves: list[Move] = []
    board_defs = board_index(state.definition.board)
    candidate_sites = [
        node_id
        for node_id in sorted(state.board.nodes)
        if board_defs[node_id].kind == NodeKind.SITE and player_id not in state.board.nodes[node_id].spies
    ]
    if state.players[player_id].spies_available > 0:
        for node_id in candidate_sites:
            moves.append(_generic_choice_move(player_id, pending, selection={"target_node_id": node_id}))
        return moves
    source_sites = [
        node_id
        for node_id in sorted(state.board.nodes)
        if player_id in state.board.nodes[node_id].spies
    ]
    for target_node_id in candidate_sites:
        for source_node_id in source_sites:
            if source_node_id == target_node_id:
                continue
            moves.append(
                _generic_choice_move(
                    player_id,
                    pending,
                    selection={
                        "target_node_id": target_node_id,
                        "source_node_id": source_node_id,
                    },
                )
            )
    return moves


def _legal_selection_return_spy(
    state: GameState,
    player_id: str,
    pending: PendingGenericChoiceState,
    card: CardDefinition,
    action: CardAction,
) -> list[Move]:
    moves: list[Move] = []
    board_defs = board_index(state.definition.board)
    owner_constraint = str(action.metadata.get("spy_owner", "any")).strip().lower()
    free_enemy_return = bool(action.metadata.get("free_enemy_return", False))
    for node_id in sorted(state.board.nodes):
        if board_defs[node_id].kind == NodeKind.ROUTE:
            continue
        node_state = state.board.nodes[node_id]
        for spy_owner_id in sorted(node_state.spies):
            if owner_constraint == "self" and spy_owner_id != player_id:
                continue
            if owner_constraint == "opponent" and spy_owner_id == player_id:
                continue
            if spy_owner_id == player_id:
                moves.append(
                    _generic_choice_move(
                        player_id,
                        pending,
                        selection={"node_id": node_id, "spy_owner_id": spy_owner_id},
                    )
                )
                continue
            if has_presence(state, player_id, node_id) and (
                free_enemy_return or state.resource_pool.power >= 3
            ):
                moves.append(
                    _generic_choice_move(
                        player_id,
                        pending,
                        selection={"node_id": node_id, "spy_owner_id": spy_owner_id},
                    )
                )
    return moves


def _legal_selection_return_unit(
    state: GameState,
    player_id: str,
    pending: PendingGenericChoiceState,
    card: CardDefinition,
    action: CardAction,
) -> list[Move]:
    moves: list[Move] = []
    opponent_only = action.target_scope == "opponent_unit"
    self_only = action.target_scope == "self_unit"
    for node_id in sorted(state.board.nodes):
        node_state = state.board.nodes[node_id]
        for slot_index, owner_id in enumerate(node_state.troop_slots):
            if owner_id is None:
                continue
            if owner_id == WHITE_TROOP_OWNER:
                continue
            if opponent_only and owner_id == player_id:
                continue
            if self_only and owner_id != player_id:
                continue
            moves.append(
                _generic_choice_move(
                    player_id,
                    pending,
                    selection={
                        "unit_type": "troop",
                        "node_id": node_id,
                        "target_slot_index": slot_index,
                    },
                )
            )
        for spy_owner_id in sorted(node_state.spies):
            if opponent_only and spy_owner_id == player_id:
                continue
            if self_only and spy_owner_id != player_id:
                continue
            moves.append(
                _generic_choice_move(
                    player_id,
                    pending,
                    selection={
                        "unit_type": "spy",
                        "node_id": node_id,
                        "spy_owner_id": spy_owner_id,
                    },
                )
            )
    return moves


def _legal_selection_move_troop(
    state: GameState,
    player_id: str,
    pending: PendingGenericChoiceState,
    card: CardDefinition,
    action: CardAction,
) -> list[Move]:
    moves: list[Move] = []
    board_defs = board_index(state.definition.board)
    for source_node_id in sorted(state.board.nodes):
        source_state = state.board.nodes[source_node_id]
        for source_slot_index, occupant in enumerate(source_state.troop_slots):
            if occupant is None or occupant == player_id:
                continue
            for target_node_id in sorted(board_defs[source_node_id].adjacent_to):
                target_state = state.board.nodes[target_node_id]
                for target_slot_index, target_occupant in enumerate(target_state.troop_slots):
                    if target_occupant is not None:
                        continue
                    moves.append(
                        _generic_choice_move(
                            player_id,
                            pending,
                            selection={
                                "source_node_id": source_node_id,
                                "source_slot_index": source_slot_index,
                                "target_node_id": target_node_id,
                                "target_slot_index": target_slot_index,
                            },
                        )
                    )
    return moves


def _legal_selection_force_discard(
    state: GameState,
    player_id: str,
    pending: PendingGenericChoiceState,
    card: CardDefinition,
    action: CardAction,
) -> list[Move]:
    moves: list[Move] = []
    for target_player_id, target_player in state.players.items():
        if target_player_id == player_id:
            continue
        for hand_index in range(len(target_player.hand)):
            moves.append(
                _generic_choice_move(
                    player_id,
                    pending,
                    selection={"target_player_id": target_player_id, "hand_index": hand_index},
                )
            )
    return moves


def _legal_selection_promote_card(
    state: GameState,
    player_id: str,
    pending: PendingGenericChoiceState,
    card: CardDefinition,
    action: CardAction,
) -> list[Move]:
    moves: list[Move] = []
    played_cards = state.players[player_id].played_cards
    if _promote_from_multiple_zones(action):
        if pending.source_card_id in played_cards:
            moves.append(
                _generic_choice_move(
                    player_id,
                    pending,
                    selection={
                        "source_zone": "played",
                        "target_card_id": pending.source_card_id,
                    },
                )
            )
        for hand_index in range(len(state.players[player_id].hand)):
            moves.append(
                _generic_choice_move(
                    player_id,
                    pending,
                    selection={
                        "source_zone": "hand",
                        "hand_index": hand_index,
                    },
                )
            )
        for discard_index in range(len(state.players[player_id].discard_pile)):
            moves.append(
                _generic_choice_move(
                    player_id,
                    pending,
                    selection={
                        "source_zone": "discard",
                        "discard_index": discard_index,
                    },
                )
            )
        return moves
    if _promote_from_discard(action):
        for discard_index in range(len(state.players[player_id].discard_pile)):
            moves.append(
                _generic_choice_move(
                    player_id,
                    pending,
                    selection={"discard_index": discard_index},
                )
            )
        return moves
    promote_other = _promote_requires_other_card(action)
    required_aspect = _promote_required_aspect(card, action)
    cards_by_id = card_index(state.definition.catalog)
    for card_id_ in played_cards:
        if promote_other and card_id_ == pending.source_card_id:
            continue
        if required_aspect is not None:
            definition = cards_by_id.get(card_id_)
            if definition is None or definition.aspect != required_aspect:
                continue
        moves.append(_generic_choice_move(player_id, pending, selection={"target_card_id": card_id_}))
    return moves


def _legal_selection_recruit_card(
    state: GameState,
    player_id: str,
    pending: PendingGenericChoiceState,
    card: CardDefinition,
    action: CardAction,
) -> list[Move]:
    moves: list[Move] = []
    cards_by_id = card_index(state.definition.catalog)
    for market_slot, card_id_ in enumerate(state.market.row):
        definition = cards_by_id.get(card_id_)
        if definition is None:
            continue
        if state.resource_pool.influence >= definition.cost and _legal_recruit_card_for_action(definition, action):
            moves.append(_generic_choice_move(player_id, pending, selection={"market_slot": market_slot}))
    return moves


def _legal_selection_play_card(
    state: GameState,
    player_id: str,
    pending: PendingGenericChoiceState,
    card: CardDefinition,
    action: CardAction,
) -> list[Move]:
    moves: list[Move] = []
    source_fragment = action.source_fragment.strip().lower()
    if source_fragment == "play_from_inner_circle_without_removal":
        for inner_circle_index in range(len(state.players[player_id].inner_circle)):
            moves.append(
                _generic_choice_move(
                    player_id,
                    pending,
                    selection={
                        "source_zone": "inner_circle",
                        "inner_circle_index": inner_circle_index,
                    },
                )
            )
        return moves
    if source_fragment == "play":
        source_zone = str(action.metadata.get("source_zone", "market")).strip().lower() or "market"
        if source_zone != "market":
            raise MissingRuleImplementationError(
                f"generic_card play_card source_zone '{source_zone}' is not implemented yet for card '{card.card_id}'"
            )
        max_cost_raw = action.metadata.get("max_cost")
        max_cost: int | None = None
        if max_cost_raw is not None:
            try:
                max_cost = int(max_cost_raw)
            except (TypeError, ValueError) as error:
                raise RuleViolationError("play_card max_cost metadata must be an integer") from error
        cards_by_id = card_index(state.definition.catalog)
        for market_slot, market_card_id in enumerate(state.market.row):
            definition = cards_by_id.get(market_card_id)
            if definition is None:
                continue
            if max_cost is not None and definition.cost > max_cost:
                continue
            moves.append(
                _generic_choice_move(
                    player_id,
                    pending,
                    selection={
                        "source_zone": "market",
                        "market_slot": market_slot,
                    },
                )
            )
        return moves
    raise MissingRuleImplementationError(
        f"generic_card play_card source_fragment '{action.source_fragment}' is not implemented yet for card '{card.card_id}'"
    )


_LEGAL_TARGET_HANDLERS: dict[str, Callable[..., list[Move]]] = {
    "deploy_troops": _legal_selection_deploy_troops,
    "assassinate_troop": _legal_selection_assassinate_supplant,
    "supplant_troop": _legal_selection_assassinate_supplant,
    "custom_effect": _legal_selection_custom_effect,
    "devour": _legal_selection_devour,
    "devour_cost": _legal_selection_devour,
    "place_spy": _legal_selection_place_spy,
    "return_spy": _legal_selection_return_spy,
    "return_unit": _legal_selection_return_unit,
    "move_troop": _legal_selection_move_troop,
    "force_discard": _legal_selection_force_discard,
    "promote_card": _legal_selection_promote_card,
    "recruit_card": _legal_selection_recruit_card,
    "play_card": _legal_selection_play_card,
}


def _legal_generic_target_selection_moves(
    state: GameState,
    player_id: str,
    pending: PendingGenericChoiceState,
    card: CardDefinition,
    action: CardAction,
) -> list[Move]:
    handler = _LEGAL_TARGET_HANDLERS.get(action.op)
    if handler is not None:
        return handler(state, player_id, pending, card, action)
    return []


def _apply_resolve_generic_choice(state: GameState, move: ResolveGenericChoiceMove) -> GameState:
    if state.phase != TurnPhase.MAIN:
        raise IllegalMoveError("resolve_generic_choice can only be used during the main phase")

    pending = state.pending_generic_choice
    if pending is None:
        raise IllegalMoveError("there is no pending generic choice to resolve")
    if pending.source_card_id != move.source_card_id:
        raise IllegalMoveError("source_card_id does not match the pending generic choice")

    updated = state.model_copy(deep=True)
    pending = updated.pending_generic_choice
    if pending is None:
        raise IllegalMoveError("pending generic choice vanished unexpectedly")

    card = _pending_generic_card_definition(updated, pending)

    if pending.awaiting_option:
        if move.option_id is None:
            raise IllegalMoveError("option_id is required while awaiting generic option selection")

        if pending.execution_kind == "repeat_choice":
            allowed_option_ids = _available_repeat_option_ids(pending)
        else:
            allowed_option_ids = list(pending.option_ids)
        if move.option_id not in allowed_option_ids:
            raise IllegalMoveError("option_id is not valid for the current pending generic choice")

        execution_model = card.execution_model
        if not isinstance(execution_model, (ModalChoiceExecutionModel, RepeatChoiceExecutionModel)):
            raise RuleViolationError("pending generic choice is inconsistent with card execution model")

        pending.current_option_id = move.option_id
        pending.selected_option_ids.append(move.option_id)
        pending.current_actions = _resolve_card_option_actions(pending, execution_model, move.option_id)
        pending.next_action_index = 0
        pending.awaiting_option = False
        if pending.execution_kind == "repeat_choice":
            pending.remaining_repeats -= 1
    else:
        action = _pending_generic_active_action(pending)
        if action is None:
            raise IllegalMoveError("there is no pending generic action to resolve")
        if not _action_focus_requirement_met(updated, move.player_id, card, pending.source_card_id, action):
            next_pending = updated.pending_generic_choice
            if next_pending is None:
                raise RuleViolationError("pending generic state disappeared before action step advanced")
            next_pending.next_action_index += 1
            return _auto_resolve_pending_generic(updated, move.player_id)
        if _action_requires_selection(action):
            if action.optional and not move.selection:
                next_pending = updated.pending_generic_choice
                if next_pending is None:
                    raise RuleViolationError("pending generic state disappeared before action step advanced")
                next_pending.next_action_index += 1
                return _auto_resolve_pending_generic(updated, move.player_id)
            pending.last_selection = dict(move.selection)
            updated = _apply_generic_action(
                updated,
                move.player_id,
                card,
                pending.source_card_id,
                action,
                selection=move.selection,
            )
        else:
            updated = _apply_generic_action(
                updated,
                move.player_id,
                card,
                pending.source_card_id,
                action,
                selection=None,
            )
        next_pending = updated.pending_generic_choice
        if next_pending is None:
            raise RuleViolationError("pending generic state disappeared before action step advanced")
        if _action_requires_additional_choice(updated, move.player_id, action):
            return _auto_resolve_pending_generic(updated, move.player_id)
        next_pending.next_action_index += 1

    return _auto_resolve_pending_generic(updated, move.player_id)


def _auto_resolve_pending_generic(state: GameState, player_id: str) -> GameState:
    updated = state

    while updated.pending_generic_choice is not None:
        pending = updated.pending_generic_choice
        if pending is None:
            break

        card = _pending_generic_card_definition(updated, pending)

        if pending.awaiting_option:
            if pending.execution_kind == "repeat_choice":
                option_ids = _available_repeat_option_ids(pending)
            else:
                option_ids = list(pending.option_ids)

            if not option_ids:
                source_card_id = pending.source_card_id
                promote_payload = card.effect_payload.get("promote")
                updated.pending_generic_choice = None
                return _apply_promote_instruction(updated, player_id, source_card_id, promote_payload)

            return updated

        action = _pending_generic_active_action(pending)
        if action is None:
            if pending.execution_kind == "repeat_choice" and pending.remaining_repeats > 0:
                pending.awaiting_option = True
                pending.current_option_id = None
                pending.current_actions = []
                pending.next_action_index = 0
                continue

            source_card_id = pending.source_card_id
            promote_payload = card.effect_payload.get("promote")
            updated.pending_generic_choice = None
            return _apply_promote_instruction(updated, player_id, source_card_id, promote_payload)

        if not _action_focus_requirement_met(updated, player_id, card, pending.source_card_id, action):
            pending.next_action_index += 1
            continue

        if _action_requires_selection(action):
            selectable_moves = _legal_generic_target_selection_moves(updated, player_id, pending, card, action)
            if not selectable_moves:
                pending.next_action_index += 1
                continue
            return updated

        current_index = pending.next_action_index
        updated = _apply_generic_action(
            updated,
            player_id,
            card,
            pending.source_card_id,
            action,
            selection=dict(pending.last_selection),
        )
        next_pending = updated.pending_generic_choice
        if next_pending is None:
            raise RuleViolationError("pending generic choice disappeared during automatic resolution")
        next_pending.next_action_index = current_index + 1

    return updated


def _require_selection_string(selection: dict[str, object], field: str) -> str:
    value = str(selection.get(field, "")).strip()
    if not value:
        raise IllegalMoveError(f"selection must include non-empty '{field}'")
    return value


def _require_selection_int(selection: dict[str, object], field: str) -> int:
    raw = selection.get(field)
    if isinstance(raw, bool):
        raise IllegalMoveError(f"selection field '{field}' must be an integer")
    if isinstance(raw, int):
        return raw
    try:
        return int(str(raw))
    except (TypeError, ValueError) as error:
        raise IllegalMoveError(f"selection field '{field}' must be an integer") from error


def _apply_devour_once(
    state: GameState,
    player_id: str,
    source_card_id: str,
    source_zone: str,
    *,
    selection: dict[str, object] | None,
) -> GameState:
    updated = state.model_copy(deep=True)
    player = updated.players[player_id]
    selection = selection or {}

    def _record(card_id: str) -> GameState:
        updated.devour_pile.append(card_id)
        return updated

    if source_zone == "hand":
        if not player.hand:
            raise IllegalMoveError("Cannot devour from hand because hand is empty")
        hand_index = _require_selection_int(selection, "hand_index") if "hand_index" in selection else 0
        if hand_index < 0 or hand_index >= len(player.hand):
            raise IllegalMoveError("selection hand_index is out of range")
        return _record(player.hand.pop(hand_index))

    if source_zone == "inner_circle":
        if not player.inner_circle:
            raise IllegalMoveError("Cannot devour from inner_circle because it is empty")
        inner_circle_index = _require_selection_int(selection, "inner_circle_index") if "inner_circle_index" in selection else 0
        if inner_circle_index < 0 or inner_circle_index >= len(player.inner_circle):
            raise IllegalMoveError("selection inner_circle_index is out of range")
        return _record(player.inner_circle.pop(inner_circle_index))

    if source_zone == "played_self":
        target_card_id = str(selection.get("target_card_id", source_card_id)).strip() or source_card_id
        try:
            played_index = player.played_cards.index(target_card_id)
        except ValueError as error:
            raise IllegalMoveError("selection target_card_id is not in played cards") from error
        return _record(player.played_cards.pop(played_index))

    if source_zone == "market":
        if not updated.market.row:
            raise IllegalMoveError("Cannot devour from market because market row is empty")
        market_slot = _require_selection_int(selection, "market_slot") if "market_slot" in selection else 0
        if market_slot < 0 or market_slot >= len(updated.market.row):
            raise IllegalMoveError("selection market_slot is out of range")
        devoured = updated.market.row.pop(market_slot)
        if updated.market.deck:
            updated.market.row.insert(market_slot, updated.market.deck.pop())
        return _record(devoured)

    raise IllegalMoveError(f"Unsupported devour source_zone '{source_zone}'")


def _apply_generic_gain_resource(
    state: GameState,
    player_id: str,
    card: CardDefinition,
    source_card_id: str,
    action: CardAction,
    *,
    selection: dict[str, object] | None,
) -> GameState:
    count = _resolve_runtime_action_count(state, player_id, action)
    resource = str(action.metadata.get("resource", "")).strip().lower()
    if resource not in {"power", "influence"}:
        raise MissingRuleImplementationError(
            f"generic_card action '{action.action_id}' has unknown resource '{resource}'"
        )
    return _grant_resource(state, resource, count)


def _apply_generic_draw_cards(
    state: GameState,
    player_id: str,
    card: CardDefinition,
    source_card_id: str,
    action: CardAction,
    *,
    selection: dict[str, object] | None,
) -> GameState:
    count = _resolve_runtime_action_count(state, player_id, action)
    updated = state.model_copy(deep=True)
    for _ in range(count):
        player = updated.players[player_id]
        if not player.deck and player.discard_pile:
            _reshuffle_discard_into_deck(updated, player_id)
        if not player.deck:
            break
        player.hand.append(player.deck.pop())
    return updated


def _apply_generic_grant_vp(
    state: GameState,
    player_id: str,
    card: CardDefinition,
    source_card_id: str,
    action: CardAction,
    *,
    selection: dict[str, object] | None,
) -> GameState:
    count = _resolve_runtime_action_count(state, player_id, action)
    updated = state.model_copy(deep=True)
    if action.source_fragment.strip().lower().startswith("scaled_vp") or str(action.metadata.get("count_from", "")).strip():
        updated.players[player_id].score += _scaled_vp_award_count(updated, player_id, action)
    else:
        updated.players[player_id].score += count
    return updated


def _apply_generic_devour(
    state: GameState,
    player_id: str,
    card: CardDefinition,
    source_card_id: str,
    action: CardAction,
    *,
    selection: dict[str, object] | None,
) -> GameState:
    count = _resolve_runtime_action_count(state, player_id, action)
    selection = selection or {}
    selected_zone = str(selection.get("source_zone", "")).strip()
    default_zone = str(action.metadata.get("source_zone", action.target_scope)).strip() or "unknown"
    if default_zone == "unknown":
        source_zone = selected_zone
        if not source_zone:
            raise IllegalMoveError("selection source_zone is required for unknown devour source")
    else:
        source_zone = default_zone

    updated = state
    for _ in range(count):
        updated = _apply_devour_once(
            updated,
            player_id,
            source_card_id,
            source_zone,
            selection=selection,
        )
    return updated


def _apply_generic_recruit_card(
    state: GameState,
    player_id: str,
    card: CardDefinition,
    source_card_id: str,
    action: CardAction,
    *,
    selection: dict[str, object] | None,
) -> GameState:
    count = _resolve_runtime_action_count(state, player_id, action)
    selection = selection or {}
    market_slot = _require_selection_int(selection, "market_slot")
    selected_card_id = state.market.row[market_slot] if 0 <= market_slot < len(state.market.row) else ""
    selected_definition = card_index(state.definition.catalog).get(selected_card_id)
    if selected_definition is None:
        raise IllegalMoveError("selection market_slot does not reference a known card")
    if not _legal_recruit_card_for_action(selected_definition, action):
        raise IllegalMoveError("selection market_slot does not satisfy recruit restrictions")
    updated = state
    for _ in range(count):
        updated = _apply_recruit(updated, RecruitMove(player_id=player_id, market_slot=market_slot))
    return updated


def _apply_generic_deploy_troops(
    state: GameState,
    player_id: str,
    card: CardDefinition,
    source_card_id: str,
    action: CardAction,
    *,
    selection: dict[str, object] | None,
) -> GameState:
    selection = selection or {}
    target_node_id = _require_selection_string(selection, "target_node_id")
    updated = _apply_free_deploy(state, player_id, target_node_id)
    pending = updated.pending_generic_choice
    if pending is not None:
        counter_key = _pending_action_counter_key(action)
        pending.action_counters[counter_key] = _pending_action_counter_value(pending, action) + 1
    return updated


def _apply_generic_assassinate_troop(
    state: GameState,
    player_id: str,
    card: CardDefinition,
    source_card_id: str,
    action: CardAction,
    *,
    selection: dict[str, object] | None,
) -> GameState:
    selection = selection or {}
    target_node_id = _require_selection_string(selection, "target_node_id")
    target_slot_index = _require_selection_int(selection, "target_slot_index")
    white_only = "white_troop_only" in action.filters
    requires_last_selected_node = bool(action.metadata.get("requires_last_selected_node", False))

    if target_node_id not in state.board.nodes:
        raise IllegalMoveError("selection target_node_id is unknown")
    if requires_last_selected_node:
        required_node_id = _require_selection_string(selection, "required_node_id")
        if target_node_id != required_node_id:
            raise IllegalMoveError("selection target_node_id must match the previously selected node")
    node_state = state.board.nodes[target_node_id]
    if target_slot_index < 0 or target_slot_index >= len(node_state.troop_slots):
        raise IllegalMoveError("selection target_slot_index is out of range")
    occupant = node_state.troop_slots[target_slot_index]
    if white_only and occupant != WHITE_TROOP_OWNER:
        raise IllegalMoveError("selection target is not a white troop")
    if not white_only and occupant == WHITE_TROOP_OWNER:
        raise IllegalMoveError("selection target cannot be a white troop for this action")

    updated = _apply_free_assassinate(state, player_id, target_node_id, target_slot_index)
    pending = updated.pending_generic_choice
    if pending is not None:
        counter_key = _pending_action_counter_key(action)
        pending.action_counters[counter_key] = _pending_action_counter_value(pending, action) + 1
    return updated


def _apply_generic_supplant_troop(
    state: GameState,
    player_id: str,
    card: CardDefinition,
    source_card_id: str,
    action: CardAction,
    *,
    selection: dict[str, object] | None,
) -> GameState:
    count = _resolve_runtime_action_count(state, player_id, action)
    selection = selection or {}
    target_node_id = _require_selection_string(selection, "target_node_id")
    target_slot_index = _require_selection_int(selection, "target_slot_index")
    white_only = "white_troop_only" in action.filters
    allow_white = "allow_white_troop" in action.filters
    target_anywhere = _action_targets_anywhere(action)
    requires_returned_spy_site = bool(action.metadata.get("requires_returned_spy_site", False))

    updated = state
    for _ in range(count):
        if target_node_id not in updated.board.nodes:
            raise IllegalMoveError("selection target_node_id is unknown")
        if requires_returned_spy_site:
            returned_node_id = _require_selection_string(selection, "returned_node_id")
            if target_node_id != returned_node_id:
                raise IllegalMoveError("selection target_node_id must match returned spy site")
        elif not target_anywhere and not has_presence(updated, player_id, target_node_id):
            raise IllegalMoveError("supplant requires presence at the target node")

        working = updated.model_copy(deep=True)
        node_state = working.board.nodes[target_node_id]
        if target_slot_index < 0 or target_slot_index >= len(node_state.troop_slots):
            raise IllegalMoveError("selection target_slot_index is out of range")

        removed_owner = node_state.troop_slots[target_slot_index]
        if removed_owner is None:
            raise IllegalMoveError("supplant target slot is empty")
        if removed_owner == player_id:
            raise IllegalMoveError("cannot supplant your own troop")
        if white_only and removed_owner != WHITE_TROOP_OWNER:
            raise IllegalMoveError("selection target is not a white troop")
        if not white_only and not allow_white and removed_owner == WHITE_TROOP_OWNER:
            raise IllegalMoveError("selection target cannot be a white troop for this action")

        node_state.troop_slots[target_slot_index] = None
        player = working.players[player_id]
        if removed_owner != WHITE_TROOP_OWNER:
            player.trophy_hall.append(removed_owner)

        if player.barracks > 0:
            node_state.troop_slots[target_slot_index] = player_id
            player.barracks -= 1
        else:
            player.score += 1

        updated = working
    return updated


def _apply_generic_place_spy(
    state: GameState,
    player_id: str,
    card: CardDefinition,
    source_card_id: str,
    action: CardAction,
    *,
    selection: dict[str, object] | None,
) -> GameState:
    count = _resolve_runtime_action_count(state, player_id, action)
    selection = selection or {}
    target_node_id = _require_selection_string(selection, "target_node_id")
    source_node_id = str(selection.get("source_node_id", "")).strip() or None
    updated = state

    for _ in range(count):
        working = updated.model_copy(deep=True)
        board_definitions = board_index(working.definition.board)
        if target_node_id not in working.board.nodes:
            raise IllegalMoveError("selection target_node_id is unknown")
        if board_definitions[target_node_id].kind == NodeKind.ROUTE:
            raise IllegalMoveError("routes cannot hold spies")
        if player_id in working.board.nodes[target_node_id].spies:
            raise IllegalMoveError("cannot place a second spy of the same owner on one node")

        player = working.players[player_id]
        if player.spies_available > 0:
            player.spies_available -= 1
        else:
            if source_node_id is None:
                raise IllegalMoveError("selection source_node_id is required when spy supply is empty")
            if source_node_id == target_node_id:
                raise IllegalMoveError("selection source_node_id must differ from target_node_id")
            if source_node_id not in working.board.nodes:
                raise IllegalMoveError("selection source_node_id is unknown")
            if player_id not in working.board.nodes[source_node_id].spies:
                raise IllegalMoveError("selection source_node_id has no movable spy for this player")
            working.board.nodes[source_node_id].spies.remove(player_id)

        working.board.nodes[target_node_id].spies.add(player_id)
        updated = working

    return updated


def _apply_generic_return_spy(
    state: GameState,
    player_id: str,
    card: CardDefinition,
    source_card_id: str,
    action: CardAction,
    *,
    selection: dict[str, object] | None,
) -> GameState:
    count = _resolve_runtime_action_count(state, player_id, action)
    selection = selection or {}
    node_id = _require_selection_string(selection, "node_id")
    spy_owner_id = _require_selection_string(selection, "spy_owner_id")
    owner_constraint = str(action.metadata.get("spy_owner", "any")).strip().lower()
    free_enemy_return = bool(action.metadata.get("free_enemy_return", False))

    updated = state
    for _ in range(count):
        if owner_constraint == "self" and spy_owner_id != player_id:
            raise IllegalMoveError("selection spy_owner_id must be the active player")
        if owner_constraint == "opponent" and spy_owner_id == player_id:
            raise IllegalMoveError("selection spy_owner_id must be an opponent")

        if free_enemy_return and spy_owner_id != player_id:
            if node_id not in updated.board.nodes:
                raise IllegalMoveError("selection node_id is unknown")
            if board_index(updated.definition.board)[node_id].kind == NodeKind.ROUTE:
                raise IllegalMoveError("routes cannot hold spies")
            if not has_presence(updated, player_id, node_id):
                raise IllegalMoveError("returning an enemy spy requires presence at the node")

            working = updated.model_copy(deep=True)
            node_state = working.board.nodes[node_id]
            if spy_owner_id not in node_state.spies:
                raise IllegalMoveError("target spy is not present at the chosen node")
            node_state.spies.remove(spy_owner_id)
            working.players[spy_owner_id].spies_available += 1
            updated = working
            continue

        updated = _apply_return_spy(
            updated,
            ReturnSpyMove(
                player_id=player_id,
                node_id=node_id,
                spy_owner_id=spy_owner_id,
            ),
        )
    return updated


def _apply_generic_return_unit(
    state: GameState,
    player_id: str,
    card: CardDefinition,
    source_card_id: str,
    action: CardAction,
    *,
    selection: dict[str, object] | None,
) -> GameState:
    count = _resolve_runtime_action_count(state, player_id, action)
    selection = selection or {}
    unit_type = _require_selection_string(selection, "unit_type")
    node_id = _require_selection_string(selection, "node_id")
    opponent_only = action.target_scope == "opponent_unit"
    self_only = action.target_scope == "self_unit"

    updated = state
    for _ in range(count):
        if node_id not in updated.board.nodes:
            raise IllegalMoveError("selection node_id is unknown")
        working = updated.model_copy(deep=True)
        node_state = working.board.nodes[node_id]

        if unit_type == "troop":
            target_slot_index = _require_selection_int(selection, "target_slot_index")
            if target_slot_index < 0 or target_slot_index >= len(node_state.troop_slots):
                raise IllegalMoveError("selection target_slot_index is out of range")
            owner_id = node_state.troop_slots[target_slot_index]
            if owner_id is None:
                raise IllegalMoveError("selected troop slot is empty")
            if owner_id == WHITE_TROOP_OWNER:
                raise IllegalMoveError("return_unit cannot target white troops")
            if opponent_only and owner_id == player_id:
                raise IllegalMoveError("selection must target an opponent unit")
            if self_only and owner_id != player_id:
                raise IllegalMoveError("selection must target an active player unit")
            node_state.troop_slots[target_slot_index] = None
            if owner_id in working.players:
                working.players[owner_id].barracks += 1
            updated = working
            continue

        if unit_type == "spy":
            spy_owner_id = _require_selection_string(selection, "spy_owner_id")
            if spy_owner_id not in node_state.spies:
                raise IllegalMoveError("selection spy_owner_id is not present at node")
            if opponent_only and spy_owner_id == player_id:
                raise IllegalMoveError("selection must target an opponent unit")
            if self_only and spy_owner_id != player_id:
                raise IllegalMoveError("selection must target an active player unit")
            node_state.spies.remove(spy_owner_id)
            if spy_owner_id in working.players:
                working.players[spy_owner_id].spies_available += 1
            updated = working
            continue

        raise IllegalMoveError("selection unit_type must be 'troop' or 'spy'")

    return updated


def _apply_generic_move_troop(
    state: GameState,
    player_id: str,
    card: CardDefinition,
    source_card_id: str,
    action: CardAction,
    *,
    selection: dict[str, object] | None,
) -> GameState:
    count = _resolve_runtime_action_count(state, player_id, action)
    selection = selection or {}
    source_node_id = _require_selection_string(selection, "source_node_id")
    source_slot_index = _require_selection_int(selection, "source_slot_index")
    target_node_id = _require_selection_string(selection, "target_node_id")
    target_slot_index = _require_selection_int(selection, "target_slot_index")

    updated = state
    for _ in range(count):
        board_definitions = board_index(updated.definition.board)
        if source_node_id not in updated.board.nodes or target_node_id not in updated.board.nodes:
            raise IllegalMoveError("selection source or target node is unknown")
        if target_node_id not in board_definitions[source_node_id].adjacent_to:
            raise IllegalMoveError("selection target_node_id is not adjacent to source_node_id")

        working = updated.model_copy(deep=True)
        source_state = working.board.nodes[source_node_id]
        target_state = working.board.nodes[target_node_id]

        if source_slot_index < 0 or source_slot_index >= len(source_state.troop_slots):
            raise IllegalMoveError("selection source_slot_index is out of range")
        if target_slot_index < 0 or target_slot_index >= len(target_state.troop_slots):
            raise IllegalMoveError("selection target_slot_index is out of range")

        occupant = source_state.troop_slots[source_slot_index]
        if occupant is None:
            raise IllegalMoveError("selection source slot is empty")
        if occupant == player_id:
            raise IllegalMoveError("selection source slot must contain an enemy troop")
        if target_state.troop_slots[target_slot_index] is not None:
            raise IllegalMoveError("selection target slot is occupied")

        source_state.troop_slots[source_slot_index] = None
        target_state.troop_slots[target_slot_index] = occupant
        updated = working
    return updated


def _apply_generic_force_discard(
    state: GameState,
    player_id: str,
    card: CardDefinition,
    source_card_id: str,
    action: CardAction,
    *,
    selection: dict[str, object] | None,
) -> GameState:
    if action.timing == "end_of_turn" and action.source_fragment.strip().lower() == "end_of_turn_mass_discard":
        return state

    count = _resolve_runtime_action_count(state, player_id, action)
    selection = selection or {}
    target_player_id = _require_selection_string(selection, "target_player_id")
    hand_index = _require_selection_int(selection, "hand_index")

    updated = state
    for _ in range(count):
        working = updated.model_copy(deep=True)
        if target_player_id == player_id:
            raise IllegalMoveError("selection target_player_id must be an opponent")
        if target_player_id not in working.players:
            raise IllegalMoveError("selection target_player_id is unknown")

        target_player = working.players[target_player_id]
        if hand_index < 0 or hand_index >= len(target_player.hand):
            raise IllegalMoveError("selection hand_index is out of range")

        target_player.discard_pile.append(target_player.hand.pop(hand_index))
        updated = working

    return updated


def _apply_generic_promote_card(
    state: GameState,
    player_id: str,
    card: CardDefinition,
    source_card_id: str,
    action: CardAction,
    *,
    selection: dict[str, object] | None,
) -> GameState:
    count = _resolve_runtime_action_count(state, player_id, action)
    selection = selection or {}

    if _promote_from_deck_top(action):
        updated = state
        for _ in range(count):
            working = updated.model_copy(deep=True)
            player = working.players[player_id]
            if not player.deck and player.discard_pile:
                _reshuffle_discard_into_deck(working, player_id)
            if not player.deck:
                updated = working
                continue
            player.inner_circle.append(player.deck.pop())
            updated = working
        return updated

    if _promote_from_multiple_zones(action):
        source_zone = _require_selection_string(selection, "source_zone").strip().lower()
        updated = state
        for _ in range(count):
            working = updated.model_copy(deep=True)
            player = working.players[player_id]

            if source_zone == "played":
                target_card_id = _require_selection_string(selection, "target_card_id")
                try:
                    played_index = player.played_cards.index(target_card_id)
                except ValueError as error:
                    raise IllegalMoveError("selection target_card_id is not in played cards") from error
                player.inner_circle.append(player.played_cards.pop(played_index))
                updated = working
                continue

            if source_zone == "hand":
                hand_index = _require_selection_int(selection, "hand_index")
                if hand_index < 0 or hand_index >= len(player.hand):
                    raise IllegalMoveError("selection hand_index is out of range")
                player.inner_circle.append(player.hand.pop(hand_index))
                updated = working
                continue

            if source_zone == "discard":
                discard_index = _require_selection_int(selection, "discard_index")
                if discard_index < 0 or discard_index >= len(player.discard_pile):
                    raise IllegalMoveError("selection discard_index is out of range")
                player.inner_circle.append(player.discard_pile.pop(discard_index))
                updated = working
                continue

            raise IllegalMoveError("selection source_zone must be one of: played, hand, discard")

        return updated

    if _promote_from_discard(action):
        discard_index = _require_selection_int(selection, "discard_index")
        updated = state
        for _ in range(count):
            working = updated.model_copy(deep=True)
            player = working.players[player_id]
            if discard_index < 0 or discard_index >= len(player.discard_pile):
                raise IllegalMoveError("selection discard_index is out of range")
            player.inner_circle.append(player.discard_pile.pop(discard_index))
            updated = working
        return updated

    if action.source_fragment.strip().lower() == "threshold_self_promote":
        if not _threshold_self_promote_enabled(state, player_id, action):
            return state
        updated = state.model_copy(deep=True)
        _promote_card(updated, player_id, source_card_id)
        return updated

    promote_other = _promote_requires_other_card(action)
    required_aspect = _promote_required_aspect(card, action)
    required_secondary_aspect = _promote_required_secondary_aspect(action)
    repeat_while_targets = bool(action.metadata.get("repeat_while_targets", False))

    if action.timing == "end_of_turn":
        updated = state
        for _ in range(count):
            working = updated.model_copy(deep=True)
            working.pending_end_of_turn_promotions.append(
                PendingPromotionState(
                    card_id=source_card_id,
                    timing="end_of_turn",
                    optional=bool(action.optional),
                    deferred_choice=True,
                    source_card_id=source_card_id,
                    requires_another_played_card=promote_other,
                    required_aspect=required_aspect,
                    required_secondary_aspect=required_secondary_aspect,
                    repeat_while_targets=repeat_while_targets,
                )
            )
            updated = working
        return updated

    target_card_id = _require_selection_string(selection, "target_card_id")
    cards_by_id = card_index(state.definition.catalog)

    updated = state
    for _ in range(count):
        if promote_other and target_card_id == source_card_id:
            raise IllegalMoveError("selection target_card_id must be another played card")
        if required_aspect is not None:
            definition = cards_by_id.get(target_card_id)
            if definition is None or definition.aspect != required_aspect:
                raise IllegalMoveError("selection target_card_id does not satisfy required aspect")
        if required_secondary_aspect is not None:
            definition = cards_by_id.get(target_card_id)
            if definition is None or required_secondary_aspect not in definition.secondary_aspects:
                raise IllegalMoveError("selection target_card_id does not satisfy required secondary aspect")
        working = updated.model_copy(deep=True)
        _promote_card(working, player_id, target_card_id)
        updated = working
    return updated


def _apply_generic_play_card(
    state: GameState,
    player_id: str,
    card: CardDefinition,
    source_card_id: str,
    action: CardAction,
    *,
    selection: dict[str, object] | None,
) -> GameState:
    selection = selection or {}
    source_fragment = action.source_fragment.strip().lower()
    nested_card_id: str

    if source_fragment == "play_from_inner_circle_without_removal":
        source_zone = str(selection.get("source_zone", "")).strip().lower()
        if source_zone != "inner_circle":
            raise IllegalMoveError("selection source_zone must be 'inner_circle'")

        inner_circle_index = _require_selection_int(selection, "inner_circle_index")
        player = state.players[player_id]
        if inner_circle_index < 0 or inner_circle_index >= len(player.inner_circle):
            raise IllegalMoveError("selection inner_circle_index is out of range")

        nested_card_id = player.inner_circle[inner_circle_index]
    elif source_fragment == "play":
        source_zone = str(selection.get("source_zone", "")).strip().lower()
        if source_zone != "market":
            raise IllegalMoveError("selection source_zone must be 'market'")

        market_slot = _require_selection_int(selection, "market_slot")
        if market_slot < 0 or market_slot >= len(state.market.row):
            raise IllegalMoveError("selection market_slot is out of range")

        nested_card_id = state.market.row[market_slot]
        cards_by_id = card_index(state.definition.catalog)
        nested_definition_for_cost = cards_by_id.get(nested_card_id)
        if nested_definition_for_cost is None:
            raise IllegalMoveError("selection market_slot does not reference a known card")

        max_cost_raw = action.metadata.get("max_cost")
        if max_cost_raw is not None:
            try:
                max_cost = int(max_cost_raw)
            except (TypeError, ValueError) as error:
                raise RuleViolationError("play_card max_cost metadata must be an integer") from error
            if nested_definition_for_cost.cost > max_cost:
                raise IllegalMoveError("selection market_slot exceeds play_card max_cost")
    else:
        raise MissingRuleImplementationError(
            f"generic_card play_card source_fragment '{action.source_fragment}' is not implemented yet for card '{card.card_id}'"
        )
    nested_definition = card_index(state.definition.catalog).get(nested_card_id)
    if nested_definition is None:
        raise IllegalMoveError("selected card for play_card is not known in catalog")

    nested_effect = _EFFECT_REGISTRY.get(nested_definition.effect_key)
    if nested_effect is None:
        raise UnknownCardEffectError(
            f"Card '{nested_card_id}' references unregistered effect '{nested_definition.effect_key}'"
        )

    working = state.model_copy(deep=True)
    outer_pending = working.pending_generic_choice.model_copy(deep=True)
    working.pending_generic_choice = None
    working.pending_ability = None

    resolved = nested_effect(working, player_id, nested_definition)
    if resolved.pending_generic_choice is not None:
        # The nested card requires choices that cannot be auto-resolved inside
        # a play_card action (e.g. place_spy, deploy_troops with valid targets).
        # Skip the action rather than raising ÔÇö consistent with how
        # _auto_resolve_pending_generic skips actions when no selectable
        # targets exist. Full nested-pending support will be added later.
        resolved.pending_generic_choice = outer_pending
        return resolved
    if resolved.pending_ability is not None:
        raise MissingRuleImplementationError(
            "play_card currently supports only nested cards without paid ability prompts"
        )

    resolved.pending_generic_choice = outer_pending
    return resolved


def _apply_generic_conditional_bonus(
    state: GameState,
    player_id: str,
    card: CardDefinition,
    source_card_id: str,
    action: CardAction,
    *,
    selection: dict[str, object] | None,
) -> GameState:
    count = _resolve_runtime_action_count(state, player_id, action)
    selection = selection or {}
    condition = str(action.metadata.get("condition", "")).strip().lower()
    resource = str(action.metadata.get("resource", "")).strip().lower()
    amount_raw = action.metadata.get("amount", count)
    try:
        amount = int(amount_raw)
    except (TypeError, ValueError) as error:
        raise RuleViolationError("conditional_bonus amount must be an integer") from error

    if condition == "selected_node_has_other_player_troop":
        node_id = str(selection.get("target_node_id", "")).strip()
        if not node_id or node_id not in state.board.nodes:
            return state
        node_state = state.board.nodes[node_id]
        has_other_troop = any(
            occupant is not None and occupant not in {player_id, WHITE_TROOP_OWNER}
            for occupant in node_state.troop_slots
        )
        if not has_other_troop:
            return state
        return _grant_resource(state, resource or "influence", amount)

    if condition == "selected_node_total_spies_at_least":
        node_id = str(selection.get("target_node_id", "")).strip()
        minimum_raw = action.metadata.get("min_spies", 0)
        try:
            minimum = int(minimum_raw)
        except (TypeError, ValueError) as error:
            raise RuleViolationError("conditional_bonus min_spies must be an integer") from error
        if node_id and node_id in state.board.nodes and len(state.board.nodes[node_id].spies) >= minimum:
            return _grant_resource(state, resource or "power", amount)
        return state

    if condition == "focus_aspect_present":
        focus_aspect = str(action.metadata.get("focus_aspect", card.aspect)).strip().lower()
        if _focus_requirement_met_for_aspect(state, player_id, focus_aspect, source_card_id):
            return _grant_resource(state, resource or "influence", amount)
        return state

    if condition == "player_trophy_hall_non_white_at_least":
        minimum_raw = action.metadata.get("min_trophies", 0)
        try:
            minimum = int(minimum_raw)
        except (TypeError, ValueError) as error:
            raise RuleViolationError("conditional_bonus min_trophies must be an integer") from error
        player = state.players[player_id]
        non_white_trophies = sum(1 for owner in player.trophy_hall if owner != WHITE_TROOP_OWNER)
        if non_white_trophies >= minimum:
            return _grant_resource(state, resource or "power", amount)
        return state

    if condition == "player_inner_circle_at_least":
        minimum_raw = action.metadata.get("min_cards", 0)
        try:
            minimum = int(minimum_raw)
        except (TypeError, ValueError) as error:
            raise RuleViolationError("conditional_bonus min_cards must be an integer") from error
        if len(state.players[player_id].inner_circle) >= minimum:
            return _grant_resource(state, resource or "influence", amount)
        return state

    raise MissingRuleImplementationError(
        f"generic_card conditional_bonus is not implemented yet for card '{card.card_id}'"
    )


def _apply_generic_custom_effect(
    state: GameState,
    player_id: str,
    card: CardDefinition,
    source_card_id: str,
    action: CardAction,
    *,
    selection: dict[str, object] | None,
) -> GameState:
    selection = selection or {}
    effect_kind = str(action.metadata.get("effect_kind", "")).strip().lower()
    handler = _CUSTOM_EFFECT_HANDLERS.get(effect_kind)
    if handler is not None:
        return handler(state, player_id, card, source_card_id, action, selection)

    raise MissingRuleImplementationError(
        f"generic_card custom_effect is not implemented yet for card '{card.card_id}'"
    )


def _custom_effect_scaled_resource_from_player_zone(
    state: GameState,
    player_id: str,
    card: CardDefinition,
    source_card_id: str,
    action: CardAction,
    selection: dict[str, object],
) -> GameState:
    source_zone = str(action.metadata.get("source_zone", "")).strip().lower()
    per_raw = action.metadata.get("per", 1)
    try:
        per = int(per_raw)
    except (TypeError, ValueError) as error:
        raise RuleViolationError("custom_effect per must be an integer") from error
    if per <= 0:
        raise RuleViolationError("custom_effect per must be greater than zero")

    resource = str(action.metadata.get("resource", "power")).strip().lower()
    player = state.players[player_id]
    if source_zone == "trophy_hall":
        source_count = len(player.trophy_hall)
    elif source_zone == "hand":
        source_count = len(player.hand)
    elif source_zone == "discard_pile":
        source_count = len(player.discard_pile)
    elif source_zone == "inner_circle":
        source_count = len(player.inner_circle)
    elif source_zone == "played_cards":
        source_count = len(player.played_cards)
    else:
        raise RuleViolationError("custom_effect source_zone is unsupported")

    gained = source_count // per
    return _grant_resource(state, resource, gained)


def _custom_effect_give_insane_outcast_to_player_with_presence(
    state: GameState,
    player_id: str,
    card: CardDefinition,
    source_card_id: str,
    action: CardAction,
    selection: dict[str, object],
) -> GameState:
    target_player_id = _require_selection_string(selection, "target_player_id")
    selected_node_id = _require_selection_string(selection, "selected_node_id")
    if target_player_id == player_id:
        raise IllegalMoveError("selection target_player_id must be an opponent")
    if target_player_id not in state.players:
        raise IllegalMoveError("selection target_player_id is unknown")
    if selected_node_id not in state.board.nodes:
        raise IllegalMoveError("selection selected_node_id is unknown")
    if not has_presence(state, target_player_id, selected_node_id):
        raise IllegalMoveError("selection target_player_id does not have presence at selected_node_id")

    updated = state.model_copy(deep=True)
    updated.players[target_player_id].discard_pile.append("insane_outcast")
    return updated


def _custom_effect_give_insane_outcast_to_selected_player(
    state: GameState,
    player_id: str,
    card: CardDefinition,
    source_card_id: str,
    action: CardAction,
    selection: dict[str, object],
) -> GameState:
    target_player_id = _require_selection_string(selection, "target_player_id")
    if target_player_id == player_id:
        raise IllegalMoveError("selection target_player_id must be an opponent")
    if target_player_id not in state.players:
        raise IllegalMoveError("selection target_player_id is unknown")

    updated = state.model_copy(deep=True)
    updated.players[target_player_id].discard_pile.append("insane_outcast")
    return updated


def _custom_effect_give_insane_outcast_to_each_opponent(
    state: GameState,
    player_id: str,
    card: CardDefinition,
    source_card_id: str,
    action: CardAction,
    selection: dict[str, object],
) -> GameState:
    updated = state.model_copy(deep=True)
    for target_player_id in sorted(updated.players):
        if target_player_id == player_id:
            continue
        updated.players[target_player_id].discard_pile.append("insane_outcast")
    return updated


def _custom_effect_mill_deck_to_discard(
    state: GameState,
    player_id: str,
    card: CardDefinition,
    source_card_id: str,
    action: CardAction,
    selection: dict[str, object],
) -> GameState:
    updated = state.model_copy(deep=True)
    player = updated.players[player_id]
    player.discard_pile.extend(player.deck)
    player.deck = []
    return updated


def _custom_effect_self_purge_to_supply(
    state: GameState,
    player_id: str,
    card: CardDefinition,
    source_card_id: str,
    action: CardAction,
    selection: dict[str, object],
) -> GameState:
    return state


def _custom_effect_steal_white_trophy_to_board(
    state: GameState,
    player_id: str,
    card: CardDefinition,
    source_card_id: str,
    action: CardAction,
    selection: dict[str, object],
) -> GameState:
    target_player_id = _require_selection_string(selection, "target_player_id")
    target_node_id = _require_selection_string(selection, "target_node_id")
    target_slot_index = _require_selection_int(selection, "target_slot_index")

    if target_player_id == player_id:
        raise IllegalMoveError("selection target_player_id must be an opponent")
    if target_player_id not in state.players:
        raise IllegalMoveError("selection target_player_id is unknown")
    if target_node_id not in state.board.nodes:
        raise IllegalMoveError("selection target_node_id is unknown")

    updated = state.model_copy(deep=True)
    target_player = updated.players[target_player_id]
    try:
        trophy_index = target_player.trophy_hall.index(WHITE_TROOP_OWNER)
    except ValueError as error:
        raise IllegalMoveError("selection target_player_id has no white trophy") from error

    node_state = updated.board.nodes[target_node_id]
    if target_slot_index < 0 or target_slot_index >= len(node_state.troop_slots):
        raise IllegalMoveError("selection target_slot_index is out of range")
    if node_state.troop_slots[target_slot_index] is not None:
        raise IllegalMoveError("selection target slot is occupied")

    target_player.trophy_hall.pop(trophy_index)
    node_state.troop_slots[target_slot_index] = WHITE_TROOP_OWNER
    return updated


def _custom_effect_discard_selected_hand_card_from_self(
    state: GameState,
    player_id: str,
    card: CardDefinition,
    source_card_id: str,
    action: CardAction,
    selection: dict[str, object],
) -> GameState:
    hand_index_raw = selection.get("hand_index")
    if hand_index_raw is None:
        raise IllegalMoveError("selection hand_index is required")
    hand_index = int(hand_index_raw)
    player = state.players[player_id]
    if hand_index < 0 or hand_index >= len(player.hand):
        raise IllegalMoveError("selection hand_index is out of range")
    updated = state.model_copy(deep=True)
    target_player = updated.players[player_id]
    discarded = target_player.hand.pop(hand_index)
    target_player.discard_pile.append(discarded)
    return updated


def _custom_effect_return_source_card_to_recruit_deck(
    state: GameState,
    player_id: str,
    card: CardDefinition,
    source_card_id: str,
    action: CardAction,
    selection: dict[str, object],
) -> GameState:
    updated = state.model_copy(deep=True)
    player = updated.players[player_id]
    if source_card_id in player.played_cards:
        player.played_cards.remove(source_card_id)
        updated.market.deck.append(source_card_id)
    return updated


_CUSTOM_EFFECT_HANDLERS: dict[str, Callable[..., GameState]] = {
    "scaled_resource_from_player_zone": _custom_effect_scaled_resource_from_player_zone,
    "give_insane_outcast_to_player_with_presence_on_last_selected_node": _custom_effect_give_insane_outcast_to_player_with_presence,
    "give_insane_outcast_to_selected_player": _custom_effect_give_insane_outcast_to_selected_player,
    "give_insane_outcast_to_each_opponent": _custom_effect_give_insane_outcast_to_each_opponent,
    "mill_deck_to_discard": _custom_effect_mill_deck_to_discard,
    "self_purge_to_supply": _custom_effect_self_purge_to_supply,
    "steal_white_trophy_to_board": _custom_effect_steal_white_trophy_to_board,
    "discard_selected_hand_card_from_self": _custom_effect_discard_selected_hand_card_from_self,
    "return_source_card_to_recruit_deck": _custom_effect_return_source_card_to_recruit_deck,
}


def _apply_generic_action(
    state: GameState,
    player_id: str,
    card: CardDefinition,
    source_card_id: str,
    action: CardAction,
    *,
    selection: dict[str, object] | None,
) -> GameState:
    if not _action_focus_requirement_met(state, player_id, card, source_card_id, action):
        return state

    handler = _GENERIC_ACTION_APPLIERS.get(action.op)
    if handler is not None:
        return handler(state, player_id, card, source_card_id, action, selection=selection)

    raise MissingRuleImplementationError(
        f"Unknown generic_card action op '{action.op}' for card '{card.card_id}'"
    )


_GENERIC_ACTION_APPLIERS: dict[str, Callable[..., GameState]] = {
    "gain_resource": _apply_generic_gain_resource,
    "draw_cards": _apply_generic_draw_cards,
    "deploy_troops": _apply_generic_deploy_troops,
    "assassinate_troop": _apply_generic_assassinate_troop,
    "supplant_troop": _apply_generic_supplant_troop,
    "place_spy": _apply_generic_place_spy,
    "return_spy": _apply_generic_return_spy,
    "return_unit": _apply_generic_return_unit,
    "move_troop": _apply_generic_move_troop,
    "force_discard": _apply_generic_force_discard,
    "promote_card": _apply_generic_promote_card,
    "recruit_card": _apply_generic_recruit_card,
    "devour": _apply_generic_devour,
    "devour_cost": _apply_generic_devour,
    "grant_vp": _apply_generic_grant_vp,
    "conditional_bonus": _apply_generic_conditional_bonus,
    "custom_effect": _apply_generic_custom_effect,
    "play_card": _apply_generic_play_card,
}


def _resolve_generic_execution(
    state: GameState,
    player_id: str,
    card: CardDefinition,
    source_card_id: str,
) -> GameState:
    execution_model = card.execution_model
    if execution_model is None:
        raise MissingRuleImplementationError(
            f"Card '{card.card_id}' has no execution_model for generic runtime"
        )

    if isinstance(execution_model, SequenceExecutionModel):
        repeat_limits: dict[str, int] = {}
        for action in execution_model.actions:
            if action.quantity.kind == "variable_repeat":
                limit = _resolve_runtime_action_count(state, player_id, action)
                if limit > 1:
                    repeat_limits[_pending_action_counter_key(action)] = limit
        pending = PendingGenericChoiceState(
            source_card_id=source_card_id,
            execution_kind="sequence",
            current_actions=[action.model_copy(deep=True) for action in execution_model.actions],
            next_action_index=0,
            awaiting_option=False,
            action_repeat_limits=repeat_limits,
        )
    elif isinstance(execution_model, ModalChoiceExecutionModel):
        pending = PendingGenericChoiceState(
            source_card_id=source_card_id,
            execution_kind="modal_choice",
            option_ids=[option.option_id for option in execution_model.options],
            awaiting_option=True,
            remaining_repeats=1,
        )
    elif isinstance(execution_model, RepeatChoiceExecutionModel):
        pending = PendingGenericChoiceState(
            source_card_id=source_card_id,
            execution_kind="repeat_choice",
            option_ids=[option.option_id for option in execution_model.options],
            allow_repeat=execution_model.allow_repeat,
            awaiting_option=True,
            remaining_repeats=execution_model.repeat_count,
        )
    else:
        raise MissingRuleImplementationError(
            f"Unsupported execution model kind for card '{card.card_id}'"
        )

    updated = state.model_copy(deep=True)
    updated.pending_generic_choice = pending
    return _auto_resolve_pending_generic(updated, player_id)


