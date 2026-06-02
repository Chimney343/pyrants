"""Canvas renderer for read-only gameplay board views."""

from __future__ import annotations

from typing import Any

import tkinter as tk

from engine.state import NodeKind
from game_setup.board_package import BoardPackageDefinition
from game_view import GameView
from interface.board_view import BoardNodeView, build_node_views_from_package
from interface.shared_board_renderer import (
    DEFAULT_ROUTE_FILL,
    DEFAULT_ROUTE_OUTLINE,
    DEFAULT_SITE_FILL,
    DEFAULT_SITE_OUTLINE,
    ROUTE_RADIUS,
    TROOP_SLOT_RADIUS,
    draw_edges,
    draw_route_base,
    draw_site_base,
)

PLAYER_COLORS = {
    "p1": "#2f72c4",
    "p2": "#2f9e66",
    "p3": "#a65bb8",
    "p4": "#cf7d2a",
    "white": "#9ca3af",
}

EMPTY_ROUTE_FILL = DEFAULT_ROUTE_FILL
WHITE_ROUTE_FILL = PLAYER_COLORS["white"]


def _total_control_owner(
    troop_slots: tuple[str | None, ...], spies: tuple[str, ...]
) -> str | None:
    non_empty = [s for s in troop_slots if s is not None]
    if not non_empty or len(non_empty) != len(troop_slots):
        return None
    if non_empty[0] == "white":
        return None
    if any(s != non_empty[0] for s in non_empty):
        return None
    if any(s != non_empty[0] for s in spies):
        return None
    return non_empty[0]


def _derive_control_owner(
    troop_slots: tuple[str | None, ...]
) -> str | None:
    counts: dict[str, int] = {}
    for occupant in troop_slots:
        if occupant is not None:
            counts[occupant] = counts.get(occupant, 0) + 1
    if not counts:
        return None
    max_count = max(counts.values())
    leaders = [owner for owner, count in counts.items() if count == max_count]
    return leaders[0] if len(leaders) == 1 and leaders[0] != "white" else None


class GameBoardRenderer:
    """Render board geometry and occupancy overlays for read-only gameplay views."""

    def redraw(
        self,
        canvas: tk.Canvas,
        package: BoardPackageDefinition,
        view: GameView,
        *,
        highlighted_node_id: str | None = None,
        scale: float = 1.0,
    ) -> None:
        """Render the board package and game-state overlays into a canvas."""

        canvas.delete("all")
        node_views = build_node_views_from_package(package)
        occupancy_by_id = view.board_nodes_by_id
        node_order = [node.node_id for node in package.layout.nodes]

        to_screen = lambda x, y: (x * scale, y * scale)  # noqa: E731
        scaled = lambda d: d * scale  # noqa: E731
        draw_edges(canvas, node_views, node_order, to_screen=to_screen, scaled=scaled)

        for node_id in node_order:
            node = node_views[node_id]
            occupancy = occupancy_by_id[node.node_id]
            is_highlighted = node.node_id == highlighted_node_id

            if node.kind == NodeKind.SITE and node.bounds is not None:
                self._draw_site(canvas, node, occupancy, is_highlighted, scale)
            else:
                self._draw_route(canvas, node, occupancy, is_highlighted, scale)

    def _draw_site(
        self,
        canvas: tk.Canvas,
        node: BoardNodeView,
        occupancy: Any,
        is_highlighted: bool,
        scale: float,
    ) -> None:
        total_owner = _total_control_owner(occupancy.troop_slots, occupancy.spies)
        if total_owner is not None:
            outline = PLAYER_COLORS.get(total_owner, DEFAULT_SITE_OUTLINE)
        elif is_highlighted:
            outline = "#1e62c7"
        else:
            outline = DEFAULT_SITE_OUTLINE

        ow = 3 if (is_highlighted or total_owner is not None) else None
        draw_site_base(
            canvas, node,
            to_screen=lambda x, y: (x * scale, y * scale),
            scaled=lambda d: d * scale,
            fill=DEFAULT_SITE_FILL, outline=outline, outline_width=ow,
        )

        slot_radius = max(4, int(round(TROOP_SLOT_RADIUS * scale)))
        troop_row_y = node.center_y * scale

        owner = _derive_control_owner(occupancy.troop_slots) or "none"
        site_text = f"Owner: {owner}  Control VP: {occupancy.control_vp}"
        canvas.create_text(
            node.center_x * scale,
            troop_row_y + slot_radius + max(10, int(round(12 * scale))),
            text=site_text,
            font=("Segoe UI", 9),
            fill="#1b2533",
        )

        if occupancy.spies:
            badge = " ".join(occupancy.spies)
            sx1 = (node.bounds[0] if node.bounds else 0) * scale  # type: ignore[index]
            canvas.create_text(
                node.center_x * scale,
                sx1 - max(10, int(round(32 * scale))),
                text=f"Spies: {badge}",
                font=("Segoe UI", 8),
                fill="#4f5b6c",
            )

        for index, owner_id in enumerate(occupancy.troop_slots):
            if index >= len(node.troop_slot_points):
                break
            slot_x, slot_y = node.troop_slot_points[index]
            slot_sx = slot_x * scale
            slot_sy = slot_y * scale
            fill = PLAYER_COLORS.get(owner_id or "", "#d8dde5") if owner_id is not None else "#d8dde5"
            slot_outline = "#2b3340" if owner_id is not None else "#8893a5"
            canvas.create_oval(
                slot_sx - slot_radius,
                slot_sy - slot_radius,
                slot_sx + slot_radius,
                slot_sy + slot_radius,
                fill=fill,
                outline=slot_outline,
                width=1,
            )

    def _draw_route(
        self,
        canvas: tk.Canvas,
        node: BoardNodeView,
        occupancy: Any,
        is_highlighted: bool,
        scale: float,
    ) -> None:
        route_owner = occupancy.troop_slots[0] if occupancy.troop_slots else None

        if route_owner is None:
            fill = EMPTY_ROUTE_FILL
            outline_color = DEFAULT_ROUTE_OUTLINE
        elif route_owner == "white":
            fill = WHITE_ROUTE_FILL
            outline_color = DEFAULT_ROUTE_OUTLINE
        else:
            fill = PLAYER_COLORS.get(route_owner, DEFAULT_ROUTE_FILL)
            outline_color = PLAYER_COLORS.get(route_owner, DEFAULT_ROUTE_OUTLINE)

        if is_highlighted:
            outline_color = "#1e62c7"

        draw_route_base(
            canvas, node,
            to_screen=lambda x, y: (x * scale, y * scale),
            scaled=lambda d: d * scale,
            fill=fill, outline=outline_color,
            outline_width=3 if is_highlighted else None,
        )

        if occupancy.spies:
            badge = " ".join(occupancy.spies)
            center_sy = node.center_y * scale
            route_radius = max(4, int(round(ROUTE_RADIUS * scale)))
            canvas.create_text(
                node.center_x * scale,
                center_sy - (route_radius + 12 * scale),
                text=f"Spies: {badge}",
                font=("Segoe UI", 8),
                fill="#4f5b6c",
            )


