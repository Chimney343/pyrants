"""Canonical "what player p knows" projection for information-state keys and determinization.

PublicView: board occupancy (controllers, troop/spy counts, VP tokens), market row,
pending effect identifiers, turn metadata.  No hand/deck/discard/devour contents.

PrivateView: PublicView + the observing player's hand ids, deck size, discard size,
barracks, inner circle, trophy hall, resources.  No opponent private zone contents.

Both models are Pydantic (frozen) for stable JSON serialization — the serialized form
is used as the information-state string key in IS-MCTS.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from engine.state import (
    GameState,
    NodeKind,
)


def _board_node_control_owner(troop_slots: list[str | None]) -> str | None:
    """Return the player id with most troops on a node, or None if no clear controller."""
    counts: dict[str, int] = {}
    for occupant in troop_slots:
        if occupant is not None:
            counts[occupant] = counts.get(occupant, 0) + 1

    if not counts:
        return None

    max_count = max(counts.values())
    leaders = [owner for owner, count in counts.items() if count == max_count]
    return leaders[0] if len(leaders) == 1 and leaders[0] != "white" else None


def _troop_counts(troop_slots: list[str | None]) -> dict[str, int]:
    """Return per-player troop count on a board node."""
    counts: dict[str, int] = {}
    for occupant in troop_slots:
        if occupant is not None:
            counts[occupant] = counts.get(occupant, 0) + 1
    return counts


class PublicNodeView(BaseModel):
    """Public board-node state — everything visible to all players."""

    model_config = ConfigDict(frozen=True)

    node_id: str = Field(min_length=1)
    kind: NodeKind
    controller: str | None = None
    troop_counts: dict[str, int] = Field(default_factory=dict)
    spy_owners: list[str] = Field(default_factory=list)
    vp_tokens: int = 0


class PublicPendingAbilityView(BaseModel):
    """Public summary of a pending paid ability."""

    model_config = ConfigDict(frozen=True)

    card_id: str = Field(min_length=1)
    ability_key: str = Field(min_length=1)


class PublicPendingPromotionView(BaseModel):
    """Public summary of a pending promotion."""

    model_config = ConfigDict(frozen=True)

    card_id: str = Field(min_length=1)
    timing: str
    optional: bool = False
    source_card_id: str | None = None
    requires_another_played_card: bool = False
    required_aspect: str | None = None


class PublicPendingGenericChoiceView(BaseModel):
    """Public summary of a pending generic card choice."""

    model_config = ConfigDict(frozen=True)

    source_card_id: str = Field(min_length=1)
    execution_kind: str
    awaiting_option: bool = False
    remaining_repeats: int = 0


class PublicView(BaseModel):
    """Everything that both players can observe.

    Excludes all hidden-zone contents (hands, decks, discards, devour piles).
    """

    model_config = ConfigDict(frozen=True)

    round_number: int = Field(ge=1)
    phase: str
    current_player_id: str = Field(min_length=1)
    turn_order: list[str] = Field(default_factory=list)

    market_row: list[str] = Field(default_factory=list)
    market_deck_size: int = 0
    market_discard_size: int = 0

    board: list[PublicNodeView] = Field(default_factory=list)

    resource_power: int = 0
    resource_influence: int = 0

    public_player_summaries: dict[str, dict[str, int]] = Field(default_factory=dict)

    pending_ability: PublicPendingAbilityView | None = None
    pending_immediate_promotions: list[PublicPendingPromotionView] = Field(default_factory=list)
    pending_end_of_turn_promotions: list[PublicPendingPromotionView] = Field(default_factory=list)
    pending_generic_choice: PublicPendingGenericChoiceView | None = None


class PrivateView(BaseModel):
    """Public view + the observing player's hidden-zone contents."""

    model_config = ConfigDict(frozen=True)

    public: PublicView

    hand: list[str] = Field(default_factory=list)
    deck_size: int = 0
    discard_size: int = 0
    devour_size: int = 0
    played_cards: list[str] = Field(default_factory=list)
    inner_circle: list[str] = Field(default_factory=list)
    trophy_hall: list[str] = Field(default_factory=list)
    barracks: int = 0
    spies_available: int = 0
    vp_tokens: int = 0
    score: int = 0


def public_view(state: GameState) -> PublicView:
    """Project ``state`` into the public-information subset visible to both players.

    Returns a frozen Pydantic model.  Two states with the same ``public_view``
    are indistinguishable to a third-party observer.
    """
    board_views: list[PublicNodeView] = []
    for node_def in state.definition.board.nodes:
        node_state = state.board.nodes[node_def.node_id]
        board_views.append(
            PublicNodeView(
                node_id=node_def.node_id,
                kind=node_def.kind,
                controller=_board_node_control_owner(node_state.troop_slots),
                troop_counts=_troop_counts(node_state.troop_slots),
                spy_owners=sorted(node_state.spies),
                vp_tokens=node_state.vp_tokens,
            )
        )

    public_player_summaries: dict[str, dict[str, int]] = {}
    for pid in state.turn_order:
        p = state.players[pid]
        public_player_summaries[pid] = {
            "hand_size": len(p.hand),
            "deck_size": len(p.deck),
            "discard_size": len(p.discard_pile),
            "devour_size": len(state.devour_pile),
            "played_size": len(p.played_cards),
            "inner_circle_size": len(p.inner_circle),
            "trophy_hall_size": len(p.trophy_hall),
            "barracks": p.barracks,
            "spies_available": p.spies_available,
            "vp_tokens": p.vp_tokens,
            "score": p.score,
        }

    pending_ability = None
    if state.pending_ability is not None:
        pending_ability = PublicPendingAbilityView(
            card_id=state.pending_ability.card_id,
            ability_key=state.pending_ability.ability_key,
        )

    pending_generic = None
    if state.pending_generic_choice is not None:
        gc = state.pending_generic_choice
        pending_generic = PublicPendingGenericChoiceView(
            source_card_id=gc.source_card_id,
            execution_kind=gc.execution_kind,
            awaiting_option=gc.awaiting_option,
            remaining_repeats=gc.remaining_repeats,
        )

    return PublicView(
        round_number=state.round_number,
        phase=state.phase.value,
        current_player_id=state.current_player_id,
        turn_order=list(state.turn_order),
        market_row=list(state.market.row),
        market_deck_size=len(state.market.deck),
        market_discard_size=len(state.market.discard_pile),
        board=board_views,
        resource_power=state.resource_pool.power,
        resource_influence=state.resource_pool.influence,
        public_player_summaries=public_player_summaries,
        pending_ability=pending_ability,
        pending_immediate_promotions=[
            PublicPendingPromotionView(
                card_id=pp.card_id,
                timing=pp.timing,
                optional=pp.optional,
                source_card_id=pp.source_card_id,
                requires_another_played_card=pp.requires_another_played_card,
                required_aspect=pp.required_aspect,
            )
            for pp in state.pending_immediate_promotions
        ],
        pending_end_of_turn_promotions=[
            PublicPendingPromotionView(
                card_id=pp.card_id,
                timing=pp.timing,
                optional=pp.optional,
                source_card_id=pp.source_card_id,
                requires_another_played_card=pp.requires_another_played_card,
                required_aspect=pp.required_aspect,
            )
            for pp in state.pending_end_of_turn_promotions
        ],
        pending_generic_choice=pending_generic,
    )


def private_view(state: GameState, player_id: str) -> PrivateView:
    """Project ``state`` into what ``player_id`` can observe.

    The output includes the full public view plus the observing player's own
    hand, deck/discard/devour sizes, inner circle, trophy hall, barracks,
    spies, VP tokens, and score.  Opponent hidden-zone contents are excluded.
    """
    pub = public_view(state)
    p = state.players[player_id]

    return PrivateView(
        public=pub,
        hand=list(p.hand),
        deck_size=len(p.deck),
        discard_size=len(p.discard_pile),
        devour_size=len(state.devour_pile),
        played_cards=list(p.played_cards),
        inner_circle=list(p.inner_circle),
        trophy_hall=list(p.trophy_hall),
        barracks=p.barracks,
        spies_available=p.spies_available,
        vp_tokens=p.vp_tokens,
        score=p.score,
    )
