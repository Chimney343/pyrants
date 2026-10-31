"""Tests for ``scripts.build_card_playstats_notebook`` — nbformat scaffold."""

from __future__ import annotations

from pathlib import Path

import nbformat

from scripts.build_card_playstats_notebook import build_notebook, write_notebook


def _code_text(nb) -> str:
    return "\n".join(cell["source"] for cell in nb.cells if cell["cell_type"] == "code")


def test_notebook_is_valid_nbformat() -> None:
    nb = build_notebook()
    nbformat.validate(nb)


def test_notebook_wires_picker_and_analysis_sections() -> None:
    source = _code_text(build_notebook())

    assert "find_run_folders" in source
    assert "SelectMultiple" in source or "Checkbox" in source or "ToggleButtons" in source
    assert "Analyze" in source
    assert "extract_game" in source
    assert "build_card_table" in source
    assert "build_modal_choice_frames" in source
    assert "build_overview_frames" in source


def test_notebook_picker_reads_selectmultiple_values() -> None:
    source = _code_text(build_notebook())

    assert "[Path(value) for value in folder_picker.value]" in source
    assert "for _, value in folder_picker.value" not in source


def test_notebook_code_cells_compile() -> None:
    nb = build_notebook()

    for index, cell in enumerate(nb.cells):
        if cell["cell_type"] == "code":
            compile(cell["source"], f"<cell {index}>", "exec")


def test_notebook_does_not_bake_in_a_fixed_run() -> None:
    source = _code_text(build_notebook())

    assert "20260911T193759Z_58e54c44a5f5" not in source


def test_write_notebook_round_trips(tmp_path: Path) -> None:
    out = tmp_path / "card_playstats.ipynb"

    write_notebook(out)

    nb = nbformat.read(out, as_version=4)
    nbformat.validate(nb)
    assert any(cell["cell_type"] == "code" for cell in nb.cells)
