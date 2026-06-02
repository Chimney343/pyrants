"""Background image lifecycle and scaling for the board editor."""

from __future__ import annotations

import math
from pathlib import Path
import tkinter as tk

_MAX_SOURCE_DIM = 1200
_MAX_INTERMEDIATE_DIM = 60000


def _best_zoom_factors(zoom_level: float, source_w: int) -> tuple[int, int]:
    """Return (numerator, denominator) for the best rational approximation of
    *zoom_level* whose numerator keeps the intermediate PhotoImage under
    *_MAX_INTERMEDIATE_DIM*.
    """
    max_n = _MAX_INTERMEDIATE_DIM // max(1, source_w)
    best_n, best_d = 1, 1
    best_error: float = 1000.0
    for d in range(1, min(max_n, 100) + 1):
        n = max(1, round(zoom_level * d))
        if n > max_n:
            break
        error = abs(n / d - zoom_level)
        if error < best_error - 1e-12:
            best_error = error
            best_n, best_d = n, d
            if error < 1e-12:
                break
    return best_n, best_d


class BackgroundImageManager:
    """Own the background image path and Tk PhotoImage objects."""

    def __init__(self) -> None:
        self.image_path: Path | None = None
        self.source_photo: tk.PhotoImage | None = None
        self.photo: tk.PhotoImage | None = None

    def clear(self) -> None:
        self.image_path = None
        self.source_photo = None
        self.photo = None

    def set_from_path(self, image_path: Path | None, adopt_image_size: bool) -> tuple[int, int] | None:
        if image_path is None:
            self.clear()
            return None

        try:
            source_photo = tk.PhotoImage(file=str(image_path))
        except tk.TclError as error:
            raise ValueError("Unsupported image format") from error

        w = source_photo.width()
        h = source_photo.height()
        over = max(w, h) / _MAX_SOURCE_DIM
        if over > 1:
            factor = max(1, math.ceil(over))
            source_photo = source_photo.subsample(factor, factor)

        self.image_path = image_path.resolve()
        self.source_photo = source_photo

        if adopt_image_size:
            return (source_photo.width(), source_photo.height())

        return None

    def refresh_for_zoom(self, zoom_level: float) -> None:
        if self.source_photo is None:
            self.photo = None
            return

        if zoom_level == 1.0:
            self.photo = self.source_photo
            return

        source_w = self.source_photo.width()
        numerator, denominator = _best_zoom_factors(zoom_level, source_w)

        scaled = self.source_photo.zoom(numerator, numerator)
        if denominator > 1:
            scaled = scaled.subsample(denominator, denominator)
        self.photo = scaled

    def load_from_layout_value(
        self,
        stored_value: str | None,
        layout_path: Path | None,
        *,
        adopt_image_size: bool,
    ) -> tuple[tuple[int, int] | None, str | None]:
        if stored_value is None:
            self.clear()
            return None, None

        candidate = Path(stored_value)
        if not candidate.is_absolute() and layout_path is not None:
            candidate = (layout_path.parent / candidate).resolve()

        if not candidate.exists():
            self.clear()
            return None, f"Background image not found: {stored_value}"

        try:
            adopted = self.set_from_path(candidate, adopt_image_size=adopt_image_size)
        except ValueError:
            self.clear()
            return None, "Background image format is unsupported by Tk PhotoImage"

        return adopted, None

    def restore_from_snapshot_value(self, snapshot_value: object, adopt_image_size: bool = False) -> None:
        if not isinstance(snapshot_value, str):
            self.clear()
            return

        image_path = Path(snapshot_value)
        if not image_path.exists():
            self.clear()
            return

        try:
            self.set_from_path(image_path, adopt_image_size=adopt_image_size)
        except ValueError:
            self.clear()

    def snapshot_value(self) -> str | None:
        if self.image_path is None:
            return None
        return self.image_path.as_posix()
