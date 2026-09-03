# AGENTS.md — pyrants

<!-- Add your custom instructions below. Repowise will never modify anything outside the REPOWISE markers. -->

> **READ THIS FIRST — AGENT DIRECTIVE**
>
> 1. **The engine is written in C and lives in `/engine_c`.** All engine logic, rules, state, and simulation work must target the C codebase under `/engine_c`. The legacy Python `engine/` directory has been removed — `/engine_c` is the only engine. Before editing anything engine-related, orient yourself in `/engine_c` first.
> 2. **Use the Repowise MCP tools everywhere possible.** This repo is indexed by Repowise. Prefer Repowise tools (`get_answer`, `get_context`, `get_symbol`, `search_codebase`, `get_why`, `get_risk`, `get_dead_code`, `get_overview`) over manual `grep`/`Read` loops for orientation, discovery, rationale, and risk assessment. See the **Repowise MCP Tools** section below for the full tool guide. Always verify Repowise output against the actual source files before making changes, and heed any `stale_warning` in `_meta`.

## CRITICAL: Engine Language

When discussing the **engine**, always remember: the engine is written in **C**, located at `/engine_c`. There is no Python engine — `/engine_c` is the only implementation.

## Project Overview

**pyrants** is a turn-based board game engine for *Tyrants of the Underdark*. The engine is written in **C** and lives in `/engine_c`; it is a pure library (no I/O) exposing state, rules, moves, phases, scoring, a card-effect runtime, player-view projection, save/load, and JSON loading via cJSON. A Python package wraps the C engine (bindings in `engine_c/bindings/`) and provides the terminal UI, simulation, OpenSpiel integration, and tooling. The legacy Python `engine/` directory has been removed.

Python side: Python 3.12+, Pydantic-typed state, headless simulation, terminal UI interface.

## Architecture

Condensed layout below; see [docs/repo-structure.md](docs/repo-structure.md) for the fuller reference (per-module file tables, entry points, conventions).

```
/engine_c              C engine (source of truth): *.c/*.h, compile.bat, Makefile, engine_c.dll
/engine_c/bindings     Python ctypes/CPython bindings to engine_c.dll
/engine_c/tests        C unit tests (test_view, test_describe, test_saveload, test_generic_actions)
/interface             Terminal UI (renderers, game viewer, board creator)
/openspiel_pyrants     OpenSpiel pyspiel wrapper + determinization
/game_setup            Loaders, market setup, board package, types, scenario generation
/data                  JSON content: boards, cards, decks, layouts, scenarios
/tests                 pytest suite (Python side, incl. C-binding tests)
/scripts               Scenario/deck generation, IS-MCTS runner, catalog audit
```

## Directory Map

| Directory | Purpose |
|-----------|---------|
| `engine_c/` | **Active C engine**: state, rules, moves, phases, scoring, generic_runtime, actions, selection, player_view, loader, view, describe, saveload |
| `engine_c/bindings/` | Python bindings to `engine_c.dll` (session runner, etc.) |
| `engine_c/tests/` | C unit tests (`test_view.c`, `test_describe.c`, `test_saveload.c`, `test_generic_actions.c`) |
| `interface/` | Terminal UI: board renderer, game viewer, board creator |
| `openspiel_pyrants/` | OpenSpiel wrapper: game, state, action encoding, observer, determinization |
| `game_setup/` | Loaders, market setup, board package, types, random state search |
| `game_setup/scenario_generation/` | Card scenario discovery and injection |
| `data/` | JSON content: boards, cards (catalog, effect families, schemas), decks (11 rosters), layouts (2), scenarios (125+ card scenarios) |
| `tests/` | pytest suite covering board, renderer, scenario market policy, C bindings |
| `scripts/` | Utilities: catalog audit, scenario generation, deck artifact generation, review workbook, execution audit, IS-MCTS runner |
| `docs/` | Game manual, engine/cards/board-creator status docs |
| `assets/` | Board/map images |
| `artifacts/` | Run outputs: replay logs, profiler data, card stuck reports, catalog consistency reports |

## Entry Points

| File | Purpose | How to run |
|------|---------|-----------|
| `interface/game_viewer.py` | Interactive terminal game viewer (C engine) | `just game-viewer` |
| `interface/replay_viewer.py` | Read-only IS-MCTS replay viewer (subclasses `GameViewerApp`; pure helpers in `interface/replay_loader.py` + `interface/replay_player.py`) | `just replay-viewer` |
| `interface/board_creator.py` | Interactive board creator | `just board-creator` |
| `scripts/run_ismcts.py` | IS-MCTS bot runner against OpenSpiel wrapper (C backend) | `just ismcts` |
| `engine_c/bindings/` | C engine Python bindings | `just simulate-c` |

## Setup Commands

- **Python (required):** Python 3.12+
- **Install dependencies:** `uv sync` (preferred; uses `uv.lock`) or `poetry install` (uses `poetry.lock`). Both lockfiles are present; pick one and stick with it.
- **Run anything via the venv Python:** commands use `.venv/Scripts/python.exe` (see `justfile`). Create the venv with `uv venv` or `python -m venv .venv` then sync.
- **C toolchain (Windows):** Visual Studio 2022 Build Tools with the C++ workload (needed for `engine_c/compile.bat`). On Linux/macOS/MinGW use `make` in `engine_c/`.
- **Just:** install the `just` command runner to use the `just <task>` shortcuts below.

## Development Workflow

- Build the C engine + run its tests + produce `engine_c.dll`:
  ```bash
  just build-c        # runs engine_c/compile.bat (Windows/MSVC)
  # or, on GCC platforms:
  cd engine_c && make && make test
  ```
- Interactive terminal viewer (C backend by default): `just game-viewer`
- Headless simulation: `just simulate-c` (override `players`, `seed`, `max_steps`)
- Board creator: `just board-creator`
- IS-MCTS: `just ismcts` (C backend); quick smoke: `just ismcts-quick`
- Hot-reload is not used; this is a CLI/library project — re-run the relevant command after edits.
- After editing C sources, **rebuild** (`just build-c`) before running Python tools that load `engine_c.dll`.

## Testing Instructions

**Python tests** (pytest, `testpaths = ["tests"]`, naming `tests/test_*.py`):
- Run all: `just test` (== `.venv/Scripts/python.exe -m pytest -q`)
- Run one file: `python -m pytest tests/test_board_package.py`
- Run by name/keyword: `python -m pytest -k "promotion"` ; by node id: `python -m pytest tests/test_board_package.py::test_name`
- OpenSpiel wrapper tests: `just openspiel-test`
- Coverage: `python -m pytest --cov` (no fixed threshold; keep new code covered)

**C engine tests** (`engine_c/`):
- Build + run the C suite: `just build-c` (compiles and runs `test_engine`, `test_view`, `test_describe`, `test_generic_actions`, `test_saveload`)
- Run already-built C test binaries: `just test-c`
- Python-side C-binding tests: `just test-c-python` (runs `pytest tests/c_engine -v`)
- C test sources live in `engine_c/tests/` (`test_view.c`, `test_describe.c`, `test_saveload.c`, `test_generic_actions.c`) plus top-level `engine_c/test_engine.c`, `test_generic.c`, `test_intern_c.c`.

**Always run both `ruff check .` and the relevant test suite before committing.** Add or update tests for any code you change.

## Code Style

- **Python:** ruff (line-length 120, target `py312`); selected rules `E,F,I,B,UP,SIM` (E501 ignored). Run `ruff check .` before committing.
- **C:** `-Wall -Wextra -std=c11` (GCC) / `/W3 /std:c11 /MT` (MSVC). Keep the engine pure — no I/O, no platform-specific calls in library sources.
- **Engine purity:** `engine_c/` must contain no I/O and no side effects. The C engine is a pure library by construction.
- **Domain types:** Pydantic models for Python domain types; pure-function state transitions on the C side (`apply(state, move) -> state'`).
- **File organization:** headers (`*.h`) declare public surfaces; implementations in matching `*.c`. New engine features go in `/engine_c`.

## Build and Deployment

- **C build (Windows/MSVC):** `just build-c` → `engine_c/compile.bat [debug|release]` produces `libengine.lib`, `test_*.exe`, and `engine_c.dll` (exports per `engine_c.def`).
- **C build (GCC/MinGW/Linux/macOS):** `cd engine_c && make` → `libengine.a`; `make test` builds and runs `test_engine`.
- **Python:** no separate build step; install deps and run. The C `engine_c.dll` must be built and present for any C-engine tooling or C-binding tests to work.
- **CI:** no `.github/workflows` present in the repo; validation is local (`just test`, `just build-c`, `just test-c-python`, `ruff check .`).
- **Artifacts:** generated outputs (replays, profiler, stuck reports) go under `artifacts/` and are not shipped.

## Pull Request Guidelines

- Title format: `[area] Brief description` (e.g. `[engine-c] fix promotion edge case`, `[ui] add replay scrubber`).
- Required pre-commit checks: `ruff check .`, `just test`, `just build-c` + `just test-c` / `just test-c-python` (when touching `/engine_c` or bindings).
- Engine changes must add/extend C or Python tests covering the new behavior.
- Keep commits focused; do not mix engine, UI, and data-format changes in one PR.
- If a PR moves/renames/deletes a file or shifts line ranges that `docs/**/*.md` cites by path or `path:line`, update or re-verify those citations. Run `just docs-check` to catch broken ones mechanically.

## Debugging and Troubleshooting

- **`engine_c.dll` not found / import errors from bindings:** rebuild with `just build-c` and ensure the DLL is in `engine_c/` on the loader's path.
- **C tests fail to link:** rerun `just build-c` from a clean state (`cd engine_c && nmake /f Makefile clean` or delete `*.obj`/`*.lib`); confirm VS 2022 Build Tools + C++ workload are installed.
- **Stale Repowise index:** the auto-generated block below may lag HEAD; trust source files first and heed any `stale_warning` in `_meta` from Repowise tools.
- **Performance profiling:** `just ismcts-perf` produces cProfile output under `artifacts/ismcts/`.

<!-- REPOWISE:START — Do not edit below this line. Auto-generated by Repowise. -->
## IMPORTANT: Codebase Intelligence Instructions for pyrants

> This repository is indexed by [Repowise](https://repowise.dev).
> Use the MCP tools below for orientation, discovery, and enriched context
> (documentation, ownership, history, decisions). **Always verify against
> actual source files before making changes** — the index may be stale.

Last indexed: 2026-06-27 (commit c4d2e5d). Confidence: 100%.
### Architecture
This repository implements a hybrid Python/C game engine for the card game **Pyrants** (a variant of the classic game “Ruritania”): it ingests game configuration files and board package definitions, applies turn-based game rules via a C‑core state machine exposed through Python bindings, executes moves with a deterministic random‑number generator and scoring logic, and produces serialized game states for both interactive play and reinforcement learning training through an OpenSpiel integration. ---



| Layer | Technology | Details |
|-------|------------|---------|
| **Core engine** | C (C11) | High‑performance state machine (engine_c/state.h, engine_c/arena.h, engine_c/intern.h). Runtime logic in engine_c/actions.c, engine_c/generic_runtime.c. |
| **Python bindings** | C Extension (CPython) | Bindings at engine_c/bindings/ (engine_bindings.py, ce_api.py, session.py).
### Key Modules
| Module | Purpose | Owner |
|--------|---------|-------|
| `community-1` | The tests/legacy_engine module is the **legacy game engine reference implementat | — |
| `community-0` | The engine_c module is the **core game-engine implementation layer** of the card | — |
| `community-3` | The openspiel_pyrants module is the **OpenSpiel integration layer** for the Pyra | — |
| `community-2` | The skills/impeccable module is the live-variant orchestration layer within the  | — |
| `community-248` | The **tests** module is the verification subsystem of repowise — it consumes gen | — |
| `community-4` | The tests/c_engine module is the **integration test suite** for the repowise C-e | — |
| `community-6` | The game_setup module is the **game-state construction and scenario generation l | — |
| `community-5` | The **interface** module is the presentation layer of the repowise board-game ap | — |
| `community-7` | The skills/skill-creator module is the core **skill optimization engine** in the | — |
| `community-400` | The data/scenarios module is the **validation and test harness** for the scenari | — |
### Entry Points
- `.augment/skills/impeccable/scripts/cleanup-deprecated.mjs`
- `.augment/skills/impeccable/scripts/design-parser.mjs`
- `.augment/skills/impeccable/scripts/detect-csp.mjs`
- `.augment/skills/impeccable/scripts/is-generated.mjs`
- `.augment/skills/impeccable/scripts/live-accept.mjs`
- `.augment/skills/impeccable/scripts/live-browser.js`
- `.augment/skills/impeccable/scripts/live-inject.mjs`
- `.augment/skills/impeccable/scripts/live-poll.mjs`
- `.augment/skills/impeccable/scripts/live-server.mjs`
- `.augment/skills/impeccable/scripts/live-wrap.mjs`
### Tech Stack
**Languages:** Python
**Frameworks:** Pydantic

### Architectural Layers
| Layer | Files | Purpose |
|-------|-------|---------|
| Determinization Core | 47 | Core module implementing determinization logic for the PyRants OpenSpiel environ |
| Utility Scripts | 58 | Collection of automation scripts for building workbooks, enriching catalogs, fin |
| Test Scenario Data | 19 | Test fixtures and JSON scenario files used for verifying card generation and beh |
| Architecture Decision Record | 31 | Records the architecture decision to treat the C engine as the source of truth. |
| Archived Planning Documents | 62 | Collection of archived planning documents, sweep results, and implementation not |
| Board Interface Rendering | 15 | Handles the visual representation and rendering of the game board, including can |
| Game Setup Loading | 14 | Manages the loading and generation of game scenarios, card data, market setup, a |
| Skill Creator Utilities | 5 | Provides utility scripts for evaluating, generating reports, and improving descr |
| Skill Packaging Tools | 2 | Contains scripts for quick validation and packaging of skills for deployment in  |
| Catalog Audit Scripts | 2 | Automated auditing and execution reporting for the game's catalog system to ensu |

### Guided Tour (10 steps)
1. **Project Overview** — `README.md`
2. **OpenSpiel Game Integration** — `openspiel_pyrants/__init__.py`
3. **C Engine Core** — `engine_c/state.h`
4. **Python Bindings to C Engine** — `engine_c/bindings/engine_bindings.py`
5. **Python Engine Logic** — `engine/state.py`
6. **Game Setup and Loading** — `game_setup/loaders.py`
... and 4 more steps
### Hotspots (High Churn)
| File | Churn | 90d Commits | Owner |
|------|-------|-------------|-------|
| `data/cards/catalog.json` | 100.0th %ile | 27 | Chimney343 |
| `tests/test_rules.py` | 99.8th %ile | 4 | Chimney343 |
| `interface/game_viewer.py` | 99.6th %ile | 17 | Chimney343 |
| `tests/test_rules_cards_a_m.py` | 99.5th %ile | 7 | Chimney343 |
| `data/scenarios/pending_modal_choice.json` | 99.4th %ile | 4 | Chimney343 |

## Code health
Hotspot health: 6.49/10 (stable) ·
Average: 7.21/10 ·
Worst: 1.0/10 (`engine/rules.py`)

### Critical biomarkers
- `.agents/skills/skill-creator/scripts/run_eval.py` — nested complexity (run_single_query) — impact −2.0
- `engine/helpers.py` — untested hotspot — impact −2.0
- `engine/rules.py` — untested hotspot — impact −2.0
- `engine/state.py` — untested hotspot — impact −2.0
- `engine_c/state.h` — untested hotspot — impact −2.0

### Repowise MCP Tools

This repo has the Repowise MCP server configured. The tools below answer questions `grep`/`Read` cannot. Every response carries an `_meta` envelope with `index_age_days`, `indexed_commit`, and a `stale_warning` only when the index has actually diverged from HEAD — silence means the index is current.

**When to call which tool:**

| Tool | What only this tool answers |
|------|------------------------------|
| `get_answer(question)` | Synthesised answer with verified citations and a calibrated `retrieval_quality`. First call for "how does X work" / "why is Y like this". On low confidence returns `best_guesses` with one-line justifications instead of an empty answer. |
| `get_context(targets=[...])` | Triage card for files/modules/symbols — title, summary, signatures, `hotspot` bit, `decision_records` titles, and `symbol_id`s to pipe into `get_symbol`. Use `include=["callers","ownership",...]` to widen. NOT for source bytes. |
| `get_symbol("path/to/file.py::Name")` | Raw source bytes for one indexed symbol with exact line bounds. Cheaper and safer than `Read` + offset math. Use the `symbol_id` returned by `get_context`. |
| `search_codebase(query, kind?)` | Find pages by concept when you don't know the file. Each result carries `search_method` (`embedding` vs `bm25` fallback). For exact identifiers use Grep — the tool will hint when it sees one. |
| `get_why(query, targets?)` | Architectural decision archaeology — *why* the code is shaped this way. Call before refactors or pattern divergences. Falls back to git archaeology when no ADRs exist for a file. |
| `get_risk(targets, changed_files?)` | What history says about touching these files: churn, owners, blast radius. Pass `changed_files` for PR mode → returns a `directive` (`will_break`, `missing_cochanges`, `missing_tests`). |
| `get_dead_code(...)` | Tiered unreachable / unused-export / zombie-package findings. Run before a cleanup sprint, not before a targeted fix. |
| `get_overview(repo?)` | Architecture map for an unfamiliar repo. One-time orientation; skip on subsequent calls in the same session. |

**Composition tips:**
- `get_answer` → if `confidence` is `medium`/`low`, follow the `best_guesses[0].file` or `fallback_targets[0]` into `get_context`, then `get_symbol` for bytes.
- `get_context` returns `decision_records` titles → call `get_why(targets=[...])` for the rationale.
- `get_context` returns `hotspot: true` → call `get_risk` before editing.
- PR review → `get_risk(targets=[...], changed_files=[...])`; read the `directive` block first.

**Verify when:** `_meta.stale_warning` is present, or `retrieval_quality` is `partial`/`weak`, or `search_method` is `bm25`. Otherwise trust the response and act on it.

### Codebase Conventions
**Commands:**
- Test: `pytest`
- Lint: `ruff check .`

<!-- REPOWISE:END -->
