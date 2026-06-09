# Repo-wide Cleanup Plan

## Scope

`pyrants` is a turn-based board game engine with three layers (`engine/`, `game_setup/`, `interface/`), three session entry points (`game_session.py`, `game_simulation.py`, `game_view.py`), and supporting `scripts/` and `tests/`. Out of ~400 indexed files, ~80 are Python source; the rest are docs, JSON data, agent skill bundles, and tooling.

This plan targets only the **whole repo cleanup** the user asked for. It is intentionally narrow: dead/stray code, unused orphans, and a small number of structural simplifications that clearly pay for themselves. It is **not** a refactor of the engine, the rules interpreter, or the UI renderer — those are churn-heavy hotspots (100th / 99.7th / 99.4th percentile) whose refactors belong in dedicated, scoped PRs and have already been split out in `.kilo/plans/split-generic-runtime.md`.

## Findings (with evidence)

### F1. `argdump.cs` is an orphan
- `C:\Users\mkkom\pyrants\argdump.cs` (146 bytes, last touched 2026-05-04)
- Contents: a one-class C# program that prints `argv` — no references anywhere in the repo (`grep argdump` → 0 matches in `*.py/*.toml/*.md/*.json/*.cs/*.ps1/*.lock`).
- Not listed in `pyproject.toml`, `justfile`, or any script. Safe to delete.

### F2. `install.ps1` is for a different project
- `C:\Users\mkkom\pyrants\install.ps1` installs `codebase-memory-mcp` (DeusData/codebase-memory-mcp) into `%LOCALAPPDATA%\Programs\codebase-memory-mcp`. The repo's own `pyproject.toml` / `justfile` use `uv` / `poetry`. Not referenced by any other file.
- Likely left over from an unrelated session. Safe to delete.

### F3. `interface/camera.py` is misnamed and mis-placed
- File is 69 lines containing `compute_fit_zoom` (a fit-to-viewport geometry helper). Docstring: *"Shared camera helpers for fit-to-board zoom calculations."*
- Imported by 3 places, all using `compute_fit_zoom`:
  - `interface/game_viewer.py:33` — UI fit-zoom
  - `interface/board_creator.py:20` — board creator fit-zoom
  - `tests/test_camera.py:5` — direct unit test
- Despite the name `camera.py`, the file has **no camera/capture code** — the index's overview is wrong on this point. The real computer-vision/camera capture is the "physical board integration" referenced in the architecture map but is not in this file. (The file's contents contradict its module name.)
- Cleanup: **rename to `interface/view_fit.py`** (or `viewport_fit.py`) and update the 3 import sites. Pure mechanical, zero behavior change. Test file rename: `tests/test_camera.py` → `tests/test_view_fit.py`.

### F4. Dead code: zero findings at high confidence
- `repowise_get_dead_code(tier="high")` → 0 high-confidence findings, 1 unreachable file (inspected: the `interface/camera.py` "rebranding" candidate; that's F3, not a deletion).
- No safe-to-delete unused exports or unreferenced modules in the Python source.

### F5. `interface/parser.py::parse_command` is the worst complexity hotspot in the project
- 290 lines, CCN 47, max nesting 5, cognitive complexity 122.
- Single function, single file, single responsibility already (parse CLI string → typed `ParsedCommand`). Splitting it further is a **refactor**, not a cleanup — defer to a dedicated plan.
- **Out of scope** for this plan.

### F6. `engine/rules.py`, `engine/generic_runtime/` are actively churning
- 100th / 97th percentile churn, bus factor 1, primarily refactored. Already has a split plan at `.kilo/plans/split-generic-runtime.md`. **Out of scope** for this cleanup.

### F7. Untested hotspots (`engine/moves.py`, `engine/state.py`, `game_setup/loaders.py`)
- 15–34 dependents each, no paired test file. Critical for safety, but adding tests is a behavior-adding task, not a cleanup. **Out of scope**.

## Plan

A single small PR containing four independent, reversible changes. Each is small enough that a code review can verify by inspection.

### 1. Delete `argdump.cs`
- File has zero references in the repo. Pure orphan from a debug session.
- No risk: no imports, no build hook, no docs reference.

### 2. Delete `install.ps1`
- Installer for a third-party tool (`codebase-memory-mcp`) unrelated to this repo. Not referenced by `justfile`, `pyproject.toml`, `README.md`, or `AGENTS.md`.
- If the user actually uses it, the action is trivially reversible via git.

### 3. Rename `interface/camera.py` → `interface/view_fit.py`
- Rename file, rename inside-file references (`compute_fit_zoom` is fine — keep API name), update the 3 import sites:
  - `interface/game_viewer.py:33`
  - `interface/board_creator.py:20`
  - `tests/test_camera.py:5` (file itself should also be renamed to `test_view_fit.py` for consistency)
- Update the module docstring to reflect what it actually does ("fit-to-viewport zoom calculation"), dropping the misleading "camera" word.
- Zero behavior change; tests should pass unchanged aside from the new file name.

### 4. Re-baseline Repowise index after the rename (informational, not a code change)
- After the rename, `interface/camera.py` will show as a deletion in the next index run. The user can re-run their indexer; nothing in the codebase depends on the index.

## Validation

After the cleanup, run from the project root:

```
pytest
ruff check .
```

These are the two commands listed in `AGENTS.md`. Both must pass. The view_fit rename is the only change that touches a code path exercised by tests (`test_camera.py` → `test_view_fit.py`); the two deletions cannot affect runtime behavior.

## What this plan deliberately does NOT do

- **Refactor `interface/parser.py::parse_command`** — biggest complexity hotspot (CCN 47), but a real refactor with semantic risk; belongs in a dedicated plan.
- **Split `engine/generic_runtime/`** — already planned in `.kilo/plans/split-generic-runtime.md`.
- **Add tests for `engine/moves.py` / `engine/state.py` / `game_setup/loaders.py`** — these are untested hotspots, but adding tests is a behavior-adding change, not a cleanup.
- **Touch the `.agents/`, `.augment/`, `.roo/` skill bundles** — those are third-party tool state, not repo code.
- **Reformat / re-style** the rest of the repo — `ruff` is the source of truth for style; no manual sweep.

## Estimated impact

- Lines removed: ~25 (argdump.cs + install.ps1 + 2-file rename net ≈ 0).
- Modules affected: 5 (`interface/camera.py` rename touches 2 importers + 1 test).
- Risk: low. Every change is either a deletion of a zero-reference file or a mechanical rename.
- Behavior change: none.

## Open question for the user

None blocking. The only judgment call is the new name for `interface/camera.py`. Options:
- `interface/view_fit.py` (recommended — short, accurate)
- `interface/fit_zoom.py` (mirrors the public function name)
- `interface/viewport.py` (more generic, leaves room for more viewport helpers)

If the user has a preference, I'll use it; otherwise default to `view_fit.py`.
