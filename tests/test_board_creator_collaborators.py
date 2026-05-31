"""Targeted tests for board-creator collaborator behavior."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import tkinter as tk

from interface.background_manager import BackgroundImageManager
from interface.board_creator import BoardCreatorApp
from interface.interaction_state import EditorInteractionState
from interface.package_manager import BoardPackageManager
from interface.state_history import EditorStateHistory


class _StatusRecorder:
    def __init__(self) -> None:
        self.value = ""

    def set(self, message: str) -> None:
        self.value = message


def _build_connect_dummy() -> object:
    calls = {"begin": 0, "dirty": 0, "redraw": 0}

    class DummyApp:
        def __init__(self) -> None:
            self.nodes = {
                "site_a": SimpleNamespace(node_id="site_a", label="Site A", adjacent_to=set()),
                "route_1": SimpleNamespace(node_id="route_1", label="1", adjacent_to=set()),
            }
            self.interaction = EditorInteractionState()
            self.status_var = _StatusRecorder()
            self._calls = calls

        def _begin_mutation(self) -> None:
            self._calls["begin"] += 1

        def _mark_dirty(self, message: str, redraw: bool = True) -> None:
            self._calls["dirty"] += 1
            self.status_var.set(message)
            if redraw:
                self._redraw()

        def _redraw(self) -> None:
            self._calls["redraw"] += 1

    return DummyApp()


def test_state_history_reports_clean_when_snapshot_matches_baseline() -> None:
    history = EditorStateHistory(max_history=3)
    baseline = {"board_id": "base", "nodes": ["a", "b"]}

    history.mark_saved_baseline(baseline)

    assert history.has_unsaved_changes({"board_id": "base", "nodes": ["a", "c"]})
    assert not history.has_unsaved_changes({"board_id": "base", "nodes": ["a", "b"]})


def test_state_history_begin_mutation_pushes_undo_and_clears_redo() -> None:
    history = EditorStateHistory(max_history=3)
    history.push_redo_snapshot({"step": "redo"})

    history.begin_mutation({"step": "before"})

    assert history.pop_undo_snapshot() == {"step": "before"}
    assert history.pop_redo_snapshot() is None


def test_background_manager_load_from_layout_value_does_not_adopt_size_when_disabled(
    monkeypatch,
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "bg.png"
    image_path.write_bytes(b"fake")

    class FakePhoto:
        def __init__(self, file: str) -> None:
            self._file = file

        def width(self) -> int:
            return 800

        def height(self) -> int:
            return 600

        def zoom(self, _: int, __: int) -> "FakePhoto":
            return self

        def subsample(self, _: int, __: int) -> "FakePhoto":
            return self

    monkeypatch.setattr("interface.background_manager.tk.PhotoImage", FakePhoto)

    manager = BackgroundImageManager()
    adopted, message = manager.load_from_layout_value(
        stored_value=str(image_path),
        layout_path=None,
        adopt_image_size=False,
    )

    assert adopted is None
    assert message is None
    assert manager.image_path == image_path.resolve()


def test_background_manager_clears_state_on_unsupported_format(
    monkeypatch,
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "bad.jpg"
    image_path.write_bytes(b"not-a-real-image")

    manager = BackgroundImageManager()
    manager.image_path = tmp_path / "stale.png"
    manager.source_photo = object()  # type: ignore[assignment]
    manager.photo = object()  # type: ignore[assignment]

    def _raise_tcl_error(*_: object, **__: object) -> None:
        raise tk.TclError("unsupported")

    monkeypatch.setattr("interface.background_manager.tk.PhotoImage", _raise_tcl_error)

    _, message = manager.load_from_layout_value(
        stored_value=str(image_path),
        layout_path=None,
        adopt_image_size=False,
    )

    assert message is not None
    assert "unsupported" in message.lower()
    assert manager.image_path is None
    assert manager.source_photo is None
    assert manager.photo is None


def test_package_manager_background_path_is_relative_inside_layout_dir(tmp_path: Path) -> None:
    layout_path = tmp_path / "layouts" / "layout.json"
    layout_path.parent.mkdir(parents=True)
    image_path = layout_path.parent / "images" / "bg.png"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"fake")

    manager = BoardPackageManager()
    serialized = manager.background_path_for_layout(image_path, layout_path)

    assert serialized == "images/bg.png"


def test_load_background_dialog_does_not_begin_mutation_on_failed_import(
    monkeypatch,
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "bad.png"
    image_path.write_bytes(b"fake")

    calls = {"begin": 0, "error": 0}

    class DummyApp:
        root = None

        def _capture_snapshot(self) -> dict[str, object]:
            return {"snapshot": 1}

        def _set_background_from_path(self, _: Path, adopt_image_size: bool) -> None:
            assert adopt_image_size is True
            raise ValueError("unsupported")

        def _begin_mutation(self, snapshot: dict[str, object] | None = None) -> None:
            calls["begin"] += 1

        def _apply_canvas_size(self) -> None:
            raise AssertionError("Should not apply canvas size when image import fails")

        def _mark_dirty(self, message: str, redraw: bool = True) -> None:
            raise AssertionError("Should not mark dirty when image import fails")

    monkeypatch.setattr(
        "interface.board_creator.filedialog.askopenfilename",
        lambda **_: str(image_path),
    )

    def _record_error(*_: object, **__: object) -> None:
        calls["error"] += 1

    monkeypatch.setattr("interface.board_creator.messagebox.showerror", _record_error)

    BoardCreatorApp._load_background_image_dialog(DummyApp())

    assert calls["begin"] == 0
    assert calls["error"] == 1


def test_connect_click_flow_requires_explicit_finalize_click() -> None:
    app = _build_connect_dummy()

    BoardCreatorApp._handle_connect_click(app, "site_a")
    assert app.interaction.connect_start_node_id == "site_a"
    assert app.interaction.connect_end_node_id is None
    assert app.interaction.selected_node_id is None

    BoardCreatorApp._handle_connect_click(app, "route_1")
    assert app.interaction.connect_start_node_id == "site_a"
    assert app.interaction.connect_end_node_id == "route_1"
    assert app.interaction.selected_node_id == "route_1"
    assert "route_1" in app.nodes["site_a"].adjacent_to
    assert "site_a" in app.nodes["route_1"].adjacent_to

    BoardCreatorApp._handle_connect_click(app, None)
    assert app.interaction.connect_start_node_id is None
    assert app.interaction.connect_end_node_id is None
    assert app.interaction.selected_node_id is None
    assert app._calls["begin"] == 1
    assert app._calls["dirty"] == 1


def test_connect_is_idempotent_for_existing_edge() -> None:
    app = _build_connect_dummy()

    BoardCreatorApp._handle_connect_click(app, "site_a")
    BoardCreatorApp._handle_connect_click(app, "route_1")
    BoardCreatorApp._handle_connect_click(app, None)

    assert app._calls["begin"] == 1
    assert app._calls["dirty"] == 1

    BoardCreatorApp._handle_connect_click(app, "site_a")
    BoardCreatorApp._handle_connect_click(app, "route_1")

    assert app._calls["begin"] == 1
    assert app._calls["dirty"] == 1
    assert "already connected" in app.status_var.value
    assert len(app.nodes["site_a"].adjacent_to) == 1
    assert len(app.nodes["route_1"].adjacent_to) == 1


def test_mode_change_clears_connect_selection_but_keeps_selected_node() -> None:
    calls = {"redraw": 0}

    class _ModeVar:
        def get(self) -> str:
            return "connect"

    class DummyApp:
        def __init__(self) -> None:
            self.mode_var = _ModeVar()
            self.interaction = EditorInteractionState(
                selected_node_id="site_a",
                connect_start_node_id="site_a",
                connect_end_node_id="route_1",
            )
            self.status_var = _StatusRecorder()

        def _redraw(self) -> None:
            calls["redraw"] += 1

    app = DummyApp()

    BoardCreatorApp._on_mode_changed(app)

    assert app.mode.value == "connect"
    assert app.interaction.selected_node_id == "site_a"
    assert app.interaction.connect_start_node_id is None
    assert app.interaction.connect_end_node_id is None
    assert app.status_var.value == "Mode: connect"
    assert calls["redraw"] == 1
