# pyrants — Repository Structure & Purpose

**pyrants** is a turn-based board game engine for *Tyrants of the Underdark*. The engine is written in **C** (pure library, no I/O) and lives in `engine_c/`; a Python package (`engine_c/bindings/`) wraps the compiled DLL and provides the terminal UI, headless simulation, OpenSpiel integration, and tooling. The legacy Python `engine/` directory has been removed.

---

## Top-Level Layout

```
pyrants/
├── engine_c/               # C engine (source of truth): *.c/*.h, compile.bat, Makefile, engine_c.dll
├── engine_c/bindings/      # Python ctypes/CPython bindings to engine_c.dll
├── engine_c/tests/         # C unit tests
├── openspiel_pyrants/      # OpenSpiel (pyspiel) wrapper (C backend)
├── game_setup/             # Loaders, market setup, board package, types, scenario generation
├── interface/              # Terminal UI: game viewer, board creator, renderers
├── scripts/                # CLI utilities, IS-MCTS runner, catalog audit
├── data/                   # JSON content: boards, cards, decks, scenarios
├── tests/                  # pytest suite (incl. C-binding tests)
├── artifacts/              # Run outputs (gitignored)
├── docs/                   # Game manual, status docs
├── assets/                 # Board/map images
├── justfile                # Task runner commands
└── pyproject.toml          # Project config, deps, lint settings
```

---

## Core Engine (`engine_c/`)

The engine is the heart of the project. It is strictly **pure** — no I/O, no side effects. All state transitions are pure functions (`apply(state, move) -> state'`). The Python bindings expose it via `engine_c/bindings/`.

| Area | Purpose |
|------|---------|
| `state.h` / `state.c` | C `GameState` structs, definitions, board/player/card state |
| `rules` / `actions` / `phases` / `scoring` | Pure state-transition and scoring logic |
| `generic_runtime` | Data-driven card-effect interpreter |
| `player_view` / `view` / `describe` | Player-view projection and move description |
| `loader` / `saveload` | JSON loading (cJSON) and scenario save/load |
| `engine_c/bindings/session.py` | `CSession` — mirrors the old `GameSession` API against the DLL |
| `engine_c/bindings/view.py` | `build_c_game_view` / `CGameViewData` for UI projection |

---

## OpenSpiel Wrapper (`openspiel_pyrants/`)

This package wraps the C engine as a **DeepMind OpenSpiel** game, enabling IS-MCTS and other game-theoretic algorithms. It is registered as `python_pyrants_c` inside OpenSpiel.

### Module Details

| File | Purpose |
|------|---------|
| `__init__.py` | Registers `python_pyrants_c` with `pyspiel.register_game()` |
| `game_c.py` | `PyrantsCGame(pyspiel.Game)` — declares `GameType`/`GameInfo` and owns a `CEngine` |
| `state_c.py` | `PyrantsCState(pyspiel.State)` — adapts the C engine; chance node selects a shuffle seed, then `CEngineAdapter` drives all transitions |
| `action_encoding_c.py` | `compute_c_action_map(adapter)` — Move ↔ int mapping in native engine order; `NUM_DISTINCT_ACTIONS = 1024` |
| `observer_c.py` | `PyrantsCObserver` — observation/information-state strings |

### Tests (`openspiel_pyrants/tests/`)

- `test_pyrants_c_register.py` — loads via `pyspiel.load_game("python_pyrants_c")`
- `test_resample_c.py` — determinization contract for the C backend
- `test_determinize_c.py` — determinization helpers
- `test_action_encoding.py` — C action-map ordering and action round-trip
- `test_ismcts_smoke_c.py` — IS-MCTS smoke run against the C backend
- `test_run_ismcts_runner.py` — runner smoke + move normalization

---

## Supporting Packages

### Game Setup (`game_setup/`)

| File | Purpose |
|------|---------|
| `types.py` | Engine-agnostic Pydantic models (`NodeKind`, `BoardDefinition`, `CardCatalog`, `SetupDefinition`, `GameDefinition`) |
| `loaders.py` | `build_game_definition_from_files()`, `build_game_definition_from_dicts()`, `default_catalog_registry()` — JSON loading + validation |
| `board_package.py` | Board definitions + layouts, `BoardPackageDefinition`, `BoardLayoutDefinition` |
| `market_setup.py` | Market deck construction, `combine_two_deck_market_setup()`, `discover_full_deck_profiles()`, `pick_random_pair()` |
| `scenario_generation/rosters.py` | Roster/scenario helpers (`iter_roster_card_ids`, `_resolve_two_deck_pairing`, `StopConditions`) |

### Interface (`interface/`)

Terminal UI built on Tk:

| File | Purpose |
|------|---------|
| `game_viewer.py` | Interactive terminal game viewer (C engine) |
| `board_creator.py` | Interactive board designer |
| `board_renderer.py` | Board drawing logic |
| `shared_board_renderer.py` | Shared rendering utilities |
| `game_renderer.py` | Read-only gameplay board renderer |

### Scripts (`scripts/`)

| File | Purpose |
|------|---------|
| `run_ismcts.py` | IS-MCTS runner: parallel game execution, per-game decision traces, cross-run summary CSV/Markdown, metrics |
| `generate_card_scenarios.py` | Generate card scenario data (C engine) |
| `catalog_audit.py` | Card catalog consistency checker |
| `generate_first_deck_artifacts.py` | Generate initial deck artifacts |
| `_obs.py` | Structured logging, metrics, run-ID helpers for IS-MCTS |
| `_replay_payload.py` | Replay payload builders for IS-MCTS runs |

### Data (`data/`)

| Directory | Content |
|-----------|---------|
| `boards/` | Board definitions (base game JSON) |
| `cards/` | Card catalog, effect families, schemas |
| `decks/` | 11 roster definitions + `base_setup.json` |
| `layouts/` | Board layout configs (2 layouts) |
| `scenarios/` | 125+ card scenario definitions |

---

## Entry Points

| Command | Entry Point | Description |
|---------|------------|-------------|
| `just game-viewer` | `interface/game_viewer.py` | Interactive terminal play (C engine) |
| `just simulate-c` | `engine_c/bindings/session.py` | Headless simulation |
| `just board-creator` | `interface/board_creator.py` | Design boards |
| `just ismcts` | `scripts/run_ismcts.py` | IS-MCTS bot tournament (C backend) |
| `just openspiel-test` | `pytest openspiel_pyrants/tests/` | OpenSpiel wrapper tests |
| `just openspiel-smoke` | — | Quick registration check |

---

## Conventions

- **Engine purity**: `engine_c/` has no I/O or side effects. The C engine is a pure library by construction.
- **Pydantic models**: Python domain types use Pydantic v2 `BaseModel` (`game_setup/types.py`).
- **Pure-function transitions**: `engine_c` `apply(state, move) → state'` — no mutation.
- **Tests**: `pytest -q` (or `just test`).
- **Lint**: `ruff check .` (line-length 120, py312 target).
