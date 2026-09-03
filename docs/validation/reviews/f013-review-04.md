# F-013 Review 04 — Uncommitted working-tree diff reopens the withdrawn C-level accessor

Reviewer role: adversarial, read-only outside `docs/validation/`. Did not write this diff. F-013
is currently **closed** (`CONFIRMED — FIXED`, Review 03, `docs/validation/reviews/f013-review-03.md`,
ACCEPTED at commit range ending `63435fa`). This review was triggered because the working tree at
invocation time carries an **uncommitted** change to `engine_c/scoring.c`, `engine_c/scoring.h`,
and `engine_c/view.c` that, per the requester, reopens F-013 by building exactly the narrower
C-level accessor that `docs/validation/f013-part-b-fix-plan.md` § 9 explicitly withdrew
("Recommendation: do not build it").

## 0. LOAD

- **Target finding:** F-013 — "Board projection regresses `private_view_json` cost 9.66×; Part A
  cache + Part B cheap pure-Python projection close the residual." Class `ENGINE-OPENSPIEL`.
  Severity **MINOR** (performance). Status at load time: **CONFIRMED — FIXED**, closed by Review 03.
- **`register.md` does not exist in this repo** (confirmed via repo-wide glob) — this project folds
  STALE-tracking into `verdict.md` §1's invariant-battery table instead. Treated as the operative
  register throughout, consistent with Reviews 01-03's own practice.
- **Commit range under review:** none — this is an **uncommitted working-tree diff** on top of
  `HEAD 63435fa` (the commit that recorded Review 03's ACCEPTED closure). No fix plan, no commit,
  no `findings.md`/`verdict.md` entry exists for this diff.
- **Falsification test, quoted verbatim from `findings.md` F-013:**
  > Falsification test: `python -u docs/validation/harness/f011_timing.py` before/after, compare
  > mean wall-time.
  > Expected if REAL: mean wall-time ratio > 2×.

  (F-013's original entry states only this one expectation; no paired "Expected if FALSE POSITIVE"
  line exists in `findings.md` for this finding — quoted as written, not supplemented.)
- **Governing constraint being tested, quoted verbatim from `f013-part-b-fix-plan.md` § 9:**
  > "Recommendation: do not build it. Revisit only if Phases 2-5 land and profiling then shows
  > `engine_build_view` among the top costs, which § 1.1 makes very unlikely."
  and Gate G0: "**Zero** diff in `openspiel_pyrants/*.py` (non-test), `scripts/`, `engine_c/*.c`,
  `.venv/`."

## 1. DIFF AUDIT

`git diff` (working tree vs `HEAD`) touches, in full:

| File | Hunk | Classification |
|---|---|---|
| `engine_c/scoring.c` | new `site_control_owner_at(state, node_index)` — extracted body of the old `site_control_owner` loop, taking an index instead of scanning for `node_id` | OUT-OF-SCOPE |
| `engine_c/scoring.c` | new `is_total_control_at(state, node_index, player_id)` — same extraction | OUT-OF-SCOPE |
| `engine_c/scoring.c` | `site_control_owner()` body replaced with a `node_id`-scan loop that calls `site_control_owner_at` | OUT-OF-SCOPE |
| `engine_c/scoring.c` | `is_total_control()` body replaced the same way | OUT-OF-SCOPE |
| `engine_c/scoring.h` | declares the two new `_at` functions, with a comment asserting index-alignment between `state->nodes[]` and `board.nodes[]` | OUT-OF-SCOPE |
| `engine_c/view.c` | `engine_build_view`'s per-site loop switched from `site_control_owner(state, nd->node_id)` / `is_total_control(state, nd->node_id, ...)` to the `_at` variants with the loop's own index `i` | OUT-OF-SCOPE |
| `interface/game_viewer.py` | adds `autostart` constructor param, `_suppress_score_dialog` flag, extracts `_build_control_bar()` | **NOT PART OF F-013 AT ALL** — no shared symbol, no shared file, no shared code path. This is scaffolding for the untracked `interface/replay_viewer.py` (a `GameViewerApp` subclass, matching `.kilo/plans/1788388431546-ismcts-replay-viewer.md`), a wholly separate, unrelated line of work sitting in the same dirty working tree. Flagged as tree contamination, not folded into this finding's hunk table below. |

**Test-change gaming checklist (Hard Rule 4):** N/A — **zero test files were touched by this diff**.
There is no weakened assertion, deleted test, widened tolerance, reduced N, seed-pinning, or
special-cased input to check, because no test exists for the new `_at` functions at all. That
absence is itself a violation: `f013-fix-plan.md` § 0 and `f013-part-b-fix-plan.md` § 0 both carry
forward "Test-driven design is mandatory. Every behavioural change starts as a failing test" as a
process constraint on any change to this finding, and no RED test precedes this one.

**Diff vs. plan:** There is no fix plan for this diff — no `f013-part-c-fix-plan.md` or equivalent
exists (confirmed: no untracked or committed file references a new C-level accessor effort). The
only applicable plan is `f013-part-b-fix-plan.md`, and it explicitly **forbids** this exact class of
change: G0 requires zero diff in `engine_c/*.c`, and § 9 recommends against building any C-level
accessor, with the reasoning re-verified below (§ 2) rather than trusted from the plan text.

**Every `engine_c/scoring.c`/`scoring.h`/`view.c` hunk is OUT-OF-SCOPE** — F-013 is closed, its own
closing plan's G0 forbids `engine_c/*.c` changes, and no other plan authorizes this diff. Per the
DIFF AUDIT rule, this alone is dispositive: **REJECTED-SCOPE**.

## 2. CONFORMANCE REVIEW

**Rulebook / Whitepaper:** `[absent]` — unchanged posture from Reviews 01-03: F-013 is a pure
engine-binding performance concern with no rules or paper anchor to violate.

**What the code now does**, independently verified at `file:line` rather than trusted from the
added comment:

- `engine_c/scoring.c:12-41` — `site_control_owner_at(state, node_index)`: reads
  `state->nodes[node_index]` directly (no `node_id` scan), otherwise byte-identical logic to the
  pre-existing tally-and-tiebreak loop.
- `engine_c/scoring.c:55-61` — `site_control_owner(state, node_id)` is now a thin wrapper: scans for
  the matching `node_id`, then calls `site_control_owner_at` with the found index. Same for
  `is_total_control` (`scoring.c:63-69`).
- `engine_c/view.c:95,100` — `engine_build_view`'s per-site loop (which already iterates
  `board->nodes[i]` and, immediately above at lines 61-85, already zips `state->nodes[i]` with
  `board->nodes[i]` under the *same*, pre-existing, unmodified index `i`) now calls
  `site_control_owner_at(state, i)` / `is_total_control_at(state, i, ...)` directly, skipping the
  `node_id`-scan `site_control_owner`/`is_total_control` would otherwise repeat.

**Independent verification of the index-alignment claim** (not trusted from `scoring.h`'s added
comment): `engine_c/state.c:101-105` constructs `gs->nodes[i]` from `def->board.nodes[i]` in the
same loop, for the same `i`, at `GameState` creation — `state->nodes[]` and
`state->definition->board.nodes[]` are index-aligned for the life of a `GameState`. This is not a
new assumption the diff introduces: the unmodified code immediately above the changed lines
(`view.c:61-85`) already relies on it to zip `ns`/`nd` pairs by index. The diff's callers
(`compute_final_scores`, `award_end_of_turn_site_vp`, `helpers.c:233`, `player_view.c:49`) were
grepped and confirmed **unchanged** — they still call `site_control_owner`/`is_total_control` by
`node_id`, so their behavior is untouched by this diff; only `engine_build_view`'s internal call
site changed.

**Verdict: CONFORMANT** — the change is a behavior-preserving extract-and-specialize refactor, and
this is corroborated by the RE-RUN evidence below (§ 4), not merely by reading the diff.
**Correctness does not cure the scope violation found in § 1.**

## 3. BLAST RADIUS

**Included, with reason:**
- **F-013** (direct target — the change touches `engine_build_view`'s per-site cost, the exact
  function F-013's Part B measured).
- **INV-4b** (`private_view_json` board completeness) — `engine_build_view` populates the `nodes[]`
  array `_board_nodes_view` reads; a behavior change here would show up as a board-content diff.
- **F-011's byte-identity surface** (`test_board_projection.py` T1/T2, G1) — same reasoning; this is
  the most sensitive test to a `view.c` regression.
- **Always-on:** INV-1/2/3/6 (replay determinism, clone independence, legality, chance mass).

**Excluded, with reason:**
- **F-014** (`insane_outcast` supply cap) — no shared symbol; F-014 lives in `actions.c`/`helpers.c`
  special-stack accounting, untouched here.
- **F-002/F-010** (shared reshuffle stream / determinization seeding) — no RNG, `shuffle_seed`, or
  `shuffle_counter` code path is touched. Ran `det_bot.py`/`f002b.py` anyway as cheap, out of an
  abundance of caution — zero regression (§ 4).
- **F-003/F-005/F-006/F-007/F-008/F-009/F-012/F-015** — no shared code path with
  `site_control_owner`/`is_total_control`/`engine_build_view`.
- **INV-7/8/9 (STRENGTH rows)** — already STALE since Review 01; not re-measured per-fix by
  convention, and this diff is being rejected rather than merged, so no new staleness trigger
  applies (see § 7).

**Wider than the fixing party's declared radius:** no radius was declared for this diff — it has
no fix plan, no author-side write-up, and no `findings.md` entry. There is nothing to compare
against; this absence is itself part of the § 1 scope finding.

## 4. RE-RUN

Working tree rebuilt via `just build-c` (recompiles `libengine.lib`, all seven C test binaries, and
`engine_c.dll` against the uncommitted diff) before every check below, at commit `63435fa` + this
uncommitted diff.

**a. Pre-registered falsification test**

| Command | N | Seeds | SHA | Prior (Review 03) | New |
|---|---|---|---|---|---|
| `.venv/Scripts/python.exe -u docs/validation/harness/f011_timing.py` | 10 searches, `num_sims=200` | fixed root (seed 42) + bot (seed 131) | `63435fa` + uncommitted diff | `f013b_timing.post.txt` mean **0.2643 s** (1.61× vs. 0.1646 s) | mean **0.2755 s** (10 per-search values: 0.3774, 0.24, 0.2985, 0.2608, 0.2759, 0.2907, 0.2726, 0.27, 0.219, 0.2498) → **1.674× vs. the pre-F-011 0.1646 s baseline** |

✅ PASS — still comfortably under the 2× gate and far under the finding's own `> 2×` "Expected if
REAL" threshold. The 0.2755 s vs. 0.2643 s difference is run-to-run wall-clock variance of the same
kind the ledger already documents between Review 01 (6.42×) and Review 02 (6.87×) — not evidence of
a measurable speedup from this diff. **No claim of additional improvement is made.**

**b. Blast-radius invariant**

| Check | Command | N | Prior | New |
|---|---|---|---|---|
| INV-4b (board-differing pairs) | `harness/inv_b2.py` | 400 same-move-type/different-site pairs | 403/403 differ, 0 identical (Review 03 corpus) | **400/400 differ, 0 identical** — exact match in kind (corpus size varies run-to-run by design, never a failure) |
| G1 byte-identity (T1-T12) | `pytest openspiel_pyrants/tests/test_board_projection.py -q` | 12 tests | 12/12 PASS | **12/12 PASS** |

**c. Always-on battery**

| Check | Command | N | Prior | New |
|---|---|---|---|---|
| INV-1 replay determinism | `harness/inv_a.py` | 100 seed-paired games | PASS | **PASS** |
| INV-2 clone independence | `harness/inv_a.py` | 277 probes | PASS | **PASS** |
| INV-3 legality | `harness/inv_a.py` | 1,200 states | 0 empty/dup/oor | **0 empty/dup/oor** |
| INV-6 chance mass | `harness/inv_a.py` | 30 chance nodes | 0 violations | **0 violations** |
| INV-4a leakage | `harness/inv_b.py` | 300 info sets | 0 violations | **0 violations** |
| INV-5 determinization | `harness/inv_b.py` | 200×K=12=2,400 | mean 11.48/12 min 8 (Review 03's own environmental figure) | **mean 11.48/12 min 8, 0 conservation violations/2,400, 0 history mismatches** — exact match |

**d. Previously-CONFIRMED findings in blast radius (F-010, F-002 — run out of caution, § 3)**

| Check | Command | Prior | New |
|---|---|---|---|
| F-010 `det_bot.py` B1 | `harness/det_bot.py` | 1 distinct chosen action | **1 distinct chosen action** (B1-B4 all consistent) |
| F-002 `f002b.py` | `harness/f002b.py` | 8/8 controlled reshuffles | **8/8 controlled reshuffles** |

**e. Regression sweep**

| Command | Result |
|---|---|
| `just build-c` | Full rebuild succeeded; all 7 C suites (`test_engine`, `test_view` incl. `build_view_board_nodes`, `test_describe`, `test_generic_actions`, `test_saveload`, `test_catalog_assembly`, `test_rollout`) **PASS** |
| `.venv/Scripts/python.exe -m pytest openspiel_pyrants/tests/ -q` | Only the 10 pre-existing postponed F-003 Part B RED failures (`test_chance_nodes.py`), same file/count as every prior review's baseline. Pytest's final counts line is dropped at teardown in this environment — the documented, pre-existing quirk, not new. |
| `.venv/Scripts/python.exe -m pytest -q` (repo root) | Same 3 pre-existing failures (`test_card_zuggtmoy.py::test_zuggtmoy_eot_promote_two_other_cards_excludes_self`, `test_engine_c.py::test_air_elemental_option_1_focus_draw`, `test_card_neogi.py::test_neogi_execution_model_deploys_four_and_random_mass_discard`), **plus one failure not in any prior baseline**: `tests/test_replay_player.py::test_decision_at_matches_step`. See note below — **not attributed to this diff.** |

**Note on the 4th repo-root failure:** `tests/test_replay_player.py` is itself an untracked,
uncommitted file (`git status` shows `?? tests/test_replay_player.py`), part of the same dirty
working tree's unrelated replay-viewer work-in-progress (§ 1's `interface/game_viewer.py` row), not
part of F-013's diff and sharing no code path with `scoring.c`/`view.c`/`site_control_owner`. Per
Hard Rule 3 (only the pre-registered F-013 test governs this review) and the review's charter (one
finding at a time), this is reported as an observation for the record, not filed as a new finding
and not investigated further — it is a broken test for a not-yet-existing feature, outside this
ledger's rules/engine-conformance domain.

**No regression found against F-013's own accepted baseline. No invariant reversed. No previously
CONFIRMED finding disturbed.** This is not a REJECTED-REGRESSION case.

## 5. NEW FINDINGS

None filed. (The `tests/test_replay_player.py` failure noted in § 4e is an observation about
unrelated, uncommitted, out-of-domain WIP — not a rules/engine conformance defect — and is not
investigated further, per instruction.)

## 6. VERDICT

**REJECTED-SCOPE.**

The change is behaviorally correct (§ 2, § 4) and introduces no regression, but it is not
authorized by any fix plan, violates the closing plan's own G0 gate
(`f013-part-b-fix-plan.md`: "Zero diff in ... `engine_c/*.c`"), reopens a recommendation that plan's
§ 9 explicitly withdrew with measured justification ("do not build it"), skips the mandatory
test-first process constraint carried by both F-013 fix plans, and targets a finding that is
already closed (`CONFIRMED — FIXED`, Review 03, ACCEPTED). Per Hard Rule 1, correctness does not
convert an unauthorized change into an acceptable one — the reviewer's job here is to reject and
hand back, not to retroactively author the missing plan.

## 7. INVALIDATION CASCADE

**Already STALE, unaffected:** INV-7/8/9 (STRENGTH rows, stale since Review 01).

**Newly STALE:** none. This diff is rejected and, per this review's recommendation, is not going
into the codebase as-is; it therefore does not trigger the "any change to the engine ... goes
STALE" cascade for STRENGTH rows. If this diff (or an authorized version of it) is later merged,
the standard cascade applies at that point and INV-7/8/9 remain the rows to re-measure at the final
gate — they are not newly implicated beyond their existing staleness.

**Count: 0.**

## 8. RECORD

This file. `findings.md` F-013 gets a new `Review 04` line (REJECTED-SCOPE, no status change — the
finding stays `CONFIRMED — FIXED` as Review 03 left it, since nothing here is being merged).
`verdict.md`'s F-013 entry gets a corresponding one-line addition; no other section of `verdict.md`
changes, and the GO/NO-GO block is unaffected since F-013 was already non-blocking and remains so.

## 9. HANDOFF

**REJECTED — numbered list of what must change before resubmission:**

1. Write a fix plan (e.g. `f013-part-c-fix-plan.md`) that explicitly supersedes
   `f013-part-b-fix-plan.md` § 9's "do not build it" recommendation, with fresh measurement
   justifying why the withdrawal no longer holds — anchored to hunk: all of
   `engine_c/scoring.c`/`scoring.h`/`view.c`.
2. Get the plan's own G0-equivalent gate to explicitly permit `engine_c/*.c` changes for this
   round, since the current, still-controlling G0 forbids them — anchored to hunk: same three
   files.
3. Write RED tests for `site_control_owner_at`/`is_total_control_at` before the GREEN
   implementation, per both existing F-013 plans' mandatory TDD constraint — anchored to: the
   complete absence of any test change in this diff (§ 1).
4. Either commit `interface/game_viewer.py`'s changes under its own, unrelated finding/feature
   (it has nothing to do with F-013) or leave it out of any F-013 resubmission entirely — anchored
   to hunk: `interface/game_viewer.py` (§ 1).
5. Resubmit through the standard fix → review cycle; do not land uncommitted C-engine changes
   against an already-closed, ACCEPTED finding without a plan.

**Acceptance condition restated verbatim (from `findings.md` F-013):** "Falsification test:
`python -u docs/validation/harness/f011_timing.py` before/after, compare mean wall-time. Expected
if REAL: mean wall-time ratio > 2×." (I.e., for this residual work to matter at all, a future
resubmission needs to show it addresses a measured cost that Part B's own § 9 measurement — 3.1 µs
of ~400 µs — found not worth pursuing; that measurement was not re-opened or refuted here and would
need to be, in the new plan, before implementation resumes.)

STOP. Not touching source; not filing a plan on the fix author's behalf.
