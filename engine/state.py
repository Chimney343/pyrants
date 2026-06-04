"""Domain models and setup helpers for engine runtime state."""

from __future__ import annotations

from copy import copy, deepcopy
from enum import Enum
from random import Random
from typing import Annotated, Any, Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic._internal._fields import PydanticUndefined


class NodeKind(str, Enum):
    """Board node categories."""

    SITE = "site"
    ROUTE = "route"


class TurnPhase(str, Enum):
    """Explicit turn and lifecycle phases for the game loop."""

    SETUP = "setup"
    MAIN = "main"
    END_OF_TURN = "end_of_turn"
    CLEANUP = "cleanup"
    GAME_OVER = "game_over"


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


class NodeState(BaseModel):
    """Mutable occupancy and marker state for one board node."""

    node_id: str = Field(min_length=1)
    troop_slots: list[str | None] = Field(default_factory=list)
    spies: set[str] = Field(default_factory=set)
    vp_tokens: int = Field(default=0, ge=0)


class BoardState(BaseModel):
    """Mutable board-wide state."""

    nodes: dict[str, NodeState] = Field(default_factory=dict)


class PlayerState(BaseModel):
    """Mutable player zones, supplies, and score counters."""

    player_id: str = Field(min_length=1)
    deck: list[str] = Field(default_factory=list)
    hand: list[str] = Field(default_factory=list)
    discard_pile: list[str] = Field(default_factory=list)
    played_cards: list[str] = Field(default_factory=list)
    inner_circle: list[str] = Field(default_factory=list)
    trophy_hall: list[str] = Field(default_factory=list)
    barracks: int = Field(default=40, ge=0)
    spies_available: int = Field(default=5, ge=0)
    vp_tokens: int = Field(default=0, ge=0)
    score: int = 0


class ResourcePool(BaseModel):
    """Transient resources that reset as turns progress."""

    power: int = Field(default=0, ge=0)
    influence: int = Field(default=0, ge=0)


class MarketState(BaseModel):
    """Mutable market row and market deck state."""

    deck: list[str] = Field(default_factory=list)
    row: list[str] = Field(default_factory=list)
    discard_pile: list[str] = Field(default_factory=list)


class PendingAbilityState(BaseModel):
    """One unresolved paid ability on a played card."""

    card_id: str = Field(min_length=1)
    ability_key: str = Field(min_length=1)


class PendingPromotionState(BaseModel):
    """One unresolved promote instruction for a played card."""

    card_id: str = Field(min_length=1)
    timing: Literal["immediate", "end_of_turn"]
    optional: bool = False
    deferred_choice: bool = False
    source_card_id: str | None = None
    requires_another_played_card: bool = False
    required_aspect: str | None = None
    required_secondary_aspect: str | None = None
    repeat_while_targets: bool = False


class PendingGenericChoiceState(BaseModel):
    """Runtime state for a structured generic card awaiting player input."""

    source_card_id: str = Field(min_length=1)
    execution_kind: Literal["sequence", "modal_choice", "repeat_choice"]
    option_ids: list[str] = Field(default_factory=list)
    selected_option_ids: list[str] = Field(default_factory=list)
    current_option_id: str | None = None
    current_actions: list[CardAction] = Field(default_factory=list)
    next_action_index: int = Field(default=0, ge=0)
    awaiting_option: bool = False
    remaining_repeats: int = Field(default=0, ge=0)
    allow_repeat: bool = False
    last_selection: dict[str, Any] = Field(default_factory=dict)
    action_counters: dict[str, int] = Field(default_factory=dict)


class GameState(BaseModel):
    """Mutable full game state used by rule evaluation and transitions."""

    definition: GameDefinition
    board: BoardState
    players: dict[str, PlayerState]
    turn_order: list[str]
    current_player_id: str = Field(min_length=1)
    phase: TurnPhase = TurnPhase.MAIN
    round_number: int = Field(default=1, ge=1)
    resource_pool: ResourcePool = Field(default_factory=ResourcePool)
    market: MarketState
    final_scores: dict[str, int] = Field(default_factory=dict)
    pending_ability: PendingAbilityState | None = None
    pending_immediate_promotions: list[PendingPromotionState] = Field(default_factory=list)
    pending_end_of_turn_promotions: list[PendingPromotionState] = Field(default_factory=list)
    pending_generic_choice: PendingGenericChoiceState | None = None
    devour_pile: list[str] = Field(default_factory=list)
    shuffle_seed: int = 0
    shuffle_count: int = Field(default=0, ge=0)

    def __deepcopy__(self, memo: dict[int, Any] | None = None) -> GameState:
        """Deep-copy the state while sharing the immutable definition tree.

        ``GameDefinition`` and all sub-models (CardCatalog, BoardDefinition,
        etc.) are frozen.  Skipping them avoids ~10 ms of wasted allocation
        per card play — a measurable saving over a 1000+ step simulation.
        """
        cls = type(self)
        m = cls.__new__(cls)
        if memo is None:
            memo = {}
        memo[id(self)] = m

        # Build __dict__ without deep-copying the immutable definition
        d: dict[str, Any] = {}
        for key, value in self.__dict__.items():
            if key == "definition":
                d[key] = value  # immutable → share reference
            else:
                d[key] = deepcopy(value, memo)

        object.__setattr__(m, "__dict__", d)
        object.__setattr__(m, "__pydantic_extra__", deepcopy(self.__pydantic_extra__, memo=memo))
        object.__setattr__(m, "__pydantic_fields_set__", copy(self.__pydantic_fields_set__))

        if not hasattr(self, "__pydantic_private__") or self.__pydantic_private__ is None:
            object.__setattr__(m, "__pydantic_private__", None)
        else:
            object.__setattr__(
                m,
                "__pydantic_private__",
                deepcopy({k: v for k, v in self.__pydantic_private__.items() if v is not PydanticUndefined}, memo=memo),
            )

        return m

    @model_validator(mode="after")
    def _validate_turn_owner(self) -> GameState:
        if self.current_player_id not in self.players:
            raise ValueError("current_player_id must be present in players")
        return self


def board_index(board_definition: BoardDefinition) -> dict[str, NodeDefinition]:
    """Return board definitions by node id."""

    return {node.node_id: node for node in board_definition.nodes}


def card_index(catalog: CardCatalog) -> dict[str, CardDefinition]:
    """Return card definitions by card id."""

    return {card.card_id: card for card in catalog.cards}


def expand_deck(deck_definition: DeckDefinition) -> list[str]:
    """Expand a counted deck definition into a flat card-id list."""

    expanded: list[str] = []
    for entry in deck_definition.entries:
        expanded.extend([entry.card_id] * entry.count)
    return expanded


def create_board_state(board_definition: BoardDefinition) -> BoardState:
    """Create mutable board state from immutable board definitions."""

    nodes: dict[str, NodeState] = {}
    for node_definition in board_definition.nodes:
        troop_slots = (
            list(node_definition.initial_troop_slots)
            if node_definition.initial_troop_slots is not None
            else [None] * node_definition.troop_capacity
        )
        nodes[node_definition.node_id] = NodeState(
            node_id=node_definition.node_id,
            troop_slots=troop_slots,
            spies=set(),
            vp_tokens=node_definition.initial_vp_tokens,
        )
    return BoardState(nodes=nodes)


def draw_cards(player_state: PlayerState, count: int, rng: Random) -> PlayerState:
    """Draw cards, reshuffling discard into deck when needed."""

    updated = player_state.model_copy(deep=True)
    for _ in range(count):
        if not updated.deck and updated.discard_pile:
            new_deck = list(updated.discard_pile)
            rng.shuffle(new_deck)
            updated.deck = new_deck
            updated.discard_pile = []

        if not updated.deck:
            break

        updated.hand.append(updated.deck.pop())

    return updated


def create_player_state(
    player_id: str,
    starter_cards: list[str],
    starting_troops: int,
    starting_spies: int,
    rng: Random,
) -> PlayerState:
    """Build a player's initial runtime state from setup definitions."""

    deck = list(starter_cards)
    rng.shuffle(deck)

    initial_state = PlayerState(
        player_id=player_id,
        deck=deck,
        barracks=starting_troops,
        spies_available=starting_spies,
    )
    return draw_cards(initial_state, count=5, rng=rng)


def create_market_state(setup_definition: SetupDefinition, rng: Random) -> MarketState:
    """Initialize market deck and visible row from setup definitions."""

    market_deck = expand_deck(setup_definition.market_deck)
    rng.shuffle(market_deck)

    row_count = min(setup_definition.market_row_size, len(market_deck))
    row = [market_deck.pop() for _ in range(row_count)]

    return MarketState(deck=market_deck, row=row)


def build_initial_game_state(
    definition: GameDefinition,
    player_ids: Iterable[str],
    rng: Random,
    shuffle_seed: int = 0,
) -> GameState:
    """Create a full initial runtime state from immutable game definitions."""

    turn_order = [player_id for player_id in player_ids]
    if not turn_order:
        raise ValueError("At least one player id is required")
    if len(turn_order) != len(set(turn_order)):
        raise ValueError("player ids must be unique")

    starter_cards = expand_deck(definition.setup.starter_deck)
    players: dict[str, PlayerState] = {}

    for player_id in turn_order:
        players[player_id] = create_player_state(
            player_id=player_id,
            starter_cards=starter_cards,
            starting_troops=definition.default_player_troops,
            starting_spies=definition.default_player_spies,
            rng=rng,
        )

    return GameState(
        definition=definition,
        board=create_board_state(definition.board),
        players=players,
        turn_order=turn_order,
        current_player_id=turn_order[0],
        phase=TurnPhase.MAIN,
        market=create_market_state(definition.setup, rng),
        shuffle_seed=shuffle_seed,
    )
