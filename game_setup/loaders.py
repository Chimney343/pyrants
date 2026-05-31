"""Load and validate external board and card setup data."""

from __future__ import annotations

import json
from pathlib import Path
from random import Random
from typing import Any, Iterable

from game_setup.board_package import (
    BoardLayoutDefinition,
    BoardPackageDefinition,
    make_default_layout,
)
from engine.state import (
    BoardDefinition,
    CardCatalog,
    GameDefinition,
    SetupDefinition,
    build_initial_game_state,
)


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        loaded = json.load(handle)
    if not isinstance(loaded, dict):
        raise ValueError(f"JSON file must contain an object at top level: {path}")
    return loaded


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
    """Load definitions from JSON files and build an immutable game definition."""

    return build_game_definition_from_dicts(
        board_data=_read_json(board_path),
        card_data=_read_json(card_path),
        setup_data=_read_json(setup_path),
        definition_id=definition_id,
    )


def create_game_state_from_files(
    board_path: Path,
    card_path: Path,
    setup_path: Path,
    player_ids: Iterable[str],
    definition_id: str = "base_game",
    seed: int | None = None,
):
    """Build immutable definitions from files and return a seeded initial game state."""

    definition = build_game_definition_from_files(
        board_path=board_path,
        card_path=card_path,
        setup_path=setup_path,
        definition_id=definition_id,
    )
    rng = Random(seed)
    return build_initial_game_state(
        definition,
        player_ids=player_ids,
        rng=rng,
        shuffle_seed=seed or 0,
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
