"""Scenario save/load helpers for persisting and restoring game states."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from engine.state import CardCatalog, GameState
from game_setup.loaders import resolve_catalog


def _json_dump(obj: Any, fp: Any, *, pretty: bool = False) -> None:
    """Serialize `obj` to `fp` as JSON.

    When ``pretty=False`` (default for batch generation), uses compact format.
    When ``pretty=True``, uses ``indent=2``.
    Tries ``orjson`` first when available for a speedup.
    """
    if not pretty:
        try:
            import orjson
            fp.write(orjson.dumps(obj).decode("utf-8"))
            return
        except ImportError:
            json.dump(obj, fp, separators=(",", ":"))
    else:
        try:
            import orjson
            fp.write(orjson.dumps(obj, option=orjson.OPT_INDENT_2).decode("utf-8"))
            return
        except ImportError:
            json.dump(obj, fp, indent=2)


class CatalogVersionMismatchError(ValueError):
    """Raised when a saved scenario's catalog version differs from the on-disk catalog."""

    def __init__(self, catalog_id: str, saved_version: str, current_version: str) -> None:
        super().__init__(
            f"Saved scenario was created with catalog '{catalog_id}' version "
            f"'{saved_version}', but the loaded catalog is version '{current_version}'. "
            "The card definitions have changed since this save was made. "
            "To proceed, either (a) revert data/cards/catalog.json to the saved version, "
            "or (b) regenerate the save file, or (c) pass force=True to override."
        )
        self.catalog_id = catalog_id
        self.saved_version = saved_version
        self.current_version = current_version


class ScenarioMetadata(BaseModel):
    """Metadata about a persisted scenario."""

    scenario_id: str = Field(min_length=1)
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    card_under_test: str | None = None
    source_board_id: str = ""
    source_catalog_id: str = ""
    source_catalog_version: str = ""
    source_setup_id: str = ""
    move_count: int = 0
    is_terminal: bool = False


class Scenario(BaseModel):
    """A persisted game scenario with metadata and state payload."""

    metadata: ScenarioMetadata
    state_payload: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_game_state(
        cls,
        state: GameState,
        *,
        scenario_id: str = "",
        description: str = "",
        tags: list[str] | None = None,
        card_under_test: str | None = None,
        move_count: int = 0,
        is_terminal: bool = False,
        catalog_version: str | None = None,
    ) -> Scenario:
        """Build a Scenario from an existing GameState with optional metadata."""
        return cls(
            metadata=ScenarioMetadata(
                scenario_id=scenario_id or state.definition.definition_id,
                description=description,
                tags=tags or [],
                card_under_test=card_under_test,
                source_board_id=state.definition.board.board_id,
                source_catalog_id=state.definition.catalog.catalog_id,
                source_catalog_version=catalog_version or state.definition.catalog.version,
                source_setup_id=state.definition.setup.setup_id,
                move_count=move_count,
                is_terminal=is_terminal,
            ),
            state_payload=state.model_dump(mode="json", exclude={"definition": {"catalog": True}}),
        )

    def to_game_state(
        self,
        *,
        catalog_registry: dict[str, CardCatalog],
        force: bool = False,
    ) -> GameState:
        """Reconstruct a validated GameState from the stored payload."""
        payload: dict[str, Any] = copy.deepcopy(self.state_payload)
        catalog_id = self.metadata.source_catalog_id
        saved_version = self.metadata.source_catalog_version

        if "catalog" in payload.get("definition", {}):
            raise ValueError(
                "Legacy save format detected: state_payload.definition.catalog is embedded. "
                "This save was created before the catalog-deduplication refactor. "
                "Regenerate the save file or use a pre-refactor version of pyrants."
            )

        catalog = resolve_catalog(catalog_id, catalog_registry)
        if not force and saved_version and catalog.version != saved_version:
            raise CatalogVersionMismatchError(catalog_id, saved_version, catalog.version)
        payload.setdefault("definition", {})["catalog"] = catalog.model_dump(mode="json")
        return GameState.model_validate(payload)


def save_scenario(scenario: Scenario, path: Path, *, pretty: bool = True) -> None:
    """Persist a Scenario to a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = scenario.model_dump(mode="json")
    with path.open("w", encoding="utf-8") as handle:
        _json_dump(payload, handle, pretty=pretty)
        handle.write("\n")


def load_scenario(path: Path) -> Scenario:
    """Load and validate a Scenario from a JSON file."""
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return Scenario.model_validate(payload)


def load_game_state_from_scenario(
    path: Path,
    *,
    catalog_registry: dict[str, CardCatalog],
    force: bool = False,
) -> GameState:
    """Load a scenario and return its reconstructed GameState."""
    scenario = load_scenario(path)
    return scenario.to_game_state(catalog_registry=catalog_registry, force=force)


def save_game_state(
    state: GameState,
    path: Path,
    *,
    scenario_id: str = "",
    description: str = "",
    tags: list[str] | None = None,
    card_under_test: str | None = None,
    move_count: int = 0,
    is_terminal: bool = False,
    catalog_version: str | None = None,
    pretty: bool = True,
) -> Scenario:
    """Convenience: create a Scenario from a GameState and persist it."""
    scenario = Scenario.from_game_state(
        state,
        scenario_id=scenario_id,
        description=description,
        tags=tags,
        card_under_test=card_under_test,
        move_count=move_count,
        is_terminal=is_terminal,
        catalog_version=catalog_version,
    )
    save_scenario(scenario, path, pretty=pretty)
    return scenario
