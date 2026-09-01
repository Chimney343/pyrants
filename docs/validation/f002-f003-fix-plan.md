# F-002 + F-003 Fix Plan — Reshuffle-Stream Independence and Mid-Game Chance-Node Exposure

**Defects:**
- `docs/validation/findings.md` § F-002 (CRITICAL) — `engine_determinize` never rerolls
  `shuffle_seed`/`shuffle_counter`, so every mid-game reshuffle/forced-discard event resolves
  identically across all ISMCTS-sampled worlds that reach the same `shuffle_counter` value.
- `docs/validation/findings.md` § F-003 (CRITICAL) — mid-game random events (discard-pile
  reshuffles, forced random discards) are never exposed as OpenSpiel chance nodes; they resolve
  silently inside whichever `apply_action` triggered them.

**Why combined, why this split:** `docs/validation/verdict.md` § 5 condition 3 groups these under
one gate and prescribes the sequencing used here, verbatim: *"Reroll `shuffle_seed`/
`shuffle_counter` inside `engine_determinize`, as was already done for the market deck. This is
the cheap half and it removes the shared reshuffle stream. Exposing the events as real chance
nodes (F-003, and then F-008) is the larger design change and can follow."* This plan therefore
has two parts that are independently testable, independently reviewable, and independently
landable:

- **Part A (F-002)** — a two-line C change confined to `engine_c/state.c::engine_determinize`.
  Fully specified below, ready to implement.
- **Part B (F-003)** — a genuine engine architecture change (new chance-node machinery spanning
  `engine_c/*.c`, the ctypes bindings, and `openspiel_pyrants/state_c.py`). Specified to the same
  rigor as Part A's gates/tests, but several implementation choices are real design decisions —
  recorded explicitly below with a recommended default and the reasoning, not assumed.

Part A does not depend on Part B and should land and clear review first — do not block it on Part
B's larger radius. Part B's own falsification test is F-003's original one, re-run for real once
chance nodes exist; F-008 (chance-node branching factor) is explicitly out of scope for both parts
and is only measured, not fixed, after Part B lands — per verdict.md's own sequencing.

---

## 0. Mandatory process constraints

Same three as `f004-fix-plan.md`, `f010-fix-plan.md`, `f011-fix-plan.md`, restated because they
are non-negotiable, not finding-specific:

1. **Test-driven design is mandatory.** Every behavioural change starts as a failing test.
   Implementation does not begin until the RED tests are written, run, and observed to **fail for
   the stated reason**.
2. **This change will be reviewed.** A Phase 5 review is required for each part, not a courtesy
   pass.
3. **`docs/validation/verdict.md` must be updated.** Phase 6 rewrites the F-002 and F-003 entries
   and the § 5 GO/NO-GO condition 3. A fix that lands without the verdict update leaves the audit
   record lying.

A fourth, plan-specific constraint given the size differential between the two parts:

4. **Part A and Part B are separate reviewable units.** Run Part A's Phase 0–6 to completion
   (including its own review and verdict update) before starting Part B's implementation. If Part
   B is not finished in the same session, split verdict.md's condition 3 into 3a (RESOLVED, F-002)
   and 3b (OPEN, F-003) rather than leaving one ambiguous line — do not mark the combined
   condition resolved until both parts are.

---

## 1. Root cause — Part A (F-002)

**(a) The bug.** `engine_c/state.c:271-309` (`engine_determinize`):
```c
GameState *engine_determinize(const GameState *src, Sym observing_player_id, uint64_t seed) {
    ...
    GameState *clone = engine_clone(src);   /* memcpy's shuffle_seed/shuffle_counter unchanged */
    ...
    RNG rng;
    rng_seed(&rng, seed);
    /* reshuffles opponents' hand+deck+discard_pile using `rng` ... */
    /* reshuffles clone->market.deck using `rng` ... */
    return clone;   /* clone->shuffle_seed / clone->shuffle_counter never touched */
}
```
`engine_clone` carries `shuffle_seed`/`shuffle_counter` through byte-for-byte (a plain
field-for-field copy). Confirmed empirically at N=141/141 (`findings.md` F-002 `Observed:` block).

**(b) Every mid-game random event is a pure function of exactly those two fields.** Ten call
sites across the engine reseed a fresh, throwaway `RNG` from `state->shuffle_seed`, fast-forward
it by calling `rng_next` exactly `state->shuffle_counter` times, draw the actual outcome, then
increment `state->shuffle_counter`:

| Site | Event |
|---|---|
| `state.c:29-40` (`draw_cards_state`, called `phases.c:31`) | Draw-phase reshuffle (deck empty → shuffle discard into deck) — the rulebook's own "Draw a Card" case. Its own, separate inline reshuffle implementation — not routed through the next row. |
| `state.c:219-231` (`reshuffle_discard_into_deck`, called `rules.c:629`, `actions.c:175`, `actions.c:430`) | Reshuffle-on-empty-deck triggered from card effects (e.g. `promote_top_of_deck`) |
| `actions.c:404-413` (`apply_force_discard`, random branch, `hand_idx<0`) | Single targeted random discard |
| `rules.c:530-538` | End-of-turn mass discard (a likely duplicate of the next row's `end_of_turn_mass_discard` interceptor — see (d)) |
| `generic_runtime.c:519-548` | `end_of_turn_mass_discard` interceptor (Neogi) |
| `generic_runtime.c:550-591` | `conditional_owner_discard` (Mindwitness) |
| `generic_runtime.c:593-633` | `local_discard` (Chuul) |
| `generic_runtime.c:635-665` | `mass_discard` (Nothic) |

(Grepped exhaustively: `grep -n "shuffle_seed\|shuffle_counter" engine_c/*.c` — these are the only
sites reading either field, aside from `engine_create_game`/`engine_clone`/`engine_determinize`
themselves.)

Since every ISMCTS-sampled determinization of one information set shares the same
`(shuffle_seed, shuffle_counter)` at its root (part (a)), two simulations that reach the same
`shuffle_counter` value at their first in-rollout event — trivially true for the *first* such
event in both, since both start at the root's counter — draw from the identical `RNG` stream and
get the identical outcome, regardless of which hidden world (the `seed` param passed to
`determinize`) produced them. Confirmed in `findings.md` F-002: 3/3 controlled reshuffles produced
bit-identical permutations when `(seed, counter, contents)` all matched, and changed when either
was perturbed — i.e. `shuffle_seed`/`shuffle_counter` are the *entire* input to the permutation,
contents aside.

**(c) The fix has a working precedent two lines below the bug.** `state.c:300-306` already solves
this exact problem for the market deck:
```c
/* Market deck order is hidden to all players (only its size is public):
 * reshuffle it on every determinization so IS-MCTS cannot exploit a single
 * clairvoyant deck order across simulations. */
if (clone->market.deck_count > 1) {
    rng_shuffle(&rng, (uint32_t *)clone->market.deck, clone->market.deck_count);
}
```
The author demonstrably understood the failure mode and fixed it for one channel; player-deck
reshuffles and forced discards were left on the shared stream. Rerolling
`clone->shuffle_seed`/`clone->shuffle_counter` from the same already-seeded `rng` extends the
identical treatment to every one of the ten sites in (b), with no changes needed at any of those
call sites themselves — they all already read `state->shuffle_seed`/`state->shuffle_counter`
polymorphically; only the *value* of those two fields on a determinized clone needs to stop being
the root's value.

**(d) A duplicate reshuffle implementation, noted but not fixed here.** `draw_cards_state`
(state.c:29-40) reimplements "shuffle discard pile into deck" inline (`memcpy` + `shuffle_deck` +
counter increment) rather than calling `reshuffle_discard_into_deck` (state.c:219-231), which does
the same thing. Both key off `shuffle_seed`/`shuffle_counter` identically, so Part A's fix
(rerolling those two fields) covers both without needing to unify them. Unifying the two
implementations is a legitimate follow-up cleanup but is out of scope here — it changes no
observable behavior any of this plan's gates check.

---

## 2. Root cause — Part B (F-003)

**(a) The gate is binary and content-blind.** `openspiel_pyrants/state_c.py:202-210`:
```python
def chance_outcomes(self):
    if not self._pending_initial_chance:
        return []
    ...
def is_chance_node(self):
    return self._pending_initial_chance and not self.is_terminal()
```
`is_chance_node()`/`chance_outcomes()` are gated solely on `self._pending_initial_chance`, a flag
that is true exactly once, before the first player acts, and false for the rest of the game.
Every one of § 1(b)'s ten call sites fires mid-game, inside whatever `apply_action` triggered it,
with `_pending_initial_chance` already `False` — so `is_chance_node()` reports `False` while
`shuffle_counter` silently advances. Confirmed empirically: 134/2,112 transitions advanced
`shuffle_counter`, 0 of them preceded by `is_chance_node()==True` (`findings.md` F-003).

**(b) The engine already has the machinery this fix needs — built for a different purpose.**
`engine_c/generic_runtime.c` implements `PendingGenericChoiceState` (`state.h:267-293`, held at
`GameState.pending_generic`, `state.h:324`): when a card effect needs a *player* decision mid-
resolution (which option, which target), the engine does not resolve it inline — it populates
`pending_generic`, returns control, and `legal_pending_generic_choice_moves`
(`generic_runtime.c:1262`) enumerates the legal `resolve_generic` moves for whatever is pending.
Python already consumes this uniformly: `CEngineAdapter.legal_moves()` →
`PyrantsCState._legal_actions()` doesn't distinguish "ordinary move" from "resolve a pending
generic choice" — both arrive through the same `legal_moves()`/`apply()` cycle (confirmed reading
`action_encoding_c.py::compute_c_action_map` and `ce_api.py`'s `_MOVE_TYPE_MAP`, which already has
a `MOVE_RESOLVE_GENERIC` → `"resolve_generic"` entry). `pending_generic` is also already exposed to
Python via ctypes (`engine_bindings.py:274`, `c_adapter.py:99-132` reads it directly through
`self._state._ptr.contents.pending_generic`) — no new ctypes plumbing pattern is needed to make a
pending state visible cross-language; the pattern already exists and is exercised in production.

**(c) The paper's own justification for not modeling the initial deal as a chance node does not
extend to these events.** `docs/ismcts-paper.md` § III-C-2: shuffles are excluded from the search
tree specifically because "this occurs before any player has made a decision." Tyrants' mid-game
reshuffles and forced discards happen after many decisions — precisely the class the paper says
*must* be a chance node. This is F-003's own citation, repeated here because it is the reason
"resolve silently" is a defect and not a legitimate simplification: F-003's own steelman (folding a
*fixed* small outcome space into the transition could be legitimate) only holds once F-002 no
longer collapses the outcome across worlds (Part A), and only if the search actually gets separate
statistics for the branch, which today it structurally cannot — `is_chance_node()` is gate-blind
per (a) regardless of F-002.

**(d) `rng_shuffle` is exactly Fisher-Yates — this matters for the outcome-space design.**
`engine_c/rng.c:68-75`:
```c
void rng_shuffle(RNG *rng, uint32_t *arr, int n) {
    for (int i = n - 1; i > 0; i--) {
        int j = rng_randint(rng, 0, i + 1);
        uint32_t tmp = arr[i]; arr[i] = arr[j]; arr[j] = tmp;
    }
}
```
A reshuffle's *true* outcome space is not "one of `n!` permutations" as a monolithic chance node —
it decomposes into `n-1` independent, sequential uniform draws, each over a shrinking range
`[0, i]`. This matters for design (§ 11 D3 below) and is relevant evidence for F-008 (deferred, not
fixed here): modeling each reshuffle as one chance node with a full-permutation outcome space would
make F-008 worse than it needs to be; modeling it as the sequence of small per-position draws the
shuffle already performs keeps each individual chance node's branching bounded by the zone size at
that position, not its factorial.

---

## 3. Acceptance gates

### Part A
| Gate | Threshold |
|---|---|
| GA1 (verdict.md § 5 condition 3, verbatim) | Two determinizations of one information set no longer share `(shuffle_seed, shuffle_counter)` over **N ≥ 100** pairs |
| GA2 | Same info-state root, same `determinize`/`resample_from_infostate` seed called twice ⇒ identical `(shuffle_seed, shuffle_counter)` **and** identical reshuffle permutation (reproducibility preserved — required for F-010's identically-seeded-search guarantee to keep holding) |
| GA3 | Two determinizations of one info-state root with **different** seeds now produce **different** reshuffle permutations at the first forced reshuffle (extends `f002b.py`'s manual-perturbation harness to the real `determinize()` → `determinize()` path) |
| GA4 | Market-deck reshuffle behaviour byte-unchanged (regression guard on the adjacent, already-correct code this fix sits next to) |
| GA5 | `just test-c` (touches `state.c`), `just openspiel-test`, `just test` all green; only the 3 pre-existing `engine_c`/catalog failures on record (Zuggtmoy, Air Elemental, Neogi) tolerated |
| GA6 | F-010's own regression probe (`det_bot.py` B1: 10 identically-seeded searches from one fixed root ⇒ 1 distinct chosen action) unchanged — this fix touches `state.c`, which `determinize()` depends on transitively |

### Part B
| Gate | Threshold |
|---|---|
| GB1 (F-003's own falsification test, re-run to flip) | Instrument a `just ismcts-quick`-scale run: every `shuffle_counter` advance is now preceded by an `is_chance_node()==True` state, over the same N-scale as the original finding (≥2,000 transitions) |
| GB2 | `chance_outcomes()` at each newly-exposed node returns a non-empty, uniformly-weighted outcome list whose length matches the true outcome count at that node (hand size for a forced discard, current remaining range for a reshuffle-position draw) |
| GB3 | Applying each declared chance outcome resumes the engine correctly — the resulting state's discarded card / deck contents match what the old inline-RNG path would have produced for that same index, i.e. behavior is preserved, only *how* the index is chosen changes (verified against a frozen pre-Part-B legacy-path baseline, N ≥ 50 events per event kind) |
| GB4 | INV-1 (replay determinism), INV-4a/4b (leakage/completeness), INV-5 (determinization/world-diversity), the always-on battery, and F-010's `det_bot.py` regression probe all still pass — a bigger tree (real chance nodes where there were none) must not break existing reproducibility or leak/completeness guarantees |
| GB5 | `just test-c`, `just openspiel-test`, `just test` green, same 3 pre-existing failures tolerated |
| GB6 | Every one of the ten call sites in § 1(b) is covered — no event kind is fixed on Part A's cheap half but left silently resolving in Part B |

---

## PART A — F-002: reroll `shuffle_seed`/`shuffle_counter` in `engine_determinize`

## 4. Phase 0 — red baseline

Extend, don't replace, the existing evidence (append-only, Hard Rule 7): `findings.py`'s F-002
section already captures N=141 "same" pairs at the harness's own scale; this phase captures a
**new**, wider run at the gate's own N so Phase 4 has an apples-to-apples comparison.

New script `docs/validation/harness/f002_reroll.py` (mirrors `f002b.py`'s `prep`/
`first_reshuffle_deck` helpers, but drives two independent
`s.resample_from_infostate(p, RandomState(seedA))` / `(p, RandomState(seedB))` calls from one
root, per `findings.py`'s own F-002 loop shape, at N ≥ 100):
```
.venv/Scripts/python.exe -u docs/validation/harness/f002_reroll.py > docs/validation/baseline/f002_reroll.pre.txt
```
Expected pre-fix content: same/tot ≈ 100/100 (matches the existing 141/141 finding) — this is the
red signal Phase 2 must flip toward 0/100.

## 5. Phase 1 — RED tests

| # | Test | Location | Asserts | Pre-fix |
|---|---|---|---|---|
| T-A1 | `test_determinize_rerolls_shuffle_stream` | **new**, `engine_c/test_engine.c` (C-level — no existing C test touches `engine_determinize` at all, confirmed by grep; follow `test_clone`'s style, `test_engine.c:96-117`) | Build a `GameState` with `shuffle_seed=X`, `shuffle_counter=Y`; call `engine_determinize(gs, observing_id, seed1)` and `engine_determinize(gs, observing_id, seed2)`, `seed1 != seed2`; assert the two clones' `shuffle_seed` values differ from each other AND from `gs->shuffle_seed` | **FAIL** today — both clones show `shuffle_seed==X`, `shuffle_counter==Y`, identical to `gs` |
| T-A2 | `test_determinize_shuffle_stream_deterministic_per_seed` | same file | Calling `engine_determinize(gs, observing_id, seed1)` twice produces the *same* rerolled `shuffle_seed` both times (control — must hold pre- and post-fix) | **PASS pre-fix** (trivially — nothing varies pre-fix); becomes the real regression guard post-fix |
| T-A3 | `test_resample_from_infostate_decouples_reshuffle_stream` | **new**, `openspiel_pyrants/tests/test_determinize_reshuffle_independence.py` (same `_load_c_game`/`import openspiel_pyrants` pattern as `test_utility_contract.py`/`test_observation_completeness.py`) | From one mid-game info-state root, two `resample_from_infostate(player, RandomState(seedA))` / `(player, RandomState(seedB))` calls produce different `(shuffle_seed, shuffle_counter)` pairs on their resulting adapters (read via `._adapter._state._s`, the same direct-struct-access pattern `harness/common.py::raw` and `test_observation_completeness.py::_force_discard` already use) | **FAIL** — both show the root's shared `(shuffle_seed, shuffle_counter)`, matching `findings.md`'s 141/141 |
| T-A4 | `test_resample_from_infostate_same_seed_reproducible` | same file | The same call with the **same** seed applied twice yields identical `(shuffle_seed, shuffle_counter)` and, when driven to a forced reshuffle, identical deck order (control — ties to F-010; must hold both pre- and post-fix) | **PASS** pre-fix (trivially, nothing varies pre-fix either) |
| T-A5 | `test_market_deck_reshuffle_unaffected` | same file | Market-deck contents after `resample_from_infostate` are unchanged in behavior from pre-fix (regression guard on the adjacent working code) | **PASS** pre-fix (baseline for comparison) |
| T-A6 (script, mirrors `f011_timing.py`/`f004_utility.py`'s N-scale precedent) | reroll independence at gate N | `docs/validation/harness/f002_reroll.py` | N ≥ 100 pairs, `(shuffle_seed, shuffle_counter)` collision rate | **FAIL** — ≈100/100 collide pre-fix |

T-A1/T-A3/T-A6 are the RED tests proper. T-A2/T-A4/T-A5 are due-diligence controls, written first
per house pattern (regression guards exist in git history before the change that could break
them).

## 6. Phase 2 — GREEN implementation

One edit, confined to `engine_c/state.c::engine_determinize`:
```c
GameState *engine_determinize(const GameState *src, Sym observing_player_id, uint64_t seed) {
    if (!src) return NULL;
    GameState *clone = engine_clone(src);
    if (!clone) return NULL;

    RNG rng;
    rng_seed(&rng, seed);

    /* ... existing opponent hand/deck/discard reshuffle loop, unchanged ... */

    /* ... existing market deck reshuffle, unchanged ... */
    if (clone->market.deck_count > 1) {
        rng_shuffle(&rng, (uint32_t *)clone->market.deck, clone->market.deck_count);
    }

    /* NEW — F-002: decouple the shared mid-game reshuffle/forced-discard
     * stream across sampled worlds, the same way the market deck already is.
     * See docs/validation/f002-f003-fix-plan.md Part A. */
    clone->shuffle_seed = rng_next(&rng);
    clone->shuffle_counter = 0;

    return clone;
}
```
Placed *after* every existing draw from `rng` so the rerolled `shuffle_seed` is a deterministic
function of the full `rng` state (and therefore of `seed`) — required for GA2/T-A4/F-010
reproducibility. Rebuild before re-running any Python-facing test: `just build-c`. Run T-A1–T-A6;
all should flip to pass except T-A2/T-A4/T-A5, which must stay passing throughout.

## 7. Phase 3 — guard against silent regression

- T-A3/T-A6 stay in the permanent suite — the guard against a future `engine_clone`/
  `engine_determinize` edit accidentally re-introducing a shared-field copy.
- T-A4 stays in the permanent suite — the guard against the reroll accidentally drawing from
  unseeded entropy (e.g. a stray `rand()`/time-based call) instead of the already-seeded `rng`,
  which would silently break F-010's reproducibility.
- T-A2/T-A5 stay as controls confirming the fix's placement (after all other `rng` draws) doesn't
  get moved earlier by a future edit in a way that would change the `seed → shuffle_seed`
  derivation.

## 8. Phase 4 — re-run the invariant battery

```
just build-c
.venv/Scripts/python.exe -u docs/validation/harness/f002_reroll.py > docs/validation/baseline/f002_reroll.post.txt
.venv/Scripts/python.exe -u docs/validation/harness/f002b.py
.venv/Scripts/python.exe -u docs/validation/harness/findings.py       # re-confirm F-002's original section, for ledger continuity
.venv/Scripts/python.exe -u docs/validation/harness/det_bot.py        # GA6 / F-010 regression
.venv/Scripts/python.exe -u docs/validation/harness/inv_a.py          # INV-1/2/3/6 always-on
.venv/Scripts/python.exe -u docs/validation/harness/inv_b.py          # INV-4a/5
pytest openspiel_pyrants/tests/test_determinize_reshuffle_independence.py -v
just test-c
just openspiel-test
just test
```
Expected: GA1 ≈0/100 collisions (not provably zero — the seed space is finite, so flag any nonzero
count for manual inspection rather than treating it as automatic pass); GA2/GA4 unchanged from
Phase 0; GA6 unchanged (1 distinct action); always-on battery unchanged; GA5 same 3 pre-existing
failures, zero new.

## 9. Phase 5 — review (required gate)

Run `/code-review` on the diff, then a pass against this checklist:

- [ ] The reroll is placed after every other `rng` draw in the function (order matters for
      GA2/reproducibility) — reviewer reads the diff, does not trust this plan's claim.
- [ ] `engine_determinize`'s opponent-hand/deck/discard loop and market-deck block are
      byte-identical to pre-fix — only the two new lines are added.
- [ ] GA1 is re-run independently at N ≥ 100, not trusted from this plan's own capture.
- [ ] F-010's `det_bot.py` B1 is re-run independently — confirms this fix does not reintroduce
      irreproducibility through a different path.
- [ ] `just test-c` is re-run independently (this is a `.c` file change; a Python-only review pass
      is insufficient).

## 10. Phase 6 — update the audit record (Part A)

1. `docs/validation/verdict.md` § 2: move F-002 into a resolved section, following the F-010/
   F-011/F-004 precedent format. § 5 condition 3 splits into 3a (F-002, **RESOLVED**) / 3b (F-003,
   tracked separately, still **OPEN**) — do not mark the combined condition resolved until Part B
   lands too.
2. `docs/validation/findings.md` F-002 `Status:` → `**CONFIRMED — FIXED** (<commit sha>)`,
   original evidence kept intact (append-only, per Hard Rule 7).

---

## PART B — F-003: expose mid-game random events as OpenSpiel chance nodes

This part is the "larger design change" verdict.md defers. It is specified to the same
test-first rigor as Part A, but — unlike Part A — several implementation choices are genuine
design decisions for the fixing agent to make, not mechanical edits. Each decision below states a
recommended default and the reasoning; a reviewer should treat a deviation as acceptable only if
justified in the diff, not silently substituted.

## 11. Design decisions

**D1 — Reuse `pending_generic`'s *plumbing pattern*, not its struct.** `PendingGenericChoiceState`
(§ 2(b)) carries card-execution context (`option_ids`, `resolve_depth`, `last_selection_keys`, ...)
that a bare "pick index 0..N-1" chance event doesn't need. Recommended: a new, minimal
`PendingChanceState` (event-kind tag + target player + outcome count + whatever the resuming code
needs to finish the original call, e.g. a saved continuation identifying which of the ten § 1(b)
sites is waiting) rather than overloading `PendingGenericChoiceState`. The *mechanism* — pause
mid-resolution, expose legal moves for the pending state, resume on `apply()` — is what's reused,
not the struct.

**D2 — A new move kind, not a repurposed `resolve_generic`.** Add `MOVE_RESOLVE_CHANCE`
(mirroring `MOVE_RESOLVE_GENERIC`) with a `data.resolve_chance.{outcome_index}` payload,
registered in the `Move` union, `ce_api.py::_MOVE_TYPE_MAP`, and wherever the top-level
move-generation dispatch lives (confirmed the pending-choice enumeration path is
`legal_pending_generic_choice_moves`, `generic_runtime.c:1262` — the top-level
`engine_legal_moves` dispatcher that calls into it was **not** located during this investigation
and must be found and extended by the fixing agent as the first concrete step). Reusing
`resolve_generic` would conflate "a player chose this" with "chance chose this" in
`information_state_string`'s action history and in any future analysis — keep them distinct at the
type level.

**D3 — Reshuffle outcome-space: per-position draws, not one factorial node.** Per § 2(d),
`rng_shuffle` is Fisher-Yates; expose each reshuffle as `n-1` sequential chance nodes
(`is_chance_node()==True` after each), each with an outcome count equal to the *current* remaining
range (`i+1` at step `i`), matching what `rng_randint(rng, 0, i+1)` already draws. This keeps each
individual node's branching factor bounded by zone size at that position rather than `n!`, and is
the most direct, no-judgment-call translation of the existing algorithm into chance nodes — it
does not attempt to solve F-008 (whether that branching is still too large for the paper's
technique), which is measured, not fixed, after this lands (§ 17).

**D4 — Forced-discard events stay a single chance node.** Unlike reshuffles, `apply_force_discard`
and the four `generic_runtime.c` mass-discard variants each draw exactly one
`rng_randint(0, hand_count)` — already a small (typically single-digit) outcome space needing no
decomposition.

**D5 — All ten call sites from § 1(b) must convert, or the fix is incomplete (GB6).** Converting
only `draw_cards_state`/`reshuffle_discard_into_deck` (the rulebook-cited "Draw a Card" case) and
leaving the four `generic_runtime.c` mass-discard variants (plus `rules.c:530-538`'s likely
duplicate) on the old inline-RNG path would leave F-003 partially fixed — `is_chance_node()` would
still report `False` immediately before a `shuffle_counter` advance for whichever sites are
skipped, and GB1's falsification test would catch this directly (same test as the original
finding, at the same N-scale).

## 12. Acceptance gates

See § 3 above (GB1–GB6) — restated there for locality with Part A's gates, not duplicated here.

## 13. Phase 0 — red baseline

The original F-003 evidence (`findings.md`, 134/2,112 unguarded advances) is immutable ledger
content per Hard Rule 7 — not re-captured. Phase 0 instead re-runs `findings.py`'s F-003 section
fresh, immediately before Part B implementation begins (i.e. *after* Part A has landed), so the
pre-Part-B baseline reflects Part A's state, not the pre-Part-A one:
```
.venv/Scripts/python.exe -u docs/validation/harness/findings.py > docs/validation/baseline/f003_chance_nodes.pre.txt
```
Expected: unchanged from the original finding in kind (still 0 advances preceded by
`is_chance_node()==True`) — Part A does not touch `is_chance_node()`/`chance_outcomes()` at all,
so this number should not move between Part A landing and Part B starting.

Additionally, capture the **frozen legacy-path baseline** T-B3 needs before any Part B code
change: at a fixed `seed`, log the outcome (discarded card / resulting deck order) the current
inline-RNG path produces for each of the ten § 1(b) sites, keyed by `(site, shuffle_seed,
shuffle_counter)`, since the inline path is deleted once Part B lands and there will be nothing
left to compare against otherwise.

## 14. Phase 1 — RED tests

| # | Test | Asserts | Pre-fix (Part B) |
|---|---|---|---|
| T-B1 | `test_forced_discard_is_chance_node` (new, `openspiel_pyrants/tests/test_chance_nodes.py`) | Drive a state to just before a forced-discard event (direct struct injection to guarantee reachability, mirroring `test_observation_completeness.py::_force_discard`, lines 118-123); assert `is_chance_node()==True` immediately before the event and `chance_outcomes()` has length == target hand size | **FAIL** — `is_chance_node()` is `False` |
| T-B2 | `test_reshuffle_is_chance_node_sequence` | Drive a state to just before a reshuffle (empty deck + nonempty discard); assert a sequence of chance nodes fires, each with the expected shrinking outcome count (D3) | **FAIL** |
| T-B3 | `test_chance_outcome_application_matches_legacy_rng_path` | At a fixed `seed`, compare the card ultimately discarded / the resulting deck order via the new explicit-chance path against the Phase 0 frozen legacy-path baseline, for the same `(shuffle_seed, shuffle_counter)` — over N ≥ 50 events per event kind (GB3) | N/A pre-fix — this is a behavior-preservation check that only makes sense once Part B exists; its ground truth is captured in Phase 0, before any Part B code changes |
| T-B4 (script, mirrors `findings.py`'s own F-003 loop) | `docs/validation/harness/f003_chance_nodes.py` — GB1 at N ≥ 2,000 transitions | Every `shuffle_counter` advance preceded by `is_chance_node()==True` | **FAIL** pre-fix (0 preceded, matching the original finding), must be 100% post-fix |
| T-B5 | `test_all_ten_sites_converted` | A targeted probe per § 1(b) site (reuse the struct-injection pattern to force each of the ten call sites individually) — GB6 | **FAIL** for all ten pre-fix |

Per house pattern: capture T-B3's frozen legacy-path baseline (Phase 0) before starting the GREEN
implementation, so there is a pre-change ground truth to diff against, not a claim.

## 15. Phase 2 — GREEN implementation (milestones, not one commit)

Given the radius (new struct, new move kind, ctypes additions, ten call-site conversions,
`state_c.py` changes), land as separate, individually-tested milestones — each with its own
build+test cycle, not one large diff:

1. **M1 — `draw_cards_state` (state.c:29-40)**, the rulebook-cited, highest-traffic path. Convert
   first: the smallest single call site, exercised by every game via the draw phase, so any
   plumbing mistake surfaces immediately in the existing suite.
2. **M2 — `reshuffle_discard_into_deck` (state.c:219-231)** and its three callers. Shares the
   outcome-space design with M1 (D3) — should be nearly mechanical once M1's plumbing exists.
3. **M3 — `apply_force_discard` random branch (actions.c:404-413).**
4. **M4 — the four `generic_runtime.c` mass-discard variants + `rules.c:530-538`'s likely
   duplicate.** Do these last and together — they share one shape (D4), and § 1(d) already flags
   `rules.c:530-538` as a probable duplicate of one of the `generic_runtime.c` variants, worth
   confirming/unifying while converting rather than converting five near-identical copies
   independently.

After each milestone: rebuild (`just build-c`), re-run T-B1–T-B5 for that milestone's sites,
re-run the always-on battery (INV-1/2/3/6) and F-010's `det_bot.py` probe before starting the next
milestone — catching a regression at M1 is cheap; catching it after M4 means re-diffing four
milestones at once.

## 16. Phase 3 — guard against silent regression

- T-B4/T-B5 stay in the permanent suite (or a marked slow/script tier, per `f011_timing.py`'s
  precedent) — the guard against a future new card effect adding an eleventh silent-RNG site the
  way `generic_runtime.c`'s four variants accumulated over time.
- T-B3's legacy-path comparison stays as a one-time migration-correctness record (frozen
  baseline), not a permanent regression test — once Part B lands, the legacy inline-RNG path is
  deleted, so there is nothing left to compare against going forward.

## 17. Phase 4 — re-run the invariant battery

```
just build-c
pytest openspiel_pyrants/tests/test_chance_nodes.py -v
.venv/Scripts/python.exe -u docs/validation/harness/f003_chance_nodes.py > docs/validation/baseline/f003_chance_nodes.post.txt
.venv/Scripts/python.exe -u docs/validation/harness/findings.py         # re-confirm F-003's original section
.venv/Scripts/python.exe -u docs/validation/harness/inv_a.py            # INV-1/2/3/6
.venv/Scripts/python.exe -u docs/validation/harness/inv_b.py            # INV-4a/5
.venv/Scripts/python.exe -u docs/validation/harness/det_bot.py          # F-010 regression
just test-c
just openspiel-test
just test
```
Then, once GB1–GB6 are all green, **measure F-008** (do not fix it): log
`len(chance_outcomes())` at every newly-exposed chance node over a representative game and
compare to the paper's ≤4 assumption — this is exactly the evidence verdict.md § 4 flags as
missing ("Evidence that would settle it: expose mid-game reshuffles ... then log
`len(chance_outcomes())`"). Record the result as new evidence on F-008's ledger entry; do not fold
a fix for it into this plan.

## 18. Phase 5 — review (required gate)

Per milestone, plus a final pass over the whole Part B diff:

- [ ] Every one of the ten § 1(b) sites is accounted for — reviewer checks GB6/T-B5 output, not
      this plan's claim of ten.
- [ ] `chance_outcomes()` probabilities are genuinely uniform and sum to 1 at every new node
      (mirrors INV-6's existing check, extended to the new nodes).
- [ ] The reshuffle decomposition (D3) matches `rng_shuffle`'s actual per-position range, not an
      approximation — reviewer re-derives the expected outcome count at a sampled position
      independently.
- [ ] T-B3's legacy-path comparison (GB3) is attached and shows behavior preservation, not just
      "no crash."
- [ ] INV-1/INV-5/F-010's `det_bot.py` probe are independently re-run, not trusted from the
      milestone logs.

## 19. Phase 6 — update the audit record (Part B)

1. `docs/validation/verdict.md` § 2: move F-003 into a resolved section. § 5: mark condition 3
   (both halves) resolved, or close 3b specifically if 3a (Part A) already landed separately (see
   § 0 constraint 4).
2. `docs/validation/findings.md` F-003 `Status:` → `**CONFIRMED — FIXED** (<commit sha>)`.
3. `docs/validation/findings.md` F-008: append the branching-factor measurement from Phase 4 above
   as new `Observed:` evidence (append-only) — this moves F-008 from UNTESTABLE to either
   CONFIRMED or REFUTED depending on what the numbers show. **Do not** silently mark F-008 fixed
   as a side effect of this plan — it gets its own status update, on its own evidence, per Hard
   Rule 7.

---

## 20. Risks

| Risk | Mitigation |
|---|---|
| (Part A) Reroll accidentally draws from something other than the already-seeded `rng`, silently reintroducing irreproducibility | T-A4 + GA6 (F-010's own probe) re-run at every phase |
| (Part A) A future edit reorders the reroll before the market/hand shuffles, changing the `seed → shuffle_seed` derivation without anyone noticing | T-A2 regression control; Phase 5 checklist item requires explicit order confirmation |
| (Part B) Ten-site conversion is large enough that a site is missed or half-converted | GB6/T-B5 is a per-site probe, not an aggregate count; milestone-by-milestone landing (§ 15) catches this incrementally instead of at the end |
| (Part B) New chance-node machinery changes `information_state_string`'s history encoding in a way that breaks F-011's completeness/leakage guarantees | GB4 re-runs INV-4a/4b explicitly, not just INV-1 |
| (Part B) Reshuffle-as-sequential-chance-nodes (D3) still leaves per-node branching above the paper's ≤4 assumption | Explicitly not this plan's problem — deferred to F-008, measured in Phase 4, tracked as its own ledger entry |
| (Part B) The estimated radius is optimistic — `engine_legal_moves`'s top-level dispatcher (referenced in D2) was not located during this investigation | Fixing agent must locate it before M1; if the dispatch structure makes D1/D2 materially harder than estimated, that is new information for a plan revision, not a reason to route chance events around the existing legal-moves/apply cycle (doing so would create a second, parallel action-application path) |

## 21. Out of scope

F-001, F-004 (done), F-005, F-006, F-008 (deferred, see § 17/19), F-009, F-010 (fix verified,
scope-rejected pending resubmission), F-011 (done), F-012, F-013, F-014 — each has its own verdict
condition, do not bundle. The engine's duplicate reshuffle implementation (§ 1(d),
`draw_cards_state` vs `reshuffle_discard_into_deck`) is noted but not unified beyond what Part B's
M1/M2 milestones naturally touch. `data/cards/*.json` card definitions are not modified by either
part — both are pure engine/binding-layer changes.
