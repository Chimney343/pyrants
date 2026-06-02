"""Tests for shared board geometry renderer."""

from __future__ import annotations

from engine.state import NodeKind
from interface.board_view import BoardNodeView
from interface.shared_board_renderer import (
    ROUTE_EDGE_FILL,
    SITE_EDGE_FILL,
    draw_edges,
)


class _CanvasStub:
    def __init__(self) -> None:
        self.lines: list[tuple[tuple[float, ...], dict[str, object]]] = []

    def delete(self, *_: object, **__: object) -> None:
        return

    def create_line(self, *args: float, **kwargs: object) -> int:
        self.lines.append((tuple(args), dict(kwargs)))
        return 0

    def create_rectangle(self, *_: object, **__: object) -> int:
        return 0

    def create_text(self, *_: object, **__: object) -> int:
        return 0

    def create_oval(self, *_: object, **__: object) -> int:
        return 0


def _build_node_views() -> dict[str, BoardNodeView]:
    return {
        "site_a": BoardNodeView(
            node_id="site_a",
            label="A",
            kind=NodeKind.SITE,
            center_x=100.0,
            center_y=100.0,
            bounds=(70.0, 70.0, 60.0, 60.0),
            troop_slot_points=(),
            adjacent_to=("route_1", "route_2"),
        ),
        "route_1": BoardNodeView(
            node_id="route_1",
            label="1",
            kind=NodeKind.ROUTE,
            center_x=200.0,
            center_y=200.0,
            bounds=None,
            troop_slot_points=(),
            adjacent_to=("site_a", "route_2"),
        ),
        "route_2": BoardNodeView(
            node_id="route_2",
            label="2",
            kind=NodeKind.ROUTE,
            center_x=300.0,
            center_y=300.0,
            bounds=None,
            troop_slot_points=(),
            adjacent_to=("site_a", "route_1"),
        ),
    }


def _line_for_edge(
    lines: list[tuple[tuple[float, ...], dict[str, object]]],
    a: tuple[float, float],
    b: tuple[float, float],
) -> dict[str, object] | None:
    for coords, style in lines:
        if len(coords) != 4:
            continue
        x1, y1, x2, y2 = coords
        if (x1, y1, x2, y2) in ((a[0], a[1], b[0], b[1]), (b[0], b[1], a[0], a[1])):
            return style
    return None


def test_draws_all_edges_once() -> None:
    canvas = _CanvasStub()
    node_views = _build_node_views()
    node_order = list(node_views.keys())

    draw_edges(canvas, node_views, node_order, to_screen=lambda x, y: (x, y), scaled=lambda d: d)

    assert len(canvas.lines) == 3


def test_site_to_route_edge_uses_site_color() -> None:
    canvas = _CanvasStub()
    node_views = _build_node_views()
    node_order = list(node_views.keys())

    draw_edges(canvas, node_views, node_order, to_screen=lambda x, y: (x, y), scaled=lambda d: d)

    style = _line_for_edge(canvas.lines, (100, 100), (200, 200))
    assert style is not None
    assert style["fill"] == SITE_EDGE_FILL


def test_route_to_route_edge_uses_route_color() -> None:
    canvas = _CanvasStub()
    node_views = _build_node_views()
    node_order = list(node_views.keys())

    draw_edges(canvas, node_views, node_order, to_screen=lambda x, y: (x, y), scaled=lambda d: d)

    style = _line_for_edge(canvas.lines, (200, 200), (300, 300))
    assert style is not None
    assert style["fill"] == ROUTE_EDGE_FILL


def test_skips_edges_to_missing_nodes() -> None:
    canvas = _CanvasStub()
    node_views = _build_node_views()
    del node_views["route_2"]
    node_order = list(node_views.keys())

    draw_edges(canvas, node_views, node_order, to_screen=lambda x, y: (x, y), scaled=lambda d: d)

    assert len(canvas.lines) == 1


def test_applies_scale_via_callables() -> None:
    canvas = _CanvasStub()
    node_views = _build_node_views()
    node_order = list(node_views.keys())

    draw_edges(canvas, node_views, node_order, to_screen=lambda x, y: (x * 2, y * 2), scaled=lambda d: d * 2)

    style = _line_for_edge(canvas.lines, (200, 200), (400, 400))
    assert style is not None
    assert style["width"] == 6  # edge_width=3 * scaled(2) = 6


def test_edge_width_is_scaled() -> None:
    canvas = _CanvasStub()
    node_views = _build_node_views()
    node_order = list(node_views.keys())

    draw_edges(canvas, node_views, node_order, to_screen=lambda x, y: (x, y), scaled=lambda d: d, edge_width=5)

    style = _line_for_edge(canvas.lines, (100, 100), (200, 200))
    assert style is not None
    assert style["width"] == 5


def test_node_order_affects_drawing_order() -> None:
    canvas = _CanvasStub()
    node_views = _build_node_views()

    draw_edges(canvas, node_views, ["route_1", "site_a", "route_2"], to_screen=lambda x, y: (x, y), scaled=lambda d: d)

    first = canvas.lines[0]
    assert (200.0, 200.0) in (first[0][:2], first[0][2:])
