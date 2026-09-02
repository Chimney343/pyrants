"""Load and validate external board and card setup data."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from game_setup.board_package import (
    BoardLayoutDefinition,
    BoardPackageDefinition,
    make_default_layout,
)
from game_setup.types import BoardDefinition, CardCatalog, GameDefinition, SetupDefinition

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CARDS_DIR = ROOT / "data" / "cards"


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        loaded = json.load(handle)
    if not isinstance(loaded, dict):
        raise ValueError(f"JSON file must contain an object at top level: {path}")
    return loaded


def _read_json_any(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def assemble_catalog_payload(cards_path: Path) -> dict[str, Any]:
    """Assemble a catalog payload from a card directory or a legacy file.

    A directory is treated as a card directory only when it contains a
    ``manifest.json`` with a ``catalog_id``. Every ``*.json`` file in the
    directory that is a JSON object with a string ``card_id`` key is treated
    as one card; everything else (``manifest.json``, ``cards_OCR.json``, a
    legacy combined ``catalog.json``) is skipped. Card order is the sorted
    filename order.

    A file argument is the legacy single-file catalog and is read as-is.
    """
    cards_path = Path(cards_path)
    if cards_path.is_dir():
        manifest_path = cards_path / "manifest.json"
        if not manifest_path.is_file():
            raise ValueError(
                f"Card directory {cards_path} has no manifest.json; "
                "expected a catalog manifest with a catalog_id"
            )
        manifest = _read_json(manifest_path)
        catalog_id = manifest.get("catalog_id")
        if not isinstance(catalog_id, str) or not catalog_id:
            raise ValueError(f"manifest.json in {cards_path} has no catalog_id")

        cards: list[dict[str, Any]] = []
        for path in sorted(cards_path.glob("*.json")):
            if path.name == "manifest.json":
                continue
            try:
                data = _read_json_any(path)
            except (OSError, ValueError):
                continue
            if isinstance(data, dict) and isinstance(data.get("card_id"), str):
                cards.append(data)
        return {"catalog_id": catalog_id, "cards": cards}

    return _read_json(cards_path)


@lru_cache(maxsize=None)
def assemble_catalog_text(cards_path: Path) -> str:
    """Return the assembled catalog as an indented JSON string (LF-newline)."""
    return json.dumps(assemble_catalog_payload(cards_path), indent=2) + "\n"


@lru_cache(maxsize=4)
def load_deck_rosters(decks_dir: Path) -> list[dict[str, Any]]:
    """Load deck roster dicts from every JSON file in a directory.

    Each file should be a single deck object with ``deck_id``, ``kind``,
    and ``entries`` keys.  Files missing those keys are silently skipped
    (e.g. base_setup.json).
    """
    decks: list[dict[str, Any]] = []
    if not decks_dir.is_dir():
        return decks
    for path in sorted(decks_dir.glob("*.json")):
        deck = _read_json(path)
        if (
            isinstance(deck.get("deck_id"), str)
            and isinstance(deck.get("kind"), str)
            and isinstance(deck.get("entries"), list)
        ):
            decks.append(deck)
    return decks


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def build_game_definition_from_dicts(
    board_data: dict[str, Any],
    card_data: dict[str, Any],
    setup_data: dict[str, Any],
    definition_id: str = "base_game",
) -> GameDefinition:
    """Validate external payloads and build an immutable game definition."""

    board_definition = BoardDefinition.model_validate(board_data)
    card_catalog = CardCatalog.model_validate(card_data)
    setup_definition = SetupDefinition.model_validate(setup_data)

    return GameDefinition(
        definition_id=definition_id,
        board=board_definition,
        catalog=card_catalog,
        setup=setup_definition,
    )


def build_game_definition_from_files(
    board_path: Path,
    card_path: Path,
    setup_path: Path,
    definition_id: str = "base_game",
) -> GameDefinition:
    """Load definitions from files and build an immutable game definition.

    *card_path* is dir-or-file: a card directory (assembled via
    :func:`assemble_catalog_payload`) or a legacy single-file catalog.
    """

    return build_game_definition_from_dicts(
        board_data=_read_json(board_path),
        card_data=assemble_catalog_payload(card_path),
        setup_data=_read_json(setup_path),
        definition_id=definition_id,
    )


def build_board_package_from_dicts(
    board_data: dict[str, Any],
    layout_data: dict[str, Any] | None,
    layout_id: str | None = None,
) -> BoardPackageDefinition:
    """Validate topology and visual layout into one editor-facing package."""

    board_definition = BoardDefinition.model_validate(board_data)
    layout_definition = (
        BoardLayoutDefinition.model_validate(layout_data)
        if layout_data is not None
        else make_default_layout(board_definition, layout_id=layout_id)
    )
    return BoardPackageDefinition(board=board_definition, layout=layout_definition)


def build_board_package_from_files(
    board_path: Path,
    layout_path: Path | None,
    layout_id: str | None = None,
) -> BoardPackageDefinition:
    """Load board topology and optional layout from JSON files."""

    board_data = _read_json(board_path)
    layout_data = _read_json(layout_path) if layout_path is not None else None
    return build_board_package_from_dicts(
        board_data=board_data,
        layout_data=layout_data,
        layout_id=layout_id,
    )


def save_board_package_to_files(
    package: BoardPackageDefinition,
    board_path: Path,
    layout_path: Path,
) -> None:
    """Persist normalized board and layout payloads to JSON files."""

    _write_json(board_path, package.board.model_dump(mode="json"))
    _write_json(layout_path, package.layout.model_dump(mode="json"))


def load_card_catalog(card_path: Path) -> CardCatalog:
    """Load a card catalog from a directory (assembled) or a legacy file."""
    return CardCatalog.model_validate(assemble_catalog_payload(card_path))


def build_catalog_registry(cards_dir: Path) -> dict[str, CardCatalog]:
    """Load card catalogs keyed by catalog_id.

    A directory containing ``manifest.json`` (with a ``catalog_id``) is
    treated as one catalog assembled from its per-card files. Otherwise every
    ``*.json`` file is parsed as a standalone ``CardCatalog``; files that fail
    validation are silently skipped.
    """
    registry: dict[str, CardCatalog] = {}
    if not cards_dir.is_dir():
        return registry
    if (cards_dir / "manifest.json").is_file():
        catalog = CardCatalog.model_validate(assemble_catalog_payload(cards_dir))
        registry[catalog.catalog_id] = catalog
        return registry
    for path in sorted(cards_dir.glob("*.json")):
        try:
            catalog = CardCatalog.model_validate(_read_json(path))
        except Exception:
            continue
        registry[catalog.catalog_id] = catalog
    return registry


def resolve_catalog(catalog_id: str, registry: dict[str, CardCatalog]) -> CardCatalog:
    """Return the catalog for a given id; raise with a clear message if missing."""
    if catalog_id not in registry:
        available = ", ".join(sorted(registry.keys())) if registry else "(none)"
        raise ValueError(
            f"Catalog '{catalog_id}' not found in registry. Available ids: {available}"
        )
    return registry[catalog_id]


def default_catalog_registry() -> dict[str, CardCatalog]:
    """Build a registry from the project-default data/cards/ directory."""
    return build_catalog_registry(DEFAULT_CARDS_DIR)
