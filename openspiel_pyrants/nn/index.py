"""Stable card and board-node indices for the NN encoder.

Loaded once from ``data/cards/*.json`` and the board JSON. A catalog or board
change deliberately changes :data:`CARD_INDEX_SHA` / :data:`NODE_INDEX_SHA`,
which the encoder tests pin — so a data change forces an intentional index
version bump rather than silently shifting every observation.

No pyspiel import: only the standard library and data files.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CARDS_DIR = ROOT / "data" / "cards"
BOARD_PATH = ROOT / "data" / "boards" / "tyrants_of_the_underdark.json"

# cards_OCR.json and manifest.json are not card definitions (G14).
_NON_CARD_FILES = frozenset({"cards_OCR.json", "manifest.json", "catalog.json"})


def _load_card_ids() -> list[str]:
    ids: set[str] = set()
    for path in CARDS_DIR.glob("*.json"):
        if path.name in _NON_CARD_FILES:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        card_id = data.get("card_id") or data.get("id") or path.stem
        if card_id:
            ids.add(str(card_id))
    return sorted(ids)


def _load_nodes() -> list[dict]:
    board = json.loads(BOARD_PATH.read_text(encoding="utf-8"))
    return list(board.get("nodes", []))


def _load_string_values(key: str) -> list[str]:
    """Sorted set of every string *key*'s value across ``data/cards/*.json``.

    Derives the op and effect-kind vocabularies from the catalog instead of
    hand-typing them (F-026/NN-4): a card change that invents a new op forces a
    deliberate pin update rather than silently encoding it as "unknown".
    """
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


def _index_sha(ids: list[str]) -> str:
    return hashlib.sha256("\n".join(ids).encode("utf-8")).hexdigest()


CARD_IDS: list[str] = _load_card_ids()
"""125 card ids, sorted."""

UNKNOWN_CARD = "__unknown__"
"""Card id for an unrecognised/off-catalog card; gets the final index."""

NUM_CARD_IDS = len(CARD_IDS) + 1
CARD_INDEX_SHA = _index_sha(CARD_IDS)
CARD_ID_TO_INDEX: dict[str, int] = {cid: i for i, cid in enumerate(CARD_IDS)}
UNKNOWN_CARD_INDEX = len(CARD_IDS)

_NODES = _load_nodes()
NODE_IDS: list[str] = [str(n["node_id"]) for n in _NODES]
NODE_INDEX_SHA = _index_sha(NODE_IDS)
NODE_ID_TO_INDEX: dict[str, int] = {nid: i for i, nid in enumerate(NODE_IDS)}
NODE_IS_SITE: dict[str, bool] = {
    str(n["node_id"]): n.get("kind") == "site" for n in _NODES
}
NODE_TROOP_CAPACITY: dict[str, int] = {
    str(n["node_id"]): int(n.get("troop_capacity", 0)) for n in _NODES
}
NODE_ADJACENT: dict[str, tuple[str, ...]] = {
    str(n["node_id"]): tuple(str(x) for x in n.get("adjacent_to", ())) for n in _NODES
}

# Pending-generic op vocabulary: the engine emits the catalog's own op strings
# (engine_c/bindings/pending_context.py via ``sym_str(action.op)``), so the
# encoder must not hand-type a different list (NN-4). ``__option__`` is the
# "choose one" marker; ``__unknown__`` is the catch-all.
OP_IDS: list[str] = _load_string_values("op")
"""(17) sorted engine op strings found in the card catalog."""
OP_INDEX_SHA = _index_sha(OP_IDS)
OP_OPTION = "__option__"
OP_UNKNOWN = "__unknown__"
OP_SLOTS: tuple[str, ...] = (*OP_IDS, OP_OPTION, OP_UNKNOWN)

EFFECT_KINDS: list[str] = _load_string_values("effect_kind")
"""(13) sorted ``custom_effect`` kinds found in the card catalog."""
EFFECT_INDEX_SHA = _index_sha(EFFECT_KINDS)
EFFECT_UNKNOWN = "__unknown__"


def card_index(card_id: str | None) -> int:
    """Return the index for *card_id*, or :data:`UNKNOWN_CARD_INDEX`."""
    if card_id is None:
        return UNKNOWN_CARD_INDEX
    return CARD_ID_TO_INDEX.get(card_id, UNKNOWN_CARD_INDEX)


def node_index(node_id: str | None) -> int:
    """Return the index for *node_id*, or raise ``KeyError``."""
    if node_id is None:
        raise KeyError("node_id is None")
    return NODE_ID_TO_INDEX[node_id]
