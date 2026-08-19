"""Tests for game_viewer.py — Combobox dropdown heights."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk

import pytest

from interface.game_viewer import GameViewerApp

BASE_DIR = Path(__file__).resolve().parents[1]
BOARD_PATH = BASE_DIR / "data" / "boards" / "tyrants_of_the_underdark.json"
LAYOUT_PATH = BASE_DIR / "data" / "layouts" / "tyrants_of_the_underdark_layout.json"
CARD_PATH = BASE_DIR / "data" / "cards"
SETUP_PATH = BASE_DIR / "data" / "decks" / "base_setup.json"
DECKS_DIR = BASE_DIR / "data" / "decks"

EXPECTED_COMBOBOX_HEIGHT = 256


@pytest.fixture
def viewer_app() -> GameViewerApp:
    root = tk.Tk()
    try:
        app = GameViewerApp(
            root,
            board_path=BOARD_PATH,
            layout_path=LAYOUT_PATH,
            card_path=CARD_PATH,
            setup_path=SETUP_PATH,
            decks_dir=DECKS_DIR,
            initial_player_count=2,
            seed=1,
        )
        yield app
    finally:
        root.destroy()


def assert_combobox_height(box: ttk.Combobox, name: str) -> None:
    actual = box.cget("height")
    assert actual == EXPECTED_COMBOBOX_HEIGHT, (
        f"{name} has height={actual}, expected {EXPECTED_COMBOBOX_HEIGHT}"
    )


def test_map_box_height(viewer_app: GameViewerApp) -> None:
    assert_combobox_height(viewer_app.map_box, "map_box")


def test_deck_a_box_height(viewer_app: GameViewerApp) -> None:
    assert_combobox_height(viewer_app.deck_a_box, "deck_a_box")


def test_deck_b_box_height(viewer_app: GameViewerApp) -> None:
    assert_combobox_height(viewer_app.deck_b_box, "deck_b_box")


def test_devoured_box_height(viewer_app: GameViewerApp) -> None:
    assert_combobox_height(viewer_app.devoured_box, "devoured_box")


def test_discard_box_height(viewer_app: GameViewerApp) -> None:
    assert_combobox_height(viewer_app.discard_box, "discard_box")


def test_inner_circle_box_height(viewer_app: GameViewerApp) -> None:
    assert_combobox_height(viewer_app.inner_circle_box, "inner_circle_box")


def test_trophy_hall_box_height(viewer_app: GameViewerApp) -> None:
    assert_combobox_height(viewer_app.trophy_hall_box, "trophy_hall_box")


def test_option_box_height(viewer_app: GameViewerApp) -> None:
    assert_combobox_height(viewer_app.option_box, "option_box")


def test_other_discard_boxes_initial_height(viewer_app: GameViewerApp) -> None:
    """Dynamic other-discard boxes may not exist yet, but once created they should have height=256."""
    boxes = viewer_app.other_discard_boxes
    for player_id, box in boxes.items():
        assert_combobox_height(box, f"other_discard_box[{player_id}]")


def test_sync_other_discard_labels_populated_for_c_engine(viewer_app: GameViewerApp) -> None:
    """When _sync_other_player_discard_boxes_c creates new discard rows for other players,
    all three supporting dicts (labels, selection_vars, boxes) must be populated.
    Regression test for KeyError on missing other_discard_labels entry."""
    from types import SimpleNamespace

    state = SimpleNamespace(
        turn_order=["p1", "p2"],
        current_player_id="p1",
        player_index=lambda pid: {"p1": 0, "p2": 1}[pid],
        player_discard=lambda idx: [],
    )
    viewer_app._sync_other_player_discard_boxes_c(state, {})

    assert "p2" in viewer_app.other_discard_labels, (
        "other_discard_labels must contain key for non-current player 'p2'"
    )
    assert "p2" in viewer_app.other_discard_selection_vars, (
        "other_discard_selection_vars must contain key for non-current player 'p2'"
    )
    assert "p2" in viewer_app.other_discard_boxes, (
        "other_discard_boxes must contain key for non-current player 'p2'"
    )
