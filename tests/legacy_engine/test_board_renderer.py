"""Rendering behavior tests for board edge visibility."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from engine.state import NodeKind
from interface.board_renderer import BoardRenderer


class _Mode(Enum):
    SELECT = "select"


class _Flag:
    def __init__(self, value: bool) -> None:
        self._value = value

    def get(self) -> bool:
        return self._value


class _CanvasStub:
    def __init__(self) -> None:
        self.lines: list[tuple[tuple[float, ...], dict[str, object]]] = []

    def delete(self, *_: object, **__: object) -> None:
        return

    def create_image(self, *_: object, **__: object) -> int:
        return 0

    def create_line(self, *coords: float, **kwargs: object) -> int:
        self.lines.append((tuple(coords), dict(kwargs)))
        return 0

    def create_rectangle(self, *_: object, **__: object) -> int:
        return 0

    def create_text(self, *_: object, **__: object) -> int:
        return 0

    def create_oval(self, *_: object, **__: object) -> int:
        return 0


@dataclass
class _Node:
    node_id: str
    label: str
    kind: NodeKind
    center_x: float
    center_y: float
    adjacent_to: set[str] = field(default_factory=set)
    bounds: tuple[float, float, float, float] | None = None
    troop_slots: list[tuple[float, float]] = field(default_factory=list)


class _AppStub:
    def __init__(self) -> None:
        self.canvas = _CanvasStub()
        self.background_photo = None
        self.grid_enabled = _Flag(False)
        self.mode = _Mode.SELECT
        self.node_order = ["site_b", "route_6", "route_7"]

        self.nodes = {
            "site_b": _Node(
                node_id="site_b",
                label="B",
                kind=NodeKind.SITE,
                center_x=100,
                center_y=100,
                bounds=(70, 70, 60, 60),
            ),
            "route_6": _Node(
                node_id="route_6",
                label="6",
                kind=NodeKind.ROUTE,
                center_x=220,
                center_y=220,
                adjacent_to={"site_b", "route_7"},
            ),
            "route_7": _Node(
                node_id="route_7",
                label="7",
                kind=NodeKind.ROUTE,
                center_x=360,
                center_y=220,
                adjacent_to={"route_6"},
            ),
        }

        self.selected_node_id = None
        self.connect_start_node_id = None
        self.connect_end_node_id = None
        self.pending_slot_node_id = None

    def _to_screen(self, x: float, y: float) -> tuple[float, float]:
        return (x, y)

    def _scaled(self, distance: float) -> float:
        return distance


def _has_edge_line(lines: list[tuple[tuple[float, ...], dict[str, object]]], a: tuple[float, float], b: tuple[float, float]) -> bool:
    for coords, _style in lines:
        if len(coords) != 4:
            continue
        x1, y1, x2, y2 = coords
        if (x1, y1, x2, y2) == (a[0], a[1], b[0], b[1]):
            return True
        if (x1, y1, x2, y2) == (b[0], b[1], a[0], a[1]):
            return True
    return False


def test_route_to_route_connection_is_drawn_as_direct_edge() -> None:
    app = _AppStub()
    renderer = BoardRenderer()

    renderer.redraw(app)

    assert _has_edge_line(app.canvas.lines, (220, 220), (360, 220))


def test_pending_connect_selection_draws_highlight_overlay() -> None:
    app = _AppStub()
    app.connect_start_node_id = "site_b"
    app.connect_end_node_id = "route_7"

    renderer = BoardRenderer()
    renderer.redraw(app)

    highlight_lines = [
        coords for coords, style in app.canvas.lines if style.get("fill") == "#11823b" and len(coords) == 4
    ]
    assert highlight_lines
    assert _has_edge_line([(coords, {"fill": "#11823b"}) for coords in highlight_lines], (100, 100), (360, 220))


def test_route_with_two_site_neighbors_draws_site_to_route_edges() -> None:
    """Connecting two sites to the same route must show individual site-to-route
    edges, not collapse them into a site-to-site line."""
    app = _AppStub()
    app.node_order = ["site_a", "site_b", "route_1"]
    app.nodes = {
        "site_a": _Node(
            node_id="site_a",
            label="A",
            kind=NodeKind.SITE,
            center_x=100,
            center_y=100,
            bounds=(70, 70, 60, 60),
            adjacent_to={"route_1"},
        ),
        "site_b": _Node(
            node_id="site_b",
            label="B",
            kind=NodeKind.SITE,
            center_x=300,
            center_y=100,
            bounds=(270, 70, 60, 60),
            adjacent_to={"route_1"},
        ),
        "route_1": _Node(
            node_id="route_1",
            label="1",
            kind=NodeKind.ROUTE,
            center_x=200,
            center_y=200,
            adjacent_to={"site_a", "site_b"},
        ),
    }

    renderer = BoardRenderer()
    renderer.redraw(app)

    assert _has_edge_line(app.canvas.lines, (100, 100), (200, 200)), "site_a to route_1 edge missing"
    assert _has_edge_line(app.canvas.lines, (300, 100), (200, 200)), "site_b to route_1 edge missing"
    assert not _has_edge_line(app.canvas.lines, (100, 100), (300, 100)), "site_a to site_b direct line must not exist"


def test_renderer_never_uses_spline_smoothing_for_lines() -> None:
    app = _AppStub()

    renderer = BoardRenderer()
    renderer.redraw(app)

    assert not any(style.get("smooth") is True for _coords, style in app.canvas.lines)
