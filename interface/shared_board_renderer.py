"""Shared board geometry drawing primitives.

Provides edge traversal, site shape, and route shape drawing so that both
the board editor and the game viewer produce identical base board geometry
from a  dict of *BoardNodeView* objects.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
import tkinter as tk

from engine.state import NodeKind
from interface.board_view import BoardNodeView

SITE_EDGE_FILL = "#b6792c"
ROUTE_EDGE_FILL = "#6f7483"

DEFAULT_SITE_FILL = "#f4f1ea"
DEFAULT_SITE_OUTLINE = "#0f172a"
DEFAULT_ROUTE_FILL = "#d8dde5"
DEFAULT_ROUTE_OUTLINE = "#4a5565"
TROOP_SLOT_RADIUS = 9
ROUTE_RADIUS = 14
LABEL_PADDING = 12
BASE_OUTLINE_WIDTH = 2
BASE_EDGE_WIDTH = 3


def draw_edges(
    canvas: tk.Canvas,
    node_views: dict[str, BoardNodeView],
    node_order: Sequence[str],
    *,
    to_screen: Callable[[float, float], tuple[float, float]],
    scaled: Callable[[float], float],
    edge_width: float = BASE_EDGE_WIDTH,
) -> None:
    """Draw connections between adjacent nodes, de-duplicating symmetric edges."""
    drawn: set[tuple[str, str]] = set()
    for node_id in node_order:
        if node_id not in node_views:
            continue
        node = node_views[node_id]
        for adjacent_id in node.adjacent_to:
            if adjacent_id not in node_views:
                continue
            edge = tuple(sorted((node_id, adjacent_id)))
            if edge in drawn:
                continue
            drawn.add(edge)
            other = node_views[adjacent_id]
            kinds = {node.kind, other.kind}
            fill = SITE_EDGE_FILL if NodeKind.SITE in kinds else ROUTE_EDGE_FILL
            sx1, sy1 = to_screen(node.center_x, node.center_y)
            sx2, sy2 = to_screen(other.center_x, other.center_y)
            canvas.create_line(
                sx1,
                sy1,
                sx2,
                sy2,
                fill=fill,
                width=max(1, int(round(scaled(edge_width)))),
            )


def draw_site_base(
    canvas: tk.Canvas,
    node_view: BoardNodeView,
    *,
    to_screen: Callable[[float, float], tuple[float, float]],
    scaled: Callable[[float], float],
    fill: str = DEFAULT_SITE_FILL,
    outline: str | None = None,
    outline_width: float | None = None,
) -> None:
    """Draw a site rectangle with the label placed inside, above centre."""
    if outline is None:
        outline = DEFAULT_SITE_OUTLINE
    if outline_width is None:
        outline_width = BASE_OUTLINE_WIDTH

    left, top, width, height = node_view.bounds  # type: ignore[misc]
    right = left + width
    bottom = top + height
    sx1, sy1 = to_screen(left, top)
    sx2, sy2 = to_screen(right, bottom)
    ow = max(1, int(round(scaled(outline_width))))
    canvas.create_rectangle(
        sx1, sy1, sx2, sy2, fill=fill, outline=outline, width=ow,
    )

    cx, cy = to_screen(node_view.center_x, node_view.center_y)
    sr = max(4, int(round(scaled(TROOP_SLOT_RADIUS))))
    ly = cy - sr - max(10, int(round(scaled(LABEL_PADDING))))
    canvas.create_text(
        cx, ly, text=node_view.label, font=("Segoe UI", 10, "bold"), fill="#1f2937",
    )


def draw_route_base(
    canvas: tk.Canvas,
    node_view: BoardNodeView,
    *,
    to_screen: Callable[[float, float], tuple[float, float]],
    scaled: Callable[[float], float],
    fill: str | None = None,
    outline: str | None = None,
    outline_width: float | None = None,
    route_radius: float | None = None,
) -> None:
    """Draw a route circle with the label centred inside."""
    if fill is None:
        fill = DEFAULT_ROUTE_FILL
    if outline is None:
        outline = DEFAULT_ROUTE_OUTLINE
    if outline_width is None:
        outline_width = BASE_OUTLINE_WIDTH
    if route_radius is None:
        route_radius = ROUTE_RADIUS

    cx, cy = to_screen(node_view.center_x, node_view.center_y)
    rr = max(4, int(round(scaled(route_radius))))
    canvas.create_oval(
        cx - rr, cy - rr, cx + rr, cy + rr,
        fill=fill, outline=outline,
        width=max(1, int(round(scaled(outline_width)))),
    )
    canvas.create_text(
        cx, cy, text=node_view.label, font=("Segoe UI", 9, "bold"), fill="#1f2937",
    )
