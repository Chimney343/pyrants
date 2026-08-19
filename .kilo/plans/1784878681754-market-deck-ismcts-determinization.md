# Plan: Reshuffle the market deck in IS-MCTS determinization

## Goal
Treat the **market deck order** as a hidden-state variable that is randomized on every
IS-MCTS determinization (every `resample_from_infostate` call), so the bot cannot
rely on a single clairvoyant deck order. The face-up **market row** stays untouched
(public/observable). This implements "perfect determinization" for the market deck
and prevents "averaging over clairvoyance" on future `Recruit` draws.

## When the shuffle fires (IS-MCTS execution model)
Verified against the stock bot at
`.venv/Lib/site-packages/open_spiel/python/algorithms/ismcts.py` — the runner
(`scripts/run_ismcts.py`) uses `ISMCTSBot`:

- `run_search` (line 127) loops `max_simulations` times. Each **iteration** calls
  `sample_root_state(state)` (line 206), which calls our `resample_from_infostate` —
  i.e. our market shuffle is a **root** operation, performed at the *real* current decision
  before any simulated play. It is NOT re-applied at deeper tree nodes.
- `run_simulation` (line 347) then descends/rolls out using that one shuffled deck for the
  whole play-down-to-terminal. **No mid-rollout reshuffle.** So "one shuffle per
  determinized world" is accurate; "per rollout-from-current-to-terminal" is imprecise
  because the shuffle precedes the rollout, at root, on the information set.
- `max_world_samples` cadence (the critical caveat):
  - `UNLIMITED` (`-1`): fresh `resample_from_infostate` → fresh shuffle **every iteration**
    (true whitepaper "per-iteration" behavior).
  - Capped (runner default `--max-world-samples 1000`): the first `max_world_samples`
    iterations resample to **fill a pool**; once the pool is full, later iterations **reuse
    a random pooled clone** (line 213) with its **frozen** market order — no new shuffle.
  - Today's defaults (`--num-sims 200` < `1000`) make every iteration resample, so default
    behavior already equals per-iteration. Configs with `num_sims >
    max_world_samples` would re-clamp the diversity of market orders to the pool size.

➡️ Requirement added below (Change 4): to fully honor the whitepaper's per-iteration
guarantee, the runner must use `max_world_samples=UNLIMITED` (or ≥ `num_sims`). Default is
already safe, but make it explicit/documented so a future `--num-sims 5000` doesn't silently
cap market-order diversity.

## Verified findings (do not re-litigate)
- Information-state key stability: `PublicView.market_deck_size` is an **int** (size only);
  `PrivateView` never contains market-deck card IDs. Shuffling `market.deck` preserves the
  `information_state_string` key because only the size is observable. → satisfies whitepaper §2.
- Market deck does **not** recycle its discard:
  - No runtime `market.discard_pile_count++` anywhere in `engine_c/` (only set at JSON load).
  - `engine_c/phases.c:55` — when `market.deck_count == 0` a refill is a **kill**, not a recycle.
  - Python `engine/state.py` `draw_cards` recycles only the **player** discard, never the market.
  - ⇒ Scope is **market deck only**; do not pool `market.discard_pile`. Including it would be wrong.
- `deterimization_c.py` (mis-spelled stub) is **dead code** — never imported. The C backend
  path is `state_c.py` → `CEngineAdapter.determinize` → `ce_api` → C `engine_determinize`.
  Leaving it untouched (out of scope; AGENTS.md: don't extend legacy). No-op noted in a comment.
- C determinism contract (`rng.c` header): same seed → same order within C engine; C shuffle
  is NOT bit-identical to Python. **No test may assert C-market-shuffle == Python-market-shuffle.**
- `rng_shuffle(RNG*, uint32_t*, int)` is Fisher-Yates; `Sym` is 32-bit, so the
  `(uint32_t*)clone->market.deck` cast is valid (already used for the opponent temp buffer).

## Changes

### 1. C engine — `engine_c/state.c` : `engine_determinize`
After the existing opponent-reshuffle loop (line ~298, before `return clone;`), append a
market-deck-only shuffle using the same seeded `rng`:
```c
/* Market deck order is hidden to all players: reshuffle it every determinization
 * so IS-MCTS cannot exploit a single clairvoyant deck order. The face-up market
 * row and the (unused, non-recycled) market discard are left untouched. */
if (clone->market.deck_count > 1) {
    rng_shuffle(&rng, (uint32_t *)clone->market.deck, clone->market.deck_count);
}
```
Rationale for placement **after** the opponent loop: keeps the existing seeded opponent
determinism byte-identical (the RNG draws consumed by opponents are unchanged), minimizing
regression risk to existing determinize tests.

### 2. Python backend — `openspiel_pyrants/determinization.py` : `determinize_opponent_hidden_zones`
After the existing `for opponent_id ...` loop (line ~86, before `return result`), append:
```python
# Market deck order is hidden to all players and not observable (only its size is).
# Reshuffle it per determinization so IS-MCTS samples over all n! deck orders across
# iterations. The face-up row (public) and market discard (no recycle in this engine)
# are intentionally left untouched.
if len(result.market.deck) > 1:
    _shuffle(result.market.deck, rng)
```
`_shuffle` already adapts to both `numpy.random.RandomState` (`.shuffle`) and the
pyspiel `UniformProbabilitySampler` (callable). The `rng` is the same object already
used for opponent reshuffles — placing market shuffle **after** the loop preserves
existing opponent determinism.

### 3. No change to `openspiel_pyrants/deterimization_c.py`
It is dead code; leave as-is. (Optional follow-up, out of scope: delete the file.)

### 4. Runner config — enforce per-iteration resampling (`scripts/run_ismcts.py`)
The market shuffle only reaches per-iteration cadence when OpenSpiel resamples every
iteration. With a capped `max_world_samples < num_sims`, once the pool fills, later
iterations reuse pooled clones with a **frozen** market order — silently re-introducing a
limited clairvoyance set. Make the guarantee explicit (chosen approach: **default to UNLIMITED**):
- Change the `--max-world-samples` CLI default from `1000` to `-1`
  (`UNLIMITED_NUM_WORLD_SAMPLES`), so every iteration always resamples regardless of
  `--num-sims`. Preserve `--max-world-samples` as a user-overridable flag for anyone wanting
  the capped-pool behavior.
- Update the argparse `help` text to note: default `-1` = fresh determinization (and thus
  fresh market-deck shuffle) every iteration, matching the whitepaper; a positive cap reuses
  pooled worlds after the cap fills (frozen market order).
- `ISMCTSBot(... max_world_samples=max_world_samples ...)` is already wired from the arg;
  passing `-1` selects the unlimited code path in `sample_root_state` (line 207-208). No
  change needed there.
- Update `justfile` `ismcts-quick` / `ismcts` / `ismcts-c` targets only if they explicitly
  pass `max_world_samples`; if they rely on the script default they pick up `-1` for free.
  Verify during validation.

## Tests to add / extend

### Python backend — `openspiel_pyrants/tests/test_resample.py`
Add (mirroring the existing `test_determinization_is_random` style):
- `test_determinize_reshuffles_market_deck`: build a state with a non-trivial, multi-card
  market deck and a known face-up row; determinize with two different seeds; assert
  `resampled.market.deck` is a **permutation** of the original multiset (counts match)
  and, with high probability, the two results differ in order. Assert the **market row is
  unchanged** card-for-card across both seeds.
- `test_determinize_preserves_market_row`: row IDs and order identical before/after.
- `test_resample_market_keeps_infostate_key`: `information_state_string(player)` is
  equal before and after `resample_from_infostate` (size is the only observable).

### C backend — `openspiel_pyrants/tests/test_determinize_c.py`
Add (alongside `test_determinize_changes_opponent_hidden`):
- `test_determinize_reshuffles_market_deck`: load a C game, seed a multi-card market deck
  (`_set_market_deck` helper already exists in `tests/c_engine/`), determinize with two
  seeds; assert market deck is permuted (multiset preserved), differs across seeds, and
  **market row unchanged**.
- `test_determinize_market_row_untouched`: row preserved across determinization.
- `test_resample_from_infostate_market_key`: extend the existing `test_resample_from_infostate_matches_key`
  to also pin a non-degenerate market deck and confirm the key still matches (regression
  for the size-only observability invariant).

Pre-existing tests that must stay green:
- `test_determinize_preserves_observing_player`, `test_determinize_changes_opponent_hidden`,
  `test_ismcts_smoke_with_determinization`.

## Validation
1. Rebuild C engine: `just build-c` (rebuilds `engine_c.dll` + C tests).
2. `just test-c-python` (C determinize tests), then `just test` (Python-side test suite).
3. `ruff check .`
4. `just test-c` for the C unit suite.
5. Sanity: `just ismcts-quick` (or `just ismcts-c`) still completes without error.

## Risks
- **Capped-pool reuse (primary behavior risk):** if `max_world_samples < num_sims` and the
  pool is full, later iterations reuse clones → frozen market order → reduced clairvoyance
  diversity even though the determinize function shuffles correctly. Mitigated by Change 4.
- Performance: every determinization now does one extra Fisher-Yates over up to ~74 market
  cards (80 total minus ~6 row). Negligible vs. the existing per-opponent reshuffles, but
  note it scales with the number of determinizations (`num_sims` × decision count).
- Placing market shuffle **before** the opponent loop would shift the RNG stream for
  opponents and could change pinned values in any test that asserts exact opponent deck
  contents after determinize (none found, but choose "after" to be safe).
- The C-vs-Python non-bit-identical-RNG caveat means **no** cross-engine equality assertion
  on market deck order.
- Special supply stacks (`house_guard`, `priestess_of_lolth`, `insane_outcast`, slots
  100/101/102) live outside `market.deck` and are unlimited — unaffected by this change.
- If a future change reintroduces market-discard recycling into the deck, the scope here
  must be revisited to pool `market.deck + market.discard_pile` before shuffling. Flag in
  the added code comments.

## Out of scope
- Deleting/exposing the dead `deterimization_c.py` stub.
- Partial determinization (top-of-deck-only resampling) — flagged as a follow-up in the
  existing module docstring; not addressed here.