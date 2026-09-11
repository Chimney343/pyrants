# F-019 Review 02 — Adversarial Review of the Committed Rollout Fix (`ea25b68`)

Reviewer role: adversarial, read-only outside `docs/validation/`. Did not write the fix.
This is the **second** review of F-019. Review 01 (`docs/validation/reviews/f019-review-01.md`)
was written against the *uncommitted* working tree and is itself committed inside the same
commit under review here; it audited only the 9-file F-019 portion. This pass reviews the
**committed SHA** and, as a consequence, the additional work the commit bundled with the fix.

## 0. LOAD

- **Target finding:** F-019 — "`engine_random_rollout` samples uniformly over unfiltered
  `engine_legal_moves()` output, so a UI-only `unavailable` placeholder move aborts 85-93% of
  rollouts onto a constant `{0,0}` leaf value instead of a real playout result." Class
  `OPENSPIEL-ISMCTS`. Severity **CRITICAL** (invalidates results).
- **Commit range since the last accepted review:** `2f6a0e7..ea25b68`, a **single** commit
  `ea25b68d0a8a0ed21d36627eddeddf9c184e451d` (parent
  `2f6a0e7530f4075d5f880f753ef6b50457b637a6`). The last accepted review for this finding,
  F-019 Review 01, was recorded against `<working tree, base 2f6a0e7>` and is committed *inside*
  `ea25b68`. Review 01's own diff audit lists 9 files; the commit's `--stat` lists **24**. The
  extra 15 files are an unrelated `decisions.jsonl` feature (see §1), so the delta since Review 01's
  reviewed state is real and was never audited by Review 01.
- **No `register.md` exists in this repo** (same as every prior review). `verdict.md` §1 is used as
  the register-equivalent.
- **Working tree status at review start:** dirty — `M .claude/CLAUDE.md`, `M docs/README.md`,
  `M justfile`, `M skills-lock.json`, plus untracked `.agents/skills/neural-network-design/`,
  `.kilo/skills/neural-network-design/`, `docs/nn-training-data.md`, `docs/nn-training-data-grug.md`.
  None of these touch `engine_c/`, `openspiel_pyrants/`, `tests/`, `scripts/`, or `interface/`; they
  are an unrelated neural-net-docs session. This review is scoped to the **committed SHA
  `ea25b68`**; the dirty working-tree changes are excluded and were not reviewed.
- **Pre-registered falsification test** (quoted verbatim from `findings.md` F-019). Per F-019's own
  Origin caveat, this test was written *after* the fix existed, not before it — a standing Hard
  Rule 3 deviation that this review carries, not launders:
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

`git diff 2f6a0e7 ea25b68 --stat` = 24 files, `+1591 / -91`. Every hunk classified:

| File | Class | Notes |
|---|---|---|
| `engine_c/generic_runtime.c` | IMPLEMENTS-FINDING | extracts `move_is_unavailable_placeholder` (`:733`) out of `apply_resolve_generic_choice`'s reject-check (`:752`); behavior-preserving |
| `engine_c/generic_runtime.h` | IMPLEMENTS-FINDING | declares the predicate (`:14`) |
| `engine_c/rollout.c` | IMPLEMENTS-FINDING | filters placeholders before sampling (`:48-54`), always `compute_final_scores` (`:73-74`); `ROLLOUT_HARD_STEP_CAP` 2000 → 4000 (`:23`) |
| `engine_c/rollout.h` | DOC-CHANGE | docstring matches new filtering/scoring |
| `engine_c/bindings/ce_api.py` | DOC-CHANGE | `random_rollout` docstring only |
| `openspiel_pyrants/state_c.py` | IMPLEMENTS-FINDING | `returns()` always calls `final_scores()` (`:185`), drops the raw-`player_score` non-terminal branch |
| `engine_c/tests/test_rollout.c` | TEST-CHANGE | header comment rewritten; cutoff test renamed + strengthened; `test_unavailable_placeholder_predicate` new |
| `tests/c_engine/test_rollout_binding.py` | TEST-CHANGE | cutoff test renamed + strengthened with a raw-score control |
| `openspiel_pyrants/tests/test_rollout_reaches_terminal.py` (new) | TEST-CHANGE | the pre-registered test's executable form (real 74-card market) |
| `docs/validation/findings.md` | DOC-CHANGE | ledger |
| `docs/validation/verdict.md` | DOC-CHANGE | ledger |
| `docs/validation/reviews/f019-review-01.md` (new) | DOC-CHANGE | ledger (Review 01 record) |
| `engine_c/bindings/pending_context.py` (new) | **OUT-OF-SCOPE** | bundled `decisions.jsonl` feature |
| `engine_c/bindings/view.py` | **OUT-OF-SCOPE** | refactors the inline pending-generic walk to call the new reader |
| `scripts/run_ismcts.py` | **OUT-OF-SCOPE** | `_enrich_resolve_generic` (`:282`) + decision-write path |
| `interface/replay_loader.py` | **OUT-OF-SCOPE** | docstring for the new fields (code body unchanged) |
| `interface/replay_viewer.py` | **OUT-OF-SCOPE** | `_decision_display_label` (`:34`) + panel wiring |
| `tests/c_engine/test_pending_context.py` (new) | **OUT-OF-SCOPE** | feature test |
| `tests/test_run_ismcts_generic_context.py` (new) | **OUT-OF-SCOPE** | feature test |
| `tests/test_replay_loader.py` | **OUT-OF-SCOPE** | 4 new helper tests added; existing tests untouched |
| `.kilo/plans/1788543394202-decisions-jsonl-generic-context.md` (new) | **OUT-OF-SCOPE** | feature plan |
| `.kilo/plans/1788388431546-ismcts-replay-viewer.md` | **OUT-OF-SCOPE** | feature field-table edit |
| `docs/openspiel-integration.md` | **OUT-OF-SCOPE** | feature doc |
| `.claude/CLAUDE.md` | **OUT-OF-SCOPE** | Repowise auto-index metadata refresh |

**Out-of-scope count: 12 files** implementing the `decisions.jsonl` generic-context feature, plus
1 carried Repowise metadata file. The commit message itself labels the feature "**Separately**".
The feature has its own plan (`.kilo/plans/1788543394202-…`), which authorizes it as a standalone
work item and says nothing about F-019. There is **no F-019 fix plan** (the finding was registered
retroactively), so nothing authorized F-019's fix commit to carry this feature. Per §1's rule,
these are OUT-OF-SCOPE hunks with no fix-plan authorization.

**Gaming checklist (Hard Rule 4) on every TEST-CHANGE hunk:**

| Hunk | Weakened assertion | Deleted/skipped | Widened tol. | Reduced N | Seed pinned | Special-cased input | Swallowed exc. | Removed invariant | Disabled warning |
|---|---|---|---|---|---|---|---|---|---|
| `engine_c/tests/test_rollout.c` (rename + `vp_tokens=7`) | clear (strengthened: `scores[i]==0` → `scores[0]>=7`) | clear | clear | clear | clear (seed `5ULL` unchanged) | clear | clear | clear | clear |
| `engine_c/tests/test_rollout.c` (predicate, new) | clear | clear | clear | clear | clear (no RNG) | clear | clear | clear | clear |
| `tests/c_engine/test_rollout_binding.py` (rename + raw control) | clear (strengthened: `{0,0}` → `{p1:3,p2:0}` with an explicit raw `[0,0]` control) | clear | clear | clear | clear (seed `5` unchanged) | clear | clear | clear | clear |
| `openspiel_pyrants/tests/test_rollout_reaches_terminal.py` (new, 4 tests) | clear (asserts 30/30 terminal; distinct margins > 5; placeholders still emitted) | clear | clear | clear | clear (fixture seeds 42/1000+i/2000+i; `RandomState(7)`) | clear | clear | clear | clear |
| `tests/c_engine/test_pending_context.py` (new, 5) | clear | clear | clear | clear | clear | clear | clear — the `except Exception: return None` is production code under test, not a test swallow | clear | clear |
| `tests/test_run_ismcts_generic_context.py` (new, 2) | clear | clear | clear | clear | clear | clear (a `_ScriptedBot` monkeypatch, not input special-casing) | clear | clear | clear |
| `tests/test_replay_loader.py` (4 new helper tests) | clear | clear | clear | clear | clear | clear | clear | clear | clear |

All 7 TEST-CHANGE hunks cleared. One `pytest.skip` guard exists in
`test_rollout_reaches_terminal.py::_real_market_setup_json` ("needs at least two full deck
profiles") — an environment guard, not defect-hiding; the run showed **0 skips** (§4a).

**Diff vs plan:** vacuous for F-019 (no plan exists). For the bundled feature, the code matches its
own plan. The problem is that the feature's plan is not an F-019 authorization.

## 2. CONFORMANCE REVIEW

**Rulebook:** `[absent]` — pure engine/search-mechanics concern, not a rules question (same posture
as F-010; re-read, not carried from the finding's summary).

**Whitepaper:** `docs/ismcts-paper.md` § III-A Monte Carlo Tree Search (line ~215): *"Simulated games
select random actions until a terminal state is reached…"* (quoted to 15 words; re-read at source).

**What the code now does, at `ea25b68`:** `engine_c/rollout.c:48-54` compacts
`move_is_unavailable_placeholder` moves out of the legal array, samples `rng % playable`, and `:73-74`
always writes `compute_final_scores(view, scores_out)`; `engine_c/generic_runtime.c:733` defines the
predicate as `MOVE_RESOLVE_GENERIC && intern_str(target_id)=="unavailable"`; and
`openspiel_pyrants/state_c.py:185` mirrors the always-score rule for direct `.returns()` callers.

**Verdict: CONFORMANT.** A move the engine's own `apply` refuses is not a "random action the game
permits"; filtering it restores the paper's simulation premise, and scoring every leaf restores a
state-dependent reward rather than the constant the packed-`score` fallback produced. This is
independently re-derived, not carried from Review 01.

`compute_final_scores` is `const` and does not mutate (`engine_c/scoring.c:90-126`), so the
non-terminal call does not corrupt the rollout's input state — corroborated by
`test_rollout_does_not_mutate_input_state` passing (§4).

## 3. BLAST RADIUS (derived independently)

Changed symbols: `move_is_unavailable_placeholder` (new), `apply_resolve_generic_choice`
(behavior-preserving refactor), `engine_random_rollout`, `ROLLOUT_HARD_STEP_CAP`,
`PyrantsCState.returns()`; plus the bundled feature's `read_pending_generic_context`,
`_enrich_resolve_generic`, `_decision_display_label`, and `scripts/run_ismcts.py`'s decision path.

**Included:**
- **F-019 falsification test** — direct target.
- **F-010 (determinism, ACCEPTED-WITH-DEBT)** — `det_isolate.py` L4/L5 and `det_bot.py` exercise
  `engine_random_rollout`/`returns()` directly; the changed leaf value must stay deterministic.
- **F-013 (timing, ACCEPTED-WITH-DEBT)** — rollouts are a large fraction of search wall-time and now
  run longer + score more; its ratio gate can move even though `c_adapter.py` is untouched.
- **F-002 (reshuffle reroll, ACCEPTED)** — longer rollouts traverse more mid-rollout reshuffle /
  forced-discard sites.
- **F-004 (returns contract, ACCEPTED-WITH-DEBT)** — `state_c.returns()` *body* changed for the first
  time; F-004's terminal-only bounds must be re-checked.
- **F-018 (replay fidelity, OPEN)** — the bundled feature rewrites `decisions.jsonl` via
  `run_ismcts.py`, which `interface/replay_player.py::decision_at` consumes. Included.
- **F-022 (artifact-dependent tests, OPEN)** — the feature's own validation step runs
  `just ismcts-quick` into `artifacts/ismcts/game_0000`, the golden artifact those tests read.
- **Always-on regardless of radius:** replay determinism (INV-1), clone independence (INV-2),
  legality (INV-3), chance mass (INV-6).

**Excluded, with reason:** F-001 (refuted), F-005 (seating), F-006 (UCT constant), F-007 (refuted),
F-009 (chance-outcome count), F-011 (observation content — untouched by this diff), F-014
(`give_insane_outcast` issuance — untouched), F-015 (Neogi double-fire — same file as the
`generic_runtime.c` predicate but a different function), F-016/F-017 (ledger-process defects),
F-020 (a comment in `test_rollout.c`, re-observed but not moved by this review).

**Comparison to a fixing-agent-declared radius:** Review 01 declared the same core set except it
*excluded* F-004 and F-018. Its exclusion of F-004 reasoned the changed branch was "already-excluded
[and] non-terminal", which under-counts because `returns()`'s n==2 zero-sum wrapper is shared with
the terminal path. Its exclusion of F-018/F-022 is understandable — those arise from the bundled
feature that Review 01 never saw. **My radius is wider** on F-004, F-018, and F-022.

## 4. RE-RUN

All commands from repo root; C engine rebuilt first (`just build-c`, release; all 7 C suites green).
SHA `ea25b68d0a8a0ed21d36627eddeddf9c184e451d`.

**0. Build / C suite** — `just build-c` / N=7 suites / SHA `ea25b68` / prior: green / new: **green**.
`test_rollout.exe` printed `PASS: unbounded rollout completed in 5.0 ms (terminal=0)` — i.e. **F-020
is still live** (header claims genuine terminal; the test shows cap hit `terminal=0`), unchanged.

**a. Pre-registered falsification test**

| Check | Command | N / seeds | Prior (Review 01) | New |
|---|---|---|---|---|
| Real-market rollouts reach terminal | `.venv/Scripts/python.exe -m pytest openspiel_pyrants/tests/test_rollout_reaches_terminal.py -v -rs` | 4 tests; 30 rollouts × {2p,4p}, 40-ply; seeds 42/1000+i, 2000+i, `RandomState(7)` | 4/4 PASS, 30/30 terminal | **4/4 PASS, 0 skips**, 30/30 terminal both counts |

Checkpoint: ✅ Falsification: **PASS**, N=30×{2p,4p}, was PASS.
Matches post-fix "Expected if FALSE POSITIVE": rollouts now reach terminal at 100% and cut-off
scores vary. (The pre-fix "Expected if REAL" state is not re-measurable at this SHA — no pre-fix
code in the tree.)

**b. Blast radius**

| Check | Command | N / seeds | Prior | New |
|---|---|---|---|---|
| INV-1/2/3/6 | `docs/validation/harness/inv_a.py` | 100 / 277 / 1200 / 30; seeds 1-100, 1..20, 1..30 | PASS | ✅ **PASS** — INV1 0 diverged, INV2 277, INV3 0/0/0, INV6 0 |
| INV-4a/4b/5 | `inv_b.py` | 300 / 776 / 2400 | 0 / 403 / mean 11.11 | ✅ **PASS** — INV4a 0/300; INV4b 776 unique, 0 collisions; INV5 mean **11.48**/12, min 8, 0 singletons |
| INV-4b (pair form) | `inv_b2.py` | seeds 1-139 | 403/403 differs | ✅ **PASS** — **400**/400 differ, 0 identical (ledger's 403 was already drifting) |
| F-002 | `f002b.py` | 8 reshuffles | 8/8,8/8,8/8 | ✅ **unchanged** 8/8, 8/8, 8/8 |
| F-010 B | `det_bot.py` | N=10, num_sims 20/200, seed 4242 | 1 distinct action | ✅ **unchanged** 1 distinct both; root intact |
| F-010 layers | `det_isolate.py` | 10/10/5/8/8 | all PASS/deterministic | ✅ **unchanged**; L4 rollout 1 distinct `{'p1':0,'p2':3}` |
| F-013 gate | `f011_timing.py` | N=10 searches, num_sims=200, fixed root | 0.2735 s (1.662×) | ✅ **PASS** mean_wall=**0.2484 s** → ratio vs pre-F-011 0.1646 s = **1.509×**, under 2× |
| F-004 gate | `f004_utility.py` | T5 N=50×3 counts; T6 N=200×3 | 0 out-of-bounds | ✅ **PASS** 0/50 out-of-bounds each count; n==2 `sum==0` 0/50; T6 worst −22/−9/−9 |
| Feature tests | `pytest tests/c_engine/test_pending_context.py tests/test_run_ismcts_generic_context.py tests/test_replay_loader.py` | 5+2+17 | n/a (new) | ✅ **24/24 PASS** |
| Rollout binding | `pytest tests/c_engine/test_rollout_binding.py` | 5 | 5/5 | ✅ **5/5 PASS** |

**c. Always-on regardless of radius:** covered by INV-1/2/3/6 above (same `inv_a.py` run; not re-run
separately).

**d. Previously-CONFIRMED findings inside the radius:** F-010 ✅ unchanged; F-013 ✅ within gate;
F-002 ✅ unchanged; F-004 ✅ within declared bounds.

**e. Regression sweep (full suite)** — `.venv/Scripts/python.exe -m pytest -q --tb=no` / 928 collected
/ SHA `ea25b68` / prior (Review 01): 3 tolerated + 3 replay failures / new: **4 failures**:
- `tests/c_engine/test_card_zuggtmoy.py::test_zuggtmoy_eot_promote_two_other_cards_excludes_self` — tolerated
- `tests/c_engine/test_engine_c.py::test_air_elemental_option_1_focus_draw` — tolerated
- `tests/test_card_neogi.py::test_neogi_execution_model_deploys_four_and_random_mass_discard` — tolerated (F-015)
- **`tests/test_replay_player.py::test_decision_at_matches_step`** — **NEW FAILURE** (F-018)

Checkpoint: ❌ `test_replay_player.py::test_decision_at_matches_step`: **FAIL**, N=1, was **PASS**
(Review 01 §4e recorded it passing). This is a previously-passing check that now fails.

**Attribution of the new failure (investigated, not assumed).** `interface/replay_player.py` is
untouched by the diff; `interface/replay_loader.py`'s committed delta is a **docstring only**. The
failure is an internally inconsistent local artifact: at `artifacts/ismcts/game_0000`, `replay.json`
holds a **517-step** game (mtime 2026-09-04 21:29) while `decisions.jsonl` (257 lines) and
`steps.jsonl` (257 lines) were overwritten at **23:17** by a different run (`run_id
"fef3b78a42b3"`, first chosen move `site_ss_zuraass_nee`) than the replay's (`site_gauntlgrym`).
`decision_at(0)["chosen_move"]` therefore cannot equal `entry_at(0)["label"]`. The artifact is
gitignored (`.gitignore:235`) and not tracked at any commit. The most likely writer is the feature's
own documented validation step (its plan §Validation step 4: "`just ismcts-quick`, then inspect
`artifacts/ismcts/game_0000/decisions.jsonl`"), which writes the runner's default output dir — the
same golden path the replay tests pin. So: **not attributable to any tracked source line of the
diff; attributable to the bundled feature's validation workflow mutating the golden artifact.**
This is new evidence for the already-OPEN F-022; it is not charged as a code regression.

**Verdict of this step:** falsification PASS; all invariants PASS; **one previously-passing
committed test now FAILS** with a local-artifact cause; no code-level regression found.

## 5. NEW FINDINGS

One new finding, appended to `findings.md` with the full original schema and to the summary table:

**F-024** (VALIDATION-PROCESS / test design, MINOR) — the bundled feature's new tests import the
pure helper `_decision_display_label` from `interface/replay_viewer.py`, which imports `tkinter` at
module level (`interface/replay_viewer.py:14`). `tests/test_replay_loader.py` was previously a
Tk-free module — the feature's own plan §Task 3 explicitly relies on that ("test in
`tests/test_replay_loader.py` (already Tk-free)") — so the change silently re-couples 20 tests to a
GUI toolkit and would turn into a collection error on any headless interpreter without Tk. On this
machine Tk is present, so the suite passes; the defect is latent and structural. Not investigated
further per protocol.

No other new finding filed: the `pending_op` refactor in `scripts/run_ismcts.py` was probed and
found behavior-preserving (below), and the artifact mutation is F-022's existing class.

**Falsification note for F-024:** `python -c "import ast; ast.parse(open('interface/replay_viewer.py').read())"` is not the test; the test is
`python -c "import sys; sys.modules['tkinter']=None; import tests.test_replay_loader"` on a Tk-less
interpreter, or static: `rg -n "^import tkinter" interface/replay_viewer.py`.

## 6. VERDICT

**REJECTED-SCOPE.**

Grounds, in order:
1. **Out-of-scope hunks.** `ea25b68` bundles 12 files of an unrelated `decisions.jsonl` feature
   (its own plan, tests, and docs) into a commit whose stated subject is the F-019 fix. No F-019 fix
   plan exists to authorize it; the feature's plan does not mention F-019. Hard Rule 8 requires
   **zero** out-of-scope hunks for ACCEPTED, and §1 makes an unauthorized out-of-scope hunk a
   REJECTED-SCOPE. The F-019 code itself is conformant and regression-free, but scope is
   dispositional, not quality-gated.
2. **Co-occurring regression-sweep failure.** A previously-passing committed check
   (`test_replay_player.py::test_decision_at_matches_step`, recorded PASS by Review 01) now FAILS at
   the committed SHA. Independently of the scope rejection, a strict reading of §4 ("Any
   previously-passing check that now fails is REJECTED-REGRESSION") also rejects. The reviewer's
   attribution is a locally-mutated gitignored golden artifact (F-022 class) driven by the bundled
   feature's own validation step, not by any tracked source line — but the commit did not restore
   the artifact it mutated, and the feature is the only part of the commit in this area.

Not ACCEPTED, not ACCEPTED-WITH-DEBT: the debt model cannot absorb a scope violation plus a failing
committed test.

## 7. INVALIDATION CASCADE

Register = `verdict.md` §1. Hard Rule 4c: any STRENGTH row goes STALE on ANY change to the engine,
binding, observation, utilities, or search.

- INV-7 (budget monotonicity), INV-8 (self-play calibration), INV-9 (baseline sanity) — **already
  STALE** from `f010-review-01.md`, reaffirmed by every later review. This commit is a further
  independent trigger (`engine_c/rollout.c` = engine; `state_c.py::returns()` = utilities/search;
  `run_ismcts.py` = search), but they were already excluded from citation.
- **Newly STALE (this review): none.** No other STRENGTH row exists in §1; INV-1/2/3/4a/4b/5/6/10 are
  invariant/resource rows, not win-rate/agent-comparison/ladder rows.

**Count: 0 newly-STALE rows.**

## 8. RECORD

This file. Appended to `findings.md`: F-019's Review 02 block and the new F-024 entry (summary table
+ full write-up). `verdict.md` §2's F-019 entry gets the Review 02 block; §5's GO/NO-GO block gets a
one-line caveat that this commit is rejected (append-only, Hard Rule 7).

## 9. HANDOFF

For the fix agent, in order. Nothing here suggests an implementation.

1. **Split the commit.** `ea25b68` must not remain a single unit. Land the F-019 change alone:
   `engine_c/generic_runtime.c`, `engine_c/generic_runtime.h`, `engine_c/rollout.c`,
   `engine_c/rollout.h`, `engine_c/bindings/ce_api.py`, `openspiel_pyrants/state_c.py`, and the three
   F-019 test files (`engine_c/tests/test_rollout.c`, `tests/c_engine/test_rollout_binding.py`,
   `openspiel_pyrants/tests/test_rollout_reaches_terminal.py`). Anchor: the 12 OUT-OF-SCOPE files in
   §1's table (`pending_context.py`, `view.py`, `run_ismcts.py`, `replay_loader.py`,
   `replay_viewer.py`, the three feature tests, the feature plan, the replay-viewer plan edit,
   `docs/openspiel-integration.md`). The `decisions.jsonl` feature is a separate work item and must
   not ride a finding-fix commit.
2. **Do not ship the F-019 fix with the 1 carried metadata hunk** (`.claude/CLAUDE.md`) unless it is
   separately declared as carried noise, as Review 01 did.
3. **Restore the golden artifact** `artifacts/ismcts/game_0000` to a self-consistent state
   (`replay.json`, `steps.jsonl`, `decisions.jsonl` from one run) **or** stop the feature's
   validation step from writing there, then confirm
   `tests/test_replay_player.py::test_decision_at_matches_step` passes. Anchor: the
   `replay.json` 517-step vs `decisions.jsonl` 257-line mismatch in §4e. As long as that test fails
   at HEAD, this finding cannot be accepted.
4. **Re-run at the new commit and report**: the pre-registered falsification test
   (`openspiel_pyrants/tests/test_rollout_reaches_terminal.py`), the always-on battery, F-004/F-010/
   F-013/F-002, and the full suite with the tolerated-failure baseline explicitly restated.

**Acceptance condition, restated verbatim:** *"ACCEPTED requires test PASS plus conformance
CONFORMANT plus zero regressions plus zero out-of-scope hunks."*

STOP. Not beginning the next finding; not touching source.
