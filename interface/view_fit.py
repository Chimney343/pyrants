"""Fit-to-viewport zoom calculations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FitZoomResult:
    """Result of a fit-to-viewport zoom calculation."""

    zoom: float
    center_x: float
    center_y: float


def compute_fit_zoom(
    node_bboxes: list[tuple[float, float, float, float]],
    viewport_w: float,
    viewport_h: float,
    *,
    min_zoom: float = 0.1,
    max_zoom: float = 3.0,
    padding: float = 0.1,
) -> FitZoomResult | None:
    """Compute zoom and center that fit all node bounding boxes within the viewport.

    Args:
        node_bboxes: list of (min_x, min_y, max_x, max_y) for each node.
        viewport_w: viewport width in pixels.
        viewport_h: viewport height in pixels.
        min_zoom: minimum allowed zoom level.
        max_zoom: maximum allowed zoom level.
        padding: fraction of total node extent to add as margin (0.1 = 10%).

    Returns:
        FitZoomResult with computed zoom and center, or None if input is empty
        or viewport is too small.
    """
    if not node_bboxes or viewport_w <= 1 or viewport_h <= 1:
        return None

    min_x = float("inf")
    min_y = float("inf")
    max_x = float("-inf")
    max_y = float("-inf")

    for left, top, right, bottom in node_bboxes:
        min_x = min(min_x, left)
        min_y = min(min_y, top)
        max_x = max(max_x, right)
        max_y = max(max_y, bottom)

    node_w = max_x - min_x
    node_h = max_y - min_y
    if node_w <= 0 or node_h <= 0:
        return None

    padded_w = node_w * (1 + 2 * padding)
    padded_h = node_h * (1 + 2 * padding)

    fit_zoom = min(viewport_w / padded_w, viewport_h / padded_h, max_zoom)
    fit_zoom = max(min_zoom, fit_zoom)

    return FitZoomResult(
        zoom=fit_zoom,
        center_x=min_x + node_w / 2,
        center_y=min_y + node_h / 2,
    )
