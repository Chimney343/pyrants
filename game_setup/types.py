"""Engine-agnostic domain types shared across setup, loading, and UI layers.

These models were extracted from the legacy Python engine so the data layer
(``game_setup``) and the surviving UI/loader code can depend on neutral
Pydantic definitions without importing the engine runtime.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class NodeKind(StrEnum):
    """Board node categories."""

    SITE = "site"
    ROUTE = "route"


class DeckEntry(BaseModel):
    """Card reference and multiplicity inside a deck definition."""

    model_config = ConfigDict(frozen=True)

    card_id: str = Field(min_length=1)
    count: int = Field(gt=0)


class DeckDefinition(BaseModel):
    """Immutable deck blueprint loaded from external data."""

    model_config = ConfigDict(frozen=True)

    deck_id: str = Field(min_length=1)
    entries: list[DeckEntry] = Field(default_factory=list)


class ActionQuantity(BaseModel):
    """Structured quantity metadata for one card action."""

    model_config = ConfigDict(frozen=True)

    kind: str = Field(min_length=1)
    value: int | None = None


class CardAction(BaseModel):
    """One structured runtime action produced from card rules text."""

    model_config = ConfigDict(frozen=True)

    action_id: str = Field(min_length=1)
    op: str = Field(min_length=1)
    target_scope: str = Field(min_length=1)
    timing: str = Field(min_length=1)
    optional: bool = False
    quantity: ActionQuantity = Field(default_factory=lambda: ActionQuantity(kind="unspecified"))
    filters: list[str] = Field(default_factory=list)
    source_fragment: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class CardOption(BaseModel):
    """One player-selectable option in a modal or repeat execution model."""

    model_config = ConfigDict(frozen=True)

    option_id: str = Field(min_length=1)
    actions: list[CardAction] = Field(default_factory=list)


class SequenceExecutionModel(BaseModel):
    """Execution model for cards that resolve actions in a fixed order."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["sequence"]
    actions: list[CardAction] = Field(default_factory=list)


class ModalChoiceExecutionModel(BaseModel):
    """Execution model for cards that offer one player-selected option."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["modal_choice"]
    selection: str = Field(default="exactly_one", min_length=1)
    options: list[CardOption] = Field(default_factory=list)


class RepeatChoiceExecutionModel(BaseModel):
    """Execution model for cards that repeat option selection multiple times."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["repeat_choice"]
    repeat_count: int = Field(gt=0)
    allow_repeat: bool = False
    options: list[CardOption] = Field(default_factory=list)


ExecutionModel = Annotated[
    SequenceExecutionModel | ModalChoiceExecutionModel | RepeatChoiceExecutionModel,
    Field(discriminator="kind"),
]


class GlobalCondition(BaseModel):
    """High-level condition metadata attached to a structured card."""

    model_config = ConfigDict(frozen=True)

    condition_type: str = Field(min_length=1)
    description: str = ""


class StateContract(BaseModel):
    """Summary of the state locations a structured card reads and writes."""

    model_config = ConfigDict(frozen=True)

    reads: list[str] = Field(default_factory=list)
    writes: list[str] = Field(default_factory=list)


class CardDefinition(BaseModel):
    """Immutable card metadata and effect linkage."""

    model_config = ConfigDict(frozen=True)

    card_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    cost: int = Field(ge=0)
    aspect: str = Field(min_length=1)
    secondary_aspects: list[str] = Field(default_factory=list)
    deck_vp: int = 0
    inner_circle_vp: int = 0
    rules_text: str = ""
    notes: str = ""
    execution_model: ExecutionModel | None = None
    actions: list[CardAction] = Field(default_factory=list)
    global_conditions: list[GlobalCondition] = Field(default_factory=list)
    state_contract: StateContract = Field(default_factory=StateContract)
    effect_key: str = Field(min_length=1)
    effect_payload: dict[str, Any] = Field(default_factory=dict)


class CardCatalog(BaseModel):
    """Collection of all cards available to a game definition."""

    model_config = ConfigDict(frozen=True)

    catalog_id: str = Field(min_length=1)
    cards: list[CardDefinition] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_unique_card_ids(self) -> CardCatalog:
        card_ids = [card.card_id for card in self.cards]
        if len(card_ids) != len(set(card_ids)):
            raise ValueError("Card ids must be unique inside a catalog")
        return self


class NodeDefinition(BaseModel):
    """Immutable board node definition loaded from external data."""

    model_config = ConfigDict(frozen=True)

    node_id: str = Field(min_length=1)
    kind: NodeKind
    adjacent_to: list[str] = Field(default_factory=list)
    troop_capacity: int = Field(gt=0)
    control_vp: int = Field(default=0, ge=0)
    total_control_vp_per_turn: int = Field(default=0, ge=0)
    initial_troop_slots: list[str | None] | None = None
    initial_vp_tokens: int = Field(default=0, ge=0)
    influence_income: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _validate_route_capacity(self) -> NodeDefinition:
        if self.kind == NodeKind.ROUTE and self.troop_capacity != 1:
            raise ValueError("Route nodes must have troop_capacity=1")

        if self.initial_troop_slots is not None:
            if len(self.initial_troop_slots) != self.troop_capacity:
                raise ValueError("initial_troop_slots length must match troop_capacity")

            for occupant in self.initial_troop_slots:
                if occupant is None:
                    continue
                if occupant != "white":
                    raise ValueError("initial_troop_slots currently supports only 'white' occupants")

        return self


class BoardDefinition(BaseModel):
    """Immutable board graph specification."""

    model_config = ConfigDict(frozen=True)

    board_id: str = Field(min_length=1)
    nodes: list[NodeDefinition] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_graph(self) -> BoardDefinition:
        node_ids = [node.node_id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("Board node ids must be unique")

        known_ids = set(node_ids)
        for node in self.nodes:
            for adjacent_id in node.adjacent_to:
                if adjacent_id not in known_ids:
                    raise ValueError(f"Node '{node.node_id}' references unknown neighbor '{adjacent_id}'")

        return self


class SetupDefinition(BaseModel):
    """Immutable setup definition for starter and market decks."""

    model_config = ConfigDict(frozen=True)

    setup_id: str = Field(min_length=1)
    starter_deck: DeckDefinition
    market_deck: DeckDefinition
    market_row_size: int = Field(default=6, gt=0)


class GameDefinition(BaseModel):
    """Top-level immutable game definition."""

    model_config = ConfigDict(frozen=True)

    definition_id: str = Field(min_length=1)
    board: BoardDefinition
    catalog: CardCatalog
    setup: SetupDefinition
    default_player_troops: int = Field(default=40, ge=0)
    default_player_spies: int = Field(default=5, ge=0)

    @model_validator(mode="after")
    def _validate_deck_references(self) -> GameDefinition:
        known_card_ids = {card.card_id for card in self.catalog.cards}
        for deck in (self.setup.starter_deck, self.setup.market_deck):
            for entry in deck.entries:
                if entry.card_id not in known_card_ids:
                    raise ValueError(
                        f"Deck '{deck.deck_id}' references unknown card id '{entry.card_id}'"
                    )
        return self
