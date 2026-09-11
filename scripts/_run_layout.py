"""Run-scoped output layout helpers for IS-MCTS runs.

Pure Python (no ``pyspiel``/``numpy``) so the layout rules are unit-testable
and usable by the runner, the experiment scripts, and the dataset builder.
Implements Phase 1 (Layer 0) of ``docs/nn-training-data-tdd-plan.md``.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

SCHEMA_VERSION = 2


class GameDirCollisionError(RuntimeError):
    """A ``game_XXXX/`` already belongs to a different run id.

    Raised by ``run_one_game`` before it opens any output file, so a second run
    into an existing directory can never silently overwrite file by file
    (finding F-025).
    """


def run_dir_name(run_id: str, now: datetime | None = None) -> str:
    """Return ``<YYYYMMDDTHHMMSSZ>_<run_id>`` for a run-scoped output dir."""
    if now is None:
        now = datetime.now(UTC)
    return f"{now.astimezone(UTC).strftime('%Y%m%dT%H%M%SZ')}_{run_id}"


def only_run_dir(base: str | Path) -> Path:
    """Return the single child directory of *base*.

    Tests that drive ``main()`` use this to resolve the nested run directory
    without hardcoding its timestamp name.
    """
    base = Path(base)
    children = sorted(p for p in base.iterdir() if p.is_dir())
    if len(children) != 1:
        raise AssertionError(f"expected exactly one run dir under {base}, found {children}")
    return children[0]


def collect_engine_provenance(root: str | Path = ".", run=subprocess.run) -> dict:
    """Return ``{engine_git_sha, engine_git_dirty, repo_git_dirty, engine_dll_sha256}``.

    Git being unavailable must never fail a run: every git field degrades to
    ``None``. ``run`` is injectable for tests.
    """
    root = Path(root)

    def _git(args: list[str]) -> subprocess.CompletedProcess:
        return run(["git", *args], cwd=str(root), capture_output=True, text=True)

    try:
        sha: str | None = _git(["rev-parse", "HEAD"]).stdout.strip() or None
    except Exception:
        sha = None

    try:
        porcelain = _git(["status", "--porcelain", "--", "engine_c"]).stdout
        dirty: bool | None = bool(porcelain.strip())
    except Exception:
        dirty = None

    try:
        repo_porcelain = _git(["status", "--porcelain"]).stdout
        repo_dirty: bool | None = bool(repo_porcelain.strip())
    except Exception:
        repo_dirty = None

    dll = root / "engine_c" / "engine_c.dll"
    dll_sha256: str | None = None
    if dll.exists():
        dll_sha256 = hashlib.sha256(dll.read_bytes()).hexdigest()

    return {
        "engine_git_sha": sha,
        "engine_git_dirty": dirty,
        "repo_git_dirty": repo_dirty,
        "engine_dll_sha256": dll_sha256,
    }


def write_json_atomic(path: str | Path, obj) -> None:
    """Serialise *obj* to *path* via a sibling ``.tmp`` file and ``os.replace``.

    A failure while serialising (e.g. a non-JSON value) leaves neither the
    destination nor a ``.tmp`` sibling behind.
    """
    path = Path(path)
    tmp = path.parent / (path.name + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise


def _jsonable(value):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def build_manifest(
    *,
    run_id: str,
    args,
    games: list[dict],
    provenance: dict,
    steps_enabled: bool,
) -> dict:
    """Build the run manifest written before the first game starts.

    ``args`` is an ``argparse.Namespace`` (or a plain dict); every field lands
    in ``config``. ``games`` is precomputed so ``setup_data_json`` is recorded
    per game (G11: it varies per ``game_index``).
    """
    config = _jsonable(vars(args) if hasattr(args, "__dict__") else dict(args))
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "created_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "engine_git_sha": provenance.get("engine_git_sha"),
        "engine_git_dirty": provenance.get("engine_git_dirty"),
        "repo_git_dirty": provenance.get("repo_git_dirty"),
        "engine_dll_sha256": provenance.get("engine_dll_sha256"),
        "steps_enabled": bool(steps_enabled),
        "config": config,
        "games": list(games),
    }
