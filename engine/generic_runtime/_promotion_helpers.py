"""Promotion-related helpers used by selection generators and action appliers."""

from __future__ import annotations

from engine.errors import RuleViolationError
from engine.state import CardAction, CardDefinition


def _promote_requires_other_card(action: CardAction) -> bool:
    metadata_value = action.metadata.get("requires_another_played_card")
    if isinstance(metadata_value, bool):
        return metadata_value

    return "another" in action.source_fragment


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
