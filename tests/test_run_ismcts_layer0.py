"""Phase 1 (Layer 0) tests: run dir, manifest, schema version, summary last.

Implements ``docs/nn-training-data-tdd-plan.md`` § 4.1 (T1.1-T1.9, T1.12).
Pure helper tests are cheap; the ``requires_c_engine`` tests drive
``run_one_game`` with ``num_sims=2``.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

import openspiel_pyrants  # noqa: F401
from interface.replay_loader import is_complete_game
from scripts._obs import new_run_id
from scripts._run_layout import (
    GameDirCollisionError,
    collect_engine_provenance,
    only_run_dir,
    run_dir_name,
    write_json_atomic,
)
from scripts.run_ismcts import (
    GameRunFailedError,
    _game_dir,
    _load_game_or_die,
    _resolve_policy,
    main,
    run_one_game,
)

# ── T1.1 run_dir_name ──────────────────────────────────────────────────────


def test_run_dir_name_is_utc_timestamp_and_run_id() -> None:
    now = datetime(2026, 9, 10, 12, 0, 0, tzinfo=UTC)
    assert run_dir_name("abc123", now=now) == "20260910T120000Z_abc123"


# ── helpers ────────────────────────────────────────────────────────────────


def _run_main(tmp_path: Path, extra: list[str]) -> None:
    import sys

    argv = [
        "run_ismcts",
        "--output-dir",
        str(tmp_path),
        "--game",
        "python_pyrants_c",
        *extra,
    ]
    old = sys.argv
    sys.argv = argv
    try:
        main()
    finally:
        sys.argv = old


def _quick_params(tmp_path: Path, **overrides) -> dict:
    params = {
        "game": _load_game_or_die("python_pyrants_c", {"num_players": "2"}),
        "game_index": 0,
        "num_sims": 2,
        "uct_c": 1.4,
        "max_world_samples": 10,
        "final_policy_type": _resolve_policy("visited"),
        "final_policy_name": "visited",
        "seed": 42,
        "shuffle_seed": 42,
        "out_dir": tmp_path,
        "deck_a_id": "deck_a",
        "deck_b_id": "deck_b",
        "show_progress": False,
        "run_id": new_run_id(),
        "rollout_count": 1,
        "rollout_max_length": None,
        "max_rounds": 3,
        "setup_data_json": "",
        "num_players": 2,
    }
    params.update(overrides)
    return params


def _flaky_game(fail_on_call: int = 3):
    """Game whose ``state.apply_action`` raises on the Nth total call.

    Mirrors ``openspiel_pyrants/tests/test_run_ismcts_step_ordering.py`` so this
    file can reuse the crash path without importing a non-package test module.
    """
    game = _load_game_or_die("python_pyrants_c", {"num_players": "2"})
    state = game.new_initial_state()
    counters = {"apply_calls": 0}

    def flaky_apply_action(action) -> None:
        counters["apply_calls"] += 1
        if counters["apply_calls"] == fail_on_call:
            raise RuntimeError("boom")
        state._apply_action(action)

    state.apply_action = flaky_apply_action
    game.new_initial_state = lambda: state
    return game, state, counters


# ── T1.2 manifest + nested run dir ─────────────────────────────────────────


def test_main_nests_run_dir_and_writes_manifest(requires_c_engine, tmp_path) -> None:
    _run_main(
        tmp_path,
        ["--num-games", "1", "--num-sims", "2", "--max-rounds", "3", "--workers", "1"],
    )

    children = [p for p in tmp_path.iterdir() if p.is_dir()]
    assert len(children) == 1, children
    run_dir = children[0]

    assert (run_dir / "manifest.json").exists()
    assert (run_dir / "game_0000").is_dir()
    assert (run_dir / "summary.csv").exists()
    assert (run_dir / "summary.md").exists()
    assert (run_dir / "metrics.json").exists()

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 2
    assert manifest["run_id"]
    sha = manifest["engine_git_sha"]
    assert sha is None or (isinstance(sha, str) and len(sha) == 40)
    dirty = manifest["engine_git_dirty"]
    assert dirty is None or isinstance(dirty, bool)
    repo_dirty = manifest["repo_git_dirty"]
    assert repo_dirty is None or isinstance(repo_dirty, bool)
    assert isinstance(manifest["engine_dll_sha256"], str)
    assert len(manifest["engine_dll_sha256"]) == 64
    assert manifest["steps_enabled"] is True

    for key in ("num_sims", "num_games", "seed", "num_players", "output_dir", "workers"):
        assert key in manifest["config"], key

    entry = manifest["games"][0]
    summary = json.loads((run_dir / "game_0000" / "summary.json").read_text(encoding="utf-8"))
    assert entry["game_index"] == 0
    assert hashlib.sha256(entry["setup_data_json"].encode()).hexdigest()[:16] == (
        summary["setup_data_sha256"]
    )


# ── T1.3 manifest precedes the first game ──────────────────────────────────


def test_manifest_written_before_first_game(requires_c_engine, tmp_path, monkeypatch) -> None:
    import scripts.run_ismcts as runner

    def boom(**kwargs):
        raise RuntimeError("no games")

    monkeypatch.setattr(runner, "run_one_game", boom)
    with pytest.raises(RuntimeError):
        _run_main(tmp_path, ["--num-games", "1", "--num-sims", "2", "--workers", "1"])

    run_dir = only_run_dir(tmp_path)
    assert (run_dir / "manifest.json").exists()


# ── T1.4 schema_version on replay + summary (success and crash) ────────────


def test_replay_and_summary_carry_schema_version(requires_c_engine, tmp_path) -> None:
    run_one_game(**_quick_params(tmp_path, run_id="sv"))
    game_out = _game_dir(tmp_path, 0)
    replay = json.loads((game_out / "replay.json").read_text(encoding="utf-8"))
    summary = json.loads((game_out / "summary.json").read_text(encoding="utf-8"))
    assert replay["schema_version"] == 2
    assert summary["schema_version"] == 2


def test_crash_summary_carries_schema_version(requires_c_engine, tmp_path) -> None:
    game, _state, _counters = _flaky_game()
    with pytest.raises(GameRunFailedError):
        run_one_game(**_quick_params(tmp_path, run_id="crash", game=game))
    summary = json.loads((_game_dir(tmp_path, 0) / "summary.json").read_text(encoding="utf-8"))
    assert summary["schema_version"] == 2
    assert summary["stopped_reason"] == "error"


# ── T1.5 summary written last + atomicity of ordering ──────────────────────


def test_summary_is_written_last(requires_c_engine, tmp_path, monkeypatch) -> None:
    import scripts.run_ismcts as runner

    order: list[str] = []
    real = runner.write_json_atomic

    def recorder(path, obj):
        order.append(Path(path).name)
        return real(path, obj)

    monkeypatch.setattr(runner, "write_json_atomic", recorder)
    run_one_game(**_quick_params(tmp_path, run_id="order"))

    assert order[:3] == ["replay.json", "final_decks.json", "summary.json"]


def test_summary_absent_when_final_decks_write_fails(requires_c_engine, tmp_path, monkeypatch) -> None:
    import scripts.run_ismcts as runner

    real = runner.write_json_atomic

    def flaky(path, obj):
        if Path(path).name == "final_decks.json":
            raise RuntimeError("disk full")
        return real(path, obj)

    monkeypatch.setattr(runner, "write_json_atomic", flaky)
    with pytest.raises(RuntimeError):
        run_one_game(**_quick_params(tmp_path, run_id="partial"))

    game_out = _game_dir(tmp_path, 0)
    assert (game_out / "replay.json").exists()
    assert not (game_out / "summary.json").exists()


# ── T1.6 write_json_atomic leaves no partial file ──────────────────────────


def test_write_json_atomic_leaves_no_partial_file(tmp_path) -> None:
    path = tmp_path / "out.json"
    with pytest.raises(TypeError):
        write_json_atomic(path, {"x": object()})

    assert not path.exists()
    assert list(tmp_path.glob("*.tmp")) == []
    assert list(tmp_path.glob("out.json*")) == []


# ── T1.7 is_complete_game ──────────────────────────────────────────────────


def test_is_complete_game(tmp_path) -> None:
    game_dir = tmp_path / "game_0000"
    game_dir.mkdir()

    assert is_complete_game(game_dir) is False

    (game_dir / "summary.json").write_text('{"stopped_reason": "error"}', encoding="utf-8")
    assert is_complete_game(game_dir) is False

    (game_dir / "summary.json").write_text('{"stopped_reason": "round_cap"}', encoding="utf-8")
    assert is_complete_game(game_dir) is False

    (game_dir / "summary.json").write_text('{"stopped_reason": "terminal"}', encoding="utf-8")
    assert is_complete_game(game_dir) is True

    (game_dir / "summary.json").write_text("NOT JSON", encoding="utf-8")
    assert is_complete_game(game_dir) is False


# ── T1.8 collect_engine_provenance ─────────────────────────────────────────


def test_collect_engine_provenance(tmp_path) -> None:
    dll = tmp_path / "engine_c" / "engine_c.dll"
    dll.parent.mkdir(parents=True)
    dll.write_bytes(b"fake dll bytes")

    def fake_run(cmd, **kwargs):
        if cmd[:3] == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="a" * 40 + "\n", stderr="")
        if cmd[:4] == ["git", "status", "--porcelain", "--"]:
            return subprocess.CompletedProcess(
                cmd, 0, stdout=" M engine_c/foo.c\n", stderr=""
            )
        raise AssertionError(cmd)

    prov = collect_engine_provenance(tmp_path, run=fake_run)
    assert prov["engine_git_sha"] == "a" * 40
    assert prov["engine_git_dirty"] is True
    assert prov["engine_dll_sha256"] == hashlib.sha256(dll.read_bytes()).hexdigest()

    def clean_run(cmd, **kwargs):
        if cmd[:3] == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="b" * 40, stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    prov = collect_engine_provenance(tmp_path, run=clean_run)
    assert prov["engine_git_sha"] == "b" * 40
    assert prov["engine_git_dirty"] is False

    def missing_run(cmd, **kwargs):
        raise FileNotFoundError("git not found")

    prov = collect_engine_provenance(tmp_path, run=missing_run)
    assert prov["engine_git_sha"] is None
    assert prov["engine_git_dirty"] is None
    assert prov["engine_dll_sha256"] == hashlib.sha256(dll.read_bytes()).hexdigest()


def test_collect_engine_provenance_reports_repo_dirty(tmp_path) -> None:
    """T1.5: the whole-tree dirty flag is distinct from the engine_c-only one."""
    dll = tmp_path / "engine_c" / "engine_c.dll"
    dll.parent.mkdir(parents=True)
    dll.write_bytes(b"fake dll bytes")

    def fake_run(cmd, **kwargs):
        if cmd[:3] == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="a" * 40 + "\n", stderr="")
        if cmd == ["git", "status", "--porcelain"]:
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout=" M openspiel_pyrants/nn/actions.py\n M engine_c/foo.c\n",
                stderr="",
            )
        if cmd[:4] == ["git", "status", "--porcelain", "--"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        raise AssertionError(cmd)

    prov = collect_engine_provenance(tmp_path, run=fake_run)
    assert prov["engine_git_dirty"] is False
    assert prov["repo_git_dirty"] is True

    def clean_run(cmd, **kwargs):
        if cmd[:3] == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="b" * 40, stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    prov = collect_engine_provenance(tmp_path, run=clean_run)
    assert prov["engine_git_dirty"] is False
    assert prov["repo_git_dirty"] is False

    def missing_run(cmd, **kwargs):
        raise FileNotFoundError("git not found")

    prov = collect_engine_provenance(tmp_path, run=missing_run)
    assert prov["repo_git_dirty"] is None


# ── T1.9 F-025 falsification: second run into same dir is refused ──────────


def test_second_run_into_same_dir_is_refused(requires_c_engine, tmp_path) -> None:
    run_one_game(**_quick_params(tmp_path, run_id="A", num_players=2))

    game4 = _load_game_or_die("python_pyrants_c", {"num_players": "4"})
    with pytest.raises(GameDirCollisionError):
        run_one_game(**_quick_params(tmp_path, run_id="B", num_players=4, game=game4))

    game_out = _game_dir(tmp_path, 0)
    replay = json.loads((game_out / "replay.json").read_text(encoding="utf-8"))
    assert replay["run_id"] == "A"

    run_ids = {
        json.loads(line)["run_id"]
        for line in (game_out / "decisions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    assert run_ids == {"A"}
