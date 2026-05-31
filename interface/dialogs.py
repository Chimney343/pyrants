"""Reusable tabular input dialogs for the board creator."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Sequence


class TabularInputDialog(tk.Toplevel):
    """A modal dialog that presents fields in a table layout (label | input).

    Each field is a row with a label and an entry widget. Supports string,
    integer, and optional-string field types. Returns a dict of field_name ->
    value, or None if cancelled.
    """

    Field = tuple[str, str, str]  # (name, label, kind) where kind is "str", "int", "opt_str"

    def __init__(
        self,
        parent: tk.Misc,
        title: str,
        fields: Sequence[Field],
        initial_values: dict[str, str] | None = None,
    ) -> None:
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.grab_set()

        self._fields = fields
        self._entries: dict[str, tk.Widget] = {}
        self._result: dict[str, object] | None = None

        self._build(fields, initial_values or {})
        self._center_on_parent(parent)

        self.wait_window()

    def _build(self, fields: Sequence[Field], initial_values: dict[str, str]) -> None:
        main = ttk.Frame(self, padding=16)
        main.pack(fill=tk.BOTH, expand=True)

        # Build a grid: column 0 = labels, column 1 = entries
        for row_idx, (name, label, kind) in enumerate(fields):
            ttk.Label(main, text=f"{label}:").grid(
                row=row_idx, column=0, sticky="w", padx=(0, 8), pady=4
            )

            initial = initial_values.get(name, "")
            if kind == "int":
                var = tk.StringVar(value=initial)
                entry = ttk.Spinbox(
                    main,
                    from_=0,
                    to=9999,
                    textvariable=var,
                    width=12,
                )
                entry.grid(row=row_idx, column=1, sticky="ew", pady=4)
                self._entries[name] = var
            else:
                entry = ttk.Entry(main, width=30)
                entry.insert(0, initial)
                entry.grid(row=row_idx, column=1, sticky="ew", pady=4)
                self._entries[name] = entry

        # Buttons
        btn_frame = ttk.Frame(main)
        btn_frame.grid(row=len(fields), column=0, columnspan=2, pady=(12, 0))

        ttk.Button(btn_frame, text="OK", command=self._on_ok).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_frame, text="Cancel", command=self._on_cancel).pack(side=tk.LEFT)

        main.columnconfigure(1, weight=1)

        # Bind Enter to OK
        self.bind("<Return>", lambda _: self._on_ok())
        self.bind("<Escape>", lambda _: self._on_cancel())

        # Focus first entry
        first_entry = next(iter(self._entries.values()), None)
        if first_entry is not None:
            if isinstance(first_entry, tk.StringVar):
                pass  # spinbox focus is fine
            else:
                first_entry.focus_set()

    def _center_on_parent(self, parent: tk.Misc) -> None:
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"+{x}+{y}")

    def _on_ok(self) -> None:
        result: dict[str, object] = {}
        for name, _label, kind in self._fields:
            widget = self._entries[name]
            if isinstance(widget, tk.StringVar):
                raw = widget.get().strip()
            else:
                raw = widget.get().strip()

            if kind == "int":
                if not raw:
                    # Treat empty as 0 for optional ints
                    result[name] = 0
                else:
                    try:
                        result[name] = int(raw)
                    except ValueError:
                        self._flash_invalid(name)
                        return
            elif kind == "opt_str":
                result[name] = raw or None
            else:
                result[name] = raw

        # Validate required strings
        for name, _label, kind in self._fields:
            if kind == "str":
                val = result[name]
                if not isinstance(val, str) or not val.strip():
                    self._flash_invalid(name)
                    return

        self._result = result
        self.destroy()

    def _on_cancel(self) -> None:
        self._result = None
        self.destroy()

    def _flash_invalid(self, field_name: str) -> None:
        widget = self._entries[field_name]
        if isinstance(widget, tk.StringVar):
            return
        original_bg = widget.cget("bg") if widget.cget("bg") else "white"
        widget.configure(bg="#ffcccc")
        self.after(600, lambda: widget.configure(bg=original_bg))

    @property
    def result(self) -> dict[str, object] | None:
        return self._result
