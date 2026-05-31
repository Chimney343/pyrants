"""Editor state history and baseline tracking."""

from __future__ import annotations

import copy
from typing import TypeAlias

Snapshot: TypeAlias = dict[str, object]


class EditorStateHistory:
    """Manage undo/redo stacks and dirty-state baseline snapshots."""

    def __init__(self, max_history: int = 100) -> None:
        self.max_history = max_history
        self.undo_stack: list[Snapshot] = []
        self.redo_stack: list[Snapshot] = []
        self._saved_baseline: Snapshot | None = None

    def reset(self) -> None:
        """Clear history and saved baseline."""

        self.undo_stack.clear()
        self.redo_stack.clear()
        self._saved_baseline = None

    def clear_redo(self) -> None:
        self.redo_stack.clear()

    def push_undo_snapshot(self, snapshot: Snapshot) -> None:
        self.undo_stack.append(copy.deepcopy(snapshot))
        if len(self.undo_stack) > self.max_history:
            self.undo_stack.pop(0)

    def push_redo_snapshot(self, snapshot: Snapshot) -> None:
        self.redo_stack.append(copy.deepcopy(snapshot))
        if len(self.redo_stack) > self.max_history:
            self.redo_stack.pop(0)

    def pop_undo_snapshot(self) -> Snapshot | None:
        if not self.undo_stack:
            return None
        return self.undo_stack.pop()

    def pop_redo_snapshot(self) -> Snapshot | None:
        if not self.redo_stack:
            return None
        return self.redo_stack.pop()

    def begin_mutation(self, snapshot_before_mutation: Snapshot) -> None:
        self.push_undo_snapshot(snapshot_before_mutation)
        self.clear_redo()

    def mark_saved_baseline(self, snapshot: Snapshot) -> None:
        self._saved_baseline = copy.deepcopy(snapshot)

    def has_unsaved_changes(self, snapshot: Snapshot) -> bool:
        if self._saved_baseline is None:
            return True
        return snapshot != self._saved_baseline
