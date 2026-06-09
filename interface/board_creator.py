"""Interactive board creator for topology and layout authoring."""

from __future__ import annotations

import argparse
import copy
import re
import tkinter as tk
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from engine.state import NodeKind
from game_setup.board_package import BoardPackageDefinition
from game_setup.loaders import _read_json, _write_json
from interface._canvas_scroll import bind_canvas_scrolling
from interface.background_manager import BackgroundImageManager
from interface.board_renderer import BoardRenderer
from interface.dialogs import TabularInputDialog
from interface.interaction_state import EditorInteractionState
from interface.package_manager import BoardPackageManager
from interface.state_history import EditorStateHistory
from interface.view_fit import compute_fit_zoom

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_BOARD_PATH = ROOT_DIR / "data" / "boards" / "tyrants_of_the_underdark.json"
DEFAULT_LAYOUT_PATH = ROOT_DIR / "data" / "layouts" / "tyrants_of_the_underdark_layout.json"
LAST_PATHS_FILE = ROOT_DIR / "artifacts" / "board_creator_last.json"

ROUTE_RADIUS = 14


class EditorMode(str, Enum):
    """Available interaction modes for the canvas editor."""

    SELECT = "select"
    ADD_SITE = "add_site"
    ADD_ROUTE = "add_route"
    CONNECT = "connect"
    RESIZE = "resize"


@dataclass
class EditableNode:
    """Mutable editor state that merges board and layout data for one node."""

    node_id: str
    label: str
    kind: NodeKind
    center_x: float
    center_y: float
    bounds: tuple[float, float, float, float] | None
    troop_slots: list[tuple[float, float]]
    troop_capacity: int
    control_vp: int
    total_control_vp_per_turn: int
    initial_vp_tokens: int
    influence_income: int
    white_troop_slot_indices: set[int] = field(default_factory=set)
    adjacent_to: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class SiteMetadata:
    """User-supplied metadata captured when creating a site."""

    label: str
    troop_capacity: int
    control_vp: int
    total_control_vp_per_turn: int
    initial_vp_tokens: int
    influence_income: int
    white_troop_count: int


@dataclass(frozen=True)
class RouteMetadata:
    """User-supplied metadata captured when creating a route."""

    control_vp: int
    total_control_vp_per_turn: int
    initial_vp_tokens: int
    influence_income: int
    has_white_troop: int


class BoardCreatorApp:
    """Tkinter application for authoring board topology and layout data."""

    def __init__(
        self,
        root: tk.Tk,
        board_path: Path | None = None,
        layout_path: Path | None = None,
    ) -> None:
        self.root = root
        self.root.title("Tyrants Board Creator")

        self.board_path: Path | None = None
        self.layout_path: Path | None = None
        self.board_id = "new_board"
        self.layout_id = "new_board_layout"

        # World-space board dimensions (layout coordinates live in this space).
        self.canvas_width = 1400
        self.canvas_height = 900

        self.background_manager = BackgroundImageManager()
        self.package_manager = BoardPackageManager()
        self.history = EditorStateHistory(max_history=100)
        self.renderer = BoardRenderer(route_radius=ROUTE_RADIUS)

        self.nodes: dict[str, EditableNode] = {}
        self.node_order: list[str] = []

        self.mode = EditorMode.SELECT
        self.mode_var = tk.StringVar(value=self.mode.value)
        self.status_var = tk.StringVar(value="Ready")

        self.grid_enabled = tk.BooleanVar(value=False)
        self.grid_size = tk.IntVar(value=20)

        self.zoom_level = 1.0
        self.min_zoom = 0.4
        self.max_zoom = 3.0
        self.zoom_step = 0.2
        self.zoom_factor = 1.15

        self.interaction = EditorInteractionState()

        self.is_dirty = False

        self._build_ui()

        if board_path is not None:
            self._load_package_from_files(board_path=board_path, layout_path=layout_path)
        else:
            self._new_board(board_id="new_board", layout_id="new_board_layout")

    @property
    def background_image_path(self) -> Path | None:
        return self.background_manager.image_path

    @property
    def background_source_photo(self) -> tk.PhotoImage | None:
        return self.background_manager.source_photo

    @property
    def background_photo(self) -> tk.PhotoImage | None:
        return self.background_manager.photo

    def _build_ui(self) -> None:
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="New Board", command=self._new_board_dialog)
        file_menu.add_command(label="Open Board Package", command=self._open_board_package_dialog)
        file_menu.add_separator()
        file_menu.add_command(label="Save", command=self._save)
        file_menu.add_command(label="Save As", command=self._save_as)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)
        menubar.add_cascade(label="File", menu=file_menu)

        edit_menu = tk.Menu(menubar, tearoff=False)
        edit_menu.add_command(label="Undo", command=self._undo)
        edit_menu.add_command(label="Redo", command=self._redo)
        edit_menu.add_separator()
        edit_menu.add_command(label="Edit Selected Node", command=self._edit_selected_node)
        edit_menu.add_command(label="Delete Selected Node", command=self._delete_selected_node)
        menubar.add_cascade(label="Edit", menu=edit_menu)

        view_menu = tk.Menu(menubar, tearoff=False)
        view_menu.add_command(label="Zoom In", command=self._zoom_in)
        view_menu.add_command(label="Zoom Out", command=self._zoom_out)
        view_menu.add_command(label="Reset Zoom", command=self._zoom_reset)
        menubar.add_cascade(label="View", menu=view_menu)

        background_menu = tk.Menu(menubar, tearoff=False)
        background_menu.add_command(label="Load Background Image", command=self._load_background_image_dialog)
        background_menu.add_command(label="Clear Background Image", command=self._clear_background_image)
        background_menu.add_command(label="Set Canvas Size", command=self._set_canvas_size_dialog)
        menubar.add_cascade(label="Background", menu=background_menu)

        node_menu = tk.Menu(menubar, tearoff=False)
        node_menu.add_command(label="Validate Package", command=self._validate_current_package)
        menubar.add_cascade(label="Node", menu=node_menu)

        self.root.config(menu=menubar)

        toolbar = ttk.Frame(self.root, padding=6)
        toolbar.pack(fill=tk.X)

        ttk.Label(toolbar, text="Mode:").pack(side=tk.LEFT, padx=(0, 6))
        ttk.Radiobutton(
            toolbar,
            text="Select",
            variable=self.mode_var,
            value=EditorMode.SELECT.value,
            command=self._on_mode_changed,
        ).pack(side=tk.LEFT)
        ttk.Radiobutton(
            toolbar,
            text="Add Site",
            variable=self.mode_var,
            value=EditorMode.ADD_SITE.value,
            command=self._on_mode_changed,
        ).pack(side=tk.LEFT)
        ttk.Radiobutton(
            toolbar,
            text="Add Route",
            variable=self.mode_var,
            value=EditorMode.ADD_ROUTE.value,
            command=self._on_mode_changed,
        ).pack(side=tk.LEFT)
        ttk.Radiobutton(
            toolbar,
            text="Connect",
            variable=self.mode_var,
            value=EditorMode.CONNECT.value,
            command=self._on_mode_changed,
        ).pack(side=tk.LEFT)
        ttk.Radiobutton(
            toolbar,
            text="Resize",
            variable=self.mode_var,
            value=EditorMode.RESIZE.value,
            command=self._on_mode_changed,
        ).pack(side=tk.LEFT)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)

        ttk.Button(toolbar, text="-", command=self._zoom_out, width=3).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="+", command=self._zoom_in, width=3).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="1:1", command=self._zoom_reset).pack(side=tk.LEFT, padx=(2, 8))

        ttk.Checkbutton(toolbar, text="Snap Grid", variable=self.grid_enabled, command=self._on_grid_toggle).pack(
            side=tk.LEFT
        )
        ttk.Label(toolbar, text="Grid:").pack(side=tk.LEFT, padx=(6, 2))
        grid_spin = ttk.Spinbox(
            toolbar,
            from_=4,
            to=200,
            increment=1,
            textvariable=self.grid_size,
            width=5,
            command=self._on_grid_size_changed,
        )
        grid_spin.pack(side=tk.LEFT)

        ttk.Button(toolbar, text="Save", command=self._save).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(toolbar, text="Validate", command=self._validate_current_package).pack(side=tk.RIGHT)
        ttk.Button(toolbar, text="Redo", command=self._redo).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(toolbar, text="Undo", command=self._undo).pack(side=tk.RIGHT)

        canvas_frame = ttk.Frame(self.root)
        canvas_frame.pack(fill=tk.BOTH, expand=True)
        canvas_frame.columnconfigure(0, weight=1)
        canvas_frame.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(
            canvas_frame,
            width=1000,
            height=700,
            bg="#fbfbfb",
            highlightthickness=0,
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")

        y_scroll = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        x_scroll.grid(row=1, column=0, sticky="ew")
        self.canvas.configure(xscrollcommand=x_scroll.set, yscrollcommand=y_scroll.set)

        self.canvas.bind("<ButtonPress-1>", self._on_canvas_press)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self.canvas.bind("<Double-Button-1>", self._on_canvas_double_click)

        self.canvas.bind("<ButtonPress-3>", self._on_canvas_right_press)
        bind_canvas_scrolling(self.canvas, self._zoom_in, self._zoom_out)

        status = ttk.Label(self.root, textvariable=self.status_var, anchor=tk.W, padding=(8, 4))
        status.pack(fill=tk.X)

        self.root.bind("<Control-s>", self._shortcut_save)
        self.root.bind("<Control-S>", self._shortcut_save_as)
        self.root.bind("<Control-z>", self._shortcut_undo)
        self.root.bind("<Control-y>", self._shortcut_redo)
        self.root.bind("<Delete>", self._shortcut_delete)
        self.root.bind("<e>", self._shortcut_edit)
        self.root.bind("<g>", self._shortcut_toggle_grid)
        self.root.bind("<plus>", self._shortcut_zoom_in)
        self.root.bind("<minus>", self._shortcut_zoom_out)
        self.root.bind("<Key-1>", self._shortcut_mode_select)
        self.root.bind("<Key-2>", self._shortcut_mode_add_site)
        self.root.bind("<Key-3>", self._shortcut_mode_add_route)
        self.root.bind("<Key-4>", self._shortcut_mode_connect)
        self.root.bind("<Key-5>", self._shortcut_mode_resize)

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _shortcut_save(self, _: tk.Event[tk.Misc]) -> str:
        self._save()
        return "break"

    def _shortcut_save_as(self, _: tk.Event[tk.Misc]) -> str:
        self._save_as()
        return "break"

    def _shortcut_undo(self, _: tk.Event[tk.Misc]) -> str:
        self._undo()
        return "break"

    def _shortcut_redo(self, _: tk.Event[tk.Misc]) -> str:
        self._redo()
        return "break"

    def _shortcut_delete(self, _: tk.Event[tk.Misc]) -> str:
        self._delete_selected_node()
        return "break"

    def _shortcut_edit(self, _: tk.Event[tk.Misc]) -> str:
        self._edit_selected_node()
        return "break"

    def _shortcut_toggle_grid(self, _: tk.Event[tk.Misc]) -> str:
        self.grid_enabled.set(not self.grid_enabled.get())
        self._on_grid_toggle()
        return "break"

    def _shortcut_zoom_in(self, _: tk.Event[tk.Misc]) -> str:
        self._zoom_in()
        return "break"

    def _shortcut_zoom_out(self, _: tk.Event[tk.Misc]) -> str:
        self._zoom_out()
        return "break"

    def _shortcut_mode_select(self, _: tk.Event[tk.Misc]) -> str:
        self._set_mode(EditorMode.SELECT)
        return "break"

    def _shortcut_mode_add_site(self, _: tk.Event[tk.Misc]) -> str:
        self._set_mode(EditorMode.ADD_SITE)
        return "break"

    def _shortcut_mode_add_route(self, _: tk.Event[tk.Misc]) -> str:
        self._set_mode(EditorMode.ADD_ROUTE)
        return "break"

    def _shortcut_mode_connect(self, _: tk.Event[tk.Misc]) -> str:
        self._set_mode(EditorMode.CONNECT)
        return "break"

    def _shortcut_mode_resize(self, _: tk.Event[tk.Misc]) -> str:
        self._set_mode(EditorMode.RESIZE)
        return "break"

    def _set_mode(self, mode: EditorMode) -> None:
        self.mode_var.set(mode.value)
        self._on_mode_changed()

    def _on_mode_changed(self) -> None:
        self.mode = EditorMode(self.mode_var.get())
        self.interaction.reset_for_mode_change()
        self.status_var.set(f"Mode: {self.mode.value}")
        self._redraw()

    def _on_grid_toggle(self) -> None:
        self._redraw()
        state = "enabled" if self.grid_enabled.get() else "disabled"
        self.status_var.set(f"Grid snapping {state}")

    def _on_grid_size_changed(self) -> None:
        self.grid_size.set(max(4, int(self.grid_size.get())))
        self._redraw()

    def _zoom_in(self) -> None:
        self._change_zoom(self.zoom_level * self.zoom_factor)

    def _zoom_out(self) -> None:
        self._change_zoom(self.zoom_level / self.zoom_factor)

    def _zoom_reset(self) -> None:
        self._change_zoom(1.0)

    def _change_zoom(self, requested_zoom: float, center_on: tuple[float, float] | None = None) -> None:
        if self.background_image_path is not None:
            requested_zoom = 1.0
        new_zoom = max(self.min_zoom, min(self.max_zoom, requested_zoom))
        if abs(new_zoom - self.zoom_level) < 0.001 and center_on is None:
            return

        old_zoom = self.zoom_level
        old_left = self.canvas.canvasx(0)
        old_top = self.canvas.canvasy(0)

        self.zoom_level = new_zoom
        self._refresh_background_photo()
        self._apply_canvas_size()

        if center_on is not None:
            cx, cy = center_on
            scaled_width = max(1.0, self.canvas_width * self.zoom_level)
            scaled_height = max(1.0, self.canvas_height * self.zoom_level)
            view_w = self.canvas.winfo_width()
            view_h = self.canvas.winfo_height()
            if view_w < 10:
                view_w = int(self.canvas.cget("width"))
            if view_h < 10:
                view_h = int(self.canvas.cget("height"))
            self.canvas.xview_moveto(min(1.0, max(0.0, (cx * self.zoom_level - view_w / 2) / scaled_width)))
            self.canvas.yview_moveto(min(1.0, max(0.0, (cy * self.zoom_level - view_h / 2) / scaled_height)))
        else:
            ratio = self.zoom_level / old_zoom
            scaled_width = max(1.0, self.canvas_width * self.zoom_level)
            scaled_height = max(1.0, self.canvas_height * self.zoom_level)
            self.canvas.xview_moveto(min(1.0, max(0.0, (old_left * ratio) / scaled_width)))
            self.canvas.yview_moveto(min(1.0, max(0.0, (old_top * ratio) / scaled_height)))

        self._redraw()
        self.status_var.set(f"Zoom: {self.zoom_level:.2f}x")

    def _auto_fit_zoom(self) -> None:
        if not self.nodes:
            return

        bboxes: list[tuple[float, float, float, float]] = []
        for node in self.nodes.values():
            if node.bounds is not None:
                left, top, width, height = node.bounds
                bboxes.append((left, top, left + width, top + height))
            else:
                bboxes.append((node.center_x - ROUTE_RADIUS, node.center_y - ROUTE_RADIUS, node.center_x + ROUTE_RADIUS, node.center_y + ROUTE_RADIUS))

        view_w = self.canvas.winfo_width()
        view_h = self.canvas.winfo_height()
        if view_w < 10:
            view_w = int(self.canvas.cget("width"))
        if view_h < 10:
            view_h = int(self.canvas.cget("height"))

        result = compute_fit_zoom(bboxes, view_w, view_h, min_zoom=self.min_zoom, max_zoom=self.max_zoom)
        if result is None:
            return

        self._change_zoom(result.zoom, center_on=(result.center_x, result.center_y))

    def _new_board_dialog(self) -> None:
        if not self._confirm_discard_if_dirty():
            return

        board_id = simpledialog.askstring("Board ID", "Board id:", parent=self.root, initialvalue="new_board")
        if board_id is None:
            return
        board_id = board_id.strip()
        if not board_id:
            messagebox.showerror("Invalid board id", "Board id is required.", parent=self.root)
            return

        layout_id = simpledialog.askstring(
            "Layout ID",
            "Layout id:",
            parent=self.root,
            initialvalue=f"{board_id}_layout",
        )
        if layout_id is None:
            return

        self._new_board(board_id=board_id, layout_id=layout_id.strip() or f"{board_id}_layout")

    def _new_board(self, board_id: str, layout_id: str) -> None:
        self.board_id = board_id
        self.layout_id = layout_id
        self.nodes = {}
        self.node_order = []
        self.interaction.reset()

        self.board_path = None
        self.layout_path = None

        self.background_manager.clear()

        self.canvas_width = 1400
        self.canvas_height = 900
        self.zoom_level = 1.0

        self.history.reset()

        self._refresh_background_photo()
        self._apply_canvas_size()
        self._mark_saved_baseline()
        self.status_var.set("Created a new board package")
        self._redraw()

    def _build_editable_node(self, layout_node: object, board_node: object) -> EditableNode:
        bounds = None
        if layout_node.bounds is not None:
            bounds = (
                layout_node.bounds.x,
                layout_node.bounds.y,
                layout_node.bounds.width,
                layout_node.bounds.height,
            )

        white_indices: set[int] = set()
        initial_slots = getattr(board_node, "initial_troop_slots", None)
        if initial_slots is not None:
            for idx, occupant in enumerate(initial_slots):
                if occupant == "white":
                    white_indices.add(idx)

        return EditableNode(
            node_id=layout_node.node_id,
            label=layout_node.label,
            kind=layout_node.kind,
            center_x=layout_node.center.x,
            center_y=layout_node.center.y,
            bounds=bounds,
            troop_slots=[(slot.x, slot.y) for slot in layout_node.troop_slots],
            troop_capacity=board_node.troop_capacity,
            control_vp=board_node.control_vp,
            total_control_vp_per_turn=getattr(board_node, "total_control_vp_per_turn", 0),
            initial_vp_tokens=board_node.initial_vp_tokens,
            influence_income=getattr(board_node, "influence_income", 0),
            white_troop_slot_indices=white_indices,
            adjacent_to=set(board_node.adjacent_to),
        )

    def _open_board_package_dialog(self) -> None:
        if not self._confirm_discard_if_dirty():
            return

        selected_board = filedialog.askopenfilename(
            parent=self.root,
            title="Select board topology JSON",
            initialdir=(ROOT_DIR / "data" / "boards"),
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if not selected_board:
            return

        layout_path: Path | None = None
        if messagebox.askyesno("Load layout", "Load an existing layout JSON for this board?", parent=self.root):
            selected_layout = filedialog.askopenfilename(
                parent=self.root,
                title="Select board layout JSON",
                initialdir=(ROOT_DIR / "data" / "layouts"),
                filetypes=[("JSON", "*.json"), ("All files", "*.*")],
            )
            if not selected_layout:
                return
            layout_path = Path(selected_layout)

        self._load_package_from_files(board_path=Path(selected_board), layout_path=layout_path)

    def _load_package_from_files(self, board_path: Path, layout_path: Path | None) -> None:
        try:
            package = self.package_manager.load_package(board_path=board_path, layout_path=layout_path)
        except ValueError as error:
            messagebox.showerror("Invalid board package", str(error), parent=self.root)
            return

        self.board_id = package.board.board_id
        self.layout_id = package.layout.layout_id
        self.board_path = board_path
        self.layout_path = layout_path
        self.canvas_width = package.layout.canvas.width
        self.canvas_height = package.layout.canvas.height
        self.zoom_level = 1.0

        self.nodes, self.node_order = self.package_manager.materialize_nodes(
            package,
            node_factory=self._build_editable_node,
        )

        self.interaction.reset()

        self.history.reset()

        self._load_background_from_layout_value(package.layout.canvas.background_image)
        self._apply_canvas_size()
        self._mark_saved_baseline()
        self.status_var.set(f"Loaded board '{self.board_id}'")
        self._redraw()
        self.root.after(100, self._auto_fit_zoom)
        _save_last_paths(board_path, layout_path)

    def _load_background_from_layout_value(self, stored_value: str | None) -> None:
        _, message = self.background_manager.load_from_layout_value(
            stored_value=stored_value,
            layout_path=self.layout_path,
            adopt_image_size=False,
        )
        self._refresh_background_photo()
        if message is not None:
            self.status_var.set(message)

    def _set_background_from_path(self, image_path: Path | None, adopt_image_size: bool) -> None:
        adopted_size = self.background_manager.set_from_path(image_path, adopt_image_size=adopt_image_size)
        if adopted_size is not None:
            self.canvas_width, self.canvas_height = adopted_size
        self._refresh_background_photo()

    def _refresh_background_photo(self) -> None:
        self.background_manager.refresh_for_zoom(self.zoom_level)

    def _save(self) -> None:
        if self.board_path is None or self.layout_path is None:
            self._save_as()
            return

        self._save_to_paths(self.board_path, self.layout_path)

    def _save_as(self) -> None:
        selected_board = filedialog.asksaveasfilename(
            parent=self.root,
            title="Save board topology JSON",
            initialdir=(ROOT_DIR / "data" / "boards"),
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if not selected_board:
            return

        selected_layout = filedialog.asksaveasfilename(
            parent=self.root,
            title="Save board layout JSON",
            initialdir=(ROOT_DIR / "data" / "layouts"),
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if not selected_layout:
            return

        self._save_to_paths(Path(selected_board), Path(selected_layout))

    def _save_to_paths(self, board_path: Path, layout_path: Path) -> None:
        try:
            package = self._build_package(layout_path=layout_path)
        except ValueError as error:
            messagebox.showerror("Validation failed", str(error), parent=self.root)
            return

        self.package_manager.save_package(package=package, board_path=board_path, layout_path=layout_path)
        self.board_path = board_path
        self.layout_path = layout_path
        self._mark_saved_baseline()
        self.status_var.set(f"Saved board package: {board_path.name} + {layout_path.name}")
        _save_last_paths(board_path, layout_path)

    def _validate_current_package(self) -> None:
        try:
            self._build_package(layout_path=self.layout_path)
        except ValueError as error:
            messagebox.showerror("Validation failed", str(error), parent=self.root)
            return

        messagebox.showinfo("Validation", "Board package is valid.", parent=self.root)

    def _build_package(self, layout_path: Path | None) -> BoardPackageDefinition:
        return self.package_manager.build_package(
            board_id=self.board_id,
            layout_id=self.layout_id,
            canvas_width=self.canvas_width,
            canvas_height=self.canvas_height,
            nodes=self.nodes,
            node_order=self.node_order,
            background_image_path=self.background_image_path,
            layout_path=layout_path,
        )

    def _background_path_for_layout(self, layout_path: Path | None) -> str | None:
        return self.package_manager.background_path_for_layout(self.background_image_path, layout_path)

    def _set_canvas_size_dialog(self) -> None:
        width = simpledialog.askinteger(
            "Canvas width",
            "Canvas width (pixels):",
            parent=self.root,
            minvalue=200,
            initialvalue=self.canvas_width,
        )
        if width is None:
            return

        height = simpledialog.askinteger(
            "Canvas height",
            "Canvas height (pixels):",
            parent=self.root,
            minvalue=200,
            initialvalue=self.canvas_height,
        )
        if height is None:
            return

        self._begin_mutation()
        self.canvas_width = width
        self.canvas_height = height
        self._apply_canvas_size()
        self._mark_dirty("Updated canvas size")

    def _apply_canvas_size(self) -> None:
        scaled_width = max(1, int(round(self.canvas_width * self.zoom_level)))
        scaled_height = max(1, int(round(self.canvas_height * self.zoom_level)))
        self.canvas.config(scrollregion=(0, 0, scaled_width, scaled_height))

    def _load_background_image_dialog(self) -> None:
        selected_path = filedialog.askopenfilename(
            parent=self.root,
            title="Select background image",
            initialdir=ROOT_DIR,
            filetypes=[
                ("Image files", "*.png *.gif *.ppm *.pgm"),
                ("PNG", "*.png"),
                ("GIF", "*.gif"),
                ("All files", "*.*"),
            ],
        )
        if not selected_path:
            return

        mutation_snapshot = self._capture_snapshot()
        try:
            self._set_background_from_path(Path(selected_path), adopt_image_size=True)
        except ValueError:
            messagebox.showerror(
                "Unsupported image",
                "Tk PhotoImage supports PNG/GIF/PPM/PGM by default.",
                parent=self.root,
            )
            return

        self._begin_mutation(snapshot=mutation_snapshot)
        self._apply_canvas_size()
        self._change_zoom(1.0)
        self._mark_dirty("Loaded background image")

    def _clear_background_image(self) -> None:
        if self.background_image_path is None:
            return
        self._begin_mutation()
        self._set_background_from_path(None, adopt_image_size=False)
        self._auto_fit_zoom()
        self._mark_dirty("Cleared background image")

    def _event_to_world(self, event: tk.Event[tk.Canvas]) -> tuple[float, float]:
        canvas_x = self.canvas.canvasx(event.x)
        canvas_y = self.canvas.canvasy(event.y)
        return (canvas_x / self.zoom_level, canvas_y / self.zoom_level)

    def _to_screen(self, x: float, y: float) -> tuple[float, float]:
        return (x * self.zoom_level, y * self.zoom_level)

    def _scaled(self, distance: float) -> float:
        return distance * self.zoom_level

    def _snap_point(self, x: float, y: float) -> tuple[float, float]:
        if not self.grid_enabled.get():
            return (x, y)
        size = max(4, int(self.grid_size.get()))
        return (round(x / size) * size, round(y / size) * size)

    def _start_drag_tracking(self) -> None:
        self.interaction.drag_started_snapshot = self._capture_snapshot()
        self.interaction.drag_changed = False

    def _commit_drag_history(self, message: str) -> None:
        if not self.interaction.drag_changed or self.interaction.drag_started_snapshot is None:
            self.interaction.drag_started_snapshot = None
            self.interaction.drag_changed = False
            return

        self._begin_mutation(snapshot=self.interaction.drag_started_snapshot)
        self.interaction.drag_started_snapshot = None
        self.interaction.drag_changed = False
        self._update_dirty_state()
        self.status_var.set(message)

    def _on_canvas_press(self, event: tk.Event[tk.Canvas]) -> None:
        x, y = self._event_to_world(event)

        if self.interaction.pending_slot_node_id is not None:
            self._capture_site_slot(x, y)
            return

        if self.mode == EditorMode.ADD_SITE:
            self.interaction.site_drag_start = self._snap_point(x, y)
            if self.interaction.site_preview_rect_id is not None:
                self.canvas.delete(self.interaction.site_preview_rect_id)
            start_x, start_y = self._to_screen(*self.interaction.site_drag_start)
            self.interaction.site_preview_rect_id = self.canvas.create_rectangle(
                start_x,
                start_y,
                start_x,
                start_y,
                outline="#2e66d0",
                width=max(1, int(round(self._scaled(2)))),
                dash=(4, 3),
            )
            return

        if self.mode == EditorMode.ADD_ROUTE:
            snapped = self._snap_point(x, y)
            self._create_route_node(*snapped)
            return

        if self.mode == EditorMode.RESIZE:
            clicked_node_id = self._find_node_at(x, y)
            if clicked_node_id is not None:
                node = self.nodes[clicked_node_id]
                if node.kind == NodeKind.SITE and node.bounds is not None:
                    self._begin_resize(clicked_node_id, x, y)
            return

        clicked_node_id = self._find_node_at(x, y)
        if self.mode == EditorMode.CONNECT:
            self._handle_connect_click(clicked_node_id)
            return

        self.interaction.selected_node_id = clicked_node_id
        self.interaction.connect_start_node_id = None
        self.interaction.connect_end_node_id = None

        if clicked_node_id is not None:
            self.interaction.dragging_node_id = clicked_node_id
            self.interaction.drag_last = (x, y)
            self._start_drag_tracking()
        else:
            self.interaction.clear_drag_state()

        self._redraw()

    def _on_canvas_drag(self, event: tk.Event[tk.Canvas]) -> None:
        x, y = self._event_to_world(event)

        if (
            self.mode == EditorMode.ADD_SITE
            and self.interaction.site_drag_start is not None
            and self.interaction.site_preview_rect_id is not None
        ):
            start_x, start_y = self.interaction.site_drag_start
            sx1, sy1 = self._to_screen(start_x, start_y)
            sx2, sy2 = self._to_screen(x, y)
            self.canvas.coords(self.interaction.site_preview_rect_id, sx1, sy1, sx2, sy2)
            return

        if (
            self.mode == EditorMode.SELECT
            and self.interaction.dragging_node_id is not None
            and self.interaction.drag_last is not None
        ):
            prev_x, prev_y = self.interaction.drag_last
            dx = x - prev_x
            dy = y - prev_y
            self.interaction.drag_last = (x, y)
            if abs(dx) > 0.0001 or abs(dy) > 0.0001:
                self.interaction.drag_changed = True
                self._translate_node(self.interaction.dragging_node_id, dx, dy)
                self._update_dirty_state()
                self.status_var.set("Moved node")
                self._redraw()

        if (
            self.mode == EditorMode.RESIZE
            and self.interaction.resize_node_id is not None
            and self.interaction.resize_anchor is not None
            and self.interaction.resize_preview_rect_id is not None
        ):
            ax, ay = self.interaction.resize_anchor
            ex, ey = self._snap_point(x, y)
            self._draw_resize_preview(ax, ay, ex, ey)
            return

    def _on_canvas_release(self, event: tk.Event[tk.Canvas]) -> None:
        x, y = self._event_to_world(event)

        if self.mode == EditorMode.ADD_SITE and self.interaction.site_drag_start is not None:
            start_x, start_y = self.interaction.site_drag_start
            self.interaction.site_drag_start = None

            if self.interaction.site_preview_rect_id is not None:
                self.canvas.delete(self.interaction.site_preview_rect_id)
                self.interaction.site_preview_rect_id = None

            end_x, end_y = self._snap_point(x, y)
            if abs(end_x - start_x) < 8 or abs(end_y - start_y) < 8:
                self.status_var.set("Site rectangle is too small")
                return

            self._create_site_node(start_x, start_y, end_x, end_y)
            return

        if self.mode == EditorMode.SELECT and self.interaction.dragging_node_id is not None:
            if self.interaction.drag_changed and self.grid_enabled.get():
                self._snap_node_to_grid(self.interaction.dragging_node_id)
            self._commit_drag_history("Moved node")
            self.interaction.dragging_node_id = None
            self.interaction.drag_last = None
            self._redraw()
            return

        if self.mode == EditorMode.RESIZE and self.interaction.resize_node_id is not None:
            self._finish_resize(x, y)
            return

        self.interaction.dragging_node_id = None
        self.interaction.drag_last = None

    def _on_canvas_right_press(self, event: tk.Event[tk.Canvas]) -> None:
        x, y = self._event_to_world(event)
        node_id = self._find_node_at(x, y)
        if node_id is not None and self.nodes[node_id].kind == NodeKind.SITE:
            self.interaction.selected_node_id = node_id
            self._show_site_context_menu(event.x_root, event.y_root, node_id)

    def _on_canvas_double_click(self, event: tk.Event[tk.Canvas]) -> None:
        x, y = self._event_to_world(event)
        node_id = self._find_node_at(x, y)

        if self.mode == EditorMode.RESIZE:
            if node_id is None or self.nodes[node_id].kind != NodeKind.SITE:
                self._set_mode(EditorMode.SELECT)
                return

        if node_id is not None and self.nodes[node_id].kind == NodeKind.SITE:
            self.interaction.selected_node_id = node_id
            self._edit_selected_site(self.nodes[node_id])
            self._redraw()

    def _show_site_context_menu(self, root_x: int, root_y: int, node_id: str) -> None:
        menu = tk.Menu(self.root, tearoff=False)
        menu.add_command(
            label="Properties",
            command=lambda: self._context_edit_site(node_id),
        )
        menu.add_command(
            label="Resize",
            command=lambda: self._context_start_resize(node_id),
        )
        menu.tk_popup(root_x, root_y)

    def _context_edit_site(self, node_id: str) -> None:
        node = self.nodes.get(node_id)
        if node is not None:
            self.interaction.selected_node_id = node_id
            self._edit_selected_site(node)
            self._redraw()

    def _context_start_resize(self, node_id: str) -> None:
        self._set_mode(EditorMode.RESIZE)
        self.interaction.selected_node_id = node_id
        self.status_var.set(f"Resize mode — drag '{self.nodes[node_id].label}'")
        self._redraw()

    def _begin_resize(self, node_id: str, click_x: float, click_y: float) -> None:
        node = self.nodes[node_id]
        if node.bounds is None:
            return

        left, top, width, height = node.bounds
        right = left + width
        bottom = top + height

        cx = left + width / 2
        cy = top + height / 2

        anchor_x = left if click_x >= cx else right
        anchor_y = top if click_y >= cy else bottom

        self.interaction.resize_node_id = node_id
        self.interaction.resize_anchor = (anchor_x, anchor_y)
        self._draw_resize_preview(anchor_x, anchor_y, click_x, click_y)

    def _draw_resize_preview(self, ax: float, ay: float, bx: float, by: float) -> None:
        if self.interaction.resize_preview_rect_id is not None:
            self.canvas.delete(self.interaction.resize_preview_rect_id)
        x1 = min(ax, bx)
        y1 = min(ay, by)
        x2 = max(ax, bx)
        y2 = max(ay, by)
        sx1, sy1 = self._to_screen(x1, y1)
        sx2, sy2 = self._to_screen(x2, y2)
        self.interaction.resize_preview_rect_id = self.canvas.create_rectangle(
            sx1,
            sy1,
            sx2,
            sy2,
            outline="#d97706",
            width=max(1, int(round(self._scaled(2)))),
            dash=(4, 3),
        )

    def _finish_resize(self, x: float, y: float) -> None:
        anchor = self.interaction.resize_anchor
        resize_node_id = self.interaction.resize_node_id
        if anchor is None or resize_node_id is None:
            return

        if self.interaction.resize_preview_rect_id is not None:
            self.canvas.delete(self.interaction.resize_preview_rect_id)
            self.interaction.resize_preview_rect_id = None

        end_x, end_y = self._snap_point(x, y)
        ax, ay = anchor

        left = min(ax, end_x)
        top = min(ay, end_y)
        width = abs(ax - end_x)
        height = abs(ay - end_y)

        if width < 8 or height < 8:
            self.status_var.set("Resize too small")
            self.interaction.resize_node_id = None
            self.interaction.resize_anchor = None
            self._redraw()
            return

        node = self.nodes[resize_node_id]
        self._begin_mutation()
        node.bounds = (left, top, width, height)
        node.center_x = left + width / 2
        node.center_y = top + height / 2
        node.troop_slots = self._compute_site_troop_slots(
            left, top, width, height, node.troop_capacity
        )
        self.interaction.resize_node_id = None
        self.interaction.resize_anchor = None
        self.interaction.selected_node_id = resize_node_id
        self._mark_dirty(f"Site '{node.label}' resized", redraw=True)

    @staticmethod
    def _compute_site_troop_slots(
        left: float, top: float, width: float, height: float, capacity: int
    ) -> list[tuple[float, float]]:
        spacing_x = width / (capacity + 1)
        row_y = top + (height / 2)
        return [
            (left + spacing_x * (slot_index + 1), row_y)
            for slot_index in range(capacity)
        ]

    def _create_site_node(self, x1: float, y1: float, x2: float, y2: float) -> None:
        metadata = self._prompt_site_metadata()
        if metadata is None:
            self.status_var.set("Site creation cancelled")
            return

        if not self._is_label_available(metadata.label):
            messagebox.showerror("Duplicate name", "A node with that name already exists.", parent=self.root)
            return

        left = min(x1, x2)
        top = min(y1, y2)
        width = abs(x2 - x1)
        height = abs(y2 - y1)

        node_id = self._unique_node_id(self._site_node_id_seed(metadata.label))
        center_x = left + (width / 2)
        center_y = top + (height / 2)

        self._begin_mutation()
        self.nodes[node_id] = EditableNode(
            node_id=node_id,
            label=metadata.label,
            kind=NodeKind.SITE,
            center_x=center_x,
            center_y=center_y,
            bounds=(left, top, width, height),
            troop_slots=self._compute_site_troop_slots(
                left, top, width, height, metadata.troop_capacity
            ),
            troop_capacity=metadata.troop_capacity,
            control_vp=metadata.control_vp,
            total_control_vp_per_turn=metadata.total_control_vp_per_turn,
            initial_vp_tokens=metadata.initial_vp_tokens,
            influence_income=metadata.influence_income,
            white_troop_slot_indices=set(range(metadata.white_troop_count)),
        )
        self.node_order.append(node_id)
        self.interaction.selected_node_id = node_id
        self._mark_dirty(
            f"Site '{metadata.label}' created.",
            redraw=True,
        )

    def _create_route_node(self, x: float, y: float) -> None:
        metadata = self._prompt_route_metadata()
        if metadata is None:
            self.status_var.set("Route creation cancelled")
            return

        route_number = self._next_route_number()
        label = str(route_number)
        node_id = self._unique_node_id(f"route_{label}")

        self._begin_mutation()
        self.nodes[node_id] = EditableNode(
            node_id=node_id,
            label=label,
            kind=NodeKind.ROUTE,
            center_x=x,
            center_y=y,
            bounds=None,
            troop_slots=[],
            troop_capacity=1,
            control_vp=metadata.control_vp,
            total_control_vp_per_turn=metadata.total_control_vp_per_turn,
            initial_vp_tokens=metadata.initial_vp_tokens,
            influence_income=metadata.influence_income,
            white_troop_slot_indices={0} if metadata.has_white_troop else set(),
        )
        self.node_order.append(node_id)
        self.interaction.selected_node_id = node_id
        self._mark_dirty(f"Route {label} created", redraw=True)

    def _capture_site_slot(self, x: float, y: float) -> None:
        assert self.interaction.pending_slot_node_id is not None

        node = self.nodes[self.interaction.pending_slot_node_id]
        if node.bounds is None:
            self.interaction.pending_slot_node_id = None
            return

        left, top, width, height = node.bounds
        if x < left or x > left + width or y < top or y > top + height:
            self.status_var.set("Troop slot must be inside the site rectangle")
            return

        self._begin_mutation()
        snapped = self._snap_point(x, y)
        node.troop_slots.append(snapped)
        remaining = node.troop_capacity - len(node.troop_slots)
        if remaining > 0:
            self._mark_dirty(f"Captured slot. {remaining} remaining.", redraw=True)
            return

        self.interaction.pending_slot_node_id = None
        self._mark_dirty(f"Site '{node.label}' completed", redraw=True)

    def _handle_connect_click(self, clicked_node_id: str | None) -> None:
        if self.interaction.connect_start_node_id is not None and self.interaction.connect_end_node_id is not None:
            self.interaction.connect_start_node_id = None
            self.interaction.connect_end_node_id = None
            self.interaction.selected_node_id = None
            self.status_var.set("Connection finalized")
            self._redraw()
            return

        if clicked_node_id is None:
            if self.interaction.connect_start_node_id is not None:
                self.interaction.connect_start_node_id = None
                self.interaction.connect_end_node_id = None
                self.interaction.selected_node_id = None
                self.status_var.set("Connect selection cleared")
                self._redraw()
                return
            self.status_var.set("Select a node to connect")
            return

        if self.interaction.connect_start_node_id is None:
            self.interaction.connect_start_node_id = clicked_node_id
            self.interaction.connect_end_node_id = None
            self.interaction.selected_node_id = None
            self.status_var.set(f"Connecting from '{self.nodes[clicked_node_id].label}'. Select another node.")
            self._redraw()
            return

        if self.interaction.connect_start_node_id == clicked_node_id:
            self.status_var.set("Select a different second node")
            self._redraw()
            return

        first = self.nodes[self.interaction.connect_start_node_id]
        second = self.nodes[clicked_node_id]
        self.interaction.connect_end_node_id = clicked_node_id
        self.interaction.selected_node_id = clicked_node_id

        if second.node_id in first.adjacent_to:
            self.status_var.set(
                f"'{first.label}' and '{second.label}' are already connected. Click once to finalize selection."
            )
            self._redraw()
            return

        self._begin_mutation()
        first.adjacent_to.add(second.node_id)
        second.adjacent_to.add(first.node_id)
        self._mark_dirty(
            f"Connected '{first.label}' and '{second.label}'. Click once more to finalize selection.",
            redraw=True,
        )

    def _translate_node(self, node_id: str, dx: float, dy: float) -> None:
        node = self.nodes[node_id]
        node.center_x += dx
        node.center_y += dy

        if node.bounds is not None:
            left, top, width, height = node.bounds
            node.bounds = (left + dx, top + dy, width, height)
            node.troop_slots = [(slot_x + dx, slot_y + dy) for slot_x, slot_y in node.troop_slots]

    def _snap_node_to_grid(self, node_id: str) -> None:
        node = self.nodes[node_id]
        snapped_center = self._snap_point(node.center_x, node.center_y)
        dx = snapped_center[0] - node.center_x
        dy = snapped_center[1] - node.center_y
        if abs(dx) <= 0.0001 and abs(dy) <= 0.0001:
            return

        self._translate_node(node_id, dx, dy)
        if node.kind == NodeKind.SITE:
            node.troop_slots = [self._snap_point(slot_x, slot_y) for slot_x, slot_y in node.troop_slots]

    def _find_node_at(self, x: float, y: float) -> str | None:
        for node_id in reversed(self.node_order):
            node = self.nodes[node_id]

            if node.kind == NodeKind.SITE and node.bounds is not None:
                left, top, width, height = node.bounds
                if left <= x <= left + width and top <= y <= top + height:
                    return node_id

            if node.kind == NodeKind.ROUTE:
                distance_sq = (node.center_x - x) ** 2 + (node.center_y - y) ** 2
                if distance_sq <= ROUTE_RADIUS**2:
                    return node_id

        return None

    def _prompt_site_metadata(self) -> SiteMetadata | None:
        fields = [
            ("label", "Site name", "str"),
            ("troop_capacity", "Troop capacity", "int"),
            ("white_troop_count", "Starting white troops", "int"),
            ("control_vp", "Control VP (end game)", "int"),
            ("influence_income", "Influence/turn (control)", "int"),
            ("total_control_vp_per_turn", "Total Control VP/turn", "int"),
        ]
        initial = {
            "troop_capacity": "2",
            "white_troop_count": "0",
            "control_vp": "0",
            "influence_income": "0",
            "total_control_vp_per_turn": "0",
        }

        while True:
            dialog = TabularInputDialog(
                parent=self.root,
                title="New Site",
                fields=fields,
                initial_values=initial,
            )
            result = dialog.result
            if result is None:
                return None

            label = str(result["label"]).strip()
            if not label:
                messagebox.showerror("Invalid name", "Site name is required.", parent=self.root)
                continue
            if not self._is_label_available(label):
                messagebox.showerror("Duplicate name", "A node with that name already exists.", parent=self.root)
                continue

            troop_capacity = int(result["troop_capacity"])
            if troop_capacity < 1 or troop_capacity > 6:
                messagebox.showerror("Invalid value", "Troop capacity must be between 1 and 6.", parent=self.root)
                continue

            white_troop_count = int(result["white_troop_count"])
            if white_troop_count < 0 or white_troop_count > troop_capacity:
                messagebox.showerror("Invalid value", f"White troops must be between 0 and {troop_capacity}.", parent=self.root)
                continue

            control_vp = int(result["control_vp"])
            if control_vp < 0:
                messagebox.showerror("Invalid value", "Control VP must be 0 or more.", parent=self.root)
                continue

            influence_income = int(result["influence_income"])
            if influence_income < 0:
                messagebox.showerror("Invalid value", "Influence income must be 0 or more.", parent=self.root)
                continue

            total_control_vp_per_turn = int(result["total_control_vp_per_turn"])
            if total_control_vp_per_turn < 0:
                messagebox.showerror("Invalid value", "Total Control VP/turn must be 0 or more.", parent=self.root)
                continue

            return SiteMetadata(
                label=label,
                troop_capacity=troop_capacity,
                control_vp=control_vp,
                total_control_vp_per_turn=total_control_vp_per_turn,
                initial_vp_tokens=0,
                influence_income=influence_income,
                white_troop_count=white_troop_count,
            )

    def _prompt_route_metadata(self) -> RouteMetadata | None:
        fields = [
            ("control_vp", "VP value", "int"),
            ("has_white_troop", "Starting white troop (1=yes, 0=no)", "int"),
        ]
        initial = {
            "control_vp": "0",
            "has_white_troop": "0",
        }

        while True:
            dialog = TabularInputDialog(
                parent=self.root,
                title="New Route",
                fields=fields,
                initial_values=initial,
            )
            result = dialog.result
            if result is None:
                return None

            control_vp = int(result["control_vp"])
            if control_vp < 0:
                messagebox.showerror("Invalid value", "VP value must be 0 or more.", parent=self.root)
                continue

            has_white_troop = int(result["has_white_troop"])
            if has_white_troop not in (0, 1):
                messagebox.showerror("Invalid value", "White troop must be 0 or 1.", parent=self.root)
                continue

            return RouteMetadata(
                control_vp=control_vp,
                total_control_vp_per_turn=0,
                initial_vp_tokens=0,
                influence_income=0,
                has_white_troop=has_white_troop,
            )

    def _edit_selected_node(self) -> None:
        if self.interaction.selected_node_id is None:
            messagebox.showinfo("Edit node", "Select a node first.", parent=self.root)
            return

        node = self.nodes[self.interaction.selected_node_id]
        if node.kind == NodeKind.SITE:
            self._edit_selected_site(node)
            return

        self._edit_selected_route(node)

    def _edit_selected_site(self, node: EditableNode) -> None:
        fields = [
            ("label", "Site name", "str"),
            ("troop_capacity", "Troop capacity", "int"),
            ("white_troop_count", "Starting white troops", "int"),
            ("control_vp", "Control VP (end game)", "int"),
            ("influence_income", "Influence/turn (control)", "int"),
            ("total_control_vp_per_turn", "Total Control VP/turn", "int"),
        ]
        initial = {
            "label": node.label,
            "troop_capacity": str(node.troop_capacity),
            "white_troop_count": str(len(node.white_troop_slot_indices)),
            "control_vp": str(node.control_vp),
            "influence_income": str(node.influence_income),
            "total_control_vp_per_turn": str(node.total_control_vp_per_turn),
        }

        while True:
            dialog = TabularInputDialog(
                parent=self.root,
                title="Edit Site",
                fields=fields,
                initial_values=initial,
            )
            result = dialog.result
            if result is None:
                return

            label = str(result["label"]).strip()
            if not label:
                messagebox.showerror("Invalid name", "Site name is required.", parent=self.root)
                continue
            if not self._is_label_available(label, ignore_node_id=node.node_id):
                messagebox.showerror("Duplicate name", "A node with that name already exists.", parent=self.root)
                continue

            troop_capacity = int(result["troop_capacity"])
            if troop_capacity < 1 or troop_capacity > 6:
                messagebox.showerror("Invalid value", "Troop capacity must be between 1 and 6.", parent=self.root)
                continue

            white_troop_count = int(result["white_troop_count"])
            if white_troop_count < 0 or white_troop_count > troop_capacity:
                messagebox.showerror("Invalid value", f"White troops must be between 0 and {troop_capacity}.", parent=self.root)
                continue

            control_vp = int(result["control_vp"])
            if control_vp < 0:
                messagebox.showerror("Invalid value", "Control VP must be 0 or more.", parent=self.root)
                continue

            influence_income = int(result["influence_income"])
            if influence_income < 0:
                messagebox.showerror("Invalid value", "Influence income must be 0 or more.", parent=self.root)
                continue

            total_control_vp_per_turn = int(result["total_control_vp_per_turn"])
            if total_control_vp_per_turn < 0:
                messagebox.showerror("Invalid value", "Total Control VP/turn must be 0 or more.", parent=self.root)
                continue

            self._begin_mutation()
            node.label = label
            node.troop_capacity = troop_capacity
            node.control_vp = control_vp
            node.total_control_vp_per_turn = total_control_vp_per_turn
            node.influence_income = influence_income
            node.white_troop_slot_indices = set(range(white_troop_count))

            if node.bounds is not None:
                node.troop_slots = self._compute_site_troop_slots(
                    node.bounds[0], node.bounds[1], node.bounds[2], node.bounds[3], troop_capacity
                )

            self._mark_dirty("Site updated", redraw=True)
            return

    def _edit_selected_route(self, node: EditableNode) -> None:
        control_vp = simpledialog.askinteger(
            "Edit Route VP Value",
            "VP value:",
            parent=self.root,
            minvalue=0,
            initialvalue=node.control_vp,
        )
        if control_vp is None:
            return

        has_white = messagebox.askyesno(
            "Edit Route White Troop",
            "Does this route start with a white troop?",
            parent=self.root,
        )
        if has_white is None:
            return

        self._begin_mutation()
        node.control_vp = control_vp
        node.white_troop_slot_indices = {0} if has_white else set()
        self._mark_dirty(f"Route {node.label} updated", redraw=True)

    def _delete_selected_node(self) -> None:
        if self.interaction.selected_node_id is None:
            messagebox.showinfo("Delete node", "Select a node first.", parent=self.root)
            return

        node = self.nodes[self.interaction.selected_node_id]
        if not messagebox.askyesno(
            "Delete node",
            f"Delete '{node.label}' and remove all of its connections?",
            parent=self.root,
        ):
            return

        self._begin_mutation()
        for neighbor_id in list(node.adjacent_to):
            self.nodes[neighbor_id].adjacent_to.discard(node.node_id)

        self.node_order.remove(node.node_id)
        del self.nodes[node.node_id]
        if self.interaction.pending_slot_node_id == node.node_id:
            self.interaction.pending_slot_node_id = None
        self.interaction.selected_node_id = None
        self.interaction.connect_start_node_id = None
        self.interaction.connect_end_node_id = None

        self._mark_dirty("Node deleted", redraw=True)

    def _next_route_number(self) -> int:
        numbers = [
            int(node.label)
            for node in self.nodes.values()
            if node.kind == NodeKind.ROUTE and node.label.isdigit()
        ]
        return max(numbers, default=0) + 1

    def _site_node_id_seed(self, label: str) -> str:
        normalized = re.sub(r"[^a-z0-9]+", "_", label.strip().lower()).strip("_")
        if not normalized:
            normalized = "site"
        if not normalized.startswith("site_"):
            normalized = f"site_{normalized}"
        return normalized

    def _unique_node_id(self, seed: str) -> str:
        candidate = seed
        suffix = 2
        while candidate in self.nodes:
            candidate = f"{seed}_{suffix}"
            suffix += 1
        return candidate

    def _is_label_available(self, label: str, ignore_node_id: str | None = None) -> bool:
        normalized = label.strip().casefold()
        for node_id, node in self.nodes.items():
            if node_id == ignore_node_id:
                continue
            if node.label.strip().casefold() == normalized:
                return False
        return True

    def _capture_snapshot(self) -> dict[str, object]:
        snapshot = {
            "board_id": self.board_id,
            "layout_id": self.layout_id,
            "canvas_width": self.canvas_width,
            "canvas_height": self.canvas_height,
            "zoom_level": self.zoom_level,
            "background_image_path": self.background_manager.snapshot_value(),
            "nodes": copy.deepcopy(self.nodes),
            "node_order": list(self.node_order),
        }
        snapshot.update(self.interaction.capture_snapshot_fields())
        return snapshot

    def _capture_dirty_snapshot(self) -> dict[str, object]:
        return {
            "board_id": self.board_id,
            "layout_id": self.layout_id,
            "canvas_width": self.canvas_width,
            "canvas_height": self.canvas_height,
            "background_image_path": self.background_manager.snapshot_value(),
            "nodes": copy.deepcopy(self.nodes),
            "node_order": list(self.node_order),
        }

    def _restore_snapshot(self, snapshot: dict[str, object]) -> None:
        self.board_id = str(snapshot["board_id"])
        self.layout_id = str(snapshot["layout_id"])
        self.canvas_width = int(snapshot["canvas_width"])
        self.canvas_height = int(snapshot["canvas_height"])
        self.zoom_level = float(snapshot.get("zoom_level", 1.0))
        self.nodes = copy.deepcopy(snapshot["nodes"])
        self.node_order = list(snapshot["node_order"])
        self.interaction.restore_snapshot_fields(snapshot)

        self.background_manager.restore_from_snapshot_value(snapshot.get("background_image_path"), adopt_image_size=False)

        self._refresh_background_photo()
        self._apply_canvas_size()
        self._update_dirty_state()
        self._redraw()

    def _push_undo_snapshot(self, snapshot: dict[str, object]) -> None:
        self.history.push_undo_snapshot(snapshot)

    def _begin_mutation(self, snapshot: dict[str, object] | None = None) -> None:
        if snapshot is None:
            snapshot = self._capture_snapshot()
        self.history.begin_mutation(snapshot)

    def _undo(self) -> None:
        snapshot = self.history.pop_undo_snapshot()
        if snapshot is None:
            self.status_var.set("Nothing to undo")
            return

        current = self._capture_snapshot()
        self.history.push_redo_snapshot(current)
        self._restore_snapshot(snapshot)
        self.status_var.set("Undo")

    def _redo(self) -> None:
        snapshot = self.history.pop_redo_snapshot()
        if snapshot is None:
            self.status_var.set("Nothing to redo")
            return

        current = self._capture_snapshot()
        self.history.push_undo_snapshot(current)
        self._restore_snapshot(snapshot)
        self.status_var.set("Redo")

    def _mark_saved_baseline(self) -> None:
        self.history.mark_saved_baseline(self._capture_dirty_snapshot())
        self.is_dirty = False

    def _update_dirty_state(self) -> None:
        self.is_dirty = self.history.has_unsaved_changes(self._capture_dirty_snapshot())

    def _mark_dirty(self, message: str, redraw: bool = True) -> None:
        self._update_dirty_state()
        self.status_var.set(message)
        if redraw:
            self._redraw()

    def _draw_grid(self) -> None:
        self.renderer.draw_grid(self)

    def _draw_world_line(self, points: list[tuple[float, float]], fill: str, width: float, smooth: bool = False) -> None:
        self.renderer.draw_world_line(self, points, fill=fill, width=width, smooth=smooth)

    def _redraw(self) -> None:
        self.renderer.redraw(self)

    def _confirm_discard_if_dirty(self) -> bool:
        if not self.is_dirty:
            return True
        return messagebox.askyesno(
            "Unsaved changes",
            "You have unsaved changes. Continue and discard them?",
            parent=self.root,
        )

    def _on_close(self) -> None:
        if not self._confirm_discard_if_dirty():
            return
        self.root.destroy()


def _save_last_paths(board_path: Path, layout_path: Path | None) -> None:
    LAST_PATHS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _write_json(LAST_PATHS_FILE, {
        "board_path": str(board_path),
        "layout_path": str(layout_path) if layout_path is not None else None,
    })


def _load_last_paths() -> tuple[Path | None, Path | None]:
    if not LAST_PATHS_FILE.exists():
        return None, None
    try:
        data = _read_json(LAST_PATHS_FILE)
    except (ValueError, OSError):
        return None, None
    board = data.get("board_path")
    layout = data.get("layout_path")
    board_path = Path(board) if isinstance(board, str) else None
    layout_path = Path(layout) if isinstance(layout, str) else None
    if board_path is None or not board_path.exists():
        return None, None
    return board_path, layout_path if (layout_path is not None and layout_path.exists()) else None


def _resolve_default_paths() -> tuple[Path | None, Path | None]:
    if DEFAULT_BOARD_PATH.exists() and DEFAULT_LAYOUT_PATH.exists():
        return DEFAULT_BOARD_PATH, DEFAULT_LAYOUT_PATH
    if DEFAULT_BOARD_PATH.exists():
        return DEFAULT_BOARD_PATH, None
    return None, None


def main() -> None:
    """Launch the interactive board creator."""

    parser = argparse.ArgumentParser(description="Launch the Tyrants interactive board creator")
    parser.add_argument("--board-path", type=Path, default=None, help="Path to board topology JSON")
    parser.add_argument("--layout-path", type=Path, default=None, help="Path to board layout JSON")
    args = parser.parse_args()

    default_board, default_layout = _resolve_default_paths()
    last_board, last_layout = _load_last_paths()
    board_path = args.board_path if args.board_path is not None else (last_board or default_board)
    layout_path = args.layout_path if args.layout_path is not None else (last_layout or default_layout)

    root = tk.Tk()
    BoardCreatorApp(root=root, board_path=board_path, layout_path=layout_path)
    root.mainloop()


if __name__ == "__main__":
    main()
