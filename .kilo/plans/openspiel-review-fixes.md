# Plan: Fix Findings from Local Review of OpenSpiel Wrapper

## Goal

Address the 4 WARNING findings from the local code review of the `python_pyrants` OpenSpiel wrapper. Per the OpenSpiel skill, information leakage through the chance action id is the most important issue (it defeats the `IMPERFECT_INFORMATION` model). Performance and duplication are secondary.

## Findings Recap

| # | Severity | File | Issue |
|---|----------|------|-------|
| 1 | WARNING | `openspiel_pyrants/state.py:59` | Shuffle seed exposed via `_action_to_string`; in EXPLICIT_STOCHASTIC mode the public history reveals both players' hidden hands. |
| 2 | WARNING | `openspiel_pyrants/action_encoding.py:39-57` | `enumerate_legal_actions`, `action_to_move`, `move_to_action_id` each independently call `get_legal_moves` + sort by `model_dump_json`. 2–3× work per node visit. |
| 3 | WARNING | `openspiel_pyrants/chance.py:13` vs `state.py:44` | `chance.py` exports `apply_chance_seed` that is never called; logic inlined in `state.py`. Dead code + drift risk. |
| 4 | WARNING | `engine/state.py:457` vs `engine/helpers.py:507` | `Random((seed << 16) ^ counter)` duplicated in `_shuffle_deck` and `_reshuffle_discard_into_deck`. |

## Fix Order

### Fix 1 — Decouple chance action id from shuffle seed (highest impact)

**Per skill `wrapping-existing-engines.md` §"Hidden information"**: the public action history must not leak hidden information. The chance outcome id is recorded in the history; if it equals the seed, the seed is leaked.

**Approach: indirect mapping.** Keep the wrapper's `chance_outcomes` returning `0..N-1` as before (unchanged API, `_legal_actions` at the chance node stays the same), but apply a one-way hash to translate the public action id to the internal seed. This way:
- The public history records the public action id (e.g., `7`).
- The actual shuffle seed passed to `build_initial_game_state` is `hash(7)` (e.g., `4242`).
- An observer of the history cannot recover the seed without knowing the hash function.

**Implementation:**
- Add a private constant `_SEED_TABLE_OFFSET = 0x9E3779B9` and use a simple mixing function: `internal_seed = (public_id * 2654435761 + offset) % (2**31)` or just `internal_seed = public_id ^ (public_id << 13) ^ (public_id >> 7)` (xorshift mixing). This is fast and non-invertible in the sense that knowing the public id does not trivially reveal the seed, but the seed is still deterministic from the id (needed for reproducibility). A player reading the history can still try all 1000 seeds to find the right one, so this is a *defense in depth* measure, not a perfect fix — the real fix is the observer (deferred).
- In `PyrantsState._apply_action`, the chance branch computes `internal_seed = _public_to_seed(action)`, then passes it to `build_initial_game_state`.
- In `_action_to_string`, keep returning the public action id (what the history records), not the internal seed. Rename to `chance_outcome_id` for clarity.

This follows the skill's "deferred observer" path — the flag is set, the hash is a minimal guard, the full observer comes later.

**Test:** add a new test `test_seed_hashing_hides_seed` to `openspiel_pyrants/tests/test_action_encoding.py` asserting that `internal_seed != public_id` for a sample of action ids.

**Alternative considered:** per-player/per-deck private seeds (the security agent's second suggestion). Rejected for first pass: changes the engine refactor and is much more invasive. The xorshift approach preserves the plan's "one seed" design and is sufficient until the observer lands.

### Fix 2 — Cache the action mapping per node visit

**Per skill `game-implementation.md` §"Variant delta: chance events"** and the `wrapping-existing-engines.md` performance section.

**Approach:** compute the sorted move list + action map once per node visit, reuse across `enumerate_legal_actions` and `action_to_move`.

Two implementation options:

**Option A (minimal):** Add a private cache attribute on `PyrantsState` — `self._cached_moves = None`, `self._cached_action_to_move = None`, keyed on `id(self._engine)`. Reset on `_apply_action` (chance or decision).

**Option B (cleaner):** Refactor `action_encoding.py` to expose a single function that returns the full mapping, and cache it on the state. The state passes its cache to encode/decode.

I'll go with **Option A** — it's the smallest change. The cache is invalidated on every `_apply_action` so correctness is preserved (id(self._engine) changes when the engine is replaced via `model_copy(deep=True)`).

**Test:** existing round-trip tests still pass. Add a micro-benchmark note in the docstring acknowledging the cache exists.

### Fix 3 — Remove `chance.py` (dead code)

The duplication finding is correct: `chance.py` is never imported. The inline logic in `state.py:44-52` is 6 lines and self-contained. Per the skill's "death by deletion" guidance, just remove the file.

**Implementation:** delete `openspiel_pyrants/chance.py`. No other code changes needed (the plan's Step 5 file listing mentioned it but the actual logic is inline in `state.py`).

### Fix 4 — Deduplicate shuffle seed derivation

Per the skill's "drift risk" note. The fix is small: have `_reshuffle_discard_into_deck` call `_shuffle_deck`.

**Current state:**
- `engine/state.py:457` (new): `_shuffle_deck(deck, seed, counter)` returns a shuffled list
- `engine/helpers.py:507` (existing): `_reshuffle_discard_into_deck(state, player_id)` mutates state in-place, uses `Random((seed << 16) ^ counter)`

**Fix:** import `_shuffle_deck` from `engine.state` into `engine.helpers`, replace the inline Random with a call.

```python
# engine/helpers.py
from engine.state import _shuffle_deck

def _reshuffle_discard_into_deck(state, player_id):
    player = state.players[player_id]
    state.shuffle_count += 1
    player.deck = _shuffle_deck(player.discard_pile, state.shuffle_seed, state.shuffle_count)
    player.discard_pile = []
```

Note: the increment of `shuffle_count` must happen *before* the call (so the counter passed to `_shuffle_deck` matches the new value, matching current behavior where `shuffle_count += 1` is between seed computation and shuffle).

**Verify:** run `tests/test_shuffle_determinism.py` and the full engine test suite to confirm no behavior change.

## Files Changed

| File | Change |
|------|--------|
| `openspiel_pyrants/state.py` | Add seed-hash function; use in `_apply_action` chance branch and `_action_to_string` |
| `openspiel_pyrants/action_encoding.py` | Add cache hint in docstring; state-side cache lives in `PyrantsState` |
| `openspiel_pyrants/tests/test_action_encoding.py` | Add `test_seed_hashing_hides_seed` |
| `openspiel_pyrants/chance.py` | **Delete** (dead code) |
| `engine/helpers.py` | Import `_shuffle_deck`; replace inline Random |

## Invariants Preserved

- `_legal_actions` at chance node still returns `list(range(shuffle_seed_count))` (public ids 0..N-1).
- `chance_outcomes()` unchanged.
- Same `shuffle_seed` → same internal seed → same deck order. Determinism preserved.
- All 30 existing engine tests still pass.
- All 10 existing openspiel tests still pass.

## What This Does NOT Fix

- The `serialize=True` path in `random_sim_test` (documented as deferred C++ interop).
- The `IMPERFECT_INFORMATION` observer (deferred per plan).
- The `_init_attrs` lazy-init re-reading from disk (only in serialization round-trip, not hot path).

## Validation Order

1. Apply Fix 4 first (simplest, isolated to engine).
2. Run `pytest -q` to confirm no engine regression.
3. Apply Fix 3 (delete dead file).
4. Apply Fix 2 (add cache).
5. Apply Fix 1 (seed hash).
6. Run `pytest openspiel_pyrants/tests/ -q` to confirm wrapper still works.
7. Run `just openspiel-smoke` for end-to-end check.
8. Re-run ruff.
