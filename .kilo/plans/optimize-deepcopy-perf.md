# Optimize GameState Deep Copy for IS-MCTS Performance

## Problem

cProfile shows `GameState.__deepcopy__` consumes **81% of IS-MCTS runtime** (85.5s of 105s). The root cause is 66.8M calls to `_copy_field` and 10.7M calls to `_model_deepcopy_fields` — generic type-dispatch + per-field function-call overhead on every state clone.

Key cProfile hotspots:

| Function | ncalls | tottime | cumtime | % total |
|---|---|---|---|---|
| `_copy_field` | 66.8M | 37.6s | 84.4s | 80% |
| `_model_deepcopy_fields` | 10.7M/637K | 30.7s | 82.1s | 78% |
| `GameState.__deepcopy__` | 124K | — | 85.5s | 81% |
| `dict.get` (type dispatch) | 79.6M | 8.7s | 8.7s | 8% |

Every IS-MCTS simulation step deep-copies the entire ~81-node GameState through the generic dispatcher. Each `GameState` copy triggers **~540 field copies** (17 top-level fields + 81 × 4 NodeState fields + 2 × 11 PlayerState fields + others), each paying function-call and type-dispatch overhead.

## Analysis: What Already Works

- **COW in `rules.apply()`**: `_cow_clone()` + lazy `_cow_node`/`_cow_player` accessors are already used for in-game state transitions. These are efficient (~3 sims/s observed for main-phase moves). Not the bottleneck.
- **`definition` sharing**: `GameState.__deepcopy__` already skips copying the frozen `GameDefinition` by reference.
- **`_TYPE_DISPATCH` table**: Optimized type dispatch but still pays dict.get() per field.

## Root Cause

The **IS-MCTS tree clone path** (`PyrantsState.clone()` → `copy.deepcopy()` → `GameState.__deepcopy__`) is a full deep copy, not COW. Each of the 124K clones walks every nested model and dispatches every field through `_copy_field`. The Python function-call overhead (~0.5μs/call) × 540 fields × 124K clones ≈ 33s just in call overhead — matching the observed 37.6s self-time of `_copy_field`.

## Strategy: Specialized `clone_fast()` Method

Replace the generic `_copy_field`/`_model_deepcopy_fields` recursion with a **hand-written `clone_fast()`** on `GameState` and hot sub-models. Each method directly constructs a new instance with known field types — no type dispatch, no per-field function calls, no dict iteration.

### Field Classification

Every `GameState` field falls into one of 5 copy categories:

| Category | Fields | Copy strategy |
|---|---|---|
| **Share (frozen)** | `definition` | Identity copy — share reference |
| **Scalar** | `current_player_id`, `phase`, `round_number`, `shuffle_seed`, `shuffle_count` | Identity copy — immutable primitives |
| **Simple container** | `turn_order`, `devour_pile`, `final_scores`, `setup_complete` | `list()`, `dict()`, `set()` — shallow copy (contents are immutable strings/ints) |
| **Mutable sub-model** | `board`, `resource_pool`, `market`, `pending_ability`, `pending_generic_choice`, `pending_immediate_promotions`, `pending_end_of_turn_promotions` | Call `.clone_fast()` or construct new instance directly |
| **Mutable dict of sub-models** | `players` | `dict()` shell + clone each value |

### Sub-model clone_fast methods

Each hot sub-model gets its own `clone_fast()`:

- **`NodeState.clone_fast()`**: 4 fields — `node_id` (str, share), `troop_slots` (list, `list()`), `spies` (set, `set()`), `vp_tokens` (int, share). Constructed with `__new__` + `__dict__` assignment to bypass Pydantic validation.
- **`BoardState.clone_fast()`**: 1 field — `nodes` (dict). Shell dict + `NodeState.clone_fast()` per value.
- **`PlayerState.clone_fast()`**: 11 fields — identity for scalars, `list()` for list fields, int fields share.
- **`ResourcePool.clone_fast()`**: 2 fields — direct int copy.
- **`MarketState.clone_fast()`**: 3 fields — `list()` for each.
- **`PendingAbilityState.clone_fast()`**: 2 fields — str share.
- **`PendingPromotionState.clone_fast()`**: 9 fields — str/bool/int share, optional str share.
- **`PendingGenericChoiceState.clone_fast()`**: 13 fields — str/int/bool share, `list()` for list fields, special handling for `current_actions` (list of frozen CardAction — `list()` shallow copy since items are frozen), `dict()` for dict fields.

### PyrantsState integration

Override `PyrantsState.__deepcopy__` to call `self._engine.clone_fast()` instead of letting Python recursively deep-copy the engine:

```python
class PyrantsState(pyspiel.State):
    def __deepcopy__(self, memo):
        new = PyrantsState.__new__(PyrantsState)
        pyspiel.State.__init__(new, self._game)
        new._game = self._game  # shared — game definition is immutable
        new._pending_initial_chance = self._pending_initial_chance
        new._cached_indexed_moves = None
        new._engine = self._engine.clone_fast() if self._engine is not None else None
        memo[id(self)] = new
        return new
```

### Expected speedup

- **Current**: 540 function calls + 540 type dispatches per GameState deep copy × 124K clones = ~80s
- **Optimized**: ~540 direct dict assignment operations per GameState × 124K clones = ~1–3s (eliminating function call + type dispatch overhead)
- **Estimated overall speedup**: 105s → ~20–25s (4–5× faster)

### What stays the same

- `_cow_clone()` and COW accessors: unchanged, still used in `rules.apply()` path
- `_model_deepcopy_fields` and `_copy_field`: kept for non-hot code paths (e.g., `determinization.py` uses `model_copy(deep=True)`)
- All tests: `__deepcopy__` continues to work, just delegates to `clone_fast()` internally

## Implementation Steps

### Step 1: Add `clone_fast()` to leaf sub-models

Add to: `NodeState`, `BoardState`, `PlayerState`, `ResourcePool`, `MarketState`, `PendingAbilityState`, `PendingPromotionState`, `PendingGenericChoiceState`

Each method:
1. Creates new instance with `cls.__new__(cls)`
2. Builds a new `__dict__` with direct field copies (no type dispatch)
3. Sets pydantic internals (`__pydantic_fields_set__`, `__pydantic_private__`, `__pydantic_extra__`)
4. Returns the new instance

### Step 2: Add `clone_fast()` to `GameState`

Builds a new `GameState` by:
1. Sharing `definition` by reference
2. Calling `board.clone_fast()` for board
3. Building `players` dict with `{pid: ps.clone_fast() for pid, ps in ...}`
4. Copying scalar fields by identity
5. Copying simple containers with `list()`/`dict()`/`set()`
6. Calling `.clone_fast()` on mutable sub-models (resource_pool, market, pending states)
7. Handling `None` for optional fields

### Step 3: Wire `GameState.__deepcopy__` to `clone_fast()`

Replace the current `__deepcopy__` implementation:
```python
def __deepcopy__(self, memo):
    result = self.clone_fast()
    if memo is not None:
        memo[id(self)] = result
    return result
```

This preserves the `memo` contract for `copy.deepcopy` while using the fast path.

### Step 4: Override `PyrantsState.__deepcopy__`

Prevent `copy.deepcopy` from walking the PyrantsState C++ base class. Use `self._engine.clone_fast()` for the engine copy. Share `self._game` by reference (it's immutable definition + shared state).

### Step 5: Update `determinization.py`

Replace `engine.model_copy(deep=True)` with `engine.clone_fast()`.

### Step 6: Run tests

```bash
just test
```

### Step 7: Run IS-MCTS perf benchmark

```bash
just ismcts-perf
```

Compare cProfile output: `clone_fast()` should appear with ~0 tottime instead of the current 37.6s + 30.7s for `_copy_field` + `_model_deepcopy_fields`.

### Step 8: Run engine purity test

```bash
python -m pytest tests/test_engine_purity.py -v
```

Ensures no I/O side effects were introduced.

## Correctness Guarantees

`clone_fast()` must produce **exactly the same result** as `__deepcopy__` — a fully independent copy where:
- Mutable containers (list, dict, set) are new objects with the same contents
- Mutable sub-models are recursively cloned with new identities
- Frozen/immutable sub-models are shared by reference (only `definition` tree)
- All Pydantic internals are correctly set

The test plan:
1. Existing `test_engine_purity.py` — no I/O violations
2. Clone-then-mutate test: deep-copy a GameState, mutate the copy, verify original is unchanged
3. Clone-equality test: deep-copy a mid-game GameState, serialize both to JSON, verify equality
4. IS-MCTS smoke test: `just ismcts-quick` should produce identical game outcomes

## Risk Assessment

- **Low risk**: `clone_fast()` is a pure optimization — same inputs produce same outputs
- **Medium risk**: Pydantic internal fields (`__pydantic_fields_set__`, etc.) must be set correctly or validation/pickling breaks. Mitigated by keeping the same `object.__setattr__` pattern as existing `_model_deepcopy_fields`
- **Medium risk**: If `GameState` fields are added/removed, `clone_fast()` must be updated. Mitigated by adding a comment in `GameState` class and a runtime assertion that checks all fields are handled

## Future Optimization (out of scope)

- **Skip immutable fields in COW**: `_cow_clone()` could share more fields by reference (e.g., `turn_order` is a `list[str]` that's never mutated in place — only replaced)
- **Structural sharing**: IS-MCTS could avoid full clones entirely by storing move deltas and reconstructing state from the root
- **`_copy_field` micro-optimization**: Replace `dict.get()` type dispatch with `match/case` (Python 3.10+) or inline checks — saves ~8s but minor compared to `clone_fast()`