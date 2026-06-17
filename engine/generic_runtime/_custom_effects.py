"""Custom card effect handlers — dispatched from custom_effect action op."""

from __future__ import annotations

from collections.abc import Callable

from engine.errors import (
    IllegalMoveError,
    RuleViolationError,
)
from engine.generic_runtime._utils import (
    _require_selection_int,
    _require_selection_string,
)
from engine.helpers import (
    WHITE_TROOP_OWNER,
    _grant_resource,
    has_presence,
)
from engine.state import (
    CardAction,
    CardDefinition,
    GameState,
    _cow_market_state,
    _cow_node,
    _cow_player,
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

    updated = state._cow_clone()
    _cow_player(updated, target_player_id).discard_pile.append("insane_outcast")
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

    updated = state._cow_clone()
    _cow_player(updated, target_player_id).discard_pile.append("insane_outcast")
    return updated


def _custom_effect_give_insane_outcast_to_each_opponent(
    state: GameState,
    player_id: str,
    card: CardDefinition,
    source_card_id: str,
    action: CardAction,
    selection: dict[str, object],
) -> GameState:
    updated = state._cow_clone()
    for target_player_id in sorted(updated.players):
        if target_player_id == player_id:
            continue
        _cow_player(updated, target_player_id).discard_pile.append("insane_outcast")
    return updated


def _custom_effect_mill_deck_to_discard(
    state: GameState,
    player_id: str,
    card: CardDefinition,
    source_card_id: str,
    action: CardAction,
    selection: dict[str, object],
) -> GameState:
    updated = state._cow_clone()
    player = _cow_player(updated, player_id)
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

    updated = state._cow_clone()
    target_player = _cow_player(updated, target_player_id)
    try:
        trophy_index = target_player.trophy_hall.index(WHITE_TROOP_OWNER)
    except ValueError as error:
        raise IllegalMoveError("selection target_player_id has no white trophy") from error

    node_state = _cow_node(updated, target_node_id)
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
    updated = state._cow_clone()
    target_player = _cow_player(updated, player_id)
    discarded = target_player.hand.pop(hand_index)
    target_player.discard_pile.append(discarded)
    return updated


def _custom_effect_take_from_devour_pile_to_discard(
    state: GameState,
    player_id: str,
    card: CardDefinition,
    source_card_id: str,
    action: CardAction,
    selection: dict[str, object],
) -> GameState:
    if not state.devour_pile:
        return state
    updated = state._cow_clone()
    top = updated.devour_pile.pop()
    _cow_player(updated, player_id).discard_pile.append(top)
    return updated


def _custom_effect_return_source_card_to_recruit_deck(
    state: GameState,
    player_id: str,
    card: CardDefinition,
    source_card_id: str,
    action: CardAction,
    selection: dict[str, object],
) -> GameState:
    updated = state._cow_clone()
    player = _cow_player(updated, player_id)
    if source_card_id in player.played_cards:
        player.played_cards.remove(source_card_id)
        _cow_market_state(updated).deck.append(source_card_id)
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
    "take_from_devour_pile_to_discard": _custom_effect_take_from_devour_pile_to_discard,
    "return_source_card_to_recruit_deck": _custom_effect_return_source_card_to_recruit_deck,
}
