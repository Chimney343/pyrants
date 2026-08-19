"""Board-package schemas for editor-facing topology + layout persistence."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from game_setup.types import BoardDefinition, NodeKind


class Coordinate(BaseModel):
    """Two-dimensional coordinate on the editor canvas."""

    model_config = ConfigDict(frozen=True)

    x: float
    y: float


class Rectangle(BaseModel):
    """Axis-aligned rectangle used for site bounds."""

    model_config = ConfigDict(frozen=True)

    x: float
    y: float
    width: float = Field(gt=0)
    height: float = Field(gt=0)


class CanvasConfig(BaseModel):
    """Canvas dimensions and optional background image path."""

    model_config = ConfigDict(frozen=True)

    width: int = Field(default=1600, gt=0)
    height: int = Field(default=900, gt=0)
    background_image: str | None = None


class NodeLayoutDefinition(BaseModel):
    """Editor-facing layout metadata for a board node."""

    model_config = ConfigDict(frozen=True)

    node_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    kind: NodeKind
    center: Coordinate
    bounds: Rectangle | None = None
    troop_slots: list[Coordinate] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_shape_by_kind(self) -> NodeLayoutDefinition:
        if self.kind == NodeKind.SITE:
            if self.bounds is None:
                raise ValueError("Site layout entries must define bounds")
            return self

        if self.bounds is not None:
            raise ValueError("Route layout entries cannot define bounds")
        if self.troop_slots:
            raise ValueError("Route layout entries cannot define troop slots")
        if not self.label.isdigit():
            raise ValueError("Route labels must be numeric")
        return self


class BoardLayoutDefinition(BaseModel):
    """Visual layout metadata kept separate from gameplay topology."""

    model_config = ConfigDict(frozen=True)

    layout_id: str = Field(min_length=1)
    board_id: str = Field(min_length=1)
    canvas: CanvasConfig = Field(default_factory=CanvasConfig)
    nodes: list[NodeLayoutDefinition] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_uniqueness(self) -> BoardLayoutDefinition:
        node_ids = [node.node_id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("Layout node ids must be unique")

        normalized_labels = [node.label.strip().casefold() for node in self.nodes]
        if len(normalized_labels) != len(set(normalized_labels)):
            raise ValueError("Layout labels must be unique across sites and routes")

        return self


class BoardPackageDefinition(BaseModel):
    """Validated board + layout package consumed by the editor."""

    model_config = ConfigDict(frozen=True)

    board: BoardDefinition
    layout: BoardLayoutDefinition

    @model_validator(mode="after")
    def _validate_cross_file_consistency(self) -> BoardPackageDefinition:
        if self.board.board_id != self.layout.board_id:
            raise ValueError("Board and layout board_id values must match")

        board_index = {node.node_id: node for node in self.board.nodes}
        layout_index = {node.node_id: node for node in self.layout.nodes}

        if set(board_index) != set(layout_index):
            raise ValueError("Board and layout must reference the same node ids")

        for node_id, board_node in board_index.items():
            layout_node = layout_index[node_id]
            if board_node.kind != layout_node.kind:
                raise ValueError(f"Node kind mismatch for '{node_id}'")

            if board_node.kind == NodeKind.SITE:
                if len(layout_node.troop_slots) != board_node.troop_capacity:
                    raise ValueError(
                        f"Site '{node_id}' requires {board_node.troop_capacity} troop slots in layout"
                    )

            for adjacent_id in board_node.adjacent_to:
                neighbor = board_index[adjacent_id]
                if node_id not in neighbor.adjacent_to:
                    raise ValueError(
                        f"Adjacency must be symmetric between '{node_id}' and '{adjacent_id}'"
                    )

        return self


def make_default_layout(
    board_definition: BoardDefinition,
    layout_id: str | None = None,
    canvas_width: int = 1600,
    canvas_height: int = 900,
) -> BoardLayoutDefinition:
    """Generate a starter layout when only topology data is available."""

    route_number = 1
    default_nodes: list[NodeLayoutDefinition] = []
    for index, node in enumerate(board_definition.nodes):
        column = index % 8
        row = index // 8
        center = Coordinate(x=150 + (column * 180), y=120 + (row * 140))

        if node.kind == NodeKind.SITE:
            width = 120.0
            height = 80.0
            left = center.x - (width / 2)
            top = center.y - (height / 2)
            spacing = width / (node.troop_capacity + 1)
            troop_slots = [
                Coordinate(x=left + spacing * (slot_index + 1), y=center.y)
                for slot_index in range(node.troop_capacity)
            ]
            default_nodes.append(
                NodeLayoutDefinition(
                    node_id=node.node_id,
                    label=node.node_id,
                    kind=node.kind,
                    center=center,
                    bounds=Rectangle(x=left, y=top, width=width, height=height),
                    troop_slots=troop_slots,
                )
            )
            continue

        default_nodes.append(
            NodeLayoutDefinition(
                node_id=node.node_id,
                label=str(route_number),
                kind=node.kind,
                center=center,
            )
        )
        route_number += 1

    return BoardLayoutDefinition(
        layout_id=layout_id or f"{board_definition.board_id}_layout",
        board_id=board_definition.board_id,
        canvas=CanvasConfig(width=canvas_width, height=canvas_height),
        nodes=default_nodes,
    )