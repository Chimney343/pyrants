"""Action applier functions for generic card action ops."""

from __future__ import annotations

from collections.abc import Callable

from engine.errors import (
    IllegalMoveError,
    MissingRuleImplementationError,
    RuleViolationError,
    UnknownCardEffectError,
)
from engine.generic_runtime._promotion_helpers import (
    _legal_recruit_card_for_action,
    _promote_from_deck_top,
    _promote_from_discard,
    _promote_from_multiple_zones,
    _promote_required_aspect,
    _promote_required_secondary_aspect,
    _promote_requires_other_card,
)
from engine.generic_runtime._utils import (
    _action_focus_requirement_met,
    _pending_action_counter_key,
    _pending_action_counter_value,
    _require_selection_int,
    _require_selection_string,
    _resolve_runtime_action_count,
    _threshold_self_promote_enabled,
    _validate_node_exists,
    _validate_slot_bounds,
)
from engine.helpers import (
    _EFFECT_REGISTRY,
    WHITE_TROOP_OWNER,
    _action_targets_anywhere,
    _apply_free_assassinate,
    _apply_free_deploy,
    _apply_recruit,
    _apply_return_spy,
    _focus_requirement_met_for_aspect,
    _grant_resource,
    _promote_card,
    _reshuffle_discard_into_deck,
    _scaled_vp_award_count,
    has_presence,
)
from engine.moves import RecruitMove, ReturnSpyMove
from engine.state import (
    CardAction,
    CardDefinition,
    GameState,
    NodeKind,
    PendingPromotionState,
    board_index,
    card_index,
)


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
        _validate_slot_bounds(player.hand, hand_index, "hand")
        return _record(player.hand.pop(hand_index))

    if source_zone == "inner_circle":
        if not player.inner_circle:
            raise IllegalMoveError("Cannot devour from inner_circle because it is empty")
        inner_circle_index = _require_selection_int(selection, "inner_circle_index") if "inner_circle_index" in selection else 0
        _validate_slot_bounds(player.inner_circle, inner_circle_index, "inner_circle")
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
        _validate_slot_bounds(updated.market.row, market_slot, "market")
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

    _validate_node_exists(state, target_node_id)
    if requires_last_selected_node:
        required_node_id = _require_selection_string(selection, "required_node_id")
        if target_node_id != required_node_id:
            raise IllegalMoveError("selection target_node_id must match the previously selected node")
    node_state = state.board.nodes[target_node_id]
    _validate_slot_bounds(node_state.troop_slots, target_slot_index, "target_slot")
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
        _validate_node_exists(updated, target_node_id)
        if requires_returned_spy_site:
            returned_node_id = _require_selection_string(selection, "returned_node_id")
            if target_node_id != returned_node_id:
                raise IllegalMoveError("selection target_node_id must match returned spy site")
        elif not target_anywhere and not has_presence(updated, player_id, target_node_id):
            raise IllegalMoveError("supplant requires presence at the target node")

        working = updated.model_copy(deep=True)
        node_state = working.board.nodes[target_node_id]
        _validate_slot_bounds(node_state.troop_slots, target_slot_index, "target_slot")

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
        _validate_node_exists(working, target_node_id)
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
            _validate_node_exists(working, source_node_id)
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
            _validate_node_exists(updated, node_id)
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
        _validate_node_exists(updated, node_id)
        working = updated.model_copy(deep=True)
        node_state = working.board.nodes[node_id]

        if unit_type == "troop":
            target_slot_index = _require_selection_int(selection, "target_slot_index")
            _validate_slot_bounds(node_state.troop_slots, target_slot_index, "target_slot")
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
        _validate_node_exists(updated, source_node_id)
        _validate_node_exists(updated, target_node_id)
        if target_node_id not in board_definitions[source_node_id].adjacent_to:
            raise IllegalMoveError("selection target_node_id is not adjacent to source_node_id")

        working = updated.model_copy(deep=True)
        source_state = working.board.nodes[source_node_id]
        target_state = working.board.nodes[target_node_id]

        _validate_slot_bounds(source_state.troop_slots, source_slot_index, "source_slot")
        _validate_slot_bounds(target_state.troop_slots, target_slot_index, "target_slot")

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
        _validate_slot_bounds(target_player.hand, hand_index, "hand")

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
                _validate_slot_bounds(player.hand, hand_index, "hand")
                player.inner_circle.append(player.hand.pop(hand_index))
                updated = working
                continue

            if source_zone == "discard":
                discard_index = _require_selection_int(selection, "discard_index")
                _validate_slot_bounds(player.discard_pile, discard_index, "discard")
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
            _validate_slot_bounds(player.discard_pile, discard_index, "discard")
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
        _validate_slot_bounds(player.inner_circle, inner_circle_index, "inner_circle")

        nested_card_id = player.inner_circle[inner_circle_index]
    elif source_fragment == "play":
        source_zone = str(selection.get("source_zone", "")).strip().lower()
        if source_zone != "market":
            raise IllegalMoveError("selection source_zone must be 'market'")

        market_slot = _require_selection_int(selection, "market_slot")
        _validate_slot_bounds(state.market.row, market_slot, "market")

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
    from engine.generic_runtime._custom_effects import _CUSTOM_EFFECT_HANDLERS

    selection = selection or {}
    effect_kind = str(action.metadata.get("effect_kind", "")).strip().lower()
    handler = _CUSTOM_EFFECT_HANDLERS.get(effect_kind)
    if handler is not None:
        return handler(state, player_id, card, source_card_id, action, selection)

    raise MissingRuleImplementationError(
        f"generic_card custom_effect is not implemented yet for card '{card.card_id}'"
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
