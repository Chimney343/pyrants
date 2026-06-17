# Plan: Fix IS-MCTS Determinization for C Engine Backend

## Problem

`PyrantsCState.resample_from_infostate()` returns `self.clone()` — identical world state
every time. IS-MCTS `sample_root_state()` calls this per simulation, expecting different
possible worlds consistent with the observing player's information set. Without
determinization, IS-MCTS degenerates into perfect-information MCTS on the current actual
state.

The Python backend does this correctly via `determinize_opponent_hidden_zones()`:
clone state → for each opponent: concatenate hand+deck+discard → Fisher-Yates shuffle
→ split back into hand/deck/discard preserving original counts.

## Approach: Python-side determinization via ctypes struct manipulation

Add `engine_determinize_opponent_hidden()` as a **C function** in engine_c. Reasons:
1. Performance — called once per IS-MCTS simulation (200× per decision × 4000 decisions =
   800K calls per game). Python ctypes field-by-field shuffle adds measurable overhead.
2. Reuse — C function can be called directly from `state_c.py` or from `c_adapter.py`.
3. Correctness — C-level Sym arrays avoid Python↔C marshalling bugs.
4. The C engine already has `rng_shuffle`, `rng_seed`, and `PlayerState` array access.

### Alternative considered: Python-only ctypes manipulation

Read `PlayerState.hand[0..hand_count-1]` + `deck[0..deck_count-1]` + `discard_pile[...]`
as Python lists via `_sym_str()`, shuffle in Python, write back via `intern()` + array
assignment. Rejected because:
- 800K calls × Python↔C marshalling overhead is significant
- Fragile: depends on `MAX_ZONE_SIZE` array layout matching struct padding
- `intern()` round-trip for each Sym is expensive (hash table lookup per card)

## Implementation steps

### Step 1: Add `engine_determinize` C function

**File: `engine_c/state.c`** (or new `engine_c/determinize.c`)

```c
// Shuffle opponent hidden zones (hand, deck, discard_pile) for one observing player.
// Returns a cloned GameState* with opponent zones reshuffled using the provided seed.
// The observing player's zones are preserved exactly.
GameState *engine_determinize(
    const GameState *src,       // source state (not mutated)
    Sym observing_player_id,   // Sym for the observing player
    uint64_t seed              // RNG seed for this determinization
);
```

Implementation:
1. Call `engine_clone(src)` to get a fresh copy
2. Seed an RNG with `seed`
3. For each player in `clone->player_ids`:
   - If player_id == observing_player_id: skip
   - Concatenate: `hidden = hand + deck + discard_pile` (Sym arrays, using counts)
   - `rng_shuffle(&rng, hidden, total_count)`
   - Split back: hand[:hand_count], deck[:deck_count], discard_pile[:discard_count]
4. Return the cloned+shuffled state

Note: `hand`, `deck`, `discard_pile` are `Sym[MAX_ZONE_SIZE]` fixed arrays in
`PlayerState`. The shuffle operates on a temporary buffer, then `memcpy` back.

### Step 2: Export in `engine_c.def`

Add `engine_determinize` to the EXPORTS list.

### Step 3: Add ctypes binding

**File: `engine_c/bindings/engine_bindings.py`**

Add to `_setup()`:
```python
_lib.engine_determinize.argtypes = [
    POINTER(GameStateStruct),  # src
    Sym,                       # observing_player_id
    c_uint64,                  # seed
]
_lib.engine_determinize.restype = POINTER(GameStateStruct)
```

### Step 4: Add `CEngine.determinize` and `CEngineAdapter.determinize`

**File: `engine_c/bindings/ce_api.py`** — add to `CEngine`:
```python
def determinize(self, state: CState, observing_player_id: Sym, seed: int) -> CState:
    """Return a cloned state with opponent hidden zones reshuffled."""
    obs_sym = _lib.intern(observing_player_id.encode())
    result = _lib.engine_determinize(state.ptr, obs_sym, seed)
    if not result:
        return None
    return CState(result)
```

**File: `engine_c/bindings/c_adapter.py`** — add to `CEngineAdapter`:
```python
def determinize(self, observing_player_id: str, seed: int) -> CEngineAdapter:
    """Return a new adapter with opponent hidden zones reshuffled."""
    new_state = self._engine.determinize(self._state, observing_player_id, seed)
    if new_state is None:
        return self.clone_via_replay(self._move_log)  # fallback
    self._engine.destroy(self._state)
    return CEngineAdapter(new_state, self._engine, self._player_ids, self._shuffle_seed)
```

Wait — `determinize` already clones internally. So `c_adapter.determinize` should NOT
destroy `self._state` (we want the original untouched). Instead:

```python
def determinize(self, observing_player_id: str, seed: int) -> CEngineAdapter:
    new_state = self._engine.determinize(self._state, observing_player_id, seed)
    if new_state is None:
        return self.clone_via_replay(self._move_log)
    return CEngineAdapter(new_state, self._engine, self._player_ids, self._shuffle_seed)
```

The original `self._state` stays alive. The new adapter owns the determinized state.

### Step 5: Fix `PyrantsCState.resample_from_infostate`

**File: `openspiel_pyrants/state_c.py`** line 284-287:

```python
def resample_from_infostate(self, player, rng):
    if self._adapter is None:
        return self

    player_id = self._game.get_player_ids()[player]

    # Generate a seed from the IS-MCTS-provided RNG
    if hasattr(rng, 'shuffle'):
        seed = rng.randint(0, 2**63 - 1)
    elif callable(rng):
        seed = int(rng() * 2**63)
    else:
        seed = 0

    determinized_adapter = self._adapter.determinize(player_id, seed)

    new = PyrantsCState.__new__(PyrantsCState)
    pyspiel.State.__init__(new, self._game)
    new._game = self._game
    new._pending_initial_chance = False
    new._cached_indexed_moves = None
    new._shuffle_seed = self._shuffle_seed
    new._move_log = list(self._move_log)
    new._history_actions = list(self._history_actions)
    new._adapter = determinized_adapter
    return new
```

Key detail: IS-MCTS passes a `pyspiel.UniformProbabilitySampler(rng)` or
`numpy.random.RandomState` as `rng`. We use it to generate a seed for the C RNG,
keeping the determinization seeded by the same RNG that IS-MCTS uses.

### Step 6: Update `c_adapter.private_view_json` (verify, likely no change needed)

The private view already includes the observing player's hand and opponent counts.
After determinization, the opponent's hand/deck/discard have different card identities
but same counts. The private view for the observing player is unchanged (correct).
The private view for an opponent now shows the reshuffled hand — but IS-MCTS only
queries the info state for the current player, so this is fine.

### Step 7: Verify info-state key stability

ISMCTS asserts `root_infostate_key == self.get_state_key(sampled_root_state)`.
After determinization:
- `history_str()` unchanged (same action history)
- `private_view_json(observing_player)` unchanged (observing player's zones preserved)
- Therefore info-state key matches. ✓

### Step 8: Add test

**File: `openspiel_pyrants/tests/test_determinize_c.py`**

```python
def test_determinize_preserves_observing_player():
    """Obs player's hand/deck/discard unchanged after determinization."""
    game = pyspiel.load_game("python_pyrants_c", {"num_players": "2"})
    state = game.new_initial_state()
    state.apply_action(42)

    obs_player_id = game.get_player_ids()[0]
    obs_hand_before = state._adapter.private_view_json(obs_player_id)

    det = state._adapter.determinize(obs_player_id, seed=12345)
    obs_hand_after = det.private_view_json(obs_player_id)

    assert obs_hand_before == obs_hand_after

def test_determinize_changes_opponent_hidden():
    """Opponent hidden zones differ across determinization seeds."""
    game = pyspiel.load_game("python_pyrants_c", {"num_players": "2"})
    state = game.new_initial_state()
    state.apply_action(42)

    opp_player_id = game.get_player_ids()[1]
    det1 = state._adapter.determinize(game.get_player_ids()[0], seed=100)
    det2 = state._adapter.determinize(game.get_player_ids()[0], seed=200)

    pv1 = det1.private_view_json(opp_player_id)
    pv2 = det2.private_view_json(opp_player_id)
    # Different seeds should produce different opponent hands (probabilistically)
    assert pv1 != pv2  # very likely with different seeds

def test_resample_from_infostate_matches_key():
    """ISMCTS assertion: resampled state has same infostate key as root."""
    game = pyspiel.load_game("python_pyrants_c", {"num_players": "2"})
    state = game.new_initial_state()
    state.apply_action(42)
    # Advance a few moves to get past setup
    for _ in range(5):
        cp = state.current_player()
        legal = state.legal_actions()
        state.apply_action(legal[0])

    rng = np.random.RandomState(99)
    resampled = state.resample_from_infostate(state.current_player(), rng)

    key_orig = state.information_state_string(state.current_player())
    key_resampled = resampled.information_state_string(state.current_player())
    assert key_orig == key_resampled

def test_ismcts_smoke_with_determinization():
    """Existing smoke test should still pass — regression check."""
    # This is already covered by test_ismcts_smoke_c.py but worth re-running
```

### Step 9: Update existing ISMCTS smoke test

No changes needed — existing test should pass with new determinization. The test
runs low-sims (5) which means `max_world_samples=100` — ISMCTS will call
`resample_from_infostate` 5 times. With the fix, each call produces a different
determinization.

## Risk assessment

| Risk | Mitigation |
|------|-----------|
| C `engine_determinize` bug corrupts state | Returns new clone, never mutates source; test with known seed |
| Shuffle produces same order (seed collision) | Different IS-MCTS sim iterations get different seeds from RNG |
| `intern()` lookup fails for player_id | Player IDs are always pre-interned during `engine_create_game` |
| Info-state key mismatch after determinization | Verified: history + observing player view unchanged |
| Memory leak if determinized state not destroyed | `PyrantsCState.__del__` calls `adapter.destroy()` |
| Performance: clone + shuffle cost | `engine_clone` is ~10μs memcpy; shuffle is O(zone_size) ~O(80); total ~20μs per call — negligible vs IS-MCTS simulation cost |

## File change summary

| File | Change |
|------|--------|
| `engine_c/state.c` | Add `engine_determinize()` C function |
| `engine_c/engine_c.def` | Add `engine_determinize` to EXPORTS |
| `engine_c/bindings/engine_bindings.py` | Add ctypes signature for `engine_determinize` |
| `engine_c/bindings/ce_api.py` | Add `CEngine.determinize()` method |
| `engine_c/bindings/c_adapter.py` | Add `CEngineAdapter.determinize()` method |
| `openspiel_pyrants/state_c.py` | Fix `resample_from_infostate` to call determinize |
| `openspiel_pyrants/tests/test_determinize_c.py` | New test file |

## Out of scope

- Partial determinization (only top-of-deck): future optimization
- Verifying `engine_clone` deep-copies all hidden arrays: separate concern
- `max_game_length` / `num_distinct_actions` validation: separate concern
