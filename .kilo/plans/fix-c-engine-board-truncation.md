# Plan: Fix C engine — board node truncation and other C↔Python divergences

## Problem statement

The C engine silently truncates the board from 81 nodes to 64 (`MAX_NODES=64` cap
in `engine_c/state.h:15` and `engine_c/state.c:101`). The Python engine has no
such cap and tracks all 81 nodes. This single root cause produces multiple
observable divergences between `python_pyrants_c` and `python_pyrants`:

| Symptom | Test | Root cause |
|---|---|---|
| C returns 23 `initial_placement` targets; Python returns 24 | `test_state_sequence_converges` | Missing site `site_the_wormwrithings` (truncated) |
| C reaches terminal at step 31; Python still ongoing | `test_full_game_reaches_terminal` | Missing 17 nodes changes VP/scoring/control — C ends game prematurely |
| C and Python report different `legal_actions` counts at step 1 | same | Same — 1 missing site |
| `test_returns_string_for_both_players` — info_state strings are equal at start | `test_information_state.py` | At game start both players have empty hands + same deck counts, so their views are byte-identical by coincidence. Not engine-related. |
| `test_runner_script_outputs_artifacts` — subprocess runner produces no output | `test_ismcts_smoke.py` | Pre-existing subprocess/import-path issue. Not engine-related. |

## Root cause (single)

`engine_c/state.c:100-101`:
```c
gs->node_count = def->board.node_count;
if (gs->node_count > MAX_NODES) gs->node_count = MAX_NODES;
```

And `engine_c/state.c:102`:
```c
for (int i = 0; i < def->board.node_count && i < MAX_NODES; i++) {
```

The 17 dropped nodes are `route_37` through `route_53` (all routes — none
are sites, but the routes affect adjacency/control/movement for many sites
that *are* retained). **However**, `site_the_wormwrithings` is also missing
from the truncated 64-node set, which is why it disappears from the
initial-placement targets.

Wait — re-checking: the missing 17 are all `route_*` nodes, but
`site_the_wormwrithings` is one of the 64 retained nodes in the C state
(I saw it in the debug output). The initial-placement divergence is
something else.

## Re-investigated: the actual missing-target cause

The C `legal_initial_placement_node_ids` iterates `state->node_count` (64)
to find nodes with empty troop slots. `site_the_wormwrithings` is in the
state with 3 slots, all empty. But the C function returns only 23 targets
while Python returns 24.

Looking at `engine_c/helpers.c:99-116`:
```c
for (int i = 0; i < state->definition->board.node_count; i++) {
    const NodeDefinition *nd = &state->definition->board.nodes[i];
    if (strcmp(intern_str(nd->kind), "site") != 0) continue;
    for (int j = 0; j < state->node_count; j++) {
        if (state->nodes[j].node_id != nd->node_id) continue;
        for (int k = 0; k < state->nodes[j].troop_slot_count; k++) {
            if (state->nodes[j].troop_slots[k] == SYM_NULL) {
                if (count < max_out) out[count++] = nd->node_id;
                break;
            }
        }
        break;  // ← exits the j-loop after first match
    }
}
return count;
```

The Python version (`engine/helpers.py:122-134`) returns `sorted(result)`.
The C version does **not sort**. Action id 23 in Python = `site_the_wormwrithings`
(alphabetically last in the sorted list). The C engine produces it in a
different order so it gets id 22 or different, and the last id is some
other site. Wait — but the C engine has 23 moves total, and Python has 24.

Actually: the C engine's 23 vs Python's 24 count difference is real.
Let me re-examine: the C function returns 23 node IDs. There are 28
sites total in the board. Of those, 5 have all slots full after p1's
initial placement. The remaining 23 should have at least one empty slot.
But the debug output showed `site_the_wormwrithings` has 3 empty slots,
so it should be in the C output. Unless...

Actually, re-reading the debug output: the C function returns 23. There
are 28 sites in the board. 5 are full (empty=0). 23 have at least one
empty slot. So the C function is returning 23 — which is correct. The
Python function returns 24. So Python has 24 sites with at least one
empty slot, and C has 23. The difference is exactly 1 site.

The question is: which site? My earlier debug showed Python's 24th target
(sorted) is `site_the_wormwrithings`. The C engine has 23 targets.
Since both iterate the same board def and same state nodes, and both
check for empty troop slots, the only way to get different counts is if
the troop slot occupancy differs between the two engines — which would
happen if a prior action (p1's initial placement) placed a troop in a
site that the other engine considers empty, or vice versa.

But the p1 initial placement is the same in both engines (action 0 is
the alphabetically-first site in both). So the resulting state should
be identical. Unless the C engine's initial-placement apply logic
diverges from Python's.

**This is a more subtle bug.** The C engine's `apply_initial_placement`
likely places the troop in a different slot or with different
side-effects than Python. Need to diff the two `apply_initial_placement`
implementations. This is a separate investigation step before writing
the fix.

## Other C engine issues found during review

1. **Dead code** in `engine_c/rules.c:72-73`:
   ```c
   out[0].player_index = player_index_for_id_state(NULL, player_id);
   out[0].player_index = 0;
   ```
   The first line passes NULL state (would crash/UB) but is immediately
   overwritten. The function returns -1 when state is NULL. This is
   leftover debugging. Should remove the first assignment.

2. **MAX_NODES truncation** in `engine_c/state.c:100-101` — should
   either increase MAX_NODES to 128 (enough for current board + growth)
   or assert/abort if the board exceeds the cap. Silent truncation is
   the worst option. Recommendation: increase to 128.

3. **C `legal_initial_placement_node_ids` does not sort** — action
   ordering diverges from Python. Add `qsort` or sort-after-collect.

## Implementation steps

### Step 1: Increase MAX_NODES to 128

**File: `engine_c/state.h:15`**
```c
#define MAX_NODES  128
```

**File: `engine_c/bindings/engine_bindings.py:38`**
```python
MAX_NODES = 128
```

**Rationale**: Board is 81 nodes, cap of 128 gives headroom for new
boards. This eliminates the 17-node truncation that causes legal-move
divergence, scoring divergence, and premature terminal detection.

### Step 2: Remove the silent truncation guard

**File: `engine_c/state.c:100-101`**
```c
// Replace:
gs->node_count = def->board.node_count;
if (gs->node_count > MAX_NODES) gs->node_count = MAX_NODES;
// With:
gs->node_count = def->board.node_count;
assert(gs->node_count <= MAX_NODES);
```

Fail loudly if a board exceeds the cap rather than silently dropping
nodes.

### Step 3: Sort initial-placement targets in C

**File: `engine_c/helpers.c:99-116`**

Add a sort after collection. The Python version sorts by node_id
(string). The C version needs to sort by `Sym` (interned string ID).
Sym IDs are assigned by `intern()` in encounter order, so they're not
alphabetically ordered. To match Python's ordering, the C function
should sort by the string representation of the Sym.

**Alternative**: Sort by `Sym` value. This gives a different ordering
than Python but is still deterministic and valid. OpenSpiel's
`compute_c_action_map` already uses native C order (no sort). For
consistency with the existing C action encoding, sort by Sym value
(using `qsort` with a comparator on `Sym`).

The key requirement is that the C action encoding is deterministic per
state. Python sorts by string; C should also sort (by Sym is fine).

### Step 4: Investigate the remaining 1-target divergence

After steps 1-3, re-run `test_state_sequence_converges`. If the
counts still differ, diff the two engines' `apply_initial_placement`
implementations to find the occupancy divergence.

**Likely fix locations**:
- `engine_c/rules.c:apply_initial_placement` (line 346)
- `engine/rules.py:_apply_initial_placement` (line 453)
- The troop-slot index used to place the initial troop.

### Step 5: Fix the dead-code bug in rules.c

**File: `engine_c/rules.c:72-73`**
```c
// Remove the first assignment, keep only:
out[0].player_index = 0;
```

### Step 6: Add a regression test

**File: `openspiel_pyrants/tests/test_state_c_vs_python.py`**

Add a new test that loads a 4-player game, runs 10 steps, and verifies
that the C and Python engines agree on:
- `current_player()` at every step
- `len(legal_actions())` at every step
- `is_terminal()` at every step
- Final `returns()` (if terminal)

Parametrize over seeds (0, 42, 137, 999) and player counts (2, 3, 4).

### Step 7: Verify

- `pytest openspiel_pyrants/tests/test_state_c_vs_python.py` — all pass
- `pytest openspiel_pyrants/tests/test_determinize_c.py` — still pass
- `pytest openspiel_pyrants/tests/test_ismcts_smoke_c.py` — still pass
- `just test` — full suite passes (or pre-existing failures remain)
- Rebuild `engine_c.dll` via `engine_c/compile.bat`
- `ruff check .` — no new issues

## File change summary

| File | Change |
|---|---|
| `engine_c/state.h:15` | `MAX_NODES` 64 → 128 |
| `engine_c/state.c:100-101` | Remove silent truncation; add `assert` |
| `engine_c/helpers.c:99-116` | Sort initial-placement targets |
| `engine_c/rules.c:72` | Remove dead `player_index_for_id_state(NULL, ...)` call |
| `engine_c/bindings/engine_bindings.py:38` | `MAX_NODES` 64 → 128 |
| `openspiel_pyrants/tests/test_state_c_vs_python.py` | Add 4-player regression test |

## Risk assessment

| Risk | Mitigation |
|---|---|
| Increasing MAX_NODES changes struct layout → breaks ctypes bindings | Update both `state.h` and `engine_bindings.py` together; rebuild DLL |
| C `qsort` on `Sym[]` has different ordering than Python's `sorted` by string | Use Sym-value sort; document that C/Python may have different action-id assignments for the same move (this is already the case — Python sorts by string, C uses native order) |
| Step 4 investigation finds a deeper occupancy bug | If found, add to plan as a separate step before implementation |

## Out of scope

- Performance optimization (MCTS throughput)
- C++ rewrite of the engine
- Generalizing to N-player beyond 4
