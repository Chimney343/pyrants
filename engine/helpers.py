"""Shared helper functions used by both rules.py and generic_runtime.py.

Extracted from rules.py to eliminate the lazy ``_get_rules()`` circular
import in generic_runtime.py. Contains constants, board queries, counting
helpers, effect wrappers, free actions, and the effect registry.
"""

from __future__ import annotations

from collections.abc import Callable

from engine.errors import (
    IllegalMoveError,
    MissingRuleImplementationError,
    RuleViolationError,
    UnknownCardEffectError,
)
from engine.moves import (
    HOUSE_GUARD_RECRUIT_SLOT,
    INSANE_OUTCAST_RECRUIT_SLOT,
    PRIESTESS_RECRUIT_SLOT,
    RecruitMove,
    ReturnSpyMove,
)
from engine.state import (
    CardAction,
    CardDefinition,
    GameState,
    NodeKind,
    PendingPromotionState,
    _cow_market_state,
    _cow_node,
    _cow_player,
    _cow_resource_pool,
    _shuffle_deck,
    board_index,
    card_index,
)

WHITE_TROOP_OWNER = "white"
ABERRATIONS_DECK_ID = "aberrations"

SPECIAL_RECRUIT_STACKS: tuple[tuple[int, str, int, bool], ...] = (
    (HOUSE_GUARD_RECRUIT_SLOT, "house_guard", 15, False),
    (PRIESTESS_RECRUIT_SLOT, "priestess_of_lolth", 15, False),
    (INSANE_OUTCAST_RECRUIT_SLOT, "insane_outcast", 30, True),
)

CardEffect = Callable[[GameState, str, CardDefinition], GameState]
_EFFECT_REGISTRY: dict[str, CardEffect] = {}


def register_effect(effect_key: str) -> Callable[[CardEffect], CardEffect]:
    def _decorator(effect: CardEffect) -> CardEffect:
        _EFFECT_REGISTRY[effect_key] = effect
        return effect

    return _decorator


# ── board helpers ──────────────────────────────────────────────────────────


def has_presence(state: GameState, player_id: str, node_id: str) -> bool:
    board_definitions = board_index(state.definition.board)
    if node_id not in board_definitions:
        raise RuleViolationError(f"Unknown node id: {node_id}")

    cache = state.__dict__.get("_presence_cache")
    if cache is None or player_id not in cache:
        present = set()
        node_states = state.board.nodes
        for nid, ns in node_states.items():
            if player_id in ns.spies or player_id in ns.troop_slots:
                present.add(nid)
            else:
                for adj_id in board_definitions[nid].adjacent_to:
                    adj_ns = node_states[adj_id]
                    if player_id in adj_ns.troop_slots:
                        present.add(nid)
                        break
        if cache is None:
            cache = {}
        cache[player_id] = present
        state.__dict__["_presence_cache"] = cache

    return node_id in cache[player_id]


def _action_targets_anywhere(action: CardAction) -> bool:
    metadata_flag = bool(action.metadata.get("ignore_presence_requirement", False))
    targeting = str(action.metadata.get("targeting", "")).strip().lower()
    source_fragment = action.source_fragment.strip().lower()
    return metadata_flag or targeting == "anywhere" or "anywhere" in source_fragment or "unrestricted" in source_fragment


def _player_has_any_troops_on_board(state: GameState, player_id: str) -> bool:
    return any(player_id in node_state.troop_slots for node_state in state.board.nodes.values())


def _can_deploy_to_node(
    state: GameState,
    player_id: str,
    node_id: str,
    has_troops_on_board: bool | None = None,
) -> bool:
    if node_id not in state.board.nodes:
        return False

    node_state = state.board.nodes[node_id]
    if None not in node_state.troop_slots:
        return False

    if has_troops_on_board is None:
        has_troops_on_board = _player_has_any_troops_on_board(state, player_id)
    if not has_troops_on_board:
        return True

    return has_presence(state, player_id, node_id)


def _legal_initial_placement_node_ids(state: GameState) -> list[str]:
    """Return sorted site node ids with at least one empty troop slot."""
    board_defs = board_index(state.definition.board)
    result: list[str] = []
    for node_id, node_def in board_defs.items():
        if node_def.kind != NodeKind.SITE:
            continue
        node_state = state.board.nodes.get(node_id)
        if node_state is None:
            continue
        if None in node_state.troop_slots:
            result.append(node_id)
    return sorted(result)


# ── counting helpers ───────────────────────────────────────────────────────


def _count_controlled_sites(state: GameState, player_id: str) -> int:
    board_definitions = board_index(state.definition.board)
    total = 0
    for node_id, node_definition in board_definitions.items():
        if node_definition.kind != NodeKind.SITE:
            continue
        node_state = state.board.nodes[node_id]
        counts: dict[str, int] = {}
        for occupant in node_state.troop_slots:
            if occupant is not None:
                counts[occupant] = counts.get(occupant, 0) + 1
        if not counts:
            continue
        max_count = max(counts.values())
        leaders = [owner for owner, count in counts.items() if count == max_count]
        if len(leaders) == 1 and leaders[0] != "white" and leaders[0] == player_id:
            total += 1
    return total


def _count_controlled_sites_by_troops(state: GameState, player_id: str) -> int:
    board_definitions = board_index(state.definition.board)
    total = 0
    for node_id, node_definition in board_definitions.items():
        if node_definition.kind != NodeKind.SITE:
            continue
        node_state = state.board.nodes[node_id]
        counts: dict[str, int] = {}
        for occupant in node_state.troop_slots:
            if occupant is not None:
                counts[occupant] = counts.get(occupant, 0) + 1
        if not counts:
            continue
        max_count = max(counts.values())
        leaders = [owner for owner, count in counts.items() if count == max_count]
        if len(leaders) == 1 and leaders[0] != "white" and leaders[0] == player_id:
            total += 1
    return total


def _count_runtime_cards_by_aspect(
    state: GameState,
    card_ids: list[str],
    *,
    required_aspect: str | None = None,
    required_secondary_aspect: str | None = None,
) -> int:
    cards_by_id = card_index(state.definition.catalog)
    normalized_aspect = required_aspect.strip().lower() if required_aspect else None
    normalized_secondary = required_secondary_aspect.strip().lower() if required_secondary_aspect else None

    total = 0
    for candidate_id in card_ids:
        definition = cards_by_id.get(candidate_id)
        if definition is None:
            continue
        if normalized_aspect is not None and definition.aspect != normalized_aspect:
            continue
        if normalized_secondary is not None and normalized_secondary not in definition.secondary_aspects:
            continue
        total += 1
    return total


def _is_aberrations_enabled(state: GameState) -> bool:
    setup_id = state.definition.setup.setup_id
    market_deck_id = state.definition.setup.market_deck.deck_id
    return ABERRATIONS_DECK_ID in setup_id or ABERRATIONS_DECK_ID in market_deck_id


def _special_stack_config(market_slot: int) -> tuple[str, int, bool] | None:
    for slot, card_id, stack_total, requires_aberrations in SPECIAL_RECRUIT_STACKS:
        if slot == market_slot:
            return card_id, stack_total, requires_aberrations
    return None


def _remaining_special_stack_count(state: GameState, card_id: str, stack_total: int) -> int:
    available = state.market.deck.count(card_id) + state.market.row.count(card_id)
    if available > 0:
        return available

    owned_total = 0
    for player in state.players.values():
        owned_total += (
            player.deck.count(card_id)
            + player.hand.count(card_id)
            + player.discard_pile.count(card_id)
            + player.played_cards.count(card_id)
            + player.inner_circle.count(card_id)
            + player.trophy_hall.count(card_id)
        )

    return max(0, stack_total - owned_total)


# ── scaled VP ──────────────────────────────────────────────────────────────


def _scaled_vp_award_count(state: GameState, player_id: str, action: CardAction) -> int:
    metadata = action.metadata
    source_fragment = action.source_fragment.strip().lower()
    count_from = str(metadata.get("count_from", "")).strip().lower()

    if not count_from:
        if source_fragment == "scaled_vp_from_white_trophies":
            count_from = "trophy_hall_white"
        elif source_fragment == "scaled_vp_from_trophies":
            count_from = "trophy_hall_non_white"
        elif source_fragment == "scaled_vp_from_controlled_sites":
            count_from = "controlled_sites"
        elif source_fragment in {"scaled_vp", "scaled_vp_from_promoted_cards"}:
            count_from = "inner_circle_cards"

    per_raw = metadata.get("per")
    if per_raw is None:
        if source_fragment == "scaled_vp_from_white_trophies":
            per_raw = 3
        elif source_fragment == "scaled_vp_from_trophies":
            per_raw = 5
        elif source_fragment == "scaled_vp_from_controlled_sites":
            per_raw = 2
        elif source_fragment in {"scaled_vp", "scaled_vp_from_promoted_cards"}:
            per_raw = 3
        else:
            per_raw = 1

    try:
        per = int(per_raw)
    except (TypeError, ValueError) as error:
        raise RuleViolationError("grant_vp per metadata must be an integer") from error
    if per <= 0:
        raise RuleViolationError("grant_vp per metadata must be positive")

    player = state.players[player_id]
    if count_from == "trophy_hall_white":
        base_count = sum(1 for trophy in player.trophy_hall if trophy == WHITE_TROOP_OWNER)
    elif count_from == "trophy_hall_non_white":
        base_count = sum(1 for trophy in player.trophy_hall if trophy != WHITE_TROOP_OWNER)
    elif count_from == "trophy_hall_all":
        base_count = len(player.trophy_hall)
    elif count_from == "inner_circle_cards":
        required_aspect = str(metadata.get("required_aspect", "")).strip().lower() or None
        required_secondary_aspect = str(metadata.get("required_secondary_aspect", "")).strip().lower() or None
        base_count = _count_runtime_cards_by_aspect(
            state,
            player.inner_circle,
            required_aspect=required_aspect,
            required_secondary_aspect=required_secondary_aspect,
        )
    elif count_from == "owned_control_markers":
        base_count = _count_controlled_sites_by_troops(state, player_id)
    elif count_from == "controlled_sites":
        base_count = _count_controlled_sites(state, player_id)
    else:
        raise MissingRuleImplementationError(
            f"Unrecognized scaled VP count_from '{count_from}' for action '{action.action_id}'"
        )

    return base_count // per


# ── focus helpers ──────────────────────────────────────────────────────────


def _focus_requirement_met(state: GameState, player_id: str, card: CardDefinition, source_card_id: str) -> bool:
    payload_aspect = card.effect_payload.get("focus_aspect", card.aspect)
    required_aspect = str(payload_aspect).strip().lower()
    return _focus_requirement_met_for_aspect(state, player_id, required_aspect, source_card_id)


def _focus_requirement_met_for_aspect(
    state: GameState,
    player_id: str,
    required_aspect: str,
    source_card_id: str,
) -> bool:
    player = state.players[player_id]

    candidate_card_ids = [*player.hand, *player.played_cards]
    try:
        candidate_card_ids.remove(source_card_id)
    except ValueError:
        pass

    catalog_index = card_index(state.definition.catalog)
    for candidate_card_id in candidate_card_ids:
        candidate = catalog_index.get(candidate_card_id)
        if candidate is not None and candidate.aspect == required_aspect:
            return True

    return False


# ── effect wrappers ────────────────────────────────────────────────────────


def _apply_effect_with_wrappers(
    state: GameState,
    player_id: str,
    card: CardDefinition,
    *,
    source_card_id: str,
) -> GameState:
    updated = state._cow_clone()
    payload = card.effect_payload

    if bool(payload.get("focus_required", False)) and not _focus_requirement_met(updated, player_id, card, source_card_id):
        effect_applied = updated
    else:
        effect = _EFFECT_REGISTRY.get(card.effect_key)
        if effect is None:
            raise UnknownCardEffectError(
                f"Card '{card.card_id}' references unregistered effect '{card.effect_key}'"
            )
        effect_applied = effect(updated, player_id, card)

    if effect_applied.pending_generic_choice is not None:
        return effect_applied

    return _apply_promote_instruction(effect_applied, player_id, source_card_id, payload.get("promote"))


# ── promotion system ───────────────────────────────────────────────────────


def _promote_card(state: GameState, player_id: str, card_id: str) -> None:
    player = _cow_player(state, player_id)
    try:
        played_index = player.played_cards.index(card_id)
    except ValueError as error:
        raise IllegalMoveError("cannot promote a card that is no longer played") from error

    promoted_card = player.played_cards.pop(played_index)
    player.inner_circle.append(promoted_card)


def _apply_promote_instruction(
    state: GameState,
    player_id: str,
    card_id: str,
    promote_payload: object,
) -> GameState:
    if promote_payload is None:
        return state
    if not isinstance(promote_payload, dict):
        raise RuleViolationError("promote payload must be an object")

    timing = str(promote_payload.get("timing", "")).strip()
    optional = bool(promote_payload.get("optional", False))
    if timing not in {"immediate", "end_of_turn"}:
        raise RuleViolationError("promote timing must be 'immediate' or 'end_of_turn'")

    updated = state._cow_clone()
    pending = PendingPromotionState(
        card_id=card_id,
        timing=timing,
        optional=optional,
        source_card_id=card_id,
    )
    if timing == "immediate":
        if optional:
            updated.pending_immediate_promotions.append(pending)
            return updated
        _promote_card(updated, player_id, card_id)
        return updated

    updated.pending_end_of_turn_promotions.append(pending)
    return updated


# ── resource utilities ─────────────────────────────────────────────────────


def _grant_resource(state: GameState, resource: str, amount: int) -> GameState:
    updated = state._cow_clone()
    pool = _cow_resource_pool(updated)
    if resource == "power":
        pool.power += amount
    elif resource == "influence":
        pool.influence += amount
    else:
        raise RuleViolationError(f"Unknown resource '{resource}'")
    return updated


# ── free actions (no resource cost) ────────────────────────────────────────


def _apply_free_assassinate(state: GameState, player_id: str, target_node_id: str, target_slot_index: int) -> GameState:
    if target_node_id not in state.board.nodes:
        raise IllegalMoveError(f"Unknown node id: {target_node_id}")
    if not has_presence(state, player_id, target_node_id):
        raise IllegalMoveError("assassinate requires presence at the target node")

    updated = state._cow_clone()
    node_state = _cow_node(updated, target_node_id)
    if target_slot_index < 0 or target_slot_index >= len(node_state.troop_slots):
        raise IllegalMoveError("target_slot_index is out of range")

    occupant = node_state.troop_slots[target_slot_index]
    if occupant is None:
        raise IllegalMoveError("target slot is empty")
    if occupant == player_id:
        raise IllegalMoveError("cannot assassinate your own troop")

    node_state.troop_slots[target_slot_index] = None
    _cow_player(updated, player_id).trophy_hall.append(occupant)
    return updated


def _apply_free_deploy(state: GameState, player_id: str, target_node_id: str) -> GameState:
    if target_node_id not in state.board.nodes:
        raise IllegalMoveError(f"Unknown node id: {target_node_id}")
    if not _can_deploy_to_node(state, player_id, target_node_id):
        raise IllegalMoveError("deploy target must have an empty slot and satisfy presence rules")

    updated = state._cow_clone()
    player = _cow_player(updated, player_id)
    if player.barracks == 0:
        player.score += 1
        return updated

    node_state = _cow_node(updated, target_node_id)
    for slot_index, occupant in enumerate(node_state.troop_slots):
        if occupant is None:
            node_state.troop_slots[slot_index] = player_id
            player.barracks -= 1
            return updated

    raise IllegalMoveError("deploy target has no empty troop slot")


def _apply_return_spy(state: GameState, move: ReturnSpyMove) -> GameState:
    if move.node_id not in state.board.nodes:
        raise IllegalMoveError(f"Unknown node id: {move.node_id}")
    if move.spy_owner_id not in state.players:
        raise IllegalMoveError(f"Unknown spy owner id: {move.spy_owner_id}")
    if board_index(state.definition.board)[move.node_id].kind == NodeKind.ROUTE:
        raise IllegalMoveError("routes cannot hold spies")

    updated = state._cow_clone()
    node_state = _cow_node(updated, move.node_id)
    if move.spy_owner_id not in node_state.spies:
        raise IllegalMoveError("target spy is not present at the chosen node")

    if move.spy_owner_id != move.player_id:
        pool = _cow_resource_pool(updated)
        if pool.power < 3:
            raise IllegalMoveError("returning an enemy spy requires 3 power")
        if not has_presence(updated, move.player_id, move.node_id):
            raise IllegalMoveError("returning an enemy spy requires presence at the node")
        pool.power -= 3

    node_state.spies.remove(move.spy_owner_id)
    _cow_player(updated, move.spy_owner_id).spies_available += 1
    return updated


def _apply_recruit(state: GameState, move: RecruitMove) -> GameState:
    special_stack = _special_stack_config(move.market_slot)
    if special_stack is not None:
        card_id, stack_total, requires_aberrations = special_stack
        if requires_aberrations and not _is_aberrations_enabled(state):
            raise IllegalMoveError("special recruit stack is not enabled")
        if _remaining_special_stack_count(state, card_id, stack_total) <= 0:
            raise IllegalMoveError("special recruit stack is empty")

        updated = state._cow_clone()
        definition = card_index(updated.definition.catalog).get(card_id)
        if definition is None:
            raise IllegalMoveError(f"Unknown special stack card id: {card_id}")
        pool = _cow_resource_pool(updated)
        if pool.influence < definition.cost:
            raise IllegalMoveError("recruit requires enough influence to pay the card cost")

        pool.influence -= definition.cost
        _cow_player(updated, move.player_id).discard_pile.append(card_id)
        return updated

    if move.market_slot >= len(state.market.row):
        raise IllegalMoveError("market_slot is out of range")

    updated = state._cow_clone()
    market = _cow_market_state(updated)
    card_id = market.row[move.market_slot]
    definition = card_index(updated.definition.catalog).get(card_id)
    if definition is None:
        raise IllegalMoveError(f"Unknown market card id: {card_id}")
    pool = _cow_resource_pool(updated)
    if pool.influence < definition.cost:
        raise IllegalMoveError("recruit requires enough influence to pay the card cost")

    pool.influence -= definition.cost
    _cow_player(updated, move.player_id).discard_pile.append(card_id)

    if market.deck:
        market.row[move.market_slot] = market.deck.pop()
    else:
        market.row.pop(move.market_slot)

    return updated


def _reshuffle_discard_into_deck(state: GameState, player_id: str) -> None:
    player = _cow_player(state, player_id)
    player.deck = _shuffle_deck(player.discard_pile, state.shuffle_seed, state.shuffle_count)
    state.shuffle_count += 1
    player.discard_pile = []


# ── paid ability checks ────────────────────────────────────────────────────


def _ability_cost_affordable(state: GameState, player_id: str, paid_ability: dict[str, object]) -> bool:
    player = state.players[player_id]
    cost = paid_ability.get("cost", {})
    if cost is None:
        return True
    if not isinstance(cost, dict):
        raise RuleViolationError("paid ability cost must be an object")

    power_cost = int(cost.get("power", 0))
    influence_cost = int(cost.get("influence", 0))
    discard_count = int(cost.get("discard_count", 0))
    return (
        state.resource_pool.power >= power_cost
        and state.resource_pool.influence >= influence_cost
        and len(player.hand) >= discard_count
    )


def _pay_ability_cost(
    state: GameState,
    player_id: str,
    paid_ability: dict[str, object],
    discard_hand_indices: list[int],
) -> None:
    if not _ability_cost_affordable(state, player_id, paid_ability):
        raise IllegalMoveError("player cannot currently pay this ability cost")

    cost = paid_ability.get("cost", {})
    if not isinstance(cost, dict):
        raise RuleViolationError("paid ability cost must be an object")

    discard_count = int(cost.get("discard_count", 0))
    if len(discard_hand_indices) != discard_count:
        raise IllegalMoveError("discard_hand_indices must satisfy the ability discard cost exactly")

    player = _cow_player(state, player_id)
    unique_indices = sorted(set(discard_hand_indices), reverse=True)
    if len(unique_indices) != discard_count:
        raise IllegalMoveError("discard_hand_indices must be unique")
    if any(index < 0 or index >= len(player.hand) for index in unique_indices):
        raise IllegalMoveError("discard_hand_indices contains an out-of-range value")

    pool = _cow_resource_pool(state)
    pool.power -= int(cost.get("power", 0))
    pool.influence -= int(cost.get("influence", 0))
    for hand_index in unique_indices:
        player.discard_pile.append(player.hand.pop(hand_index))


def _can_activate_pending_ability(state: GameState, player_id: str, card_id: str, ability_key: str) -> bool:
    if state.pending_ability is None:
        return False
    if state.pending_ability.card_id != card_id or state.pending_ability.ability_key != ability_key:
        return False

    definition = card_index(state.definition.catalog).get(card_id)
    if definition is None:
        return False
    paid_ability = definition.effect_payload.get("paid_ability")
    if not isinstance(paid_ability, dict):
        return False
    if card_id not in state.players[player_id].played_cards:
        return False

    return _ability_cost_affordable(state, player_id, paid_ability)


# ── deferred promotion helpers ─────────────────────────────────────────────


def _deferred_promotion_target_ids(
    state: GameState,
    player_id: str,
    pending: PendingPromotionState,
) -> list[str]:
    player = state.players[player_id]
    cards_by_id = card_index(state.definition.catalog)

    target_ids: list[str] = []
    for candidate_id in player.played_cards:
        if (
            pending.requires_another_played_card
            and pending.source_card_id is not None
            and candidate_id == pending.source_card_id
        ):
            continue

        if pending.required_aspect is not None:
            definition = cards_by_id.get(candidate_id)
            if definition is None or definition.aspect != pending.required_aspect:
                continue

        if pending.required_secondary_aspect is not None:
            definition = cards_by_id.get(candidate_id)
            if definition is None or pending.required_secondary_aspect not in definition.secondary_aspects:
                continue

        target_ids.append(candidate_id)

    return target_ids
