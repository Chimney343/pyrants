# Plan: optimize `_apply_action` cumulative time (post-cache)

## Context

`just ismcts-perf` was re-run after caching `GameDefinition`. The win was large but `_apply_action` is now the dominant cost:

| Metric | Value |
|---|---|
| Total CPU time | 93.46 s |
| `_apply_action` cumtime | **47.49 s (50.8 %)** |
| `_apply_action` calls | 498,878 |
| `_apply_action` tottime (self) | 1.22 s |
| `apply` (rules.py:126) cumtime | 46.27 s |
| `_apply_play_card` cumtime | 25.91 s (186,086 calls) |
| `_resolve_generic_execution` cumtime | 20.20 s |
| `_auto_resolve_pending_generic` cumtime | 8.62 s |
| `_apply_resolve_generic_choice` cumtime | 4.85 s |
| `_apply_generic_action` cumtime | 4.95 s |
| `_legal_main_phase_actions` cumtime | 13.73 s (321,161 calls) |
| `compute_action_map` cumtime | 26.28 s (498,877 calls) |
| `legal_moves` cumtime | 22.84 s (499,330 calls) |
| `_cow_clone` tottime / cumtime | 5.99 / 12.38 s (1,287,273 calls) |
| `validate_python` tottime | 4.87 s (3,254,398 calls) |
| `has_presence` tottime / cumtime | 3.15 / 3.97 s (3,211,145 calls) |
| `_can_deploy_to_node` tottime / cumtime | 1.33 / 4.83 s (4,219,809 calls) |
| `_remaining_special_stack_count` tottime / cumtime | 2.61 / 5.63 s (988,901 calls) |
| `_model_deepcopy_fields` cumtime | 2.50 s (151,303 calls) |

The MCTS loop for each decision in OpenSpiel is roughly: `legal_actions` → `_legal_actions` → `compute_action_map` → `legal_moves` → `_legal_main_phase_actions`, then per simulated step: `apply_action` → `_apply_action` → `apply` → handler. Both code paths are exercised almost once per simulated action.

## Goal

Reduce `_apply_action` cumulative time by **30–50 %** through targeted, low-risk changes inside the engine and OpenSpiel adapter. Validate via `just ismcts-perf` re-measurement.

## Key observations from reading the code

1. **Two COW clones per `play_card`.** `_apply_play_card` (rules.py:223) calls `state._cow_clone()` at line 233, then calls `_apply_effect_with_wrappers(updated, ...)` which calls `state._cow_clone()` *again* at line 347. Total = 2 COW clones per play card (186,086 × 2 = 372,172 COW clones just from this pattern). The second COW is wasted because `_apply_play_card` does no further writes after the wrapper returns.

2. **`_resolve_generic_execution` may make a third COW clone** (resolve.py:327) when `pending_generic_choice` is set. For cards with pending choices this is unavoidable, but for "auto-resolved" cards (no choice), the pending is still set and the clone still happens.

3. **`legal_moves` is called ~once per `_apply_action`.** `compute_action_map` (action_encoding.py:119) sorts the full legal-move list each time. The sort key uses `str(move)`; this is expensive because of nested Pydantic models and lists. In MCTS many legal-move computations are on cloned states, so `self._cached_indexed_moves` (on `PyrantsState`) is invalidated.

4. **`_legal_main_phase_actions` iterates every node on the board twice** (deploy loop and the assassinate/return-spy loop). For each deploy check it calls `_can_deploy_to_node` → `has_presence` (with a per-player cache) and `_player_has_any_troops_on_board` (no cache). For an 81-node board with mostly-empty slots this is 162 board iterations per legal-moves call.

5. **`_remaining_special_stack_count` (helpers.py:220)** iterates `state.market.deck + state.market.row + 5 player card zones` per call. It is called from `_legal_main_phase_actions` (up to 3 times per legal-moves call) and from `_apply_recruit`. Total 988,901 calls, 2.6 s tottime. The result depends only on the immutable `CardDefinition` and the *sum* of card counts per zone; it could be memoized per `(card_id, state_id)`.

6. **`has_presence` cache** (helpers.py:64) is invalidated only when `_cow_node` mutates a node (line 706). But many state changes don't touch a node (resource pool, hand, played cards, market, etc.) yet the cache persists across them. This is correct, but the cache key is `player_id` only — the whole per-player set is recomputed the first time `has_presence` is asked for a player whose state hasn't changed. Many MCTS nodes share most state, so re-using the cache aggressively helps.

7. **`_cow_clone` itself** does ~12 field copies and one `model_copy` for `pending_generic_choice`. The `__pydantic_extra__` dict is recreated, and `__pydantic_fields_set__` is copied. For 1.29 M calls this is ~6 s of self time. Most of the per-state work is small but cumulative.

8. **`Pydantic validate_python`** is called 3.25 M times for 4.87 s. Most of these come from `__init__` (3.25 M calls) and `model_copy` (374 K calls). Each Pydantic `__init__` re-validates all fields. We could use `model_construct` or pass `__pydantic_validator__.validate_python` skip flags. But this is a larger, riskier change.

9. **`_model_deepcopy_fields` (state.py:71)** is called 151 K times for 2.5 s. This is the fallback `__deepcopy__` for Pydantic models that don't have `clone_fast`. It uses `copy.deepcopy` internally. Could be replaced with field-by-field shallow copy where appropriate.

10. **`PyrantsState._cached_indexed_moves` is not preserved across `__deepcopy__`** of the OpenSpiel state (line 44-52). But it is preserved on `_cow_clone` of the engine state, since `__deepcopy__` uses `self._engine.clone_fast()`. However, OpenSpiel clones the `PyrantsState` (not the engine) via `__deepcopy__`, and the new `PyrantsState` gets a fresh `_engine` and a `None` cache. So MCTS rollout re-computes `compute_action_map` after every clone.

## Optimization proposals (ranked by impact and risk)

### 1. Eliminate the duplicate COW clone in `_apply_effect_with_wrappers` (high impact, low risk)

`_apply_effect_with_wrappers` always starts with `updated = state._cow_clone()`. The caller `_apply_play_card` has already done a COW clone and only mutates the player zone (hand pop, append to played_cards). After that, `_apply_effect_with_wrappers` calls the effect, then optionally `_apply_promote_instruction`. The effect itself uses COW on the already-COW'd state.

**Change:** remove the redundant `state._cow_clone()` at the top of `_apply_effect_with_wrappers`. Document that the caller must pass a mutable state. The effect implementation already uses `_cow_*` accessors so it can accept an already-COW'd state.

Expected savings: ~6 s (one COW clone per play card, at ~5 µs each × 186 K = 0.93 s of tottime, plus downstream `__deepcopy__` cost). Actually, COW tottime is ~6 µs, so 186 K × 6 µs = 1.1 s tottime. But each COW clone also triggers `_model_deepcopy_fields` and `validate_python` downstream. Total realistic saving: **2–4 s**.

### 2. Drop the third COW clone in `_resolve_generic_execution` for sequence / repeat_choice without auto-resolve (medium impact, medium risk)

For a sequence execution model with no selection required, the pending is set then auto-resolved, but we still pay the COW cost twice. The first COW is the wrapper's; we just removed it (point 1). The second COW is in `_resolve_generic_execution` line 327. This COW is needed because `updated.pending_generic_choice = pending` mutates the state. The pending is a fresh `PendingGenericChoiceState` with `model_copy(deep=True)` actions.

**Change:** skip the COW clone when the state is *already* a fresh mutable state (i.e., the caller has already done `_cow_clone`). Track via a private flag (`_is_mutable_view`) set by `_cow_clone`. Or pass an explicit `mutate=True` parameter. Less invasive: accept a `mutate` kwarg defaulting to `False` and pass `True` from `_apply_effect_with_wrappers` (after point 1).

Expected savings: ~1–2 s. Fewer COW clones during generic-card resolution.

### 3. Cache `compute_action_map` and `legal_moves` on the engine state, not on the OpenSpiel state (high impact, medium risk)

The OpenSpiel adapter's `_cached_indexed_moves` lives on `PyrantsState` and is invalidated by `__deepcopy__` (it sets `new._cached_indexed_moves = None`). The engine `GameState` is preserved across `PyrantsState` clones (via `self._engine.clone_fast()`), so we can cache the indexed moves and the legal-move list there, keyed by a monotonic version stamp that increments whenever the engine mutates.

**Change:**
- Add a `_version: int` field (managed via `__dict__` for performance) to `GameState` and a `bump_version()` helper.
- Bump the version in every COW accessor / mutator (`_cow_player`, `_cow_node`, `_cow_market_state`, `_cow_resource_pool`) and in places that mutate top-level state (`_apply_play_card`, `_apply_resolve_generic_choice`, etc., i.e. wherever `updated = state._cow_clone()` is followed by writes).
- Add `_cached_legal_moves: list[Move] | None`, `_cached_legal_moves_version: int`, `_cached_indexed_actions: list[tuple[int, Move]] | None`, `_cached_indexed_actions_version: int` to `GameState.__dict__`.
- In `_legal_actions` and `compute_action_map`, check the version and return the cached list when unchanged.

Expected savings: **6–10 s**. Most MCTS clones will reuse the cache, since most clones only change a few board positions. The legal-move computation is currently 26.3 s; caching could halve it.

Risk: must bump the version on *every* write. A single missed write yields stale legal moves. Mitigation: also bump in a Pydantic-friendly way and add a "strict mode" that disables the cache for tests.

### 4. Pre-compute deploy targets and presence set per state (medium impact, low risk)

`_legal_main_phase_actions` (rules.py:332) does 81 node iterations for deploy and 81 for assassinate/return-spy. The per-node checks (`_can_deploy_to_node`, `has_presence`, `_player_has_any_troops_on_board`) can be batched.

**Change:** compute a single set of `deploy_targets` and a `has_troops` boolean once, then iterate once. Use the existing `_presence_cache` for `has_presence` (already does). Skip nodes whose first troop slot is `None` early. Iterate `state.board.nodes.items()` once and bucket by operation.

Expected savings: **2–4 s** (out of 13.7 s for `_legal_main_phase_actions`, plus reduce `has_presence` recomputations).

### 5. Memoize `_remaining_special_stack_count` on `(state_version, card_id)` (medium impact, low risk)

The result depends only on card counts across the market and player zones. Adding to the version-keyed cache from point 3 yields near-zero cost for repeated calls.

Expected savings: **1–2 s** (out of 2.6 s tottime).

### 6. Avoid Pydantic `validate_python` during model copies (low impact, high risk)

3.25 M calls, 4.87 s tottime. Most come from `BaseModel.__init__` and `model_copy`. We could pass `_PydanticGenericType` or use `model_construct`. But this is a pervasive change with subtle correctness implications. Defer.

Expected savings if done: **2–4 s**, but correctness risk is high.

### 7. Inline `_cow_clone` shallow copies (low impact, low risk)

The `_cow_clone` does `dict(self.players)`, `list(self.turn_order)`, `set(self.setup_complete)`, `list(self.devour_pile)`. These are shallow. The 5.99 s tottime for 1.29 M calls is ~4.6 µs per call. Most of the cost is the dict/list/set construction. Marginal savings possible by inlining.

Expected savings: **0.5–1 s**. Defer unless other changes leave a clear bottleneck.

## Proposed implementation order

1. **Point 1** — remove duplicate COW in `_apply_effect_with_wrappers`. Lowest risk, immediate gain.
2. **Point 4** — single-pass legal-move generation in `_legal_main_phase_actions`.
3. **Point 5** — memoize `_remaining_special_stack_count` per state version.
4. **Point 3** — versioned legal-move / indexed-actions cache on `GameState`.
5. **Point 2** — drop third COW in `_resolve_generic_execution` once the cache (point 3) is in place.
6. Re-measure with `just ismcts-perf`.

## Acceptance criteria

1. `just ismcts-perf` runs to completion; game length is comparable to baseline.
2. `cprofile.pstats` shows:
   - `_apply_action` cumtime < 35 s (down from 47.5 s).
   - `legal_moves` cumtime < 15 s (down from 22.8 s).
   - `_cow_clone` calls < 1 M (down from 1.29 M).
   - `_legal_main_phase_actions` cumtime < 9 s (down from 13.7 s).
3. Wall time per move < 1.1 s (down from 1.3 s).
4. `just test` passes — no regression in engine correctness.
5. `tests/test_engine_purity.py` still passes — no I/O introduced.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Stale legal-move cache after a missed write | Add a "strict mode" flag (env var or pytest fixture) that disables the cache and asserts in tests; enable strict mode in `just test`. |
| Removing COW clone breaks COW invariants | Add a `mutate=True` contract: callers that pass an already-COW'd state are responsible for COW accessors. The current code path already uses COW accessors downstream. |
| Versioning causes subtle bugs | Set version bump in a single helper `bump_version(state)`; replace all `state.__dict__[...] = ...` writes with a wrapped helper that bumps. Add a debug-only check that the cache is invalidated when a known-mutating method is called. |
| Engine purity test (no I/O) | No I/O introduced; verified by `tests/test_engine_purity.py`. |
| OpenSpiel clone semantics | `PyrantsState.__deepcopy__` already deep-copies `_engine`; the engine-level cache will be cloned with the state (clone_fast). Cache invalidation on the new state will be correct as long as we bump on writes to *either* parent or child. |

## Files to change

- `engine/helpers.py` — `_apply_effect_with_wrappers`, `_legal_main_phase_actions` (via new internal helper or inline), `_remaining_special_stack_count` (add cache).
- `engine/rules.py` — call sites that need `mutate=True` (if point 2 is done).
- `engine/state.py` — version field, bump helper, cache fields, COW accessors.
- `engine/generic_runtime/_resolve.py` — `_resolve_generic_execution` skip COW path.
- `openspiel_pyrants/state.py` — use engine-level cache; fall back to local cache if engine cache not present.
- `tests/conftest.py` (or new file) — strict-mode fixture.

## Out of scope

- Replacing Pydantic models with dataclasses or attrs (too invasive).
- Cython/Rust extensions.
- `validate_python` elimination (too risky).
- Parallel MCTS rollouts.
