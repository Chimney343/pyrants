"""Rule evaluation and pure state transition functions."""

from __future__ import annotations

from random import Random
from typing import Callable

from engine.errors import (
    IllegalMoveError,
    MissingRuleImplementationError,
    RuleViolationError,
    UnknownCardEffectError,
)
from engine.moves import (
    ActivateCardAbilityMove,
    AssassinateMove,
    DeclineCardAbilityMove,
    DeployMove,
    EndMainPhaseMove,
    Move,
    PlayCardMove,
    PromoteCardMove,
    RecruitMove,
    ResolveCleanupMove,
    ResolveGenericChoiceMove,
    ResolveEndOfTurnMove,
    ReturnSpyMove,
    SkipPromoteMove,
    HOUSE_GUARD_RECRUIT_SLOT,
    INSANE_OUTCAST_RECRUIT_SLOT,
    PRIESTESS_RECRUIT_SLOT,
)
from engine.phases import advance_phase
from engine.scoring import award_end_of_turn_site_vp, compute_final_scores
from engine.state import (
    CardAction,
    CardDefinition,
    GameState,
    ModalChoiceExecutionModel,
    NodeKind,
    PendingAbilityState,
    PendingGenericChoiceState,
    PendingPromotionState,
    RepeatChoiceExecutionModel,
    SequenceExecutionModel,
    TurnPhase,
    board_index,
    card_index,
)

CardEffect = Callable[[GameState, str, CardDefinition], GameState]
_EFFECT_REGISTRY: dict[str, CardEffect] = {}
WHITE_TROOP_OWNER = "white"
ABERRATIONS_DECK_ID = "aberrations"

SPECIAL_RECRUIT_STACKS: tuple[tuple[int, str, int, bool], ...] = (
    (HOUSE_GUARD_RECRUIT_SLOT, "house_guard", 15, False),
    (PRIESTESS_RECRUIT_SLOT, "priestess_of_lolth", 15, False),
    (INSANE_OUTCAST_RECRUIT_SLOT, "insane_outcast", 30, True),
)


def _action_targets_anywhere(action: CardAction) -> bool:
    metadata_flag = bool(action.metadata.get("ignore_presence_requirement", False))
    targeting = str(action.metadata.get("targeting", "")).strip().lower()
    source_fragment = action.source_fragment.strip().lower()
    return metadata_flag or targeting == "anywhere" or "anywhere" in source_fragment or "unrestricted" in source_fragment


def _count_controlled_sites(state: GameState, player_id: str) -> int:
    board_definitions = board_index(state.definition.board)
    return sum(
        1
        for node_id, node_definition in board_definitions.items()
        if node_definition.kind == NodeKind.SITE and has_presence(state, player_id, node_id)
    )


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
        return 0

    return base_count // per


def register_effect(effect_key: str) -> Callable[[CardEffect], CardEffect]:
    """Register a card effect handler by effect key."""

    def _decorator(effect: CardEffect) -> CardEffect:
        _EFFECT_REGISTRY[effect_key] = effect
        return effect

    return _decorator


def _is_aberrations_enabled(state: GameState) -> bool:
    setup_id = state.definition.setup.setup_id
    market_deck_id = state.definition.setup.market_deck.deck_id
    return ABERRATIONS_DECK_ID in setup_id or ABERRATIONS_DECK_ID in market_deck_id


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


def _special_stack_config(market_slot: int) -> tuple[str, int, bool] | None:
    for slot, card_id, stack_total, requires_aberrations in SPECIAL_RECRUIT_STACKS:
        if slot == market_slot:
            return card_id, stack_total, requires_aberrations
    return None


def has_presence(state: GameState, player_id: str, node_id: str) -> bool:
    """Check presence at a node, including troop adjacency for neighboring nodes."""

    board_definitions = board_index(state.definition.board)
    if node_id not in board_definitions:
        raise RuleViolationError(f"Unknown node id: {node_id}")

    node_state = state.board.nodes[node_id]
    if player_id in node_state.spies or any(slot == player_id for slot in node_state.troop_slots):
        return True

    for adjacent_id in board_definitions[node_id].adjacent_to:
        adjacent_state = state.board.nodes[adjacent_id]
        if any(slot == player_id for slot in adjacent_state.troop_slots):
            return True

    return False


def legal_moves(state: GameState) -> list[Move]:
    """Return legal moves for the active player in the current phase."""

    if state.phase == TurnPhase.GAME_OVER:
        return []

    player_id = state.current_player_id
    player = state.players[player_id]

    if state.phase == TurnPhase.MAIN:
        if state.pending_immediate_promotions:
            return _legal_optional_promotion_moves(state, player_id, state.pending_immediate_promotions[0])
        if state.pending_generic_choice is not None:
            return _legal_pending_generic_choice_moves(state, player_id)

        moves: list[Move] = [
            *_legal_pending_ability_moves(state, player_id),
        ]
        if state.pending_ability is None:
            moves.extend(
                PlayCardMove(player_id=player_id, card_id=card_id, hand_index=index)
                for index, card_id in enumerate(player.hand)
            )
        moves.extend(_legal_main_phase_actions(state, player_id))
        moves.append(EndMainPhaseMove(player_id=player_id))
        return moves

    if state.phase == TurnPhase.END_OF_TURN:
        if state.pending_end_of_turn_promotions:
            pending = state.pending_end_of_turn_promotions[0]
            if pending.deferred_choice:
                return _legal_deferred_end_of_turn_promotion_moves(state, player_id, pending)
            if pending.optional:
                return _legal_optional_promotion_moves(state, player_id, pending)
        return [ResolveEndOfTurnMove(player_id=player_id)]

    if state.phase == TurnPhase.CLEANUP:
        return [ResolveCleanupMove(player_id=player_id)]

    return []


def apply(state: GameState, move: Move) -> GameState:
    """Apply one move and return a new state without mutating the input state."""

    if move.player_id != state.current_player_id:
        raise IllegalMoveError("Only the active player can make a move")

    if isinstance(move, PlayCardMove):
        return _apply_play_card(state, move)

    if isinstance(move, EndMainPhaseMove):
        if state.phase != TurnPhase.MAIN:
            raise IllegalMoveError("end_main_phase can only be used during the main phase")
        return _enter_end_of_turn(state)

    if isinstance(move, ResolveEndOfTurnMove):
        if state.phase != TurnPhase.END_OF_TURN:
            raise IllegalMoveError("resolve_end_of_turn can only be used during end_of_turn")
        if state.pending_end_of_turn_promotions:
            raise IllegalMoveError("resolve end of turn requires all pending promotions to be resolved first")
        updated = state.model_copy(deep=True)
        _apply_end_of_turn_generic_effects(updated, include_force_discard=False, include_scaled_vp=True)
        scored = award_end_of_turn_site_vp(updated, player_id=updated.current_player_id)
        return advance_phase(scored)

    if isinstance(move, ResolveCleanupMove):
        if state.phase != TurnPhase.CLEANUP:
            raise IllegalMoveError("resolve_cleanup can only be used during cleanup")
        return _apply_cleanup(state)

    if isinstance(move, ResolveGenericChoiceMove):
        return _apply_resolve_generic_choice(state, move)

    if isinstance(move, AssassinateMove):
        return _apply_assassinate(state, move)

    if isinstance(move, DeployMove):
        return _apply_deploy(state, move)

    if isinstance(move, RecruitMove):
        return _apply_recruit(state, move)

    if isinstance(move, ReturnSpyMove):
        raise IllegalMoveError("return_spy can only be resolved through a card effect")

    if isinstance(move, ActivateCardAbilityMove):
        return _apply_activate_card_ability(state, move)

    if isinstance(move, DeclineCardAbilityMove):
        return _apply_decline_card_ability(state, move)

    if isinstance(move, PromoteCardMove):
        return _apply_promote_card(state, move)

    if isinstance(move, SkipPromoteMove):
        return _apply_skip_promote(state, move)

    raise IllegalMoveError(f"Unsupported move type: {move}")


def is_terminal(state: GameState) -> bool:
    """Check terminal conditions from current source rules."""

    if state.phase == TurnPhase.GAME_OVER:
        return True

    if not state.market.deck:
        return True

    return any(player_state.barracks == 0 for player_state in state.players.values())


def winner(state: GameState) -> str | None:
    """Return winner id when terminal state has a unique high score."""

    if not is_terminal(state):
        return None

    totals = state.final_scores or compute_final_scores(state)
    if not totals:
        return None

    max_score = max(totals.values())
    leaders = [player_id for player_id, score in totals.items() if score == max_score]
    if len(leaders) == 1:
        return leaders[0]

    return None


def _apply_play_card(state: GameState, move: PlayCardMove) -> GameState:
    if state.phase != TurnPhase.MAIN:
        raise IllegalMoveError("play_card can only be used during the main phase")
    if state.pending_immediate_promotions:
        raise IllegalMoveError("resolve pending promotions before playing another card")
    if state.pending_ability is not None:
        raise IllegalMoveError("resolve or decline the pending ability before playing another card")
    if state.pending_generic_choice is not None:
        raise IllegalMoveError("resolve the pending generic card choices before playing another card")

    updated = state.model_copy(deep=True)
    player = updated.players[updated.current_player_id]

    hand_index = move.hand_index
    if hand_index is None:
        try:
            hand_index = player.hand.index(move.card_id)
        except ValueError as error:
            raise IllegalMoveError(f"Card '{move.card_id}' is not in hand") from error

    if hand_index >= len(player.hand):
        raise IllegalMoveError("hand_index is out of range")

    played_card_id = player.hand.pop(hand_index)
    if played_card_id != move.card_id:
        raise IllegalMoveError("Card id does not match card at hand_index")

    player.played_cards.append(played_card_id)

    definition = card_index(updated.definition.catalog).get(played_card_id)
    if definition is None:
        raise IllegalMoveError(f"Unknown card id in player's hand: {played_card_id}")

    effect = _EFFECT_REGISTRY.get(definition.effect_key)
    if effect is None:
        raise UnknownCardEffectError(
            f"Card '{played_card_id}' references unregistered effect '{definition.effect_key}'"
        )

    updated = _apply_effect_with_wrappers(updated, updated.current_player_id, definition, source_card_id=played_card_id)

    paid_ability = definition.effect_payload.get("paid_ability")
    if paid_ability is None:
        return updated
    if not isinstance(paid_ability, dict):
        raise RuleViolationError("paid_ability payload must be an object")
    if played_card_id not in updated.players[updated.current_player_id].played_cards:
        raise MissingRuleImplementationError(
            "Cards with unresolved paid abilities cannot also leave the played area before the ability choice"
        )

    ability_key = str(paid_ability.get("ability_key", paid_ability.get("effect_key", ""))).strip()
    if not ability_key:
        raise RuleViolationError("paid_ability must define ability_key or effect_key")
    updated.pending_ability = PendingAbilityState(card_id=played_card_id, ability_key=ability_key)
    return updated


def _legal_pending_ability_moves(state: GameState, player_id: str) -> list[Move]:
    if state.pending_ability is None:
        return []

    pending = state.pending_ability
    moves: list[Move] = [
        DeclineCardAbilityMove(
            player_id=player_id,
            card_id=pending.card_id,
            ability_key=pending.ability_key,
        )
    ]

    if _can_activate_pending_ability(state, player_id, pending.card_id, pending.ability_key):
        moves.append(
            ActivateCardAbilityMove(
                player_id=player_id,
                card_id=pending.card_id,
                ability_key=pending.ability_key,
            )
        )

    return moves


def _legal_optional_promotion_moves(
    state: GameState,
    player_id: str,
    pending: PendingPromotionState,
) -> list[Move]:
    return [
        PromoteCardMove(player_id=player_id, card_id=pending.card_id),
        SkipPromoteMove(player_id=player_id, card_id=pending.card_id),
    ]


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


def _legal_deferred_end_of_turn_promotion_moves(
    state: GameState,
    player_id: str,
    pending: PendingPromotionState,
) -> list[Move]:
    target_ids = _deferred_promotion_target_ids(state, player_id, pending)
    if target_ids:
        moves = [PromoteCardMove(player_id=player_id, card_id=card_id) for card_id in target_ids]
        if pending.optional:
            moves.append(SkipPromoteMove(player_id=player_id, card_id=pending.card_id))
        return moves

    return [SkipPromoteMove(player_id=player_id, card_id=pending.card_id)]


def _legal_main_phase_actions(state: GameState, player_id: str) -> list[Move]:
    moves: list[Move] = []
    cards_by_id = card_index(state.definition.catalog)
    board_definitions = board_index(state.definition.board)

    if state.resource_pool.power >= 1:
        for node_id in state.board.nodes:
            if _can_deploy_to_node(state, player_id, node_id):
                moves.append(DeployMove(player_id=player_id, target_node_id=node_id, troop_count=1))

    if state.resource_pool.power >= 3:
        for node_id, node_state in state.board.nodes.items():
            if not has_presence(state, player_id, node_id):
                continue

            for slot_index, occupant in enumerate(node_state.troop_slots):
                if occupant is None or occupant == player_id:
                    continue
                moves.append(
                    AssassinateMove(
                        player_id=player_id,
                        target_node_id=node_id,
                        target_slot_index=slot_index,
                    )
                )

    for market_slot, card_id in enumerate(state.market.row):
        definition = cards_by_id.get(card_id)
        if definition is None:
            continue
        if state.resource_pool.influence >= definition.cost:
            moves.append(RecruitMove(player_id=player_id, market_slot=market_slot))

    for market_slot, card_id, stack_total, requires_aberrations in SPECIAL_RECRUIT_STACKS:
        if requires_aberrations and not _is_aberrations_enabled(state):
            continue
        if _remaining_special_stack_count(state, card_id, stack_total) <= 0:
            continue

        definition = cards_by_id.get(card_id)
        if definition is None:
            continue
        if state.resource_pool.influence >= definition.cost:
            moves.append(RecruitMove(player_id=player_id, market_slot=market_slot))

    return moves


def _player_has_any_troops_on_board(state: GameState, player_id: str) -> bool:
    for node_state in state.board.nodes.values():
        if any(slot_owner == player_id for slot_owner in node_state.troop_slots):
            return True
    return False


def _can_deploy_to_node(state: GameState, player_id: str, node_id: str) -> bool:
    if node_id not in state.board.nodes:
        return False

    node_state = state.board.nodes[node_id]
    if not any(slot_owner is None for slot_owner in node_state.troop_slots):
        return False

    if not _player_has_any_troops_on_board(state, player_id):
        return True

    return has_presence(state, player_id, node_id)


def _apply_free_assassinate(state: GameState, player_id: str, target_node_id: str, target_slot_index: int) -> GameState:
    if target_node_id not in state.board.nodes:
        raise IllegalMoveError(f"Unknown node id: {target_node_id}")
    if not has_presence(state, player_id, target_node_id):
        raise IllegalMoveError("assassinate requires presence at the target node")

    updated = state.model_copy(deep=True)
    node_state = updated.board.nodes[target_node_id]
    if target_slot_index < 0 or target_slot_index >= len(node_state.troop_slots):
        raise IllegalMoveError("target_slot_index is out of range")

    occupant = node_state.troop_slots[target_slot_index]
    if occupant is None:
        raise IllegalMoveError("target slot is empty")
    if occupant == player_id:
        raise IllegalMoveError("cannot assassinate your own troop")

    node_state.troop_slots[target_slot_index] = None
    updated.players[player_id].trophy_hall.append(occupant)
    return updated


def _apply_free_deploy(state: GameState, player_id: str, target_node_id: str) -> GameState:
    if target_node_id not in state.board.nodes:
        raise IllegalMoveError(f"Unknown node id: {target_node_id}")
    if not _can_deploy_to_node(state, player_id, target_node_id):
        raise IllegalMoveError("deploy target must have an empty slot and satisfy presence rules")

    updated = state.model_copy(deep=True)
    player = updated.players[player_id]
    if player.barracks == 0:
        player.score += 1
        return updated

    node_state = updated.board.nodes[target_node_id]
    for slot_index, occupant in enumerate(node_state.troop_slots):
        if occupant is None:
            node_state.troop_slots[slot_index] = player_id
            player.barracks -= 1
            return updated

    raise IllegalMoveError("deploy target has no empty troop slot")


def _apply_assassinate(state: GameState, move: AssassinateMove) -> GameState:
    if state.phase != TurnPhase.MAIN:
        raise IllegalMoveError("assassinate can only be used during the main phase")

    if move.target_node_id not in state.board.nodes:
        raise IllegalMoveError(f"Unknown node id: {move.target_node_id}")

    updated = state.model_copy(deep=True)
    if updated.resource_pool.power < 3:
        raise IllegalMoveError("assassinate requires 3 power")

    if not has_presence(updated, move.player_id, move.target_node_id):
        raise IllegalMoveError("assassinate requires presence at the target node")

    node_state = updated.board.nodes[move.target_node_id]
    if move.target_slot_index >= len(node_state.troop_slots):
        raise IllegalMoveError("target_slot_index is out of range")

    occupant = node_state.troop_slots[move.target_slot_index]
    if occupant is None:
        raise IllegalMoveError("target slot is empty")
    if occupant == move.player_id:
        raise IllegalMoveError("cannot assassinate your own troop")

    updated.resource_pool.power -= 3
    node_state.troop_slots[move.target_slot_index] = None
    updated.players[move.player_id].trophy_hall.append(occupant)
    return updated


def _apply_deploy(state: GameState, move: DeployMove) -> GameState:
    if state.phase != TurnPhase.MAIN:
        raise IllegalMoveError("deploy can only be used during the main phase")

    if move.target_node_id not in state.board.nodes:
        raise IllegalMoveError(f"Unknown node id: {move.target_node_id}")
    if move.troop_count != 1:
        raise IllegalMoveError("deploy currently places exactly one troop per action")

    updated = state.model_copy(deep=True)
    if updated.resource_pool.power < 1:
        raise IllegalMoveError("deploy requires 1 power")
    if not _can_deploy_to_node(updated, move.player_id, move.target_node_id):
        raise IllegalMoveError("deploy target must have an empty slot and satisfy presence rules")

    updated.resource_pool.power -= 1
    player = updated.players[move.player_id]
    if player.barracks == 0:
        player.score += 1
        return updated

    node_state = updated.board.nodes[move.target_node_id]
    for slot_index, occupant in enumerate(node_state.troop_slots):
        if occupant is None:
            node_state.troop_slots[slot_index] = move.player_id
            player.barracks -= 1
            return updated

    raise IllegalMoveError("deploy target has no empty troop slot")


def _apply_recruit(state: GameState, move: RecruitMove) -> GameState:
    if state.phase != TurnPhase.MAIN:
        raise IllegalMoveError("recruit can only be used during the main phase")

    special_stack = _special_stack_config(move.market_slot)
    if special_stack is not None:
        card_id, stack_total, requires_aberrations = special_stack
        if requires_aberrations and not _is_aberrations_enabled(state):
            raise IllegalMoveError("special recruit stack is not enabled")
        if _remaining_special_stack_count(state, card_id, stack_total) <= 0:
            raise IllegalMoveError("special recruit stack is empty")

        updated = state.model_copy(deep=True)
        definition = card_index(updated.definition.catalog).get(card_id)
        if definition is None:
            raise IllegalMoveError(f"Unknown special stack card id: {card_id}")
        if updated.resource_pool.influence < definition.cost:
            raise IllegalMoveError("recruit requires enough influence to pay the card cost")

        updated.resource_pool.influence -= definition.cost
        updated.players[move.player_id].discard_pile.append(card_id)
        return updated

    if move.market_slot >= len(state.market.row):
        raise IllegalMoveError("market_slot is out of range")

    updated = state.model_copy(deep=True)
    card_id = updated.market.row[move.market_slot]
    definition = card_index(updated.definition.catalog).get(card_id)
    if definition is None:
        raise IllegalMoveError(f"Unknown market card id: {card_id}")
    if updated.resource_pool.influence < definition.cost:
        raise IllegalMoveError("recruit requires enough influence to pay the card cost")

    updated.resource_pool.influence -= definition.cost
    updated.players[move.player_id].discard_pile.append(card_id)

    if updated.market.deck:
        updated.market.row[move.market_slot] = updated.market.deck.pop()
    else:
        updated.market.row.pop(move.market_slot)

    return updated


def _apply_return_spy(state: GameState, move: ReturnSpyMove) -> GameState:
    if state.phase != TurnPhase.MAIN:
        raise IllegalMoveError("return_spy can only be used during the main phase")

    if move.node_id not in state.board.nodes:
        raise IllegalMoveError(f"Unknown node id: {move.node_id}")
    if move.spy_owner_id not in state.players:
        raise IllegalMoveError(f"Unknown spy owner id: {move.spy_owner_id}")
    if board_index(state.definition.board)[move.node_id].kind == NodeKind.ROUTE:
        raise IllegalMoveError("routes cannot hold spies")

    updated = state.model_copy(deep=True)
    node_state = updated.board.nodes[move.node_id]
    if move.spy_owner_id not in node_state.spies:
        raise IllegalMoveError("target spy is not present at the chosen node")

    if move.spy_owner_id != move.player_id:
        if updated.resource_pool.power < 3:
            raise IllegalMoveError("returning an enemy spy requires 3 power")
        if not has_presence(updated, move.player_id, move.node_id):
            raise IllegalMoveError("returning an enemy spy requires presence at the node")
        updated.resource_pool.power -= 3

    node_state.spies.remove(move.spy_owner_id)
    updated.players[move.spy_owner_id].spies_available += 1
    return updated


def _apply_activate_card_ability(state: GameState, move: ActivateCardAbilityMove) -> GameState:
    if state.phase != TurnPhase.MAIN:
        raise IllegalMoveError("activate_card_ability can only be used during the main phase")
    if state.pending_ability is None:
        raise IllegalMoveError("there is no pending ability to activate")

    pending = state.pending_ability
    if pending.card_id != move.card_id or pending.ability_key != move.ability_key:
        raise IllegalMoveError("requested ability does not match the pending ability")

    updated = state.model_copy(deep=True)
    definition = card_index(updated.definition.catalog).get(move.card_id)
    if definition is None:
        raise IllegalMoveError(f"Unknown card id: {move.card_id}")
    if move.card_id not in updated.players[move.player_id].played_cards:
        raise IllegalMoveError("cannot activate an ability on a card that is no longer played")

    paid_ability = definition.effect_payload.get("paid_ability")
    if not isinstance(paid_ability, dict):
        raise IllegalMoveError("card has no paid ability to activate")

    ability_key = str(paid_ability.get("ability_key", paid_ability.get("effect_key", ""))).strip()
    if ability_key != move.ability_key:
        raise IllegalMoveError("requested ability key does not match the card definition")

    _pay_ability_cost(updated, move.player_id, paid_ability, move.discard_hand_indices)

    effect_key = str(paid_ability.get("effect_key", ability_key)).strip()
    effect_payload = paid_ability.get("effect_payload", {})
    if not isinstance(effect_payload, dict):
        raise RuleViolationError("paid ability effect_payload must be an object")

    ability_card = definition.model_copy(
        update={
            "effect_key": effect_key,
            "effect_payload": {**effect_payload},
        }
    )
    updated.pending_ability = None
    return _apply_effect_with_wrappers(updated, move.player_id, ability_card, source_card_id=move.card_id)


def _apply_decline_card_ability(state: GameState, move: DeclineCardAbilityMove) -> GameState:
    if state.phase != TurnPhase.MAIN:
        raise IllegalMoveError("decline_card_ability can only be used during the main phase")
    if state.pending_ability is None:
        raise IllegalMoveError("there is no pending ability to decline")

    pending = state.pending_ability
    if pending.card_id != move.card_id or pending.ability_key != move.ability_key:
        raise IllegalMoveError("requested decline does not match the pending ability")

    updated = state.model_copy(deep=True)
    updated.pending_ability = None
    return updated


def _apply_promote_card(state: GameState, move: PromoteCardMove) -> GameState:
    updated = state.model_copy(deep=True)

    if state.phase == TurnPhase.MAIN:
        pending_list = updated.pending_immediate_promotions
    elif state.phase == TurnPhase.END_OF_TURN:
        pending_list = updated.pending_end_of_turn_promotions
    else:
        raise IllegalMoveError("promote_card is not available in the current phase")

    if not pending_list:
        raise IllegalMoveError("there is no pending promotion to resolve")

    pending = pending_list[0]
    if pending.deferred_choice:
        valid_target_ids = _deferred_promotion_target_ids(updated, move.player_id, pending)
        if move.card_id not in valid_target_ids:
            raise IllegalMoveError("requested promotion target is not valid for the pending promotion")
        _promote_card(updated, move.player_id, move.card_id)
        if pending.repeat_while_targets:
            remaining_target_ids = _deferred_promotion_target_ids(updated, move.player_id, pending)
            if not remaining_target_ids:
                pending_list.pop(0)
        else:
            pending_list.pop(0)
        return updated

    if pending.card_id != move.card_id or not pending.optional:
        raise IllegalMoveError("requested promotion does not match the pending optional promotion")

    pending_list.pop(0)
    _promote_card(updated, move.player_id, move.card_id)
    return updated


def _apply_skip_promote(state: GameState, move: SkipPromoteMove) -> GameState:
    updated = state.model_copy(deep=True)

    if state.phase == TurnPhase.MAIN:
        pending_list = updated.pending_immediate_promotions
    elif state.phase == TurnPhase.END_OF_TURN:
        pending_list = updated.pending_end_of_turn_promotions
    else:
        raise IllegalMoveError("skip_promote is not available in the current phase")

    if not pending_list:
        raise IllegalMoveError("there is no pending promotion to skip")

    pending = pending_list[0]
    if pending.deferred_choice:
        if pending.card_id != move.card_id:
            raise IllegalMoveError("requested skip does not match the pending deferred promotion")
        valid_target_ids = _deferred_promotion_target_ids(updated, move.player_id, pending)
        if valid_target_ids and not pending.optional:
            raise IllegalMoveError("cannot skip deferred promotion while valid targets exist")
        pending_list.pop(0)
        return updated

    if pending.card_id != move.card_id or not pending.optional:
        raise IllegalMoveError("requested skip does not match the pending optional promotion")

    pending_list.pop(0)
    return updated


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

    player = state.players[player_id]
    unique_indices = sorted(set(discard_hand_indices), reverse=True)
    if len(unique_indices) != discard_count:
        raise IllegalMoveError("discard_hand_indices must be unique")
    if any(index < 0 or index >= len(player.hand) for index in unique_indices):
        raise IllegalMoveError("discard_hand_indices contains an out-of-range value")

    state.resource_pool.power -= int(cost.get("power", 0))
    state.resource_pool.influence -= int(cost.get("influence", 0))
    for hand_index in unique_indices:
        player.discard_pile.append(player.hand.pop(hand_index))


def _apply_effect_with_wrappers(
    state: GameState,
    player_id: str,
    card: CardDefinition,
    *,
    source_card_id: str,
) -> GameState:
    updated = state.model_copy(deep=True)
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

    updated = state.model_copy(deep=True)
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


def _promote_card(state: GameState, player_id: str, card_id: str) -> None:
    player = state.players[player_id]
    try:
        played_index = player.played_cards.index(card_id)
    except ValueError as error:
        raise IllegalMoveError("cannot promote a card that is no longer played") from error

    promoted_card = player.played_cards.pop(played_index)
    player.inner_circle.append(promoted_card)


def _enter_end_of_turn(state: GameState) -> GameState:
    if state.pending_immediate_promotions:
        raise IllegalMoveError("resolve pending immediate promotions before ending the main phase")

    updated = state.model_copy(deep=True)
    updated.pending_ability = None
    mandatory_promotions = [
        pending
        for pending in updated.pending_end_of_turn_promotions
        if not pending.optional and not pending.deferred_choice
    ]
    updated.pending_end_of_turn_promotions = [
        pending
        for pending in updated.pending_end_of_turn_promotions
        if pending.optional or pending.deferred_choice
    ]

    for pending in mandatory_promotions:
        if pending.card_id not in updated.players[updated.current_player_id].played_cards:
            continue
        _promote_card(updated, updated.current_player_id, pending.card_id)

    _apply_end_of_turn_generic_effects(updated, include_force_discard=True, include_scaled_vp=False)

    return advance_phase(updated)


def _apply_end_of_turn_generic_effects(
    state: GameState,
    *,
    include_force_discard: bool,
    include_scaled_vp: bool,
) -> None:
    current_player_id = state.current_player_id
    cards_by_id = card_index(state.definition.catalog)
    played_card_ids = list(state.players[current_player_id].played_cards)

    for played_card_id in played_card_ids:
        definition = cards_by_id.get(played_card_id)
        if definition is None or definition.effect_key != "generic_card":
            continue

        for action in definition.actions:
            if action.timing != "end_of_turn":
                continue
            if (
                include_force_discard
                and action.op == "force_discard"
                and action.source_fragment.strip().lower() == "end_of_turn_mass_discard"
            ):
                for target_player_id, target_player in state.players.items():
                    if target_player_id == current_player_id:
                        continue
                    if not target_player.hand:
                        continue
                    target_player.discard_pile.append(target_player.hand.pop(0))
                continue

            if (
                include_scaled_vp
                and action.op == "grant_vp"
                and action.source_fragment.strip().lower().startswith("scaled_vp")
            ):
                state.players[current_player_id].score += _scaled_vp_award_count(state, current_player_id, action)


def _reshuffle_discard_into_deck(state: GameState, player_id: str) -> None:
    player = state.players[player_id]
    shuffled_deck = list(player.discard_pile)
    shuffler = Random((state.shuffle_seed << 16) ^ state.shuffle_count)
    shuffler.shuffle(shuffled_deck)
    state.shuffle_count += 1
    player.deck = shuffled_deck
    player.discard_pile = []


def _apply_cleanup(state: GameState) -> GameState:
    cleaned = state.model_copy(deep=True)
    player = cleaned.players[cleaned.current_player_id]

    player.discard_pile.extend(player.hand)
    player.discard_pile.extend(player.played_cards)
    player.hand = []
    player.played_cards = []

    for _ in range(5):
        if not player.deck and player.discard_pile:
            _reshuffle_discard_into_deck(cleaned, cleaned.current_player_id)
        if not player.deck:
            break
        player.hand.append(player.deck.pop())

    return advance_phase(cleaned)


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
        return int(pending.action_counters.get("assassinate_troop", 0))

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
    if action.op != "deploy_troops":
        return False

    pending = state.pending_generic_choice
    if pending is None:
        return False

    return _pending_action_counter_value(pending, action) < _resolve_runtime_action_count(
        state,
        player_id,
        action,
    )


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


def _legal_generic_target_selection_moves(
    state: GameState,
    player_id: str,
    pending: PendingGenericChoiceState,
    card: CardDefinition,
    action: CardAction,
) -> list[Move]:
    moves: list[Move] = []
    board_definitions = board_index(state.definition.board)

    if action.op == "deploy_troops":
        for node_id in sorted(state.board.nodes):
            if _can_deploy_to_node(state, player_id, node_id):
                moves.append(_generic_choice_move(player_id, pending, selection={"target_node_id": node_id}))
        return moves

    if action.op in {"assassinate_troop", "supplant_troop"}:
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
                selection = {
                    "target_node_id": node_id,
                    "target_slot_index": slot_index,
                }
                if requires_returned_spy_site:
                    selection["returned_node_id"] = returned_spy_node_id
                if requires_last_selected_node:
                    selection["required_node_id"] = last_selected_node_id
                moves.append(
                    _generic_choice_move(
                        player_id,
                        pending,
                        selection=selection,
                    )
                )
        return moves

    if action.op == "custom_effect":
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

    if action.op == "place_spy":
        candidate_sites = [
            node_id
            for node_id in sorted(state.board.nodes)
            if board_definitions[node_id].kind == NodeKind.SITE and player_id not in state.board.nodes[node_id].spies
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

    if action.op == "return_spy":
        owner_constraint = str(action.metadata.get("spy_owner", "any")).strip().lower()
        free_enemy_return = bool(action.metadata.get("free_enemy_return", False))
        for node_id in sorted(state.board.nodes):
            if board_definitions[node_id].kind == NodeKind.ROUTE:
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

    if action.op == "return_unit":
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

    if action.op == "move_troop":
        for source_node_id in sorted(state.board.nodes):
            source_state = state.board.nodes[source_node_id]
            for source_slot_index, occupant in enumerate(source_state.troop_slots):
                if occupant is None or occupant == player_id:
                    continue
                for target_node_id in sorted(board_definitions[source_node_id].adjacent_to):
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

    if action.op == "force_discard":
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

    if action.op == "promote_card":
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
        for card_id in played_cards:
            if promote_other and card_id == pending.source_card_id:
                continue
            if required_aspect is not None:
                definition = cards_by_id.get(card_id)
                if definition is None or definition.aspect != required_aspect:
                    continue
            moves.append(_generic_choice_move(player_id, pending, selection={"target_card_id": card_id}))
        return moves

    if action.op == "recruit_card":
        cards_by_id = card_index(state.definition.catalog)
        for market_slot, card_id in enumerate(state.market.row):
            definition = cards_by_id.get(card_id)
            if definition is None:
                continue
            if state.resource_pool.influence >= definition.cost and _legal_recruit_card_for_action(definition, action):
                moves.append(_generic_choice_move(player_id, pending, selection={"market_slot": market_slot}))
        return moves

    if action.op == "play_card":
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

    if action.op == "devour":
        default_zone = str(action.metadata.get("source_zone", action.target_scope)).strip() or "unknown"

        def _append_for_zone(zone: str) -> None:
            if zone == "hand":
                for hand_index in range(len(state.players[player_id].hand)):
                    moves.append(_generic_choice_move(player_id, pending, selection={"source_zone": zone, "hand_index": hand_index}))
                return
            if zone == "inner_circle":
                for inner_circle_index in range(len(state.players[player_id].inner_circle)):
                    moves.append(
                        _generic_choice_move(
                            player_id,
                            pending,
                            selection={"source_zone": zone, "inner_circle_index": inner_circle_index},
                        )
                    )
                return
            if zone == "played_self":
                moves.append(
                    _generic_choice_move(
                        player_id,
                        pending,
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
                                player_id,
                                pending,
                                selection={"source_zone": zone, "market_slot": market_slot},
                            )
                        )
                    return

                for market_slot in range(len(state.market.row)):
                    moves.append(
                        _generic_choice_move(
                            player_id,
                            pending,
                            selection={"source_zone": zone, "market_slot": market_slot},
                        )
                    )

        if default_zone == "unknown":
            for zone in ("hand", "played_self", "market", "inner_circle"):
                _append_for_zone(zone)
            return moves

        _append_for_zone(default_zone)
        return moves

    return moves


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
    updated = state.model_copy(deep=True)
    if resource == "power":
        updated.resource_pool.power += count
    else:
        updated.resource_pool.influence += count
    return updated


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
    count = _resolve_runtime_action_count(state, player_id, action)
    selection = selection or {}
    target_node_id = _require_selection_string(selection, "target_node_id")
    target_slot_index = _require_selection_int(selection, "target_slot_index")
    white_only = "white_troop_only" in action.filters
    requires_last_selected_node = bool(action.metadata.get("requires_last_selected_node", False))

    updated = state
    for _ in range(count):
        if target_node_id not in updated.board.nodes:
            raise IllegalMoveError("selection target_node_id is unknown")
        if requires_last_selected_node:
            required_node_id = _require_selection_string(selection, "required_node_id")
            if target_node_id != required_node_id:
                raise IllegalMoveError("selection target_node_id must match the previously selected node")
        node_state = updated.board.nodes[target_node_id]
        if target_slot_index < 0 or target_slot_index >= len(node_state.troop_slots):
            raise IllegalMoveError("selection target_slot_index is out of range")
        occupant = node_state.troop_slots[target_slot_index]
        if white_only and occupant != WHITE_TROOP_OWNER:
            raise IllegalMoveError("selection target is not a white troop")
        if not white_only and occupant == WHITE_TROOP_OWNER:
            raise IllegalMoveError("selection target cannot be a white troop for this action")

        updated = _apply_free_assassinate(updated, player_id, target_node_id, target_slot_index)
        pending = updated.pending_generic_choice
        if pending is not None:
            pending.action_counters["assassinate_troop"] = pending.action_counters.get("assassinate_troop", 0) + 1
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
        # Skip the action rather than raising — consistent with how
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

        resource = str(action.metadata.get("resource", "influence")).strip().lower()
        amount_raw = action.metadata.get("amount", count)
        try:
            amount = int(amount_raw)
        except (TypeError, ValueError) as error:
            raise RuleViolationError("conditional_bonus amount must be an integer") from error

        updated = state.model_copy(deep=True)
        if resource == "power":
            updated.resource_pool.power += amount
        elif resource == "influence":
            updated.resource_pool.influence += amount
        else:
            raise RuleViolationError("conditional_bonus resource must be power or influence")
        return updated

    if condition == "selected_node_total_spies_at_least":
        node_id = str(selection.get("target_node_id", "")).strip()
        minimum_raw = action.metadata.get("min_spies", 0)
        try:
            minimum = int(minimum_raw)
        except (TypeError, ValueError) as error:
            raise RuleViolationError("conditional_bonus min_spies must be an integer") from error

        if node_id and node_id in state.board.nodes and len(state.board.nodes[node_id].spies) >= minimum:
            resource = str(action.metadata.get("resource", "power")).strip().lower()
            amount_raw = action.metadata.get("amount", count)
            try:
                amount = int(amount_raw)
            except (TypeError, ValueError) as error:
                raise RuleViolationError("conditional_bonus amount must be an integer") from error

            updated = state.model_copy(deep=True)
            if resource == "power":
                updated.resource_pool.power += amount
            elif resource == "influence":
                updated.resource_pool.influence += amount
            else:
                raise RuleViolationError("conditional_bonus resource must be power or influence")
            return updated
        return state

    if condition == "focus_aspect_present":
        focus_aspect = str(action.metadata.get("focus_aspect", card.aspect)).strip().lower()
        resource = str(action.metadata.get("resource", "influence")).strip().lower()
        amount_raw = action.metadata.get("amount", count)
        try:
            amount = int(amount_raw)
        except (TypeError, ValueError) as error:
            raise RuleViolationError("conditional_bonus amount must be an integer") from error

        if _focus_requirement_met_for_aspect(state, player_id, focus_aspect, source_card_id):
            updated = state.model_copy(deep=True)
            if resource == "power":
                updated.resource_pool.power += amount
            elif resource == "influence":
                updated.resource_pool.influence += amount
            else:
                raise RuleViolationError("conditional_bonus resource must be power or influence")
            return updated
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
            resource = str(action.metadata.get("resource", "power")).strip().lower()
            amount_raw = action.metadata.get("amount", count)
            try:
                amount = int(amount_raw)
            except (TypeError, ValueError) as error:
                raise RuleViolationError("conditional_bonus amount must be an integer") from error

            updated = state.model_copy(deep=True)
            if resource == "power":
                updated.resource_pool.power += amount
            elif resource == "influence":
                updated.resource_pool.influence += amount
            else:
                raise RuleViolationError("conditional_bonus resource must be power or influence")
            return updated
        return state

    if condition == "player_inner_circle_at_least":
        minimum_raw = action.metadata.get("min_cards", 0)
        try:
            minimum = int(minimum_raw)
        except (TypeError, ValueError) as error:
            raise RuleViolationError("conditional_bonus min_cards must be an integer") from error

        player = state.players[player_id]
        if len(player.inner_circle) >= minimum:
            resource = str(action.metadata.get("resource", "influence")).strip().lower()
            amount_raw = action.metadata.get("amount", count)
            try:
                amount = int(amount_raw)
            except (TypeError, ValueError) as error:
                raise RuleViolationError("conditional_bonus amount must be an integer") from error

            updated = state.model_copy(deep=True)
            if resource == "power":
                updated.resource_pool.power += amount
            elif resource == "influence":
                updated.resource_pool.influence += amount
            else:
                raise RuleViolationError("conditional_bonus resource must be power or influence")
            return updated
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
    if effect_kind == "scaled_resource_from_player_zone":
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
        updated = state.model_copy(deep=True)
        if resource == "power":
            updated.resource_pool.power += gained
        elif resource == "influence":
            updated.resource_pool.influence += gained
        else:
            raise RuleViolationError("custom_effect resource must be power or influence")
        return updated

    if effect_kind == "give_insane_outcast_to_player_with_presence_on_last_selected_node":
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

    if effect_kind == "give_insane_outcast_to_selected_player":
        target_player_id = _require_selection_string(selection, "target_player_id")
        if target_player_id == player_id:
            raise IllegalMoveError("selection target_player_id must be an opponent")
        if target_player_id not in state.players:
            raise IllegalMoveError("selection target_player_id is unknown")

        updated = state.model_copy(deep=True)
        updated.players[target_player_id].discard_pile.append("insane_outcast")
        return updated

    if effect_kind == "give_insane_outcast_to_each_opponent":
        updated = state.model_copy(deep=True)
        for target_player_id in sorted(updated.players):
            if target_player_id == player_id:
                continue
            updated.players[target_player_id].discard_pile.append("insane_outcast")
        return updated

    if effect_kind == "mill_deck_to_discard":
        updated = state.model_copy(deep=True)
        player = updated.players[player_id]
        player.discard_pile.extend(player.deck)
        player.deck = []
        return updated

    if effect_kind == "self_purge_to_supply":
        return state

    if effect_kind == "steal_white_trophy_to_board":
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

    raise MissingRuleImplementationError(
        f"generic_card custom_effect is not implemented yet for card '{card.card_id}'"
    )


def _apply_generic_action(
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

    if not _action_focus_requirement_met(state, player_id, card, source_card_id, action):
        return state

    if action.op == "gain_resource":
        return _apply_generic_gain_resource(state, player_id, card, source_card_id, action, selection=selection)

    if action.op == "draw_cards":
        return _apply_generic_draw_cards(state, player_id, card, source_card_id, action, selection=selection)

    if action.op == "deploy_troops":
        return _apply_generic_deploy_troops(state, player_id, card, source_card_id, action, selection=selection)

    if action.op == "assassinate_troop":
        return _apply_generic_assassinate_troop(state, player_id, card, source_card_id, action, selection=selection)

    if action.op == "supplant_troop":
        return _apply_generic_supplant_troop(state, player_id, card, source_card_id, action, selection=selection)

    if action.op == "place_spy":
        return _apply_generic_place_spy(state, player_id, card, source_card_id, action, selection=selection)

    if action.op == "return_spy":
        return _apply_generic_return_spy(state, player_id, card, source_card_id, action, selection=selection)

    if action.op == "return_unit":
        return _apply_generic_return_unit(state, player_id, card, source_card_id, action, selection=selection)

    if action.op == "move_troop":
        return _apply_generic_move_troop(state, player_id, card, source_card_id, action, selection=selection)

    if action.op == "force_discard":
        return _apply_generic_force_discard(state, player_id, card, source_card_id, action, selection=selection)

    if action.op == "promote_card":
        return _apply_generic_promote_card(state, player_id, card, source_card_id, action, selection=selection)

    if action.op == "recruit_card":
        return _apply_generic_recruit_card(state, player_id, card, source_card_id, action, selection=selection)

    if action.op == "devour":
        return _apply_generic_devour(state, player_id, card, source_card_id, action, selection=selection)

    if action.op == "grant_vp":
        return _apply_generic_grant_vp(state, player_id, card, source_card_id, action, selection=selection)

    if action.op == "conditional_bonus":
        return _apply_generic_conditional_bonus(state, player_id, card, source_card_id, action, selection=selection)

    if action.op == "custom_effect":
        return _apply_generic_custom_effect(state, player_id, card, source_card_id, action, selection=selection)

    if action.op == "play_card":
        return _apply_generic_play_card(state, player_id, card, source_card_id, action, selection=selection)

    raise MissingRuleImplementationError(
        f"Unknown generic_card action op '{action.op}' for card '{card.card_id}'"
    )


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
        pending = PendingGenericChoiceState(
            source_card_id=source_card_id,
            execution_kind="sequence",
            current_actions=[action.model_copy(deep=True) for action in execution_model.actions],
            next_action_index=0,
            awaiting_option=False,
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


@register_effect("gain_power")
def _effect_gain_power(state: GameState, player_id: str, card: CardDefinition) -> GameState:
    updated = state.model_copy(deep=True)
    updated.resource_pool.power += int(card.effect_payload.get("power", 0))
    return updated


@register_effect("gain_influence")
def _effect_gain_influence(state: GameState, player_id: str, card: CardDefinition) -> GameState:
    updated = state.model_copy(deep=True)
    updated.resource_pool.influence += int(card.effect_payload.get("influence", 0))
    return updated


@register_effect("noop")
def _effect_noop(state: GameState, player_id: str, card: CardDefinition) -> GameState:
    return state.model_copy(deep=True)


@register_effect("todo_assassinate")
def _effect_todo_assassinate(state: GameState, player_id: str, card: CardDefinition) -> GameState:
    raise MissingRuleImplementationError(
        "Card effect 'todo_assassinate' is blocked until full assassinate rules are provided"
    )


@register_effect("generic_card")
def _effect_generic_card(state: GameState, player_id: str, card: CardDefinition) -> GameState:
    source_card_id = str(card.effect_payload.get("source_card_id", card.card_id))
    return _resolve_generic_execution(state, player_id, card, source_card_id)
