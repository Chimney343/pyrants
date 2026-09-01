# F-002 Review 01 — Adversarial Review of the `engine_determinize` Shuffle-Stream Reroll

Reviewer role: adversarial, read-only outside `docs/validation/`. Did not write the fix
(`e9a2702` was committed by a prior session).

## 0. LOAD

- **Target finding:** F-002 — "`engine_determinize` never rerolls `shuffle_seed`/
  `shuffle_counter`, so post-determinization chance events collapse across worlds."
  Class `OPENSPIEL-ISMCTS`. Severity **CRITICAL** (invalidates results; blocking half of
  `verdict.md` § 5 condition 3).
- **Commit range:** `b0f3173` (parent) → `e9a2702` ("[engine-c] fix F-002: reroll shuffle stream
  in engine_determinize"). Current repo `HEAD` is `d26a920`, five commits later; verified via
  `git diff e9a2702 HEAD --stat` that `engine_c/state.c` and both test files are untouched since
  the fix commit (the only later production-code changes are F-004's `game_c.py` and F-013's
  `c_adapter.py` cache, both previously adjudicated), so re-running against current `HEAD` is
  equivalent to re-running at `e9a2702` for every check this review performs.
- **Correction to the completion plan, recorded here (§ 1 class, doc-accuracy):**
  `docs/validation/f002-f003-completion-plan.md` § 1 states the diff should be reviewed at
  `e9a2702` "(parent `2cfd836`)". The actual parent of `e9a2702` is `b0f3173` ("docs: record
  F-011 Review 01"); `2cfd836` is the grandparent. The review was run against the true parent;
  `git show --stat e9a2702` is the authoritative diff and it is clean (§ 1). This changes no
  conclusion — the completion plan's intent (review the fix commit's own diff) is what was done.
- **Scope note (pre-review housekeeping):** at review start the working tree carried uncommitted
  ledger edits from the already-adjudicated F-013 review (`findings.md`/`verdict.md` Review-01
  appends), the untracked `f013-review-01.md`, and the untracked completion plan. This review's
  target is a **committed** diff (`b0f3173..e9a2702`), so tree state does not affect diff
  isolation; those artifacts were not touched and are not part of any audited diff.
- **No `register.md` exists in this repo** (confirmed via `Glob`, same finding as
  `f010-review-01.md` § 7, `f011-review-01.md` § 0, `f004-review-01.md` § 0, `f013-review-01.md`
  § 0). `verdict.md` § 1 is used as the register-equivalent throughout.
- **Prior review:** none for F-002 — this is Review 01. Three later reviews (F-004, F-013) and
  one earlier (F-011's incidental findings.py run) each re-ran some slice of F-002's evidence as
  blast-radius collateral without ever finding a problem, but none adjudicated F-002 as its own
  primary target — which is the gap this review closes, per the fix plan's own § 0 constraint 2.
- **Pre-registered falsification test** (quoted verbatim from `findings.md` F-002, read before
  any diff inspection — not taken from the fix plan's restatement):
  > From one information-state root, produce two adapters via `CEngineAdapter.determinize(player_id, seed1)`
  > and `determinize(player_id, seed2)`, seed1≠seed2. Confirm both report identical
  > `shuffle_seed`/`shuffle_counter` (they must, since `engine_determinize` never writes them).
  > Drive each to the same `shuffle_counter` value via a reshuffle-triggering draw and record the
  > **relative permutation** `rng_shuffle` applies (index mapping), not the resulting card
  > identities (which differ anyway because the pre-shuffle contents differ per world).
  > Expected if REAL: The permutation indices are bit-for-bit identical between the two worlds at
  > matching `shuffle_counter` values.
  > Expected if FALSE POSITIVE: The permutation indices differ, meaning `shuffle_seed`/
  > `shuffle_counter` are perturbed by determinization somewhere not found in this reading.

  Post-fix, the falsification test's premise ("they must, since `engine_determinize` never
  writes them") no longer holds — which is the fix working as intended. The finding's own
  post-fix gate is GA1/GA3 (fix plan § 3), re-run fresh in § 4 below.

## 1. DIFF AUDIT

`git show --stat e9a2702` touches 9 files (parent `b0f3173`), all additions except a 3-line
findings.md edit. Hunk-by-hunk classification:

| File | Classification | Notes |
|---|---|---|
| `engine_c/state.c` | IMPLEMENTS-FINDING | the only production-code file touched; single hunk at the tail of `engine_determinize`, +10 lines (8-line comment + 2 code lines) |
| `engine_c/test_engine.c` | TEST-CHANGE | new T-A1 `test_determinize_rerolls_shuffle_stream` and T-A2 `test_determinize_shuffle_stream_deterministic_per_seed`, plus 2 registrations in `main()` |
| `openspiel_pyrants/tests/test_determinize_reshuffle_independence.py` (new) | TEST-CHANGE | T-A3/T-A4/T-A5 (3 tests, not parametrized) |
| `docs/validation/f002-f003-fix-plan.md` (new) | DOC-CHANGE | the plan document itself |
| `docs/validation/harness/f002_reroll.py` (new) | DOC-CHANGE (evidence) | T-A6 gate probe script (GA1 + GA3 halves) |
| `docs/validation/baseline/f002_reroll.pre.txt`, `.post.txt` (new) | DOC-CHANGE (evidence) | required by plan Phase 0/4 |
| `docs/validation/findings.md` | DOC-CHANGE | F-002 status flip + Resolution paragraph, required by plan Phase 6.2 |
| `docs/validation/verdict.md` | DOC-CHANGE | F-002 moved to resolved, § 5 condition 3 split into 3a (struck) / 3b (open), required by plan Phase 6.1 |

**No OUT-OF-SCOPE hunks.** Every touched file maps to a phase the fix plan explicitly authorizes
(§ 6 Phase 2 for `state.c`; § 5 Phase 1 for both test files; § 4/§ 8 Phase 0/4 for the harness
script and baseline captures; § 10 Phase 6 for the ledger updates). `actions.c`, `rules.c`,
`generic_runtime.c`, the bindings, and `openspiel_pyrants/` non-test code are untouched — all ten
§ 1(b) reshuffle/forced-discard call sites were correctly left alone (the fix works by rerolling
the two fields they already read polymorphically; verified by reading `engine_clone` at
`state.c:175-207`: plain `memcpy` at `:182`, scalars carry through byte-for-byte, so the root
cause claim holds at HEAD).

**The `state.c` production diff, read in full** (at `e9a2702`, re-read at HEAD `d26a920`,
`engine_c/state.c:308-316`):

```c
/* F-002: decouple the shared mid-game reshuffle/forced-discard stream
 * across sampled worlds, the same way the market deck already is. Every
 * mid-game random event reseeds from state->shuffle_seed/shuffle_counter;
 * rerolling them here makes each determinized world draw an independent
 * stream. Placed after every prior rng draw so the rerolled seed is a
 * deterministic function of `seed` (F-010 reproducibility). See
 * docs/validation/f002-f003-fix-plan.md Part A. */
clone->shuffle_seed = rng_next(&rng);
clone->shuffle_counter = 0;
```

This is exactly fix-plan § 6 Phase 2's two code lines, verbatim. The comment wording differs
slightly from the plan's illustrative comment ("NEW — F-002: ...") — an expanded, equivalent
version, not a substantive deviation. Independently verified properties, not trusted from the
plan:

- **Placement (Phase 5 checklist item 1):** the hunk sits after the opponent-zone reshuffle loop
  (`state.c:279-298`) and after the market-deck `rng_shuffle` (`:304-306`), immediately before
  `return clone`. It is the last consumer of `rng` in the function, so the rerolled
  `shuffle_seed` is a deterministic function of the full rng state and therefore of `seed` —
  the GA2/T-A4/F-010 reproducibility requirement.
- **Adjacency intact (Phase 5 checklist item 2):** the opponent-zone loop and market-deck block
  are byte-identical to pre-fix — `git diff b0f3173 e9a2702 -- engine_c/state.c` contains only
  this one appended hunk, nothing modified or removed.
- **No unseeded entropy:** `rng_next` (`rng.c:45`) draws from the already-seeded xoshiro-style
  `RNG` (`rng_seed` at `rng.c:36` derives all four state words from `seed` via splitmix64); no
  `rand()`/time-based call is involved anywhere in the function.

**Gaming checklist (Hard Rule 4), run against both TEST-CHANGE hunks:**

| Hunk | Weakened assertion | Deleted/skipped test | Widened tolerance | Reduced N | Seed pinned to pass | Special-cased input | Swallowed exception | Removed invariant | Disabled warning |
|---|---|---|---|---|---|---|---|---|---|
| `engine_c/test_engine.c` (new, 2 tests) | clear | clear | clear | clear | clear | clear | clear | clear | clear |
| `test_determinize_reshuffle_independence.py` (new, 3 tests) | clear | clear | clear | clear | clear | clear | clear | clear | clear |

Cleared. Both are new files (no weakened/deleted pre-existing assertions). All assertions are
strict inequalities/equalities on the actual fields (`d1->shuffle_seed != gs->shuffle_seed`,
`d1->shuffle_seed != d2->shuffle_seed`, tuple-equality for the T-A4 control, sorted-multiset
equality for T-A5's market-deck guard). Seeds 1111/2222/11/22 are the fix plan's own prescribed
T-A1/T-A3 values, not chosen post hoc; `shuffle_seed=42`/`n_moves=40` is the fixture already
established by the F-011 test files. No `except:`/bare-`assert` tricks; C tests use plain
`assert()`. One noted characteristic, not a trap: T-A3/T-A4 contain a `pytest.skip("game ended
early")` guard for a terminal-by-luck fixture — the § 4 run shows **3 passed, 0 skipped**, so
nothing was silently skipped. T-A1's `d1->shuffle_seed != d2->shuffle_seed` has a theoretical
~2⁻⁶⁴ collision for seeds 1111/2222 — the plan itself flags the seed space as finite; observed
0 collisions, and GA1's N=100 gate is the load-bearing check, not this single pair.

**Diff vs. plan:**
- Phase 2's exact code: present verbatim (§ above).
- Phase 1's T-A1–T-A5: present, named identically to the plan's table (T-A6 is the script,
  present as `f002_reroll.py`).
- Phase 4's required commands were all actually run by the fixing agent (evidenced by
  `baseline/f002_reroll.post.txt` matching the claimed numbers: GA1 0/100, GA3 3/3) and
  independently re-run fresh in this review (§ 4), not merely re-read from the ledger.
- Phase 6's required verdict/findings updates are both present, read in full: `findings.md`
  F-002 gained the Resolution paragraph with post-fix evidence; `verdict.md` § 5 condition 3 is
  split into struck 3a / open 3b exactly per § 0 constraint 4 (the combined condition was NOT
  marked resolved — correct, since F-003/Part B is still open).
- One ledger-precision staleness noted (correction, not a finding, Hard Rule 7 append-only):
  `findings.md` F-002's `Status:` line still reads "(working-tree change; not yet committed)" —
  written pre-commit and now superseded by `e9a2702` itself. The commit hash is not yet in the
  ledger text. Noted for the record; this review's appended entry (§ 8) supplies the sha.
- Nothing the plan promised is absent. Nothing beyond the plan's authorized scope was added.

**Verdict of this step:** 0 out-of-scope hunks, 2 test-change hunks cleared, 1 ledger staleness
corrected (not a new finding).

## 2. CONFORMANCE REVIEW

**Rulebook:** `docs/tyrants-rulebook.md` § Draw a Card (line 328): "Whenever you need to draw a
card but there are none left, shuffle your discard pile to re-form your deck." The fix does not
change *what* the engine does at any of the ten reshuffle/forced-discard sites — each still
performs its rulebook-mandated shuffle/discard exactly as before. What changes is which hidden
world's stream each ISMCTS-sampled determinization consults. No rule is touched; the rulebook
anchors the *finding* (reshuffles are real game events), not the fix mechanics.

**Whitepaper:** `docs/ismcts-paper.md` § III-C-2: "chance nodes do occur under certain
circumstances ... they cannot be ignored completely," and § III-C-1's determinization scheme
requires that sampled determinizations differ across simulations precisely where hidden
information is unresolved. Pre-fix, every sampled world shared one reshuffle outcome — a
violation of the paper's determinization premise for these events. The fix restores it: two
determinizations of one information set now draw independent streams (GA1), while same-seed
repeats remain bit-identical (GA2), which the paper's identically-seeded-search requirement and
F-010's fix both need.

**Verdict: CONFORMANT.** The change is the minimal, correctly-placed reroll the finding's own
resolution prescribes; behavior at every game-rules site is preserved (only *which* hidden
stream a sampled world consults changes, which is the defect being fixed); reproducibility
guarantees are preserved and re-verified by execution (§ 4).

## 3. BLAST RADIUS (derived independently)

Changed symbol: `engine_determinize` (`engine_c/state.c`). Its callers: `ce_api.py::CEngine.determinize`
→ `c_adapter.py::CEngineAdapter.determinize` → `state_c.py::resample_from_infostate` and the
ISMCTS determinization path (`open_spiel.python.algorithms.ismcts` calls `resample_from_infostate`
each simulation), plus every harness that determinizes.

**Included:**
- **T-A1–T-A6** — direct target.
- **INV-1 (replay determinism)** — `clone_via_replay`/replay paths must stay deterministic; a
  nondeterministic reroll would break seed-pair replay equality. Included, primary.
- **INV-2 (clone independence)** — determinize/clone construction is adjacent surface. Included.
- **INV-3 (legality), INV-6 (chance mass)** — always-on (Hard Rule 4c); INV-6 additionally
  touches the initial chance node, whose outcome space must be unaffected by the reroll.
- **INV-4a/4b (leakage/completeness), INV-5 (determinization diversity + conservation)** — INV-5
  is the most exposed: it measures world diversity across determinizations, which this fix
  changes by design (worlds now differ in one more channel). Its conservation check (per-info-set
  card conservation) would catch an over-eager reroll that corrupted zone contents. Included, primary.
- **F-010's `det_bot.py` B1 (identically-seeded search ⇒ 1 distinct action)** — GA6 explicitly.
  The reroll must draw from the seeded rng, not break same-seed reproducibility. Included, primary.
- **F-002's own GA4 market-deck guard (T-A5 / `f002b.py`)** — the adjacent already-correct code.
- **F-013's board-cache suite (`test_board_view_cache.py`)** — `determinize()` is one of the four
  construction paths that must start with an empty cache; covered transitively by the full
  OpenSpiel suite re-run (§ 4e, 78/78).
- **Always-on regardless of radius (Hard Rule 4c):** INV-1/2/3/6 (list above).

**Excluded, with reason:**
- **F-003/Part B** — `is_chance_node()`/`chance_outcomes()` are untouched by this diff
  (`state_c.py` has zero diff in `b0f3173..e9a2702`); F-003's number is expected unchanged
  (fix plan § 13 says so explicitly). Not re-run as a radius obligation.
- **F-004 (utilities), F-011 (observation content), F-013 (cache perf)** — the reroll writes two
  scalar fields on a fresh clone; it cannot change returns, observation strings, or adapter
  caching. F-011's INV-4 battery is re-run anyway as always-on collateral (§ 4c). Excluded as
  radius obligations.
- **F-005/F-006/F-009/F-014, F-001** — no mechanism connects a determinize-time scalar reroll to
  seating, UCT calibration, chance-outcome limits, insane-outcast minting, or action-ID stability.
  Excluded.

**Comparison to the fixing agent's declared radius:** fix plan § 8 Phase 4 lists exactly
`f002_reroll.py`, `f002b.py`, `findings.py`, `det_bot.py`, `inv_a.py`, `inv_b.py`, the new
pytest file, `just test-c`, `just openspiel-test`, `just test`. My derived radius is a subset
plus the F-013 suite (transitively covered); nothing material is missing from the declared
radius. No wider-radius finding.

## 4. RE-RUN

All commands run from repo root against `HEAD` `d26a920`, equivalent to `e9a2702` for every path
this review touches (§ 0). All numbers below are this review's own fresh runs, not inherited —
the completion plan permitted citing `f013-review-01.md` § 4b/d with provenance; fresher runs
were cheap, so provenance is first-hand throughout.

**a. Pre-registered falsification test, post-fix form (GA1/GA3)**

| Check | Command | N / seeds | SHA | Pre-fix | New (this review) |
|---|---|---|---|---|---|
| GA1: determinization pairs preserving root `(shuffle_seed, shuffle_counter)` | `docs/validation/harness/f002_reroll.py` part 1 | N=100 pairs; roots from shuffle_seeds 1..probed every 13th ply; determinize seeds `RandomState(101)`/`(202)` | `d26a920` | 141/141 (`findings.py`), 100/100 (`f002_reroll.pre.txt`) | **0/100** |
| GA3: first-reshuffle deck order across distinct determinize seeds | same script, part 2 | 3 controlled pairs (seeds 3/31/37 × steps 40) | `d26a920` | 0/3 changed | **3/3 changed** |

✅ Gate GA1 (verbatim: "two determinizations of one information set no longer share
`(shuffle_seed, shuffle_counter)` over N ≥ 100 pairs"): **met**, 0/100. Flag-per-plan note: 0 is
not provably the asymptote (finite seed space), but no nonzero count occurred to inspect.
✅ Gate GA3: **met**, 3/3.

**b. Blast-radius checks**

| Check | Command | N | Prior | New (this review) |
|---|---|---|---|---|
| GA2 same-seed reproducibility (C level) | `engine_c/test_engine.c::test_determinize_shuffle_stream_deterministic_per_seed` (via `just build-c`) | 2 calls, seed 1111 | PASS | **PASS** |
| T-A3/T-A4/T-A5 | `.venv/Scripts/python.exe -m pytest openspiel_pyrants/tests/test_determinize_reshuffle_independence.py -v` | 3 tests | 3/3 pass | **3/3 pass, 0 skipped**, 0.29s |
| F-002 permutation control (`f002b.py`) | `docs/validation/harness/f002b.py` | 3 controlled reshuffles | 3/3 + 3/3 + 3/3 | **3/3 + 3/3 + 3/3 — unchanged** |
| F-010 `det_bot.py` B1 | `docs/validation/harness/det_bot.py` | 10 identically-seeded searches, num_sims 20 & 200 | 1 distinct chosen action | **1 distinct chosen action — unchanged** (B2 root intact both scales, B3 10×[8], B4 5×8) |

**c. Always-on regardless of radius**

| Check | Command | N | SHA | Prior | New (this review) |
|---|---|---|---|---|---|
| Replay determinism (INV-1) | `docs/validation/harness/inv_a.py` | 100 seed pairs (1-100) | `d26a920` | PASS | **PASS, failures: []** |
| Clone independence (INV-2) | same run | 235 probes | `d26a920` | PASS | **PASS, N=235, 0 failures** |
| Legality (INV-3) | same run | 1,200 states | `d26a920` | clean | **N=1200, empty=0 dup=0 oor=0** |
| Chance mass (INV-6) | same run | 30 nodes | `d26a920` | clean | **N=30, bad=0** |
| INV-4a leakage | `docs/validation/harness/inv_b.py` | 300 | 0 violations | **0 violations** |
| INV-4b distinguishability | same run | 618 states | 618/618 unique, 0 collisions | **618 unique, 0 same-key-different-board** |
| INV-4b-2 board-mutating moves | same run | 65 | 65/65 changed-and-reflected | **65/65 — unchanged** |
| INV-5 determinization | same run | 200 info sets × K=12 | mean 11.11, min 7, max 12, singletons 0, conservation 0/2400 | **mean 11.11, min 7, max 12, singletons 0, conservation 0/2400, history mismatches 0/2400 — exact** |

**d. Previously-CONFIRMED findings inside the radius**

| Finding | Prior status | Re-run result |
|---|---|---|
| F-010 | fix logic verified, commit REJECTED-SCOPE (resubmission pending) | `det_bot.py` B1 unchanged (§ 4b) |
| F-011 | CONFIRMED — FIXED, ACCEPTED-WITH-DEBT | INV-4a/4b/5 all exact-match (§ 4c) |
| F-013 | CONFIRMED — MITIGATED, ACCEPTED-WITH-DEBT | `test_board_view_cache.py` 5/5 within the 78/78 OpenSpiel suite run (§ 4e); `c_adapter.py` has no diff in the audited range |

**e. Regression sweep beyond the declared radius**

| Command | N | Result |
|---|---|---|
| `just build-c` (full C build + all C test executables) | all suites | **All PASS**, including both new F-002 C tests (`PASS: determinize rerolls shuffle stream`, `PASS: determinize shuffle stream deterministic per seed`) |
| `.venv/Scripts/python.exe -m pytest openspiel_pyrants/tests/ -v` (`just openspiel-test` equivalent) | 78 collected | **78/78 PASS**, 39.48s |
| `.venv/Scripts/python.exe -m pytest -q` (repo root, `just test` equivalent) | full suite | **3 FAILED, rest passed**: `tests/c_engine/test_card_zuggtmoy.py::test_zuggtmoy_eot_promote_two_other_cards_excludes_self`, `tests/c_engine/test_engine_c.py::test_air_elemental_option_1_focus_draw`, `tests/test_card_neogi.py::test_neogi_execution_model_deploys_four_and_random_mass_discard` |

**On the 3 full-suite failures:** identical 3 tests, identical names, to the ones
`f010-review-01.md`/`f011-review-01.md`/`f004-review-01.md`/`f013-review-01.md` each already
found and attributed to the unrelated, ongoing `engine_c` card-execution-model backlog (GA5's
tolerated set, exactly). None touches `engine_c/state.c::engine_determinize`. No new failure;
no prior failure disappeared.

**No regression found. No invariant reversed. No previously-CONFIRMED/FIXED finding disturbed.**
The only numbers that moved are F-002's own gate numbers (GA1 100/100→0/100, GA3 0/3→3/3),
moving exactly in the direction the fix intends.

## 5. NEW FINDINGS

None. The two documentation items surfaced in § 0/§ 1 (completion plan's wrong parent sha;
`findings.md`'s stale "not yet committed" parenthetical) name no rulebook, whitepaper, or code
defect and are recorded as corrections per the precedent of `f004-review-01.md` § 1 and
`f013-review-01.md` § 1 — not elevated to ledger findings.

Count: **0 new findings.**

## 6. VERDICT

**ACCEPTED.**

Every Hard Rule 8 component is satisfied with no residual debt specific to this fix:
falsification gate re-run fresh and met (GA1 0/100 at N=100, GA3 3/3 — § 4a); conformance
CONFORMANT (§ 2); zero regressions across the full blast radius plus the always-on battery plus
the full repo suite plus the C build/test cycle (§ 4b–e); zero out-of-scope hunks (§ 1). The two
review-checklist items that demand independent verification rather than trust — reroll placement
after every other rng draw, and byte-identical adjacency of the pre-existing blocks — were both
verified by direct source reading at HEAD, not from the plan's claim (§ 1). GA5's tolerated
failure set matches the four prior reviews' recorded 3-test backlog exactly.

One process note for the record, not debt: `findings.md` F-002's `Status:` line predates the
commit and lacks the sha; per Hard Rule 7 this review does not edit it — the sha and this
review's adjudication are supplied by the appended Review 01 entry (§ 8) and `verdict.md`'s
F-002 Review block.

## 7. INVALIDATION CASCADE

Applying Hard Rule 4c ("any STRENGTH row ... goes STALE on ANY change to the engine, the
binding, the observation, the utilities, or the search") to `verdict.md` § 1:

**Already STALE, unaffected by this review (no double-invalidation):**
- INV-7 (budget monotonicity), INV-8 (self-play calibration), INV-9 (baseline sanity) — marked
  STALE by `f010-review-01.md`, reaffirmed by `f011-review-01.md`, `f004-review-01.md`, and
  `f013-review-01.md` for four independent, already-sufficient reasons. This fix is a *fifth*
  independent trigger (a change to "the engine" itself, `engine_c/state.c`) — but they were
  already correctly excluded from citation; no new STALE marking needed.

**Newly STALE (this review, first invalidation):** None. No other STRENGTH row exists in
`verdict.md` § 1 beyond INV-7/8/9.

**Not STALE:** INV-1 through INV-6 are non-strength structural/correctness checks, all
independently re-measured fresh in § 4 above (not merely asserted from the diff).

**Count: 0 newly-STALE rows.** (3 rows — INV-7/8/9 — remain STALE from prior reviews; not
re-counted here as this review's own invalidation.)

## 8. RECORD

This file. Ledger entries appended by this review:
- `findings.md` F-002: Review 01 lines (verdict, diff summary, conformance, test, regressions,
  invalidation) — same format as the F-013 entry.
- `verdict.md` § 2 (F-002 resolved block): Review 01 block quoting the verdict and the fresh
  gate numbers.

## 9. HANDOFF

**ACCEPTED.** F-002 is closed as its own primary review target; `verdict.md` § 5 condition 3a
stands struck with review backing. Condition 3b (F-003, Part B) remains the open half of the
combined condition — `docs/validation/f002-f003-completion-plan.md` Steps 3–7 are now unblocked
per § 0 constraint 4 ("Part A and Part B are separate reviewable units"), and its Step 1
blocking condition ("do not start Part B's implementation work until this review lands") is
hereby satisfied.

**Next work in recommended order:** Part B Phases 0-remainder → 1 → 2 (M1–M4) → 3 → 4 → 5 → 6
per the completion plan — legacy-path baseline capture first, then the five RED tests, then the
four milestones. F-006 remains the other blocking finding before GO.

**Blocking findings remaining: 2** (F-002+F-003 counted together per `verdict.md` § 5 condition
3 — 3a now reviewed-struck, 3b open; and F-006) before GO. F-013/F-014 remain tracked
non-blocking debt; F-005/F-009 non-blocking per condition 5.
