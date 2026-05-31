"""Tests for the generated first-deck roster artifact."""

from __future__ import annotations

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
CARD_PATH = BASE_DIR / "data" / "cards" / "catalog.json"
ROSTER_PATH = BASE_DIR / "data" / "decks" / "first_deck_rosters.json"


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_first_deck_rosters_reference_catalog_cards_and_match_expected_totals() -> None:
    catalog_payload = _load_json(CARD_PATH)
    roster_payload = _load_json(ROSTER_PATH)

    cards = catalog_payload["cards"]
    decks = roster_payload["decks"]
    assert isinstance(cards, list)
    assert isinstance(decks, list)

    catalog_card_ids = {card["card_id"] for card in cards}
    expected_totals = {
        "aberrations": 40,
        "dragon": 40,
        "drow": 40,
        "elementals": 40,
        "fungus": 40,
        "undead": 40,
        "insane_outcast": 30,
        "house_guard": 15,
        "priestess_of_lolth": 15,
        "starter_deck": 10,
    }

    assert {deck["deck_id"] for deck in decks} == set(expected_totals)

    for deck in decks:
        entries = deck["entries"]
        assert isinstance(entries, list)
        assert entries
        assert sum(entry["count"] for entry in entries) == expected_totals[deck["deck_id"]]
        assert all(entry["card_id"] in catalog_card_ids for entry in entries)


def test_first_deck_rosters_capture_starter_and_kobold_dragon_assignment() -> None:
    roster_payload = _load_json(ROSTER_PATH)
    decks = {deck["deck_id"]: deck for deck in roster_payload["decks"]}
    starter_deck = decks["starter_deck"]

    assert starter_deck["kind"] == "starter_deck"
    assert starter_deck["per_player"] is True
    assert starter_deck["entries"] == [
        {"card_id": "noble", "count": 7},
        {"card_id": "soldier", "count": 3},
    ]

    dragon_entries = {entry["card_id"]: entry["count"] for entry in decks["dragon"]["entries"]}
    drow_entries = {entry["card_id"]: entry["count"] for entry in decks["drow"]["entries"]}
    assert dragon_entries["kobold"] == 3
    assert "kobold" not in drow_entries

    assert roster_payload["normalizations"] == []