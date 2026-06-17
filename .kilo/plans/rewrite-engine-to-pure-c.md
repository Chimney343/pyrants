# Plan: Rewrite Engine to Pure C

## Overview

Rewrite the `engine/` Python package (~6,500 lines across 13 files) as a pure C library. The engine is a headless, pure-function game state machine with no I/O — an ideal candidate for C. The rewrite preserves the exact same public API semantics (`apply`, `legal_moves`, `is_terminal`, `winner`) while eliminating Python/Pydantic overhead.

---

## Key Challenges & Decisions

### 1. No Pydantic — Manual Struct Definitions
Every Pydantic model must become a C struct. Pydantic's frozen models and validators need manual enforcement. The `clone_fast`/`_cow_clone` copy-on-write pattern must be reimplemented with explicit reference counting or arena allocation.

**Approach:** Arena-based allocation. Each `GameState` owns an arena. `clone_fast` creates a new arena and deep-copies into it. COW is done with simple dirty-bit flags on sub-structs (matching current `_cow_dirty` set).

### 2. Dynamic Collections → Fixed-Size Arrays
Python uses `list[str]`, `dict[str, T]`, `set[str]`. C has no built-in hash maps or dynamic arrays.

**Approach:**
- **String interning:** All card IDs, node IDs, and player IDs are interned at game-setup time. The interning table maps `const char*` → `uint32_t` index. All collections use `uint32_t` IDs internally.
- **Board nodes:** Stored as a flat `NodeState[]` indexed by interned node ID. Node lookup is O(1) via index.
- **Player zones (hand, deck, etc.):** Fixed-size circular buffers with `head`/`count` offsets. Max capacity is a game constant (e.g., 60 cards per zone).
- **Troop slots:** Fixed `const char*[]` (interned player IDs or NULL).
- **Spies:** Fixed `uint32_t[]` (interned player IDs) with a count; max players = 4.
- **Card catalog / board definition:** Interned at setup, stored as flat arrays with `uint32_t` lookups.
- **Pending promotions:** Fixed max (e.g., 8) inline array.

### 3. JSON Data Loading
Currently Pydantic validates JSON directly. In C, we need a JSON parser.

**Approach:** Use [cJSON](https://github.com/DaveGamble/cJSON) (single-file, MIT, ~3K lines) as a vendored dependency. Write a `loader.c` that parses JSON into `CardCatalog`, `BoardDefinition`, `GameDefinition` structs. Validation occurs during loading. Single-file vendoring keeps the engine self-contained.

### 4. Deterministic Shuffle
Currently uses `random.Random` with seed + counter. C needs a deterministic PRNG.

**Approach:** Use a simple xoshiro256** or PCG RNG seeded identically to Python. The shuffle is Fisher-Yates. We match Python's `Random.shuffle` output by using the same algorithm if needed, or accept a one-time cross-validation suite that proves behavioral equivalence.

### 5. Effect Registry Pattern
Python uses `@register_effect("key")` decorators to build `_EFFECT_REGISTRY`. C uses a function-pointer dispatch table.

**Approach:** `typedef GameState* (*EffectFn)(GameState*, const char* player_id, const CardDefinition*);` with a `static EffectFn effect_registry[EFFECT_COUNT]` indexed by interned effect key.

### 6. Generic Runtime / Card Interpreter
The `generic_runtime/` module is a data-driven card interpreter (~2,100 lines). This is the most complex part.

**Approach:** Translate directly. `CardAction`, `CardOption`, `ExecutionModel` become flat C structs. The `PendingGenericChoiceState` interpreter loop maps to a C switch/state-machine. The `_GENERIC_ACTION_APPLIERS` dispatch dict becomes a `switch` on interned `action.op` string IDs.

### 7. Testing Strategy
Existing pytest suite must still pass. Two options:

**Recommended: C library with Python bindings via ctypes/cffi.** This lets us:
- Keep all existing tests unchanged
- Replace `engine.state` / `engine.rules` internals with C calls
- Validate behavioral equivalence incrementally (module by module)
- The Python layer becomes a thin FFI wrapper

**Alternative: Pure C with its own test harness.** Loses the existing test investment.

---

## Architecture

### Directory Layout

```
engine_c/
├── Makefile
├── cJSON.c              # vendored JSON parser
├── cJSON.h
├── engine.h             # public API header
├── intern.c              # string interning
├── intern.h
├── state.c              # GameState, clone, COW accessors
├── state.h              # struct definitions
├── moves.c              # move creation & validation helpers
├── moves.h
├── rules.c              # apply(), legal_moves(), is_terminal(), winner()
├── rules.h
├── helpers.c            # board presence, counting, effect registry
├── helpers.h
├── phases.c             # advance_phase, set_game_over
├── phases.h
├── scoring.c            # end-of-turn and final scoring
├── scoring.h
├── generic_runtime.c    # card interpreter (all generic_runtime/ modules merged)
├── generic_runtime.h
├── actions.c            # generic action appliers
├── actions.h
├── selection.c          # legal target selection generators
├── selection.h
├── player_view.c        # public/private view projection
├── player_view.h
├── loader.c             # JSON → struct loading
├── loader.h
├── rng.c                # deterministic PRNG + shuffle
├�── rng.h
├── arena.c              # arena allocator for state cloning
├── arena.h
├── bindings/
│   └── engine_bindings.py  # cffi/ctypes wrapper exposing Python API
└── tests/
    └── test_engine_c.py     # cross-validation against Python engine
```

### Core Struct Design

```c
// intern.h
typedef uint32_t Sym;          // interned string ID
Sym sym(const char* s);        // intern / lookup
const char* sym_str(Sym s);    // reverse lookup

// state.h
#define MAX_PLAYERS        4
#define MAX_NODES          64
#define MAX_ZONE_SIZE      80
#define MAX_CARDS          256
#define MAX_TROOP_SLOTS    8
#define MAX_PENDING_PROMO  8
#define MAX_SPY_SLOTS      4

typedef struct {
    Sym  node_id;
    Sym* troop_slots;    // interned player IDs, NULL for empty
    int  troop_slot_count;
    Sym* spies;          // interned player IDs
    int  spy_count;
    int  vp_tokens;
} NodeState;

typedef struct {
    Sym   player_id;
    Sym   deck[MAX_ZONE_SIZE];
    int   deck_count;
    Sym   hand[MAX_ZONE_SIZE];
    int   hand_count;
    Sym   discard_pile[MAX_ZONE_SIZE];
    int   discard_pile_count;
    Sym   played_cards[MAX_ZONE_SIZE];
    int   played_cards_count;
    Sym   inner_circle[MAX_ZONE_SIZE];
    int   inner_circle_count;
    Sym   trophy_hall[MAX_ZONE_SIZE];
    int   trophy_hall_count;
    int   barracks;
    int   spies_available;
    int   vp_tokens;
    int   score;
} PlayerState;

typedef struct {
    Sym   source_card_id;
    Sym   ability_key;
} PendingAbility;

// ... (full struct hierarchy mirrors Python models)

typedef struct {
    // immutable definition (shared, not cloned)
    const GameDefinition* definition;
    // board
    NodeState  nodes[MAX_NODES];
    int        node_count;
    // players
    PlayerState players[MAX_PLAYERS];
    int         player_count;
    Sym         player_ids[MAX_PLAYERS];  // turn order
    Sym         current_player_id;
    int         phase;  // TurnPhase enum
    int         round_number;
    ResourcePool resource_pool;
    MarketState  market;
    // pending effects
    PendingAbility*  pending_ability;  // NULL or arena-allocated
    PendingPromo     pending_immediate[MAX_PENDING_PROMO];
    int              pending_immediate_count;
    PendingPromo     pending_eot[MAX_PENDING_PROMO];
    int              pending_eot_count;
    PendingGeneric*  pending_generic;   // NULL or arena-allocated
    Sym              devour_pile[MAX_ZONE_SIZE];
    int              devour_pile_count;
    // setup bookkeeping
    Sym              setup_complete[MAX_PLAYERS];
    int              setup_complete_count;
    int              shuffle_seed;
    int              shuffle_count;
    // COW dirty flags
    uint64_t        cow_dirty;  // bitmask
    // caches
    PresenceCache*  presence_cache;
} GameState;
```

### Memory Model

- **Arena allocator:** Each `GameState` owns an arena. `clone_fast()` creates a new arena and memcpy's the entire state. COW dirty flags track which sub-structs need deep copy on mutation. This is faster than Python's per-field `clone_fast` because it's one `memcpy` + selective fixups.
- **Interned strings:** All `Sym` values are stable across clones. No string copying needed.
- **CardDefinition / BoardDefinition:** Stored once in `GameDefinition`, shared by reference (pointer). Never mutated, so never cloned.
- **`PendingGenericChoice`:** Variable-length action list. Arena-allocated with max-bounds (e.g., 32 actions per card).

---

## Phase Plan

### Phase 0: Infrastructure & Build System (~1 day)
- [ ] Create `engine_c/` directory structure
- [ ] Vendor cJSON
- [ ] Write `Makefile` (compile all .c, link static library `libengine.a`, compile test runner)
- [ ] Write `intern.h/intern.c` — symbol table with hash map
- [ ] Write `arena.h/arena.c` — bump allocator with snapshot/restore
- [ ] Write `rng.h/rng.c` — xoshiro256** PRNG + Fisher-Yates shuffle matching Python's `Random` output for same seeds
- [ ] Write `engine.h` — public API:
  ```c
  GameState* engine_create_game(const char* json_path, const char** player_ids, int count, int seed);
  GameState* engine_clone(const GameState* state);
  void       engine_destroy(GameState* state);
  int        engine_legal_moves(const GameState* state, Move* out, int max_moves);
  GameState* engine_apply(const GameState* state, const Move* move);
  int        engine_is_terminal(const GameState* state);
  Sym        engine_winner(const GameState* state, int* score_out);
  void       engine_public_view(const GameState* state, PublicView* out);
  void       engine_private_view(const GameState* state, Sym player_id, PrivateView* out);
  ```

### Phase 1: Data Structures & Loader (~2-3 days)
- [ ] Define all structs in `state.h` (matching Pydantic model fields)
- [ ] Write `loader.c` — cJSON-based JSON parser for `catalog.json`, `board` JSON, `setup` JSON
- [ ] Write `state.c` — `engine_create_game()`, `engine_clone()`, COW accessors
- [ ] Write `moves.h` — move structs with discriminate union (move_type enum)
- [ ] Cross-validate: load same JSON in Python and C, compare struct field-by-field

### Phase 2: Core Rules (~2-3 days)
- [ ] Write `phases.c` — phase state machine (setup → draw → main → end_of_turn → cleanup → main)
- [ ] Write `scoring.c` — site VP, final score computation
- [ ] Write `helpers.c` — presence checks, deploy/assassinate/spy validation, effect registry, focus checks, recruit logic
- [ ] Write `rules.c` — `engine_apply()` (big switch on move_type), `engine_legal_moves()`, `engine_is_terminal()`, `engine_winner()`
- [ ] Port tests: run existing pytest suite against C engine via bindings, compare move-by-move

### Phase 3: Generic Runtime / Card Interpreter (~2-3 days)
- [ ] Write `generic_runtime.c` — `PendingGenericChoice` interpreter loop, auto-resolve, option selection
- [ ] Write `actions.c` — all 18 generic action appliers (deploy, assassinate, supplant, place_spy, return_spy, etc.)
- [ ] Write `selection.c` — legal target selection generators (deploy targets, spy targets, recruit targets, etc.)
- [ ] Write `player_view.c` — public/private view projection for IS-MCTS
- [ ] Port custom effects from `_custom_effects.py`

### Phase 4: Python Bindings & Cross-Validation (~1-2 days)
- [ ] Write `bindings/engine_bindings.py` using cffi
- [ ] Create `test_engine_c.py` — regression suite that runs both engines side-by-side
- [ ] Validate: for every possible game state reached in existing tests, both engines produce identical `legal_moves()` lists and `apply()` transitions
- [ ] Fix discrepancies until 100% behavioral parity

### Phase 5: Integration & Cleanup (~1 day)
- [ ] Update `game_session.py`, `game_simulation.py`, `game_view.py` to use C engine via bindings
- [ ] Update OpenSpiel wrapper (`openspiel_pyrants/`) if needed
- [ ] Build CI: compile C engine, run cffi bindings, run pytest
- [ ] Remove Python-only engine code (or keep as reference implementation behind a flag)

---

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| Behavioral divergence from Python engine | Phase 4 cross-validation suite catches every discrepancy. Run 10K+ random simulations comparing both engines. |
| Fixed-size array overflow | Define generous bounds (4× max expected). Add `assert()` bounds checks in debug builds. |
| String interning collisions | Use FNV-1a hash with 64-bit keys. Collision check at startup. |
| Memory leaks in arena | Each `GameState` owns one arena. `engine_destroy()` frees it. `engine_clone()` allocates fresh arena. No manual malloc/free outside arena. |
| Performance of COW vs pure clone | Benchmark. Arena-based full `memcpy` is ~100ns for a 50KB state. COW adds branch overhead. Start with full clone, optimize to COW only if profiling demands it. |
| Generic runtime complexity | The interpreter loop is already structured as a state machine in Python. Direct mechanical translation. |

---

## Estimated Timeline

| Phase | Duration | Dependencies |
|-------|----------|-------------|
| Phase 0: Infrastructure | 1 day | None |
| Phase 1: Data Structures & Loader | 2-3 days | Phase 0 |
| Phase 2: Core Rules | 2-3 days | Phase 1 |
| Phase 3: Generic Runtime | 2-3 days | Phase 2 |
| Phase 4: Bindings & Cross-Validation | 1-2 days | Phase 3 |
| Phase 5: Integration & Cleanup | 1 day | Phase 4 |
| **Total** | **9-13 days** | |

---

## Open Questions

1. **Pure C or C with a lightweight framework?** Plan assumes ANSI C11 with no external dependencies beyond cJSON. If you want C++ for RAII/smart pointers, that changes the arena strategy.

2. **Keep Python engine as reference?** Recommended yes, at least until cross-validation passes. Then decide whether to delete or keep as a documentation reference.

3. **OpenSpiel integration?** The `openspiel_pyrants/` wrapper currently imports from `engine.state`. If we move to C, the OpenSpiel wrapper would call engine_c via Python bindings or directly via C API. This is Phase 5 scope.

4. **RNG compatibility?** Must the C engine produce identical shuffled decks as Python's `Random` for the same seed? If yes, we need to port Python's Mersenne Twister. If behavioral equivalence is sufficient (same game outcomes for same starting conditions without bit-identical RNG), xoshiro256** is simpler and faster.

5. **Max bounds for fixed-size arrays?** The current game supports 2-4 players. Proposed: MAX_PLAYERS=4, MAX_ZONE_SIZE=80 (largest realistic deck/hand), MAX_NODES=64, MAX_TROOP_SLOTS=8, MAX_SPY_SLOTS=4. Are these sufficient for all scenarios in `data/`?