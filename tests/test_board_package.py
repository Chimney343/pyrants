"""Board-package schema and persistence tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from game_setup.loaders import (
    build_board_package_from_dicts,
    build_board_package_from_files,
    save_board_package_to_files,
)

BASE_DIR = Path(__file__).resolve().parents[1]
BOARD_PATH = BASE_DIR / "data" / "boards" / "base_game.json"
LAYOUT_PATH = BASE_DIR / "data" / "layouts" / "base_game_layout.json"


def test_build_board_package_from_files() -> None:
    package = build_board_package_from_files(BOARD_PATH, LAYOUT_PATH)

    assert package.board.board_id == "base_underdark"
    assert package.layout.layout_id == "base_underdark_layout"
    assert len(package.layout.nodes) == len(package.board.nodes)
    route_layout = next(node for node in package.layout.nodes if node.node_id == "route_ab")
    assert route_layout.label.isdigit()


def test_build_board_package_without_layout_generates_defaults() -> None:
    package = build_board_package_from_files(BOARD_PATH, None)

    assert package.layout.board_id == package.board.board_id
    assert len(package.layout.nodes) == len(package.board.nodes)
    assert all(node.label.isdigit() for node in package.layout.nodes if node.kind.value == "route")


def test_rejects_duplicate_layout_labels() -> None:
    board_data = {
        "board_id": "tiny",
        "nodes": [
            {
                "node_id": "site_a",
                "kind": "site",
                "adjacent_to": ["route_1"],
                "troop_capacity": 1,
                "vp_value": 1,
            },
            {
                "node_id": "route_1",
                "kind": "route",
                "adjacent_to": ["site_a"],
                "troop_capacity": 1,
                "vp_value": 0,
            },
        ],
    }
    layout_data = {
        "layout_id": "tiny_layout",
        "board_id": "tiny",
        "nodes": [
            {
                "node_id": "site_a",
                "label": "1",
                "kind": "site",
                "center": {"x": 10, "y": 10},
                "bounds": {"x": 0, "y": 0, "width": 50, "height": 50},
                "troop_slots": [{"x": 10, "y": 10}],
            },
            {
                "node_id": "route_1",
                "label": "1",
                "kind": "route",
                "center": {"x": 100, "y": 10},
                "bounds": None,
                "troop_slots": [],
            },
        ],
    }

    with pytest.raises(ValueError, match="labels must be unique"):
        build_board_package_from_dicts(board_data=board_data, layout_data=layout_data)


def test_rejects_site_slot_count_mismatch() -> None:
    board_data = {
        "board_id": "tiny",
        "nodes": [
            {
                "node_id": "site_a",
                "kind": "site",
                "adjacent_to": ["route_1"],
                "troop_capacity": 2,
                "vp_value": 1,
            },
            {
                "node_id": "route_1",
                "kind": "route",
                "adjacent_to": ["site_a"],
                "troop_capacity": 1,
                "vp_value": 0,
            },
        ],
    }
    layout_data = {
        "layout_id": "tiny_layout",
        "board_id": "tiny",
        "nodes": [
            {
                "node_id": "site_a",
                "label": "Site A",
                "kind": "site",
                "center": {"x": 10, "y": 10},
                "bounds": {"x": 0, "y": 0, "width": 50, "height": 50},
                "troop_slots": [{"x": 10, "y": 10}],
            },
            {
                "node_id": "route_1",
                "label": "1",
                "kind": "route",
                "center": {"x": 100, "y": 10},
                "bounds": None,
                "troop_slots": [],
            },
        ],
    }

    with pytest.raises(ValueError, match="requires 2 troop slots"):
        build_board_package_from_dicts(board_data=board_data, layout_data=layout_data)


def test_legacy_waypoints_payload_is_ignored() -> None:
    board_data = {
        "board_id": "tiny",
        "nodes": [
            {
                "node_id": "site_a",
                "kind": "site",
                "adjacent_to": ["route_1"],
                "troop_capacity": 1,
                "vp_value": 1,
            },
            {
                "node_id": "route_1",
                "kind": "route",
                "adjacent_to": ["site_a"],
                "troop_capacity": 1,
                "vp_value": 0,
            },
        ],
    }
    layout_data = {
        "layout_id": "tiny_layout",
        "board_id": "tiny",
        "nodes": [
            {
                "node_id": "site_a",
                "label": "Site A",
                "kind": "site",
                "center": {"x": 10, "y": 10},
                "bounds": {"x": 0, "y": 0, "width": 50, "height": 50},
                "troop_slots": [{"x": 10, "y": 10}],
                "waypoints": [{"x": 12, "y": 12}],
            },
            {
                "node_id": "route_1",
                "label": "1",
                "kind": "route",
                "center": {"x": 100, "y": 10},
                "bounds": None,
                "troop_slots": [],
            },
        ],
    }

    package = build_board_package_from_dicts(board_data=board_data, layout_data=layout_data)
    assert package.layout.board_id == "tiny"


def test_route_can_connect_to_multiple_neighbors() -> None:
    board_data = {
        "board_id": "tiny",
        "nodes": [
            {
                "node_id": "site_a",
                "kind": "site",
                "adjacent_to": ["route_1"],
                "troop_capacity": 1,
                "vp_value": 1,
            },
            {
                "node_id": "site_b",
                "kind": "site",
                "adjacent_to": ["route_1"],
                "troop_capacity": 1,
                "vp_value": 1,
            },
            {
                "node_id": "site_c",
                "kind": "site",
                "adjacent_to": ["route_1"],
                "troop_capacity": 1,
                "vp_value": 1,
            },
            {
                "node_id": "route_1",
                "kind": "route",
                "adjacent_to": ["site_a", "site_b", "site_c"],
                "troop_capacity": 1,
                "vp_value": 0,
            },
        ],
    }

    layout_data = {
        "layout_id": "tiny_layout",
        "board_id": "tiny",
        "nodes": [
            {
                "node_id": "site_a",
                "label": "Site A",
                "kind": "site",
                "center": {"x": 10, "y": 10},
                "bounds": {"x": 0, "y": 0, "width": 50, "height": 50},
                "troop_slots": [{"x": 10, "y": 10}],
            },
            {
                "node_id": "site_b",
                "label": "Site B",
                "kind": "site",
                "center": {"x": 120, "y": 10},
                "bounds": {"x": 100, "y": 0, "width": 50, "height": 50},
                "troop_slots": [{"x": 120, "y": 10}],
            },
            {
                "node_id": "site_c",
                "label": "Site C",
                "kind": "site",
                "center": {"x": 230, "y": 10},
                "bounds": {"x": 210, "y": 0, "width": 50, "height": 50},
                "troop_slots": [{"x": 230, "y": 10}],
            },
            {
                "node_id": "route_1",
                "label": "1",
                "kind": "route",
                "center": {"x": 120, "y": 120},
                "bounds": None,
                "troop_slots": [],
            },
        ],
    }

    package = build_board_package_from_dicts(board_data=board_data, layout_data=layout_data)
    route = next(node for node in package.board.nodes if node.node_id == "route_1")
    assert set(route.adjacent_to) == {"site_a", "site_b", "site_c"}


def test_save_board_package_round_trip(tmp_path: Path) -> None:
    package = build_board_package_from_files(BOARD_PATH, LAYOUT_PATH)

    output_board_path = tmp_path / "board.json"
    output_layout_path = tmp_path / "layout.json"
    save_board_package_to_files(package, output_board_path, output_layout_path)

    reloaded = build_board_package_from_files(output_board_path, output_layout_path)
    assert reloaded.model_dump(mode="json") == package.model_dump(mode="json")
