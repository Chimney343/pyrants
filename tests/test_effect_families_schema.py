"""Schema validation tests for generated effect family registry."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

BASE_DIR = Path(__file__).resolve().parents[1]
SCHEMA_PATH = BASE_DIR / "data" / "cards" / "effect_families.schema.json"
REGISTRY_PATH = BASE_DIR / "data" / "cards" / "effect_families.json"


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    assert isinstance(payload, dict), f"Expected object JSON at {path}"
    return payload


def test_effect_families_json_matches_schema() -> None:
    schema = _load_json(SCHEMA_PATH)
    registry = _load_json(REGISTRY_PATH)

    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(registry), key=lambda err: list(err.path))

    assert not errors, "\n".join(
        [
            "effect_families.json failed schema validation:",
            *[
                f"- path={list(error.path)} message={error.message}"
                for error in errors
            ],
        ]
    )


def test_effect_families_header_counts_are_consistent() -> None:
    registry = _load_json(REGISTRY_PATH)
    families = registry["families"]

    assert registry["family_count"] == len(families)

    card_ids = {
        card_ref["card_id"]
        for family in families
        for card_ref in family["cards"]
    }
    assert registry["card_count"] == len(card_ids)
