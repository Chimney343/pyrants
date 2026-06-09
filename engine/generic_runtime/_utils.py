"""Utility helpers shared across generic_runtime sub-modules."""

from __future__ import annotations

from engine.errors import (
    IllegalMoveError,
    RuleViolationError,
)
from engine.helpers import (
    WHITE_TROOP_OWNER,
    _count_controlled_sites,
    _count_controlled_sites_by_troops,
    _focus_requirement_met,
    _focus_requirement_met_for_aspect,
)
from engine.moves import ResolveGenericChoiceMove
from engine.state import (
    CardAction,
    CardDefinition,
    GameState,
    PendingGenericChoiceState,
    card_index,
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


def _action_requires_selection(action: CardAction) -> bool:
    from engine.generic_runtime._promotion_helpers import (
        _promote_from_deck_top,
    )

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


def _require_selection_string(selection: dict[str, object], field: str) -> str:
    value = str(selection.get(field, "")).strip()
    if not value:
        raise IllegalMoveError(f"selection must include non-empty '{field}'")
    return value


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


def _validate_node_exists(state: GameState, node_id: str) -> None:
    if node_id not in state.board.nodes:
        raise IllegalMoveError(f"Unknown node id: {node_id}")


def _validate_slot_bounds(slots: list[str | None], slot_index: int, label: str = "slot") -> None:
    if slot_index < 0 or slot_index >= len(slots):
        raise IllegalMoveError(f"selection {label}_index is out of range")
