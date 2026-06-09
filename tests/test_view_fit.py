"""Tests for the shared view fit-zoom helper."""

from __future__ import annotations

from interface.view_fit import compute_fit_zoom


def test_fit_zoom_empty_bboxes_returns_none() -> None:
    assert compute_fit_zoom([], 800, 600) is None


def test_fit_zoom_small_viewport_returns_none() -> None:
    assert compute_fit_zoom([(0, 0, 100, 100)], 0, 0) is None
    assert compute_fit_zoom([(0, 0, 100, 100)], 1, 1) is None


def test_fit_zoom_zero_size_bbox_returns_none() -> None:
    assert compute_fit_zoom([(0, 0, 0, 0)], 800, 600) is None


def test_fit_zoom_single_node_centers_and_fits() -> None:
    result = compute_fit_zoom([(0, 0, 100, 100)], 800, 600)
    assert result is not None
    assert result.zoom > 0
    assert result.center_x == 50.0
    assert result.center_y == 50.0


def test_fit_zoom_large_padding_reduces_zoom() -> None:
    result_tight = compute_fit_zoom([(0, 0, 100, 100)], 800, 600, padding=0.0, max_zoom=10.0)
    result_padded = compute_fit_zoom([(0, 0, 100, 100)], 800, 600, padding=0.5, max_zoom=10.0)
    assert result_tight is not None
    assert result_padded is not None
    assert result_tight.zoom > result_padded.zoom


def test_fit_zoom_respects_min_max() -> None:
    result = compute_fit_zoom([(0, 0, 10, 10)], 8000, 6000, min_zoom=0.2, max_zoom=5.0)
    assert result is not None
    assert result.zoom == 5.0  # would be much higher without max clamp

    result_min = compute_fit_zoom([(0, 0, 10000, 10000)], 8, 6, min_zoom=0.2, max_zoom=5.0)
    assert result_min is not None
    assert result_min.zoom == 0.2  # would be much lower without min clamp


def test_fit_zoom_center_is_midpoint() -> None:
    result = compute_fit_zoom([(100, 200, 300, 400), (500, 600, 700, 800)], 1000, 1000)
    assert result is not None
    assert result.center_x == 400.0  # midpoint of 100 and 700
    assert result.center_y == 500.0  # midpoint of 200 and 800
