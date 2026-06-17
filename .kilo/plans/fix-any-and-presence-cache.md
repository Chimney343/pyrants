# Fix `builtins.any` Overhead and `has_presence` Cache Propagation

## Problem

cProfile shows `builtins.any` is the **#1 self-time hotspot** (36.7s, 82M calls) and `has_presence` is the #2 self-time hotspot (31.8s, 7.4M calls). Together they consume ~73s cumulative time out of 381s total — roughly 19% of all CPU time.

### Root Causes

1. **Generator + `any()` overhead on hot paths.** Every `any(slot == player_id for slot in ns.troop_slots)` creates a Python generator object, then `any()` iterates it. This is ~0.7µs/call. With 82M calls, that's 57s. Replacing with C-level `list.__contains__` (`player_id in ns.troop_slots`) costs ~0.05µs/call — a ~14× speedup per call.

2. **`has_presence` cache is cold on every COW clone.** `_cow_clone` builds a new `__dict__` without copying `_presence_cache`, so every COW clone starts with a cold cache. Each cache miss rebuilds the full presence set by iterating all 81 nodes. With 777K `_legal_main_phase_actions` calls, the cache is rebuilt ~777K times (once per player per state). Copying the cache in `_cow_clone` eliminates most of these rebuilds.

3. **`_cow_node` invalidates cache too aggressively.** Already sets `_presence_cache = None` on any node mutation. This is correct but blunt. Acceptable for now — the wins from propagation dwarf the occasional invalidation.

## Optimizations

### A. Replace `any()` with `list.__contains__` (`in`) on hot paths

All `troop_slots` fields are `list[str | None]`. Checking `player_id in node_state.troop_slots` is semantically identical to `any(slot == player_id for slot in node_state.troop_slots)` — both scan for an element equal to `player_id`, but `list.__contains__` runs in C without creating a generator.

| File | Line | Current | Replacement |
|------|------|---------|-------------|
| `engine/helpers.py` | 74 | `any(slot == player_id for slot in ns.troop_slots)` | `player_id in ns.troop_slots` |
| `engine/helpers.py` | 79 | `any(slot == player_id for slot in adj_ns.troop_slots)` | `player_id in adj_ns.troop_slots` |
| `engine/helpers.py` | 99 | `any(slot_owner == player_id for slot_owner in node_state.troop_slots)` | `player_id in node_state.troop_slots` |
| `engine/helpers.py` | 114 | `any(slot_owner is None for slot_owner in node_state.troop_slots)` | `None in node_state.troop_slots` |
| `engine/helpers.py` | 135 | `any(slot is None for slot in node_state.troop_slots)` | `None in node_state.troop_slots` |
| `engine/scoring.py` | 30 | `any(spy_owner != player_id for spy_owner in node_state.spies)` | `bool(node_state.spies - {player_id})` |

**Non-hot-path `any()` calls** — leave as-is for clarity:
- `engine/rules.py:199` — `any(player_state.barracks == 0 ...)` (2 players, negligible cost)
- `engine/generic_runtime/_actions.py:797` — conditional bonus check (rare path)
- `engine/helpers.py:596` — validation check (non-hot)

### B. Propagate `_presence_cache` through `_cow_clone`

Currently, `_cow_clone` (line 666-691 in `engine/state.py`) builds `d = {...}` without `_presence_cache`. Every COW clone starts cold, forcing `has_presence` to rebuild the presence set from scratch (81-node iteration with `any()` calls).

**Fix**: Add `_presence_cache` to the `_cow_clone` dict, shallow-copying the outer dict (inner sets are read-only after construction and safe to share).

Change in `engine/state.py` `_cow_clone` (line 685 area):
```python
# Before (line ~685, after "shuffle_count"):
"_presence_cache": dict(self.__dict__.get("_presence_cache", {})) if self.__dict__.get("_presence_cache") is not None else None,
```

Wait — there's a simpler approach. The current `_presence_cache` format is `dict[str, set[str]]` (player_id → set of node_ids). We just need a shallow copy of the outer dict. The inner sets are never mutated after construction.

```python
pc = self.__dict__.get("_presence_cache")
"_presence_cache": dict(pc) if pc is not None else None,
```

This `dict(pc)` creates a new outer dict referencing the same inner `set` objects. Since `has_presence` only reads the sets (never mutates), sharing is safe. The outer dict must be copied because `has_presence` writes `cache[player_id] = present` which would otherwise mutate the parent's cache.

**Invalidation is already handled**: `_cow_node` sets `state.__dict__["_presence_cache"] = None`, which replaces the entire cache reference on the COW clone. When `_cow_node` fires on a state, any subsequent `has_presence` call rebuilds from scratch.

### C. Remove `__dict__` cache invalidation from COW accessors that don't affect presence

Currently, ALL four COW accessors invalidate the presence cache:
- `_cow_node` — correct (troop/spy changes affect presence)
- `_cow_player` — **unnecessary** (player fields like hand/deck don't affect presence on the board)
- `_cow_market_state` — **unnecessary** (market changes don't affect presence)
- `_cow_resource_pool` — **unnecessary** (resource changes don't affect presence)

Remove `state.__dict__["_presence_cache"] = None` from `_cow_player`, `_cow_market_state`, and `_cow_resource_pool`. Keep it only in `_cow_node`. This preserves cache warmth across most COW mutations (deploy, assassinate, recruit, etc. all call `_cow_node`, but resource grants and card draws don't need to invalidate presence).

## Implementation Steps

1. **Replace `any()` with `in`** in `engine/helpers.py` (lines 74, 79, 99, 114, 135) and `engine/scoring.py` (line 30)
2. **Add `_presence_cache` propagation** in `engine/state.py` `_cow_clone`
3. **Remove cache invalidation** from `_cow_player`, `_cow_market_state`, `_cow_resource_pool`
4. **Run tests**: `pytest -x -q`
5. **Run lint**: `ruff check .`
6. **Run perf**: `just ismcts-perf` to measure impact

## Expected Savings

| Optimization | Mechanism | Est. Savings |
|---|---|---|
| A. Replace `any()` → `in` | Eliminate ~69M generator+any calls | ~45-50s (12-13%) |
| B. Propagate cache | Skip 81-node rebuild on ~770K states | ~5-10s (1-3%) |
| C. Narrow invalidation | Preserve cache across non-node COW mutations | ~1-2s (marginal) |
| **Total** | | **~50-60s (13-16%)** |

From 381s total → ~325s, or ~245µs/action → ~210µs/action (1.17× faster per action, on top of the previous 6.7× speedup).

## Risk Assessment

- **Semantic correctness**: `player_id in list[str | None]` is identical to `any(slot == player_id for slot in list)`. Python `list.__contains__` uses `==` comparison, which correctly handles `None` elements (`None == "player1"` is `False`).
- **Cache correctness**: Presence cache propagation is safe because `_cow_clone` shares `board.nodes` values by reference. The cache reflects the state of those shared nodes. When `_cow_node` replaces a node, it invalidates the cache. The outer dict is shallow-copied to prevent cross-clone mutations.
- **Invalidation correctness**: Only `_cow_node` mutations (troop/spy changes) can affect presence. Player deck/hand, market, and resource changes do not affect which nodes a player has presence at.