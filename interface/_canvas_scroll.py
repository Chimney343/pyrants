"""Shared canvas mouse wheel scroll, middle-button pan, and Ctrl+wheel zoom bindings.

Both the board creator and game viewer use the same Tk canvas interaction
patterns. This module keeps the five bindings and their handler logic in
one place so the calling code only has to provide the canvas and two zoom
callables.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable


def bind_canvas_scrolling(
    canvas: tk.Canvas,
    zoom_in: Callable[[], None],
    zoom_out: Callable[[], None],
) -> None:
    """Apply scroll/pan/zoom mouse bindings to *canvas*.

    - ``<MouseWheel>``         → vertical scroll
    - ``<Shift-MouseWheel>``   → horizontal scroll
    - ``<Control-MouseWheel>`` → zoom in/out via *zoom_in* / *zoom_out*
    - ``<ButtonPress-2>``      → begin middle-button pan
    - ``<B2-Motion>``          → drag middle-button pan
    """
    canvas.bind("<MouseWheel>", lambda e: _scroll_vert(canvas, e))
    canvas.bind("<Shift-MouseWheel>", lambda e: _scroll_horiz(canvas, e))
    canvas.bind("<Control-MouseWheel>", lambda e: _ctrl_wheel(zoom_in, zoom_out, e))
    canvas.bind("<ButtonPress-2>", lambda e: _pan_start(canvas, e))
    canvas.bind("<B2-Motion>", lambda e: _pan_drag(canvas, e))


# ------------------------------------------------------------------ handlers


def _scroll_vert(canvas: tk.Canvas, event: tk.Event[tk.Canvas]) -> None:
    canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


def _scroll_horiz(canvas: tk.Canvas, event: tk.Event[tk.Canvas]) -> None:
    canvas.xview_scroll(int(-1 * (event.delta / 120)), "units")


def _ctrl_wheel(
    zoom_in: Callable[[], None],
    zoom_out: Callable[[], None],
    event: tk.Event[tk.Canvas],
) -> None:
    if event.delta > 0:
        zoom_in()
    else:
        zoom_out()


def _pan_start(canvas: tk.Canvas, event: tk.Event[tk.Canvas]) -> None:
    canvas.scan_mark(event.x, event.y)


def _pan_drag(canvas: tk.Canvas, event: tk.Event[tk.Canvas]) -> None:
    canvas.scan_dragto(event.x, event.y, gain=1)
