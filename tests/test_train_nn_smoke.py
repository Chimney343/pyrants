"""End-to-end smoke test for ``scripts/train_nn_smoke.py``."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")

from scripts.run_ismcts import run_one_game  # noqa: E402
from tests.test_build_nn_dataset import _make_game, _quick_params  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _write_run_manifest(run_dir: Path) -> None:
    (run_dir / "manifest.json").write_text(
        json.dumps({"run_id": "test", "engine_git_sha": "a" * 40}), encoding="utf-8"
    )


def _run_cli(run_dir: Path, *extra_args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable, "-m", "scripts.train_nn_smoke",
            "--runs", str(run_dir),
            "--epochs", "1",
            "--batch-size", "2",
            *extra_args,
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=300,
    )


def test_cli_smoke_two_games(requires_c_engine, tmp_path) -> None:
    """Two accepted games exercise the normal group train/val split path."""
    run_dir = tmp_path / "run"
    run_one_game(**_quick_params(
        run_dir, num_players=2, num_sims=4, max_rounds=6, game_index=0,
    ))
    run_one_game(**_quick_params(
        run_dir, num_players=2, num_sims=4, max_rounds=6, game_index=1,
        seed=43, shuffle_seed=43,
    ))
    _write_run_manifest(run_dir)

    result = _run_cli(run_dir, "--val-frac", "0.5")
    assert result.returncode == 0, result.stderr
    assert "games accepted=2" in result.stderr
    assert "epoch   1" in result.stdout
    assert "--- baselines ---" in result.stdout
    assert "NOT better" in result.stdout or "BETTER" in result.stdout


def test_cli_smoke_single_game_skips_validation(requires_c_engine, tmp_path) -> None:
    """A single accepted game must not crash the group split — it trains on
    everything and reports that no verdict was computed."""
    run_dir = tmp_path / "run"
    _make_game(run_dir, num_players=2, num_sims=4, max_rounds=6)
    _write_run_manifest(run_dir)

    result = _run_cli(run_dir)
    assert result.returncode == 0, result.stderr
    assert "games accepted=1" in result.stderr
    assert "skipping validation split" in result.stderr
    assert "no verdict computed" in result.stdout


def test_no_samples_exits_nonzero(tmp_path) -> None:
    """An empty/nonexistent run folder should fail loudly, not crash or hang."""
    run_dir = tmp_path / "empty"
    run_dir.mkdir()
    result = _run_cli(run_dir)
    assert result.returncode == 2
    assert "no samples to train on" in result.stderr
