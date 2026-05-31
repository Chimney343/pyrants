"""Transient interaction state for the board creator canvas."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EditorInteractionState:
    """Own transient canvas-selection, connect, and drag state."""

    selected_node_id: str | None = None
    connect_start_node_id: str | None = None
    connect_end_node_id: str | None = None
    pending_slot_node_id: str | None = None
    dragging_node_id: str | None = None
    drag_last: tuple[float, float] | None = None
    drag_started_snapshot: dict[str, object] | None = None
    drag_changed: bool = False
    site_drag_start: tuple[float, float] | None = None
    site_preview_rect_id: int | None = None

    def reset(self) -> None:
        """Clear all transient interaction state."""

        self.selected_node_id = None
        self.connect_start_node_id = None
        self.connect_end_node_id = None
        self.pending_slot_node_id = None
        self.clear_drag_state()
        self.site_drag_start = None
        self.site_preview_rect_id = None

    def reset_for_mode_change(self) -> None:
        """Clear mode-specific connect selection while preserving node selection."""

        self.connect_start_node_id = None
        self.connect_end_node_id = None

    def clear_connect_selection(self) -> None:
        """Clear the in-progress connect gesture and selection."""

        self.connect_start_node_id = None
        self.connect_end_node_id = None
        self.selected_node_id = None

    def clear_drag_state(self) -> None:
        """Clear the in-progress drag gesture state."""

        self.dragging_node_id = None
        self.drag_last = None
        self.drag_started_snapshot = None
        self.drag_changed = False

    def capture_snapshot_fields(self) -> dict[str, object]:
        """Return interaction fields that participate in undo and redo."""

        return {
            "selected_node_id": self.selected_node_id,
            "connect_start_node_id": self.connect_start_node_id,
            "connect_end_node_id": self.connect_end_node_id,
            "pending_slot_node_id": self.pending_slot_node_id,
        }

    def restore_snapshot_fields(self, snapshot: dict[str, object]) -> None:
        """Restore persisted interaction fields from a snapshot."""

        selected_node_id = snapshot.get("selected_node_id")
        self.selected_node_id = selected_node_id if isinstance(selected_node_id, str) else None

        connect_start_node_id = snapshot.get("connect_start_node_id")
        self.connect_start_node_id = connect_start_node_id if isinstance(connect_start_node_id, str) else None

        connect_end_node_id = snapshot.get("connect_end_node_id")
        self.connect_end_node_id = connect_end_node_id if isinstance(connect_end_node_id, str) else None

        pending_slot_node_id = snapshot.get("pending_slot_node_id")
        self.pending_slot_node_id = pending_slot_node_id if isinstance(pending_slot_node_id, str) else None

        self.clear_drag_state()
        self.site_drag_start = None
        self.site_preview_rect_id = None
