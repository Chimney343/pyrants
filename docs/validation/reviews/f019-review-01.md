# F-019 Review 01 — Adversarial Review of the Rollout Placeholder-Move Filter

Reviewer role: adversarial, read-only outside `docs/validation/`. Did not write the fix.

## 0. LOAD

- **Target finding:** F-019 — "`engine_random_rollout` samples uniformly over unfiltered
  `engine_legal_moves()` output, so a UI-only `unavailable` placeholder move aborts 85-93% of
  rollouts onto a constant `{0,0}` leaf value instead of a real playout result." Class
  `OPENSPIEL-ISMCTS`. Severity **CRITICAL** (invalidates results — corrupts the majority of leaf
  values UCT backpropagates).
- **This finding did not exist in the ledger when this review began.** `git status` at session
  start showed a dirty working tree touching `engine_c/rollout.c`, `rollout.h`,
  `generic_runtime.c`, `generic_runtime.h`, `bindings/ce_api.py`, `openspiel_pyrants/state_c.py`,
  two test files, and one new test file — with `docs/validation/findings.md` and `verdict.md`
  both clean (not in `git status`), no `fNNN-fix-plan.md` for this defect, and no `.kilo/plans/
  *rollout*` entry. `findings.md` at `HEAD` runs F-001 through F-018; none of them is this defect
  (independently confirmed by reading the full file, not by grep alone). Per Hard Rule 3 there was
  no pre-registered falsification test to quote here. This is disclosed, not laundered: at owner
  direction (this review's operator explicitly chose "describe F-019 and include it in
  findings.md" over rejecting-and-handing-back or waiting for someone else to register it first),
  this reviewer wrote the F-019 entry into `findings.md` — Class/Severity/Code/Rulebook/
  Whitepaper/Disagreement/Steelman/falsification test/both Expected clauses/Status/Command/N/
  Observed/Verdict-rationale/Resolution — from direct reading of the diff plus a prior working
  session's own measurements (recorded in this reviewer's own persistent memory from a 2026-08-31
  / 2026-09-04 investigation), and only then began this review. **This is a standing deviation
  from Hard Rule 3**, carried as permanent debt on the verdict (§6), not resolved by this review.
- **Commit range:** working tree at `HEAD=2f6a0e7` (docs: F-006 Review 01 commit) + uncommitted
  diff. Not yet committed.
- **No `register.md` exists in this repo** (confirmed via `Glob`, same finding as every prior
  review in this ledger). `verdict.md` §1 is used as the register-equivalent throughout.
- **Prior review:** none — this is Review 01 for F-019 (a finding this same review session
  created).
- **Pre-registered falsification test** (quoted verbatim from `findings.md` F-019, as written by
  this review before the RE-RUN step — the debt above applies to this quotation's provenance,
  not to whether it was read before testing began):
  > Falsification test: from a representative 40-ply position on the runner's real setup
  > (`_build_ismcts_setup_json`, both 2-player and 4-player), run N rollouts through
  > `engine_random_rollout` (or its Python-replayed equivalent) at a range of `max_length` values
  > including large/unbounded, and record: the fraction reaching a true terminal state, the
  > specific rejection reason for every abort, and the reported score for aborted rollouts against
  > the true board state.
  > Expected if REAL: a large majority of rollouts abort specifically because `engine_apply`
  > rejected an `unavailable`-tagged `MOVE_RESOLVE_GENERIC` move drawn from the unfiltered
  > legal-moves list; raising `max_length` does not raise the terminal rate; the reported score for
  > aborted rollouts is `{0,0}` (or near-zero) independent of the true board state.
  > Expected if FALSE POSITIVE: rollouts reach terminal (or abort only via the step cap) at a high
  > rate regardless of `max_length`, and non-terminal scores vary with the true board state.

## 1. DIFF AUDIT

`git diff --stat` (working tree vs `HEAD`) touches 9 files:

| File | Classification | Notes |
|---|---|---|
| `engine_c/generic_runtime.c` | IMPLEMENTS-FINDING | exports `move_is_unavailable_placeholder`, factored out of the pre-existing reject-check inside `apply_resolve_generic_choice` (same behavior, no logic change) |
| `engine_c/generic_runtime.h` | IMPLEMENTS-FINDING | declares the new predicate |
| `engine_c/rollout.c` | IMPLEMENTS-FINDING | `#include "generic_runtime.h"`; filters placeholders out of the sampled-move array before picking; always calls `compute_final_scores` regardless of terminal; `ROLLOUT_HARD_STEP_CAP` 2000 → 4000 with a measured terminal-rate table in the new comment |
| `engine_c/rollout.h` | DOC-CHANGE | docstring updated to match the new filtering/scoring behavior |
| `engine_c/bindings/ce_api.py` | DOC-CHANGE | `CEngine.random_rollout`'s docstring updated to match |
| `openspiel_pyrants/state_c.py` | IMPLEMENTS-FINDING | `PyrantsCState.returns()` now always calls `self._adapter.final_scores()` instead of branching on `is_terminal()` with the same raw-`score`-field fallback — the Python-side mirror of the C fix, for any caller of `.returns()` at a non-terminal state (e.g. a `RandomRolloutEvaluator`-style playout) |
| `engine_c/tests/test_rollout.c` | TEST-CHANGE | file-header comment rewritten; `test_rollout_short_cutoff_scores_current_state` renamed + strengthened (injects `vp_tokens=7`, asserts `scores[0] >= 7` instead of the old `scores[i] == 0`); new `test_unavailable_placeholder_predicate` unit test |
| `tests/c_engine/test_rollout_binding.py` | TEST-CHANGE | module docstring updated; `test_random_rollout_short_cutoff_scores_current_state` renamed + strengthened (asserts raw score is `[0,0]` then the reported result is `{"p1":3,"p2":0}`, replacing the old tautological `{"p1":0,"p2":0}`) |
| `openspiel_pyrants/tests/test_rollout_reaches_terminal.py` (new, untracked) | TEST-CHANGE | 4 new tests against the runner's real two-half-deck market: terminal-rate, score-variance, and a "generator still emits placeholders" guard |
| `.claude/CLAUDE.md` | OUT-OF-SCOPE | Repowise auto-index metadata refresh (dates, hotspot percentiles, health scores) — no source/test/data content, not authored by the fix, not referenced by anything F-019 touches |

**No fix plan exists to authorize anything** (§0). This reviewer's own F-019 "Resolution" text
(written from the diff, before this section) covers exactly the 8 rollout/generic-runtime/state_c
files above; `.claude/CLAUDE.md` is the one hunk that text does not cover.

**`.claude/CLAUDE.md` disposition:** read in full (`git diff -- .claude/CLAUDE.md`). Every changed
line is index metadata — "Last indexed" date/commit, module-ownership table churn percentiles,
hotspot health scores — none of it touches `engine_c/`, `openspiel_pyrants/`, `tests/`, or
`docs/validation/`. This is Repowise's own background reindexing hook output, not a deliberate
addition by whoever wrote the rollout fix. Treated the same way `f006-review-01.md` treated its 4
out-of-scope `justfile` hunks: carried, not authored, by this fix — noted as debt (§6), not grounds
for `REJECTED-SCOPE` on its own, since it is inert with respect to F-019 and every other file in
this ledger.

**Gaming checklist (Hard Rule 4), run against each TEST-CHANGE hunk:**

| Hunk | Weakened assertion | Deleted/skipped test | Widened tolerance | Reduced N | Seed pinned to pass | Special-cased input | Swallowed exception | Removed invariant | Disabled warning |
|---|---|---|---|---|---|---|---|---|---|
| `engine_c/tests/test_rollout.c` (rename + `vp_tokens` injection) | clear — strengthened (`scores[i]==0` → `scores[0]>=7` with a real non-zero injected value) | clear | clear | clear | clear — seed `5ULL` byte-identical to before | clear | clear | clear | clear |
| `engine_c/tests/test_rollout.c` (`test_unavailable_placeholder_predicate`, new) | clear | clear | clear | clear | clear (no RNG in this test) | clear | clear | clear | clear |
| `tests/c_engine/test_rollout_binding.py` (rename + raw-vs-final assertion) | clear — strengthened (`{"p1":0,"p2":0}` → `{"p1":3,"p2":0}` with an explicit raw-score control proving the two rules are distinguishable) | clear | clear | clear | clear — seed `5` byte-identical to before | clear | clear | clear | clear |
| `openspiel_pyrants/tests/test_rollout_reaches_terminal.py` (new, 4 tests) | clear | clear | clear | clear | clear — seeds are fixture-construction seeds (42), not tuned to a specific pass | clear | clear | clear | clear |

Cleared, all 4 hunks. Every rename strengthens rather than weakens: the two renamed C/Python tests
previously asserted the *buggy* behavior as if it were correct (`scores == {0,0}`, tautological
against the old fallback), and now assert a real, non-trivial value that could only pass if
`compute_final_scores` is genuinely being called. `test_random_rollout_short_cutoff_scores_as_if_
ended_now`'s own docstring states the fixture was chosen so the two scoring rules are
distinguishable — verified independently in §4a, not merely trusted.

One `pytest.skip` guard exists in the new file (`_real_market_setup_json`, "needs at least two
full deck profiles") — an environment guard, not a defect-hiding one; confirmed 0-skip in §4a (all
4 new tests actually executed).

**Diff vs. plan:** no plan exists (§0), so this comparison is vacuous by construction — this
reviewer's own "Resolution" paragraph was written *from* this diff, so it trivially matches it.
Stated explicitly as a limitation, not silently passed over.

**Verdict of this step:** 1 out-of-scope hunk (`.claude/CLAUDE.md`, assessed as inert/carried, not
authored by the fix), 0 test-change hunks fail the gaming checklist.

## 2. CONFORMANCE REVIEW

**Rulebook:** `[absent]` — pure engine/search-mechanics concern, not a rules-conformance question.

**Whitepaper:** `docs/ismcts-paper.md:215`, § III-A Monte Carlo Tree Search: "Simulated games
select random actions until a terminal state is reached and the reward is averaged over multiple
simulations to estimate the strength of each action."

**What the code now does**, at the working-tree diff (`engine_c/rollout.c:36-74`):
```c
while (depth < cap) {
    if (engine_is_terminal(view)) break;
    int n = engine_legal_moves(view, moves, ROLLOUT_MOVE_BUFFER);
    if (n <= 0) break;
    int playable = 0;
    for (int i = 0; i < n; i++) {
        if (move_is_unavailable_placeholder(&moves[i])) continue;
        if (playable != i) moves[playable] = moves[i];
        playable++;
    }
    if (playable <= 0) break;
    int pick = (int)(rng_next(&rng) % (unsigned int)playable);
    GameState *next = engine_apply(view, &moves[pick]);
    if (!next) break;
    ...
}
...
compute_final_scores(view, scores_out);   /* always, terminal or not */
```
`openspiel_pyrants/state_c.py:171-190` (`PyrantsCState.returns()`) mirrors this: always
`self._adapter.final_scores()`, no non-terminal fallback branch.

**Verdict: CONFORMANT.** The paper's simulation step assumes a playout's reward reflects an actual
(or terminal-equivalent) outcome of "random actions" — actions the game actually permits. Sampling
uniformly over `engine_legal_moves()`'s raw output included moves `engine_apply` was guaranteed to
reject (a GUI-only affordance, never a legal game action), which is not "a random action" in the
paper's sense at all; filtering them restores the paper's assumption. The scoring change
(`compute_final_scores` unconditionally) does not itself have a paper citation — it is what makes
a cut-off rollout's reward meaningful, which the paper's own phrase "the reward is averaged...to
estimate the strength" presupposes.

## 3. BLAST RADIUS (derived independently)

Changed symbols: `move_is_unavailable_placeholder` (new), `apply_resolve_generic_choice` (behavior
-preserving refactor), `engine_random_rollout`, `ROLLOUT_HARD_STEP_CAP`, `PyrantsCState.returns()`.

**Included:**
- **The falsification test itself** (`openspiel_pyrants/tests/test_rollout_reaches_terminal.py`,
  `tests/c_engine/test_rollout_binding.py`, `engine_c/tests/test_rollout.c`) — direct target.
- **F-010 (determinism, CRITICAL, ACCEPTED-WITH-DEBT)** — `det_isolate.py`'s L4
  ("`adapter.random_rollout(seed)` x8: deterministic") calls `engine_random_rollout` directly, the
  exact function modified. Included, primary.
- **F-013 (board-projection timing, MINOR, ACCEPTED-WITH-DEBT)** — F-013's own gate is an
  end-to-end search wall-time ratio, and rollouts (now ~4.7× longer on the real market, per this
  session's memory of the fix's own prior measurements) are a large fraction of that wall time.
  Included: a defect elsewhere in the search's cost structure can move F-013's ratio even though
  F-013's own code (`c_adapter.py`) is untouched.
- **F-002 (shuffle-seed/counter reroll, CRITICAL, ACCEPTED)** — not a changed symbol, but rollouts
  now run far longer and so pass through many more mid-rollout reshuffle/forced-discard events than
  before; included as an exposure-risk check even though the mechanism itself
  (`engine_determinize`) is untouched.
- **Always-on regardless of radius (Hard Rule 4c):** replay determinism (INV-1), clone
  independence (INV-2), legality (INV-3), chance mass (INV-6).

**Excluded, with reason:**
- **F-001, F-004, F-005, F-006, F-007, F-009, F-011, F-014, F-015, F-016, F-017, F-018** — none
  reads or is read by `rollout.c`/`generic_runtime.c`'s placeholder-filtering or
  `PyrantsCState.returns()`'s scoring branch; each lives in `action_encoding_c.py`, `game_c.py`'s
  `GameInfo` declarations (F-004's own fix explicitly left `returns()`'s *body* untouched — this
  diff is the first to touch it, but only the already-excluded non-terminal branch, so F-004's
  terminal-only measurements are unaffected), seating logic, `run_ismcts.py` UCT defaults, a
  refuted claim, a hardcoded outcome count, `c_adapter.py`'s board-view merge, `actions.c`'s
  `give_insane_outcast`, `generic_runtime.c`'s Neogi double-fire (same file as this diff, but a
  different function — `end_of_turn_mass_discard`/`apply_end_of_turn_effects`, not
  `apply_resolve_generic_choice`/`legal_pending_generic_choice_moves`), or process-only ledger
  defects. Excluded.
- **INV-4a/4b (observation leakage/completeness), INV-5 (world-sampling diversity)** — these
  measure `private_view_json`/`determinize()` content, upstream of and independent from what a
  leaf-evaluation rollout does with a sampled world. Excluded.
- **F-003 (POSTPONED, ADR-0002)** — chance-node exposure is a distinct design question from how
  the (currently non-chance-node) rollout samples moves; this diff does not touch any of F-003's
  ten call sites' *exposure* as chance nodes, only how the rollout's uniform sampling treats one
  specific move-type's placeholder variant. Excluded.

**Comparison to a fixing-agent-declared radius:** none exists — there is no fix plan (§0), so there
is nothing to compare against. Stated as a limitation, not glossed over.

## 4. RE-RUN

All commands run from repo root, `.venv/Scripts/python.exe -u <path>` (or `pytest`), against the
working tree at `HEAD=2f6a0e7` + F-019's uncommitted diff, after `cmd /c engine_c\compile.bat`
succeeded cleanly (all 7 `test_rollout.c` assertions pass at the C level, including the new
`test_unavailable_placeholder_predicate`).

**a. Pre-registered falsification test**

| Check | Command | N / seeds | SHA | Prior (pre-fix, this session's own memory) | New (this review) |
|---|---|---|---|---|---|
| Rollouts reach terminal on the real market, 2p+4p | `pytest openspiel_pyrants/tests/test_rollout_reaches_terminal.py -v` | 4 tests, N=30 rollouts/case, 40-ply fixture, real two-half-deck market | working tree | 2p 15/300 (5%), 4p 6/40 (15%) terminal | **4/4 PASS** — `test_rollouts_reach_terminal_on_the_real_market[2]` and `[4]` both 30/30 terminal, 0 aborts |
| C-level cutoff scoring | `.\engine_c\test_rollout.exe` (via `just build-c`) | 1 fixture, seed 5 | working tree | `scores[i]==0` (old, tautological) | **PASS**: `scores[0] >= 7` (real `vp_tokens` injection now visible) |
| Python-binding cutoff scoring | `pytest tests/c_engine/test_rollout_binding.py -v` | 5 tests | working tree | `scores == {"p1":0,"p2":0}` (old) | **5/5 PASS**: `scores == {"p1":3,"p2":0}` |

✅ Falsification test: **matches "Expected if FALSE POSITIVE"** (post-fix) — rollouts reach
terminal at a high rate (100%, both player counts) regardless of the earlier abort pattern, and
non-terminal/cut-off scores now vary with true board state (`vp_tokens`/margin spread) rather than
collapsing to a constant. This is the correct post-fix reading: the finding's "Expected if REAL"
describes the *pre-fix* defect, which this run confirms is gone.

**b. Blast-radius checks**

| Check | Command | N | Prior | New |
|---|---|---|---|---|
| INV-1/2/3/6 (always-on battery) | `docs/validation/harness/inv_a.py` | 100/277/1200/30 | PASS/PASS/N=1200 0-0-0/N=30 0 (F-006 Review 01 baseline) | **PASS/PASS N=277/N=1200 0-0-0/N=30 0 — exact match** |
| F-010 B1 (fixed root, 10 identically-seeded bots) | `docs/validation/harness/det_bot.py` | num_sims 20 & 200, N=10 each | 1 distinct chosen action (both) | **1 distinct chosen action (both) — unchanged**; B2 root fingerprint intact; B3/B4 consistent |
| F-010 L1-L5 (layer isolation) | `docs/validation/harness/det_isolate.py` | N=10/10/5/8/8 | all PASS/deterministic | **all PASS/deterministic — unchanged** (L4 `random_rollout` x8: 1 distinct result, `{'p1':0,'p2':3}`, terminal=True) |
| F-013 timing gate (pre-registered `f011_timing.py`, Hard Rule 3) | `docs/validation/harness/f011_timing.py` | num_sims=200, N=10 searches, fixed 40-ply 2p root | mean_wall 0.2643-0.2755s, ratio 1.61-1.674× | **mean_wall 0.2735s, ratio 1.662× — still under the 2× gate, no measurable change** |
| F-002 shuffle-permutation invariant | `docs/validation/harness/f002b.py` | 8 controlled reshuffles | 8/8 same-perm-when-fixed, 8/8 changed-on-counter, 8/8 changed-on-seed | **8/8, 8/8, 8/8 — unchanged** |

**Caveat surfacing from this table (elevated to F-021, §5):** F-013's timing gate showed
essentially zero change despite the fix's own comments measuring rollouts ~4.7× longer on the real
market. Direct verification (ad hoc probe, `common.py::load(2)`, 20 seeds × up to 400 steps, 1,239
sampled states) found **0** states offering a placeholder move — this entire blast-radius table
(everything in this subsection) was measured on a fixture proven blind to F-019's defect class.
The falsification test itself (§4a) is unaffected, since it explicitly builds the real market.

**c. Always-on regardless of radius**

Identical commands/output to §4b's INV-1/2/3/6 row (same `inv_a.py` run) — not re-run separately.

**d. Previously-CONFIRMED findings inside the radius**

| Finding | Prior status | Re-run result |
|---|---|---|
| F-010 | ACCEPTED-WITH-DEBT (F-012 open) | `det_bot.py`/`det_isolate.py` unchanged (§4b) |
| F-013 | ACCEPTED-WITH-DEBT (residual ~1.66-1.674× regression) | `f011_timing.py` unchanged (§4b) — but see the F-021 caveat above: this check does not exercise F-019's fixed code path |
| F-002 | ACCEPTED (Review 02) | `f002b.py` unchanged (§4b) |

**e. Regression sweep beyond the declared radius**

| Command | N | Result |
|---|---|---|
| `pytest openspiel_pyrants/tests/ -q` | ~92 collected (78 prior + 4 new F-019 tests, approx.) | 10 FAILED, matching the documented ADR-0002-postponed F-003 Part B RED set by name exactly (`test_forced_discard_is_chance_node`, `test_reshuffle_is_chance_node_sequence`, `test_chance_outcome_application_matches_legacy_rng_path`, `test_site_draw_cards_state_is_chance_node`, `test_site_apply_force_discard_is_chance_node`, `test_site_neogi_mass_discard_is_chance_node`, `test_site_chuul_local_discard_is_chance_node`, `test_site_nothic_mass_discard_is_chance_node`, `test_site_mindwitness_conditional_owner_discard_is_chance_node`, `test_site_reshuffle_discard_into_deck_is_chance_node`); final summary-line count dropped by the same pre-existing pytest-teardown quirk `f013-review-03.md` already documented ("chance-node teardown also drops pytest's final counts line in this environment") — reproduced identically here, not new |
| `pytest tests/c_engine -q` | full collection | 2 FAILED: `test_card_zuggtmoy.py::test_zuggtmoy_eot_promote_two_other_cards_excludes_self`, `test_engine_c.py::test_air_elemental_option_1_focus_draw` — both the documented tolerated baseline, unchanged |
| `pytest -q --tb=no` (repo root) | full suite | 6 FAILED: the 3 documented tolerated (Zuggtmoy, Air Elemental, Neogi/F-015) **plus 3 new**: `tests/test_replay_loader.py::test_load_replay_real_artifact_setup_sha_matches`, `tests/test_replay_player.py::test_full_replay_is_deterministic`, `tests/test_replay_player.py::test_total_steps_excludes_terminal_sentinel` |

**Investigating the 3 non-baseline failures (F-018's own `test_decision_at_matches_step` now
passes — not in this list at all, an unrelated improvement, not investigated further per Hard Rule
5):** all three assert `assert 1308 == 517` — a recorded-artifact step count. `interface/
replay_player.py`/`replay_loader.py` are absent from `git diff --stat` (§1) — this diff touches
neither. Isolated via `git worktree add --detach ../pyrants-f019-baseline HEAD` (a clean checkout
at the same commit, no working-tree diff, built independently with its own `engine_c.dll`):

```
clean worktree (HEAD, no local artifacts/):        all 3 tests SKIP (GAME_DIR absent — artifacts/
                                                     is gitignored, .gitignore:235, not tracked)
main working tree (same HEAD + F-019 diff):         3 FAILED, assert 1308 == 517
```
`artifacts/ismcts/game_0000/{steps.jsonl,replay.json}` mtime: `2026-09-04` (today), a locally
regenerated recording this review did not create and the diff does not touch. **Confirmed: not a
regression attributable to this diff.** Worktree removed after verification
(`git worktree remove --force`). Filed as F-022 (§5) rather than left as an unexplained anomaly.

**No regression attributable to this diff.** F-021 and F-022 are both real gaps, both filed, and
both independently proven not to implicate F-019's own correctness.

## 5. NEW FINDINGS

Three, all appended to `findings.md` with the full schema (Class/Severity/Origin/Code/Rulebook/
Whitepaper/Disagreement/Steelman/falsification test/both Expected clauses/Status/Command/N/
Observed/Verdict-rationale) and to the summary table:

1. **F-020** (ENGINE, MINOR) — `engine_c/tests/test_rollout.c`'s file-header comment claims a
   post-fix unbounded rollout from a fresh 2p state reaches genuine terminal; the file's own test
   (`test_rollout_unbounded_completes_within_time_bound`) and a live run
   (`terminal=0`, cap hit) contradict it. Cosmetic, no behavioral effect.
2. **F-021** (VALIDATION-PROCESS, MAJOR) — `docs/validation/harness/common.py::load()` defaults to
   `data/decks/base_setup.json`'s 10-card market, independently confirmed (1,239 sampled states,
   0 placeholder moves) to never exercise F-019's defect class; essentially the entire harness
   battery, including this review's own §4b/d table, is blind to this class of defect on the
   runner's real production market.
3. **F-022** (VALIDATION-PROCESS / test-design, MODERATE) — `test_replay_player.py`/
   `test_replay_loader.py` hardcode exact values against the gitignored, locally-mutable
   `artifacts/ismcts/game_0000`; a locally-regenerated recording fails all three tests with no
   git-diff-visible cause. Proven (§4e) not attributable to F-019's diff.

**Count: 3 new findings.**

## 6. VERDICT

**ACCEPTED-WITH-DEBT** — four items:

1. **Hard Rule 3 deviation on F-019's own registration (§0).** The finding and its falsification
   test were both written by this reviewer, from the diff plus a prior session's own measurements,
   after the fix already existed in the working tree. This is exactly the failure mode Hard Rule 3
   exists to prevent, done at explicit owner direction rather than by reviewer error. The
   falsification test nonetheless passed against real, independently-executed evidence (§4a) — the
   new Python test file builds the runner's actual market and measures a real terminal-rate jump —
   so this is not a rubber stamp, but the provenance debt is permanent and should not be read as an
   ordinary pre-registered CONFIRMED finding in any future citation.
2. **F-021: the blast-radius re-run in §4b/d does not cover the code path that matters.** Every
   check in that table except the falsification test itself ran on a market fixture proven to never
   trigger a placeholder move. The *correctness* claim (rollouts now reach genuine terminal) is
   solidly validated on the real market. The *zero-regression* claim (determinism, timing, world
   sampling) is not — it is validated only on a fixture this fix's own defect never touched, so it
   is silent on whether the fix disturbs anything under real conditions. F-013's "no timing change"
   result in particular should be read as "no timing change on a fixture where none was expected,"
   not as evidence the ~3.1× real-market slowdown documented in the fix's own comments is safe.
3. **One out-of-scope hunk** (`.claude/CLAUDE.md`), assessed as inert Repowise tooling noise, not
   scope creep — same disposition F-006 Review 01 gave its 4 carried `justfile` hunks.
4. **F-020/F-022 open**, both low-consequence and independently confirmed not to implicate F-019's
   own correctness (F-020 is a comment-precision nit; F-022 is proven pre-existing local-environment
   drift, not a defect in this diff).

Every other Hard Rule 8 component the fix can satisfy, it does: conformance is CONFORMANT (§2),
the pre-registered falsification test PASSes on the configuration that actually matters (§4a), and
zero regressions were found anywhere this diff's own code is exercised (§4b/e, including the
non-obvious near-miss in §4e that turned out to be pre-existing local drift, not a regression).
This is the same shape of debt this ledger has accepted before (`f011-review-01.md`'s failed G5
gate, `f013-review-01.md`'s unmet G4 gate) — a real, correctly-scoped, behavior-verified fix that
ships with named, disclosed gaps rather than a false claim of completeness.

## 7. INVALIDATION CASCADE

Applying Hard Rule 4c ("any STRENGTH row ... goes STALE on ANY change to the engine, the binding,
the observation, the utilities, or the search") to `verdict.md` §1:

**Already STALE, unaffected by this review (no double-invalidation):**
- INV-7 (budget monotonicity), INV-8 (self-play calibration), INV-9 (baseline sanity) — marked
  STALE by `f010-review-01.md`, reaffirmed by every subsequent engine/binding/search-touching
  review in this ledger. This fix is a further independent trigger (`engine_c/rollout.c`, "the
  engine"; `openspiel_pyrants/state_c.py::returns()`, "the utilities"/"the search" leaf value) —
  already correctly excluded from citation; no new STALE marking needed.

**Newly STALE (this review, first invalidation):** None. No other STRENGTH row exists in
`verdict.md` §1 beyond INV-7/8/9.

**Additionally noted (not a STALE marking, a scope caveat on the whole §5 GO block):** F-021
establishes that the harness battery underlying every STRENGTH-adjacent measurement in this ledger
has never exercised modal-choice-dependent behavior on the real market. This does not newly
STALE any row (INV-7/8/9 were already STALE for independent reasons, and no other row claims
strength), but it is recorded as a caveat on `verdict.md` §5's GO conclusion (added there directly,
per RECORD below) since that conclusion predates F-019 through F-022 entirely.

**Count: 0 newly-STALE rows.**

## 8. RECORD

This file. `findings.md` carries the F-019/F-020/F-021/F-022 entries (summary table + full write-
ups) this review authored/reviewed. `verdict.md` §2 carries F-019's RESOLVED entry plus this
review's block; `verdict.md` §5 carries a caveat note ahead of the existing 🟢 GO text, not a
rewrite of it (Hard Rule 7).

## 9. HANDOFF

**ACCEPTED-WITH-DEBT.** Debt, in priority order: (1) F-021 — before trusting any future
blast-radius re-run's "no regression" conclusion for rollout- or modal-choice-adjacent code, verify
it did not silently run on `base_setup.json`; the harness needs a real-market `load()` variant or
an explicit fixture-coverage check, neither of which exists yet; (2) the real-market ~3.1× search
wall-time cost this fix's own comments document is unmeasured by any gate in this ledger — no
action demanded by this review, but no throughput/performance claim should be made against the
current numbers without re-measuring on the real market; (3) F-019's own Hard-Rule-3 registration
debt (§6.1), permanent; (4) F-020/F-022, both low-priority, independently confirmed non-blocking.

**Next finding in recommended order:** F-021 itself is the natural next target — it is MAJOR,
OPEN, newly raised by this very review, and (unlike F-019) has a clean pre-registered falsification
test with no Hard Rule 3 debt attached, since it was filed before any fix for it exists.

**Blocking findings remaining:** this review does not attempt to recompute `verdict.md` §5's
blocking-condition list (that section predates F-019 and is explicitly not rewritten here, only
caveated — §7/§8). At minimum, F-021 (MAJOR, OPEN) and F-022 (MODERATE, OPEN) are new open items
not previously counted anywhere in that section.

STOP. Not beginning the next finding; not touching source.
