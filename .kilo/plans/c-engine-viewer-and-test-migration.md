# Plan: Rewire `just game-viewer` to the C engine + migrate Python tests to C

## Goal

The `interface/game_viewer.py` Tkinter hotseat viewer currently drives the Python
`engine/` stack via `game_session.GameSession` and `game_view.build_game_view`.
We want to keep the same GUI but back it with the C engine in `engine_c/`. From
now on, new viewer work happens in C (and its thin Python shim). Separately,
the existing Python pytest suite under `tests/` is to be ported to C. The
Python engine stays in the tree — it is not removed by this plan.

## Constraints / facts that shape the plan

- `engine_c/` already exposes a full engine via `engine.h`:
  `engine_create_game_definition`, `engine_legal_moves`, `engine_apply`,
  `engine_is_terminal`, `engine_winner`, `engine_public_view`,
  `engine_private_view`, plus `engine_load_definition`.
- A Python shim already exists: `engine_c/bindings/{ce_api.py, session.py,
  c_adapter.py, engine_bindings.py}`. `CSession` mirrors `GameSession`. There
  is *no* `CGameView` shim — that is the missing piece for the viewer.
- The Python engine (`engine/`, `game_session.py`, `game_view.py`,
  `game_setup/`, etc.) is **kept intact** throughout this plan. It is
  still used by the simulation, IS-MCTS, OpenSpiel wrapper, scripts,
  the board creator, and the tests that haven't been migrated yet.
  Nothing in this plan deletes or rewrites Python engine code.
- The C `GameState` struct already contains everything `build_game_view` reads
  (hand, played, discard, inner_circle, trophy_hall, barracks, spies_available,
  vp_tokens, score, market row/deck/discard, devour_pile, per-node
  troop_slots/spies/vp_tokens, current_player_id, round_number, phase,
  resource_pool). It does **not** contain node *layout* (x/y, label) or card
  catalog metadata (name, cost, aspect, rules_text, etc.) — both of those
  must come from `GameDefinition` (loaded once) and the layout JSON.
- Scenario save/load is currently Python-only
  (`game_setup/scenarios.save_game_state` and `load_game_state_from_scenario`).
  The Python viewer also round-trips through it. Per user decision: add C-side
  save/load instead of hybridising.
- The C engine has no `Move` Python objects — moves come back as
  `CMoveWrapper` and legal move labels would need a C-side `describe_move`.
- Tkinter UI bits that don't need engine state (file dialogs, layout
  selection, deck selection) can stay in Python.
- Existing C test executables: `engine_c/test_engine.c`, `test_game.c`,
  `test_generic.c`. Empty `engine_c/tests/` directory.
- Python test suite: 36 files, ~500KB total. Several are UI/CLI tests that
  cannot be expressed against a pure C engine and will stay in Python (or be
  moved to manual smoke tests) — per user decision we'll port everything that
  can be ported.

## Target architecture

```
interface/game_viewer.py (Tkinter, mostly unchanged structure)
    │
    │  talks to a thin Protocol that the GUI does not care about
    ▼
engine_c/bindings/session.py   CSession  (already exists)
engine_c/bindings/view.py     CGameView  (NEW — wraps engine_c/view.c output)
    │
    ▼
engine_c/engine_c.dll
   ├─ engine.c / rules.c / moves.c        (existing)
   ├─ player_view.c                       (existing — public/private views)
   ├─ view.c / view.h                     (NEW — GameView projection)
   ├─ saveload.c / saveload.h             (NEW — scenario JSON in/out)
   └─ describe.c / describe.h             (NEW — move labels, prompts)
```

`game_viewer.py` gains a `--engine {python,c}` flag (default `c` going
forward, env var `PYRANTS_ENGINE=c` to match the existing convention in
`ce_api.py`) that selects whether `GameSession`/`build_game_view` (Python) or
`CSession`/`CGameView` (C) is used. UI internals (hitboxes, scrolling, card
drawing, save dialog) do not change.

## Phase 1 — C view layer (blocks Phase 2)

### 1.1 `engine_c/view.h` / `engine_c/view.c` (NEW)

Add a C API that projects `GameState` into a flat struct mirroring
`game_view.GameView`:

```c
// view.h (sketch)
typedef struct {
    int  hand[MAX_ZONE_SIZE];          // indexes into card catalog
    int  hand_count;
    int  discard[MAX_ZONE_SIZE];
    int  discard_count;
    int  played[MAX_ZONE_SIZE];
    int  played_count;
    int  inner_circle[MAX_ZONE_SIZE];
    int  inner_circle_count;
    int  trophy_hall_owner[MAX_ZONE_SIZE]; // Sym; 0 = white, else player_id
    int  trophy_hall_count;
    int  barracks;
    int  spies_available;
    int  vp_tokens;
    int  score;
} CPlayerZoneView;

typedef struct {
    int  node_index;                   // index into GameDefinition.board.nodes
    int  kind;                         // 0 site, 1 route
    int  adjacent_to[MAX_NODES];
    int  adjacent_count;
    int  control_vp;
    int  total_control_vp_per_turn;
    int  troop_owner_slot[MAX_TROOP_SLOTS]; // Sym; 0 = empty, else player/white
    int  spy_owner[MAX_SPY_SLOTS];     // Sym
    int  vp_tokens;
} CNodeOccupancyView;

typedef struct {
    int  controlled_sites;             // for current_player_id
    int  total_control_sites;
} CPlayerSiteControl;

typedef struct {
    int                 round_number;
    int                 phase;
    int                 current_player_index;
    CPlayerZoneView     players[MAX_PLAYERS];
    int                 player_count;
    int                 market_row[MAX_ZONE_SIZE];
    int                 market_row_count;
    int                 market_deck_count;
    int                 market_discard_count;
    int                 resource_power;
    int                 resource_influence;
    int                 devour_pile[MAX_ZONE_SIZE];
    int                 devour_pile_count;
    CNodeOccupancyView  nodes[MAX_NODES];
    int                 node_count;
    CPlayerSiteControl  site_control;
} CGameView;
```

Implementation lives in `view.c` and reads directly from the existing
`GameState` / `NodeState` / `PlayerState` / `MarketState` structs in
`state.h`. ~300–400 lines. Re-uses the same `intern_str` to give back Syms
that the Python shim decodes to `str` via the existing `_lib.intern_str`
binding (do not change Sym encoding).

### 1.2 `engine_c/describe.c` / `engine_c/describe.h` (NEW)

Port `game_view.describe_move` (~80 lines) plus the few helpers it needs
(`_card_name`, `_node_display_name`, generic option summary, devour /
assassinate / return_unit / place_spy labels). Public surface:

```c
// Returns required buffer size; writes into out (NUL-terminated).
int engine_describe_move(const GameState *state, const Move *move,
                         const char *const *node_names, int node_name_count,
                         char *out, int out_cap);
```

`node_names` is a `Sym -> const char *` lookup table populated from the
layout JSON the viewer already loads. Implement as a small arena-backed hash
or linear scan (max ~20 nodes — linear is fine).

### 1.3 `engine_c/saveload.c` / `engine_c/saveload.h` (NEW)

Mirror the JSON shape `game_setup.scenarios.save_game_state` produces. Two
functions:

```c
// Serialise state + definition paths + metadata to JSON.
int engine_serialize_state(const GameState *state,
                           const char *catalog_path,
                           const char *board_path,
                           const char *setup_path,
                           int move_count, bool is_terminal,
                           char *out_json, int out_cap);

// Parse JSON scenario, create a fresh state, apply move_count moves.
GameState *engine_deserialize_state(const char *json,
                                    const char *catalog_path_override,
                                    Arena *arena,
                                    int *out_move_count);
```

JSON layout follows the existing `data/scenarios/*.json` shape: top-level
`{"scenario_id", "description", "tags", "move_count", "is_terminal",
"definition": {"catalog_path", "board_path", "setup_path"}, "state": {...}}`.
Re-use the bundled `cJSON.c` (already linked). Use existing
`engine_create_game_definition` to seed the state, then replay the move log
(via `engine_legal_moves` + `engine_apply`).

### 1.4 `engine_c/bindings/view.py` (NEW)

Thin Python wrapper that:
- Calls a new `_lib.engine_build_view(state.ptr, view_ptr)` exported from
  `view.c`.
- Decodes all `Sym` ints back to Python `str` via existing `_lib.intern_str`.
- Reads card catalog metadata from a `CardCatalog` table the binding loads
  once (small Python-side cache from `data/cards/catalog.json`) and
  constructs `CardView` / `PlayerSummaryView` / `NodeOccupancyView` /
  `LegalMoveView` / `GameView` dataclasses.
- Exposes `build_c_game_view(session, *, node_names=None) -> GameView` that
  mirrors `game_view.build_game_view`'s signature.

Catalog metadata can be loaded via the existing `game_setup.card_catalog`
Pydantic models (kept purely as a *data loader*; not engine code) so card
names/aspects/rules stay in sync with the canonical JSON.

### 1.5 `engine_c/bindings/engine_bindings.py` (NEW function exports)

Add the new C functions to the ctypes binding (function signatures,
argtypes, restype) and bump the build (already covered by
`engine_c/Makefile` / `compile.bat`).

## Phase 2 — Rewire `interface/game_viewer.py`

### 2.1 New session/view abstraction

Add a tiny module `interface/_session_protocol.py` (NEW) defining a
`SessionLike` Protocol with the methods the viewer actually uses:
`state`, `move_count`, `is_terminal()`, `legal_moves()`, `apply()`, plus
`save(path)`, `load(path)`. Both `GameSession` and `CSession` already
satisfy the engine half; the save/load half needs a thin adapter
(`CSession` gains `save()` / `load()` classmethods in `session.py` that
delegate to `engine_serialize_state` / `engine_deserialize_state`).

### 2.2 `interface/game_viewer.py` changes (MINIMAL)

- Replace `from game_session import GameSession` with a factory that
  selects the backend based on `--engine` / `PYRANTS_ENGINE`.
- Replace `from game_view import build_game_view, …` with a dispatcher:
  ```python
  def build_view(session, *, node_names=None):
      if ENGINE == "c":
          return build_c_game_view(session, node_names=node_names)
      return build_game_view_py(session, node_names=node_names)
  ```
- `create_hotseat_session` and `_load_game` get a `c_engine` branch
  building a `CSession` instead of a `GameSession`. The
  `_derive_market_deck_metadata` and `_rebuild_package_for_loaded_state`
  helpers stay — they consume `state.definition` which the C side
  exposes via the CState struct (read through the bindings; need to add
  `CState.definition` accessor that returns a small Python wrapper).
- All `_refresh_view` / `_apply_selected_legal_move` etc. stay unchanged
  because they operate on the `GameView` dataclass which is now produced
  by either backend.
- Card hover, hitboxes, scrolling, save dialog, layout discovery, deck
  discovery: **zero changes**.

### 2.3 `justfile`

- `game-viewer` recipe unchanged from the user's perspective but the
  underlying command gains a default `--engine c` flag.
- Add `game-viewer-py` to keep the old Python backend reachable during
  the transition.
- `build-c` now also compiles the new `view.c`, `describe.c`, `saveload.c`.
- `test-c` runs the new C test binaries (see Phase 3).

### 2.4 Parity verification (gating step)

- Add a parity test (in `tests/test_engine_c.py` and a new
  `engine_c/test_view.c`) that:
  1. Loads the same `data/boards/tyrants_of_the_underdark.json` /
     `data/cards/catalog.json` / `data/decks/base_setup.json`.
  2. Replays the first N moves of every scenario under
     `data/scenarios/canonical/` in both engines.
  3. Asserts `build_game_view` (Python) and `build_c_game_view` (C)
     produce byte-identical `GameView` payloads (or at least, identical
     card_id / player_id / count fields; names/aspects come from the
     catalog, identical by construction).
- The viewer's existing `tests/test_game_viewer_setup.py` is updated to
  run against both backends via `pytest.mark.parametrize("engine",
  ["python", "c"])`.

## Phase 3 — Migrate Python tests to C

Per user decision: "Everything possible." We translate the 36 pytest files
under `tests/` into a mix of C test binaries (for engine-touching tests) and
kept-as-Python tests (for things that intrinsically need Python or the
filesystem/UI).

### 3.1 New C test executables under `engine_c/`

Move all flat C test files (`test_engine.c`, `test_game.c`, `test_generic.c`)
into `engine_c/tests/` and follow the convention. Add new files. **Each
Python test file stays in place** (no deletions); the C file is an
additional, parallel implementation. A small shim layer (see 3.5) is the
only Python change in this phase, and only if the user opts in.

| New C file | Mirrors Python test(s) |
|---|---|
| `tests/test_state_machine.c` | `test_state_machine.py`, `test_setup.py` |
| `tests/test_rules_basics.c` | `test_rules_basics.py` |
| `tests/test_rules_focus.c` | `test_rules_focus.py` |
| `tests/test_rules_ability.c` | `test_rules_ability.py` |
| `tests/test_rules_promotion.c` | `test_rules_promotion.py` |
| `tests/test_rules_cards_a_m.c` | `test_rules_cards_a_m.py` |
| `tests/test_rules_cards_n_z.c` | `test_rules_cards_n_z.py` |
| `tests/test_initial_placement.c` | `test_initial_placement.py` |
| `tests/test_scoring.c` | `test_scoring.py` |
| `tests/test_shuffle_determinism.c` | `test_shuffle_determinism.py` |
| `tests/test_scenarios.c` | `test_scenarios.py`, `test_scenario_helpers.py` (engine portions) |
| `tests/test_player_view.c` | `test_player_view.py` |
| `tests/test_view.c` | (new — covers Phase 1 view API) |
| `tests/test_saveload.c` | (new — covers Phase 1 saveload API) |
| `tests/test_generic_interpreter.c` | `test_generic_interpreter.py` (extend the existing skeleton) |
| `tests/test_first_ten_cards.c` | `test_first_ten_cards.py` |
| `tests/test_card_scenario_market_policy.c` | `test_card_scenario_market_policy.py` |
| `tests/test_state_generator.c` | `test_state_generator.py` |
| `tests/test_check_roster_card_stuck_states.c` | `test_check_roster_card_stuck_states.py` (logic) |
| `tests/test_game_session.c` | `test_game_session.py` (CSession via bindings) |
| `tests/test_game_simulation.c` | `test_game_simulation.py` (CSimulation via bindings) |
| `tests/test_market_setup.c` | `test_market_setup.py` (logic, since it's setup JSON) |
| `tests/test_deck_rosters.c` | `test_deck_rosters.py` |
| `tests/test_card_model.c` | `test_card_model.py` (Pydantic model; parallel C JSON validator — kept) |
| `tests/test_board_package.c` | `test_board_package.py` (kept in Python — board_package is a Tkinter authoring concern) |
| `tests/test_board_renderer.c` / `test_game_renderer.c` / `test_shared_board_renderer.c` / `test_board_view.c` / `test_view_fit.c` | kept in Python (pure rendering helpers) |
| `tests/test_cli.c` | `test_cli.py` (kept in Python — CLI argument parsing) |
| `tests/test_engine_purity.c` | kept in Python (asserts no I/O in `engine/` package) |
| `tests/test_engine_c.py` | kept and extended; orchestrator that runs all C test executables and asserts Python↔C parity on a fixed scenario set |
| `tests/test_game_viewer_setup.py` | kept; updated to parametrize over `engine ∈ {python, c}` and assert view bytes match |
| `tests/test_board_creator_collaborators.py` | kept; board creator is Python/Tkinter |
| `tests/test_effect_families_schema.py` | kept; JSON schema validation |

The empty `engine_c/tests/` directory becomes the canonical C test home.
The `Makefile` / `compile.bat` is updated to glob `engine_c/tests/test_*.c`,
compile each into its own executable, and produce a `run_all_tests.bat` /
`run_all_tests.sh` that runs them all and aggregates exit codes.

### 3.2 Test conversion strategy

For each Python test file, the C counterpart is a *parallel*
implementation. The original Python file is not removed. A small
`engine_c/tests/_test_util.h` helper provides:

- `void assert_state_loaded(GameState *s, const char *scenario_id)`
- `int assert_moves_contain(const GameState *s, const char *type, ...)`
- `void assert_player_zone(const GameState *s, int pid, ...)`
- `void assert_node_state(const GameState *s, int node_idx, ...)`
- `int assert_sym_eq(Sym got, const char *expected)`

Conversion rules for each test:
1. The fixture-style setup becomes direct calls to
   `engine_create_game_definition` with the same player IDs and seed.
2. `assert legal_moves(state) == expected` becomes
   `assert_moves_contain(state, "...")`.
3. Pydantic-specific assertions (e.g. `move.model_dump()`) become raw
   struct field reads.
4. Scenario-driven tests use the same JSON files under `data/scenarios/`,
   loaded by `engine_deserialize_state` (Phase 1.3) so no Python scenario
   loader is needed in C.
5. `pytest.mark.parametrize` becomes a `for` loop over an array of
   `{name, args}` entries in the C test.

### 3.5 Optional shim layer (user opt-in, per file)

For each migrated test, the user may choose one of:
- **(a)** Leave `tests/test_foo.py` exactly as is. The new
  `engine_c/tests/test_foo.c` is a parallel implementation with no
  pytest entry point. Run via `just test-c` and `engine_c/run_all_tests`.
- **(b)** Convert `tests/test_foo.py` into a thin pytest shim that
  `subprocess.run([executable])`s the C binary and asserts exit 0.
  This keeps `just test` reporting coverage of the same scenarios.

The default is (a) — leaving the Python test files untouched.

### 3.3 Engine parity harness (gating)

`tests/test_engine_c.py` is retained and extended:
- Run a fixed corpus of scenarios (e.g. 25 hand-picked scenarios from
  `data/scenarios/canonical/`) through both engines, replay all moves,
  and assert that public + private view JSON are byte-identical.
- This stays Python because the C engine's `engine_private_view` /
  `engine_public_view` produce the same JSON shape already consumed by
  the C adapter.

### 3.4 What stays in Python

The Python engine and its test surface remain first-class throughout this
plan. After Phase 3 completes:

- `engine/`, `game_session.py`, `game_view.py`, `game_setup/`,
  `game_simulation.py`, `scripts/*`, `openspiel_pyrants/` all stay.
- `tests/test_*.py` files that have a C counterpart remain in the
  tree unchanged by default. If the user opts in (see 3.5), a given
  file may be converted to a thin pytest shim that re-exports or
  invokes the C test executable, so that the existing `just test`
  pytest entry point continues to drive the full suite without
  breakage.
- `just test` keeps running `pytest -q`; the C binaries are
  additionally runnable via `just test-c` (existing recipe).
- No removals of Python engine code, no removals of Python test
  files, no breaking of the simulation / IS-MCTS / OpenSpiel / board
  creator / scripts entry points. Future removal of the Python
  engine is a separate plan, out of scope here.

## Order of work

1. **Phase 1.1** — `engine_c/view.{h,c}` + bind in `engine_bindings.py`
   + add `engine_c/bindings/view.py` (does not touch the viewer yet).
2. **Phase 1.2** — `engine_c/describe.{h,c}` so moves can be labelled
   from the C side.
3. **Phase 1.3** — `engine_c/saveload.{h,c}`.
4. **Phase 2.1–2.3** — Wire the viewer to the C backend behind
   `--engine c`. Add `tests/test_game_viewer_setup.py` parametrization.
5. **Phase 2.4** — Parity test (gating: viewer must be pixel-equivalent
   on a fixed scenario set before any further migration).
6. **Phase 3.1–3.2** — Add C counterparts under `engine_c/tests/` for
   each Python test file. The Python test files stay in place by
   default; the user may optionally convert any of them to a thin
   pytest shim (see 3.5).
7. **Phase 3.3** — Final parity harness added to `tests/test_engine_c.py`
   (already exists, extended). The Python engine and the rest of the
   Python test surface stay as they are.

## Open questions for the user

None — all three trade-off questions were answered (save/load = C native,
test scope = everything possible, view layer = `engine_c/view.c` + Python
shim). The Python engine and Python tests are preserved; nothing in this
plan removes existing Python engine code. Implementation can begin on
Phase 1.1 once the plan is approved.
