"""Discover IS-MCTS run folders (run marker + ``game_*`` dirs).

A *run folder* is the timestamped directory that holds the run-level metadata
next to its ``game_XXXX/`` children, e.g.
``artifacts/ismcts/runs/20260911T193759Z_58e54c44a5f5/``. Run folders can be
nested at any depth (``runs/``, ``quick/``, ``experiments/uct_sweep/``), so
discovery is a recursive walk from a root.

Two run-marker formats exist in the wild:

- ``manifest.json`` — the standard IS-MCTS run manifest (with ``config`` and
  per-game inline ``setup_data_json``); only ``runs/`` and ``quick/`` runs carry
  it.
- ``experiment_config.json`` — the sweep runner's flat config; the
  ``experiments/*`` folders carry this instead.

Completeness classification reuses
:func:`interface.replay_loader.is_complete_game` — the single shared predicate
(a game is complete only when ``summary.json`` exists and is terminal).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from interface.replay_loader import is_complete_game

RUN_MARKERS = ("manifest.json", "experiment_config.json")


@dataclass(frozen=True)
class RunFolder:
    """One discovered run folder and its game directories."""

    run_dir: Path
    run_id: str
    manifest: dict
    game_dirs: tuple[Path, ...]
    complete_game_dirs: tuple[Path, ...]
    incomplete_game_dirs: tuple[Path, ...]

    @property
    def config(self) -> dict:
        config = self.manifest.get("config")
        return config if isinstance(config, dict) else {}

    def __str__(self) -> str:  # pragma: no cover - display helper
        config = self.config
        return (
            f"{self.run_dir.name} [{self.run_id}] "
            f"{len(self.complete_game_dirs)}/{len(self.game_dirs)} complete"
            f" (sims={config.get('num_sims', '?')}, players={config.get('num_players', '?')})"
        )


def _load_manifest(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _run_marker(run_dir: Path) -> Path | None:
    for name in RUN_MARKERS:
        candidate = run_dir / name
        if candidate.is_file():
            return candidate
    return None


def _normalize_manifest(marker: Path, data: dict) -> dict:
    """Give experiment-config runs the manifest shape downstream code expects."""
    if marker.name == "experiment_config.json":
        config = data.get("config")
        if not isinstance(config, dict):
            config = data
        return {"run_id": data.get("run_id"), "config": config, "source": "experiment_config"}
    return data


def _game_dirs(run_dir: Path) -> tuple[Path, ...]:
    dirs = [
        child
        for child in run_dir.iterdir()
        if child.is_dir() and child.name.startswith("game_") and (child / "replay.json").is_file()
    ]
    return tuple(sorted(dirs, key=lambda p: p.name))


def _run_folder(run_dir: Path, manifest: dict) -> RunFolder:
    games = _game_dirs(run_dir)
    complete = tuple(game for game in games if is_complete_game(game))
    incomplete = tuple(game for game in games if game not in complete)
    run_id = manifest.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        run_id = run_dir.name
    return RunFolder(
        run_dir=run_dir,
        run_id=run_id,
        manifest=manifest,
        game_dirs=games,
        complete_game_dirs=complete,
        incomplete_game_dirs=incomplete,
    )


def find_run_folders(root: Path) -> list[RunFolder]:
    """Return every run folder under *root*, newest-looking first.

    Ordering is by directory name descending, which matches the timestamped
    ``<ts>_<run_id>`` naming convention without depending on filesystem mtimes.
    """
    root = Path(root)
    if not root.exists():
        return []

    candidates: set[Path] = set()
    for name in RUN_MARKERS:
        candidates.update(marker.parent for marker in root.rglob(name))

    seen: set[Path] = set()
    folders: list[RunFolder] = []
    for run_dir in candidates:
        if run_dir in seen:
            continue
        seen.add(run_dir)
        marker = _run_marker(run_dir)
        if marker is None:
            continue
        data = _load_manifest(marker)
        if data is None:
            continue
        folder = _run_folder(run_dir, _normalize_manifest(marker, data))
        if not folder.game_dirs:
            continue
        folders.append(folder)

    folders.sort(key=lambda f: f.run_dir.name, reverse=True)
    return folders
