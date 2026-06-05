"""Rule evaluation and pure state transition functions."""

from __future__ import annotations

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
    CardDefinition,
    GameState,
    PendingAbilityState,
    PendingPromotionState,
    TurnPhase,
    card_index,
)

from engine.helpers import (
    SPECIAL_RECRUIT_STACKS,
    _EFFECT_REGISTRY,
    _apply_effect_with_wrappers,
    _apply_recruit,
    _can_activate_pending_ability,
    _can_deploy_to_node,
    _deferred_promotion_target_ids,
    _is_aberrations_enabled,
    _pay_ability_cost,
    _promote_card,
    _remaining_special_stack_count,
    _reshuffle_discard_into_deck,
    _scaled_vp_award_count,
    _special_stack_config,
    has_presence,
    register_effect,
)

from engine.generic_runtime import (
    _action_requires_selection,
    _apply_resolve_generic_choice,
    _legal_pending_generic_choice_moves,
    _resolve_generic_execution,
)

# ── public API ──────────────────────────────────────────────────────────────


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


# ── core board actions ──────────────────────────────────────────────────────


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


# ── end of turn and cleanup ─────────────────────────────────────────────────


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


# ── effect registration ────────────────────────────────────────────────────


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
