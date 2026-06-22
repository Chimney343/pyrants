"""Canvas renderer for read-only gameplay board views."""

from __future__ import annotations

import tkinter as tk
from typing import Any

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
)

PLAYER_COLORS = {
    "p0": "#c44b2f",
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


def _lighten_color(hex_color: str, factor: float = 1.25) -> str:
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    r = min(255, int(r * factor))
    g = min(255, int(g * factor))
    b = min(255, int(b * factor))
    if r == 0:
        r = 1
    if g == 0:
        g = 1
    if b == 0:
        b = 1
    return f"#{r:02x}{g:02x}{b:02x}"


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
        control_owner = _derive_control_owner(occupancy.troop_slots)
        total_owner = _total_control_owner(occupancy.troop_slots, occupancy.spies)
        if control_owner is not None:
            outline = PLAYER_COLORS.get(control_owner, DEFAULT_SITE_OUTLINE)
        elif is_highlighted:
            outline = "#1e62c7"
        else:
            outline = DEFAULT_SITE_OUTLINE

        ow = 3 if (is_highlighted or control_owner is not None) else None
        rect_ow_raw = ow if ow is not None else 2
        rect_ow = max(1, int(round(rect_ow_raw * scale)))
        left_s, top_s, w_s, h_s = node.bounds
        canvas.create_rectangle(
            left_s * scale,
            top_s * scale,
            (left_s + w_s) * scale,
            (top_s + h_s) * scale,
            fill=DEFAULT_SITE_FILL, outline=outline, width=rect_ow,
        )

        if total_owner is not None:
            sc_left = left_s * scale
            sc_top = top_s * scale
            sc_right = (left_s + w_s) * scale
            sc_bottom = (top_s + h_s) * scale
            hatch_color = _lighten_color(PLAYER_COLORS[total_owner])
            step = max(4, int(round(6 * scale)))
            b_start = sc_top - sc_right
            b_end = sc_bottom - sc_left
            b = int(b_start)
            while b <= b_end:
                x1 = max(sc_left, sc_top - b)
                y1 = x1 + b
                x2 = min(sc_right, sc_bottom - b)
                y2 = x2 + b
                if x1 <= x2 and y1 <= y2:
                    canvas.create_line(x1, y1, x2, y2, fill=hatch_color, width=1)
                b += step

        label_cx = node.center_x * scale
        label_cy = node.center_y * scale
        label_sr = max(4, int(round(TROOP_SLOT_RADIUS * scale)))
        label_y = label_cy - label_sr - max(10, int(round(12 * scale)))
        canvas.create_text(
            label_cx, label_y,
            text=node.label,
            font=("Segoe UI", 10, "bold"),
            fill="#1f2937",
        )

        slot_radius = max(4, int(round(TROOP_SLOT_RADIUS * scale)))
        troop_row_y = node.center_y * scale

        vp_text = f"VP: {occupancy.control_vp}"
        canvas.create_text(
            node.center_x * scale,
            troop_row_y + slot_radius + max(10, int(round(12 * scale))),
            text=vp_text,
            font=("Segoe UI", 9, "bold"),
            fill="#1b2533",
        )

        if occupancy.spies:
            left, top, w, h = node.bounds
            sx_left = left * scale
            sx_top = top * scale
            sx_right = (left + w) * scale
            sx_bottom = (top + h) * scale
            spy_corners = {
                "p1": (sx_left, sx_top, "nw"),
                "p2": (sx_right, sx_top, "ne"),
                "p3": (sx_left, sx_bottom, "sw"),
                "p4": (sx_right, sx_bottom, "se"),
            }
            for spy_id in occupancy.spies:
                info = spy_corners.get(spy_id)
                if info is None:
                    continue
                sx, sy, anchor = info
                color = PLAYER_COLORS.get(spy_id, "#4f5b6c")
                canvas.create_text(
                    sx, sy,
                    text="★",
                    font=("Segoe UI", max(9, int(round(14 * scale)))),
                    fill=color,
                    anchor=anchor,
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
            center_sx = node.center_x * scale
            center_sy = node.center_y * scale
            rr = max(4, int(round(ROUTE_RADIUS * scale)))
            spy_positions = {
                "p1": (center_sx - rr, center_sy - rr),
                "p2": (center_sx + rr, center_sy - rr),
                "p3": (center_sx - rr, center_sy + rr),
                "p4": (center_sx + rr, center_sy + rr),
            }
            for spy_id in occupancy.spies:
                pos = spy_positions.get(spy_id)
                if pos is None:
                    continue
                color = PLAYER_COLORS.get(spy_id, "#4f5b6c")
                canvas.create_text(
                    pos[0], pos[1],
                    text="★",
                    font=("Segoe UI", max(9, int(round(14 * scale)))),
                    fill=color,
                    anchor="center",
                )


