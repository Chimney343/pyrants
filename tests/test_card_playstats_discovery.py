"""Tests for ``scripts.card_playstats.discovery`` — run-folder discovery."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.card_playstats.discovery import RunFolder, find_run_folders

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_ROOT = ROOT / "artifacts" / "ismcts"
UCT_SWEEP_ROOT = ARTIFACTS_ROOT / "experiments" / "uct_sweep"
RECOMMENDED_RUN = "20260911T193759Z_58e54c44a5f5"


def _write_run(
    base: Path,
    run_name: str,
    game_names: tuple[str, ...] = ("game_0000",),
    *,
    complete: tuple[bool, ...] | None = None,
    run_id: str | None = None,
    config: dict | None = None,
) -> Path:
    run = base / run_name
    run.mkdir(parents=True)
    manifest = {
        "schema_version": 1,
        "run_id": run_id if run_id is not None else run_name,
        "config": config or {"num_games": len(game_names), "num_players": 4},
        "games": [],
    }
    (run / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    flags = complete if complete is not None else (True,) * len(game_names)
    for name, is_complete in zip(game_names, flags, strict=True):
        game_dir = run / name
        game_dir.mkdir()
        (game_dir / "replay.json").write_text(
            json.dumps(
                {
                    "step_count": 1,
                    "replay_log": [],
                    "replay_context": {"player_ids": ["p1", "p2"]},
                }
            ),
            encoding="utf-8",
        )
        if is_complete:
            (game_dir / "summary.json").write_text(
                json.dumps({"stopped_reason": "terminal", "winner": 0}),
                encoding="utf-8",
            )
    return run


def test_discovers_nested_run_folders(tmp_path: Path) -> None:
    _write_run(tmp_path, "b_run")
    _write_run(tmp_path / "experiments", "a_run")

    folders = find_run_folders(tmp_path)

    assert [f.run_id for f in folders] == ["b_run", "a_run"]
    assert all(isinstance(f, RunFolder) for f in folders)


def test_ignores_dirs_without_manifest(tmp_path: Path) -> None:
    (tmp_path / "not_a_run" / "game_0000").mkdir(parents=True)

    assert find_run_folders(tmp_path) == []


def test_ignores_manifest_without_game_dirs(tmp_path: Path) -> None:
    empty = tmp_path / "empty_run"
    empty.mkdir()
    (empty / "manifest.json").write_text(json.dumps({"run_id": "empty"}), encoding="utf-8")

    assert find_run_folders(tmp_path) == []


def test_run_folder_separates_complete_and_incomplete(tmp_path: Path) -> None:
    run = _write_run(
        tmp_path,
        "mixed_run",
        ("game_0000", "game_0001", "game_0002"),
        complete=(True, False, True),
    )

    (folder,) = find_run_folders(tmp_path)

    assert folder.run_dir == run
    assert len(folder.game_dirs) == 3
    assert len(folder.complete_game_dirs) == 2
    assert len(folder.incomplete_game_dirs) == 1
    assert folder.config["num_games"] == 3


def test_run_id_falls_back_to_directory_name(tmp_path: Path) -> None:
    run = _write_run(tmp_path, "named_run")
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    del manifest["run_id"]
    (run / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    (folder,) = find_run_folders(tmp_path)

    assert folder.run_id == "named_run"


def test_accepts_run_dir_itself_as_root(tmp_path: Path) -> None:
    run = _write_run(tmp_path, "direct_run")

    folders = find_run_folders(run)

    assert [f.run_dir for f in folders] == [run]


def test_discovers_experiment_config_run(tmp_path: Path) -> None:
    run = tmp_path / "sweep" / "20260101T000000Z_abc"
    run.mkdir(parents=True)
    (run / "experiment_config.json").write_text(
        json.dumps({"run_id": "abc", "num_sims": 16, "num_games": 1}), encoding="utf-8"
    )
    game_dir = run / "game_0000"
    game_dir.mkdir()
    (game_dir / "replay.json").write_text(json.dumps({"replay_log": []}), encoding="utf-8")
    (game_dir / "summary.json").write_text(
        json.dumps({"stopped_reason": "terminal"}), encoding="utf-8"
    )

    (folder,) = find_run_folders(tmp_path)

    assert folder.run_id == "abc"
    assert folder.config["num_sims"] == 16
    assert len(folder.complete_game_dirs) == 1


@pytest.mark.skipif(not UCT_SWEEP_ROOT.exists(), reason="UCT sweep artifacts not present")
def test_finds_uct_sweep_run() -> None:
    folders = find_run_folders(UCT_SWEEP_ROOT)

    assert folders
    assert len(folders[0].complete_game_dirs) >= 1


@pytest.mark.skipif(not ARTIFACTS_ROOT.exists(), reason="ISMCTS artifacts not present")
def test_finds_recommended_run_on_real_artifacts() -> None:
    folders = find_run_folders(ARTIFACTS_ROOT)

    dir_names = {f.run_dir.name for f in folders}
    assert RECOMMENDED_RUN in dir_names
    recommended = next(f for f in folders if f.run_dir.name == RECOMMENDED_RUN)
    assert len(recommended.game_dirs) >= 30
    assert len(recommended.complete_game_dirs) >= 1
