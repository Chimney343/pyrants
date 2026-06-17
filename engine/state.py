"""Domain models and setup helpers for engine runtime state."""

from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy
from enum import Enum
from random import Random
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Fast type-dispatch table for _copy_field.
# Maps exact types to dispatch codes: 0=share, 1=list, 2=set, 3=dict.
_COPY_SHARE = 0
_COPY_LIST = 1
_COPY_SET = 2
_COPY_DICT = 3
_TYPE_DISPATCH: dict[type, int] = {
    type(None): _COPY_SHARE,
    str: _COPY_SHARE,
    int: _COPY_SHARE,
    bool: _COPY_SHARE,
    float: _COPY_SHARE,
    list: _COPY_LIST,
    set: _COPY_SET,
    dict: _COPY_DICT,
}


def _copy_field(value: Any, memo: dict[int, Any]) -> Any:
    """Copy a single field value, dispatching by type.

    Uses ``type()`` dict lookup for the common primitive and collection
    types, falling back to ``isinstance`` for BaseModel and Enum.
    Empty collections are returned as-is (they carry no mutable state).
    """
    action = _TYPE_DISPATCH.get(type(value))
    if action is not None:
        if action is _COPY_SHARE:
            return value
        if action is _COPY_LIST:
            # Empty list short-circuit — strings/int are immutable so a
            # shallow list() copy is equivalent to recursive _copy_field.
            # For lists that may contain BaseModel instances we must
            # recurse, but the hot path (list[str]) is fast-tracked.
            if not value:
                return []
            first = value[0]
            if type(first) is str or first is None or isinstance(first, (int, bool, float)):
                return list(value)
            return [_copy_field(v, memo) for v in value]
        if action is _COPY_SET:
            if not value:
                return set()
            # Set elements are always immutable in our domain (strings).
            return set(value)
        # action is _COPY_DICT
        if not value:
            return {}
        return {_copy_field(k, memo): _copy_field(v, memo) for k, v in value.items()}
    if isinstance(value, BaseModel):
        if type(value).model_config.get("frozen", False):
            return value
        return value.__deepcopy__(memo)
    if isinstance(value, Enum):
        return value
    return deepcopy(value, memo)


def _model_deepcopy_fields(self: BaseModel, memo: dict[int, Any] | None = None) -> BaseModel:
    """Fast structural clone for Pydantic v2 mutable models.

    Builds via ``cls.__new__`` + ``object.__setattr__`` to bypass
    ``pydantic.main.__deepcopy__`` overhead.  Assumes the model has
    no ``PrivateAttr`` fields (sets ``__pydantic_private__`` to ``None``).
    """
    cls = type(self)
    m = cls.__new__(cls)
    if memo is None:
        memo = {}
    memo[id(self)] = m

    d = {key: _copy_field(value, memo) for key, value in self.__dict__.items()}

    object.__setattr__(m, "__dict__", d)
    extra = self.__pydantic_extra__
    object.__setattr__(m, "__pydantic_extra__", {} if not extra else dict(extra))
    object.__setattr__(m, "__pydantic_fields_set__", self.__pydantic_fields_set__.copy())
    object.__setattr__(m, "__pydantic_private__", None)

    return m


class NodeKind(str, Enum):
    """Board node categories."""

    SITE = "site"
    ROUTE = "route"


class TurnPhase(str, Enum):
    """Explicit turn and lifecycle phases for the game loop."""

    SETUP = "setup"
    DRAW = "draw"
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
    version: str = Field(min_length=1)
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

    def clone_fast(self) -> NodeState:
        m = NodeState.__new__(NodeState)
        d = {
            "node_id": self.node_id,
            "troop_slots": list(self.troop_slots),
            "spies": set(self.spies),
            "vp_tokens": self.vp_tokens,
        }
        object.__setattr__(m, "__dict__", d)
        object.__setattr__(m, "__pydantic_extra__", {})
        object.__setattr__(m, "__pydantic_fields_set__", self.__pydantic_fields_set__.copy())
        object.__setattr__(m, "__pydantic_private__", None)
        return m

    __deepcopy__ = _model_deepcopy_fields


class BoardState(BaseModel):
    """Mutable board-wide state."""

    nodes: dict[str, NodeState] = Field(default_factory=dict)

    def clone_fast(self) -> BoardState:
        m = BoardState.__new__(BoardState)
        d = {
            "nodes": {nid: node.clone_fast() for nid, node in self.nodes.items()},
        }
        object.__setattr__(m, "__dict__", d)
        object.__setattr__(m, "__pydantic_extra__", {})
        object.__setattr__(m, "__pydantic_fields_set__", self.__pydantic_fields_set__.copy())
        object.__setattr__(m, "__pydantic_private__", None)
        return m

    def clone_fast_shallow(self) -> BoardState:
        m = BoardState.__new__(BoardState)
        d = {"nodes": dict(self.nodes)}
        object.__setattr__(m, "__dict__", d)
        object.__setattr__(m, "__pydantic_extra__", {})
        object.__setattr__(m, "__pydantic_fields_set__", self.__pydantic_fields_set__.copy())
        object.__setattr__(m, "__pydantic_private__", None)
        return m

    __deepcopy__ = _model_deepcopy_fields


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

    def clone_fast(self) -> PlayerState:
        m = PlayerState.__new__(PlayerState)
        d = {
            "player_id": self.player_id,
            "deck": list(self.deck),
            "hand": list(self.hand),
            "discard_pile": list(self.discard_pile),
            "played_cards": list(self.played_cards),
            "inner_circle": list(self.inner_circle),
            "trophy_hall": list(self.trophy_hall),
            "barracks": self.barracks,
            "spies_available": self.spies_available,
            "vp_tokens": self.vp_tokens,
            "score": self.score,
        }
        object.__setattr__(m, "__dict__", d)
        object.__setattr__(m, "__pydantic_extra__", {})
        object.__setattr__(m, "__pydantic_fields_set__", self.__pydantic_fields_set__.copy())
        object.__setattr__(m, "__pydantic_private__", None)
        return m

    __deepcopy__ = _model_deepcopy_fields


class ResourcePool(BaseModel):
    """Transient resources that reset as turns progress."""

    power: int = Field(default=0, ge=0)
    influence: int = Field(default=0, ge=0)

    def clone_fast(self) -> ResourcePool:
        m = ResourcePool.__new__(ResourcePool)
        d = {
            "power": self.power,
            "influence": self.influence,
        }
        object.__setattr__(m, "__dict__", d)
        object.__setattr__(m, "__pydantic_extra__", {})
        object.__setattr__(m, "__pydantic_fields_set__", self.__pydantic_fields_set__.copy())
        object.__setattr__(m, "__pydantic_private__", None)
        return m

    __deepcopy__ = _model_deepcopy_fields


class MarketState(BaseModel):
    """Mutable market row and market deck state."""

    deck: list[str] = Field(default_factory=list)
    row: list[str] = Field(default_factory=list)
    discard_pile: list[str] = Field(default_factory=list)

    def clone_fast(self) -> MarketState:
        m = MarketState.__new__(MarketState)
        d = {
            "deck": list(self.deck),
            "row": list(self.row),
            "discard_pile": list(self.discard_pile),
        }
        object.__setattr__(m, "__dict__", d)
        object.__setattr__(m, "__pydantic_extra__", {})
        object.__setattr__(m, "__pydantic_fields_set__", self.__pydantic_fields_set__.copy())
        object.__setattr__(m, "__pydantic_private__", None)
        return m

    __deepcopy__ = _model_deepcopy_fields


class PendingAbilityState(BaseModel):
    """One unresolved paid ability on a played card."""

    card_id: str = Field(min_length=1)
    ability_key: str = Field(min_length=1)

    def clone_fast(self) -> PendingAbilityState:
        m = PendingAbilityState.__new__(PendingAbilityState)
        d = {
            "card_id": self.card_id,
            "ability_key": self.ability_key,
        }
        object.__setattr__(m, "__dict__", d)
        object.__setattr__(m, "__pydantic_extra__", {})
        object.__setattr__(m, "__pydantic_fields_set__", self.__pydantic_fields_set__.copy())
        object.__setattr__(m, "__pydantic_private__", None)
        return m

    __deepcopy__ = _model_deepcopy_fields


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

    def clone_fast(self) -> PendingPromotionState:
        m = PendingPromotionState.__new__(PendingPromotionState)
        d = {
            "card_id": self.card_id,
            "timing": self.timing,
            "optional": self.optional,
            "deferred_choice": self.deferred_choice,
            "source_card_id": self.source_card_id,
            "requires_another_played_card": self.requires_another_played_card,
            "required_aspect": self.required_aspect,
            "required_secondary_aspect": self.required_secondary_aspect,
            "repeat_while_targets": self.repeat_while_targets,
        }
        object.__setattr__(m, "__dict__", d)
        object.__setattr__(m, "__pydantic_extra__", {})
        object.__setattr__(m, "__pydantic_fields_set__", self.__pydantic_fields_set__.copy())
        object.__setattr__(m, "__pydantic_private__", None)
        return m

    __deepcopy__ = _model_deepcopy_fields


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
    action_repeat_limits: dict[str, int] = Field(default_factory=dict)

    def clone_fast(self) -> PendingGenericChoiceState:
        m = PendingGenericChoiceState.__new__(PendingGenericChoiceState)
        d = {
            "source_card_id": self.source_card_id,
            "execution_kind": self.execution_kind,
            "option_ids": list(self.option_ids),
            "selected_option_ids": list(self.selected_option_ids),
            "current_option_id": self.current_option_id,
            "current_actions": list(self.current_actions),
            "next_action_index": self.next_action_index,
            "awaiting_option": self.awaiting_option,
            "remaining_repeats": self.remaining_repeats,
            "allow_repeat": self.allow_repeat,
            "last_selection": dict(self.last_selection),
            "action_counters": dict(self.action_counters),
            "action_repeat_limits": dict(self.action_repeat_limits),
        }
        object.__setattr__(m, "__dict__", d)
        object.__setattr__(m, "__pydantic_extra__", {})
        object.__setattr__(m, "__pydantic_fields_set__", self.__pydantic_fields_set__.copy())
        object.__setattr__(m, "__pydantic_private__", None)
        return m

    __deepcopy__ = _model_deepcopy_fields


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
    setup_complete: set[str] = Field(default_factory=set)
    shuffle_seed: int = 0
    shuffle_count: int = Field(default=0, ge=0)

    def clone_fast(self) -> GameState:
        """Fast specialized deep copy — no type dispatch, no per-field function calls.

        See ``.kilo/plans/optimize-deepcopy-perf.md`` for the field
        classification and copy strategy.  Carries version-keyed cache
        entries so clones in the MCTS tree can reuse computed legal moves.
        """
        m = GameState.__new__(GameState)
        d = {
            "definition": self.definition,
            "board": self.board.clone_fast(),
            "players": {pid: ps.clone_fast() for pid, ps in self.players.items()},
            "turn_order": list(self.turn_order),
            "current_player_id": self.current_player_id,
            "phase": self.phase,
            "round_number": self.round_number,
            "resource_pool": self.resource_pool.clone_fast(),
            "market": self.market.clone_fast(),
            "final_scores": dict(self.final_scores),
            "pending_ability": self.pending_ability.clone_fast() if self.pending_ability is not None else None,
            "pending_immediate_promotions": [p.clone_fast() for p in self.pending_immediate_promotions],
            "pending_end_of_turn_promotions": [p.clone_fast() for p in self.pending_end_of_turn_promotions],
            "pending_generic_choice": self.pending_generic_choice.clone_fast() if self.pending_generic_choice is not None else None,
            "devour_pile": list(self.devour_pile),
            "setup_complete": set(self.setup_complete),
            "shuffle_seed": self.shuffle_seed,
            "shuffle_count": self.shuffle_count,
            "_version": self.__dict__.get("_version", 0),
            "_presence_cache": dict(pc) if (pc := self.__dict__.get("_presence_cache")) is not None else None,
            "_special_stack_cache": dict(ssc) if (ssc := self.__dict__.get("_special_stack_cache")) is not None else None,
            "_cached_legal_moves": self.__dict__.get("_cached_legal_moves"),
            "_cached_legal_moves_version": self.__dict__.get("_cached_legal_moves_version"),
            "_cached_indexed_moves": self.__dict__.get("_cached_indexed_moves"),
            "_cached_indexed_moves_version": self.__dict__.get("_cached_indexed_moves_version"),
        }
        object.__setattr__(m, "__dict__", d)
        object.__setattr__(m, "__pydantic_extra__", {})
        object.__setattr__(m, "__pydantic_fields_set__", self.__pydantic_fields_set__.copy())
        object.__setattr__(m, "__pydantic_private__", None)
        return m

    def __deepcopy__(self, memo: dict[int, Any] | None = None) -> GameState:
        result = self.clone_fast()
        if memo is not None:
            memo[id(self)] = result
        return result

    @model_validator(mode="after")
    def _validate_turn_owner(self) -> GameState:
        if self.current_player_id not in self.players:
            raise ValueError("current_player_id must be present in players")
        return self

    def _cow_clone(self) -> GameState:
        """Create a shallow copy-on-write clone of the game state.

        Mutable containers (board.nodes, players, market, resource_pool)
        are shared by reference.  Individual nodes and players are
        deep-copied lazily on first write via ``_cow_node`` /
        ``_cow_player`` accessors, avoiding the full O(all-nodes) clone
        cost for moves that touch only 1–2 locations.

        Exception: ``pending_generic_choice`` is eager-deep-copied because
        the generic-card resolver mutates it in-place at 21 sites without
        a COW accessor.
        """
        cls = type(self)
        m = cls.__new__(cls)
        d = {
            "definition": self.definition,
            "board": self.board.clone_fast_shallow(),
            "players": dict(self.players),
            "turn_order": list(self.turn_order) if isinstance(self.turn_order, list) else self.turn_order,
            "current_player_id": self.current_player_id,
            "phase": self.phase,
            "round_number": self.round_number,
            "resource_pool": self.resource_pool,
            "market": self.market,
            "final_scores": dict(self.final_scores) if self.final_scores else {},
            "pending_ability": self.pending_ability,
            "pending_immediate_promotions": list(self.pending_immediate_promotions),
            "pending_end_of_turn_promotions": list(self.pending_end_of_turn_promotions),
            "pending_generic_choice": self.pending_generic_choice.clone_fast() if self.pending_generic_choice is not None else None,
            "devour_pile": list(self.devour_pile),
            "setup_complete": set(self.setup_complete),
            "shuffle_seed": self.shuffle_seed,
            "shuffle_count": self.shuffle_count,
            "_presence_cache": dict(pc) if (pc := self.__dict__.get("_presence_cache")) is not None else None,
        }
        object.__setattr__(m, "__dict__", d)
        object.__setattr__(m, "__pydantic_extra__", {} if not self.__pydantic_extra__ else dict(self.__pydantic_extra__))
        object.__setattr__(m, "__pydantic_fields_set__", self.__pydantic_fields_set__.copy())
        object.__setattr__(m, "__pydantic_private__", None)
        object.__setattr__(m, "_cow_dirty", set())
        return m


# ── COW accessors ──────────────────────────────────────────────────────────


def _cow_node(state: GameState, node_id: str) -> NodeState:
    """Return a mutable NodeState, lazily copying from the shared reference."""
    node = state.board.nodes[node_id]
    dirty_key = ("n", node_id)
    if dirty_key not in state._cow_dirty:  # type: ignore[attr-defined]
        node = node.clone_fast()
        state.board.nodes[node_id] = node
        state._cow_dirty.add(dirty_key)  # type: ignore[attr-defined]
        state.__dict__["_presence_cache"] = None
    return node


def _cow_player(state: GameState, player_id: str) -> PlayerState:
    """Return a mutable PlayerState, lazily copying from the shared reference."""
    player = state.players[player_id]
    dirty_key = ("p", player_id)
    if dirty_key not in state._cow_dirty:  # type: ignore[attr-defined]
        player = player.clone_fast()
        state.players[player_id] = player
        state._cow_dirty.add(dirty_key)  # type: ignore[attr-defined]
    return player


def _cow_market_state(state: GameState) -> MarketState:
    """Return a mutable MarketState, lazily copying from the shared reference."""
    dirty_key = "market"
    if dirty_key not in state._cow_dirty:  # type: ignore[attr-defined]
        state.market = state.market.clone_fast()
        state._cow_dirty.add(dirty_key)  # type: ignore[attr-defined]
    return state.market


def _cow_resource_pool(state: GameState) -> ResourcePool:
    """Return a mutable ResourcePool, lazily copying from the shared reference."""
    dirty_key = "pool"
    if dirty_key not in state._cow_dirty:  # type: ignore[attr-defined]
        state.resource_pool = state.resource_pool.clone_fast()
        state._cow_dirty.add(dirty_key)  # type: ignore[attr-defined]
    return state.resource_pool


# ── index caches (identity-checked single-entry) ──────────────────────────
_board_index_cache_obj: BoardDefinition | None = None
_board_index_cache_result: dict[str, NodeDefinition] | None = None
_card_index_cache_obj: CardCatalog | None = None
_card_index_cache_result: dict[str, CardDefinition] | None = None


def board_index(board_definition: BoardDefinition) -> dict[str, NodeDefinition]:
    """Return board definitions by node id.

    Results are cached using object-identity (``is``) against the last
    ``BoardDefinition`` seen.  Since definitions are frozen and shared
    by reference across all state copies, the cache is invalidated only
    when a different definition object is passed — safe against ``id()``
    reuse after garbage collection.
    """
    global _board_index_cache_obj, _board_index_cache_result
    if _board_index_cache_obj is board_definition and _board_index_cache_result is not None:
        return _board_index_cache_result
    result = {node.node_id: node for node in board_definition.nodes}
    _board_index_cache_obj = board_definition
    _board_index_cache_result = result
    return result


def card_index(catalog: CardCatalog) -> dict[str, CardDefinition]:
    """Return card definitions by card id.

    Results are cached using object-identity (``is``) against the last
    ``CardCatalog`` seen.  Since catalogs are frozen and shared by
    reference across all state copies, the cache is invalidated only
    when a different catalog object is passed.
    """
    global _card_index_cache_obj, _card_index_cache_result
    if _card_index_cache_obj is catalog and _card_index_cache_result is not None:
        return _card_index_cache_result
    result = {card.card_id: card for card in catalog.cards}
    _card_index_cache_obj = catalog
    _card_index_cache_result = result
    return result


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


def _shuffle_deck(deck: list[str], seed: int, counter: int) -> list[str]:
    """Deterministic shuffle using seed and counter (same pattern as _reshuffle_discard_into_deck)."""
    rng = Random((seed << 16) ^ counter)
    result = list(deck)
    rng.shuffle(result)
    return result


def draw_cards(player_state: PlayerState, count: int, shuffle_seed: int, shuffle_counter: int) -> tuple[PlayerState, int]:
    """Draw cards, reshuffling discard into deck when needed.

    Returns (updated_state, new_shuffle_counter).
    """

    updated = player_state.model_copy(deep=True)
    counter = shuffle_counter
    for _ in range(count):
        if not updated.deck and updated.discard_pile:
            updated.deck = _shuffle_deck(updated.discard_pile, shuffle_seed, counter)
            updated.discard_pile = []
            counter += 1

        if not updated.deck:
            break

        updated.hand.append(updated.deck.pop())

    return updated, counter


def create_player_state(
    player_id: str,
    starter_cards: list[str],
    starting_troops: int,
    starting_spies: int,
    shuffle_seed: int,
    shuffle_counter: int,
) -> tuple[PlayerState, int]:
    """Build a player's initial runtime state from setup definitions.

    Returns (player_state, new_shuffle_counter).
    """

    deck = _shuffle_deck(starter_cards, shuffle_seed, shuffle_counter)
    counter = shuffle_counter + 1

    initial_state = PlayerState(
        player_id=player_id,
        deck=deck,
        barracks=starting_troops,
        spies_available=starting_spies,
    )
    return draw_cards(initial_state, count=5, shuffle_seed=shuffle_seed, shuffle_counter=counter)


def create_market_state(setup_definition: SetupDefinition, shuffle_seed: int, shuffle_counter: int) -> tuple[MarketState, int]:
    """Initialize market deck and visible row from setup definitions.

    Returns (market_state, new_shuffle_counter).
    """

    market_deck = expand_deck(setup_definition.market_deck)
    shuffled = _shuffle_deck(market_deck, shuffle_seed, shuffle_counter)
    counter = shuffle_counter + 1

    row_count = min(setup_definition.market_row_size, len(shuffled))
    row = [shuffled.pop() for _ in range(row_count)]

    return MarketState(deck=shuffled, row=row), counter


def build_initial_game_state(
    definition: GameDefinition,
    player_ids: Iterable[str],
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
    counter = 0

    for player_id in turn_order:
        deck = _shuffle_deck(starter_cards, shuffle_seed, counter)
        counter += 1
        players[player_id] = PlayerState(
            player_id=player_id,
            deck=deck,
            barracks=definition.default_player_troops,
            spies_available=definition.default_player_spies,
        )

    market_state, counter = create_market_state(definition.setup, shuffle_seed, counter)

    return GameState(
        definition=definition,
        board=create_board_state(definition.board),
        players=players,
        turn_order=turn_order,
        current_player_id=turn_order[0],
        phase=TurnPhase.SETUP,
        setup_complete=set(),
        market=market_state,
        shuffle_seed=shuffle_seed,
        shuffle_count=counter,
    )
