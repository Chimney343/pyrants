"""Tests for shared board view model projection."""

from __future__ import annotations

from types import SimpleNamespace

from engine.state import NodeKind
from game_setup.board_package import (
    BoardPackageDefinition,
    BoardLayoutDefinition,
    CanvasConfig,
    Coordinate,
    NodeLayoutDefinition,
    Rectangle,
)
from interface.board_view import (
    BoardNodeView,
    build_node_views_from_editor,
    build_node_views_from_package,
)


def _make_board_def(board_id: str, site_id: str, route_id: str, connect: bool = True):
    from engine.state import BoardDefinition, NodeDefinition

    return BoardDefinition(
        board_id=board_id,
        nodes=[
            NodeDefinition(
                node_id=site_id,
                kind=NodeKind.SITE,
                troop_capacity=2,
                control_vp=3,
                total_control_vp_per_turn=1,
                influence_income=2,
                initial_vp_tokens=0,
                adjacent_to=[route_id] if connect else [],
            ),
            NodeDefinition(
                node_id=route_id,
                kind=NodeKind.ROUTE,
                troop_capacity=1,
                control_vp=1,
                total_control_vp_per_turn=0,
                influence_income=1,
                initial_vp_tokens=0,
                adjacent_to=[site_id] if connect else [],
            ),
        ],
    )


def _make_layout(layout_id: str, board_id: str, site_id: str, route_id: str):
    return BoardLayoutDefinition(
        layout_id=layout_id,
        board_id=board_id,
        canvas=CanvasConfig(width=1000, height=800),
        nodes=[
            NodeLayoutDefinition(
                node_id=site_id,
                label="SiteA",
                kind=NodeKind.SITE,
                center=Coordinate(x=150, y=100),
                bounds=Rectangle(x=100, y=75, width=100, height=50),
                troop_slots=[Coordinate(x=130, y=100), Coordinate(x=170, y=100)],
            ),
            NodeLayoutDefinition(
                node_id=route_id,
                label="1",
                kind=NodeKind.ROUTE,
                center=Coordinate(x=300, y=200),
            ),
        ],
    )


def test_build_from_package_produces_correct_site_view() -> None:
    board = _make_board_def("b", "site_a", "route_1")
    layout = _make_layout("l", "b", "site_a", "route_1")
    package = BoardPackageDefinition(board=board, layout=layout)

    views = build_node_views_from_package(package)

    assert "site_a" in views
    sv = views["site_a"]
    assert sv.node_id == "site_a"
    assert sv.label == "SiteA"
    assert sv.kind == NodeKind.SITE
    assert sv.center_x == 150.0
    assert sv.center_y == 100.0
    assert sv.bounds == (100.0, 75.0, 100.0, 50.0)
    assert len(sv.troop_slot_points) == 2
    assert sv.troop_slot_points[0] == (130.0, 100.0)
    assert sv.troop_slot_points[1] == (170.0, 100.0)
    assert sv.adjacent_to == ("route_1",)


def test_build_from_package_produces_correct_route_view() -> None:
    board = _make_board_def("b", "site_a", "route_1")
    layout = _make_layout("l", "b", "site_a", "route_1")
    package = BoardPackageDefinition(board=board, layout=layout)

    views = build_node_views_from_package(package)

    assert "route_1" in views
    rv = views["route_1"]
    assert rv.node_id == "route_1"
    assert rv.label == "1"
    assert rv.kind == NodeKind.ROUTE
    assert rv.center_x == 300.0
    assert rv.center_y == 200.0
    assert rv.bounds is None
    assert rv.troop_slot_points == ()
    assert rv.adjacent_to == ("site_a",)


def test_build_from_editor_produces_equivalent_view() -> None:
    editor_nodes = {
        "site_a": SimpleNamespace(
            node_id="site_a",
            label="SiteA",
            kind=NodeKind.SITE,
            center_x=150.0,
            center_y=100.0,
            bounds=(100.0, 75.0, 100.0, 50.0),
            troop_slots=[(130.0, 100.0), (170.0, 100.0)],
            adjacent_to={"route_1"},
        ),
        "route_1": SimpleNamespace(
            node_id="route_1",
            label="1",
            kind=NodeKind.ROUTE,
            center_x=300.0,
            center_y=200.0,
            bounds=None,
            troop_slots=[],
            adjacent_to={"site_a"},
        ),
    }

    views = build_node_views_from_editor(editor_nodes)

    assert views["site_a"].node_id == "site_a"
    assert views["site_a"].label == "SiteA"
    assert views["site_a"].kind == NodeKind.SITE
    assert views["site_a"].bounds == (100.0, 75.0, 100.0, 50.0)
    assert views["site_a"].troop_slot_points == ((130.0, 100.0), (170.0, 100.0))
    assert views["site_a"].adjacent_to == ("route_1",)

    assert views["route_1"].node_id == "route_1"
    assert views["route_1"].label == "1"
    assert views["route_1"].kind == NodeKind.ROUTE
    assert views["route_1"].bounds is None
    assert views["route_1"].troop_slot_points == ()
    assert views["route_1"].adjacent_to == ("site_a",)


def test_editor_and_package_projections_are_equal_for_same_data() -> None:
    """The two projection paths must produce identical BoardNodeView instances."""
    board = _make_board_def("b", "site_x", "route_9")
    layout = _make_layout("l", "b", "site_x", "route_9")
    package = BoardPackageDefinition(board=board, layout=layout)

    from_pkg = build_node_views_from_package(package)

    editor_nodes = {
        "site_x": SimpleNamespace(
            node_id="site_x",
            label="SiteA",
            kind=NodeKind.SITE,
            center_x=150.0,
            center_y=100.0,
            bounds=(100.0, 75.0, 100.0, 50.0),
            troop_slots=[(130.0, 100.0), (170.0, 100.0)],
            adjacent_to={"route_9"},
        ),
        "route_9": SimpleNamespace(
            node_id="route_9",
            label="1",
            kind=NodeKind.ROUTE,
            center_x=300.0,
            center_y=200.0,
            bounds=None,
            troop_slots=[],
            adjacent_to={"site_x"},
        ),
    }
    from_ed = build_node_views_from_editor(editor_nodes)

    assert from_pkg == from_ed


def test_board_node_view_is_immutable() -> None:
    import pytest as pt

    nv = BoardNodeView("n", "L", NodeKind.ROUTE, 1.0, 2.0, None, (), ("x",))
    with pt.raises(Exception):
        nv.label = "changed"  # type: ignore[misc]
