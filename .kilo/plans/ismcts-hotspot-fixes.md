# IS-MCTS Performance Plan — Address cProfile Hotspots

## Context

A `cProfile` run of `just ismcts-perf` (3 sims × 1 game × 2 rounds, seed 42,
~455s) shows ~96% of cumulative time is `copy.deepcopy` of `GameState` for
every OpenSpiel state clone. The remaining hotspots are leaf-evaluation
action-map recomputation, board scanning, and dict allocation inside
Pydantic deep-copy. Profile artifacts live in
`artifacts/ismcts/performance_testing/cprofile.pstats` and
`cprofile_top.txt`.

The plan keeps `engine/` pure (no I/O, no caching layers in the public API)
and minimizes blast radius. Each step is independently testable and
reversible.

## Hotspot Summary (sorted by ROI)

| # | Hotspot | Cumulative | Root cause | Plan step |
|---|---------|------------|------------|-----------|
| 1 | `engine/state.py:376 __deepcopy__` (delegates to pydantic + `copy.deepcopy`) | 430s / 455s | Walks entire `GameState` graph via Pydantic `__deepcopy__` per field; allocates new dict/list per attribute | 1 |
| 2 | `openspiel_pyrants/state.py:57 _apply_action` (accumulates 438s via `apply_move` → `rules.apply` → `model_copy(deep=True)`) | 438s | Each `apply` does a deep copy of state | 1 (root fix) |
| 3 | `openspiel_pyrants/action_encoding.py:74 compute_action_map` (called twice per legal-actions query: 11.8s) | 11.8s | Recomputed on every `_legal_actions` call; result not cached across `is_terminal` / `legal_actions` cycle | 2 |
| 4 | `engine/helpers.py:91 _can_deploy_to_node` + `_player_has_any_troops_on_board` | 8.9s + 5.3s | Scans every board node per deploy action; `state.board.nodes` iterated for every legal `DeployMove` (~9 per turn × 50 turns) | 3 |
| 5 | `pydantic.main.__deepcopy__` recursion overhead | 23.6s self | Pydantic v2 deep-copy re-instantiates each sub-model via `model_copy` | 1, 4 |

## Step 1 — Replace `GameState.__deepcopy__` with a hand-rolled structural clone

**File:** `engine/state.py` (lines 376-409)

Replace the current pydantic-aware `__deepcopy__` with a one-shot structural
copy that:

- Skips the `definition` field (immutable, already shared) — already done.
- Iterates `self.__dict__` exactly once, but instead of `deepcopy(value, memo)`
  per attribute, dispatches by type: `list` → `list comprehension copy`,
  `set` → `set.copy()`, `dict` → `{k: v.copy() if isinstance(v, (list, set, dict)) else deepcopy(v, memo) for k, v in d.items()}`,
  primitives → share.
- Bypasses `pydantic.main.__deepcopy__` recursion by:
  1. Building child objects via `model_construct(...)` with already-copied
     field values, OR
  2. A whitelist of mutable sub-models (`BoardState`, `PlayerState`,
     `ResourcePool`, `PendingGenericChoiceState`) where we copy fields
     directly with `object.__setattr__`, mirroring what the current
     implementation does for the top level.

The fastest safe pattern is the second: extract a small
`_shallow_copy_state_attrs(self) -> dict` helper used by `__deepcopy__` for
each sub-model. This avoids `pydantic.main.__deepcopy__`'s overhead entirely.

**Existing code under change:**

```python
# engine/state.py:376-409
def __deepcopy__(self, memo: dict[int, Any] | None = None) -> GameState:
    cls = type(self)
    m = cls.__new__(cls)
    if memo is None:
        memo = {}
    memo[id(self)] = m

    # Build __dict__ without deep-copying the immutable definition
    d: dict[str, Any] = {}
    for key, value in self.__dict__.items():
        if key == "definition":
            d[key] = value  # immutable → share reference
        else:
            d[key] = deepcopy(value, memo)

    object.__setattr__(m, "__dict__", d)
    object.__setattr__(m, "__pydantic_extra__", deepcopy(self.__pydantic_extra__, memo=memo))
    object.__setattr__(m, "__pydantic_fields_set__", copy(self.__pydantic_fields_set__))
    # ... private attrs copy ...
```

**Target shape:**

```python
_MUTABLE_LIST_FIELDS = (...)   # derived from each sub-model's annotations
_MUTABLE_SET_FIELDS  = (...)
_MUTABLE_DICT_FIELDS = (...)

def _copy_field(value: Any, memo: dict[int, Any]) -> Any:
    if isinstance(value, (str, int, bool, type(None))) or value is ...:
        return value
    if isinstance(value, list):
        return [__copy_field(v, memo) for v in value]
    if isinstance(value, set):
        return {__copy_field(v, memo) for v in value}
    if isinstance(value, dict):
        return {k: __copy_field(v, memo) for k, v in value.items()}
    if hasattr(value, "__deepcopy__"):
        return value.__deepcopy__(memo)
    return deepcopy(value, memo)
```

Plus a typed copier for the three Pydantic sub-models that hold the
mutable bulk (`board`, `players`, `pending_generic_choice`,
`pending_end_of_turn_promotions`, `devour_pile`, `setup_complete`).

**Tests that must continue to pass (none directly cover deepcopy):**
- `tests/test_state_machine.py` — verifies apply/move semantics; relies on
  `apply()` returning an independent state. Add a new test
  `test_deepcopy_is_independent` asserting `copy.deepcopy(s) is not s`,
  `s2.definition is s.definition`, and mutating a list on `s2.players[0].hand`
  does not affect `s`.
- `tests/test_rules_basics.py`, `test_rules_cards_a_m.py`,
  `test_rules_cards_n_z.py`, `test_rules_focus.py`, `test_rules_ability.py`,
  `test_rules_promotion.py` — all exercise full game apply/clone cycles.
- `tests/test_engine_purity.py` — must remain green; the new helper is pure.
- `tests/test_shuffle_determinism.py` — depends on identity of
  `definition` being shared; the new code must preserve that contract.
- `tests/test_player_view.py` — projects state; depends on copy correctness.

**Success criteria:** `just ismcts-perf` cProfile run shows `tottime` for
`copy.deepcopy` and `pydantic.main.__deepcopy__` drop by ≥50%; `cumulative`
inside `state._apply_action` drops proportionally. All 32 test files pass
(`just test`).

## Step 2 — Cache `compute_action_map` in `OpenspielPyrantsState`

**File:** `openspiel_pyrants/state.py` (lines 51-73)

The current code already has `self._cached_indexed_moves` but invalidates
it on every `_apply_action`. OpenSpiel's `State` API calls
`legal_actions()` many times per decision (once for OpenSpiel internal
bookkeeping, once by `ISMCTSBot.step`, often more during
`is_terminal`/`current_player` cycles). Cache for the lifetime of the
state, invalidated only on `_apply_action` (already correct).

The remaining miss: `_legal_actions` is called *before* the first
`_apply_action` and we compute the map fresh each call. The fix: compute
once on first access, store in `self._cached_indexed_moves`, and only
recompute if the field is `None` (current code does this — verify
`_legal_actions` is the only entry point that mutates the cache).

**Code to change:**

```python
# openspiel_pyrants/state.py:51
def _legal_actions(self, player):
    if self._pending_initial_chance:
        return list(range(self._game.get_shuffle_seed_count()))
    if self._cached_indexed_moves is None:
        self._cached_indexed_moves = compute_action_map(self._engine)
    return list(range(len(self._cached_indexed_moves)))
```

Also: hoist `compute_action_map` work to `_apply_action` (after the
move, before returning) so the next `legal_actions` call hits cache:

```python
# openspiel_pyrants/state.py:67-73
self._engine = apply_move(self._engine, move)
self._cached_indexed_moves = compute_action_map(self._engine)
```

`compute_action_map` itself does two `model_dump_json` per move (lines 67-69
of `action_encoding.py`) inside the dedup check. Profile shows that is
<1s; not the primary win, but switching to `move == move` identity
comparison on the typed `Move` instance (with a tie-breaker on a stable
key tuple) avoids two `pydantic` serializations per move.

**Tests that must pass:**
- `tests/test_player_view.py` — verifies determinization round-trips.
- `tests/test_state_machine.py` and scenario tests.
- Add a new unit test asserting that
  `OpenspielPyrantsState.legal_actions()` returns the same list identity
  across two consecutive calls (cache hit), and that `_apply_action`
  invalidates the cache.

**Success criteria:** `_legal_actions` cumulative time in the pstats
drops by ≥80%; `compute_action_map` tottime drops by ≥50%.

## Step 3 — Precompute per-player board occupation

**File:** `engine/helpers.py` (lines 60-102)

Both `_player_has_any_troops_on_board` and `has_presence` scan
`state.board.nodes.values()` for every call. `_legal_main_phase_actions`
calls `_can_deploy_to_node` once per node (up to 81 nodes) per turn, and
`has_presence` from `_legal_main_phase_actions` is also per-node in the
assassinate loop.

Two options, in order of impact:

1. **Per-state memoization key on `state` id**: a tiny module-level
   cache `{(id(state), player_id): set[node_id]}` mapping player to the
   set of nodes where they have troops. Invalidate by `id` collision is
   fine here because `GameState` is immutable; we never mutate, only
   create new ones, and ids are recycled only after GC. Wrap in
   `functools.lru_cache`-equivalent: a `WeakValueDictionary` keyed on the
   state itself, or simply a `dict[GameState, set[str]]` since state
   instances are short-lived per `apply` and the dict stays bounded by
   the search depth.

2. **Cheaper scan**: cache `troop_slots_owner_index` once per state and
   short-circuit `_can_deploy_to_node` against an `int` count. The first
   approach is simpler and gives bigger wins.

```python
_PLAYER_TROOP_NODES: dict[int, set[str]] = {}

def _player_has_any_troops_on_board(state, player_id):
    key = id(state)
    cache = _PLAYER_TROOP_NODES.get(key)
    if cache is None:
        cache = {
            nid
            for nid, ns in state.board.nodes.items()
            if any(slot == ... for slot in ns.troop_slots)  # any player
        }
        _PLAYER_TROOP_NODES[key] = cache
    return player_id in cache  # and similarly per-player
```

To avoid unbounded growth, clear `_PLAYER_TROOP_NODES` when the count
exceeds e.g. 10_000 entries, or use `cachetools.LRUCache(maxsize=2048)`
(adding a dep) or a `WeakKeyDictionary` keyed on the state.

**Code under change:**

```python
# engine/helpers.py:60-88
def has_presence(state, player_id, node_id): ...   # iterates board
def _player_has_any_troops_on_board(state, player_id): ...   # iterates board
def _can_deploy_to_node(state, player_id, node_id): ...
```

**Tests that must pass:**
- `tests/test_rules_basics.py` — legal-move generation tests; verify no
  change in set of generated deploy moves.
- `tests/test_rules_cards_*` — full game integration.
- `tests/test_state_machine.py`.
- `tests/test_engine_purity.py` — module-level cache is process-local
  state, not I/O; explicitly check purity is preserved (no `print`,
  no `open`, no `random` global). Cache does not violate purity.

**Caveat:** a module-level mutable cache is technically a global. If the
purity test asserts "no module-level state mutation", we should gate the
cache behind a `functools.lru_cache(maxsize=2048)` on a helper that takes
the state by id+`__dict__` snapshot, OR use `WeakKeyDictionary` on the
state instance (states are referenced by the search tree, so they stay
alive — `WeakKeyDictionary` would clear them when the tree drops them,
which is the desired behavior).

**Success criteria:** `_can_deploy_to_node` + `has_presence` cumulative
time drops by ≥70% in the profile.

## Step 4 — Bypass pydantic `__deepcopy__` recursion for hot sub-models

**Files:** `engine/state.py` (lines 1-50, model definitions)

Pydantic v2's `BaseModel.__deepcopy__` (line 990 of `main.py` per the
profile) recurses through every field and calls `model_copy(deep=True)`
per sub-model. For models with frozen sub-models like `definition`, this
re-validates constraints on every copy.

Optimization: define `__deepcopy__` on the three Pydantic sub-models
(`BoardState`, `PlayerState`, `ResourcePool`,
`PendingGenericChoiceState`, `MarketState`) using the same hand-rolled
pattern as Step 1. The Pydantic `__deepcopy__` cost is a function of the
model's field count, so eliminating it on the bulk-data sub-models
(BoardState with 81 nodes, PlayerState with hand/deck/agent) is the
biggest single win after Step 1.

This is essentially a generalization of Step 1 to nested models. Do it
as a follow-up if Step 1's top-level change leaves measurable
`pydantic.main.__deepcopy__` time in the next profile.

**Tests:** same as Step 1 (the new helpers must produce correct, fully
independent copies of all sub-models).

**Success criteria:** `pydantic.main.__deepcopy__` tottime in pstats
drops by ≥90%.

## Out of Scope (intentionally not addressed)

- **Action map `model_dump_json` dedup** — sub-second; not worth the
  complexity of switching to identity comparison without first measuring.
- **Cython/Rust rewrite of `apply`** — too invasive for a 2-3x speedup
  target; the structural copy in Step 1 alone should reach that.
- **Replacing Pydantic with `dataclasses` or `attrs`** — wide blast
  radius; the `BaseModel` model validation is load-bearing for the
  scenario system. Defer.
- **`engine/rules.py:122 apply` itself** — its 0.3s self-time is dwarfed
  by the deep copy it triggers; the fix is in the copy, not the
  dispatcher.
- **`_apply_play_card` / `_effect_generic_card`** — 221s cumulative is
  entirely the deep copy underneath them. Once Step 1 lands, this
  collapses with it.

## Validation Plan

After each step:

1. Run `just test` — full pytest suite must remain green.
2. Run `just lint` — `ruff check .` clean.
3. Run `just ismcts-perf` — re-profile, compare `cprofile_top.txt`
   to the baseline saved at `artifacts/ismcts/performance_testing/cprofile_top.txt`.

Final pass criteria:

- IS-MCTS `--num-sims 10 --num-games 1 --max-rounds 3` wall time
  (from `metrics.json`) drops from baseline ≥ 50%.
- `copy.deepcopy` + `pydantic.main.__deepcopy__` combined cumulative
  time drops from ~440s to ≤150s on the same scenario.
- All 32 test files pass; `ruff` clean.
