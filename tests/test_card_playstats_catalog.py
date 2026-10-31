"""Tests for ``scripts.card_playstats.catalog`` — card/modal metadata loader."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.card_playstats.catalog import CardCatalog, CardInfo, load_catalog

ROOT = Path(__file__).resolve().parents[1]
CARD_DIR = ROOT / "data" / "cards"


def _write_card(card_dir: Path, card_id: str, payload: dict) -> None:
    card_dir.mkdir(parents=True, exist_ok=True)
    (card_dir / f"{card_id}.json").write_text(json.dumps(payload), encoding="utf-8")


def _modal_card(card_id: str, options: list[dict]) -> dict:
    return {
        "card_id": card_id,
        "name": card_id.title(),
        "execution_model": {"kind": "modal_choice", "options": options},
    }


def test_loads_plain_card_as_non_modal(tmp_path: Path) -> None:
    _write_card(tmp_path, "soldier", {"card_id": "soldier", "name": "Soldier", "execution_model": {"kind": "static"}})

    catalog = load_catalog(tmp_path)

    info = catalog.get("soldier")
    assert isinstance(info, CardInfo)
    assert info.is_modal is False
    assert info.option_ids == frozenset()
    assert catalog.is_modal("soldier") is False


def test_loads_modal_options(tmp_path: Path) -> None:
    _write_card(
        tmp_path,
        "advocate",
        _modal_card(
            "advocate",
            [
                {"option_id": "gain_influence", "actions": []},
                {"option_id": "promote_end_of_turn", "label": "Promote at end of turn", "actions": []},
            ],
        ),
    )

    catalog = load_catalog(tmp_path)

    info = catalog.get("advocate")
    assert info.is_modal is True
    assert info.option_ids == frozenset({"gain_influence", "promote_end_of_turn"})
    assert info.label_for("promote_end_of_turn") == "Promote at end of turn"
    assert info.label_for("gain_influence") == "gain_influence"


def test_repeat_choice_card_is_modal(tmp_path: Path) -> None:
    _write_card(
        tmp_path,
        "mummy_lord",
        _modal_card("mummy_lord", [{"option_id": "option_1"}, {"option_id": "option_2"}]),
    )
    payload = json.loads((tmp_path / "mummy_lord.json").read_text(encoding="utf-8"))
    payload["execution_model"]["kind"] = "repeat_choice"
    (tmp_path / "mummy_lord.json").write_text(json.dumps(payload), encoding="utf-8")

    catalog = load_catalog(tmp_path)

    assert catalog.is_modal("mummy_lord") is True
    assert catalog.option_ids("mummy_lord") == frozenset({"option_1", "option_2"})


def test_ignores_non_card_json_files(tmp_path: Path) -> None:
    _write_card(tmp_path, "soldier", {"card_id": "soldier", "execution_model": {"kind": "static"}})
    (tmp_path / "manifest.json").write_text(json.dumps({"cards": []}), encoding="utf-8")
    (tmp_path / "cards_OCR.json").write_text(json.dumps({"ocr": []}), encoding="utf-8")

    catalog = load_catalog(tmp_path)

    assert len(catalog) == 1
    assert "manifest" not in catalog
    assert "cards_OCR" not in catalog


def test_unknown_card_is_not_modal(tmp_path: Path) -> None:
    _write_card(tmp_path, "soldier", {"card_id": "soldier", "execution_model": {"kind": "static"}})

    catalog = load_catalog(tmp_path)

    assert catalog.get("missing") is None
    assert catalog.is_modal("missing") is False
    assert catalog.option_ids("missing") == frozenset()


def test_card_id_falls_back_to_filename_stem(tmp_path: Path) -> None:
    _write_card(tmp_path, "mystery", {"name": "Mystery", "execution_model": {"kind": "static"}})

    catalog = load_catalog(tmp_path)

    assert catalog.get("mystery") is not None


@pytest.mark.skipif(not CARD_DIR.exists(), reason="card catalog not present")
def test_real_catalog_counts_and_advocate() -> None:
    catalog = load_catalog(CARD_DIR)

    assert len(catalog) == 125
    assert len(catalog.modal_card_ids()) == 36
    assert catalog.option_ids("advocate") == frozenset({"gain_influence", "promote_end_of_turn"})
    assert catalog.is_modal("mummy_lord") is True
    assert catalog.is_modal("soldier") is False


@pytest.mark.skipif(not CARD_DIR.exists(), reason="card catalog not present")
def test_card_catalog_classmethod(tmp_path: Path) -> None:
    _write_card(tmp_path, "soldier", {"card_id": "soldier", "execution_model": {"kind": "static"}})

    catalog = CardCatalog.from_dir(tmp_path)

    assert "soldier" in catalog
