"""Board package loading/building/saving helpers for the editor."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol, TypeVar

from game_setup.board_package import BoardPackageDefinition
from game_setup.loaders import (
    build_board_package_from_dicts,
    build_board_package_from_files,
    save_board_package_to_files,
)


class EditableNodeLike(Protocol):
    """Minimal node interface required for package serialization."""

    node_id: str
    label: str
    kind: Any
    center_x: float
    center_y: float
    bounds: tuple[float, float, float, float] | None
    troop_slots: list[tuple[float, float]]
    white_troop_slot_indices: set[int]
    troop_capacity: int
    control_vp: int
    total_control_vp_per_turn: int
    initial_vp_tokens: int
    influence_income: int
    adjacent_to: set[str]


NodeType = TypeVar("NodeType", bound=EditableNodeLike)


class BoardPackageManager:
    """Editor-facing adapter around board-package loader and saver APIs."""

    def load_package(self, board_path: Path, layout_path: Path | None) -> BoardPackageDefinition:
        return build_board_package_from_files(board_path=board_path, layout_path=layout_path)

    def materialize_nodes(
        self,
        package: BoardPackageDefinition,
        node_factory: Callable[[Any, Any], NodeType],
    ) -> tuple[dict[str, NodeType], list[str]]:
        board_index = {node.node_id: node for node in package.board.nodes}

        nodes: dict[str, NodeType] = {}
        node_order: list[str] = []
        for layout_node in package.layout.nodes:
            board_node = board_index[layout_node.node_id]
            editable = node_factory(layout_node, board_node)
            nodes[editable.node_id] = editable
            node_order.append(editable.node_id)

        return nodes, node_order

    def save_package(self, package: BoardPackageDefinition, board_path: Path, layout_path: Path) -> None:
        save_board_package_to_files(package=package, board_path=board_path, layout_path=layout_path)

    def build_package(
        self,
        *,
        board_id: str,
        layout_id: str,
        canvas_width: int,
        canvas_height: int,
        nodes: dict[str, EditableNodeLike],
        node_order: list[str],
        background_image_path: Path | None,
        layout_path: Path | None,
    ) -> BoardPackageDefinition:
        board_nodes: list[dict[str, object]] = []
        layout_nodes: list[dict[str, object]] = []

        for node_id in node_order:
            node = nodes[node_id]
            initial_troop_slots = [
                "white" if slot_index in node.white_troop_slot_indices else None
                for slot_index in range(node.troop_capacity)
            ]
            board_nodes.append(
                {
                    "node_id": node.node_id,
                    "kind": node.kind.value,
                    "adjacent_to": sorted(node.adjacent_to),
                    "troop_capacity": node.troop_capacity,
                    "control_vp": node.control_vp,
                    "total_control_vp_per_turn": node.total_control_vp_per_turn,
                    "initial_troop_slots": initial_troop_slots,
                    "initial_vp_tokens": node.initial_vp_tokens,
                    "influence_income": node.influence_income,
                }
            )

            bounds_payload = None
            if node.bounds is not None:
                left, top, width, height = node.bounds
                bounds_payload = {
                    "x": left,
                    "y": top,
                    "width": width,
                    "height": height,
                }

            layout_nodes.append(
                {
                    "node_id": node.node_id,
                    "label": node.label,
                    "kind": node.kind.value,
                    "center": {"x": node.center_x, "y": node.center_y},
                    "bounds": bounds_payload,
                    "troop_slots": [{"x": x, "y": y} for x, y in node.troop_slots],
                }
            )

        background = self.background_path_for_layout(background_image_path, layout_path)

        board_data = {
            "board_id": board_id,
            "nodes": board_nodes,
        }
        layout_data = {
            "layout_id": layout_id,
            "board_id": board_id,
            "canvas": {
                "width": canvas_width,
                "height": canvas_height,
                "background_image": background,
            },
            "nodes": layout_nodes,
        }

        return build_board_package_from_dicts(board_data=board_data, layout_data=layout_data)

    def background_path_for_layout(self, background_image_path: Path | None, layout_path: Path | None) -> str | None:
        if background_image_path is None:
            return None

        if layout_path is None:
            return background_image_path.as_posix()

        try:
            relative = background_image_path.resolve().relative_to(layout_path.parent.resolve())
            return relative.as_posix()
        except ValueError:
            return background_image_path.as_posix()
