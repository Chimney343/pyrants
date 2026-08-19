"""Whole-catalog assembly tests: Python assembler -> C engine path.

These lock in the per-card catalog layout (data/cards/*.json + manifest.json)
and the production path that assembles the catalog in Python and hands the
JSON string to the C engine via engine_load_definition_json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from game_setup.loaders import assemble_catalog_payload, assemble_catalog_text  # noqa: E402
from game_setup.types import CardCatalog  # noqa: E402

from engine_c.bindings.ce_api import CEngine  # noqa: E402
from engine_c.bindings.engine_bindings import _lib  # noqa: E402
from engine_c.bindings.session import CSession  # noqa: E402

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
CARDS_DIR = DATA_DIR / "cards"
BOARD_PATH = DATA_DIR / "boards" / "tyrants_of_the_underdark.json"
SETUP_PATH = DATA_DIR / "decks" / "base_setup.json"

EXPECTED_CARD_COUNT = 125


def test_assemble_catalog_payload_matches_contract() -> None:
    payload = assemble_catalog_payload(CARDS_DIR)
    assert payload["catalog_id"] == "base_catalog"
    assert isinstance(payload["cards"], list)
    assert len(payload["cards"]) == EXPECTED_CARD_COUNT

    card_ids = [card["card_id"] for card in payload["cards"]]
    assert len(card_ids) == len(set(card_ids))
    assert card_ids == sorted(card_ids)

    # Must validate as a CardCatalog (the Pydantic model the Python side uses).
    catalog = CardCatalog.model_validate(payload)
    assert catalog.catalog_id == "base_catalog"
    assert len(catalog.cards) == EXPECTED_CARD_COUNT


def test_assemble_catalog_text_formatting_contract() -> None:
    payload = assemble_catalog_payload(CARDS_DIR)
    text = assemble_catalog_text(CARDS_DIR)
    assert text == json.dumps(payload, indent=2) + "\n"


def test_assemble_catalog_skips_non_card_json() -> None:
    payload = assemble_catalog_payload(CARDS_DIR)
    ids = {card["card_id"] for card in payload["cards"]}
    # cards_OCR.json is a top-level array; manifest.json has catalog_id, not card_id.
    assert len(payload["cards"]) == EXPECTED_CARD_COUNT
    assert "catalog_id" not in ids


def test_assemble_catalog_dir_requires_manifest(tmp_path: Path) -> None:
    import pytest

    (tmp_path / "not_a_card.json").write_text('{"foo": 1}', encoding="utf-8")
    with pytest.raises(ValueError, match="manifest.json"):
        assemble_catalog_payload(tmp_path)


def test_assemble_catalog_accepts_legacy_single_file(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy_catalog.json"
    legacy.write_text(
        json.dumps({"catalog_id": "base_catalog", "cards": []}, indent=2) + "\n",
        encoding="utf-8",
    )
    payload = assemble_catalog_payload(legacy)
    assert payload == {"catalog_id": "base_catalog", "cards": []}


def test_engine_load_definition_json_loads_whole_catalog() -> None:
    text = assemble_catalog_text(CARDS_DIR)
    arena = _lib.arena_create(16 * 1024 * 1024)
    assert arena
    try:
        def_ptr = _lib.engine_load_definition_json(
            text.encode(), str(BOARD_PATH).encode(), str(SETUP_PATH).encode(), arena
        )
        assert def_ptr, "engine_load_definition_json returned NULL"
        cat = def_ptr.contents.catalog
        assert cat.card_count == EXPECTED_CARD_COUNT
        for i in range(cat.card_count):
            assert cat.cards[i].card_id != 0
    finally:
        _lib.arena_destroy(arena)


def test_cengine_default_initialize_smoke() -> None:
    engine = CEngine()
    engine.initialize()
    state = engine.create_game(["p1", "p2"])
    assert state.player_count == 2
    engine.destroy(state)


def test_load_legacy_scenario_ignores_embedded_catalog_path() -> None:
    engine = CEngine()
    engine.initialize()
    scenario = DATA_DIR / "scenarios" / "cards" / "blackguard_seed_0.json"
    assert scenario.exists()
    session = CSession.load(str(scenario), engine)
    assert session.state.player_count == 4
