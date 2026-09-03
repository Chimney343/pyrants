# F-010 Review 02 — Adversarial Review of the Scope-Resolution Re-submission

Reviewer role: adversarial, read-only outside `docs/validation/`. Did not write the fix or the
prior review.

## 0. LOAD

- **Target finding:** F-010 — "ISMCTS determinization seeds come from an unseeded RNG, so runs
  are not reproducible." Class `OPENSPIEL-ISMCTS`. Severity **CRITICAL** (invalidates
  reproducibility of every reported result).
- **Prior review:** `docs/validation/reviews/f010-review-01.md` (commit `028ff9d`):
  **REJECTED-SCOPE**. The fix logic itself was found CONFORMANT with zero regressions, but the
  commit bundled 4 unauthorized hunks (3 dead-script deletions absent from the plan's 7-site
  table, plus a new, plan-external `docs/validation/grug_findings.md`) and was rejected on that
  basis alone (Hard Rule 8: zero out-of-scope hunks required for ACCEPTED).
- **Commit range:** `028ff9d` (Review 01's target) → `2cfd836` ("resolve F-010 review scope
  findings: authorize dead-script deletions, drop grug_findings.md") → current `HEAD`
  (`74f2be31716712d5fb9385c2a524b8747dba3b9e`, 2026-09-02 11:02:58 +0200). Independently
  confirmed via `git diff 028ff9d HEAD --stat -- openspiel_pyrants/state_c.py
  openspiel_pyrants/ismcts_factory.py scripts/run_ismcts.py openspiel_pyrants/__init__.py
  openspiel_pyrants/tests/test_ismcts_reproducibility.py
  openspiel_pyrants/tests/test_ismcts_smoke_c.py openspiel_pyrants/tests/test_determinize_c.py
  openspiel_pyrants/tests/test_c_rollout_evaluator.py` → **empty output**: every production and
  test file the fix logic touches is byte-identical between the reviewed commit and current
  `HEAD`. The only thing that changed since Review 01 is the scope/process objection itself, via
  `2cfd836`. This review evaluates `2cfd836` as the re-submission, not a re-audit of unchanged
  fix logic.
- **Working tree:** clean except `.claude/CLAUDE.md` (unrelated, pre-existing, confirmed via
  `git status`).
- **Pre-registered falsification test** (quoted verbatim from `findings.md` F-010, unchanged
  since Review 01):
  > Falsification test: run the same seed, same policy, twice, and compare action sequences and
  > terminal returns; then re-run a single search from one fixed, unmutated root with an
  > identically seeded fresh bot.
  > Expected if REAL: identical seeds produce different action sequences and different returns;
  > a fixed root yields different chosen actions across identically seeded searches.
  > Expected if FALSE POSITIVE: identical seeds reproduce the game exactly.

## 1. DIFF AUDIT

`git show 2cfd836 --stat`: 5 files changed, 397 insertions(+), 95 deletions(-). Read in full
(not summarized from the commit message). Hunk-by-hunk classification:

| File | Classification | Notes |
|---|---|---|
| `docs/validation/f010-fix-plan.md` (+10) | DOC-CHANGE (scope remediation) | adds a "Decision record — 3 additional dead scripts (post-review, owner-approved)" section, explicitly naming `check_clone_attrs.py`, `check_ismcts_chain.py`, `trace_clone.py`, re-confirming the no-hits grep, and stating the owner accepts the deletions |
| `docs/validation/findings.md` (+21) | DOC-CHANGE | appends F-010's Review 01 verdict block (per Rule 8 record format) and the full F-012 entry Review 01 raised |
| `docs/validation/grug_findings.md` (-85, deleted) | DOC-CHANGE (scope remediation) | the file Review 01 flagged as unauthorized is removed from the tree entirely |
| `docs/validation/reviews/f010-review-01.md` (+336, new) | DOC-CHANGE | the Review 01 record itself, committed here (Hard Rule 1: reviewer's only writes are inside `docs/validation/`) |
| `docs/validation/verdict.md` (+40/-10) | DOC-CHANGE | flips the F-010 verdict-summary language to "FIX LOGIC VERIFIED, COMMIT REJECTED-SCOPE", marks INV-7/8/9 STALE, records the Review 01 citation |

**Zero production-code hunks. Zero test-file hunks.** No `TEST-CHANGE` row exists, so the Hard
Rule 4 gaming checklist has nothing to run against — recorded as N/A, not silently skipped.

**Diff vs. the two Review 01 handoff items, checked literally:**
1. *"Either revert the deletion of `check_clone_attrs.py`/`check_ismcts_chain.py`/`trace_clone.py`,
   or amend `f010-fix-plan.md` with an explicit decision record authorizing these 3 additional
   deletions."* — The plan was amended (§ above). Independently re-verified the amendment's own
   factual claim rather than trusting it: `grep -rn "check_clone_attrs|check_ismcts_chain|trace_clone"`
   across the working tree at `HEAD`, excluding `.venv/`, returns **zero hits** — confirming the
   3 scripts remain genuinely unreferenced dead code, the same claim Review 01 already
   independently verified and the plan amendment now restates. **Satisfied.**
2. *"Remove `grug_findings.md` from this diff ... or add it to the plan's scope explicitly."* —
   Neither literal option (git history is append-only, so "removing from the diff" of an already-
   merged commit is impossible) but the substantively equivalent action was taken: the file is
   deleted outright. Confirmed via `git cat-file -e HEAD:docs/validation/grug_findings.md`, which
   fails ("does not exist") — the file is genuinely gone from the tree, not merely edited.
   **Satisfied**, by the stronger of the two offered remedies (full removal, not re-scoping).

**Nothing beyond the two handoff items was touched.** `git diff 028ff9d HEAD --stat` (full,
unfiltered) shows exactly the 5 files above plus files attributable to the *other*, later, and
already-independently-reviewed fixes (F-011, F-002, F-013, F-004, and F-003 Part B's RED-test
scaffolding) — none of which this review's independent per-file diff check (§0) found any
overlap with F-010's own production/test surface.

**Verdict of this step:** 0 out-of-scope hunks in `2cfd836` itself, and — checked directly rather
than assumed — 0 out-of-scope files remain in the cumulative `f16799e..HEAD` diff for F-010's
blast radius (re-confirmed live: `git diff f16799e HEAD --stat -- scripts/` shows exactly the 6
deleted scripts and the unrelated `run_ismcts.py` edit, nothing else; `grug_findings.md` does not
appear in `git diff f16799e HEAD --stat` at all, i.e. its net effect across the full range is
zero). Both Review 01 blockers are resolved, and resolved by legitimate means (an explicit,
independently-verified owner decision record for item 1; outright deletion, not mere
re-labeling, for item 2) — not by editing away the evidence of the original problem, which
remains on record in `f010-review-01.md` (now itself committed) and in `findings.md`'s
append-only F-010 entry.

## 2. CONFORMANCE REVIEW

Same as Review 01, restated because the underlying code is unchanged (§0): F-010 carries no
rulebook or whitepaper citation (`findings.md` marks both fields absent) — a pure engine/API
reproducibility-contract question, not a rules-fidelity one.

**What the code does at `HEAD`** (unchanged from `028ff9d`, re-read directly, not assumed):
- `openspiel_pyrants/state_c.py:307-323` — `resample_from_infostate` accepts only an object with
  `.shuffle`; any other callable (the old silent unseeded-fallback path) raises `TypeError`.
- `openspiel_pyrants/ismcts_factory.py:30-70` — `make_ismcts_bot` always installs a seeded numpy
  resampler via `ISMCTSBot.set_resampler`, using a dedicated `RandomState(seed ^ 0x5F10)` stream.
- `scripts/run_ismcts.py:374-401` — every production bot is built through the factory.
- `grep -rn "ISMCTSBot(" --include=*.py . | grep -v .venv` at `HEAD`: **exactly one hit**,
  `openspiel_pyrants/ismcts_factory.py:53` — the constructor itself. All 7 originally-grepped
  call sites (the factory's own construction plus the 6 converted/deleted sites) are accounted
  for; no bare `ISMCTSBot(` construction survives anywhere reachable.

**Verdict: CONFORMANT.** Unchanged from Review 01's finding, independently re-verified by fresh
execution in §4 below rather than carried over as an assertion.

## 3. BLAST RADIUS (derived independently)

Since the fix logic is byte-identical to what Review 01 already assessed (§0), the radius is the
same class of change (`resample_from_infostate` guard, `ismcts_factory.make_ismcts_bot`,
`run_ismcts.py` bot construction) — re-derived here rather than copied, to check Review 01 did
not miss anything:

**Included:**
- **INV-1 (replay determinism)** — direct target; the finding's own falsification test.
- **INV-5 (determinization/world-diversity)** — the G2 anti-over-fix gate; the fixed function
  decides how many distinct worlds get sampled.
- **F-002 (shared `shuffle_seed`/`shuffle_counter` stream)** — previously CONFIRMED, and now also
  independently re-reviewed and ACCEPTED (`f002-review-01.md`) since Review 01's pass on F-010.
  Still in radius: F-002's own fix (`e9a2702`) sits downstream of F-010's world-sampling fix, and
  a regression in either direction would show up in `f002b.py`.
- **Always-on regardless of radius (Hard Rule 4c):** INV-1 (above), INV-2 clone independence,
  INV-3 legality, INV-6 chance mass.

**Excluded, with reason:**
- **INV-4a/4b, F-011** — different code path (`c_adapter.py`/`view.py`), untouched by anything in
  `028ff9d..HEAD` that bears on F-010. Not independently in radius, though re-run anyway as part
  of the shared `inv_b.py`/`inv_b2.py` invocation (§4) since this review batch also covers F-011.
- **F-001** — calls `resample_from_infostate` only via the `RandomState` branch, unchanged by
  this fix's guard (only the `else` branch changed). Excluded, not re-run.
- **INV-7/8/9, F-005, F-006 (STRENGTH rows)** — never re-measured inside a per-fix review per
  Hard Rule 4; addressed in §7 (invalidation), not re-measured here.
- **F-003, F-004, F-007, F-008, F-009, F-012, F-013, F-014, F-015** — unrelated code paths
  (chance-node exposure, `game_c.py` utility contract, discard-pile visibility, the board-cache,
  `insane_outcast` issuance, `neogi` double-discard). No plausible interaction with a
  resampler-seeding scope fix.

**Comparison to Review 01's own declared radius:** identical — INV-1/INV-5 as direct target,
F-002 as the one previously-CONFIRMED finding inside radius, INV-2/3/4a/6 as always-on/adjacent.
Nothing wider or narrower here; the fix itself did not change, so there is no basis for the
radius to move.

## 4. RE-RUN

All commands run from repo root, `.venv/Scripts/python.exe -u <path>`, at `HEAD`
(`74f2be31716712d5fb9385c2a524b8747dba3b9e`), fresh this session (not copied from
`f010-review-01.md`).

**a. Pre-registered falsification test**

| Check | Command | N / seeds | Prior (Review 01, `028ff9d`) | New (this review, `HEAD`) |
|---|---|---|---|---|
| Full-game replay | `docs/validation/harness/inv_a.py` (INV1) | N=100, seeds 1–100 | PASS, 0/100 diverged | **PASS, 0/100 diverged** |
| Fixed-root repeated search | `docs/validation/harness/det_bot.py` (B1) | N=10, seed=4242, num_sims∈{20,200} | 1 distinct chosen action @ both | **1 distinct chosen action @ both** (`[8]`), 1 distinct policy — exact match |

✅ Falsification test: **PASS**, unchanged from Review 01 — matches "Expected if FALSE POSITIVE"
(the defect is gone).

**b. Blast-radius checks, original N/seeds**

| Check | Command | N | Prior | New |
|---|---|---|---|---|
| INV-5 world diversity | `harness/inv_b.py` | 200 info sets × K=12 = 2400 | mean 10.26/12 (Review 01, pre-F-011) | **mean 11.11/12, min 7, max 12, singletons=0** — shifted from 10.26 to 11.11 for the reason already on record in `verdict.md` (F-011's discard-identity fingerprint change, not a G2 regression; this review did not re-derive that explanation, only confirmed the number matches the current ledger's post-F-011 baseline exactly) |
| INV-4a leakage | `harness/inv_b.py` (same run) | 300 | 0 violations | **0 violations** |
| F-002 shuffle-stream sharing | `harness/f002b.py` | 3 controlled reshuffles | still CONFIRMED (shared stream), unchanged by F-010's fix | **Still exactly reproduced: 3/3 identical when (seed,counter) fixed, 3/3 changed on counter+1, 3/3 changed on seed^const** — this is F-002's pre-fix signature; F-002 has its own separate fix (`e9a2702`) already independently ACCEPTED (`f002-review-01.md`), unrelated to F-010's scope resolution |

**c. Always-on regardless of radius**

| Check | Command | N | Prior | New |
|---|---|---|---|---|
| Replay determinism | `inv_a.py` | 100 | PASS | **PASS, 0/100** |
| Clone independence | `inv_a.py` | 235 | PASS | **PASS, N=235, 0 failures** |
| Legality | `inv_a.py` | 1200 | PASS, empty=0 dup=0 oor=0 | **PASS, N=1200, empty=0 dup=0 oor=0** |
| Chance mass | `inv_a.py` | 30 | PASS, bad=0 | **PASS, N=30, bad=0** |
| Layer isolation (L1–L5) | `det_isolate.py` | 10+10+5+8+8 | PASS | **PASS** — L1 10/10, L2 10/10, L3 5/5, L4 1 distinct/8, L5 1 distinct/8 |
| Root-cause probes (S1,S4,S5) | `det_root.py` | 6+6+6 | S1 unseeded (expected, upstream), S4/S5 deterministic | **S1: 6/6 different draws (upstream `UniformProbabilitySampler` still genuinely unseeded, as expected — this fix routes around it, does not patch it); S4: factory-built bot, 6/6 identical chosen action; S5: control, 1 distinct fingerprint** |

**d. Previously-CONFIRMED findings inside the radius**

| Finding | Command | Prior status | Re-run result |
|---|---|---|---|
| F-002 | `f002b.py` | CONFIRMED, own fix ACCEPTED (`f002-review-01.md`) | Pre-fix-signature reproduced exactly (§4b) — undisturbed by F-010's scope resolution, as expected since no F-010 production code changed |

**e. Regression sweep beyond the declared radius**

| Command | N | Result |
|---|---|---|
| `pytest openspiel_pyrants/tests/test_ismcts_reproducibility.py -v` | 7 tests | **7/7 PASS** |
| `pytest openspiel_pyrants/tests/ -q` | 88 collected | **78 passed, 10 failed** — all 10 failures are `test_chance_nodes.py::test_*`, the F-003 Part B RED-test suite (`docs/validation/f002-f003-completion-plan.md` Phase 0/1, landed `6a097de`, postponed by ADR-0002); confirmed by name-matching every failure against that suite's own file, none touches anything in F-010's diff |
| `pytest -q` (repo root) | full suite | **3 FAILED, 1 skipped, rest passed**: `tests/c_engine/test_card_zuggtmoy.py::test_zuggtmoy_eot_promote_two_other_cards_excludes_self`, `tests/c_engine/test_engine_c.py::test_air_elemental_option_1_focus_draw`, `tests/test_card_neogi.py::test_neogi_execution_model_deploys_four_and_random_mass_discard` — identical 3 names to every prior review (`f010`/`f011`/`f004`/`f013-review-01.md`), pre-existing `engine_c`/catalog issues, none touching `openspiel_pyrants/`, `scripts/run_ismcts.py`, or `docs/validation/` |
| `just test-c` (from `engine_c/`) | full C suite | **exit 0, 0 "FAIL" occurrences** across 95 lines of output |

**No regression found. No invariant reversed. No previously-CONFIRMED finding disturbed.** The 10
`test_chance_nodes.py` failures are a pre-existing, expected, out-of-radius condition (postponed
F-003, RED by design) — not new, not attributable to `2cfd836` or to F-010's own diff, and not
silently reclassified as passing: they are reported here exactly as failing.

## 5. NEW FINDINGS

None. `2cfd836` is a documentation/scope-remediation commit only; there is no new production or
test surface to originate a finding from. F-012 (raised by Review 01) remains on record, `OPEN`,
not re-investigated here per Hard Rule 5's "do not investigate it further" instruction — it was
not raised by this review, only re-confirmed still present and unresolved.

Count: **0 new findings.**

## 6. VERDICT

**ACCEPTED-WITH-DEBT** (F-012 open, unchanged from Review 01).

Every Hard Rule 8 component: test PASS (§4a, exact match to Review 01), conformance CONFORMANT
(§2), zero regressions (§4, full battery plus both test suites plus the C suite), and — the
component Review 01 found lacking — **zero out-of-scope hunks**, now genuinely met: `2cfd836`
itself contains none, and the cumulative diff no longer contains `grug_findings.md` while the 3
extra script deletions now carry an explicit, independently-re-verified owner authorization in
the fix plan (§1). The scope objection that produced REJECTED-SCOPE in Review 01 is resolved by
the specific, narrow means that review's own handoff (§9) prescribed — not by a broader change,
not by editing away the record of the original problem (which stays on record, append-only, in
both `findings.md` and the now-committed `f010-review-01.md`), and not by touching any of the
fix's own production or test code (§0, confirmed byte-identical).

Debt carried forward: **F-012** — `resample_from_infostate`'s accept branch and its own guard
message both claim `numpy.random.Generator` support that the branch's `.randint()` call does not
actually have. Dormant (no caller in the repo passes a `Generator`), unchanged by `2cfd836`
(that commit touches no production code), and not addressed by this review per Hard Rule 1 — a
review never repairs, only accepts or rejects.

## 7. INVALIDATION CASCADE

Applying Hard Rule 4c to `verdict.md` §1, as Review 01 already did for this same fix:

**Already STALE, unaffected by this review (no double-invalidation):** INV-7 (budget
monotonicity), INV-8 (self-play calibration), INV-9 (baseline sanity) — marked STALE by Review
01 for this same finding, reaffirmed independently by `f011-review-01.md`, `f004-review-01.md`,
and `f013-review-01.md` since. `2cfd836` changes no engine/binding/observation/search code, so it
is not itself a new invalidation trigger — it is documentation only.

**Newly STALE (this review):** None.

**Not STALE:** INV-1 through INV-6 — non-strength structural/correctness checks, all freshly
re-measured in §4 above, not merely asserted.

**Count: 0 newly-STALE rows.** (3 rows — INV-7/8/9 — remain STALE from Review 01; not
re-counted here.)

## 8. RECORD

This file. See `findings.md` and `verdict.md` for the corresponding ledger/verdict entries
appended by this review.

## 9. HANDOFF

**ACCEPTED-WITH-DEBT.** Debt: F-012 (dormant `Generator`/`.randint()` mismatch in
`resample_from_infostate`'s guard) stays `OPEN`, tracked, non-blocking (dormant, no live caller).

F-010 is now closed procedurally as well as logically: fix logic CONFORMANT (Review 01, reaffirmed
here unchanged), commit scope now clean (this review). No further re-submission is required for
F-010 itself.

**Next finding in recommended order:** per this session's assignment (review all fixes except
F-003), the remaining un-re-reviewed items are F-011, F-002, F-013, F-004 — each already
`ACCEPTED`/`ACCEPTED-WITH-DEBT` under its own Review 01, with zero drift since (independently
confirmed, `git diff <review-01 SHA>..HEAD` empty for each one's production/test surface). F-003
itself is explicitly out of scope for this session per user instruction.

**Blocking findings remaining toward GO:** unchanged by this review — F-002+F-003 (condition 3)
and F-006 (condition 4) per `verdict.md` §5; F-010 was never itself a listed blocking condition
once its fix logic was confirmed (`verdict.md` §5's numbered conditions start at F-011).

STOP. Not beginning source changes; not touching source.
