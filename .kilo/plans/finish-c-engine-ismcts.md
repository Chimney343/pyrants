# Plan: Finish C-Engine Implementation & Make IS-MCTS Work

## Goal

Make `just ismcts-c` complete a 4-game run (or at least, complete a 1-game run) with the C engine, instead of crashing on every `play_card` move. Fix the root cause that prevents the C engine from playing cards through IS-MCTS, then verify behavioral parity against the Python engine on the same action sequences.

## Background — What's Actually Broken

The C engine DLL works for the setup phase (`initial_placement`) and most non-`play_card` moves (assassinate, deploy, recruit, end_main_phase). It fails on `play_card` moves with `engine_apply` returning NULL. The xfail comment in `test_ismcts_smoke_c.py` blames "card effect runtime incomplete" — this is **misleading**. The actual root cause is a **move-struct bug**: the C `Move` struct for `play_card` has only `card_id`, not `hand_index`. `apply_play_card` reads `ps->hand[hand_index]` where `hand_index` defaults to 0, then checks `played == card_id`. If the chosen card is not the first in hand, the engine rejects the move.

### Why IS-MCTS always crashes

IS-MCTS picks a random `chosen` from the policy and calls `state.apply_action(chosen)`. `chosen` is an integer index into the sorted action map. The first play_card in the sorted action map could be any hand card. In `apply_play_card`, `ps->hand[0]` may not equal the chosen card → returns NULL → Python wrapper raises `RuntimeError` → all games fail.

The "20-move smoke test" works because it always picks `legal_actions[0]`, which is the first play_card sorted by `str(sorted(data.items()))`. With the default data dict `{"card_id": "..."}`, the sort key reduces to the card_id, and the IS-MCTS test picks `legal[0]` which is the alphabetically-first hand card. If that card happens to be `ps->hand[0]`, it works. But IS-MCTS rolls out with random actions, so it picks non-zero indices and the move fails.

### Cross-validation evidence

The Python engine uses a Move struct that includes `hand_index`:
```python
# engine/moves.py
class PlayCardMove(BaseModel):
    card_id: str
    hand_index: int
```

The Python `_move_sort_key` includes `(mt, move.card_id, move.hand_index)`. The C struct omitted `hand_index` during translation, breaking the bijection for hands with 2+ copies of a card.

### Other gaps identified

1. **`engine_legal_moves` for `play_card`**: one move per hand card but no `hand_index` field. If two copies of "noble" are in hand, both moves are identical (same `card_id`) and `CMoveWrapper._extract_data` returns identical dicts. Stable sort keeps enumeration order, but `apply_play_card` only checks `hand[0]`, so only the first can ever be applied.
2. **`public_view` struct mismatch**: `engine_public_view` writes 81 nodes but the Python struct only has space for 64 (`MAX_NODES=64`). The OpenSpiel wrapper now sidesteps this by reading CState properties directly (see `c_adapter.py:_build_public_dict`), so the broken C function is not called. This is a known workaround, not a fix.
3. **Clone-via-replay hot spot**: `resample_from_infostate` takes 0.55s for 1 call (~47% of total profile time). Each clone does `CEngine.create_game` (full setup) + replay moves. For IS-MCTS, this is called once per simulation. A real fix would use `engine_clone_cow` (already exposed) or fix the cloner.
4. **IS-MCTS runner hardcoded to Python engine**: `state._engine` access pattern only works for `PyrantsState`. I added a compatibility shim (`_EngineShim` in `state_c.py`) and dispatch helpers in `run_ismcts.py` to handle both backends.
5. **Module import overhead**: `import openspiel_pyrants` loads both Python and C backends, costing 0.5s+ of module imports. The Python backend's Pydantic chain is the biggest contributor.

## Architecture

No new components. The fix is small and surgical.

### Decision: Fix at the C engine level, not the wrapper

The wrapper is correct (it faithfully delegates to C). Fixing this in the wrapper (e.g., by searching the hand for the card) would mask the C engine bug and create drift. The plan is to add `hand_index` to the C `Move` struct and make `apply_play_card` use it.

The `Move` struct is a public C API consumed by `engine_bindings.py`. Adding a field changes the struct layout. Need to verify no other C code depends on the exact size, then rebuild `engine_c.dll`.

## Phases

### Phase 1: Fix C `Move` struct to include `hand_index` (C-side)

**File:** `engine_c/state.h`
- Add `int hand_index;` to the `play_card` member of the `Move` union.

**File:** `engine_c/rules.c`
- In `apply_play_card` (line ~266), pass `hand_index` through to the function and use it as the hand slot index instead of hardcoded 0.
- In `legal_moves` (line ~222-227), set `out[w].data.play_card.hand_index = i` (the hand index being iterated).
- Verify the `Move` struct rebuild doesn't break any other call sites by rebuilding and running the existing C test suite.

**Rebuild DLL:**
- `just build-c`

**Verify:**
- `python -m pytest tests/test_engine_c.py -v` — should still pass.
- New test: in `tests/test_engine_c.py`, add a test that plays a card from hand[1] (not hand[0]) to confirm the fix works.

### Phase 2: Update C `Move` Python binding for `hand_index`

**File:** `engine_c/bindings/engine_bindings.py`
- The ctypes `MoveData` union's `play_card` struct needs to be updated to match the new C layout. Currently:
  ```python
  ("play_card", type("_pc", (Structure,), {"_fields_": [("card_id", Sym)]})),
  ```
  Add `("hand_index", c_int)` field.

**File:** `engine_c/bindings/ce_api.py`
- In `CMoveWrapper._extract_data` (line ~84), include `hand_index` in the play_card data dict:
  ```python
  if mt == "play_card":
      return {
          "card_id": _sym_str(m.data.play_card.card_id),
          "hand_index": m.data.play_card.hand_index,
      }
  ```
- Add `__slots__` entry for `_c_move` already includes it; no change needed.

**File:** `openspiel_pyrants/action_encoding_c.py`
- Remove the docstring claim that play_card lacks hand_index. The sort key now includes hand_index, so duplicate cards sort distinctly.

**Verify:**
- `python -m pytest openspiel_pyrants/tests/test_pyrants_c_register.py openspiel_pyrants/tests/test_state_c_vs_python.py openspiel_pyrants/tests/test_resample_c.py -v` — should still pass.
- `python -m pytest openspiel_pyrants/tests/test_ismcts_smoke_c.py -v` — should start passing (remove `xfail` marker and `strict=True`).

### Phase 3: Update xfail annotations in IS-MCTS smoke test

**File:** `openspiel_pyrants/tests/test_ismcts_smoke_c.py`
- Remove `@pytest.mark.xfail` and `strict=True` decorators from `test_one_game_low_sims`.
- Update the long-reason comment to reflect that the C engine is now complete and the tests are expected to pass.
- If the test still fails for other reasons (e.g., other move types), update the xfail with the new specific reason. Otherwise remove the marker entirely.

### Phase 4: Behavioral parity verification (cross-validation)

**Goal:** Run C engine and Python engine through identical action sequences, verify outputs match.

**Existing tests:**
- `tests/test_engine_c.py` — cross-validates C engine vs Python engine at the `engine_*` C API level (9 tests). Must continue to pass.
- `openspiel_pyrants/tests/test_state_c_vs_python.py` — cross-validates at the OpenSpiel State level (16 tests). Must continue to pass.
- `openspiel_pyrants/tests/test_ismcts_smoke_c.py` — IS-MCTS completes a game (1-2 sims).

**New test:** Add a parity test in `tests/test_engine_c.py` or `openspiel_pyrants/tests/` that:
- Loads both engines with same seed.
- Runs a 20-move action sequence (covering: initial_placement, end_main_phase, play_card, deploy, assassinate, end_of_turn, cleanup).
- Asserts `current_player_id`, `phase`, `round_number`, `player_score` match at every step.

### Phase 5: Optional perf improvements (defer if time-bound)

If time permits, address the `resample_from_infostate` 0.55s bottleneck:
- Use `engine_clone_cow` (already exposed in C bindings) instead of `clone_via_replay`. This avoids the full `create_game` + replay overhead.
- Trade-off: the existing `engine_clone_cow` does a full `memcpy` of the struct (~15KB) plus separate arena for pending fields. For IS-MCTS depths ~50 moves, replay is also fine. Profile both approaches.

Other optional optimizations:
- `compute_c_action_map` re-enumerates moves on every call. Add a version-keyed cache on `PyrantsCState` (the plan's `_cached_indexed_moves` already does this).
- `information_state_string` builds a 4.5ms JSON per call. For deep IS-MCTS, batch the calls or cache the result.
- Module import overhead (~0.5s): split `openspiel_pyrants` so Python-only import doesn't trigger C engine load. This is invasive — defer.

## Risks

| Risk | Mitigation |
|------|-----------|
| `Move` struct layout change breaks other C call sites | Run existing C test suite (`tests/test_engine_c.py`) after rebuild; if green, struct change is safe. |
| `engine_clone_cow` may have its own bugs (corruption, arena ownership) | Keep clone-via-replay as default; clone_cow is an opt-in perf win. |
| IS-MCTS tests become flaky on first run due to random playouts | Already have `seed=42` determinism; IS-MCTS uses `RandomRolloutEvaluator(1)` which is deterministic per seed. |
| `hand_index` field changes the size of `Move` struct and breaks `engine_create_game` callers | Only `engine_apply` and `engine_legal_moves` consume Move; both are updated. |
| Cross-engine parity test fails on subtle differences (e.g., RNG ordering, symmetry) | Use a small fixed action sequence (10-20 moves) to avoid RNG divergence. For longer tests, add a `--seed` parameter to the test and accept minor differences. |

## Files to Modify

| File | Change |
|------|--------|
| `engine_c/state.h` | Add `hand_index` field to `Move.play_card` union member |
| `engine_c/rules.c` | Set `hand_index` in legal_moves, use it in apply_play_card |
| `engine_c/bindings/engine_bindings.py` | Update ctypes `MoveData` play_card struct to add `hand_index` |
| `engine_c/bindings/ce_api.py` | Include `hand_index` in `CMoveWrapper._extract_data` for play_card |
| `openspiel_pyrants/action_encoding_c.py` | Update docstring to reflect hand_index in sort key |
| `openspiel_pyrants/tests/test_ismcts_smoke_c.py` | Remove or update xfail marker |
| `tests/test_engine_c.py` | (optional) Add a 20-move parity test |

## Acceptance Criteria

- [ ] `python -m pytest tests/test_engine_c.py -v` — all 9 (or 10) tests pass
- [ ] `python -m pytest openspiel_pyrants/tests/test_pyrants_c_register.py openspiel_pyrants/tests/test_state_c_vs_python.py openspiel_pyrants/tests/test_resample_c.py -v` — all 35 tests pass
- [ ] `python -m pytest openspiel_pyrants/tests/test_ismcts_smoke_c.py -v` — all 3 tests pass (no xfail)
- [ ] `just ismcts-c-quick` — completes without crashing
- [ ] `just ismcts-c` — at least 1 of 4 games completes successfully
- [ ] `just ismcts-c-perf` — completes and produces profile stats (perf improvement on resample_from_infostate would be a bonus)
- [ ] No regressions in the 507 existing tests
- [ ] `ruff check .` (if available) — no new warnings
