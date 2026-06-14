"""Core generic choice resolution — the central game loop for card actions."""

from __future__ import annotations

from engine.errors import (
    IllegalMoveError,
    MissingRuleImplementationError,
    RuleViolationError,
)
from engine.generic_runtime._utils import (
    _action_focus_requirement_met,
    _action_requires_additional_choice,
    _action_requires_selection,
    _available_repeat_option_ids,
    _generic_choice_move,
    _pending_action_counter_key,
    _pending_generic_active_action,
    _pending_generic_card_definition,
    _resolve_runtime_action_count,
)
from engine.helpers import _apply_promote_instruction
from engine.moves import Move, ResolveGenericChoiceMove
from engine.state import (
    CardAction,
    CardDefinition,
    GameState,
    ModalChoiceExecutionModel,
    PendingGenericChoiceState,
    RepeatChoiceExecutionModel,
    SequenceExecutionModel,
    TurnPhase,
)


def _resolve_card_option_actions(
    pending: PendingGenericChoiceState,
    execution_model: SequenceExecutionModel | ModalChoiceExecutionModel | RepeatChoiceExecutionModel,
    option_id: str,
) -> list[CardAction]:
    if isinstance(execution_model, (ModalChoiceExecutionModel, RepeatChoiceExecutionModel)):
        option = next((candidate for candidate in execution_model.options if candidate.option_id == option_id), None)
        if option is None:
            raise IllegalMoveError("selected option_id does not exist on execution model")
        return [action.model_copy(deep=True) for action in option.actions]

    raise RuleViolationError("pending generic choice is inconsistent with card execution model")


def _option_is_currently_selectable(
    state: GameState,
    player_id: str,
    pending: PendingGenericChoiceState,
    card: CardDefinition,
    option_id: str,
) -> bool:
    from engine.generic_runtime._selection import _legal_generic_target_selection_moves

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
    from engine.generic_runtime._selection import _legal_generic_target_selection_moves

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


def _auto_resolve_pending_generic(state: GameState, player_id: str) -> GameState:
    from engine.generic_runtime._actions import _apply_generic_action
    from engine.generic_runtime._selection import _legal_generic_target_selection_moves

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


def _apply_resolve_generic_choice(state: GameState, move: ResolveGenericChoiceMove) -> GameState:
    from engine.generic_runtime._actions import _apply_generic_action

    if state.phase != TurnPhase.MAIN:
        raise IllegalMoveError("resolve_generic_choice can only be used during the main phase")

    pending = state.pending_generic_choice
    if pending is None:
        raise IllegalMoveError("there is no pending generic choice to resolve")
    if pending.source_card_id != move.source_card_id:
        raise IllegalMoveError("source_card_id does not match the pending generic choice")

    updated = state._cow_clone()
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
            execution_kind="repeat_choice",
            option_ids=[option.option_id for option in execution_model.options],
            allow_repeat=False,
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

    updated = state._cow_clone()
    updated.pending_generic_choice = pending
    return _auto_resolve_pending_generic(updated, player_id)
