"""Move payload models for the rules engine."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

HOUSE_GUARD_RECRUIT_SLOT = 100
PRIESTESS_RECRUIT_SLOT = 101
INSANE_OUTCAST_RECRUIT_SLOT = 102

SPECIAL_RECRUIT_SLOT_CARD_IDS: dict[int, str] = {
    HOUSE_GUARD_RECRUIT_SLOT: "house_guard",
    PRIESTESS_RECRUIT_SLOT: "priestess_of_lolth",
    INSANE_OUTCAST_RECRUIT_SLOT: "insane_outcast",
}


def special_recruit_card_id(market_slot: int) -> str | None:
    """Return the fixed card id for a special recruit slot, if any."""

    return SPECIAL_RECRUIT_SLOT_CARD_IDS.get(market_slot)


class MoveBase(BaseModel):
    """Shared move fields."""

    model_config = ConfigDict(extra="forbid")

    player_id: str = Field(min_length=1)


class PlayCardMove(MoveBase):
    """Play one card from hand."""

    move_type: Literal["play_card"] = "play_card"
    card_id: str = Field(min_length=1)
    hand_index: int | None = Field(default=None, ge=0)


class EndMainPhaseMove(MoveBase):
    """End the main phase and advance turn flow."""

    move_type: Literal["end_main_phase"] = "end_main_phase"


class ResolveEndOfTurnMove(MoveBase):
    """Run end-of-turn scoring and then transition to cleanup."""

    move_type: Literal["resolve_end_of_turn"] = "resolve_end_of_turn"


class ResolveCleanupMove(MoveBase):
    """Discard hand or played cards, draw a new hand, and pass turn."""

    move_type: Literal["resolve_cleanup"] = "resolve_cleanup"


class AssassinateMove(MoveBase):
    """Spend power to remove one enemy troop at a chosen node and slot."""

    move_type: Literal["assassinate"] = "assassinate"
    target_node_id: str = Field(min_length=1)
    target_slot_index: int = Field(ge=0)


class DeployMove(MoveBase):
    """Spend power to place one troop or gain fallback VP if barracks are empty."""

    move_type: Literal["deploy"] = "deploy"
    target_node_id: str = Field(min_length=1)
    troop_count: int = Field(default=1, gt=0)


class RecruitMove(MoveBase):
    """Spend influence to recruit one market card into the discard pile."""

    move_type: Literal["recruit"] = "recruit"
    market_slot: int = Field(ge=0)


class ReturnSpyMove(MoveBase):
    """Return one spy from a node to its owner's available supply."""

    move_type: Literal["return_spy"] = "return_spy"
    node_id: str = Field(min_length=1)
    spy_owner_id: str = Field(min_length=1)


class ActivateCardAbilityMove(MoveBase):
    """Activate one paid ability on a played card."""

    move_type: Literal["activate_card_ability"] = "activate_card_ability"
    card_id: str = Field(min_length=1)
    ability_key: str = Field(min_length=1)
    discard_hand_indices: list[int] = Field(default_factory=list)


class DeclineCardAbilityMove(MoveBase):
    """Choose not to pay for a pending card ability."""

    move_type: Literal["decline_card_ability"] = "decline_card_ability"
    card_id: str = Field(min_length=1)
    ability_key: str = Field(min_length=1)


class PromoteCardMove(MoveBase):
    """Resolve one optional promote instruction by moving the card to inner_circle."""

    move_type: Literal["promote_card"] = "promote_card"
    card_id: str = Field(min_length=1)


class SkipPromoteMove(MoveBase):
    """Resolve one optional promote instruction by declining the promotion."""

    move_type: Literal["skip_promote"] = "skip_promote"
    card_id: str = Field(min_length=1)


class ResolveGenericChoiceMove(MoveBase):
    """Resolve one pending generic-card option or target selection step."""

    move_type: Literal["resolve_generic_choice"] = "resolve_generic_choice"
    source_card_id: str = Field(min_length=1)
    option_id: str | None = None
    selection: dict[str, object] = Field(default_factory=dict)


class InitialPlacementMove(MoveBase):
    """Place one free troop on a site during setup phase."""

    move_type: Literal["initial_placement"] = "initial_placement"
    target_node_id: str = Field(min_length=1)


Move = Annotated[
    PlayCardMove
    | EndMainPhaseMove
    | ResolveEndOfTurnMove
    | ResolveCleanupMove
    | AssassinateMove
    | DeployMove
    | RecruitMove
    | ReturnSpyMove
    | ActivateCardAbilityMove
    | DeclineCardAbilityMove
    | PromoteCardMove
    | SkipPromoteMove
    | ResolveGenericChoiceMove
    | InitialPlacementMove,
    Field(discriminator="move_type"),
]


def move_type(move: Move) -> str:
    """Return the discriminator value for a move payload."""

    return move.move_type
