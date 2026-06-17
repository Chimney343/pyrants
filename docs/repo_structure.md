# pyrants — Repository Structure & Purpose

**pyrants** is a turn-based board game engine for *Tyrants of the Underdark*, implemented in Python 3.12+ with Pydantic-typed state and pure-function state transitions. The engine is headless (no I/O in `engine/`), supports 2–4 players, and provides an OpenSpiel wrapper for game-theoretic analysis via IS-MCTS.

---

## Top-Level Layout

```
pyrants/
├── engine/                 # Pure game logic (no I/O, no side effects)
├── engine/generic_runtime/  # Data-driven card-effect interpreter
├── openspiel_pyrants/      # OpenSpiel (pyspiel) wrapper
├── game_setup/             # Board/card/scenario loaders, state generator
├── interface/              # Terminal UI: viewer, replay, board creator
├── scripts/                # CLI utilities, IS-MCTS runner, benchmarks
├── data/                   # JSON/TOML content: boards, cards, decks, scenarios
├── tests/                  # pytest suite (36 files)
├── artifacts/               # Run outputs (gitignored)
├── docs/                   # Game manual, status docs
├── assets/                 # Board/map images
├── game_session.py          # Session controller (state + move log)
├── game_simulation.py       # Headless simulation runner
├── game_view.py             # Structured game-state projection (no I/O)
├── justfile                 # Task runner commands
└── pyproject.toml          # Project config, deps, lint settings
```

---

## Core Engine (`engine/`)

The engine is the heart of the project. It is strictly **pure** — no I/O, no side effects, enforced by `tests/test_engine_purity.py`. All state transitions are pure functions.

| File | Purpose |
|------|---------|
| `state.py` | Domain models: `GameState`, `TurnPhase`, `NodeKind`, board/player/card definitions, `build_initial_game_state()`, and a fast COW-style `_cow_clone()` via Pydantic deep-copy |
| `moves.py` | Pydantic move payload types: `PlayCardMove`, `DeployMove`, `AssassinateMove`, `RecruitMove`, `ReturnSpyMove`, `EndMainPhaseMove`, `ResolveEndOfTurnMove`, `ResolveCleanupMove`, `PromoteCardMove`, `SkipPromoteMove`, `ActivateCardAbilityMove`, `DeclineCardAbilityMove`, `ResolveGenericChoiceMove`, `InitialPlacementMove` |
| `rules.py` | Pure state-transition functions: `apply(state, move) → state`, `legal_moves(state) → list[Move]`, `is_terminal(state) → bool`, `winner(state) → str | None` |
| `phases.py` | Turn-phase state machine: `advance_phase()`, `next_player_id()` |
| `scoring.py` | End-of-turn and final scoring: node control VP, trophy hall, inner circle, site bonuses |
| `player_view.py` | Information projection: `public_view(state) → PublicView` (shared), `private_view(state, player_id) → PrivateView` (per-player). Frozen Pydantic models used as IS-MCTS information-state keys |
| `helpers.py` | Shared helpers: effect registry (`_EFFECT_REGISTRY`), board queries, deploy/assassinate/recruit logic, free-action application |
| `errors.py` | Typed exceptions: `RuleViolationError`, `IllegalMoveError`, `MissingRuleImplementationError`, `UnknownCardEffectError` |

### Generic Card-Effect Runtime (`engine/generic_runtime/`)

Data-driven interpreter for structured card actions. Avoids hardcoding each card's effect; instead, cards declare actions via JSON schemas that this runtime resolves.

| File | Purpose |
|------|---------|
| `__init__.py` | Public re-exports: `_apply_resolve_generic_choice`, `_legal_pending_generic_choice_moves`, `_resolve_generic_execution`, `_action_requires_selection` |
| `_resolve.py` | Core generic-choice resolution loop: processes `PendingGenericChoiceState`, dispatches actions, handles modal/repeat execution |
| `_actions.py` | Action applier functions for each card-action op (deploy, assassinate, draw, recruit, gain resources, etc.) |
| `_selection.py` | Selection resolver: maps focus/target specifications to concrete game entities |
| `_custom_effects.py` | Custom/special effect handlers that don't fit the generic pattern |
| `_promotion_helpers.py` | Promotion-phase helpers: promote-from-deck, promote-from-discard, aspect filtering |
| `_utils.py` | Shared utilities: action counter keys, focus checks, node validation |

---

## OpenSpiel Wrapper (`openspiel_pyrants/`)

This package wraps the pyrants engine as a **DeepMind OpenSpiel** game, enabling IS-MCTS and other game-theoretic algorithms to run against it. Registered as `python_pyrants` inside OpenSpiel.

### Architecture

The wrapper follows the standard `pyspiel.Game` / `pyspiel.State` contract:

```
pyspiel.load_game("python_pyrants")
     │
     ▼
PyrantsGame (pyspiel.Game)
     │  new_initial_state()
     ▼
PyrantsState (pyspiel.State)
     │  ._engine  ──►  engine.state.GameState (the true game state)
     │  ._pending_initial_chance  (True before seed is chosen)
     │  ._cached_indexed_moves     (per-state Move ↔ int mapping)
     │
     │  resample_from_infostate()  ──►  determinization for IS-MCTS
     │  information_state_string() ──►  JSON of PrivateView + history
     │  chance_outcomes()          ──►  uniform distribution over seeds
     │  returns()                  ──►  zero-sum payoff [Δscore, −Δscore]
     ▼
PyrantsObserver  ──►  string_from(state, player) → PrivateView JSON
```

### Key Design Decisions

**Chance node for shuffling.** Game initialization is modeled as a single CHANCE node that selects a shuffle seed (0..999 by default, configurable via `shuffle_seed_count`). A Knuth multiplicative hash (`_public_to_seed`) maps public action IDs to internal seeds, preventing trivial seed recovery from the action history.

**Imperfect information.** The game is declared `IMPERFECT_INFORMATION` because players have private hands, decks, and discard piles. The `information_state_string(player)` produces a JSON serialization of `PrivateView` (public board + observing player's private zones), optionally prefixed with the action history (`||` separator). This string serves as the information-state key in IS-MCTS.

**Per-state action encoding.** Legal moves are re-indexed 0..N−1 each turn using `compute_action_map()`, sorted deterministically by Pydantic model dump. The global upper bound is `NUM_DISTINCT_ACTIONS = 1024` (reserved for OpenSpiel's fixed-size API). See `action_encoding.py` for the bound calculation.

**Determinization (resample).** `resample_from_infostate()` implements "perfect determinization" — it preserves the observing player's private zones exactly while reshuffling the opponent's hand+deck+discard from the same card multiset. Public zones (devour pile, board, market) are untouched. This powers IS-MCTS world sampling.

**Zero-sum utility.** `returns()` computes `[p0_score − p1_score, p1_score − p0_score]`, satisfying OpenSpiel's zero-sum contract (`utility_sum = 0`).

### Module Details

| File | Purpose |
|------|---------|
| `__init__.py` | Registers `python_pyrants` with `pyspiel.register_game()` so that `pyspiel.load_game("python_pyrants")` works |
| `game.py` | `PyrantsGame(pyspiel.Game)` — declares `GameType` (sequential, explicit-stochastic, imperfect-info, zero-sum, terminal reward), `GameInfo` (1024 actions, 2 players, utility ∈ [−200, 200]), and constructs the `GameDefinition` from JSON data files. Supports runtime params for custom board/card/setup paths and `setup_data_json` for IS-MCTS deck pairing |
| `state.py` | `PyrantsState(pyspiel.State)` — the core adapter. Holds `._engine: GameState | None` (None before chance node resolves). Implements `current_player()`, `_legal_actions()`, `_apply_action()`, `is_terminal()`, `returns()`, `chance_outcomes()`, `information_state_string()`, `observation_string()`, and `resample_from_infostate()` |
| `action_encoding.py` | Bidirectional Move ↔ int mapping. `compute_action_map(state)` builds sorted `(index, Move)` list. `NUM_DISTINCT_ACTIONS = 1024` is the fixed upper bound |
| `determinization.py` | `determinize_opponent_hidden_zones(engine, player_id, rng) → GameState` — creates a COW copy, collects opponent's hand+deck+discard into a flat list, Fisher-Yates shuffles it, and redistributes. Adapts to both `numpy.random.RandomState` and `pyspiel.UniformProbabilitySampler` |
| `observer.py` | `PyrantsObserver` — implements `string_from(state, player)` by calling `private_view(state._engine, player_id)` and serializing to JSON. Used by `make_py_observer()` |

### Tests (`openspiel_pyrants/tests/`)

| File | Coverage |
|------|---------|
| `test_pyrants_register.py` | Game loads via `pyspiel.load_game("python_pyrants")`; validates GameType fields, direct construction, chance node at init |
| `test_random_sim.py` | 100-iteration random-play loop asserting legal actions, sorted IDs, terminal returns sum to zero, utility bounds; chance-outcome uniformity; seed determinism |
| `test_action_encoding.py` | Round-trip: enumerate → action_to_move → move_to_action_id; sorted IDs from 0; seed hashing bijection |
| `test_information_state.py` | Info-state strings differ per player, stable across clone, deterministic for same seed, diverge after different actions, include history (`\|\|` marker), observation string matches info state |
| `test_resample.py` | Determinization contract: public view preserved, observing player's hand/deck/discard unchanged, opponent multiset preserved, zone sizes preserved, random across seeds, legal actions preserved, resampled state is playable |
| `test_ismcts_smoke.py` | Runs IS-MCTS bot (5 sims/move) to completion; validates policy sums to 1.0, chosen action is legal; also runs the `scripts/run_ismcts.py` CLI and checks artifact outputs (CSV, Markdown, decisions.jsonl, replay.json, summary.json). Skippable via `PYRANTS_SKIP_ISMCTS=1` |
| `test_api_test.py` | `pyspiel.random_sim_test(game, num_sims=5)` — OpenSpiel's built-in API consistency check |

---

## Supporting Packages

### Game Setup (`game_setup/`)

| File | Purpose |
|------|---------|
| `loaders.py` | `build_game_definition_from_files()`, `build_game_definition_from_dicts()`, `create_game_state_from_files()`, `default_catalog_registry()` — JSON loading + validation |
| `board_package.py` | Board definitions + layouts, `BoardPackageDefinition`, `BoardLayoutDefinition` |
| `market_setup.py` | Market deck construction, `combine_two_deck_market_setup()`, `discover_full_deck_profiles()`, `pick_random_pair()` — used by IS-MCTS to randomize deck pairings |
| `scenarios.py` | Scenario loading from `data/scenarios/` |
| `state_generator.py` | Random state generation for testing |
| `random_state_search.py` | Search for specific game states by criteria |
| `scenario_generation/` | Card scenario discovery and injection scripts |

### Interface (`interface/`)

Terminal UI built on `curses`/`rich`:

| File | Purpose |
|------|---------|
| `game_viewer.py` | Interactive terminal game viewer (main play interface) |
| `replay_viewer.py` | Step-through saved replay logs |
| `board_creator.py` | Interactive board designer |
| `board_renderer.py` | Board drawing logic |
| `shared_board_renderer.py` | Shared rendering utilities |
| `cli.py` | Argument parser for viewer/replay/board-creator CLIs |
| `parser.py` | Input parsing for game commands |

### Scripts (`scripts/`)

| File | Purpose |
|------|---------|
| `run_ismcts.py` | IS-MCTS runner: parallel game execution, per-game decision traces, cross-run summary CSV/Markdown, metrics. Entry point for `just ismcts` |
| `random_walk.py` | Random walk simulation |
| `bench_simulation.py` | Performance benchmark |
| `catalog_audit.py` | Card catalog consistency checker |
| `check_roster_card_stuck_states.py` | Detect card stuck states |
| `generate_card_scenarios.py` | Generate scenario data |
| `generate_first_deck_artifacts.py` | Generate initial deck artifacts |
| `_obs.py` | Structured logging, metrics, run-ID helpers for IS-MCTS |

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
| `just game-viewer` | `interface/game_viewer.py` | Interactive terminal play |
| `just game-simulate` | `game_simulation.py` | Headless random/policy simulation |
| `just replay-viewer` | `interface/replay_viewer.py` | Replay saved games |
| `just board-creator` | `interface/board_creator.py` | Design boards |
| `just ismcts` | `scripts/run_ismcts.py` | IS-MCTS bot tournament |
| `just openspiel-test` | `pytest openspiel_pyrants/tests/` | OpenSpiel wrapper tests |
| `just openspiel-smoke` | — | Quick registration check |

---

## Conventions

- **Engine purity**: `engine/` has no I/O or side effects. Enforced by `tests/test_engine_purity.py`.
- **Pydantic models**: All domain types use Pydantic v2 `BaseModel`.
- **Pure-function transitions**: `engine.rules.apply(state, move) → state'` — no mutation.
- **Tests**: `pytest -q` (or `just test`).
- **Lint**: `ruff check .` (line-length 120, py312 target).

---

## OpenSpiel Integration Flow

```
                     ┌──────────────────────────────────┐
                     │  pyspiel.load_game("python_pyrants")  │
                     └──────────────┬───────────────────────┘
                                    │
                     ┌──────────────▼───────────────────────┐
                     │  PyrantsGame.__init__()               │
                     │  • loads board/card/setup JSON         │
                     │  • builds GameDefinition               │
                     │  • stores player_ids, shuffle_seed_count │
                     └──────────────┬───────────────────────┘
                                    │ new_initial_state()
                     ┌──────────────▼───────────────────────┐
                     │  PyrantsState(chance node pending)    │
                     │  • _engine is None                    │
                     │  • current_player() = CHANCE           │
                     │  • chance_outcomes() = [0..999]       │
                     └──────────────┬───────────────────────┘
                                    │ apply_action(seed_id)
                                    │  → _public_to_seed(seed_id)
                                    │  → build_initial_game_state(...)
                     ┌──────────────▼───────────────────────┐
                     │  PyrantsState(ready)                   │
                     │  • _engine = GameState                 │
                     │  • current_player() = 0 or 1          │
                     │  • legal_actions() via action_encoding │
                     │  • information_state_string()          │
                     │      = PrivateView JSON + "||" + history │
                     │  • resample_from_infostate()           │
                     │      = determinize opponent hidden zones │
                     └──────────────┬───────────────────────┘
                                    │ per action:
                                    │  compute_action_map(state)
                                    │  → sorted Move list
                                    │  apply_action(int) → engine.rules.apply()
                     ┌──────────────▼───────────────────────┐
                     │  PyrantsState(terminal)                │
                     │  • is_terminal() = True                │
                     │  • returns() = [Δscore, −Δscore]      │
                     └────────────────────────────────────────┘
```

### IS-MCTS Pipeline

```
scripts/run_ismcts.py
     │
     │  pyspiel.load_game("python_pyrants", {setup_data_json: ...})
     │  ISMCTSBot(game, evaluator, uct_c, max_simulations, ...)
     │  state = game.new_initial_state()
     │  state.apply_action(shuffle_seed)
     │
     │  while not terminal:
     │      bot.step_with_policy(state)
     │        → state.information_state_string(p)  [PrivateView JSON]
     │        → state.legal_actions()                [0..N-1 ints]
     │        → state.resample_from_infostate(p, rng) [determinize]
     │        → ... MCTS search ...
     │      state.apply_action(chosen)
     │
     │  Outputs: decisions.jsonl, replay.json, summary.json, summary.csv, summary.md
     └── metrics.json
```