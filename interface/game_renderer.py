"""Canvas renderer for read-only gameplay board views."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import tkinter as tk

from engine.state import NodeKind
from game_setup.board_package import BoardPackageDefinition
from game_view import GameView

PLAYER_COLORS = {
    "p1": "#2f72c4",
    "p2": "#2f9e66",
    "p3": "#a65bb8",
    "p4": "#cf7d2a",
    "white": "#9ca3af",
}


@dataclass(frozen=True)
class LayoutNodeView:
    """Merged board topology + layout metadata for one node."""

    node_id: str
    label: str
    kind: NodeKind
    center_x: float
    center_y: float
    bounds: tuple[float, float, float, float] | None
    troop_slot_points: tuple[tuple[float, float], ...]
    adjacent_to: tuple[str, ...]


class GameBoardRenderer:
    """Render board geometry and occupancy overlays for read-only gameplay views."""

    def __init__(self) -> None:
        self._edge_width = 3

    def redraw(
        self,
        canvas: tk.Canvas,
        package: BoardPackageDefinition,
        view: GameView,
        *,
        highlighted_node_id: str | None = None,
    ) -> None:
        """Render the board package and game-state overlays into a canvas."""

        canvas.delete("all")
        layout_index = self._layout_nodes(package)
        occupancy_by_id = view.board_nodes_by_id

        drawn_edges: set[tuple[str, str]] = set()
        for node in layout_index.values():
            for adjacent_id in node.adjacent_to:
                if adjacent_id not in layout_index:
                    continue
                edge = tuple(sorted((node.node_id, adjacent_id)))
                if edge in drawn_edges:
                    continue
                drawn_edges.add(edge)
                other = layout_index[adjacent_id]
                kinds = {node.kind, other.kind}
                fill = "#9c6a2e" if NodeKind.SITE in kinds else "#777f8f"
                canvas.create_line(
                    node.center_x,
                    node.center_y,
                    other.center_x,
                    other.center_y,
                    fill=fill,
                    width=self._edge_width,
                )

        for node in layout_index.values():
            occupancy = occupancy_by_id[node.node_id]
            is_highlighted = node.node_id == highlighted_node_id
            if node.kind == NodeKind.SITE and node.bounds is not None:
                left, top, width, height = node.bounds
                canvas.create_rectangle(
                    left,
                    top,
                    left + width,
                    top + height,
                    fill="#f4f1ea",
                    outline="#1e62c7" if is_highlighted else "#2f3643",
                    width=3 if is_highlighted else 2,
                )
                canvas.create_text(
                    node.center_x,
                    node.center_y,
                    text=node.label,
                    font=("Segoe UI", 10, "bold"),
                    fill="#1b2533",
                )
            else:
                radius = 14
                canvas.create_oval(
                    node.center_x - radius,
                    node.center_y - radius,
                    node.center_x + radius,
                    node.center_y + radius,
                    fill="#ece6d6",
                    outline="#1e62c7" if is_highlighted else "#4a5565",
                    width=3 if is_highlighted else 2,
                )
                canvas.create_text(
                    node.center_x,
                    node.center_y,
                    text=node.label,
                    font=("Segoe UI", 9, "bold"),
                    fill="#1b2533",
                )

            self._draw_troops(canvas, node, occupancy)
            self._draw_spy_badges(canvas, node, occupancy)
            self._draw_node_footer(canvas, node, occupancy)

    def _draw_troops(self, canvas: tk.Canvas, node: LayoutNodeView, occupancy: Any) -> None:
        slot_points = list(node.troop_slot_points)
        if not slot_points:
            slot_points = [(node.center_x, node.center_y + 24)]
        for index, owner_id in enumerate(occupancy.troop_slots):
            if index >= len(slot_points):
                break
            slot_x, slot_y = slot_points[index]
            fill = PLAYER_COLORS.get(owner_id or "", "#d8dde5") if owner_id is not None else "#d8dde5"
            outline = "#2b3340" if owner_id is not None else "#8893a5"
            canvas.create_oval(slot_x - 9, slot_y - 9, slot_x + 9, slot_y + 9, fill=fill, outline=outline, width=1)

    def _draw_spy_badges(self, canvas: tk.Canvas, node: LayoutNodeView, occupancy: Any) -> None:
        if not occupancy.spies:
            return
        badge = " ".join(occupancy.spies)
        canvas.create_text(
            node.center_x,
            node.center_y - 22,
            text=f"Spies: {badge}",
            font=("Segoe UI", 8),
            fill="#4f5b6c",
        )

    def _draw_node_footer(self, canvas: tk.Canvas, node: LayoutNodeView, occupancy: Any) -> None:
        footer_y = node.center_y + 30 if node.kind == NodeKind.ROUTE else node.center_y + 36
        control = occupancy.control_marker or "none"
        canvas.create_text(
            node.center_x,
            footer_y,
            text=f"Ctrl: {control}  VP: {occupancy.vp_tokens}",
            font=("Segoe UI", 8),
            fill="#4f5b6c",
        )

    def _layout_nodes(self, package: BoardPackageDefinition) -> dict[str, LayoutNodeView]:
        board_index = {node.node_id: node for node in package.board.nodes}
        nodes: dict[str, LayoutNodeView] = {}
        for layout_node in package.layout.nodes:
            board_node = board_index[layout_node.node_id]
            bounds = None
            if layout_node.bounds is not None:
                bounds = (
                    layout_node.bounds.x,
                    layout_node.bounds.y,
                    layout_node.bounds.width,
                    layout_node.bounds.height,
                )
            nodes[layout_node.node_id] = LayoutNodeView(
                node_id=layout_node.node_id,
                label=layout_node.label,
                kind=layout_node.kind,
                center_x=layout_node.center.x,
                center_y=layout_node.center.y,
                bounds=bounds,
                troop_slot_points=tuple((slot.x, slot.y) for slot in layout_node.troop_slots),
                adjacent_to=tuple(board_node.adjacent_to),
            )
        return nodes
