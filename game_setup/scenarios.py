"""Scenario save/load helpers for persisting and restoring game states."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from engine.state import GameState


class ScenarioMetadata(BaseModel):
    """Metadata about a persisted scenario."""

    scenario_id: str = Field(min_length=1)
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    card_under_test: str | None = None
    source_board_id: str = ""
    source_catalog_id: str = ""
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
                source_setup_id=state.definition.setup.setup_id,
                move_count=move_count,
                is_terminal=is_terminal,
            ),
            state_payload=state.model_dump(mode="json"),
        )

    def to_game_state(self) -> GameState:
        """Reconstruct a validated GameState from the stored payload."""
        return GameState.model_validate(self.state_payload)


def save_scenario(scenario: Scenario, path: Path) -> None:
    """Persist a Scenario to a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = scenario.model_dump(mode="json")
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def load_scenario(path: Path) -> Scenario:
    """Load and validate a Scenario from a JSON file."""
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return Scenario.model_validate(payload)


def load_game_state_from_scenario(path: Path) -> GameState:
    """Load a scenario and return its reconstructed GameState."""
    scenario = load_scenario(path)
    return scenario.to_game_state()


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
    )
    save_scenario(scenario, path)
    return scenario
