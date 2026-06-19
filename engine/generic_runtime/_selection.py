"""Target selection generators for generic card actions."""

from __future__ import annotations

from collections.abc import Callable

from engine.errors import (
    MissingRuleImplementationError,
    RuleViolationError,
)
from engine.generic_runtime._promotion_helpers import (
    _legal_recruit_card_for_action,
    _promote_from_discard,
    _promote_from_multiple_zones,
    _promote_required_aspect,
    _promote_requires_other_card,
)
from engine.generic_runtime._utils import (
    _generic_choice_move,
)
from engine.helpers import (
    WHITE_TROOP_OWNER,
    _action_targets_anywhere,
    _can_deploy_to_node,
    has_presence,
)
from engine.moves import Move
from engine.state import (
    CardAction,
    CardDefinition,
    GameState,
    NodeKind,
    PendingGenericChoiceState,
    board_index,
    card_index,
)


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
    if effect_kind == "select_site":
        board_idx = board_index(state.definition.board)
        for node_id in sorted(state.board.nodes):
            node_def = board_idx.get(node_id)
            if node_def is None or node_def.kind != NodeKind.SITE:
                continue
            if not has_presence(state, player_id, node_id):
                continue
            moves.append(
                _generic_choice_move(
                    player_id,
                    pending,
                    selection={"target_node_id": node_id},
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
    sf = action.source_fragment.strip().lower()
    if sf == "targeted_discard":
        moves = []
        for target_player_id, target_player in state.players.items():
            if target_player_id == player_id:
                continue
            if len(target_player.hand) < 3:
                continue
            moves.append(
                _generic_choice_move(
                    player_id,
                    pending,
                    selection={"target_player_id": target_player_id},
                )
            )
        return moves

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
