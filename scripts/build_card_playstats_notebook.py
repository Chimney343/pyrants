"""One-time ``nbformat`` scaffold for ``card_playstats.ipynb``.

The notebook lets the user pick discovered run folders at **open** time (a
multi-select widget + free-text path + Analyze button) and renders the
per-run overview, per-card play table and modal-choice breakdowns into an
``Output`` widget. Folder choice is never baked into the generated file.

Usage:
    python scripts/build_card_playstats_notebook.py [--out card_playstats.ipynb]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

ROOT = Path(__file__).resolve().parents[1]

TITLE_CELL = """\
# Card Play Post-Mortem

Analyse per-card play behavior — recruited / appeared in hand / played / modal
choices — across one or more IS-MCTS run folders under `artifacts/ismcts/`.

Run the cells top to bottom, then pick run folders below and press **Analyze**.
Results are cached per game under `artifacts/card_playstats_cache/`, so
re-selecting an overlapping set of folders does not re-run the engine replay
for games already analyzed.
"""

IMPORTS_CELL = """\
from pathlib import Path

import ipywidgets as widgets
import plotly.express as px
from IPython.display import clear_output, display

from scripts.card_playstats.catalog import load_catalog
from scripts.card_playstats.discovery import find_run_folders
from scripts.card_playstats.extract import extract_game
from scripts.card_playstats.metadata import (
    metadata_for_selection,
    modal_market_card_ids,
)
from scripts.card_playstats.report import (
    build_card_table,
    build_modal_choice_frames,
    build_overview_frames,
)

ROOT = Path.cwd()
ARTIFACTS_ROOT = ROOT / "artifacts" / "ismcts"
DATA_CARDS = ROOT / "data" / "cards"
CACHE_DIR = ROOT / "artifacts" / "card_playstats_cache"
"""

PICKER_CELL = """\
discovered = find_run_folders(ARTIFACTS_ROOT)
folder_options = [
    (
        f"{folder.run_dir.relative_to(ARTIFACTS_ROOT)}  "
        f"({len(folder.complete_game_dirs)}/{len(folder.game_dirs)} complete)",
        str(folder.run_dir),
    )
    for folder in discovered
]

folder_picker = widgets.SelectMultiple(
    options=folder_options,
    description="Run folders",
    layout=widgets.Layout(width="70%", height="220px"),
)
extra_path = widgets.Text(
    description="Other path",
    placeholder=r"artifacts/ismcts/... or an absolute path",
    layout=widgets.Layout(width="70%"),
)
analyze_button = widgets.Button(description="Analyze", button_style="primary")
output = widgets.Output()


def selected_paths():
    paths = [Path(value) for value in folder_picker.value]
    raw = extra_path.value.strip()
    if raw:
        paths.append(Path(raw))
    return paths
"""

PIPELINE_CELL = """\
def collect_folders(paths):
    folders = []
    seen = set()
    for path in paths:
        for folder in find_run_folders(path):
            key = str(folder.run_dir.resolve())
            if key in seen:
                continue
            seen.add(key)
            folders.append(folder)
    return folders


def analyze(paths):
    catalog = load_catalog(DATA_CARDS)
    folders = collect_folders(paths)
    if not folders:
        print("No run folders discovered for the selected paths.")
        return

    extractions = []
    errors = []
    for folder in folders:
        for game_dir in folder.game_dirs:
            try:
                extractions.append(extract_game(game_dir, catalog, cache_dir=CACHE_DIR))
            except Exception as exc:  # one bad game must not sink the whole run
                errors.append(f"{game_dir}: {type(exc).__name__}: {exc}")

    metadatas = metadata_for_selection(folders)
    render(catalog, folders, metadatas, extractions, errors)
"""

RENDER_CELL = """\
def render(catalog, folders, metadatas, extractions, errors):
    overview = build_overview_frames(metadatas)
    modal_ids = set(modal_market_card_ids(folders, catalog))
    modal_ids |= {
        card_id
        for extraction in extractions
        for card_id in extraction.market_card_ids
        if catalog.is_modal(card_id)
    }
    card_table = build_card_table(extractions, catalog)
    modal_frames = build_modal_choice_frames(extractions, catalog, modal_ids)

    display(widgets.HTML("<h2>Collection overview</h2>"))
    display(widgets.HTML("<h3>Run config (per run, unblended)</h3>"))
    display(overview["config"])
    display(widgets.HTML("<h3>Completion &amp; engine provenance</h3>"))
    display(overview["summary"])

    if not overview["win_rate_by_seat"].empty:
        display(widgets.HTML("<h3>Win rate by seat</h3>"))
        display(overview["win_rate_by_seat"])
    if not overview["matchups"].empty:
        display(widgets.HTML("<h3>Deck matchups</h3>"))
        display(px.bar(overview["matchups"], x="matchup", y="count", color="run_id"))
    if not overview["deck_diversity"].empty:
        display(widgets.HTML("<h3>Mean deck diversity (Shannon entropy)</h3>"))
        long_diversity = overview["deck_diversity"].melt(
            id_vars="run_id", var_name="variant", value_name="shannon_entropy"
        )
        display(
            px.bar(
                long_diversity,
                x="run_id",
                y="shannon_entropy",
                color="variant",
                barmode="group",
            )
        )

    if not overview["game_lengths"].empty:
        display(widgets.HTML("<h3>Game length distribution (decisions per game)</h3>"))
        display(px.histogram(overview["game_lengths"], x="decision_count", color="run_id"))
    if not overview["mean_scores"].empty:
        display(widgets.HTML("<h3>Mean score by seat</h3>"))
        display(
            px.bar(
                overview["mean_scores"],
                x="player_id",
                y="mean_score",
                color="run_id",
                barmode="group",
            )
        )

    display(widgets.HTML("<h2>Per-card play</h2>"))
    display(card_table)
    display(widgets.HTML("<h3>Recruited but never played</h3>"))
    display(card_table[card_table["recruited_never_played"]])

    display(widgets.HTML("<h2>Modal choices</h2>"))
    if not modal_frames:
        print("No modal cards appear in the selected games' market decks.")
    for card_id, frame in modal_frames.items():
        display(
            px.bar(
                frame,
                x="option_id",
                y="count",
                text="count",
                title=f"{card_id} ({int(frame['count'].sum())} picks)",
            )
        )

    if extractions:
        warnings = [w for extraction in extractions for w in extraction.warnings]
        display(widgets.HTML("<h3>Warnings</h3>"))
        if warnings:
            for warning in warnings:
                print(warning)
        else:
            print("No sanity warnings.")

    if errors:
        display(widgets.HTML("<h3>Extraction errors (skipped games)</h3>"))
        for error in errors:
            print(error)
"""

WIRE_CELL = """\
def on_analyze(_button):
    with output:
        clear_output(wait=True)
        analyze(selected_paths())


analyze_button.on_click(on_analyze)

display(
    widgets.VBox([folder_picker, extra_path, analyze_button]),
    output,
)
"""


def build_notebook() -> nbformat.NotebookNode:
    """Build the notebook node (no folder selection baked in)."""
    return new_notebook(
        cells=[
            new_markdown_cell(TITLE_CELL),
            new_code_cell(IMPORTS_CELL),
            new_code_cell(PICKER_CELL),
            new_code_cell(PIPELINE_CELL),
            new_code_cell(RENDER_CELL),
            new_code_cell(WIRE_CELL),
        ],
        metadata={
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
        },
    )


def write_notebook(path: Path) -> Path:
    """Write the generated notebook to *path* (atomic replace)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    nbformat.write(build_notebook(), str(path))
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scaffold card_playstats.ipynb.")
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "card_playstats.ipynb",
        help="Output notebook path (default: card_playstats.ipynb in repo root).",
    )
    args = parser.parse_args(argv)
    out = write_notebook(args.out)
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
