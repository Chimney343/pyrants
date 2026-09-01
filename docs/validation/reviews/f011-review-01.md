# F-011 Review 01 — Adversarial Review of the Board-Observation Fix

Reviewer role: adversarial, read-only outside `docs/validation/`. Did not write the fix.

## 0. LOAD

- **Target finding:** F-011 — "Board state is absent from the information state and the
  observation." Class `ENGINE-OPENSPIEL`. Severity **CRITICAL** (invalidates results; the
  observation omits the game's primary scoring substrate).
- **Commit range:** `2cfd83634005ae3d56b0e575eef83b236ec55f49` (parent, "before", HEAD of
  `develop` at review start) → `a7cee832287aa8040a3a70b4b1e0223faec2a8f6` (fix commit, "after").
  `a7cee83` is dated 2026-09-01 13:00:13 +0200, authored by Chimney343. Verified
  `git diff 2cfd836 a7cee83 --stat` is byte-identical to the working-tree diff this review
  audited before the commit existed (same 11 files, same insertion/deletion counts).
- **Prior review:** `docs/validation/reviews/f010-review-01.md` (F-010, `028ff9d`,
  REJECTED-SCOPE, since resolved by `2cfd836`). No prior review of F-011 exists — this is
  Review 01 for this finding.
- **No `register.md` exists in this repo** (confirmed via `Glob`/`Grep`, same finding as
  `f010-review-01.md` §7). The closest analog remains `verdict.md` §1's invariant/strength
  table; used as the register-equivalent throughout this review.
- **Working tree at review time:** clean except `.claude/CLAUDE.md` (unrelated Repowise
  auto-index refresh, deliberately excluded from `a7cee83` at this reviewer's request before
  the commit was made, so the scope problem that got F-010 REJECTED-SCOPE would not repeat).
- **Pre-registered falsification test** (quoted verbatim from `findings.md` F-011):
  > Falsification test: construct state pairs that differ only in a public board fact — same
  > move type applied to a different site, so barracks/resource bookkeeping is identical —
  > verify the boards genuinely differ, then compare `private_view_json(p)`.
  > Expected if REAL: boards differ while the observation is byte-identical.
  > Expected if FALSE POSITIVE: the observation differs whenever the board differs.

## 1. DIFF AUDIT

`a7cee83` touches 11 files (778 insertions / 33 deletions). Hunk-by-hunk classification:

| File | Classification | Notes |
|---|---|---|
| `engine_c/bindings/c_adapter.py` | IMPLEMENTS-FINDING | the only production-code file touched; adds `discard` key, merges `board_nodes` into `private_view_json`, adds `_board_nodes_view()` |
| `openspiel_pyrants/tests/test_observation_completeness.py` (new) | TEST-CHANGE | new T1–T5, T7–T9 suite (T6 is the non-pytest timing script below) |
| `docs/validation/harness/f011_timing.py` (new) | DOC-CHANGE (evidence, plan's T6) | wall-time probe, not a pytest assertion |
| `docs/validation/f011-fix-plan.md` (new) | DOC-CHANGE | the plan document itself |
| `docs/validation/findings.md` | DOC-CHANGE | F-011 status flip + Resolution/Cost-note text + new F-013 entry, required by plan Phase 6.2 |
| `docs/validation/verdict.md` | DOC-CHANGE | INV-4b row flip, F-011 moved to RESOLVED, F-013 added, §5 conditions rewritten, required by plan Phase 6.1 |
| `docs/validation/baseline/inv_b.post.txt` | DOC-CHANGE (evidence) | re-captured post-fix (binary diff — UTF-16, PowerShell redirection artifact, not a content concern) |
| `docs/validation/baseline/inv_b2.pre.txt`, `inv_b2.post.txt` (new) | DOC-CHANGE (evidence) | required by plan Phase 0/4 |
| `docs/validation/baseline/f011_timing.pre.txt`, `f011_timing.post.txt` (new) | DOC-CHANGE (evidence) | required by plan Phase 0/4 (G5) |

**No OUT-OF-SCOPE hunks.** Unlike F-010's `028ff9d` (which bundled 3 unauthorized debug-script
deletions and an unauthorized doc), this commit touches exactly one production file
(`c_adapter.py`) plus the plan-required test/evidence/ledger files. `.claude/CLAUDE.md` — the
file that would have repeated F-010's scope mistake — was confirmed excluded from this commit
(`git show --stat a7cee83`, `git status` post-commit shows it still modified, uncommitted).

**Gaming checklist (Hard Rule 4), run against the one TEST-CHANGE hunk:**

| Hunk | Weakened assertion | Deleted/skipped test | Widened tolerance | Reduced N | Seed pinned to pass | Special-cased input | Swallowed exception | Removed invariant | Disabled warning |
|---|---|---|---|---|---|---|---|---|---|
| `test_observation_completeness.py` (new, 8 tests) | clear | clear | clear | clear | clear | clear | clear | clear | clear |

Cleared. This is a new file, not a modification of an existing test, so "weakened/widened/
reduced/deleted" don't apply in the literal sense — checked instead for the equivalent trap: a
new test written to be trivially satisfiable. All 8 assertions are strict equality/inequality
(`==`, `!=`, `not in`, `isdisjoint`) against fixed, meaningful values (a forced card ID, a
specific key set, board fingerprints from independent clones) — none use loosened bounds except
`test_tier1_snapshot_shape_and_cost_unaffected`'s `< 100.0` µs cost trip-wire, which the test's
own docstring justifies as "a generous upper bound that still catches a re-coupling regression"
against a measured 7.8 µs baseline (12.8× headroom, not a tolerance loosened to dodge failure).
No seed is pinned to a value chosen after observing a passing result — `_mid_game_state` uses
`shuffle_seed=42` uniformly across the file, matching the fix plan's own examples, not a
cherry-picked seed. No `except:` blocks anywhere in the file.

**Diff vs. plan:**
- Phase 2's exact code (`f011-fix-plan.md` §5.1–5.2) is present verbatim in `c_adapter.py`:
  the `discard` line, the `{**pub, "board_nodes": ...}` merge, and `_board_nodes_view()` with
  its docstring citing "f011-fix-plan.md § 1" for the current-player-aggregate exclusion.
- Plan §4's T1–T9 (8 tests; T6 is the separate timing script) are all present, named
  identically, and — per plan §4's instruction to write anti-overfix controls (T2, T4, T5)
  before the completeness tests — the file's own docstring states this ordering was followed;
  not independently checked via reflog since this is a squashed single commit, but the file's
  section comments match the plan's stated intent.
- Plan §6 Phase 3's trip-wire (`current_player_*` aggregate exclusion) is present as
  `test_board_nodes_omit_current_player_aggregates` (T9), matching the plan's "T9, reviewer's
  call" language — the fixing agent made the call to include it, which this review endorses.
- Plan §9 Phase 6 required verdict/findings updates: both present, checked in detail in §2/§4
  below.
- Nothing the plan promised is absent. Nothing beyond the plan's authorized scope was added.

**Verdict of this step:** 0 out-of-scope hunks, 1 test-change hunk cleared. No REJECTED-SCOPE
condition triggered — a clean contrast to F-010's Review 01.

## 2. CONFORMANCE REVIEW

**Rulebook** (`docs/tyrants-rulebook.md` § Final Scoring, quoted from the finding, ≤15 words):
> "The player with the most VP at the end of the game wins" [site/troop VP sources implied]

**Whitepaper:** `[absent]` in the original finding — F-011 carries no whitepaper citation
(re-confirmed by re-reading `findings.md` F-011 directly, not taking the finding's own framing
on faith): this is a pure engine/OpenSpiel-API observation-completeness defect, not a paper
concern, the same posture F-010 had.

**What the code now does**, at `a7cee83`:
- `engine_c/bindings/c_adapter.py:200-224` (`private_view_json`) — merges
  `{**pub, "board_nodes": self._board_nodes_view()}` into the `"public"` key, and adds a
  `"discard"` key built from `p.discard_pile`/`p.discard_pile_count`, alongside the pre-existing
  `hand` construction.
- `engine_c/bindings/c_adapter.py:226-244` (`_board_nodes_view`, new) — calls
  `build_c_board_view(self)` and projects only `node_id`, `troop_slots`, `spies`, `control_vp`,
  `total_control_vp_per_turn`, `vp_tokens` per node — independently confirmed by reading
  `engine_c/bindings/view.py:80-97` that these six are the per-node (`BoardNodeView`) fields,
  disjoint from `CBoardViewData`'s four `current_player_*` aggregates, which are never read.
- `engine_c/bindings/c_adapter.py:158-198` (`_build_public_dict`) — read in full, confirmed
  **byte-unchanged** from the pre-fix version (`git diff 2cfd836 a7cee83 -- engine_c/bindings/c_adapter.py`
  shows zero hunks inside this function's line range).
- `openspiel_pyrants/state_c.py:212-232` (`information_state_string`/`observation_string`) —
  read, confirmed **unchanged** by this diff; both still route through `private_view_json`
  verbatim, so the new board/discard content flows through automatically without a separate
  edit there.

**Verdict: CONFORMANT.** Site control, troop placement, and spy placement — the rulebook's
primary VP substrate — are now present in every player's `private_view_json`, and therefore in
`information_state_string`/`observation_string`. This is independently re-verified by execution
in §4, not read off the diff alone.

## 3. BLAST RADIUS (derived independently)

Changed symbols: `CEngineAdapter.private_view_json` (new `board_nodes`/`discard` keys),
`CEngineAdapter._board_nodes_view` (new method). `_build_public_dict` is unchanged but is the
sibling function sharing the same class — checked, not assumed, to still be untouched (§2).

**Included:**
- **INV-4b (completeness)** — direct target; the finding's own falsification test *is* INV-4b's
  method.
- **INV-4a (leakage)** — the fix plan's own G2 trap: fixing the observed-gap could leak hidden
  info; must be re-asserted with a real run, not assumed.
- **INV-5 (determinization consistency + conservation)** — shares `inv_b.py` with INV-4a/4b and
  reads `private_view_json` fields (`hand`, `deck_size`, `discard_size`,
  `public_player_summaries`) for its conservation check; the world-diversity fingerprint
  function also consumes `private_view_json` output, so a content change here can shift its
  numbers even without a defect (verdict.md already predicts this; independently checked, not
  trusted, in §4).
- **F-010 (previously CONFIRMED-FIXED, `a7cee83`'s parent chain)** — `ISMCTSBot` keys tree
  nodes by `information_state_string`, which this diff changes in content (now carries board
  data) for every non-terminal state. A previously-fixed finding whose node-keying substrate
  just changed shape belongs in the radius by the same logic Review 01 of F-010 applied to
  F-002 (Hard Rule / Step 4d: masking/substrate condition changed, even though F-010's own code
  — `ismcts_factory.py`, `state_c.py`'s resampler guard — is untouched by this diff).
- **F-007 (REFUTED)** — this diff adds a player's *own* discard-pile identities. F-007's own
  refutation explicitly carved out "own-discard invisibility... now carried by F-011," so this
  fix is F-007's own promised resolution path; the risk to check is that *opponent* discard
  stays hidden (T4 in the new suite; independently re-checked in §4).
- **Always-on regardless of radius (rule 4c):** replay determinism (INV-1), clone independence
  (INV-2), legality (INV-3), chance mass (INV-6).

**Excluded, with reason:**
- **F-002 (shared `shuffle_seed`/`shuffle_counter` stream)** — different code path entirely
  (`engine_c/state.c`), untouched by this diff, and no plausible interaction: F-002 is about
  RNG-stream sharing during reshuffles, not observation content. Not re-run.
- **F-001 (action-ID stability)** — `compute_c_action_map` reads `legal_moves()` enumeration
  order, not `private_view_json` content. No interaction; excluded.
- **F-003, F-004, F-008, F-009 (chance-node exposure, returns contract, chance branching,
  max_chance_outcomes)** — all in `game_c.py`/`state_c.py`'s chance-handling or `Returns()`
  logic, none of which touches `c_adapter.py`. Excluded.
- **INV-7/8/9 (STRENGTH rows)** — per Hard Rule 4, never re-measured inside a per-fix review;
  they belong to the final gate. They are already STALE from F-010's Review 01 and stay STALE
  here (§7) — not re-invalidated twice, just not lifted.
- **INV-10 (resource stability)** — measures `tracemalloc`/tree-size, not observation content;
  no plausible interaction with a JSON-payload size change of this magnitude at the sim counts
  INV-10 uses. Excluded.

**Comparison to the fixing agent's declared radius:** the fix plan's G1–G6 gates map exactly to
my INV-4a/4b/5 inclusion and the Tier-1-cost/search-time checks. The plan explicitly scoped out
F-002/F-003/F-004/F-006/F-008/F-009 (§11 "Out of scope") — matching my exclusions on all of
those. **Mine is wider in one place:** the plan's Phase 4 "expected post-fix results" table does
not mention re-running any F-010 check (`det_bot.py`/`inv_a.py`'s INV-1), even though F-010's
node-keying substrate is a direct consequence of this fix's content change to
`information_state_string`. I re-ran `det_bot.py` (§4d) as a previously-CONFIRMED finding inside
the radius, which the plan did not call for — the same kind of gap Review 01 found in F-010's
own plan regarding F-002.

## 4. RE-RUN

All commands run from repo root, `.venv/Scripts/python.exe -u <path>`, at SHA `a7cee83`
(re-run post-commit to confirm the commit reproduces the same pre-commit working-tree numbers
already captured; not re-pasted from the pre-commit run — genuinely re-executed).

**a. Pre-registered falsification test**

| Check | Command | N / seeds | Prior (pre-fix, `baseline/inv_b2.pre.txt`) | New (this review) |
|---|---|---|---|---|
| Board-differing pairs vs. `private_view_json` | `docs/validation/harness/inv_b2.py` | N=403, seeds 1–139 | 403/403 `private_view_json` IDENTICAL (board invisible) | **403/403 `private_view_json` DIFFERS (board visible)**, 0 identical |

✅ Falsification test: **PASS** — matches "Expected if FALSE POSITIVE" (the defect is gone):
the observation now differs whenever the board differs, in all 403 sampled pairs.

**b. Blast-radius invariants, original N/seeds**

| Check | Command | N | Prior (pre-fix) | New (this review, post-commit) |
|---|---|---|---|---|
| INV-4a leakage | `harness/inv_b.py` | 300 info sets | PASS, 0 violations (unaffected by fix, pre-existing) | **PASS, N=300, violations=0** |
| INV-4b-2 board-mutating moves | `harness/inv_b.py` | 65 (derived from same 618-state sample) | (not separately tracked pre-fix) | **N=65, board changed & `private_view_json` UNCHANGED=0, changed=65** — 0/65 silent misses |
| INV-5 world diversity | `harness/inv_b.py` | 200 info sets × K=12 = 2400 | mean 10.26/12, min 6, 0 singletons | **mean 11.11/12, min 7, max 12, singleton_infosets=0** — matches the ledger's claimed shift exactly |
| INV-5 conservation | `harness/inv_b.py` | 2400 draws | 0 violations (pre-existing) | **0/2400 violations, 0/2400 history mismatches** |

The INV-5 mean shift (10.26→11.11) is real and reproduces exactly; independently confirmed the
ledger's explanation (own-discard identities now entering the omniscient fingerprint) by reading
`harness/common.py::fingerprint` — it hashes `private_view_json` output directly, which now
includes `discard`, so two determinizations that reshuffle an opponent's discard into different
contents are no longer fingerprint-collapsed. This is additional distinguishing power in a
diagnostic fingerprint, not a change to what any single player's own `information_state_string`
exposes (INV-4a, re-run above, still 0/300 violations) — G2 holds.

**c. Always-on regardless of radius**

| Check | Command | N | Prior | New |
|---|---|---|---|---|
| Replay determinism | `inv_a.py` (INV-1) | 100 seed pairs | PASS (post F-010 fix) | **PASS, 0/100 diverged** |
| Clone independence | `inv_a.py` (INV-2) | 235 probes | PASS | **PASS, N=235, 0 failures** |
| Legality | `inv_a.py` (INV-3) | 1200 states | PASS | **PASS, empty=0 dup=0 oor=0** |
| Chance mass | `inv_a.py` (INV-6) | 30 nodes | PASS | **PASS, N=30, bad=0** |

Full run took 10m18s wall-clock (`time` measured) — under the 15-minute stop condition, no
truncation on the final run (first attempt was piped through `tail` and lost early output; the
untruncated re-run above is the one this review relies on).

**d. Previously-CONFIRMED/FIXED findings inside the radius**

| Finding | Command | Prior status | Re-run result |
|---|---|---|---|
| F-010 | `harness/det_bot.py` (B1–B4) | CONFIRMED–FIXED (`028ff9d`+`2cfd836`); `baseline/det_bot.post.txt`: B1 1 distinct chosen action @20/200 sims, B2 root intact, B3 constant [8]×10, B4 chosen=8×5 | **Unchanged**: B1 1 distinct chosen action @ both 20 and 200 sims (`[8]`), B2 root fp intact before/after, B3 `[8,8,8,8,8,8,8,8,8,8]`, B4 `chosen=8` ×5, `nodes=20` ×5 — byte-identical *pattern* to the F-010 post-fix baseline (state fingerprint value itself differs, expected: `fp_hash` consumes `private_view_json`, whose content this diff changed) |

F-010's reproducibility guarantee is undisturbed: identically-seeded searches still converge to
exactly one chosen action, even though the underlying observation string driving ISMCTS node
keys is now richer.

**e. Regression sweep beyond the declared radius**

| Command | N | Result |
|---|---|---|
| `pytest openspiel_pyrants/tests/test_observation_completeness.py -v` | 8 tests | **8/8 PASS**, 0.33s |
| `pytest openspiel_pyrants/tests/ -q` | 63 collected | **100% pass**, 58s |
| `pytest -q` (repo root, `just test`) | 151 collected | **3 FAILED, rest passed**: `tests/c_engine/test_card_zuggtmoy.py::test_zuggtmoy_eot_promote_two_other_cards_excludes_self`, `tests/c_engine/test_engine_c.py::test_air_elemental_option_1_focus_draw`, `tests/test_card_neogi.py::test_neogi_execution_model_deploys_four_and_random_mass_discard` |

**On the 3 full-suite failures:** identical 3 tests, identical failure reasons, to the ones
`f010-review-01.md` §4e already found and attributed to an unrelated, ongoing `engine_c`
card-execution-model backlog (Zuggtmoy self-promotion, Air Elemental option-1 draw count, Neogi
discard timing) — none touches `data/cards/catalog.json` or `engine_c/rules.c` from this diff,
which is confined to `engine_c/bindings/c_adapter.py` (Python-layer JSON projection) and test/doc
files. No new failure appeared; no prior failure disappeared. Not a regression from this diff.

**G4/G5 gates, independently re-measured:**

| Gate | Claimed | Independently measured |
|---|---|---|
| G4 Tier-1 cost | `_build_public_dict()` key set unchanged, cost within noise of 7.8 µs | Confirmed via `test_tier1_snapshot_shape_and_cost_unaffected` (part of the 8/8 pass above) — key set assertion plus a <100 µs trip-wire, both green |
| G5 search-time budget | 9.66× regression (0.165s → 1.589s at num_sims=200) | `f011_timing.py` re-run: **mean_wall pre=0.1646s, post=1.5892s → ratio 9.655×**, matching the claimed figure to 3 significant figures |

**No regression found. No invariant reversed. No previously-CONFIRMED/FIXED finding disturbed.**

## 5. NEW FINDINGS

None surfaced beyond what the fixing agent already filed as F-013 (board-projection cost
regression), which this review's own G5 re-measurement (§4e) independently reproduces at
9.655× — consistent with the ledger's 9.66×, not a new finding, the same one already on record
with `Status: OPEN`. No further investigation performed, per protocol (findings are not
investigated or fixed during review).

Count: **0 new findings.**

## 6. VERDICT

**ACCEPTED-WITH-DEBT — F-013 (board-projection cost, 9.66× search wall-time regression) remains OPEN.**

Every Hard Rule 8 component is satisfied: falsification test PASSES (§4a), conformance is
CONFORMANT (§2), zero regressions across the full blast radius plus the always-on battery plus
the full repo suite (§4b–e), and zero out-of-scope hunks (§1). The "debt" is not a defect in
this fix — it is the pre-registered, honestly-reported G5 cost finding (F-013) that the fix
plan itself flagged in advance as a permitted outcome ("if it does, this plan still lands
(correctness first) but Phase 6 must open a follow-up finding"). F-013 was opened, not buried,
and is correctly left `OPEN` rather than silently fixed inside this commit (which would itself
have been an out-of-scope hunk). The debt is: no large-scale ISMCTS throughput claim should be
made until F-013 closes via the narrower C-level board-only accessor its own resolution section
describes.

## 7. INVALIDATION CASCADE

Applying the rule ("any STRENGTH row ... goes STALE on ANY change to the engine, the binding,
the observation, the utilities, or the search") to `verdict.md` §1:

**Already STALE, unaffected by this review (no double-invalidation):**
- INV-7 (budget monotonicity), INV-8 (self-play calibration), INV-9 (baseline sanity) — marked
  STALE by `f010-review-01.md` for a different, already-sufficient reason (unseeded-resampler
  measurement). This fix is a second, independent reason they must not be cited pre-remeasurement
  (the observation content they were measured against has also now changed), but they were
  already correctly excluded from citation; no new STALE marking needed.

**Newly STALE (this review, first invalidation):**
- None. INV-10 (resource stability) is not a STRENGTH row (memory/tree-size, not agent
  strength/win-rate) and was not exercised by this diff's code path in a way that changes its
  prior measurement's validity — excluded from the radius in §3 with reason, not silently
  skipped.

**Not STALE:** INV-1 through INV-6 are non-strength structural/correctness checks, all
independently re-measured fresh at `a7cee83` in §4 above (not merely asserted from the diff).

**Count: 0 newly-STALE rows.** (3 rows — INV-7/8/9 — remain STALE from the prior review; not
re-counted here as this review's own invalidation.)

## 8. RECORD

This file. See `findings.md` and `verdict.md` for the corresponding ledger/verdict entries
appended by this review.

## 9. HANDOFF

**ACCEPTED.** Per Hard Rule 8, ACCEPTED requires test PASS + CONFORMANT + zero regressions +
zero out-of-scope hunks — all four are satisfied (§1, §2, §4). The ACCEPTED-WITH-DEBT
qualifier names F-013 (throughput regression) as tracked debt, not a rejection condition.

**Next finding in recommended order:** F-004 (`Returns()`/`UtilitySum` contract violated for
3–4 player games) — `verdict.md` §5 condition 2, the next listed blocking gate after F-011's
now-struck condition 1, and it blocks the project's own default configuration
(`just ismcts` runs `num_players=4`).

**Blocking findings remaining: 3** (F-004, F-002+F-003 counted together per `verdict.md` §5
condition 3, F-006) before GO, plus F-010's procedural closure already resolved by `2cfd836`.
F-013 is tracked debt (non-blocking for 2-player engine/performance work, blocking only for
throughput claims) and F-005/F-009 are non-blocking per `verdict.md` §5 condition 5.

STOP. Not beginning the next finding; not touching source.
