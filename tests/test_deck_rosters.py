"""Tests for the generated deck roster artifacts."""

from __future__ import annotations

from pathlib import Path

from game_setup.loaders import assemble_catalog_payload, load_deck_rosters

BASE_DIR = Path(__file__).resolve().parents[1]
CARD_PATH = BASE_DIR / "data" / "cards"
DECKS_DIR = BASE_DIR / "data" / "decks"


def _load_decks() -> list[dict[str, object]]:
    return load_deck_rosters(DECKS_DIR)


def test_deck_rosters_reference_catalog_cards_and_match_expected_totals() -> None:
    catalog_payload = assemble_catalog_payload(CARD_PATH)
    decks = _load_decks()

    cards = catalog_payload["cards"]
    assert isinstance(cards, list)
    assert isinstance(decks, list)

    catalog_card_ids = {card["card_id"] for card in cards}
    expected_totals = {
        "aberrations": 40,
        "dragon": 40,
        "drow": 40,
        "elementals": 40,
        "demons": 40,
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


def test_deck_rosters_capture_starter_and_kobold_dragon_assignment() -> None:
    decks = {deck["deck_id"]: deck for deck in _load_decks()}
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