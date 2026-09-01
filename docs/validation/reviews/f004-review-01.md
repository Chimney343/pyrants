# F-004 Review 01 — Adversarial Review of the `Returns()`/`GameInfo` Utility-Contract Fix

Reviewer role: adversarial, read-only outside `docs/validation/`. Did not write the fix.

## 0. LOAD

- **Target finding:** F-004 — "`Returns()`/`UtilitySum`/`MinUtility`/`MaxUtility` contract violated
  for 3–4 player games." Class `ENGINE-OPENSPIEL`. Severity **CRITICAL** (invalidates results;
  blocks the project's own default configuration, `just ismcts` runs `num_players=4`,
  `justfile:63`).
- **Commit range:** `b0f3173` (HEAD at review start — this reviewer's own prior commit recording
  F-011 Review 01; see scope note below) → working tree (**uncommitted** — the fix has not been
  committed). `git diff b0f3173` isolates cleanly to exactly the F-004 fix; verified below.
- **Scope note (pre-review housekeeping, not part of the F-004 fix itself):** at review start the
  working tree mixed two unrelated things: this reviewer's own already-completed F-011 Review 01
  (`docs/validation/reviews/f011-review-01.md` plus its `findings.md`/`verdict.md` ledger entries,
  written in a prior session but never committed) and the new, uncommitted F-004 fix. Per the
  review protocol's own stop conditions ("reviewing a diff that spans more than one finding" /
  "reviewing a dirty working tree"), the user was asked how to proceed and chose to have the
  F-011 review artifacts committed first (commit `b0f3173`) so this review's diff would isolate to
  F-004 alone. That commit is bookkeeping for a *previously already-adjudicated* review (verdict
  ACCEPTED-WITH-DEBT, unchanged) — it is not itself under review here. **A second fact surfaced
  during this housekeeping and is recorded for the record:** `ListAgents` showed four other
  interactive Claude Code sessions active on this same machine, and a new untracked file
  `docs/validation/f013-fix-plan.md` appeared mid-session, consistent with a concurrent session
  independently working the F-013 fix in this same shared working directory. That file is
  untracked, was not staged, is not part of the diff audited below, and was not touched.
- **Prior review:** `docs/validation/reviews/f011-review-01.md` (F-011, `a7cee83`,
  ACCEPTED-WITH-DEBT). No prior review of F-004 exists — this is Review 01 for this finding.
- **No `register.md` exists in this repo** (confirmed via `Glob`, same finding as
  `f010-review-01.md` §7 and `f011-review-01.md` §0). `verdict.md` §1 is used as the
  register-equivalent throughout.
- **Pre-registered falsification test** (quoted verbatim from `findings.md` F-004, read before any
  edit in this diff — not taken from the fix plan's restatement of it):
  > Falsification test: `pyspiel.load_game("python_pyrants_c", {"num_players": "4"}).new_initial_state()`,
  > play to terminal, call `.returns()`, and check `sum(returns) == 0` and `all(r >= -400 for r in returns)`
  > against the declared contract.
  > Expected if REAL: `sum(returns())` is strongly positive and no return is ever negative.
  > Expected if FALSE POSITIVE: Observed returns are numerically consistent with the declared
  > zero-sum, symmetric-bound contract.

## 1. DIFF AUDIT

`git diff b0f3173` (working tree) touches 3 tracked files plus 4 new untracked files. Hunk-by-hunk
classification:

| File | Classification | Notes |
|---|---|---|
| `openspiel_pyrants/game_c.py` | IMPLEMENTS-FINDING | the only production-code file touched; `_build_c_game_info` (lines 65-81) branches `min_utility`/`utility_sum` on `num_players == 2` |
| `openspiel_pyrants/tests/test_utility_contract.py` (new) | TEST-CHANGE | new T1–T5 suite (8 tests via parametrize) |
| `docs/validation/f004-fix-plan.md` (new) | DOC-CHANGE | the plan document itself |
| `docs/validation/harness/f004_utility.py` (new) | DOC-CHANGE (evidence) | T5/T6 gate probe script, not a pytest module — same precedent as `f011_timing.py` |
| `docs/validation/baseline/f004_utility.pre.txt`, `f004_utility.post.txt` (new) | DOC-CHANGE (evidence) | required by plan Phase 0/4 |
| `docs/validation/findings.md` | DOC-CHANGE | F-004 status flip + Resolution/Post-fix-evidence text + new F-014 entry + F-014 summary row, required by plan Phase 6.2/6.3 |
| `docs/validation/verdict.md` | DOC-CHANGE | F-004 moved to RESOLVED, F-014 added, §5 condition 2 struck, §5 problem statement / bullet 5 / "Conditional partial GO" rewritten, appendix row added, required by plan Phase 6.1 |

**No OUT-OF-SCOPE hunks.** Every touched file maps to a phase the fix plan explicitly authorizes
(§5 Phase 2 for `game_c.py`, §4 Phase 1 for the test file, §3/§7 Phase 0/4 for the harness script
and baseline captures, §9 Phase 6 for the ledger updates). `state_c.py`, `engine_c/`, and every
other file in the repo are untouched — confirmed via `git diff -- openspiel_pyrants/state_c.py`
(empty) and `git status --porcelain -- openspiel_pyrants/state_c.py engine_c/` (clean).

**Gaming checklist (Hard Rule 4), run against the one TEST-CHANGE hunk:**

| Hunk | Weakened assertion | Deleted/skipped test | Widened tolerance | Reduced N | Seed pinned to pass | Special-cased input | Swallowed exception | Removed invariant | Disabled warning |
|---|---|---|---|---|---|---|---|---|---|
| `test_utility_contract.py` (new, 8 tests) | clear | clear | clear | clear | clear | clear | clear | clear | clear |

Cleared. New file, not a modification, so checked for the equivalent trap (a new test written to be
trivially satisfiable) instead. All 8 assertions are strict equality/inequality (`==`, `is None`,
range checks) against fixed values matching the plan's own G1/G2 gate thresholds verbatim (`-200.0`,
`200.0`, `0.0`, `None`, `-50.0`, `400.0`). `N_GAMES = 50` matches plan §2 gate G3's own stated
threshold (N ≥ 50), not a number chosen after the fact. Seeds are `range(1, N_GAMES+1)` — sequential,
not cherry-picked. No `except:` blocks anywhere in the file (`_random_terminal_returns` has a
`steps > 4096` bail-out matching `max_game_length`, not exception suppression). Ran the file directly
(§4 below) and confirmed 8/8 actually execute (not silently skipped by `requires_c_engine`).

**Diff vs. plan:**
- Phase 2's exact code (`f004-fix-plan.md` §5) is present verbatim in `game_c.py:67-72`: the
  `if num_players == 2: ... else: ...` branch with the stated comments citing the fix plan.
- Plan §4's T1–T5 (5 pytest tests, T3/T4/T5 parametrized over `{3,4}` = 8 collected) are present,
  named identically to the plan's table. T6 (script, not pytest) is present as
  `docs/validation/harness/f004_utility.py::section_t6`.
- Plan §7 Phase 4's required commands were all actually run by the fixing agent (evidenced by
  `baseline/f004_utility.post.txt` existing and matching the claimed numbers, checked in §4 below)
  and independently re-run fresh in this review, not merely re-read from the ledger.
- Plan §9 Phase 6's required verdict/findings updates are both present, checked in detail in §2/§4
  below, including the §11-authorized contingency: T6's direct-injection probe did produce values
  below −50.0 (at inject counts 50 and 80), and per the plan's own explicit instruction ("raise it
  as a new ledger finding... not silently widen `min_utility`") the fixing agent filed **F-014**
  rather than changing the bound. This is the plan's own anticipated branch, correctly taken.
- Plan §8 Phase 5's review checklist (n==2 byte-identical, `-50.0` justified, G5 independently
  re-verified, `state_c.py::returns()` diff empty, pre/post harness outputs attached) is addressed
  point-by-point in §2/§4 below — this review re-derives each answer rather than trusting the
  plan's own checklist as self-certifying.
- Nothing the plan promised is absent. Nothing beyond the plan's authorized scope was added.

**Independent correction to a claim in the fix plan (not a defect in the fix itself):**
`f004-fix-plan.md` §1(c) states: *"Grepping the entire installed `open_spiel` Python package
(`.venv/Lib/site-packages/open_spiel/python/`) for `utility_sum`, `min_utility`, `max_utility`,
`UtilitySum`, `MinUtility`, `MaxUtility` returns **zero matches** — confirmed fresh this session."*
Re-ran this grep independently: **182 matches across 60+ files** (`algorithms/mcts.py`,
`algorithms/exploitability.py`, `algorithms/generate_playthrough.py`, `games/*.py`,
`mfg/games/*.py`, the pybind11 C++ binding source, etc.) — the plan's stated evidence is factually
wrong. However, the *substantive* claim the plan actually needs (this repo's own search is
unaffected) survives independent re-verification by a narrower, correct check: `ismcts.py`
(`ISMCTSBot`, the bot this repo actually instantiates per `findings.md`'s own Path Map) has **zero**
matches, confirmed directly. `mcts.py` **is** imported in this repo (`c_rollout_evaluator.py:13`,
`scripts/run_ismcts.py:383`, `docs/validation/harness/common.py:45`), but only for
`Evaluator`/`RandomRolloutEvaluator` — never `MCTSBot`, the one class in that file
(`mcts.py:258`, `self.max_utility = game.max_utility()`) that reads the changed field. So the
fix plan's conclusion is correct, but for a narrower reason than it claimed; its own "confirmed
fresh this session" grep evidence should not be trusted at face value in future reviews. Not
elevated to a ledger finding — this is an inaccuracy in supporting documentation about a
zero-effect claim, not a code defect, rulebook mismatch, or paper disagreement.

**Verdict of this step:** 0 out-of-scope hunks, 1 test-change hunk cleared.

## 2. CONFORMANCE REVIEW

**Rulebook** (`docs/tyrants-rulebook.md` § Final Scoring, quoted from the finding, ≤15 words):
> "The player with the most VP at the end of the game wins" [VP sources are additive]

**Whitepaper:** `[absent]` in the original finding, re-confirmed by re-reading `findings.md` F-004
directly — "GameInfo bounds are an engine/API contract, not a paper concern." Same citation-free
posture as F-010/F-011.

**What the code now does**, at the working-tree HEAD (`openspiel_pyrants/game_c.py:65-81`,
`_build_c_game_info`):
```python
max_utility = 200.0 if num_players == 2 else 400.0
if num_players == 2:
    min_utility = -max_utility
    utility_sum = 0.0
else:
    min_utility = -50.0
    utility_sum = None
```
`num_players == 2`'s two values (`min_utility=-max_utility`, `utility_sum=0.0`) are the exact same
formula/literal as pre-fix — re-derived from the same expressions, not merely coincidentally equal
(confirmed by diffing `game_c.py` at `b0f3173` against the working tree: the only change inside
that branch is syntactic, moving from inline kwargs to named locals). `num_players > 2` now
declares `min_utility=-50.0` (was `-max_utility` = `-400.0`) and `utility_sum=None` (was `0.0`,
literally OpenSpiel's own documented default for the parameter — verified live in §4). `returns()`
itself (`openspiel_pyrants/state_c.py:171-187`) is confirmed byte-unchanged (`git diff` empty).

**Verdict: CONFORMANT.** The rulebook makes VP strictly additive with no subtraction rule (aside
from the one already-known `insane_outcast` card, tracked separately by F-014); nothing in this
fix's scope — a `GameInfo` metadata correction — touches VP computation at all, so there is no
rulebook behavior to violate. The prior violation was a pure API-contract mismatch (declared
zero-sum/symmetric-bound metadata vs. actual non-negative, non-zero-summing raw-VP returns for
`n>2`); the fix makes the declaration match the already-conformant `returns()` behavior rather
than the reverse. Independently re-verified by execution in §4, not read off the diff alone.

## 3. BLAST RADIUS (derived independently)

Changed symbol: `_build_c_game_info(num_players)` in `openspiel_pyrants/game_c.py` — specifically
the `min_utility`/`utility_sum` computation. `max_chance_outcomes`, `num_distinct_actions`,
`max_game_length`, and `_build_c_game_type` (the `ZERO_SUM`/`GENERAL_SUM` `GameType` declaration)
are all unchanged inside the same function/file.

**Included:**
- **T1–T5 (`test_utility_contract.py`)** — direct target.
- **G5 (zero production consumers)** — the fix plan's own trap: if anything in `scripts/`,
  `openspiel_pyrants/`, or `engine_c/` reads these three fields, the fix could change observable
  behavior, not just metadata. Independently re-grepped, not trusted from the plan (§4 below).
- **STRENGTH rows (INV-7/8/9)** — Hard Rule 4c: "any STRENGTH row goes STALE on ANY change to the
  engine, the binding, the observation, **the utilities**, or the search." This fix is literally a
  change to declared utilities (`GameInfo.utility_sum`/`min_utility`/`max_utility`). They are
  already STALE from `f010-review-01.md` for an unrelated reason (unseeded-resampler measurement);
  this fix is an independent, second reason they must not be cited pre-remeasurement — not a new
  STALE marking (§7).
- **Always-on regardless of radius (rule 4c):** replay determinism (INV-1), clone independence
  (INV-2), legality (INV-3), chance mass (INV-6).

**Excluded, with reason:**
- **F-001, F-002, F-003, F-005 (`findings.py`'s other sections)** — different code paths entirely
  (`action_encoding_c.py`, `engine_c/state.c`, `state_c.py` chance handling, `engine_c/state.c`
  seating), none of which reads or is read by `_build_c_game_info`. Not required by the radius, but
  incidentally re-executed anyway as an unavoidable side effect of `findings.py` running all its
  sections in one script (§4, "incidental" table) — results unchanged from the ledger, consistent
  with exclusion being correct.
- **F-006, F-007, F-008** — `run_ismcts.py` argument default, refuted finding, and an untestable
  finding conditional on F-003; no code-path overlap. Excluded.
- **F-009** — lives in the *same function* (`_build_c_game_info`'s `max_chance_outcomes=1000`
  literal) but that specific line is untouched by this diff (confirmed in the raw diff: only the
  `min_utility`/`utility_sum` lines changed). Excluded on that basis, re-confirmed by re-running
  F-009's own authoritative script (`f009.py`, not `findings.py`'s embedded duplicate) unchanged
  (§4, "aside" note).
- **F-010, F-011, F-012, F-013** — all in `ismcts_factory.py`/`state_c.py`'s resampler or
  `c_adapter.py`'s observation projection, none of which `_build_c_game_info` calls or is called
  by. Unlike F-011's own diff (which changed `information_state_string` content and thereby pulled
  F-010's node-keying into scope), this diff changes no string ISMCTS keys nodes by and no rollout
  input — there is no plausible mechanism for interaction. Excluded. F-013 additionally excluded
  because it is presently being worked by a concurrent session in this same working tree (visible
  only as an untracked `f013-fix-plan.md`, not part of this diff) and is out of scope for this
  finding regardless.
- **INV-4a/4b, INV-5, INV-10** — read `private_view_json`/observation content or
  `tracemalloc`/tree-size, none of which `GameInfo`'s three scalar fields feed into. Excluded, same
  reasoning F-011's own review applied to INV-10.

**Comparison to the fixing agent's declared radius:** `f004-fix-plan.md` §11 explicitly scopes out
F-002/F-003/F-005/F-006/F-008/F-009/F-013 — matching my exclusions on all of those. §7's "expected
post-fix results" table calls for the always-on battery and separately notes F-002/F-010/F-011 are
"not expected to move; not re-measured here beyond what the always-on battery already covers" —
also matching. **Mine is wider in one place:** the plan's own radius reasoning never invokes Hard
Rule 4c's STRENGTH-row trigger ("the utilities") explicitly, even though this fix is a textbook
case of it; the plan's exclusion of INV-7/8/9 is correct in outcome (they're already STALE, so no
action is needed) but arrives there without stating the rule that actually governs it. I state it
explicitly in §7.

## 4. RE-RUN

All commands run from repo root, `.venv/Scripts/python.exe -u <path>`, against the working tree
(fix uncommitted; base `b0f3173`).

**a. Pre-registered falsification test**

| Check | Command | N / seeds | Prior (pre-fix declaration) | New (post-fix declaration, this review) |
|---|---|---|---|---|
| `num_players=4`, play to terminal, check `sum(returns)==0` and `all(r>=-400)` | `docs/validation/harness/findings.py` (F-004 section) | N=8 terminal games/player-count, seeds 1-8 | `utility_sum=0.0`, `min_utility=-400.0` declared vs. observed `sum(returns)` ∈ {14,...,23} (never 0) and `min(returns)` ∈ {0,1,2} (never negative) — **contract VIOLATED** | `utility_sum=None`, `min_utility=-50.0` declared; same observed returns (state_c.py untouched) now satisfy `-50 ≤ r ≤ 400` for every sampled value and impose no zero-sum requirement for `n>2` — **contract SATISFIED** |

✅ Falsification test: **PASS** — matches "Expected if FALSE POSITIVE" (the defect is gone): the
declared contract is now numerically consistent with the observed returns. Full section output
(all of F-001/002/003/004/005, one shared script):
```
########## F-004 returns()/utility contract for 3-4 players ##########
  --- num_players=2  utility_sum=0.0 min_utility=-200.0 max_utility=200.0 type=Utility.ZERO_SUM
     N=8 terminal returns: sum(returns) values=[0.0]*8
     min(returns) values=[-7.0,-5.0,-2.0,-18.0,-3.0,-4.0,0.0,-3.0]   any negative=True   (expected: n==2 IS a margin)
  --- num_players=3  utility_sum=None min_utility=-50.0 max_utility=400.0 type=Utility.GENERAL_SUM
     N=8 terminal returns: sum(returns) values=[18.0,9.0,9.0,23.0,4.0,8.0,10.0,9.0]
     min(returns) values=[4.0,1.0,1.0,0.0,1.0,0.0,2.0,0.0]   any negative=False
  --- num_players=4  utility_sum=None min_utility=-50.0 max_utility=400.0 type=Utility.GENERAL_SUM
     N=8 terminal returns: sum(returns) values=[14.0,14.0,9.0,11.0,8.0,12.0,14.0,9.0]
     min(returns) values=[1.0,1.0,0.0,0.0,1.0,0.0,2.0,0.0]   any negative=False
```
Byte-identical raw-return values to the ledger's original N=8 capture (append-only evidence
undisturbed) — only the *declared* `utility_sum`/`min_utility`/`type` lines differ, exactly as
`returns()` being untouched predicts.

**b. Blast-radius checks**

| Check | Command | N | Result |
|---|---|---|---|
| T1–T5 (`test_utility_contract.py`) | `pytest openspiel_pyrants/tests/test_utility_contract.py -v` | 8 tests | **8/8 PASS**, 0.75s |
| G5 zero production consumers | `grep -rn "\.utility_sum()\|\.min_utility()\|\.max_utility()" --include=*.py` (repo-wide, then filtered) | full repo | **3 files matched, all in `docs/validation/` or the new test file** (`harness/f004_utility.py`, `harness/findings.py`, `tests/test_utility_contract.py`) — zero matches in `scripts/`, `openspiel_pyrants/` (non-test), `engine_c/`. G5 holds. |
| Post-fix gate probe (T5/T6) | `docs/validation/harness/f004_utility.py` | N=50×3 (T5), N=200×3 + 9 injections (T6) | Re-ran fresh; output byte-identical to `baseline/f004_utility.post.txt` in every T5/T6 number (checked line-by-line) |

**c. Always-on regardless of radius**

| Check | Command | N | Prior | New |
|---|---|---|---|---|
| Replay determinism (INV-1) | `inv_a.py` | 100 seed pairs | PASS | **PASS, 0 failures** |
| Clone independence (INV-2) | `inv_a.py` | 235 probes | PASS | **PASS, N=235, 0 failures** |
| Legality (INV-3) | `inv_a.py` | 1,200 states | PASS | **PASS, empty=0 dup=0 oor=0** |
| Chance mass (INV-6) | `inv_a.py` | 30 nodes | PASS | **PASS, N=30, 0 violations** |

Full `inv_a.py` run took 10m10s wall-clock (backgrounded and monitored — this machine currently
has 4 other interactive Claude Code sessions active, materially slower than the ~2-3 min this
script took standalone in prior reviews) — under the 15-minute stop condition, no truncation.

**d. Previously-CONFIRMED findings inside the radius**

None — §3 found no previously-fixed finding with a plausible interaction mechanism. For
completeness, F-001/F-002/F-003/F-005 were incidentally re-executed as an unavoidable side effect
of `findings.py` running every section in one script (not a required re-run per this review's
radius, but reported since it happened):

| Finding | Prior status | Incidental re-run result |
|---|---|---|
| F-001 | REFUTED (0/993 index changes) | **Unchanged: 0/993, 0/251 count differences** |
| F-002 | CONFIRMED (141/141 fields preserved) | **Unchanged: 141/141** |
| F-003 | CONFIRMED (134/2112 unguarded advances) | **Unchanged: 134 advances, 0 chance-node-guarded** |
| F-005 | CONFIRMED (`p1` in 10/10) | **Unchanged: `{'p1': 10}`** |

**Aside (not required, not a regression):** `findings.py`'s own embedded F-009 section crashed
(`SpielError: Wrong type for parameter shuffle_seed_count. Expected type: kInt, got kString`) —
this is a duplicate/legacy probe inside the shared script, distinct from F-009's actual
ledger-cited command (`f009.py`). Re-ran `f009.py` directly: **unchanged from the ledger**
(`shuffle_seed_count=1000→CONSISTENT=True`, `5000`/`250`→`CONSISTENT=False`, outcome id 4999
still applies without error). Confirmed via git status that `findings.py` is untouched by this
diff, so this is a pre-existing harness quirk unrelated to F-004, not a regression this diff
caused, and not the finding's authoritative evidence path.

**e. Regression sweep beyond the declared radius**

| Command | N | Result |
|---|---|---|
| `pytest openspiel_pyrants/tests/ -q` | 70 collected | **70/70 PASS** (matches `f011-review-01.md`'s own count) |
| `pytest -q` (repo root, `just test`) | 151 collected (per `f011-review-01.md`'s prior count) | **3 FAILED, rest passed**: `tests/c_engine/test_card_zuggtmoy.py::test_zuggtmoy_eot_promote_two_other_cards_excludes_self`, `tests/c_engine/test_engine_c.py::test_air_elemental_option_1_focus_draw`, `tests/test_card_neogi.py::test_neogi_execution_model_deploys_four_and_random_mass_discard` |

**On the 3 full-suite failures:** identical 3 tests, identical names, to the ones `f010-review-01.md`
§4e and `f011-review-01.md` §4e already found and attributed to an unrelated, ongoing `engine_c`
card-execution-model backlog — none touches `openspiel_pyrants/game_c.py`, the only production
file this diff changes. No new failure appeared; no prior failure disappeared. Not a regression
from this diff.

**No regression found. No invariant reversed. No previously-CONFIRMED/FIXED finding disturbed.**

## 5. NEW FINDINGS

None surfaced beyond what the fixing agent already filed as **F-014**
(`give_insane_outcast` mints without its 30-copy special-stack cap, MAJOR, OPEN), which this
review's own re-run of `f004_utility.py`'s T6 section (§4b) independently reproduces byte-for-byte
against `baseline/f004_utility.post.txt` — consistent with the ledger, not a new finding. No
further investigation of F-014 performed, per protocol (findings are not investigated or fixed
during review). The documentation-accuracy issue in §1 (fix plan's incorrect "zero matches in the
installed `open_spiel` package" claim) is not elevated to a ledger finding — it names no rulebook,
whitepaper, or code defect, only an inaccurate supporting grep in a planning document whose actual
conclusion holds under a corrected, narrower check.

Count: **0 new findings.**

## 6. VERDICT

**ACCEPTED-WITH-DEBT — F-014 (`give_insane_outcast` uncapped issuance; `min_utility=-50.0` is a
practical, not formally tight, bound) remains OPEN.**

Every Hard Rule 8 component is satisfied: falsification test PASSES (§4a), conformance is
CONFORMANT (§2), zero regressions across the full blast radius plus the always-on battery plus the
full repo suite (§4b–e), and zero out-of-scope hunks (§1). The "debt" is not a defect in this fix —
`min_utility=-50.0` was never claimed to be formally tight; the fix plan's own §1 "Load-bearing
detail" derived it as a conservative, explicitly-labeled-as-practical floor and pre-committed to
filing a new finding rather than silently re-widening the bound if the stress probe ever produced a
value below it. That is exactly what happened (T6's direct-injection probe reached −80 at the
80-copy hard cap) and exactly what the fixing agent did (filed F-014, left it OPEN, did not touch
`min_utility` or `engine_c/`). The debt is: no claim that `min_utility=-50.0` is a hard, unbreakable
floor should be made until F-014 closes (either by capping `give_insane_outcast`'s issuance in the
engine, or by re-deriving a formally tight bound) — ordinary play is nowhere near this edge (worst
observed greedy-play return was −23.0 over N=200 games, §4b), so this is a latent risk, not an
active violation.

## 7. INVALIDATION CASCADE

Applying Hard Rule 4c ("any STRENGTH row ... goes STALE on ANY change to the engine, the binding,
the observation, the utilities, or the search") to `verdict.md` §1:

**Already STALE, unaffected by this review (no double-invalidation):**
- INV-7 (budget monotonicity), INV-8 (self-play calibration), INV-9 (baseline sanity) — marked
  STALE by `f010-review-01.md` for a different, already-sufficient reason (unseeded-resampler
  measurement), reaffirmed still-STALE (not re-invalidated) by `f011-review-01.md` for the
  observation-content change. This fix is a *third*, independent reason (the declared `utilities`
  themselves changed, per §3) they must not be cited pre-remeasurement — but they were already
  correctly excluded from citation; no new STALE marking needed.

**Newly STALE (this review, first invalidation):** None. No other STRENGTH row exists in `verdict.md`
§1 beyond INV-7/8/9.

**Not STALE:** INV-1 through INV-6 are non-strength structural/correctness checks, all
independently re-measured fresh in §4 above (not merely asserted from the diff).

**Count: 0 newly-STALE rows.** (3 rows — INV-7/8/9 — remain STALE from prior reviews; not
re-counted here as this review's own invalidation.)

## 8. RECORD

This file. See `findings.md` and `verdict.md` for the corresponding ledger/verdict entries
appended by this review.

## 9. HANDOFF

**ACCEPTED-WITH-DEBT.** Per Hard Rule 8, ACCEPTED requires test PASS + CONFORMANT + zero
regressions + zero out-of-scope hunks — all four are satisfied (§1, §2, §4). The debt qualifier
names F-014 (uncapped `insane_outcast` issuance) as tracked residual risk, not a rejection
condition; per §6, it does not block this fix's acceptance.

**Next finding in recommended order:** F-002 + F-003 (`verdict.md` §5 condition 3) —
rerolling `shuffle_seed`/`shuffle_counter` inside `engine_determinize`, the next listed blocking
gate after F-011's and F-004's conditions are both struck, and the cheaper of the two remaining
search-validity blockers per the verdict's own dependency ordering.

**Blocking findings remaining: 2** (F-002+F-003 counted together per `verdict.md` §5 condition 3,
F-006) before GO. F-013 and F-014 are tracked debt (non-blocking for 2-player engine/performance
work; F-013 blocks only throughput claims, F-014 blocks only a "formally tight" claim about the
3-4 player floor) and F-005/F-009 are non-blocking per `verdict.md` §5 condition 5. Note: F-013 may
already be in progress by a concurrent session in this working directory (§0) — its own review,
when that fix lands, is a separate exercise from this one.

STOP. Not beginning the next finding; not touching source.
