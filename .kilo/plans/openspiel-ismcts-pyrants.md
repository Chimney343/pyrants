# Plan — Run IS-MCTS against `python_pyrants` and persist/analyze results

## Goal

Drive the stock `open_spiel.python.algorithms.ismcts.ISMCTSBot` against the
existing `python_pyrants` OpenSpiel wrapper, capture per-game decision traces
plus a cross-run summary, and land it as a runnable script + tests.

## Context — what the wrapper does and does not give us today

Read in full before touching code:

- `openspiel_pyrants/game.py:29-60` declares
  `provides_information_state_string=False` and
  `provides_observation_string=False`.
- `openspiel_pyrants/state.py:33-124` does **not** implement
  `information_state_string`, `information_state_tensor`,
  `observation_string`, `observation_tensor`, or
  `resample_from_infostate`.
- `engine/state.py:353-408` is a Pydantic `GameState` with a hand-rolled
  `__deepcopy__` that documents ~10 ms+ per call. This dominates IS-MCTS
  wall-time.
- `docs/openspiel_integration.md:96-101` explicitly defers the
  hidden-info observer and notes it as the path forward for "full
  imperfect-info" search.

The OpenSpiel `ISMCTSBot` (`open_spiel/python/algorithms/ismcts.py`)
**requires** (verified in source):

- `state.information_state_string()` (line 108) — used as the
  search-tree key. Raises `SpielError` if the GameType flag is false.
- `state.resample_from_infostate(player, rng)` (line 223) — the
  determinization step. Every simulation samples a world state
  consistent with the current player's information.
- `state.is_chance_node()` returning True at root only — our existing
  single chance node is fine; during the rollout `run_simulation` will
  encounter no further chance nodes.
- The root `current_player()` must be a real player id, not
  `CHANCE/TERMINAL/SIMULTANEOUS` — already correct.

User has decided: full imperfect-info scope, per-game replay + stats
JSON + summary CSV, default 200 sims/move with a CLI override.

---

## Step 1 — Engine-side: what does each player privately know?

A new module `engine/player_view.py` (pure, no I/O) with one function:

```python
def public_view(state: GameState) -> PublicView: ...
def private_view(state: GameState, player_id: str) -> PrivateView: ...
```

Shape (Pydantic, frozen):

- `PublicView`: round, phase, current_player_id, market (card ids),
  board nodes (controller, troop counts only — no hand/deck contents),
  pending ability/promotion/choice ids (no choices), full public action
  log. **No** hand contents, no deck order, no discard pile, no
  devours.
- `PrivateView`: public view + own hand (card ids in hand order),
  own deck size, own discard size, own barracks, own inner circle,
  own trophy hall counts, own resources. **No** opponent hand, deck
  order, discard, devour.

This is the data we serialize into both the information-state string
and the determinization sampler. It is the canonical "what player p
legitimately knows" projection — `make_py_observer` and
`resample_from_infostate` both use it.

Rules to encode (all in `engine/player_view.py`):

1. Public = everything not in a player's hidden set. Hidden per
   player: own hand, own deck (card order), own discard, own
   devour pile, own face-down deployments (none in current rules —
   confirm and note).
2. Public board: each `NodeState.control` (None / player_id),
   `NodeState.troops` count, `NodeState.spies` count,
   `NodeState.trophy` (None / card_id), `NodeState.aspect`. **No**
   hand-derived info on the node itself.
3. Public market: card ids only, no future draw order.
4. Public log: every action applied so far, plus chance outcome id.
   Use the existing `state.history()` / `state.full_history()` —
   these are already populated by `_apply_action`.

Add `tests/test_player_view.py`:

- Same engine state observed from p0 vs p1 differs only in private
  fields.
- Public view is identical for both players.
- After a `PlayCardMove`, the card's id appears in the mover's
  private view's "played log" but the opponent's private view does
  not include the card's identity (only the count of cards played).
- Serialize/deserialize round-trip via `model_dump_json` /
  `model_validate_json`.

---

## Step 2 — Wrapper-side: information-state string + observer

Update `openspiel_pyrants/game.py`:

- Flip `provides_information_state_string=True` and
  `provides_observation_string=True` in the `GameType`.
- Leave tensor flags `False` for now (out of scope).
- `make_py_observer` returns a new `PyrantsObserver` defined in
  `openspiel_pyrants/observer.py`.

Update `openspiel_pyrants/state.py`:

- `information_state_string(player)` → canonical
  `json.dumps(player_view.private_view(self._engine, player), sort_keys=True)`
  — stable, deterministic, content-addressable. Prefix with the
  `current_player()`'s public `action_history` so the perfect-recall
  property holds (the string must include every private observation
  the player has made, in order). This is the key IS-MCTS uses for
  the search tree.
- `observation_string(player)` → `information_state_string(player)`
  for now (no separate observation/perception split in the bot path;
  can be split later if RL agents need it).
- `resample_from_infostate(player, rng)` — full determinization:
  - Build a fresh `GameState` from the current engine's
    `definition`, `board`, `turn_order`, `phase`, `round_number`,
    `resource_pool`, market, and the public board snapshot
    (controllers + troop counts + spies + trophies).
  - For the current player: copy hand, discard, devour, barracks,
      inner circle, trophy hall, resources, deck size **exactly**.
      Determinization does **not** reshuffle their hand or rewrite
      their known history.
  - For the opponent: copy public hand **size** and public deck
      **size**; the opponent's hidden contents are resampled by
      drawing from the union of undealt cards in
      `(deck ∪ discard ∪ devour) − known_cards`.
      - The "known cards" set for the current player is:
        own hand ids, own discard ids, own devour ids, all
        public cards (market, board trophies, public promotions
        — any card id that ever became public).
      - For determinization of the opponent's hidden zones,
        compute the set of card ids that could plausibly be
        there (total cards in the opponent's pool minus public
        ones), and deal them into a freshly shuffled deck/hand
        whose sizes match the public counts.
      - For any non-public card effects (e.g. cards in inner
        circle that are face-down and were never played), they
        stay where the public view says they are.
  - Re-run `build_initial_game_state`-style setup only for the
    zones that are truly underdetermined. The public history
    (action log) is **preserved exactly** — the determinized
    state must reproduce the same `action_to_string` sequence
    via the same `_apply_action` calls (or, equivalently,
    `game.deserialize_state(serialize(state))`).
  - This is the trickiest piece. Implementation will live in
    `openspiel_pyrants/determinization.py` so it can be
    unit-tested against a fixed `GameState` with known private
    contents.

Pydantic `GameState` is mutable but Pydantic's `model_copy(deep=True)`
+ the existing `__deepcopy__` is fine for the sampled world state.

Update `openspiel_pyrants/action_encoding.py`: no changes; the
encoding is engine-state-scoped, and determinized states share the
same public action history (and thus the same legal-action ids for
all public moves).

Add `openspiel_pyrants/tests/test_information_state.py`:

- `information_state_string` is identical for two states with
  identical `private_view` regardless of chance seed (verify by
  constructing two states with the same hand but different shuffles).
- `information_state_string` is **stable across clone** (call clone,
  compare strings).
- `information_state_string` differs when private contents differ
  (e.g. swap a hidden card between two determinized views).
- `resample_from_infostate` returns a state whose public view
  matches the original exactly.
- `resample_from_infostate` returns a state whose private view for
  the current player matches exactly.
- `resample_from_infostate` round-trip: applying the same public
  actions to the resampled state produces the same `action_to_string`
  sequence.

---

## Step 3 — IS-MCTS runner script

New file: `scripts/run_ismcts.py`. Pure script, no game logic. Mirrors
the `argparse` style of `scripts/random_walk.py` and
`scripts/check_roster_card_stuck_states.py`.

CLI:

```
--num-sims INT          # default 200; passed to ISMCTSBot
--uct-c FLOAT           # default 1.4
--max-world-samples INT # default 1000; passed to ISMCTSBot
--final-policy {visited,max_value,max_visit}  # default visited (normalized)
--num-games INT         # default 4 (2 per side)
--seed INT              # default 42
--output-dir PATH       # default artifacts/ismcts
--shuffle-seed INT      # default 0; if None, random per game
--no-plots              # skip the per-game policy tree dump
```

Per-game behavior:

1. Load game via `pyspiel.load_game("python_pyrants")`.
2. Build an `ISMCTSBot` instance per side using a fresh
   `np.random.RandomState(seed + game_index * 2 + side)`. Each bot
   uses `mcts.RandomRolloutEvaluator(rollout_count=1, n_rollouts=1)`
   for the leaf evaluator (random rollout to terminal — no
   heuristics yet, fastest correctness path).
3. For each game:
   a. Resolve the chance node with `--shuffle-seed` (or random).
   b. Loop: if `is_chance_node()` (only at root), apply the seed.
      Else call the active bot's `step(state)` (or
      `step_with_policy(state)` for the first run to dump policies).
   c. At every decision node, capture:
      - `round`, `phase`, `current_player`
      - `legal_actions` (engine ids → moves via
        `openspiel_pyrants.action_encoding.action_to_move`)
      - `policy` (action → visit-prob from the bot)
      - `chosen_action` (id and move)
      - `wall_time_ms` for the bot's `step()` call
      - `info_state_string` (for debugging/aggregation)
   d. On terminal: `returns()` → winner, score diff, decision count.
4. Write per-game artifacts (see Step 4).
5. Print a one-line summary: seed, sims/move, decisions, sims/sec,
   returns.

Add a new `just` recipe in `justfile`:

```
ismcts num_sims="200" num_games="4" seed="42" output_dir="artifacts/ismcts":
    & {{python}} -m scripts.run_ismcts --num-sims {{num_sims}} --num-games {{num_games}} --seed {{seed}} --output-dir {{output_dir}}
```

(Place it next to `random-walk` / `card-stuck-check`.)

---

## Step 4 — Artifact schema (per-game + summary)

Per-game, under `<output-dir>/game_<NNNN>/`:

- `replay.json` — every engine state snapshot reachable in the game,
  serialized via `pyspiel.serialize_game_and_state(game, state)` at
  each decision node + the terminal node. This is replayable through
  `interface/replay_viewer.py` (it already loads `serialize` strings;
  confirm and adjust the viewer's loader in Step 5 if needed).
- `decisions.jsonl` — one JSON object per line per decision node,
  schema:
  ```
  {
    "node": int, "round": int, "phase": str, "current_player": str,
    "info_state_sha256": str,   // for de-dup across games
    "legal_action_ids": [int],
    "legal_moves": [str],       // engine Move reprs
    "policy": {"action_id": float, ...},  // visit-fraction
    "visit_counts": {"action_id": int, ...},
    "chosen_action_id": int, "chosen_move": str,
    "wall_time_ms": float, "sims_requested": int
  }
  ```
- `summary.json` — single object:
  ```
  {
    "game_index": int, "shuffle_seed": int, "num_sims_per_move": int,
    "uct_c": float, "policy_type": str,
    "decision_count": int, "wall_time_sec": float,
    "sims_per_sec_avg": float,   // sims_requested * decisions / wall
    "returns": [float, float], "winner": 0|1|null,
    "score_diff": float, "moves_per_round": [int, ...]
  }
  ```

Across all games in the run, write a single
`<output-dir>/summary.csv`:

```
game_index,shuffle_seed,num_sims,uct_c,decision_count,wall_time_sec,sims_per_sec,winner,score_diff,avg_policy_entropy
```

And a `<output-dir>/summary.md` with the same rows formatted as a
markdown table plus the run-wide totals (overall sims/sec, win
split, mean decision count, mean game length). Use the
`scripts/build_review_workbook.py` markdown style (no new
dependencies — plain `f.write`).

Add `scripts/run_ismcts.py:write_summary(out_dir, summaries)` to
produce both the CSV and the MD.

---

## Step 5 — Verify and analyze

Add `openspiel_pyrants/tests/test_ismcts_smoke.py`:

- 1 game, 5 sims/move, fixed seed, assert:
  - Returns length 2, sums to ~0.
  - `decisions.jsonl` has at least one line per decision node.
  - Every `policy` entry sums to 1.0 (±1e-6).
  - `chosen_action_id` is in `legal_action_ids`.
  - The replay JSON deserializes back to a state with identical
    `returns()`.
- Skipped automatically if the env var
  `PYRANTS_SKIP_ISMCTS=1` is set (so the main `pytest` run stays
  fast — full IS-MCTS is wall-clock expensive).

Add `openspiel_pyrants/tests/test_resample.py`:

- Build a known state with two fixed hand contents for both players.
- `resample_from_infostate(0, rng)` produces a state whose public
  view matches the original exactly and whose `players["p0"]` hand
  matches the original `players["p0"]` hand exactly.
- The opponent's hand contains the same multiset of card ids as
  the original opponent's hand (across many rng seeds).
- Re-applying the same action sequence to the resampled state
  reproduces the same final `returns()` (within engine tolerance).

Manual analysis (one-off, no script — just print, eyeball, write
findings into `docs/openspiel-ismcts-results.md`):

- Run with `--num-sims 200 --num-games 4 --seed 42`. Note: a
  full 4096-node pyrants game with 200 sims/move is roughly
  200 × 4096 × ~15 ms (one clone + one engine step per sim) ≈
  3.4 hours per game on this machine. **Warn the user explicitly
  in the script's docstring and in the just recipe comment.**
  For first iteration, recommend `--num-sims 50 --num-games 2` to
  prove the pipeline, then scale up.
- After one full game: print sims/sec, win distribution, mean
  decision count. Cross-check with the random policy's numbers
  (we already have those from `docs/openspiel-architecture.md`'s
  random_sim baseline).

---

## Step 6 — Docs and recipe updates

- `docs/openspiel_integration.md`: remove the "Hidden-info observer
  deferred" bullet from the deferred table. Add an "IS-MCTS
  integration" section pointing at the runner script, the new
  observer module, and the determinization module.
- `docs/openspiel-architecture.md`: append a short
  "Information-state projection" section showing the
  `player_view` shape and the determinization contract.
- `AGENTS.md`: add the new scripts to the directory map and
  reference the new just recipe.
- `justfile`: add `ismcts` recipe from Step 3. Optional: add a
  `ismcts-quick` alias for `--num-sims 50 --num-games 2`.

---

## Files touched (summary)

New:

- `engine/player_view.py`
- `engine/tests/test_player_view.py` (or `tests/test_player_view.py`
  to match the existing test layout — confirm in step 1)
- `openspiel_pyrants/observer.py`
- `openspiel_pyrants/determinization.py`
- `openspiel_pyrants/tests/test_information_state.py`
- `openspiel_pyrants/tests/test_resample.py`
- `openspiel_pyrants/tests/test_ismcts_smoke.py`
- `scripts/run_ismcts.py`
- `docs/openspiel-ismcts-results.md` (post-run analysis)

Modified:

- `openspiel_pyrants/game.py` (GameType flags, make_py_observer)
- `openspiel_pyrants/state.py` (information_state_string,
  observation_string, resample_from_infostate)
- `justfile` (`ismcts` recipe)
- `docs/openspiel_integration.md` (remove deferred bullet, new section)
- `docs/openspiel-architecture.md` (projection section)
- `AGENTS.md` (directory map updates)

---

## Out of scope (explicit non-goals for this plan)

- Information-state **tensors** (the bot only needs strings for its
  key). Set `provides_information_state_tensor=False` and leave a
  note.
- Observation/perception split (tensors for RL agents).
- 4-player support (the wrapper still works for 2-player only;
  determinization for 3+ opponents is harder and changes the
  multiset of public-vs-private cards).
- C++ port.
- Heuristic leaf evaluator. `RandomRolloutEvaluator` is the
  correctness baseline; swap it in a follow-up once the plumbing
  is proven.
- Strong-policy output (alphazero, exploitability). The deliverable
  is a working IS-MCTS plumbing, not a strong bot.
- Parallel IS-MCTS (`async_mcts.py`). Mention in a follow-up note
  only — it does not help when the bottleneck is the engine clone.

## Risks

1. **Determinization correctness.** The hardest single piece. If
   `resample_from_infostate` is wrong, the bot will silently
   explore impossible worlds and the search tree will not reflect
   the real game. Mitigation: the test suite in Steps 1 and 2
   asserts the contract (public view unchanged, current player's
   private view unchanged, multiset of opponent's hidden cards
   preserved, action-log replay round-trip).
2. **Pydantic clone cost.** ~10 ms+ per state, times
   `num_sims × decision_count`. With `--num-sims 50` and a 4000
   decision game, that's 50 × 4000 × 10 ms ≈ 33 minutes per game
   on a single core. The script will print sims/sec so the user
   can extrapolate. **Will warn in script docstring, the recipe
   comment, and the first-run docs update.**
3. **History-aliasing bugs.** The existing wrapper has
   `PyrantsState.__deepcopy__` delegated to Pydantic; the
   `__init__` re-initializes the lazy attrs. Need to confirm
   `pyspiel.State` clone is correct after the wrapper changes
   (add a test that clones a state, mutates the original, and
   checks the clone is untouched).
4. **`resample_from_infostate` performance.** Building a fresh
   `GameState` from scratch plus re-dealing cards is itself
   expensive; for now we re-run the *known public actions*
   through a fresh `PyrantsState.clone()` to keep the action
   log consistent. If this is too slow, the follow-up is to
   serialize the public history as a single string and let
   `pyspiel.deserialize_state` rebuild it.

## Verification checklist (must all pass before declaring done)

- [ ] `ruff check .` clean.
- [ ] `just test` (full pytest) passes, including the new
      `test_player_view`, `test_information_state`, `test_resample`,
      `test_ismcts_smoke` tests.
- [ ] `just openspiel-smoke` still passes.
- [ ] `just ismcts num_sims=50 num_games=2` produces
      `artifacts/ismcts/summary.md` with non-zero sims/sec and
      a valid two-game CSV.
- [ ] `decisions.jsonl` for at least one game round-trips:
      loading `replay.json` into `interface/replay_viewer.py`
      reproduces the same final `returns()`.
- [ ] `docs/openspiel_integration.md` "Hidden-info observer
      deferred" bullet removed; new IS-MCTS section present.
- [ ] `AGENTS.md` directory map mentions the new files.
