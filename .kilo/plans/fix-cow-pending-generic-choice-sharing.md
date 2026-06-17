# Fix `pending_generic_choice` Sharing in `_cow_clone()`

## Background

The COW optimization in `engine/state.py` introduced `_cow_clone()` (a
shallow clone) to replace eager `model_copy(deep=True)`. It shares most
mutable sub-objects by reference and relies on COW accessors
(`_cow_node`, `_cow_player`, `_cow_market_state`, `_cow_resource_pool`)
to deep-copy on first write.

**Bug:** `pending_generic_choice` was put in the `_shared` set
(`state.py:531`), so the clone and the parent share the same
`PendingGenericChoiceState` object. But the generic-card resolver
mutates that object in place at 21 sites across two files — most
prominently in `engine/generic_runtime/_resolve.py` and
`engine/generic_runtime/_actions.py`.

| File | Lines | Mutations |
|------|-------|-----------|
| `engine/generic_runtime/_resolve.py` | 71-73, 152-155, 164, 170, 186, 225-231, 240, 247, 249, 272 | `pending.awaiting_option = …`, `pending.selected_option_ids.append(…)`, `pending.current_actions = …`, `pending.next_action_index += 1`, `pending.remaining_repeats -= 1`, `pending.last_selection = dict(…)` |
| `engine/generic_runtime/_actions.py` | 243, 279 | `pending.action_counters[counter_key] = …` |

**Tellingly,** `_apply_generic_play_card` at `_actions.py:756` already
does `outer_pending = working.pending_generic_choice.model_copy(deep=True)`
because the original author knew `pgc` needed deep-copy semantics. The
other 21 sites were missed by the COW refactor.

## Why it isn't caught today

- `tests/test_engine_purity.py::test_cow_apply_does_not_mutate_source_state`
  only exercises `_apply_play_card` for gain_power/gain_influence
  effects (soldier/noble). These do not produce a `pending_generic_choice`.
- `tests/test_generic_interpreter.py` and friends exercise the resolver,
  but always with a fresh state per assertion. They never check the
  parent state's `pgc` is unchanged after `apply()`.
- The OpenSpiel wrapper replaces `self._engine` wholesale on each
  `_apply_action`, so the corrupted parent `_engine` becomes unreachable
  on the very next action — the bug is invisible during a forward walk
  but violates the documented purity contract
  (`apply(state, move) -> state'` never mutates input).

## Impact assessment

| Path | Risk |
|------|------|
| IS-MCTS forward walk (current `just ismcts-perf`) | None — `_engine` replaced wholesale; corrupted parent state is discarded. |
| Tree algorithms that branch from a held parent (CFR, exploitability, alpha-beta, custom evaluators probing `apply(state, move_i)` for several moves) | **Real** — sibling branches share the corrupted `pgc`. |
| Any caller that re-reads `state.pending_generic_choice` after `apply()` | **Real** — silent stale data. |
| `resample_from_infostate` | None — `determinize_opponent_hidden_zones` uses `model_copy(deep=True)`. |
| Engine purity contract | **Violated.** |

## Fix

**Approach:** Eager deep-copy of `pending_generic_choice` in
`_cow_clone()`. Rationale: the object is small (a handful of
string/None/bool/int fields and 3-5 short lists/dicts of strings),
and only present during generic-card resolution. Most `_cow_clone()`
calls (non-resolution moves) pay ~0 cost because `pgc` is `None`. A
lazy `_cow_pgc` accessor would be faster on the resolution hot path
but would require touching all 21 mutation sites — high invasiveness
for low impact. Start with eager deep-copy; optimize later if profile
shows it matters.

### Change 1 — `engine/state.py` `_cow_clone()`

1. Remove `"pending_generic_choice"` from the `_shared` set
   (line 531-532).
2. Add a dedicated branch (alongside the `"board"` branch) before the
   `elif key in _shared` check:

```python
elif key == "pending_generic_choice":
    # Must deep-copy: mutated in-place by the generic-card resolver
    # without a COW accessor. Adding a lazy accessor would require
    # touching 21 mutation sites in generic_runtime/_resolve.py and
    # _actions.py; eager copy is cheap (small object, None most of
    # the time).
    d[key] = value.model_copy(deep=True) if value is not None else None
```

3. Update the docstring to mention the exception (one-line note).

### Change 2 — Regression test in `tests/test_engine_purity.py`

Add a new test, `test_cow_does_not_mutate_pending_generic_choice`,
following the existing scenario-based pattern from
`tests/test_scenarios.py::test_reload_state_with_pending_generic_choice`
(line 234) which uses the Enchanter of Thay card to set up a
`pending_generic_choice` reliably.

The test must:
1. Build a `GameState` that produces a `pending_generic_choice` (use
   the Enchanter of Thay pattern from `test_scenarios.py:234`).
2. Snapshot `id(state.pending_generic_choice)` and
   `state.pending_generic_choice.model_copy(deep=True)`.
3. Pick a legal `ResolveGenericChoiceMove` from `legal_moves(state)`.
4. Call `updated = apply(state, choice_move)`.
5. Assert:
   - `id(state.pending_generic_choice) == snapshot_id` (identity preserved)
   - `state.pending_generic_choice == snapshot_pgc` (value preserved)
   - The state-level `state.pending_generic_choice` field was not
     replaced (same `id` as before).

The test harness should also verify the value-level preservation
catches the actual mutation — i.e. snapshot
`selected_option_ids` and `action_counters` separately, then check
they didn't change.

## Validation

- `just test` — full suite must remain green. The new test should
  FAIL on the pre-fix code (proving it actually catches the bug) and
  PASS after the fix.
- `ruff check engine/ openspiel_pyrants/ tests/` — no new warnings.
- Optional re-run of `just ismcts-perf` to confirm the tiny
  `model_copy` cost is in the noise (it is — the object is at most
  a few hundred bytes and the resolver is not the dominant
  bottleneck).

## Out of scope (deferred)

- Migrating `determinize_opponent_hidden_zones` to `_cow_clone()` for
  IS-MCTS world-sampling speedup. Separate task.
- Lazier `_cow_pending_generic_choice` accessor if eager copy shows up
  in profiles. Measure first.
- Auditing the 21 mutation sites for a migration to a lazy accessor.
  Would remove the double-copy in `_apply_generic_play_card:756`, but
  the win is marginal (the object is tiny).

## Files touched

| File | Change |
|------|--------|
| `engine/state.py` | Remove `pending_generic_choice` from `_shared`; add dedicated deep-copy branch in `_cow_clone()`; update docstring. |
| `tests/test_engine_purity.py` | Add `test_cow_does_not_mutate_pending_generic_choice`. |
