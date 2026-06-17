"""Python-side enrichment for C-engine move labels.

The C engine cannot easily map ``ability_key`` → card name or resolve
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

_ENRICH_MOVES = frozenset({"activate_ability", "decline_ability", "resolve_generic"})


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


def enrich_label(move_type: str, raw_label: str, move_data: dict) -> str:
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

    if move_type == "resolve_generic":
        # If the C engine already produced a descriptive label, keep it.
        if raw_label.startswith("Devour ") or raw_label.startswith("Promote ") or \
           raw_label.startswith("Recruit ") or raw_label == "Skip (resign)":
            return raw_label
        target_id = move_data.get("target_id", "")
        action_id = move_data.get("action_id", "")
        card_id = target_id or action_id
        if card_id:
            name = _card_name(card_id)
            if name != card_id:
                return f"Resolve {name} choice"
        return "Resolve pending choice"

    return raw_label
