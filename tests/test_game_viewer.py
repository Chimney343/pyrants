"""Tk-free regression tests for game_viewer face-up zone syncing.

The previous test_game_viewer.py suite depended on a live Tk interpreter
(``tk.Tk()`` in a fixture) and intermittently errored in headless sessions
with ``_tkinter.TclError``. The cosmetic combobox-height checks were dropped;
the one non-cosmetic regression guard (other-discard ``KeyError``) is preserved
here without instantiating Tk by patching the widget constructors.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import interface.game_viewer as gv


def _make_app() -> gv.GameViewerApp:
    app = gv.GameViewerApp.__new__(gv.GameViewerApp)
    app.other_discards_frame = object()
    app._other_discards_placeholder = None
    app.other_discard_boxes = {}
    app.other_discard_labels = {}
    app.other_discard_selection_vars = {}
    return app


def test_sync_other_discard_labels_populated_for_c_engine() -> None:
    """When _sync_other_player_discard_boxes_c creates a new discard row, all
    three supporting dicts (labels, selection_vars, boxes) must be populated.
    Regression test for KeyError on missing other_discard_labels entry."""
    app = _make_app()

    state = SimpleNamespace(
        turn_order=["p1", "p2"],
        current_player_id="p1",
        player_index=lambda pid: {"p1": 0, "p2": 1}[pid],
        player_discard=lambda idx: [],
    )

    with (
        patch.object(gv.ttk, "Frame"),
        patch.object(gv.ttk, "Label"),
        patch.object(gv.ttk, "Combobox"),
        patch.object(gv.tk, "StringVar"),
    ):
        app._sync_other_player_discard_boxes_c(state, {})

    assert "p2" in app.other_discard_labels, (
        "other_discard_labels must contain key for non-current player 'p2'"
    )
    assert "p2" in app.other_discard_selection_vars, (
        "other_discard_selection_vars must contain key for non-current player 'p2'"
    )
    assert "p2" in app.other_discard_boxes, (
        "other_discard_boxes must contain key for non-current player 'p2'"
    )
