"""Shared immutable view model for board geometry projection.

Provides a single representation consumed by both the board editor and the
read-only game viewer, eliminating the need to duplicate layout-index
construction in every renderer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from engine.state import NodeKind
from game_setup.board_package import BoardPackageDefinition


@dataclass(frozen=True)
class BoardNodeView:
    """Render-ready snapshot of one board node's geometry and topology."""

    node_id: str
    label: str
    kind: NodeKind
    center_x: float
    center_y: float
    bounds: tuple[float, float, float, float] | None
    troop_slot_points: tuple[tuple[float, float], ...]
    adjacent_to: tuple[str, ...]


def build_node_views_from_package(
    package: BoardPackageDefinition,
) -> dict[str, BoardNodeView]:
    """Project a validated board-and-layout package into immutable node views."""
    board_index = {node.node_id: node for node in package.board.nodes}
    nodes: dict[str, BoardNodeView] = {}
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
        nodes[layout_node.node_id] = BoardNodeView(
            node_id=layout_node.node_id,
            label=layout_node.label,
            kind=layout_node.kind,
            center_x=layout_node.center.x,
            center_y=layout_node.center.y,
            bounds=bounds,
            troop_slot_points=tuple(
                (slot.x, slot.y) for slot in layout_node.troop_slots
            ),
            adjacent_to=tuple(board_node.adjacent_to),
        )
    return nodes


def build_node_views_from_editor(
    editor_nodes: dict[str, Any],
) -> dict[str, BoardNodeView]:
    """Project mutable editor nodes into the shared immutable view."""
    nodes: dict[str, BoardNodeView] = {}
    for node_id, node in editor_nodes.items():
        bounds = None
        if node.bounds is not None:
            bounds = (
                node.bounds[0],
                node.bounds[1],
                node.bounds[2],
                node.bounds[3],
            )
        nodes[node_id] = BoardNodeView(
            node_id=node.node_id,
            label=node.label,
            kind=node.kind,
            center_x=node.center_x,
            center_y=node.center_y,
            bounds=bounds,
            troop_slot_points=tuple(node.troop_slots),
            adjacent_to=tuple(node.adjacent_to),
        )
    return nodes
