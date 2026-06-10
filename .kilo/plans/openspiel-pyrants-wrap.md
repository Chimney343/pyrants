# Plan: Wrap pyrants `/engine` as an OpenSpiel Python Game

## Goal
Register pyrants as `python_pyrants` in OpenSpiel so CFR-family algorithms, exploitability analysis, and tree-walkers can train / evaluate agents against the existing engine. Two-player, base game, base board, base_setup, all 14 move types. No observer in this first pass (defer hidden-info to a follow-up).

Decisions captured from clarification round:
- **Goal:** AI training / CFR research.
- **Refactor approach:** Partial refactor — extract randomness from engine, then wrap.
- **Scope:** Two-player base game, no scenarios, no observer.
- **Layout:** New top-level package `openspiel_pyrants/`.

---

## Game classification (drives `GameType` flags)

| Property        | Value | Reason |
|-----------------|-------|--------|
| Dynamics        | `SEQUENTIAL` | One player at a time (`MAIN` / `END_OF_TURN` / `CLEANUP` phases). |
| Chance          | `EXPLICIT_STOCHASTIC` | Deck shuffles + market draw. We'll expose each as a chance node. |
| Information     | `IMPERFECT_INFORMATION` | Hidden hands. *Observer is deferred — set the flag now so CFR can later use IIGObserverForPublicInfoGame or our future observer.* |
| Utility         | `ZERO_SUM` | Scoring.py:94 `compute_final_scores` returns per-player VP totals; engine treats higher score = winner. |
| Reward model    | `TERMINAL` | No per-step rewards. |
| Players         | `min=2, max=2` for this pass. |

---

## Action encoding (the hardest decision)

Single-integer encoding per `Move` subtype, using small reserved id-spaces so the per-`num_distinct_actions` upper bound is small and the `move ↔ id` bijection is stable across runs. All ids are computed deterministically from the current `GameState` (no state-independent global ids) so they line up with what `_legal_actions` enumerates.

Encoding scheme (reserves 4 high-bit "kinds" of slot):

```
0                                 → reserved "no-op / pass" (unused)
1..K_PLAY_CARD                    → PlayCardMove        (card_id from hand, ordered by current hand)
K_PLAY_CARD+1..K_END_MAIN         → EndMainPhaseMove
... (10 base moves: assassin/deploy/recruit/return-spy/activate/decline/promote/skip/resolve-eot/resolve-cleanup)
...                                 + ResolveGenericChoiceMove (option-id based)
... + chance outcomes (K_CHANCE..) and an explicit "RESOLVE" sentinel for "I'm done resolving the current pending thing, advance if possible"
```

Concretely: build **per-`State` action enumeration** by walking `engine.rules.legal_moves(state)` and assigning sorted ids `0..N-1`. The wrapper exposes `num_distinct_actions` as a *fixed* upper bound (computed once at game construction from base definitions — see "num_distinct_actions" below) and `_legal_actions` returns the actual legal slice.

Decision (committed): **flatten per-state, not global.** The global `num_distinct_actions` is the max branching factor over a small synthetic state enumeration. This is the standard OpenSpiel pattern (`kuhn_poker`, `block_dominoes`).

`num_distinct_actions` upper bound, computed once in `__init__`:
- max hand size 5 → 5 PlayCardMove ids
- 1 EndMainPhase
- max deploy targets = 81 nodes
- max assassinate = 81 × 6 slots ≈ 486
- max return-spy ≈ 81 × 2
- max recruit = 6 (market row) + 3 (special) = 9
- 1 Activate + 1 Decline (only 1 pending ability at a time)
- 1 Promote + 1 Skip
- 1 ResolveEOT + 1 ResolveCleanup + 1 ResolveGenericChoice
- + 5 chance outcomes (initial shuffle node: top of 5-card hand — one node per player; 2 players = 2 chance nodes max in any single decision path)

Pick `num_distinct_actions = 1024` (power of 2, comfortably above the synthetic max ~520). Document the computation in a comment block at the top of `state.py`.

`max_game_length`: rough upper bound = 2 players × 20 rounds × 30 decisions/turn ≈ **1200 decision nodes**. Use **4096** to give CFR safety margin. (Chance nodes are *not* counted per the invariant.)

`max_chance_outcomes`: 5 (single-card deals). 

`min_utility` / `max_utility`: with a 40-troop, 5-spy start, a tight reasonable bound is `[-100, 100]` (trophy hall caps, plus scale VP). Use `[-200, 200]` for safety; the tests will flag a violation.

`utility_sum = 0.0` (zero-sum).

---

## Engine refactor: extract randomness into chance outcomes

This is the big non-wrapper work. The skill says this is usually the biggest refactor — and you chose to do it.

### Where randomness hides today
1. `engine/state.py:464` — `draw_cards` reshuffles discard into deck.
2. `engine/state.py:486` — `create_player_state` initial deck shuffle.
3. `engine/state.py:501` — `create_market_state` initial market deck shuffle.
4. `engine/helpers.py:507-513` — `_reshuffle_discard_into_deck` (used by `state.py:464` indirectly through this).
5. `engine/state.py:457-473` — `draw_cards` uses the passed-in `rng`.

### Refactor plan
- Introduce an engine-internal "shuffle box" concept: a **deterministic permutation of a deck given a seed**. Wrap with `engine.helpers.shuffle_with_seed(deck: list[str], seed: int) -> list[str]` (stable, pure). Keep the seed-deterministic `Random` only inside the engine; expose no `Random` to callers.
- In `engine/state.py:457-473`, replace the rng-driven path with a counter-based "shuffle seed" that the engine itself owns. The state carries a `pending_shuffles: int` counter; on every shuffle, the engine produces a fresh, deterministic permutation from `(state.shuffle_seed, state.pending_shuffles)` and increments the counter. **This is the same pattern `helpers.py:507-513` already uses — we extend it, not replace it.** No new RNG state to serialize.
- In `apply()` (rules), **shuffle results are now a fixed function of state.shuffle_seed + state.shuffle_count**. OpenSpiel never needs to inject outcomes; the engine's permutation is fully deterministic given the seed.
- For the wrapper, **the shuffle seed itself becomes the chance outcome**: the wrapper sets `state.shuffle_seed = N` via `_apply_action` at the chance node, where N is the integer action id from `chance_outcomes()`. The chance node enumerates the N possible initial seeds (e.g. `0..999`) and returns uniform probabilities.
- **Game initialization needs the same treatment.** `build_initial_game_state` currently takes `rng: Random` and an explicit `shuffle_seed`. We change it to take only `shuffle_seed: int` and use the deterministic shuffle helper. The wrapper will set the seed via a chance node *after* the engine has created a "blank" initial state.
- **Game type change**: `chance_mode=EXPLICIT_STOCHASTIC`. After refactor, the wrapper's first decision node is a chance node that picks the initial shuffle seed, then a chance node per player picks each opening hand card in order, then play begins.

The refactor must not change any existing test result. The 32 test files in `tests/` should all pass after the refactor — they are our regression net.

---

## File layout

```
openspiel_pyrants/
├── __init__.py            # exports PyrantsGame, register at import
├── game.py                # PyrantsGame(pyspiel.Game) + _GAME_TYPE + _GAME_INFO
├── state.py               # PyrantsState(pyspiel.State) — all adapter methods
├── action_encoding.py     # move <-> int bijection, num_distinct_actions helper
├── chance.py              # chance_outcomes() and outcome injection
├── history.py             # Action-to-string helpers (used for playthroughs and debug)
├── tests/
│   ├── test_pyrants_register.py
│   ├── test_action_encoding.py
│   ├── test_random_sim.py
│   └── test_api_test.py
└── pyproject_extra.toml   # optional: add open_spiel as a dev dep here
```

Top-level `pyproject.toml` is left untouched for the wrapper; we add `open_spiel` as a dev-dep via the existing extras mechanism. A `justfile` recipe `just openspiel-test` is added that runs the four tests.

---

## Implementation steps (in order)

### Step 1 — Engine refactor (randomness extraction)
- File: `engine/state.py` and `engine/helpers.py`.
- Replace `rng: Random` parameter in `build_initial_game_state` and `create_player_state` / `create_market_state` / `draw_cards` with a deterministic `shuffle(deck, seed, counter) -> list[str]` helper. The `state.shuffle_seed` and `state.shuffle_count` are the only sources of randomness. Behavior is **byte-identical** given the same seed.
- Run `pytest` to confirm no test breaks. Iterate until green.
- Add a new test `tests/test_shuffle_determinism.py` asserting the same `shuffle_seed` produces the same hand order on two fresh states.

### Step 2 — Action encoding module
- `openspiel_pyrants/action_encoding.py`:
  - `enumerate_legal_actions(state) -> list[int]` — calls `engine.rules.legal_moves(state)`, assigns sorted ids, returns the list.
  - `action_to_move(state, action_id) -> engine.moves.Move` — inverse.
  - `move_to_action_id(state, move) -> int` — convenience.
  - The mapping is **rebuilt every call** (cheap: ≤ ~500 moves per state). The `num_distinct_actions` constant lives in `game.py` and is fixed at game construction.

### Step 3 — `game.py`
- Define `_GAME_TYPE` and `_GAME_INFO` per the classification table.
- `PyrantsGame(pyspiel.Game).__init__(params)`:
  - Defaults: `board_path = data/boards/tyrants_of_the_underdark.json`, `card_path = data/cards/catalog.json`, `setup_path = data/decks/base_setup.json`, `player_ids = ("p0", "p1")`, `shuffle_seed_count = 1000`.
  - Load the `GameDefinition` once and store on `self._definition`.
  - Compute `num_distinct_actions` from a small synthetic "all moves legal" state.
- `new_initial_state()` returns `PyrantsState(self)`.
- `make_py_observer(...)` — return `IIGObserverForPublicInfoGame(...)` for the perfect-info public-history mode (we don't need a custom observer in this pass; the perfect-info view is fine for CFR on small scenarios).

### Step 4 — `state.py`
- `PyrantsState(pyspiel.State).__init__(self, game)`:
  - `self._game = game`
  - `self._engine = game._build_blank_initial_state()` — pre-shuffles *not* yet applied.
- `current_player()`:
  - terminal → `pyspiel.PlayerId.TERMINAL`
  - if `self._pending_initial_chance` is set → `pyspiel.PlayerId.CHANCE`
  - else `state.turn_order.index(state.current_player_id)`.
- `_legal_actions(player)`:
  - At a chance node: returns chance outcome ids (sorted).
  - At a decision node: builds ids from `enumerate_legal_actions(self._engine)`.
- `_apply_action(action)`:
  - If `is_chance_node()`: dispatch to `chance.apply_chance(self._engine, action)`. After the last initial chance node is resolved, the engine state is fully initialized and we move to player 0's `MAIN` phase.
  - Else: convert id → `engine.moves.Move`, call `engine.rules.apply`, replace `self._engine` with the new state.
- `is_terminal()`: `engine.rules.is_terminal(self._engine)`.
- `returns()`: `engine.scoring.compute_final_scores(self._engine)` if terminal, else current per-player scores. Symmetrize around player 0: `returns = [0 - p0, 0 - p1]...` is wrong; instead declare `utility_sum = 0` and use `returns = [score(p0) - score(p1) ...]` so the array sums to 0. (Decision: use **raw score differences**, signed: winner gets positive, loser gets negative, sum to 0.) For mid-game (non-terminal), use current `score` differences too — the spec says returns is total-return-so-far, and the difference is already a valid 0-sum projection.
- `chance_outcomes()`: returns `[ (i, 1/N) for i in range(N) ]` for the initial-shuffle chance nodes. After those resolve, the game is purely deterministic — no more chance nodes (no in-game card draws that depend on hidden deck order, since shuffle_seed controls everything).
- `__str__`: delegate to `engine.helpers.render_state` if it exists, else a 1-line summary. (Used heavily during debugging.)
- `_action_to_string(player, action)`: route through `action_encoding.action_to_move(state, action)` then format the move.

### Step 5 — `chance.py`
- `apply_chance(state, action_id) -> GameState`:
  - Decodes `action_id` to a shuffle seed (id 0 = seed 0, id 1 = seed 1, …).
  - Creates a fresh `build_initial_game_state(definition, player_ids, shuffle_seed=seed)`.
  - Returns the result.
- One chance node only, with `max_chance_outcomes = shuffle_seed_count` (default 1000). Each outcome picks one seed uniformly. This is the standard Kuhn/Leduc "deal one card" pattern, applied to the whole game's seed.

### Step 6 — Tests
- `test_pyrants_register.py`: `pyspiel.load_game("python_pyrants")` works; `num_distinct_actions`, `max_game_length`, `min_utility`, `max_utility` are set.
- `test_action_encoding.py`: round-trip — for each `(state, action_id)`, decode gives a `Move` that `engine.rules.apply` accepts; `_legal_actions` is sorted and non-empty at every decision node; `_legal_actions` is non-empty at the chance node.
- `test_random_sim.py`: hand-rolled 100 random playouts, asserting:
  - `returns()` is `[float, float]` summing to 0
  - both within `[min_utility, max_utility]`
  - game length never exceeds `max_game_length`
  - no `_legal_actions` calls on terminal states
  - `chance_outcomes()` probs sum to 1
- `test_api_test.py`: `pyspiel.random_sim_test(game, num_sims=10, serialize=True, verbose=True)` passes (this is the built-in OpenSpiel API consistency test — catches aliasing, serialization, observer issues).

### Step 7 — Justfile recipe
- Add `openspiel-test` recipe running `pytest openspiel_pyrants/tests/`.
- Add `openspiel-smoke` recipe running the inline smoke script for manual verification.

### Step 8 — Documentation
- Add `docs/openspiel_integration.md` (one page) describing the action encoding, the chance model, what's covered and what isn't, and how to plug a future observer.

---

## Key invariants to defend in the plan

- `_legal_actions` returns sorted, non-empty lists at every non-terminal decision node. (No exceptions during play, including during the `END_OF_TURN` and `CLEANUP` phases where the engine restricts the move set.)
- `current_player` returns `TERMINAL` at game over, `CHANCE` only at the initial-seed chance node.
- `returns()` always has exactly 2 entries, sum to 0, each within `[-200, 200]`.
- `chance_outcomes()` probabilities sum to 1.0; the only chance node is the initial-shuffle node.
- `max_game_length = 4096` is comfortable for 2p games.
- State mutation: `_apply_action` does `self._engine = new_engine_state` (full replacement). The Pydantic deepcopy already happens inside `engine.rules.apply` so we don't double-copy. This avoids shared-substructure aliasing.
- `clone()` works because `PyrantsState` only holds a reference to `self._engine`, and `GameState.__deepcopy__` is already implemented in `engine/state.py:374-408` (this is the "Pydantic models with deep-copy" path the skill recommends).

---

## What is *out of scope* for this first pass (explicit deferrals)

| Deferred item | Why | Path forward |
|---|---|---|
| Hidden-info observer with perfect-recall | Two-player base game still has hidden hands; CFR via IIGObserverForPublicInfoGame is enough for public-history analysis. | Add `openspiel_pyrants/observer.py` later: build info-state string from `(my_hand, my_played_cards, my_inner_circle, public_action_history)`. Verify with the info-set sanity test. |
| 4-player support | Bigger parameter surface, but the engine already supports it. | Pass `player_ids` as a list parameter; adjust `num_distinct_actions` and `utility_sum` accordingly. |
| Scenario injection (`load_scenario.json` as initial state) | Useful for the 125+ card-scenario tests, but requires a chance-node + scenario-file convention. | Add `scenario_path` parameter; resolve a fixed chance action to "load scenario N". |
| C++ port | Only if MCTS becomes the chosen training algorithm. | The Python playthrough is the regression oracle. |
| End-of-turn promotion deferred choices + repeat_while_targets | These are valid in the engine but blow up the action space. | Verify in step 4 that the encoding handles them; if not, the smoke test will catch it. |

---

## Risks

1. **Engine purity test (`test_engine_purity.py`).** The refactor in step 1 must not introduce `print`/`input`/`open` calls or `interface` imports into `engine/`. Add a grep pre-flight.
2. **Pydantic deep-copy cost.** `GameState.__deepcopy__` was already tuned for performance (`state.py:374-408`). Don't bypass it; don't add a faster but unsound alternative.
3. **Action-id stability.** Since we rebuild the encoding per call, two different states with the same legal-move *type* and *parameters* will get the same id (the `Move` is uniquely identified by `move_type` + fields). This is enough for `_legal_actions` correctness. For CFR info-set identification, what matters is the **information state string** (deferred).
4. **Shuffle seed exhaustion.** `shuffle_seed_count = 1000` gives 1000 distinct initial states. CFR's exploitability estimates converge with sample size, so 1000 is enough for prototype. Make this a parameter.
5. **Move legality at the END_OF_TURN and CLEANUP phases.** The engine restricts moves heavily here (e.g. only `ResolveEndOfTurnMove` if no pending promotions). The encoding must reflect that — `enumerate_legal_actions` will naturally do so.
6. **Test flakiness on Windows.** `Random` with a fixed seed should produce identical output across platforms. Add a determinism test that constructs two states from the same `shuffle_seed` and asserts their deck contents match.

---

## Acceptance criteria

The plan is "done" when all of the following are true:

- [ ] `engine/` purity test still passes.
- [ ] All 32 existing test files pass.
- [ ] `pytest openspiel_pyrants/tests/` is green.
- [ ] `pyspiel.load_game("python_pyrants")` works.
- [ ] `pyspiel.random_sim_test(game, num_sims=10, serialize=True)` is green.
- [ ] 100-iteration random simulation completes without invariant violations.
- [ ] `just openspiel-smoke` exits 0.
- [ ] `docs/openspiel_integration.md` exists and matches the implementation.
- [ ] `ruff check .` is green (the wrapper does not introduce lint regressions).
