"""Canvas rendering collaborator for the board editor."""

from __future__ import annotations

from typing import Any
import tkinter as tk

from engine.state import NodeKind


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

        drawn_edges: set[tuple[str, str]] = set()

        for node_id in app.node_order:
            node = app.nodes[node_id]
            for adjacent_id in sorted(node.adjacent_to):
                if adjacent_id not in app.nodes:
                    continue

                edge = tuple(sorted((node_id, adjacent_id)))
                if edge in drawn_edges:
                    continue
                drawn_edges.add(edge)

                other = app.nodes[adjacent_id]
                kinds = {node.kind, other.kind}
                fill = "#b6792c" if NodeKind.SITE in kinds else "#6f7483"
                self.draw_world_line(
                    app,
                    [(node.center_x, node.center_y), (other.center_x, other.center_y)],
                    fill=fill,
                    width=2,
                )

        for node_id in app.node_order:
            node = app.nodes[node_id]
            is_selected = node_id == interaction.selected_node_id
            is_connect_anchor = node_id == interaction.connect_start_node_id

            if node.kind == NodeKind.SITE and node.bounds is not None:
                left, top, width, height = node.bounds
                right = left + width
                bottom = top + height

                sx1, sy1 = app._to_screen(left, top)
                sx2, sy2 = app._to_screen(right, bottom)

                outline = "#0f172a"
                if is_connect_anchor:
                    outline = "#20803d"
                elif is_selected:
                    outline = "#1756cc"

                app.canvas.create_rectangle(
                    sx1,
                    sy1,
                    sx2,
                    sy2,
                    fill="",
                    outline=outline,
                    width=max(1, int(round(app._scaled(2 if not (is_selected or is_connect_anchor) else 3)))),
                )

                center_sx, center_sy = app._to_screen(node.center_x, node.center_y)
                app.canvas.create_text(
                    center_sx,
                    center_sy,
                    text=node.label,
                    font=("Segoe UI", 10, "bold"),
                    fill="#1f2937",
                )

                slot_radius = max(4, int(round(app._scaled(self.route_radius))))
                for slot_x, slot_y in node.troop_slots:
                    slot_sx, slot_sy = app._to_screen(slot_x, slot_y)
                    app.canvas.create_oval(
                        slot_sx - slot_radius,
                        slot_sy - slot_radius,
                        slot_sx + slot_radius,
                        slot_sy + slot_radius,
                        fill="#8a1c1c",
                        outline="#5d1010",
                    )

            if node.kind == NodeKind.ROUTE:
                fill = "#fce8c9"
                outline = "#7a5f2e"
                if is_connect_anchor:
                    outline = "#20803d"
                elif is_selected:
                    outline = "#1756cc"

                center_sx, center_sy = app._to_screen(node.center_x, node.center_y)
                route_radius = max(4, int(round(app._scaled(self.route_radius))))
                app.canvas.create_oval(
                    center_sx - route_radius,
                    center_sy - route_radius,
                    center_sx + route_radius,
                    center_sy + route_radius,
                    fill=fill,
                    outline=outline,
                    width=max(1, int(round(app._scaled(2 if not (is_selected or is_connect_anchor) else 3)))),
                )
                app.canvas.create_text(
                    center_sx,
                    center_sy,
                    text=node.label,
                    font=("Segoe UI", 9, "bold"),
                    fill="#1f2937",
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

        pending_slot_node_id = getattr(interaction, "pending_slot_node_id", None)
        if pending_slot_node_id is not None:
            pending = app.nodes[pending_slot_node_id]
            remaining = pending.troop_capacity - len(pending.troop_slots)
            app.canvas.create_text(
                12,
                12,
                anchor=tk.NW,
                text=f"Click {remaining} troop slot positions inside '{pending.label}'",
                font=("Segoe UI", 10, "bold"),
                fill="#9c1c1c",
            )
