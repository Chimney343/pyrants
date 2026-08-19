"""Split the combined catalog.json into one JSON file per card.

Kept in the repo for provenance. The migration is irreversible in intent:
``data/cards/catalog.json`` is deleted and replaced by ``manifest.json`` plus
125 per-card files (``<card_id>.json``) that the engine assembles at runtime.

Run the *write* phase first (while ``catalog.json`` still exists), migrate the
code, validate, then run the *migrate/delete* phases:

    python scripts/split_catalog.py --write
    # ... migrate code, run test suite ...
    python scripts/split_catalog.py --migrate-scenarios
    git rm data/cards/catalog.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from game_setup.loaders import assemble_catalog_payload

CARDS_DIR = ROOT / "data" / "cards"
CATALOG_PATH = CARDS_DIR / "catalog.json"
MANIFEST_PATH = CARDS_DIR / "manifest.json"
SCENARIOS_DIR = ROOT / "data" / "scenarios"

EXPECTED_CARD_COUNT = 125
OLD_REFERENCE = '"data/cards/catalog.json"'
NEW_REFERENCE = '"data/cards"'


def _normalize_crlf(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def write_phase() -> None:
    raw = CATALOG_PATH.read_bytes()
    original_lf = _normalize_crlf(raw)

    payload = json.loads(original_lf.decode("utf-8"))
    if sorted(payload.keys()) != ["cards", "catalog_id"]:
        raise SystemExit(f"Unexpected top-level keys: {sorted(payload.keys())}")
    cards = payload["cards"]
    if not isinstance(cards, list):
        raise SystemExit("catalog.json cards is not a list")
    if len(cards) != EXPECTED_CARD_COUNT:
        raise SystemExit(f"Expected {EXPECTED_CARD_COUNT} cards, found {len(cards)}")

    card_ids = [card["card_id"] for card in cards]
    if len(card_ids) != len(set(card_ids)):
        raise SystemExit("Duplicate card_ids found in catalog.json")
    if card_ids != sorted(card_ids):
        raise SystemExit("card_ids are not sorted in catalog.json")

    MANIFEST_PATH.write_text(
        json.dumps({"catalog_id": payload["catalog_id"]}, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    for card in cards:
        card_id = card["card_id"]
        card_path = CARDS_DIR / f"{card_id}.json"
        card_path.write_text(
            json.dumps(card, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    reassembled = assemble_catalog_payload(CARDS_DIR)
    reassembled_text = json.dumps(reassembled, indent=2) + "\n"
    if reassembled_text.encode("utf-8") != original_lf:
        raise SystemExit(
            "Round-trip gate failed: reassembled per-card files differ from "
            "the original catalog.json after CRLF normalization."
        )
    print(f"Wrote manifest.json and {len(cards)} per-card files; round-trip gate passed.")


def migrate_scenarios() -> None:
    changed = 0
    for path in sorted(SCENARIOS_DIR.rglob("*.json")):
        text = path.read_text(encoding="utf-8")
        if OLD_REFERENCE not in text:
            continue
        new_text = text.replace(OLD_REFERENCE, NEW_REFERENCE)
        path.write_text(new_text, encoding="utf-8", newline="\n")
        changed += 1
    print(f"Migrated {changed} scenario files ({OLD_REFERENCE} -> {NEW_REFERENCE}).")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Write manifest + per-card files")
    parser.add_argument("--migrate-scenarios", action="store_true", help="Rewrite scenario catalog_path references")
    args = parser.parse_args()

    if not (args.write or args.migrate_scenarios):
        parser.error("provide --write and/or --migrate-scenarios")

    if args.write:
        write_phase()
    if args.migrate_scenarios:
        migrate_scenarios()


if __name__ == "__main__":
    main()
