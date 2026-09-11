"""T3.1 — card and node indices are stable and pinned."""

from __future__ import annotations

import json
from pathlib import Path

from openspiel_pyrants.nn.index import (
    CARD_ID_TO_INDEX,
    CARD_IDS,
    CARD_INDEX_SHA,
    NODE_IDS,
    NODE_INDEX_SHA,
    UNKNOWN_CARD_INDEX,
    card_index,
    node_index,
)

ROOT = Path(__file__).resolve().parents[2]
CARDS_DIR = ROOT / "data" / "cards"
_NON_CARD_FILES = {"cards_OCR.json", "manifest.json", "catalog.json"}

# A deliberate catalog/board change must update these pins (the whole point).
PINNED_CARD_INDEX_SHA = "436bc19340c6fc8770b3c57e0d04d5277ddf3c5574e62670b9ff5fd84835d996"
PINNED_NODE_INDEX_SHA = "72f2be9539dc0ab87ed306b636776959ccfbf31d0b65659c007d445001c0ec97"
PINNED_OP_INDEX_SHA = "eba3c74a99c41e3ff188bfc24b90ce4f60f9a73cd35ae754e327fc125f65784c"
PINNED_EFFECT_INDEX_SHA = "8060c6b0e13487744fdd17951aa4a0f2a2ca648420f2a0b6a20769df445fba09"


def _catalog_keys(key: str) -> list[str]:
    """Independent extraction of *key* values from ``data/cards/*.json``."""
    found: set[str] = set()

    def walk(node) -> None:
        if isinstance(node, dict):
            value = node.get(key)
            if isinstance(value, str):
                found.add(value)
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    for path in CARDS_DIR.glob("*.json"):
        if path.name in _NON_CARD_FILES:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, dict):
            walk(data)
    return sorted(found)



def test_card_and_node_index_are_stable() -> None:
    assert len(CARD_IDS) == 125
    assert sorted(CARD_IDS) == CARD_IDS
    assert UNKNOWN_CARD_INDEX == 125
    assert card_index("__no_such_card__") == 125
    assert card_index(None) == 125
    assert card_index(CARD_IDS[0]) == 0
    assert CARD_INDEX_SHA == PINNED_CARD_INDEX_SHA
    assert len(CARD_ID_TO_INDEX) == 125

    assert len(NODE_IDS) == 81
    assert len(set(NODE_IDS)) == 81
    assert node_index(NODE_IDS[0]) == 0
    assert NODE_INDEX_SHA == PINNED_NODE_INDEX_SHA


def test_op_vocabulary_is_the_catalog() -> None:
    """T2.2: the op / effect-kind vocabulary is derived from the catalog."""
    from openspiel_pyrants.nn.index import (
        EFFECT_INDEX_SHA,
        EFFECT_KINDS,
        OP_IDS,
        OP_INDEX_SHA,
        OP_SLOTS,
    )
    from openspiel_pyrants.nn.observation import op_index

    assert _catalog_keys("op") == OP_IDS
    assert len(OP_IDS) == 17
    assert OP_INDEX_SHA == PINNED_OP_INDEX_SHA

    assert _catalog_keys("effect_kind") == EFFECT_KINDS
    assert len(EFFECT_KINDS) == 13
    assert EFFECT_INDEX_SHA == PINNED_EFFECT_INDEX_SHA

    assert len(OP_SLOTS) == 19
    assert set(OP_SLOTS) == set(OP_IDS) | {"__option__", "__unknown__"}
    assert op_index("supplant_troop") != op_index("__no_such_op__")
    assert op_index(None, awaiting_option=True) == OP_SLOTS.index("__option__")
    assert op_index("__no_such_op__") == OP_SLOTS.index("__unknown__")
