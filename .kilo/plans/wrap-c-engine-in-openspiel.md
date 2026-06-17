# Plan: Wrap C Engine in OpenSpiel (PyrantsState v2)

## Goal

Replicate the existing OpenSpiel wrapper (`openspiel_pyrants/state.py`, `action_encoding.py`, etc.) so it uses the pure-C `engine_c.dll` instead of the Pydantic-based Python engine. Two engine backends, one `pyspiel.State` interface, selected at game construction via a `load_params` flag.

The `python_pyrants` registration stays (OpenSpiel requires the name match `class::SN` in `GameType.short_name` — that's a hard OpenSpiel constraint, not a typo), but a second registration `python_pyrants_c` is added for the C-backend game.

## Classify the game (per skill rules)

- **Dynamics**: sequential — turn-based with phases.
- **Chance**: explicit stochastic — one initial shuffle-seed chance node, then deterministic.
- **Information**: imperfect — hidden hands, decks, discards.
- **Utility**: zero-sum (2 players) / general-sum (3–4 players).

This dictates:
- `Dynamics.SEQUENTIAL`, `ChanceMode.EXPLICIT_STOCHASTIC`, `Information.IMPERFECT_INFORMATION`
- `Utility.ZERO_SUM` or `Utility.GENERAL_SUM` (already set)
- One chance node, then `current_player()` returns the player id
- `_legal_actions` must be non-empty at every decision node and never called at terminal
- `returns()` sums to 0 for 2-player zero-sum; raw scores for 3–4 player general-sum
- `chance_outcomes()` probabilities sum to 1
- `max_game_length=4096` (counts decision nodes, not chance — unchanged)

## Four wrappability properties (per skill rules)

The C engine already has all four (verified in Phases 0–4):
- ✅ **Extractable randomness** — single chance node at game start selects shuffle seed
- ✅ **Cheap cloning** — `engine_clone_cow` is O(state size), used by `__deepcopy__`
- ✅ **Integer action mapping** — `action_encoding.compute_action_map` already handles this
- ✅ **Pure rules core** — no I/O, COW accessors, `engine_apply` is deterministic given the state

**Hidden-information caveat (from skill rules)**: C engine state is opaque to OpenSpiel. For `information_state_string` and `resample_from_infostate`, we still need Python-side views into the C state. The C engine already provides `engine_public_view` / `engine_private_view` (Phase 3), so we can call them on a clone and serialize the result. **This is the key insight: the information_state doesn't need to be derived from Python state — it can be derived from a C state clone.**

## Architecture

### Decision: single adapter class, backend selected at construction

A new `PyrantsCState(pyspiel.State)` mirrors `PyrantsState` but holds a C state pointer (`CState` wrapper) and delegates to `engine_c.dll`. The two backends are independent classes because the C state is held in ctypes memory and can't be combined with the Pydantic `GameState` — having one class dispatch on every method is slower and buggier than two clean classes.

**Trade-off**: some code duplication. **Benefit**: each class is straightforward, no per-call dispatch overhead, and the Python class can stay untouched as a reference implementation.

```
openspiel_pyrants/
├── state.py           # PyrantsState (Python engine) — UNCHANGED
├── state_c.py         # PyrantsCState (C engine) — NEW
├── action_encoding.py # Pyrants engine action encoding — UNCHANGED
├── action_encoding_c.py # C engine action encoding — NEW (uses CMoveWrapper)
├── game.py            # PyrantsGame (python_pyrants) — UNCHANGED
├── game_c.py          # PyrantsCGame (python_pyrants_c) — NEW
├── determinization.py # Python engine determinization — UNCHANGED
├── determinization_c.py # C engine determinization — NEW
├── observer.py        # PyrantsObserver — UNCHANGED
├── observer_c.py      # PyrantsCObserver — NEW
└── __init__.py        # Register BOTH games — UPDATED
```

### C-side state wrapper

A new class `CEngineAdapter` in `engine_c/bindings/c_adapter.py` wraps a C `GameState*` and exposes the methods the OpenSpiel wrapper needs:

```python
class CEngineAdapter:
    def __init__(self, c_state: CState, c_engine: CEngine):
        self._state = c_state
        self._engine = c_engine

    def clone(self) -> 'CEngineAdapter': ...
    def destroy(self) -> None: ...
    def legal_moves(self) -> list[CMoveWrapper]: ...
    def apply(self, move: CMoveWrapper) -> 'CEngineAdapter': ...
    def is_terminal(self) -> bool: ...
    def is_setup_done(self) -> bool: ...  # check if past chance node
    def phase(self) -> str: ...
    def current_player_id(self) -> str: ...
    def round_number(self) -> int: ...
    def player_score(self, index: int) -> int: ...
    def final_scores(self) -> dict[str, int]: ...
    def private_view_json(self, player_id: str) -> str: ...  # for info state
    def public_view_data(self) -> dict: ...
```

**Critical design choice**: `clone()` allocates a fresh C state via `engine_create_game_definition` with the same seed, then replays the move history. **This avoids deep-copying the C state.** The replay is O(move_count) which is fine for IS-MCTS depths (typically <50 moves).

**Alternative considered**: shallow-copy the ctypes pointer. Rejected because the C state has its own arena; sharing the arena across "clones" would corrupt state. Also, the C engine's `engine_clone_cow` does a deep memcpy of the struct plus separate arena for pending_ability/pending_generic, so it would be more expensive than replay.

**Another alternative**: serialize state to JSON, parse JSON back. Rejected: ~5ms per state on this machine, ~10x slower than replay.

### Action encoding for the C backend

`action_encoding_c.py` follows the same pattern as the Python version but sorts `CMoveWrapper` objects by their `data` dict (stringified) instead of Pydantic model fields:

```python
def _c_move_sort_key(m: CMoveWrapper) -> tuple:
    return (m.move_type, str(sorted(m.data.items())))

def compute_c_action_map(state: CState) -> list[tuple[int, CMoveWrapper]]:
    moves = CEngine.legal_moves(state)
    return sorted(enumerate(moves), key=lambda item: _c_move_sort_key(item[1]))
```

The `NUM_DISTINCT_ACTIONS = 1024` upper bound is unchanged.

### PyrantsCState methods

Following the skill's "key invariants" checklist:

- **`current_player()`**:
  - `TERMINAL` if `_engine.is_terminal()`
  - `CHANCE` if `_pending_initial_chance`
  - else `_player_index(self._engine.current_player_id)`

- **`_legal_actions(player)`**:
  - If chance: `range(shuffle_seed_count)`
  - Else: cached `compute_c_action_map(self._state)` → `range(len(...))`
  - ✅ Sorted, non-empty at every non-terminal decision node (rely on C engine's `engine_legal_moves` to satisfy this)

- **`_apply_action(action)`**:
  - If chance: seed = `_public_to_seed(action)`, create new C state
  - Else: `move = indexed[action]`, `new_state = CEngine.apply(self._state, move)`, swap

- **`is_terminal()`**: `_engine.is_terminal()`

- **`returns()`**:
  - If terminal: call `engine.compute_final_scores(self._state)`, return zero-sum diff (2p) or raw scores (3-4p)
  - Else: use `_engine.player_score(i)` for each player
  - ✅ Sums to 0 for 2p zero-sum, stays in [min_utility, max_utility]

- **`chance_outcomes()`**: `[(i, 1/n) for i in range(n)]` — ✅ sum to 1

- **`information_state_string(player)`**: clone the C state, call `engine_private_view`, dump JSON, append history
  - Uses the **clone-via-replay** technique described above

- **`resample_from_infostate(player, rng)`**: same as Python version but operates on a C-state clone

- **`__deepcopy__`**: uses **clone-via-replay** — copy the move history, replay on a fresh C state from the same seed

### PyrantsCGame

Mirrors `PyrantsGame` exactly:
- Same `parameter_specification` dict
- Same `_build_game_type`, `_build_game_info`
- `new_initial_state()` returns `PyrantsCState(self)`
- `make_py_observer()` returns `PyrantsCObserver`

The C engine is loaded once at game construction (singleton), passed to the state via `game._c_engine`.

### Registration

```python
# openspiel_pyrants/__init__.py
from openspiel_pyrants.game import PyrantsGame       # python_pyrants
from openspiel_pyrants.game_c import PyrantsCGame   # python_pyrants_c
```

OpenSpiel picks up both names automatically via `pyspiel.Game.__init__` side effects.

## Testing strategy (per skill's "verify immediately")

### 1. Smoke test (reuse existing pattern)

`openspiel_pyrants/tests/test_pyrants_c_register.py`:
```python
import pyspiel
game = pyspiel.load_game("python_pyrants_c")
state = game.new_initial_state()
assert state.is_chance_node()
state.apply_action(42)
assert state.current_player() != pyspiel.PlayerId.CHANCE
# Try a few legal actions
for _ in range(10):
    if state.is_terminal(): break
    legal = state.legal_actions()
    state.apply_action(legal[0])
```

### 2. Cross-validation against Python backend

`openspiel_pyrants/tests/test_state_c_vs_python.py`:
- Load both games with the same seed
- Apply the same action sequence
- Assert `current_player()`, `legal_actions()`, `returns()` match at every step
- This is a regression suite — any divergence means the C wrapper is wrong

### 3. API consistency test

Run `pyspiel.random_sim(game, num_sims=20)` — the C wrapper should not throw.

### 4. Determinization

`openspiel_pyrants/tests/test_resample_c.py`:
- `resample_from_infostate` returns a state whose `information_state_string` matches
- This validates the hidden-info path

### 5. IS-MCTS smoke

`openspiel_pyrants/tests/test_ismcts_smoke_c.py`:
- 10 sims, 1 game, 2 players
- Asserts the bot can find legal actions and the game completes

## Files

| File | Lines | Purpose |
|------|-------|---------|
| `engine_c/bindings/c_adapter.py` (new) | 200 | C state clone-via-replay, public/private view projection |
| `openspiel_pyrants/state_c.py` (new) | 200 | `PyrantsCState(pyspiel.State)` |
| `openspiel_pyrants/game_c.py` (new) | 180 | `PyrantsCGame(pyspiel.Game)` |
| `openspiel_pyrants/action_encoding_c.py` (new) | 100 | C-backend action id ↔ CMoveWrapper bijection |
| `openspiel_pyrants/determinization_c.py` (new) | 80 | Resample opponents' hidden zones |
| `openspiel_pyrants/observer_c.py` (new) | 40 | C-backend observer stub |
| `openspiel_pyrants/__init__.py` (updated) | 60 | Register both games |
| `openspiel_pyrants/tests/test_pyrants_c_register.py` (new) | 40 | Smoke test |
| `openspiel_pyrants/tests/test_state_c_vs_python.py` (new) | 200 | Cross-validation |
| `openspiel_pyrants/tests/test_resample_c.py` (new) | 50 | Determinization |
| `openspiel_pyrants/tests/test_ismcts_smoke_c.py` (new) | 60 | Bot can play |

## Risks

1. **Sort-key divergence**: Python's `_move_sort_key` uses Pydantic field access; C's uses `data` dict stringification. The cross-validation test will catch any divergence.
2. **`is_chance_node` vs `is_terminal`**: C state must be queried at the chance node (no C state yet). The `PyrantsCState` handles this via a `_pending_initial_chance` flag, same as the Python version.
3. **Slow clone**: replay-via-history is O(move_count). For depths <100 this is sub-millisecond. For deep trees, `engine_clone_cow` could be added later.
4. **DLL must be present**: the test harness already builds it via `just build-c`. A pytest fixture can `pytest.skip` if the DLL is missing.

## What does NOT change

- `state.py`, `game.py`, `action_encoding.py`, `determinization.py`, `observer.py` — the Python adapter stays as the reference implementation (per Phase 5 plan: "Keep Python engine as reference behind a flag")
- The 380 Python tests
- The 9 cross-validation tests in `tests/test_engine_c.py`
- The 7 OpenSpiel tests in `openspiel_pyrants/tests/` (Python backend)
- `game_setup/`, `engine/`, `interface/`, `scripts/` — pure Python, untouched

## Acceptance criteria

- [ ] `pyspiel.load_game("python_pyrants_c")` works
- [ ] `pyspiel.random_sim(c_game, 20)` completes without exception
- [ ] All 8 new C-backend tests pass
- [ ] Existing 7 Python-backend tests still pass
- [ ] All 9 Phase 4 cross-validation tests still pass
- [ ] All 380+ Phase 0 tests still pass
- [ ] `just openspiel-test` includes both backends
