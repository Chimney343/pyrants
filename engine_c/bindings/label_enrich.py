"""Python-side enrichment for C-engine move labels.

The C engine cannot easily map ``ability_key`` -> card name or resolve
``MOVE_RESOLVE_GENERIC`` labels because the card-name mapping lives in
``data/cards/catalog.json``. This module enriches labels after the C
engine produces a raw label.

Usage:
    from engine_c.bindings.label_enrich import enrich_label
    final = enrich_label("activate_ability", "Activate ambush",
                         {"card_id": "shade_enforcer", "ability_key": "ambush"})
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_ENRICH_MOVES = frozenset({"activate_ability", "decline_ability", "resolve_generic", "promote_card"})

_OP_DESCRIPTIONS = {
    "place_spy": "Place spy",
    "assassinate_troop": "Assassinate troop",
    "supplant_troop": "Replace troop",
    "deploy_troops": "Deploy troops",
    "return_spy": "Return spy",
    "return_unit": "Return unit",
    "move_troop": "Move troop",
    "draw_cards": "Draw cards",
    "recruit_card": "Recruit card",
    "promote_card": "Promote card",
    "devour": "Devour",
    "devour_cost": "Devour (cost)",
    "force_discard": "Force discard",
    "play_card": "Play a card",
}

_FILTER_DESCRIPTIONS = {
    "white_troop_only": "white",
}


def _load_catalog() -> dict[str, dict]:
    catalog_path = Path(__file__).resolve().parent.parent.parent / "data" / "cards" / "catalog.json"
    with open(catalog_path, encoding="utf-8") as f:
        raw = json.load(f)
    cards = raw.get("cards", raw) if isinstance(raw, dict) else raw
    result: dict[str, dict] = {}
    for entry in cards:
        cid = entry.get("card_id", "")
        if cid:
            result[cid] = entry
    return result


@lru_cache(maxsize=1)
def _catalog_cache() -> dict[str, dict]:
    return _load_catalog()


def _card_name(card_id: str) -> str:
    cat = _catalog_cache()
    entry = cat.get(card_id)
    if entry:
        return entry.get("name", card_id)
    return card_id


def _describe_action_by_op(op: str, quantity: dict | None = None) -> str:
    base = _OP_DESCRIPTIONS.get(op, op.replace("_", " ").title())
    if quantity and isinstance(quantity, dict) and quantity.get("kind") == "fixed" and quantity.get("value", 0) > 1:
        return f"{base} (x{quantity['value']})"
    return base


def _lookup_card_action(card_entry: dict | None, action_id: str) -> dict | None:
    if not card_entry or not action_id:
        return None
    exec_model = card_entry.get("execution_model")
    if not exec_model:
        return None
    for act in exec_model.get("actions", []):
        if act.get("action_id") == action_id:
            return act
    for opt in exec_model.get("options", []):
        for act in opt.get("actions", []):
            if act.get("action_id") == action_id:
                return act
    return None


def _describe_single_action(action: dict, *, spy_count: int = 0) -> str:
    desc = _describe_action_by_op(action.get("op", ""), action.get("quantity"))
    filters = action.get("filters", [])
    if isinstance(filters, list):
        for f_val in filters:
            mapped = _FILTER_DESCRIPTIONS.get(f_val)
            if mapped:
                desc = desc.replace(" troop", f" {mapped} troop", 1)
    meta = action.get("metadata")
    if isinstance(meta, dict):
        count_from = meta.get("count_from", "")
        if count_from == "spies_on_board" and spy_count > 0:
            dc = f"{spy_count} card" if spy_count == 1 else f"{spy_count} cards"
            ds = f"{spy_count} spy" if spy_count == 1 else f"{spy_count} spies"
            return f"Draw {dc} (from {ds} on board)"
        elif count_from:
            source = count_from.replace("_", " ")
            desc = f"{desc} (from {source})"
    return desc


def _describe_option(option: dict, *, spy_count: int = 0) -> str:
    actions = option.get("actions", [])
    if not actions:
        return "unknown"
    # Compress identical actions: "Place spy (x2)" not "Place spy and Place spy"
    if len(actions) > 1:
        first_op = actions[0].get("op", "")
        first_qty = actions[0].get("quantity")
        all_same = all(
            a.get("op", "") == first_op and a.get("quantity") == first_qty
            for a in actions
        )
        if all_same:
            desc = _describe_single_action(actions[0], spy_count=spy_count)
            return f"{desc} (x{len(actions)})"
    parts = [_describe_single_action(a, spy_count=spy_count) for a in actions]
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return f"{', '.join(parts[:-1])}, and {parts[-1]}"


def _humanize_action(action_id: str) -> str:
    words = action_id.replace("_", " ").strip()
    if words:
        return words[0].upper() + words[1:]
    return action_id


def _format_action_with_target(card_name: str, action_desc: str, target_id: str) -> str:
    name = _card_name(target_id)
    if name != target_id:
        return f"{card_name}: {action_desc} {name}"
    humanized = _humanize_action(target_id)
    return f"{card_name}: {action_desc} at {humanized}"


def _card_id_from_data(move_data: dict) -> str:
    target_id = move_data.get("target_id", "")
    if target_id:
        name = _card_name(target_id)
        if name != target_id:
            return name
    action_id = move_data.get("action_id", "")
    if action_id:
        name = _card_name(action_id)
        if name != action_id:
            return name
    return ""


def enrich_label(move_type: str, raw_label: str, move_data: dict, *, source_card_id: str = "", card_action_id: str = "", is_option_choice: bool = False, player_spy_count: int = 0, promotion_source_card_id: str = "") -> str:
    if move_type not in _ENRICH_MOVES:
        return raw_label

    if move_type == "activate_ability":
        card_id = move_data.get("card_id", "")
        if card_id:
            name = _card_name(card_id)
            return f"Activate {name}'s ability"
        return raw_label

    if move_type == "decline_ability":
        card_id = move_data.get("card_id", "")
        if card_id:
            name = _card_name(card_id)
            return f"Decline {name}'s ability"
        return raw_label

    if move_type == "promote_card":
        card_id = move_data.get("card_id", "")
        if card_id:
            target_name = _card_name(card_id)
            if promotion_source_card_id:
                source_name = _card_name(promotion_source_card_id)
                if source_name != promotion_source_card_id:
                    return f"{source_name}: Promote card {target_name}"
            return f"Promote {target_name}"
        return raw_label

    if move_type == "resolve_generic":
        source_card_id = source_card_id or ""
        catalog = _catalog_cache()
        card_entry = catalog.get(source_card_id) if source_card_id else None
        action_id = move_data.get("action_id", "")
        target_id = move_data.get("target_id", "")

        # Skip moves have no action_id; label them with the current action's description.
        if not action_id:
            card_name = (card_entry.get("name") if card_entry else source_card_id) or source_card_id
            card_action = _lookup_card_action(card_entry, card_action_id) if card_action_id else None
            if card_action:
                desc = _describe_single_action(card_action)
                return f"Skip {desc} for {card_name}"
            return f"Skip for {card_name}"

        # Level 1: Describe using the card's execution model from the catalog.
        # When is_option_choice=True, the move's action_id is the option_id.
        # When is_option_choice=False, card_action_id (from state) is the
        #   card's real action_id; the move's action_id is a selection target.
        lookup_id = action_id if is_option_choice else card_action_id
        target_display = target_id or (action_id if not is_option_choice else "")

        if card_entry and lookup_id:
            card_name = card_entry.get("name", source_card_id)
            exec_model = card_entry.get("execution_model")
            if exec_model:
                options = exec_model.get("options", [])

                # 1a: option choice -> match option_id
                for opt in options:
                    if opt.get("option_id") == lookup_id:
                        desc = _describe_option(opt, spy_count=player_spy_count)
                        return f"{card_name}: {desc}"

                # 1b: target selection -> match the card's action_id, append target
                for opt in options:
                    for act in opt.get("actions", []):
                        if act.get("action_id") == lookup_id:
                            if act.get("op") in ("assassinate_troop", "supplant_troop", "move_troop"):
                                return raw_label
                            desc = _describe_single_action(act, spy_count=player_spy_count)
                            if target_display:
                                return _format_action_with_target(card_name, desc, target_display)
                            return f"{card_name}: {desc}"

                # 1c: sequence-type execution model -> flat actions directly on
                #     exec_model, not nested inside options (non-modal cards).
                flat_actions = exec_model.get("actions", [])
                for act in flat_actions:
                    if act.get("action_id") == lookup_id:
                        if act.get("op") in ("assassinate_troop", "supplant_troop", "move_troop"):
                            return raw_label
                        desc = _describe_single_action(act, spy_count=player_spy_count)
                        if target_display:
                            return _format_action_with_target(card_name, desc, target_display)
                        return f"{card_name}: {desc}"

        # Level 2: target_id or action_id resolved through catalog as a card name
        name = _card_id_from_data(move_data)
        if name:
            return f"Resolve {name} choice"

        # Level 3: source_card_id resolved through catalog as a card name
        if source_card_id:
            name = _card_name(source_card_id)
            if name != source_card_id:
                return f"Resolve {name} choice"

        # Level 4: humanize the raw action_id
        if action_id:
            humanized = _humanize_action(action_id)
            return f"Resolve {humanized}"

        # Level 5: absolute fallback
        return "Resolve pending choice"

    return raw_label
