# Optimize Special Recruit Stack Counting

## Problem

`_remaining_special_stack_count` in `engine/helpers.py:220` is a hotspot:
- **973K calls**, 2.8s tottime, 6.1s cumtime
- Called 3 times per legal move computation (once per special stack: house_guard, priestess_of_lolth, insane_outcast)
- Each call does 6 `.count()` operations per player on lists (deck, hand, discard_pile, played_cards, inner_circle, trophy_hall)
- `list.count` is O(n), and with 2 players × 6 lists × 3 stacks = 36 `.count()` calls per legal move computation

## Root Cause

The function is called from `_legal_main_phase_actions` in `engine/rules.py:376-386`:
```python
for market_slot, card_id, stack_total, requires_aberrations in SPECIAL_RECRUIT_STACKS:
    if requires_aberrations and not _is_aberrations_enabled(state):
        continue
    if _remaining_special_stack_count(state, card_id, stack_total) <= 0:
        continue
    ...
```

Each iteration independently computes card counts by scanning all player collections.

## Solution

**Batch the computation**: Compute card counts once for all 3 special stacks in a single pass, then look up results.

### Implementation

1. **Add a new function** `_compute_special_stack_counts(state) -> dict[str, int]` in `engine/helpers.py`:
   - Scans market.deck and market.row once
   - Scans each player's collections once
   - Returns a dict mapping `card_id -> remaining_count` for all 3 special stacks

2. **Modify `_legal_main_phase_actions`** in `engine/rules.py`:
   - Call `_compute_special_stack_counts(state)` once before the loop
   - Look up results from the dict instead of calling `_remaining_special_stack_count` per stack

3. **Keep `_remaining_special_stack_count`** for the apply path (`_apply_recruit` in helpers.py:508) where it's called once per recruit action.

### Expected Impact

- Reduce 36 `.count()` calls per legal move to ~12 (one pass through all collections)
- Estimated 3x speedup for this specific hotspot: ~2s saved per 10 sims
- No behavioral change — pure optimization

## Files to Modify

1. `engine/helpers.py`:
   - Add `_compute_special_stack_counts(state) -> dict[str, int]`

2. `engine/rules.py`:
   - Import `_compute_special_stack_counts`
   - Modify `_legal_main_phase_actions` to use batched computation

## Verification

1. Run `just test` to ensure no regressions
2. Run `just ismcts-perf` and compare:
   - `_remaining_special_stack_count` calls should drop from 973K to ~325K (1/3)
   - `list.count` calls should drop from 13.6M to ~4.5M (1/3)
   - Total time should improve by ~2-4s
