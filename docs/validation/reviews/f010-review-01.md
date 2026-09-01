# F-010 Review 01 — Adversarial Review of the Reproducible-Determinization Fix

Reviewer role: adversarial, read-only outside `docs/validation/`. Did not write the fix.

## 0. LOAD

- **Target finding:** F-010 — "ISMCTS determinization seeds come from an unseeded RNG, so runs
  are not reproducible." Class `OPENSPIEL-ISMCTS`. Severity **CRITICAL** (invalidates
  reproducibility of every reported result).
- **Commit range:** `f16799e5a41a1e61d1a0529d8a66f0c8866ee4a7` (parent, "before") →
  `028ff9d1d27841e63f0945b5ddd69b4afe838d85` (fix commit, "after" / HEAD of `develop`).
  `028ff9d` is dated 2026-08-31 21:29:33 +0200, authored by Chimney343.
- **No prior review exists.** `git log --oneline --all -- docs/validation/` returns exactly one
  commit (`028ff9d`) — this is the first and only commit that has ever touched
  `docs/validation/`. There is no `register.md` and no `docs/validation/reviews/` directory in
  the repo prior to this review; both are being interacted with here for the first time. This is
  genesis, not an increment on a prior review.
- **Working tree at review time:** clean except `.claude/CLAUDE.md` (unrelated, pre-existing
  local instructions edit, not part of this diff; verified via `git status`).
- **Pre-registered falsification test** (quoted verbatim from `findings.md` F-010):
  > Falsification test: run the same seed, same policy, twice, and compare action sequences and
  > terminal returns; then re-run a single search from one fixed, unmutated root with an
  > identically seeded fresh bot.
  > Expected if REAL: identical seeds produce different action sequences and different returns;
  > a fixed root yields different chosen actions across identically seeded searches.
  > Expected if FALSE POSITIVE: identical seeds reproduce the game exactly.

## 1. DIFF AUDIT

`028ff9d` touches 40 files (2328 insertions / 335 deletions). Hunk-by-hunk classification:

| File | Classification | Notes |
|---|---|---|
| `openspiel_pyrants/__init__.py` | IMPLEMENTS-FINDING | exports `make_ismcts_bot` |
| `openspiel_pyrants/ismcts_factory.py` (new) | IMPLEMENTS-FINDING | the seeded-resampler factory |
| `openspiel_pyrants/state_c.py` | IMPLEMENTS-FINDING | `resample_from_infostate` guard replaces silent `seed=0`/unseeded-callable fallback with `raise TypeError` |
| `scripts/run_ismcts.py` | IMPLEMENTS-FINDING | production entry point routed through the factory, per-seat seed derivation preserved |
| `openspiel_pyrants/tests/test_ismcts_smoke_c.py` | TEST-CHANGE | bot construction only, converted to factory |
| `openspiel_pyrants/tests/test_determinize_c.py` | TEST-CHANGE | bot construction only, converted to factory |
| `openspiel_pyrants/tests/test_c_rollout_evaluator.py` | TEST-CHANGE | bot construction only, converted to factory |
| `openspiel_pyrants/tests/test_ismcts_reproducibility.py` (new) | TEST-CHANGE | new T1–T7 suite (the falsification test as code) |
| `scripts/check_bot_keys.py` (deleted) | INCIDENTAL | dead debug script; on the fix plan's authorized 7-site list |
| `scripts/test_ismcts_minimal.py` (deleted) | INCIDENTAL | dead debug script; on the fix plan's authorized 7-site list |
| `scripts/trace_ismcts.py` (deleted) | INCIDENTAL | dead debug script; on the fix plan's authorized 7-site list |
| `scripts/check_clone_attrs.py` (deleted) | **OUT-OF-SCOPE** | not on the plan's 7-site list; does not reference ISMCTS at all |
| `scripts/check_ismcts_chain.py` (deleted) | **OUT-OF-SCOPE** | not on the plan's 7-site list; never calls `ISMCTSBot(` (manually replicates the sampler chain) |
| `scripts/trace_clone.py` (deleted) | **OUT-OF-SCOPE** | not on the plan's 7-site list; does not reference ISMCTS at all |
| `docs/validation/findings.md` (new) | DOC-CHANGE | required by fix-plan Phase 6.2 |
| `docs/validation/verdict.md` (new) | DOC-CHANGE | required by fix-plan Phase 6.1 |
| `docs/validation/f010-fix-plan.md` (new) | DOC-CHANGE | the plan document itself |
| `docs/validation/grug_findings.md` (new) | **OUT-OF-SCOPE** | not required or mentioned anywhere in `f010-fix-plan.md`; content predates F-010/F-011 (lists only 9 findings) |
| `docs/validation/harness/*.py` (14 files, new) | DOC-CHANGE (evidence) | required by fix-plan Phase 0/3/4 |
| `docs/validation/baseline/*.txt` (6 files, new) | DOC-CHANGE (evidence) | required by fix-plan Phase 0 (pre) / Phase 4 (post) |

**Gaming checklist (Hard Rule 4), run against every TEST-CHANGE hunk:**

| Hunk | Weakened assertion | Deleted/skipped test | Widened tolerance | Reduced N | Seed pinned to pass | Special-cased input | Swallowed exception | Removed invariant | Disabled warning |
|---|---|---|---|---|---|---|---|---|---|
| `test_ismcts_smoke_c.py` | clear | clear | clear | clear | clear | clear | clear | clear | clear |
| `test_determinize_c.py` | clear | clear | clear | clear | clear | clear | clear | clear | clear |
| `test_c_rollout_evaluator.py` | clear | clear | clear | clear | clear | clear | clear | clear | clear |
| `test_ismcts_reproducibility.py` | clear | clear | clear | clear | clear | clear | clear | clear | clear |

All four cleared. The three converted test files only change the bot-construction call
(`ISMCTSBot(...)` → `make_ismcts_bot(...)`); the diff contains zero touched assertion lines in
any of them (verified via `git diff f16799e 028ff9d -- <file>`, read in full above). The new
suite uses strict equality/inequality assertions throughout (`len(fps) == 1`,
`pytest.raises(TypeError)`, `len(set(results)) == 1`, `acts1 == acts2 and ret1 == ret2`,
`acts_a != acts_b`, `mean >= 8.0` + `all(c > 1 ...)`, `chosen1 == chosen2 and outcome1 ==
outcome2`) with N and seed counts matching the plan (5 repeats, 5 seeds, 200-step diversity
probe). One opt-in `pytest.mark.skipif(PYRANTS_SKIP_ISMCTS=="1", ...)` exists but is off by
default and did not trigger in this review's run (7/7 collected and passed, not skipped).

**Diff vs. plan:**
- Everything the plan's Phase 2/3/5.1/5.2 promised is present: the factory with a decoupled
  `resample_rng` (`seed ^ 0x5F10`), the `TypeError` guard naming F-010, all 7 grepped
  `ISMCTSBot(` call sites converted, the T1–T7 suite, `openspiel_pyrants/__init__.py` export.
- The plan's Phase 3 table names exactly 3 debug scripts as "budgeted for possible deletion":
  `scripts/check_bot_keys.py`, `scripts/test_ismcts_minimal.py`, `scripts/trace_ismcts.py`. The
  commit deletes those 3 **plus 3 more** (`check_clone_attrs.py`, `check_ismcts_chain.py`,
  `trace_clone.py`) that appear nowhere in the plan and are not referenced anywhere else in the
  repo (`grep -rn "check_clone_attrs|check_ismcts_chain|trace_clone"` — no hits). The commit
  message's claim ("deletes 6 dead debug scripts that exercised the unseeded sampler") is
  factually accurate for only 3 of the 6 — `check_clone_attrs.py` never touches ISMCTS at all,
  and `check_ismcts_chain.py` invokes the sampler manually, never through `ISMCTSBot(`, so it was
  never in the grep set the plan used to define its own blast radius.
- `docs/validation/grug_findings.md` appears with no mention anywhere in `f010-fix-plan.md`.

**Verdict of this step:** 4 out-of-scope hunks found (3 script deletions + 1 new doc), none
authorized by the fix plan. Per protocol, this alone is `REJECTED-SCOPE` unless authorized —
it is not authorized. Continuing through the remaining steps regardless, so the handoff is
complete and the fix's actual correctness is on record.

## 2. CONFORMANCE REVIEW

F-010 is one of the two empirically-discovered findings (with F-011) and, unlike F-001–F-009,
carries **no rulebook or whitepaper citation** in `findings.md` — its "Rulebook:"/"Whitepaper:"
fields are simply absent, not marked `[absent]` as the other findings do, but the effect is the
same: this is a pure engine/API reproducibility-contract defect (does `--seed` reproduce a run?),
not a rules-fidelity question. There is nothing to quote at 15 words from either document.

**Governing anchor:** none (implementation contract only — the finding's own "Disagreement"
clause is the contract: `scripts/run_ismcts.py` exposes `--seed` and records `shuffle_seed` in
`summary.csv`, presenting runs as reproducible; that promise is the thing being checked).

**What the code now does**, at the fixed commit:
- `openspiel_pyrants/state_c.py:307-323` — `PyrantsCState.resample_from_infostate` accepts only
  an object with `.shuffle` (a seeded numpy `RandomState`/`Generator`-shaped object) and derives
  the determinization seed from it (`rng.randint` ×2 → 62-bit seed); any other callable (the
  previous silent fallback, including a bare `pyspiel.UniformProbabilitySampler`) now raises
  `TypeError` naming F-010 and pointing at the factory.
- `openspiel_pyrants/ismcts_factory.py:30-70` — `make_ismcts_bot` always installs a seeded numpy
  resampler via the stock `ISMCTSBot.set_resampler` hook, using a dedicated
  `RandomState(seed ^ 0x5F10)` stream decoupled from the bot's own `random_state`.
- `scripts/run_ismcts.py:374-401` — every bot is built through `make_ismcts_bot`, preserving the
  existing per-seat seed derivation `seed + game_index * num_players + i`.

**Verdict: CONFORMANT.** The code now satisfies the contract the finding describes: seeds
control determinization end-to-end, and the defective silent-fallback path is unreachable
without raising. This is independently re-verified in §4 below, not just read off the diff.

## 3. BLAST RADIUS (derived independently)

Changed symbols: `PyrantsCState.resample_from_infostate` (guard), `ismcts_factory.make_ismcts_bot`
(new), `run_one_game`'s bot construction in `scripts/run_ismcts.py`, 3 test files' bot
construction.

**Included:**
- **INV-1 (replay determinism)** — direct target of the fix; the finding's own falsification
  test *is* INV-1's method.
- **INV-5 (determinization/world-diversity)** — explicitly the G2 gate in the fix plan; the
  fixed function is the one that decides how many distinct worlds get sampled.
- **F-002 (shared `shuffle_seed`/`shuffle_counter` stream)** — previously CONFIRMED, and
  `findings.md` itself notes this fix *unmasks* F-002 (hidden-zone draws now vary per
  simulation, making the previously-masked shared reshuffle stream newly load-bearing). A
  previously-CONFIRMED finding whose masking condition just changed belongs in the radius by
  Hard Rule/Step 4d, even though F-002's own code (`engine_c/state.c`) is untouched by this diff.
- **Always-on regardless of radius (rule 4c):** INV-1 (above), INV-2 clone independence, INV-3
  legality, INV-6 chance mass.

**Excluded, with reason:**
- **INV-2/INV-3/INV-6** — not exercised by the changed code (their harness uses `RandomBot`
  only, no ISMCTS resampling) — included anyway because they are always-on per rule 4c, not
  because they're in the derived radius.
- **INV-4a/INV-4b, F-011 (board-observation gap)** — different code path
  (`_build_public_dict`/`private_view_json` in `engine_c/bindings/c_adapter.py`), untouched by
  this diff. INV-4a is cheap and shares a script with INV-5 so it was re-run as a byproduct, but
  it is not independently in-radius.
- **F-001 (action-ID stability)** — calls `resample_from_infostate` but only via the
  `RandomState` branch, which this diff does not touch (only the `else` branch changed).
  Excluded; not re-run.
- **INV-7/8/9, F-005, F-006 (STRENGTH rows / `uct_c` calibration)** — per Hard Rule 4, STRENGTH
  rows are never re-measured inside a per-fix review; they belong to the final gate. They are
  however invalidated (§7 below) because the RNG streams they depend on changed.
- **F-003, F-004, F-007, F-008, F-009** — unrelated code paths (`game_c.py`, chance-node
  exposure, discard-pile visibility). No plausible interaction with a resampler-seeding fix.

**Comparison to the fixing agent's declared radius:** the fix plan's own gates (G1=INV-1,
G2=INV-5, G3=seed separation, G4=guard reachability, G5=test suites) match my radius on INV-1/
INV-5, and Phase 4's "expected post-fix results" table additionally names INV-2/3/4a/6 as
"unchanged (PASS)" checks — so on invariants, theirs is roughly as wide as mine. The one place
mine is **wider**: the fix plan's Phase 6.3 treats F-002 as a **documentation note only**
("record that F-002 is now the binding constraint... the one permitted overlap is the
documentation note"), not something to be re-tested. I re-ran F-002's own falsification script
(`f002b.py`) against the fixed commit as a previously-CONFIRMED finding inside the radius,
which the plan did not call for.

## 4. RE-RUN

All commands run from repo root, `.venv/Scripts/python.exe -u <path>`, at SHA `028ff9d`.

**a. Pre-registered falsification test**

| Check | Command | N / seeds | Prior (pre-fix, `baseline/*.pre.txt`) | New (this review, independently re-run) |
|---|---|---|---|---|
| Full-game replay | `docs/validation/harness/inv_a.py` (INV1 section) | N=100, seeds 1–100 | FAIL, 10/10 seeds diverged (`baseline/inv_a.pre.txt`, N=10 at the time) | **PASS**, 0/100 diverged |
| Fixed-root repeated search | `docs/validation/harness/det_bot.py` (B1) | N=10, seed=4242, num_sims∈{20,200} | 4 distinct chosen actions @20 sims, 1 @200 sims (`baseline/det_bot.pre.txt`) | **1 distinct chosen action** @ both 20 and 200 sims, policy also converges to 1 distinct — output byte-identical to `docs/validation/baseline/det_bot.post.txt` |

✅ Falsification test: **PASS** — matches "Expected if FALSE POSITIVE" (i.e., the defect is
gone): identical seeds now reproduce the game exactly, and a fixed root yields the same chosen
action across identically seeded fresh bots.

**b. Blast-radius invariants, original N/seeds**

| Check | Command | N | Prior | New |
|---|---|---|---|---|
| INV-1 replay determinism | `harness/inv_a.py` | 100 seed pairs | FAIL (pre-fix) | **PASS**, 0/100 |
| INV-5 world diversity | `harness/inv_b.py` | 200 info sets × K=12 = 2400 | mean 10.26/12, min 6, 0 singletons (unaffected by fix — sampled post-fix already in ledger) | **mean 10.26, min 6, max 12, singleton_infosets=0** — byte-identical to the ledger's post-fix number; G2 holds |
| INV-4a leakage (adjacent, shares script with INV-5) | `harness/inv_b.py` | 300 | PASS | **PASS, N=300, violations=0** |
| F-002 shuffle-stream sharing | `harness/f002b.py` | 3 controlled reshuffles + field-invariance halves | CONFIRMED (shared stream) | **Unchanged: 3/3 identical when (seed,counter) held fixed, 3/3 changed when either perturbed** — F-002 still CONFIRMED, not disturbed by this fix (as `findings.md`'s own "unmasks, not cancels" note predicts) |

**c. Always-on regardless of radius**

| Check | Command | N | Prior | New |
|---|---|---|---|---|
| Replay determinism | `inv_a.py` | 100 | FAIL | **PASS** |
| Clone independence | `inv_a.py` | 235 probes | PASS | **PASS, N=235** |
| Legality | `inv_a.py` | 1200 states | PASS | **PASS, empty=0 dup=0 oor=0** |
| Chance mass | `inv_a.py` | 30 nodes | PASS | **PASS, N=30 bad=0** |
| Layer isolation (L1–L5) | `det_isolate.py` | 10+10+5+8+8 | PASS | **PASS** — L1 engine replay 10/10, L2 RandomBot 10/10, L3 ISMCTS(random-py) 5/5, L4 `random_rollout` 1 distinct/8, L5 evaluator 1 distinct/8 |
| Root-cause probes (S1–S5) | `det_root.py` | 6+3+3+6+6 | — | S1 confirms the raw `UniformProbabilitySampler` is still genuinely unseeded (0/6 identical draws) — expected, this is upstream OpenSpiel, not something this fix touches. S4: factory-built bot, 6/6 identical chosen action. S5 control: RandomState branch, 1/6 distinct (deterministic), unchanged. |

**d. Previously-CONFIRMED findings inside the radius**

| Finding | Command | Prior status | Re-run result |
|---|---|---|---|
| F-002 | `f002b.py` | CONFIRMED | **Still CONFIRMED** — permutation is a pure function of `(shuffle_seed, shuffle_counter)`, both fields still bit-inherited from root, unchanged by this fix (matches the fix's own "unmasks, does not cancel" framing) |

**e. Regression sweep beyond the declared radius (G5)**

| Command | N | Result |
|---|---|---|
| `pytest openspiel_pyrants/tests/ -q` | full package suite | **100% pass**, 17s |
| `pytest openspiel_pyrants/tests/test_ismcts_reproducibility.py -v` | T1–T7 | **7/7 PASS**, 14s, none skipped |
| `pytest -q` (repo root, `just test`) | 151 collected | **3 FAILED, rest passed**, 8.7s: `tests/c_engine/test_card_zuggtmoy.py::test_zuggtmoy_eot_promote_two_other_cards_excludes_self`, `tests/c_engine/test_engine_c.py::test_air_elemental_option_1_focus_draw`, `tests/test_card_neogi.py::test_neogi_execution_model_deploys_four_and_random_mass_discard` |

**On the 3 full-suite failures:** none is a regression from this diff. All three exercise
`engine_c` card-execution logic (Zuggtmoy promote-self, Air Elemental option-1 draw, Neogi
discard timing) and `data/cards/catalog.json` — files `028ff9d` does not touch at all (its full
40-file list is `openspiel_pyrants/*`, `scripts/run_ismcts.py`, 3 deleted debug scripts, and
`docs/validation/*`; zero overlap with `engine_c/`, `data/cards/`, or the 3 failing test files).
`openspiel_pyrants/__init__.py`'s new top-level import is a plain module import with no global
side effects, and none of the 3 failing tests import `openspiel_pyrants`. The repo's own recent
commit history (`d81a8d6 fix Air Elemental: option 2...`, `5f4c2ab fix Wyrmspeaker`,
`3218d31 fix White Dragon`, etc.) shows an active, ongoing, separate card-by-card
execution-model fix backlog — these 3 failures are consistent with that backlog, not with
anything in this diff. No further action taken per Hard Rule 4c/d (out-of-radius, pre-existing).

**No regression found. No invariant reversed. No previously-CONFIRMED finding disturbed.**

## 5. NEW FINDINGS

One new finding surfaced by reading the diff (not by a run — per instruction, not investigated
further, falsification test defined but not executed):

**F-012 — `resample_from_infostate`'s accept-branch and its own new error message both claim
`numpy.random.Generator` works, but the branch body calls `.randint()`, which `Generator` does
not have.**
- Class: OPENSPIEL-ISMCTS
- Severity: MINOR (dormant — no caller in this diff or the pre-existing codebase passes a
  `Generator`; every call site uses `np.random.RandomState`)
- Code: `openspiel_pyrants/state_c.py:313-316` (`if hasattr(rng, 'shuffle'): hi = rng.randint(0,
  2**31-1); lo = rng.randint(0, 2**31-1)`) vs. the new text this diff adds at
  `state_c.py:318-323` ("requires a seeded numpy RandomState/**Generator**") and
  `openspiel_pyrants/ismcts_factory.py`'s docstring ("dedicated ... stream ... requires a seeded
  numpy RandomState/**Generator**" — paraphrased from the module docstring's "Generator" mention)
- Rulebook: [absent] — pure API-contract concern, no rulebook citation applies (same category
  as F-010 itself)
- Whitepaper: [absent]
- Disagreement: `numpy.random.Generator` (the modern numpy random API) has `.shuffle()` (so it
  passes the `hasattr(rng, 'shuffle')` gate) but has no `.randint()` method — `Generator` uses
  `.integers()` instead; `.randint()` exists only on the legacy `numpy.random.RandomState`. A
  caller who followed the new error message's own advice and passed a `Generator` instead of a
  `RandomState` would hit an unrelated `AttributeError` deeper inside the accept branch, not the
  clean, documented behavior the message promises.
- Steelman: fully dormant today — `make_ismcts_bot`, all converted tests, and
  `docs/validation/harness/common.py::make_bot` construct only `np.random.RandomState`, never
  `Generator`. This pre-dates the diff (the `hasattr`/`randint` branch itself is unchanged by
  `028ff9d`); the diff's only new contribution is the message text asserting `Generator` support
  that was never actually there.
- Falsification test: call `state.resample_from_infostate(player, np.random.default_rng(1))`
  (a `Generator`) on any live mid-game state.
- Expected if REAL: raises `AttributeError: 'Generator' object has no attribute 'randint'`.
- Expected if FALSE POSITIVE: succeeds and returns a determinized state.
- Status: **OPEN**

Count: **1 new finding (F-012)**.

## 6. VERDICT

**REJECTED-SCOPE.**

The fix itself — `ismcts_factory.make_ismcts_bot`, the `resample_from_infostate` guard, the
`run_ismcts.py` conversion, and the T1–T7 test suite — is CONFORMANT, fully re-verified
(§2, §4a), and disturbs nothing in its blast radius (§4b–e). Taken alone it would be ACCEPTED.
But the commit as submitted bundles 4 hunks the fix plan never authorized (§1): deletion of 3
debug scripts absent from the plan's 7-site table, and addition of `grug_findings.md`, which
appears nowhere in the plan. Hard Rule 8 requires zero out-of-scope hunks for ACCEPTED; the DIFF
AUDIT step is explicit that any unauthorized out-of-scope hunk is REJECTED-SCOPE. This is a
scope/process rejection, not a correctness rejection — see §9 for the narrow, mechanical fix.

## 7. INVALIDATION CASCADE

No `register.md` exists in this repo (confirmed via `Glob`/`Grep` — this review is the first to
look for one). The closest analog is `verdict.md` §1's invariant/strength table. Applying the
rule ("any STRENGTH row ... goes STALE on ANY change to the engine, the binding, the
observation, the utilities, or the search") to that table:

**STALE (invalidated by this fix, dated at a commit older than `028ff9d`):**
- **INV-7 — budget monotonicity** (win-rate/margin numbers, `verdict.md` §1 row + detail).
  STRENGTH row; measured under the unseeded resampler.
- **INV-8 — self-play calibration ≈ 50%** (win-rate 0.438 figure). STRENGTH row; same reason.
- **INV-9 — baseline sanity vs. uniform-random** (win-rate 0.984 figure). STRENGTH row; same
  reason.

These three were already flagged by the fixing agent in the same commit
(`verdict.md`'s own "Note on § 1 win-rate figures" paragraph, and the "Deviation..." /
calibration prose) — this review independently confirms and formalizes that flag as the
required invalidation-cascade record. **Not re-measured here**, per Hard Rule 4 (STRENGTH rows
belong to the final gate).

**Not STALE:** INV-1 through INV-6, INV-10 are either non-strength (legality, chance mass,
clone independence, leakage/completeness, resource stability — structural/correctness checks,
not agent-strength measurements) or were already re-measured fresh at this SHA in §4 above
(INV-1, INV-5 explicitly; INV-2/3/6 as part of the same `inv_a.py` run).

**Count: 3 STALE rows** (INV-7, INV-8, INV-9), all inside `verdict.md` §1 — no separate
`register.md` rows exist to mark.

## 8. RECORD

This file. See `findings.md` and `verdict.md` for the corresponding ledger/verdict entries
appended by this review.

## 9. HANDOFF

**REJECTED.** Numbered list of exactly what must change before re-submission:

1. Either revert the deletion of `scripts/check_clone_attrs.py`, `scripts/check_ismcts_chain.py`,
   and `scripts/trace_clone.py` (they are not on `f010-fix-plan.md`'s authorized 7-site
   deletion table — only `check_bot_keys.py`, `test_ismcts_minimal.py`, and `trace_ismcts.py`
   were budgeted), **or** amend `f010-fix-plan.md` with an explicit decision record
   authorizing these 3 additional deletions (per the plan's own Phase 5 checklist item: "Decision
   recorded on the ... debug tools: converted, or deleted as dead" — that item covers the 3
   planned deletions, not these 3 unplanned ones), before the commit lands again.
2. Remove `docs/validation/grug_findings.md` from this diff (split it into its own,
   separately-reviewable commit), **or** add it to `f010-fix-plan.md`'s scope explicitly.
3. Re-submit for review once (1) and (2) are resolved. No other change is required — §2–§5 of
   this review found the fix logic itself CONFORMANT with zero regressions and zero disturbed
   findings.

**Acceptance condition (restated verbatim, Hard Rule 8):** "ACCEPTED requires test PASS plus
conformance CONFORMANT plus zero regressions plus zero out-of-scope hunks." Items 1–2 above are
the only blockers against that bar; test PASS, CONFORMANT, and zero regressions are already
satisfied and will not need to be re-demonstrated unless the re-submitted diff changes the fix
logic itself.
