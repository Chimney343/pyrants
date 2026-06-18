# AGENTS.md — pyrants

<!-- Add your custom instructions below. Repowise will never modify anything outside the REPOWISE markers. -->

> **READ THIS FIRST — AGENT DIRECTIVE**
>
> 1. **The engine you must work on is written in C and lives in `/engine_c`.** All engine logic, rules, state, and simulation work should target the C codebase under `/engine_c`. The Python `engine/` directory is a **deprecated legacy port** — do not treat it as the engine, do not extend it, and only touch it when explicitly asked. Before editing anything engine-related, orient yourself in `/engine_c` first.
> 2. **Use the Repowise MCP tools everywhere possible.** This repo is indexed by Repowise. Prefer Repowise tools (`get_answer`, `get_context`, `get_symbol`, `search_codebase`, `get_why`, `get_risk`, `get_dead_code`, `get_overview`) over manual `grep`/`Read` loops for orientation, discovery, rationale, and risk assessment. See the **Repowise MCP Tools** section below for the full tool guide. Always verify Repowise output against the actual source files before making changes, and heed any `stale_warning` in `_meta`.

## CRITICAL: Engine Language

When discussing the **engine**, always remember: the engine is written in **C**, located at `/engine_c`. Never treat the Python `engine/` directory as if it is the engine itself — it is an old Python version of the C engine.

## Project Overview

**pyrants** is a turn-based board game engine for *Tyrants of the Underdark*. The active engine is written in **C** and lives in `/engine_c`; it is a pure library (no I/O) exposing state, rules, moves, phases, scoring, a card-effect runtime, player-view projection, save/load, and JSON loading via cJSON. A Python package wraps the C engine (bindings in `engine_c/bindings/`) and provides the terminal UI, simulation, OpenSpiel integration, and tooling. The legacy `engine/` directory is a **deprecated Python port** — do not extend it.

Python side: Python 3.12+, Pydantic-typed state, headless simulation, terminal UI interface.

## Architecture

```
/engine_c              C engine (source of truth): *.c/*.h, compile.bat, Makefile, engine_c.dll
/engine_c/bindings     Python ctypes/CPython bindings to engine_c.dll
/engine_c/tests        C unit tests (test_view, test_describe, test_saveload, test_generic_actions)
/engine                DEPRECATED legacy Python engine — do not extend
/interface             Terminal UI (renderer, viewers, board creator, CLI)
/openspiel_pyrants     OpenSpiel pyspiel wrapper + determinization
/game_setup            Loaders, state generator, board package, scenarios
/data                  JSON content: boards, cards, decks, layouts, scenarios
/tests                 pytest suite (Python side, incl. C-binding tests)
/scripts               Benchmarks, random walk, scenario/deck generation, IS-MCTS runner
```

## Directory Map

| Directory | Purpose |
|-----------|---------|
| `engine_c/` | **Active C engine**: state, rules, moves, phases, scoring, generic_runtime, actions, selection, player_view, loader, view, describe, saveload |
| `engine_c/bindings/` | Python bindings to `engine_c.dll` (session runner, etc.) |
| `engine_c/tests/` | C unit tests (`test_view.c`, `test_describe.c`, `test_saveload.c`, `test_generic_actions.c`) |
| `engine/` | **DEPRECATED** legacy Python port — only touch when explicitly asked |
| `interface/` | Terminal UI: board renderer, game viewer, replay viewer, board creator, CLI parser |
| `openspiel_pyrants/` | OpenSpiel wrapper: game, state, action encoding, observer, determinization |
| `game_setup/` | Loaders, state generator, board package, scenarios, random state search |
| `game_setup/scenario_generation/` | Card scenario discovery and injection |
| `data/` | JSON content: boards, cards (catalog, effect families, schemas), decks (11 rosters), layouts (2), scenarios (125+ card scenarios) |
| `tests/` | pytest suite: 40 test files covering rules, state, scoring, CLI, scenarios, board, renderer, viewer, simulation, session, engine purity, card model, generic interpreter, C bindings |
| `scripts/` | Utilities: benchmark, random walk, catalog audit, scenario generation, deck artifact generation, review workbook, execution audit, IS-MCTS runner |
| `docs/` | Game manual, engine/cards/board-creator status docs |
| `assets/` | Board/map images |
| `artifacts/` | Run outputs: replay logs, profiler data, card stuck reports, catalog consistency reports |

## Entry Points

| File | Purpose | How to run |
|------|---------|-----------|
| `game_session.py` | Shared session controller (state + move log snapshots) | `python game_session.py` |
| `game_simulation.py` | Headless simulation runner | `just game-simulate` or `python game_simulation.py --players 2 --seed 42 --policy random` |
| `game_view.py` | Structured game state projection (no I/O) | Import only |
| `interface/game_viewer.py` | Interactive terminal game viewer (defaults to `--engine c`) | `just game-viewer` (C) / `just game-viewer-py` (legacy Python) |
| `interface/replay_viewer.py` | Step through saved replays | `just replay-viewer` |
| `interface/board_creator.py` | Interactive board creator | `just board-creator` |
| `scripts/run_ismcts.py` | IS-MCTS bot runner against OpenSpiel wrapper | `just ismcts` (Python backend) / `just ismcts-c` (C backend) |
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
- Headless simulation: `just game-simulate` (override `players`, `seed`, `policy`, `max_steps`)
- Replay viewer: `just replay-viewer`
- Board creator: `just board-creator`
- IS-MCTS: `just ismcts` (Python backend) or `just ismcts-c` (C backend); quick smoke: `just ismcts-quick`
- Hot-reload is not used; this is a CLI/library project — re-run the relevant command after edits.
- After editing C sources, **rebuild** (`just build-c`) before running Python tools that load `engine_c.dll`.

## Testing Instructions

**Python tests** (pytest, `testpaths = ["tests"]`, naming `tests/test_*.py`):
- Run all: `just test` (== `.venv/Scripts/python.exe -m pytest -q`)
- Run one file: `python -m pytest tests/test_rules_basics.py`
- Run by name/keyword: `python -m pytest -k "promotion"` ; by node id: `python -m pytest tests/test_rules_basics.py::test_name`
- OpenSpiel wrapper tests: `just openspiel-test`
- Coverage: `python -m pytest --cov` (no fixed threshold; keep new code covered)

**C engine tests** (`engine_c/`):
- Build + run the C suite: `just build-c` (compiles and runs `test_engine`, `test_view`, `test_describe`, `test_generic_actions`, `test_saveload`)
- Run already-built C test binaries: `just test-c`
- Python-side C-binding tests: `just test-c-python` (runs `tests/test_engine_c.py -v`)
- C test sources live in `engine_c/tests/` (`test_view.c`, `test_describe.c`, `test_saveload.c`, `test_generic_actions.c`) plus top-level `engine_c/test_engine.c`, `test_generic.c`, `test_intern_c.c`.

**Always run both `ruff check .` and the relevant test suite before committing.** Add or update tests for any code you change.

## Code Style

- **Python:** ruff (line-length 120, target `py312`); selected rules `E,F,I,B,UP,SIM` (E501 ignored). Run `ruff check .` before committing.
- **C:** `-Wall -Wextra -std=c11` (GCC) / `/W3 /std:c11 /MT` (MSVC). Keep the engine pure — no I/O, no platform-specific calls in library sources.
- **Engine purity:** `engine_c/` (and the legacy `engine/`) must contain no I/O and no side effects. Enforced on the Python side by `tests/test_engine_purity.py`.
- **Domain types:** Pydantic models for Python domain types; pure-function state transitions on the C side (`apply(state, move) -> state'`).
- **File organization:** headers (`*.h`) declare public surfaces; implementations in matching `*.c`. New engine features go in `/engine_c`, never in `/engine`.

## Build and Deployment

- **C build (Windows/MSVC):** `just build-c` → `engine_c/compile.bat [debug|release]` produces `libengine.lib`, `test_*.exe`, and `engine_c.dll` (exports per `engine_c.def`).
- **C build (GCC/MinGW/Linux/macOS):** `cd engine_c && make` → `libengine.a`; `make test` builds and runs `test_engine`.
- **Python:** no separate build step; install deps and run. The C `engine_c.dll` must be built and present for any `--engine c` tooling or C-binding tests to work.
- **CI:** no `.github/workflows` present in the repo; validation is local (`just test`, `just build-c`, `just test-c-python`, `ruff check .`).
- **Artifacts:** generated outputs (replays, profiler, stuck reports) go under `artifacts/` and are not shipped.

## Pull Request Guidelines

- Title format: `[area] Brief description` (e.g. `[engine-c] fix promotion edge case`, `[ui] add replay scrubber`).
- Required pre-commit checks: `ruff check .`, `just test`, `just build-c` + `just test-c` / `just test-c-python` (when touching `/engine_c` or bindings).
- Engine changes must keep `tests/test_engine_purity.py` green and add/extend C or Python tests covering the new behavior.
- Do not extend the deprecated `engine/` Python port in a PR unless explicitly scoped.
- Keep commits focused; do not mix engine, UI, and data-format changes in one PR.

## Debugging and Troubleshooting

- **`engine_c.dll` not found / import errors from bindings:** rebuild with `just build-c` and ensure the DLL is in `engine_c/` on the loader's path.
- **C tests fail to link:** rerun `just build-c` from a clean state (`cd engine_c && nmake /f Makefile clean` or delete `*.obj`/`*.lib`); confirm VS 2022 Build Tools + C++ workload are installed.
- **Stale Repowise index:** the auto-generated block below may lag HEAD; trust source files first and heed any `stale_warning` in `_meta` from Repowise tools.
- **Card-stuck states:** `just card-stuck-check` (and CI variant `just card-stuck-check-ci`) detect rosters that deadlock; reports written to `artifacts/card_stuck_report.json`.
- **Performance profiling:** `just ismcts-perf` / `just ismcts-c-perf` produce cProfile output under `artifacts/ismcts/`.

> **Note:** The Repowise index below was last generated 2026-06-04 (commit `2a60abe`).
> Current HEAD is `e7791be` (3 commits ahead). The index is stale.

<!-- REPOWISE:START — Do not edit below this line. Auto-generated by Repowise. -->
## IMPORTANT: Codebase Intelligence Instructions for pyrants

> This repository is indexed by [Repowise](https://repowise.dev).
> Use the MCP tools below for orientation, discovery, and enriched context
> (documentation, ownership, history, decisions). **Always verify against
> actual source files before making changes** — the index may be stale.

Last indexed: 2026-06-04 (commit 2a60abe). Confidence: 100%.
### Architecture
**Repo** is a turn-based board game engine: it consumes scenario definitions and board packages from JSON and TOML configuration files, processes them through a game-setup pipeline that validates components and initializes a state machine, then executes player moves through a rules engine that enforces game logic, phases, and scoring, ultimately producing a rendered board view via a Python interface and optionally generating simulation traces for replay analysis. | Layer | Technology | Purpose |
|---|---|---|
| Core Engine | Python 3.x | State management, rule enforcement, move execution, scoring |
| Game Setup | Python, JSON, TOML | Parsing scenario definitions, board components, validation |
| Interface | Python (likely Pygame or Tkinter) | Real-time rendering of board view with camera zoom |
| Frontend (optional) | TypeScript (.kilo package) | Could provide an alternative web/desktop UI |
| Configuration | JSON, YAML, TOML | Game scenario and catalog files |
| Tooling | Justfile, Claude | Automation, documentation |



- **game_session.py** – Primary interactive entry point for a live game session (state-driven, user moves). - **game_simulation.py** – Headless simulation mode: runs automated moves or replays for testing and analysis. - **game_view.py** – Possibly a viewer entry point to replay saved states or visualize scenarios.
### Key Modules
| Module | Purpose | Owner |
|--------|---------|-------|
| `community-1` | The tests module is the quality assurance layer of repowise's Tyrants of the Und | — |
| `community-0` | The skills/impeccable module is the **skill lifecycle and injection subsystem**  | — |
| `community-3` | The interface module is the graphical presentation and authoring subsystem of th | — |
| `community-2` | The tests module is the verification and validation layer of the repowise system | — |
| `community-248` | The **tests** module is the verification subsystem of repowise — it consumes gen | — |
### Entry Points
- `.agents/skills/impeccable/scripts/cleanup-deprecated.mjs`
- `.agents/skills/impeccable/scripts/design-parser.mjs`
- `.agents/skills/impeccable/scripts/detect-csp.mjs`
- `.agents/skills/impeccable/scripts/is-generated.mjs`
- `.agents/skills/impeccable/scripts/live-accept.mjs`
- `.agents/skills/impeccable/scripts/live-browser.js`
- `.agents/skills/impeccable/scripts/live-inject.mjs`
- `.agents/skills/impeccable/scripts/live-poll.mjs`
- `.agents/skills/impeccable/scripts/live-server.mjs`
- `.agents/skills/impeccable/scripts/live-wrap.mjs`
### Tech Stack
**Languages:** Python
**Frameworks:** Pydantic

### Architectural Layers
| Layer | Files | Purpose |
|-------|-------|---------|
| Deck Artifact Generator | 35 | Generates initial deck artifacts for the first deck setup. |
| Test Suite and Manifests | 37 | Contains test cases for deck rosters, effect families schema, engine purity, alo |
| Deck Roster Data | 6 | JSON data file containing the roster for the first deck. |
| Interface Package Init | 7 | Package initialization file for the interface module. |
| Scripts Package Init | 2 | Package initialization file for the scripts module. |
| pyproject | 1 |  |
| agents | 1 |  |
| product | 1 |  |
| skills/grug-brain-development | 1 |  |
| skills-lock | 1 |  |

### Guided Tour (8 steps)
1. **Game Session Entry Point** — `game_session.py`
2. **Core Game State Definition** — `engine/state.py`
3. **Game Moves and Actions** — `engine/moves.py`
4. **Rules and Validation** — `engine/rules.py`
5. **Game Setup and Data Loading** — `game_setup/loaders.py`
6. **Game Content Data Files** — `data/cards/effect_families.json`
... and 2 more steps
### Hotspots (High Churn)
| File | Churn | 90d Commits | Owner |
|------|-------|-------------|-------|
| `engine/rules.py` | 100.0th %ile | 3 | Chimney343 |
| `tests/test_generic_interpreter.py` | 99.7th %ile | 3 | Chimney343 |
| `interface/game_viewer.py` | 99.4th %ile | 3 | Chimney343 |
| `interface/board_creator.py` | 99.1th %ile | 2 | Chimney343 |
| `data/cards/catalog.json` | 98.9th %ile | 2 | Chimney343 |

## Code health
Hotspot health: 7.25/10 (stable) ·
Average: 7.46/10 ·
Worst: 5.3/10 (`.augment/skills/impeccable/scripts/design-parser.mjs`)

### Critical biomarkers
- `engine/state.py` — untested hotspot — impact −2.0
- `.agents/skills/impeccable/scripts/live-browser.js` — large method (<anonymous>) — impact −1.1
- `game_view.py` — complex method (describe_move) — impact −0.5
- `.agents/skills/impeccable/scripts/live-server.mjs` — complex method (createRequestHandler) — impact −0.5
- `.agents/skills/impeccable/scripts/live-server.mjs` — complex method (validateEvent) — impact −0.5

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
