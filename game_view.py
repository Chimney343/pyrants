"""Structured session projections for GUI clients and simulations."""

from __future__ import annotations

from dataclasses import dataclass

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
    ResolveEndOfTurnMove,
    ResolveGenericChoiceMove,
    ReturnSpyMove,
    SkipPromoteMove,
    move_type,
    special_recruit_card_id,
)
from engine.state import GameState, NodeKind, PendingGenericChoiceState, PendingPromotionState, card_index
from engine.state import CardAction, ModalChoiceExecutionModel, RepeatChoiceExecutionModel
from game_session import GameSession, GameSessionSnapshot


@dataclass(frozen=True)
class CardView:
    """UI-friendly summary of one card reference."""

    card_id: str
    name: str
    cost: int
    aspect: str
    deck_vp: int
    inner_circle_vp: int
    rules_text: str
    notes: str
    secondary_aspects: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlayerSummaryView:
    """Aggregate counts and resources for one player."""

    player_id: str
    is_current: bool
    hand_count: int
    deck_count: int
    discard_count: int
    played_count: int
    inner_circle_count: int
    trophy_hall_count: int
    barracks: int
    spies_available: int
    vp_tokens: int
    score: int


@dataclass(frozen=True)
class NodeOccupancyView:
    """Board occupancy details without any layout coordinates."""

    node_id: str
    kind: NodeKind
    adjacent_to: tuple[str, ...]
    control_vp: int
    total_control_vp_per_turn: int
    troop_slots: tuple[str | None, ...]
    spies: tuple[str, ...]
    vp_tokens: int


@dataclass(frozen=True)
class LegalMoveView:
    """Rendered move metadata for list-based clients."""

    move: Move
    move_type: str
    label: str
    payload: dict[str, object]


@dataclass(frozen=True)
class GameView:
    """Session state projected into client-friendly collections."""

    round_number: int
    phase: str
    current_player_id: str
    resource_power: int
    resource_influence: int
    hand: tuple[CardView, ...]
    current_player_played: tuple[CardView, ...]
    current_player_deck_count: int
    current_player_discard: tuple[CardView, ...]
    current_player_inner_circle: tuple[CardView, ...]
    current_player_trophy_hall: tuple[str, ...]
    market_row: tuple[CardView, ...]
    market_deck_count: int
    market_discard_count: int
    player_summaries: tuple[PlayerSummaryView, ...]
    board_nodes: tuple[NodeOccupancyView, ...]
    prompts: tuple[str, ...]
    legal_moves: tuple[LegalMoveView, ...]
    is_terminal: bool
    winner_id: str | None
    final_scores: dict[str, int] | None

    @property
    def board_nodes_by_id(self) -> dict[str, NodeOccupancyView]:
        """Return board nodes keyed by id for layout-aware consumers."""

        return {node.node_id: node for node in self.board_nodes}


def filter_legal_moves(
    legal_moves: tuple[LegalMoveView, ...],
    *,
    hand_card_id: str | None = None,
    played_card_id: str | None = None,
    market_slot: int | None = None,
    node_id: str | None = None,
    option_id: str | None = None,
) -> tuple[LegalMoveView, ...]:
    """Filter legal moves using interactive UI selection context."""

    filtered = legal_moves

    if hand_card_id is not None:
        filtered = tuple(
            legal_move
            for legal_move in filtered
            if isinstance(legal_move.move, PlayCardMove)
            and legal_move.move.card_id == hand_card_id
        )

    if played_card_id is not None:
        filtered = tuple(
            legal_move
            for legal_move in filtered
            if isinstance(legal_move.move, ResolveGenericChoiceMove)
            and str(legal_move.move.selection.get("target_card_id", "")).strip() == played_card_id
        )

    if market_slot is not None:
        filtered = tuple(
            legal_move
            for legal_move in filtered
            if isinstance(legal_move.move, RecruitMove)
            and legal_move.move.market_slot == market_slot
        )

    if option_id is not None:
        filtered = tuple(
            legal_move
            for legal_move in filtered
            if isinstance(legal_move.move, ResolveGenericChoiceMove)
            and legal_move.move.option_id == option_id
        )

    if node_id is not None:
        filtered = tuple(
            legal_move
            for legal_move in filtered
            if _move_targets_node(legal_move.move, node_id)
        )

    return filtered


def build_game_view(session: GameSession, *, node_names: dict[str, str] | None = None) -> GameView:
    """Project the current session into a GUI-friendly view model."""

    return build_game_view_from_snapshot(session.snapshot(), node_names=node_names)


def build_game_view_from_snapshot(snapshot: GameSessionSnapshot, *, node_names: dict[str, str] | None = None) -> GameView:
    """Project a frozen session snapshot into a GUI-friendly view model."""

    state = snapshot.state
    cards_by_id = card_index(state.definition.catalog)
    current_player = state.players[state.current_player_id]

    hand = tuple(_card_view(cards_by_id, card_id) for card_id in current_player.hand)
    current_player_played = tuple(_card_view(cards_by_id, card_id) for card_id in current_player.played_cards)
    current_player_discard = tuple(_card_view(cards_by_id, card_id) for card_id in current_player.discard_pile)
    current_player_inner_circle = tuple(_card_view(cards_by_id, card_id) for card_id in current_player.inner_circle)
    current_player_trophy_hall = tuple(current_player.trophy_hall)
    market_row = tuple(_card_view(cards_by_id, card_id) for card_id in state.market.row)
    player_summaries = tuple(
        PlayerSummaryView(
            player_id=player_id,
            is_current=player_id == state.current_player_id,
            hand_count=len(player.hand),
            deck_count=len(player.deck),
            discard_count=len(player.discard_pile),
            played_count=len(player.played_cards),
            inner_circle_count=len(player.inner_circle),
            trophy_hall_count=len(player.trophy_hall),
            barracks=player.barracks,
            spies_available=player.spies_available,
            vp_tokens=player.vp_tokens,
            score=player.score,
        )
        for player_id in state.turn_order
        for player in [state.players[player_id]]
    )
    board_nodes = tuple(
        NodeOccupancyView(
            node_id=node_definition.node_id,
            kind=node_definition.kind,
            adjacent_to=tuple(node_definition.adjacent_to),
            control_vp=node_definition.control_vp,
            total_control_vp_per_turn=node_definition.total_control_vp_per_turn,
            troop_slots=tuple(state.board.nodes[node_definition.node_id].troop_slots),
            spies=tuple(sorted(state.board.nodes[node_definition.node_id].spies)),
            vp_tokens=state.board.nodes[node_definition.node_id].vp_tokens,
        )
        for node_definition in state.definition.board.nodes
    )
    prompts = _build_prompts(state, snapshot, cards_by_id)
    legal_moves = tuple(
        LegalMoveView(
            move=move,
            move_type=move_type(move),
            label=describe_move(state, move, node_names=node_names),
            payload=move.model_dump(mode="json"),
        )
        for move in snapshot.legal_moves
    )

    return GameView(
        round_number=state.round_number,
        phase=state.phase.value,
        current_player_id=state.current_player_id,
        resource_power=state.resource_pool.power,
        resource_influence=state.resource_pool.influence,
        hand=hand,
        current_player_played=current_player_played,
        current_player_deck_count=len(current_player.deck),
        current_player_discard=current_player_discard,
        current_player_inner_circle=current_player_inner_circle,
        current_player_trophy_hall=current_player_trophy_hall,
        market_row=market_row,
        market_deck_count=len(state.market.deck),
        market_discard_count=len(state.market.discard_pile),
        player_summaries=player_summaries,
        board_nodes=board_nodes,
        prompts=prompts,
        legal_moves=legal_moves,
        is_terminal=snapshot.is_terminal,
        winner_id=snapshot.winner_id,
        final_scores=snapshot.final_scores,
    )


def describe_move(state: GameState, move: Move, *, node_names: dict[str, str] | None = None) -> str:
    """Return a short, user-facing label for a legal move."""

    cards_by_id = card_index(state.definition.catalog)

    if isinstance(move, PlayCardMove):
        return f"Play {_card_name(cards_by_id, move.card_id)}"
    if isinstance(move, EndMainPhaseMove):
        return "End main phase"
    if isinstance(move, ResolveEndOfTurnMove):
        return "Resolve end of turn"
    if isinstance(move, ResolveCleanupMove):
        return "Resolve cleanup"
    if isinstance(move, DeployMove):
        return f"Deploy to {_node_display_name(move.target_node_id, node_names)}"
    if isinstance(move, AssassinateMove):
        owner = _troop_owner_label(state, move.target_node_id, move.target_slot_index)
        site_name = _node_display_name(move.target_node_id, node_names)
        return f"Assassinate {owner} troop at {site_name} slot {move.target_slot_index}"
    if isinstance(move, RecruitMove):
        if move.market_slot < len(state.market.row):
            card_id = state.market.row[move.market_slot]
        else:
            card_id = special_recruit_card_id(move.market_slot) or str(move.market_slot)
        return f"Recruit {_card_name(cards_by_id, card_id)}"
    if isinstance(move, ReturnSpyMove):
        return f"Return {move.spy_owner_id} spy from {_node_display_name(move.node_id, node_names)}"
    if isinstance(move, ActivateCardAbilityMove):
        return f"Activate {move.ability_key} on {_card_name(cards_by_id, move.card_id)}"
    if isinstance(move, DeclineCardAbilityMove):
        return f"Decline {move.ability_key} on {_card_name(cards_by_id, move.card_id)}"
    if isinstance(move, PromoteCardMove):
        return f"Promote {_card_name(cards_by_id, move.card_id)}"
    if isinstance(move, SkipPromoteMove):
        return f"Skip promote for {_card_name(cards_by_id, move.card_id)}"
    if isinstance(move, ResolveGenericChoiceMove):
        if move.option_id is not None:
            option_summary = _describe_generic_option_actions(cards_by_id, move.source_card_id, move.option_id)
            if option_summary is not None:
                return f"Choose {option_summary} for {_card_name(cards_by_id, move.source_card_id)}"
            return f"Choose {move.option_id} for {_card_name(cards_by_id, move.source_card_id)}"
        if move.selection:
            pending = state.pending_generic_choice
            action: CardAction | None = None
            if pending is not None and pending.source_card_id == move.source_card_id:
                if 0 <= pending.next_action_index < len(pending.current_actions):
                    action = pending.current_actions[pending.next_action_index]

            if action is not None:
                action_desc = _describe_option_action(action).capitalize()
                if action.op == "devour":
                    return _describe_devour_label(state, cards_by_id, move.selection)
                if action.op in {"assassinate_troop", "supplant_troop"}:
                    return _describe_assassinate_label(state, cards_by_id, move.selection, action, node_names)
                if action.op == "return_unit":
                    return _describe_return_unit_label(state, cards_by_id, move.selection, node_names)
                if action.op == "place_spy":
                    return _describe_place_spy_label(state, cards_by_id, move.selection, node_names)
                selection_parts = _format_selection_parts(cards_by_id, move.selection, node_names=node_names)
                preposition = "in" if node_names else "to"
                return f"{action_desc} {preposition} {', '.join(selection_parts)}"

            selection_label = _describe_generic_selection(cards_by_id, move.selection)
            return f"Resolve {selection_label} for {_card_name(cards_by_id, move.source_card_id)}"
        pending = state.pending_generic_choice
        if pending is not None and pending.source_card_id == move.source_card_id:
            if 0 <= pending.next_action_index < len(pending.current_actions):
                action = pending.current_actions[pending.next_action_index]
                action_desc = _describe_option_action(action)
                if action.optional:
                    return f"Skip {action_desc} for {_card_name(cards_by_id, move.source_card_id)}"
                return f"{action_desc} for {_card_name(cards_by_id, move.source_card_id)}"
        return f"Continue {_card_name(cards_by_id, move.source_card_id)}"

    return move_type(move).replace("_", " ").title()


def _card_view(cards_by_id: dict[str, object], card_id: str) -> CardView:
    card = cards_by_id.get(card_id)
    if card is None:
        return CardView(
            card_id=card_id,
            name="Unknown Card",
            cost=0,
            aspect="unknown",
            deck_vp=0,
            inner_circle_vp=0,
            rules_text="",
            notes="",
        )
    return CardView(
        card_id=card.card_id,
        name=card.name,
        cost=card.cost,
        aspect=card.aspect,
        deck_vp=card.deck_vp,
        inner_circle_vp=card.inner_circle_vp,
        rules_text=card.rules_text,
        notes=card.notes,
        secondary_aspects=tuple(getattr(card, "secondary_aspects", ())),
    )


def _card_name(cards_by_id: dict[str, object], card_id: str) -> str:
    card = cards_by_id.get(card_id)
    if card is None:
        return "Unknown Card"
    return card.name


def _node_display_name(node_id: str, node_names: dict[str, str] | None) -> str:
    if node_names is not None:
        return node_names.get(node_id, node_id)
    return node_id


def _describe_generic_selection(cards_by_id: dict[str, object], selection: dict[str, object]) -> str:
    target_card_id = str(selection.get("target_card_id", "")).strip()
    if target_card_id:
        return f"target {_card_name(cards_by_id, target_card_id)}"

    if not selection:
        return "target"

    details_parts: list[str] = []
    for key, value in selection.items():
        if key.endswith("card_id"):
            details_parts.append(f"{key}={_card_name(cards_by_id, str(value))}")
        else:
            details_parts.append(f"{key}={value}")
    details = ", ".join(details_parts)
    return f"target ({details})"


def _format_selection_parts(
    cards_by_id: dict[str, object],
    selection: dict[str, object],
    *,
    node_names: dict[str, str] | None = None,
) -> list[str]:
    parts: list[str] = []
    for key, value in selection.items():
        if key.endswith("card_id"):
            parts.append(f"{key}={_card_name(cards_by_id, str(value))}")
        elif node_names is not None and key.endswith("node_id"):
            node_name = node_names.get(str(value), str(value))
            parts.append(node_name)
        else:
            parts.append(f"{key}={value}")
    return parts if parts else ["target"]


_SOURCE_ZONE_LABELS: dict[str, str] = {
    "market": "market",
    "hand": "hand",
    "inner_circle": "inner circle",
    "played_self": "played cards",
}


def _describe_devour_label(state: GameState, cards_by_id: dict[str, object], selection: dict[str, object]) -> str:
    source_zone = str(selection.get("source_zone", "market")).strip()
    zone_label = _SOURCE_ZONE_LABELS.get(source_zone, source_zone.replace("_", " "))

    card_id: str | None = None
    if source_zone == "market":
        market_slot = int(selection.get("market_slot", -1))
        if 0 <= market_slot < len(state.market.row):
            card_id = state.market.row[market_slot]
    elif source_zone == "hand":
        hand_index = int(selection.get("hand_index", -1))
        player_hand = state.players[state.current_player_id].hand
        if 0 <= hand_index < len(player_hand):
            card_id = player_hand[hand_index]
    elif source_zone == "inner_circle":
        inner_circle_index = int(selection.get("inner_circle_index", -1))
        player_inner = state.players[state.current_player_id].inner_circle
        if 0 <= inner_circle_index < len(player_inner):
            card_id = player_inner[inner_circle_index]
    elif source_zone == "played_self":
        card_id = str(selection.get("target_card_id", "")).strip() or None

    card_label = _card_name(cards_by_id, card_id) if card_id is not None else "Unknown Card"
    return f"Devour {card_label} from {zone_label}"


def _describe_return_unit_label(
    state: GameState,
    cards_by_id: dict[str, object],
    selection: dict[str, object],
    node_names: dict[str, str] | None,
) -> str:
    unit_type = str(selection.get("unit_type", "unit")).strip()
    node_id = str(selection.get("node_id", "")).strip()
    target_slot_index = int(selection.get("target_slot_index", -1))
    site_name = _node_display_name(node_id, node_names)
    return f"Return {unit_type} from {site_name}, target_slot_index={target_slot_index}"


def _describe_place_spy_label(
    state: GameState,
    cards_by_id: dict[str, object],
    selection: dict[str, object],
    node_names: dict[str, str] | None,
) -> str:
    target_node_id = str(selection.get("target_node_id", "")).strip()
    source_node_id = str(selection.get("source_node_id", "")).strip()
    target_name = _node_display_name(target_node_id, node_names)
    if source_node_id:
        source_name = _node_display_name(source_node_id, node_names)
        return f"Move spy from {source_name} to {target_name}"
    preposition = "in" if node_names else "to"
    return f"Place spy {preposition} {target_name}"


def _troop_owner_label(state: GameState, node_id: str, slot_index: int) -> str:
    node_state = state.board.nodes.get(node_id)
    if node_state is None or slot_index < 0 or slot_index >= len(node_state.troop_slots):
        return "unknown"
    owner = node_state.troop_slots[slot_index]
    if owner == "white":
        return "white"
    if owner is None:
        return "empty"
    return owner


def _describe_assassinate_label(
    state: GameState,
    cards_by_id: dict[str, object],
    selection: dict[str, object],
    action: CardAction,
    node_names: dict[str, str] | None,
) -> str:
    target_node_id = str(selection.get("target_node_id", "")).strip()
    target_slot_index = int(selection.get("target_slot_index", -1))
    owner = _troop_owner_label(state, target_node_id, target_slot_index)
    site_name = _node_display_name(target_node_id, node_names)
    verb = action.op.split("_")[0].capitalize()
    return f"{verb} {owner} troop at {site_name} slot {target_slot_index}"


def _describe_end_of_turn_promotion(
    cards_by_id: dict[str, object],
    pending: PendingPromotionState,
) -> str:
    source_card_id = pending.source_card_id or pending.card_id
    source_label = _card_name(cards_by_id, source_card_id)

    if pending.deferred_choice:
        return f"from {source_label} (choose target)"

    if pending.card_id != source_card_id:
        return f"from {source_label} -> {_card_name(cards_by_id, pending.card_id)}"

    return f"from {source_label}"


def _describe_generic_option_actions(
    cards_by_id: dict[str, object],
    source_card_id: str,
    option_id: str,
) -> str | None:
    card = cards_by_id.get(source_card_id)
    if card is None:
        return None

    execution_model = card.execution_model
    if not isinstance(execution_model, (ModalChoiceExecutionModel, RepeatChoiceExecutionModel)):
        return None

    option = next((candidate for candidate in execution_model.options if candidate.option_id == option_id), None)
    if option is None:
        return None

    return _summarize_option_actions(option.actions)


def _summarize_option_actions(actions: list[CardAction]) -> str:
    if not actions:
        return "no effect"

    counts: dict[str, int] = {}
    ordered_labels: list[str] = []
    for action in actions:
        label = _describe_option_action(action)
        if label not in counts:
            counts[label] = 0
            ordered_labels.append(label)
        counts[label] += 1

    summary_parts: list[str] = []
    for label in ordered_labels:
        count = counts[label]
        summary_parts.append(f"{label} x{count}" if count > 1 else label)
    return ", ".join(summary_parts)


def _describe_option_action(action: CardAction) -> str:
    if action.op == "gain_resource":
        resource = str(action.metadata.get("resource", "resource")).strip().lower() or "resource"
        amount = action.quantity.value if action.quantity.kind == "fixed" and action.quantity.value is not None else 1
        return f"gain {amount} {resource}"

    if action.op == "draw_cards":
        amount = action.quantity.value if action.quantity.kind == "fixed" and action.quantity.value is not None else None
        if amount is None:
            return "draw cards"
        unit = "card" if amount == 1 else "cards"
        return f"draw {amount} {unit}"

    return action.op.replace("_", " ")


def _build_prompts(
    state: GameState,
    snapshot: GameSessionSnapshot,
    cards_by_id: dict[str, object],
) -> tuple[str, ...]:
    prompts: list[str] = []

    if snapshot.is_terminal:
        winner = snapshot.winner_id if snapshot.winner_id is not None else "tie"
        prompts.append(f"Game over. Winner: {winner}.")
        return tuple(prompts)

    if state.pending_ability is not None:
        prompts.append(
            f"Resolve paid ability {state.pending_ability.ability_key} on "
            f"{_card_name(cards_by_id, state.pending_ability.card_id)}."
        )

    if state.pending_immediate_promotions:
        labels = ", ".join(_card_name(cards_by_id, pending.card_id) for pending in state.pending_immediate_promotions)
        prompts.append(f"Resolve immediate promotion for {labels}.")

    if state.pending_end_of_turn_promotions:
        labels = ", ".join(
            _describe_end_of_turn_promotion(cards_by_id, pending)
            for pending in state.pending_end_of_turn_promotions
        )
        prompts.append(f"Resolve end-of-turn promotion: {labels}.")

    if state.pending_generic_choice is not None:
        prompts.append(_generic_prompt(state.pending_generic_choice, cards_by_id))

    if not prompts:
        prompts.append(
            f"{state.current_player_id} is acting in {state.phase.value.replace('_', ' ')}."
        )

    return tuple(prompts)


def _generic_prompt(pending: PendingGenericChoiceState, cards_by_id: dict[str, object]) -> str:
    card_label = _card_name(cards_by_id, pending.source_card_id)
    if pending.awaiting_option:
        return f"Choose an option for {card_label}."
    return f"Resolve the next step for {card_label}."


def _move_targets_node(move: Move, node_id: str) -> bool:
    if isinstance(move, DeployMove):
        return move.target_node_id == node_id
    if isinstance(move, AssassinateMove):
        return move.target_node_id == node_id
    if isinstance(move, ReturnSpyMove):
        return move.node_id == node_id
    if isinstance(move, ResolveGenericChoiceMove):
        if not move.selection:
            return False
        candidate_node_ids = {
            str(value)
            for key, value in move.selection.items()
            if key in {"target_node_id", "node_id", "source_node_id"}
        }
        return node_id in candidate_node_ids
    return False
