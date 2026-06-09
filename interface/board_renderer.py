"""Canvas rendering collaborator for the board editor."""

from __future__ import annotations

import tkinter as tk
from typing import Any

from engine.state import NodeKind
from interface.board_view import build_node_views_from_editor
from interface.shared_board_renderer import (
    DEFAULT_ROUTE_FILL,
    DEFAULT_ROUTE_OUTLINE,
    DEFAULT_SITE_OUTLINE,
    TROOP_SLOT_RADIUS,
    draw_edges,
    draw_route_base,
    draw_site_base,
)


def _interaction_view(app: Any) -> Any:
    """Return interaction state object, falling back to app for test stubs."""

    return getattr(app, "interaction", app)


class BoardRenderer:
    """Render grid, edges, nodes, and overlays for the editor canvas."""

    def __init__(self, route_radius: int = 14) -> None:
        self.route_radius = route_radius

    def draw_world_line(
        self,
        app: Any,
        points: list[tuple[float, float]],
        *,
        fill: str,
        width: float,
    ) -> None:
        if len(points) < 2:
            return

        flattened: list[float] = []
        for x, y in points:
            sx, sy = app._to_screen(x, y)
            flattened.extend([sx, sy])

        app.canvas.create_line(
            *flattened,
            fill=fill,
            width=max(1, int(round(app._scaled(width)))),
            smooth=False,
        )

    def draw_grid(self, app: Any) -> None:
        if not app.grid_enabled.get():
            return

        step = max(4, int(app.grid_size.get()))
        screen_step = app._scaled(step)
        if screen_step < 8:
            return

        max_x = int(app.canvas_width)
        max_y = int(app.canvas_height)
        max_screen_x = app._scaled(app.canvas_width)
        max_screen_y = app._scaled(app.canvas_height)

        for grid_x in range(0, max_x + 1, step):
            sx, _ = app._to_screen(grid_x, 0)
            app.canvas.create_line(sx, 0, sx, max_screen_y, fill="#edf0f5")

        for grid_y in range(0, max_y + 1, step):
            _, sy = app._to_screen(0, grid_y)
            app.canvas.create_line(0, sy, max_screen_x, sy, fill="#edf0f5")

    def redraw(self, app: Any) -> None:
        app.canvas.delete("all")
        interaction = _interaction_view(app)

        if app.background_photo is not None:
            app.canvas.create_image(0, 0, image=app.background_photo, anchor=tk.NW)

        self.draw_grid(app)

        node_views = build_node_views_from_editor(app.nodes)
        to_screen = app._to_screen
        scaled = app._scaled
        draw_edges(app.canvas, node_views, app.node_order, to_screen=to_screen, scaled=scaled)

        for node_id in app.node_order:
            node = app.nodes[node_id]
            node_view = node_views[node_id]
            is_selected = node_id == interaction.selected_node_id
            is_connect_anchor = node_id == interaction.connect_start_node_id

            if node.kind == NodeKind.SITE and node.bounds is not None:
                outline = DEFAULT_SITE_OUTLINE
                if is_connect_anchor:
                    outline = "#20803d"
                elif is_selected:
                    outline = "#1756cc"

                ow = 3 if (is_selected or is_connect_anchor) else None
                draw_site_base(
                    app.canvas, node_view,
                    to_screen=to_screen, scaled=scaled,
                    fill="", outline=outline, outline_width=ow,
                )

                slot_radius = max(4, int(round(scaled(TROOP_SLOT_RADIUS))))
                white_slots: set[int] = getattr(node, "white_troop_slot_indices", set())
                for index, (slot_x, slot_y) in enumerate(node.troop_slots):
                    slot_sx, slot_sy = app._to_screen(slot_x, slot_y)
                    if index in white_slots:
                        fill = "#9ca3af"
                        outline = "#2b3340"
                    else:
                        fill = "#d8dde5"
                        outline = "#8893a5"
                    app.canvas.create_oval(
                        slot_sx - slot_radius,
                        slot_sy - slot_radius,
                        slot_sx + slot_radius,
                        slot_sy + slot_radius,
                        fill=fill,
                        outline=outline,
                    )

            if node.kind == NodeKind.ROUTE:
                outline = DEFAULT_ROUTE_OUTLINE
                if is_connect_anchor:
                    outline = "#20803d"
                elif is_selected:
                    outline = "#1756cc"

                white_slots: set[int] = getattr(node, "white_troop_slot_indices", set())
                route_fill = "#9ca3af" if white_slots else DEFAULT_ROUTE_FILL

                ow = 3 if (is_selected or is_connect_anchor) else None
                draw_route_base(
                    app.canvas, node_view,
                    to_screen=to_screen, scaled=scaled,
                    fill=route_fill, outline=outline, outline_width=ow,
                    route_radius=self.route_radius,
                )

        connect_start = getattr(interaction, "connect_start_node_id", None)
        connect_end = getattr(interaction, "connect_end_node_id", None)
        if (
            connect_start is not None
            and connect_end is not None
            and connect_start in app.nodes
            and connect_end in app.nodes
        ):
            start_node = app.nodes[connect_start]
            end_node = app.nodes[connect_end]
            self.draw_world_line(
                app,
                [(start_node.center_x, start_node.center_y), (end_node.center_x, end_node.center_y)],
                fill="#11823b",
                width=3.5,
            )


