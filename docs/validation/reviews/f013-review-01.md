# F-013 Review 01 — Adversarial Review of the `CEngineAdapter` Board-View Cache

Reviewer role: adversarial, read-only outside `docs/validation/`. Did not write the fix.

## 0. LOAD

- **Target finding:** F-013 — "Board projection regresses `private_view_json` cost 9.66×;
  cache mitigates, narrower C accessor still warranted." Class `ENGINE-OPENSPIEL`. Severity
  **MINOR** (performance — non-blocking for 2-player engine/performance work, blocking for any
  large-scale ISMCTS throughput claim).
- **Commit range:** `e9a2702` (parent, F-002 fix — HEAD immediately before this fix) →
  `16f8712` ("perf: cache board projection on CEngineAdapter (F-013)"). Current repo `HEAD` is
  `d26a920`, three commits later (F-004's fix `3508466`, its review-recording commit `f473855`,
  and an F-003 baseline-capture commit `a6509b1`, plus a repowise-metadata commit); none of those
  touch `engine_c/bindings/c_adapter.py`, `engine_c/bindings/view.py`, the F-013 test file, or the
  F-013 harness/baseline files (verified: `git diff 16f8712 HEAD --stat -- engine_c/bindings/
  openspiel_pyrants/tests/test_board_view_cache.py docs/validation/harness/f013_timing.py`
  is empty for all of those paths), so re-running against current `HEAD` is equivalent to
  re-running at `16f8712` for every check this review performs.
- **Scope note (pre-review housekeeping):** at the start of this review session the working tree
  mixed F-004's already-reviewed-but-uncommitted fix with F-013's target fix, plus untracked F-003
  exploratory artifacts and an unrelated `.claude/CLAUDE.md` edit. Per the review protocol's stop
  conditions, the user was asked how to proceed and chose to have F-004 committed first. It was
  (commits `3508466`/`f473855`), which is how `16f8712` (F-013, committed *before* F-004
  chronologically) ended up cleanly isolated once the tree was clean. That commit is bookkeeping
  for a *previously already-adjudicated* review (`docs/validation/reviews/f004-review-01.md`,
  ACCEPTED-WITH-DEBT, unchanged) — it is not itself under review here. One untracked file remains
  in the tree, `docs/validation/grug-verdict.md` (a stylistic rewrite of `verdict.md` predating
  this fix, harmless, not part of any diff, not touched).
- **No `register.md` exists in this repo** (confirmed via `Glob`, same finding as
  `f010-review-01.md` §7, `f011-review-01.md` §0, and `f004-review-01.md` §0). `verdict.md` §1 is
  used as the register-equivalent throughout.
- **Prior review:** none for F-013 — this is Review 01. Most recent adjacent review:
  `docs/validation/reviews/f004-review-01.md` (F-004, working tree at base `b0f3173`,
  ACCEPTED-WITH-DEBT).
- **Pre-registered falsification test** (quoted verbatim from `findings.md` F-013, read before any
  diff inspection):
  > Falsification test: `python -u docs/validation/harness/f011_timing.py` before/after, compare
  > mean wall-time.
  > Expected if REAL: mean wall-time ratio > 2×.

  Note, stated for the record and not remedied here (Hard Rule 7, append-only): unlike every other
  finding in this ledger, F-013's own entry never states an "Expected if FALSE POSITIVE" clause.
  This is consistent with F-013's unusual origin — it was filed already `CONFIRMED` (discovered
  empirically by F-011's own G5 timing gate, with the 9.66× regression already measured at filing
  time), not filed `OPEN` pending a first test run. Per Hard Rule 3, `f011_timing.py` — the
  originally-registered script — is the one used below, not the newly-added `f013_timing.py`
  (compared byte-for-byte in §1).

## 1. DIFF AUDIT

`git diff e9a2702 16f8712` touches 3 tracked files plus 5 new untracked-then-added files.
Hunk-by-hunk classification:

| File | Classification | Notes |
|---|---|---|
| `engine_c/bindings/c_adapter.py` | IMPLEMENTS-FINDING | the only production-code file touched; adds `_board_cache` to `__slots__`, initializes it to `None` in `__init__`, resets it to `None` in `apply()`, and makes `_board_nodes_view()` populate-once/return-a-copy |
| `openspiel_pyrants/tests/test_board_view_cache.py` (new) | TEST-CHANGE | new T1/T2/T3/T4/T5 suite (5 tests, not parametrized) |
| `docs/validation/f013-fix-plan.md` (new) | DOC-CHANGE | the plan document itself |
| `docs/validation/harness/f013_timing.py` (new) | DOC-CHANGE (evidence) | G4 gate probe script, functionally a byte-for-byte duplicate of the pre-registered `f011_timing.py` (verified in this section) |
| `docs/validation/baseline/f013_timing.pre.txt`, `.post.txt` (new) | DOC-CHANGE (evidence) | required by plan Phase 0/4 |
| `docs/validation/findings.md` | DOC-CHANGE | F-013 status flip (`OPEN` → `CONFIRMED — MITIGATED`) + Resolution/Observed/Verdict-rationale text, required by plan Phase 6.2 |
| `docs/validation/verdict.md` | DOC-CHANGE | F-013 moved to "MITIGATED", §5 condition 5 rewritten, required by plan Phase 6.1 |

**No OUT-OF-SCOPE hunks.** Every touched file maps to a phase the fix plan explicitly authorizes
(§5 Phase 2 for `c_adapter.py`; §4 Phase 1 for the test file; §3/§7 Phase 0/4 for the harness
script and baseline captures; §9 Phase 6 for the ledger updates). Mechanically verified per the
plan's own G0/Phase-5 checklist item: `git show --stat 16f8712` touches exactly
`engine_c/bindings/c_adapter.py`, `openspiel_pyrants/tests/test_board_view_cache.py`, and four
`docs/validation/*` paths — **zero** diff in `openspiel_pyrants/` (non-test), `scripts/`, or
anywhere under `.venv/`. G0 holds.

**The `c_adapter.py` production diff, read in full** (not summarized from the plan): adds
`"_board_cache"` to the `__slots__` tuple; adds `self._board_cache = None` at the end of
`__init__`; adds `self._board_cache = None` at the end of `apply()`, immediately after
`self._state = new_state`; and rewrites `_board_nodes_view()` from an unconditional
build-and-return into a check-cache/build-if-empty/return-a-shallow-copy. This is exactly Phase
2 §5.1–5.3 of the fix plan, verbatim, including the shallow-copy judgment call flagged in the
plan's own §6. Independently confirmed via `grep -n "self\._state = " engine_c/bindings/
c_adapter.py`: exactly 3 matches (`__init__:45`, `apply:119`, `destroy:259`), matching the plan's
own claimed invalidation surface and the new T5 test's assertion.

**`f013_timing.py` vs. the pre-registered `f011_timing.py`:** read both files in full. They are
identical except for the docstring (references "F-013 gate G4" vs. "F-011 gate G5" and the
diff-target file) and the `print()` label string (`"f013_timing"` vs. `"f011_timing"`). `NUM_SIMS`,
`N_SEARCHES`, the fixed-root construction (`fresh(game, 42)` + 40 `RandomBot(131)` steps), and the
per-search bot seeding (`1000 + i`) are byte-identical. This is a faithful duplicate, not a
substitution that changes what is measured — but see the discrepancy noted below.

**Discrepancy (not gaming, but a process deviation from the plan's own stated method):** the fix
plan's Phase 0 (§3) instructs capturing the pre-fix baseline by running `f011_timing.py` and
piping its output to `baseline/f013_timing.pre.txt`. The actual content of that file
(`f013_timing num_sims=200 searches=10 mean_wall=1.7453s`) carries the `f013_timing` print label,
which only `f013_timing.py` emits — meaning the "pre" baseline was actually captured by running
the *new* script, not the pre-registered one the plan itself specifies. Because the two scripts
are otherwise identical (confirmed above), this does not change the measured number, but it is a
documentation-accuracy gap in how Phase 0 was actually executed versus how the plan says it was
executed. Not elevated to a ledger finding (no rulebook/whitepaper/code defect — see `f004-review-
01.md` §1 for the precedent of treating this class of issue as a noted inaccuracy, not a finding).

**Gaming checklist (Hard Rule 4), run against the one TEST-CHANGE hunk:**

| Hunk | Weakened assertion | Deleted/skipped test | Widened tolerance | Reduced N | Seed pinned to pass | Special-cased input | Swallowed exception | Removed invariant | Disabled warning |
|---|---|---|---|---|---|---|---|---|---|
| `test_board_view_cache.py` (new, 5 tests) | clear | clear | clear | clear | clear | clear | clear | clear | clear |

Cleared. New file, checked for the equivalent trap (a new test written to be trivially
satisfiable): T2 (`test_repeated_calls_hit_the_cache`) asserts `spy.call_count == 1` via
`mock.patch.object(view_mod, "build_c_board_view", wraps=...)` — a real call-count spy on the
actual production function, not a stub that can't fail. T4 asserts `spy.call_count == 2` (one per
independently-constructed clone/determinization), the exact number the plan's own "fresh cache per
construction" design requires — not loosened to `>= 1` or similar. T5's structural trip-wire
(`assert len(sites) == 3`) is a strict equality, not a range. T1/T3 are unmutated-repeated-call and
apply-then-differs controls with no tolerance windows. The fixed root (`shuffle_seed=42`,
`n_moves=40`) reused across T2–T4 is the same fixture already established by `f011_timing.py`/
`f013_timing.py` for benchmarking, not a seed newly chosen for this test file to pass. No
`except:` blocks anywhere in the file. Ran the file directly (§4 below): 5/5 actually execute, not
silently skipped by `requires_c_engine`.

**Diff vs. plan:**
- Phase 2's exact code (fix plan §5.1–5.3) is present verbatim, confirmed above.
- Phase 1's T1–T5 (fix plan §4 table) are present, named identically to the plan's table. T6
  (the timing script) is present as `docs/validation/harness/f013_timing.py`.
- Phase 4's required commands were run (evidenced by the baseline files and the ledger's cited
  numbers, independently re-run fresh in §4 below rather than trusted from the ledger).
- Phase 6's required verdict/findings updates are both present (§8/§9's diff table above).
- **What the plan promised that is not fully honest in the ledger text it produced:** the fix
  plan's own G4 gate (§2) is defined as inheriting "the original G5 threshold from
  `f011-fix-plan.md`" — and F-011's own fix plan defines that G5 threshold explicitly: "End-to-end
  ISMCTS wall-time... does not regress by more than 2×" relative to the **pre-F-011** baseline
  (`f011-fix-plan.md:128`, confirmed by reading that file directly, not the F-013 plan's
  restatement of it). By that literal definition, the relevant ratio is
  post-fix-mean / pre-F-011-mean. Measured: `1.0500s / 0.1646s = 6.38×` (ledger's own numbers) —
  independently re-measured in §4 as `6.42×` — **not under 2×.** The ledger's F-013 entries in both
  `findings.md` and `verdict.md` instead report *"1.66× vs. the pre-fix regression, under the 2×
  gate"* — a ratio computed as `pre-F-013-recapture (1.7453s) / post-F-013 (1.0500s)`, a different,
  much easier-to-clear comparison than what G4 actually specifies. This is **not gaming** in the
  Hard-Rule-4 sense (no test file was touched, no assertion weakened — G4 has no pytest assertion
  at all, it's a script + a human-read threshold) and it is **not concealment** — the true `~6.4×`
  residual is stated in the very same sentence in both documents, and the overall status is
  honestly `MITIGATED`, not `FIXED`. But taken at face value, "under the 2× gate" is an incorrect
  characterization of gate G4, which by its own borrowed definition is **not met**. Recorded here
  as an independent correction (same posture as `f004-review-01.md`'s correction of the fix plan's
  "zero matches" grep claim) — not elevated to a new ledger finding, because it names no rulebook,
  whitepaper, or code defect, only an imprecise gate characterization whose underlying number is
  disclosed accurately elsewhere in the same text. It changes the *content* of this review's
  verdict (see §6), not its category.
- Nothing else the plan promised is absent, and nothing beyond the plan's authorized scope was
  added.

**Verdict of this step:** 0 out-of-scope hunks, 1 test-change hunk cleared, 1 documentation
characterization independently corrected (not a new finding).

## 2. CONFORMANCE REVIEW

**Rulebook:** `[absent]` — re-confirmed by re-reading `findings.md` F-013 directly: unlike every
other entry in the ledger, F-013 has no `Rulebook:`/`Whitepaper:` line at all (a pre-existing gap
in how the finding was originally filed by the F-011 fix, not something introduced by this diff —
not remedied here per Hard Rule 7, append-only). This is a pure engine/API performance concern,
the same citation-free posture `f010-review-01.md` documented for F-010.

**Whitepaper:** `[absent]`, same reasoning.

**What the code now does**, at the fixed commit (`engine_c/bindings/c_adapter.py:239-254`,
`_board_nodes_view`):
```python
def _board_nodes_view(self) -> list[dict]:
    if self._board_cache is None:
        from .view import build_c_board_view
        view = build_c_board_view(self)
        self._board_cache = [ ... ]   # same six fields per node as before this fix
    return list(self._board_cache)
```
`apply()` (`:100-120`) resets `self._board_cache = None` immediately after reassigning
`self._state`, the one mutation site on an existing adapter (confirmed 3 total `self._state = `
sites, §1). `__init__` (`:38-50`) sets `self._board_cache = None` unconditionally, and every
construction path — fresh (`__init__` directly), `__deepcopy__` (`:52-60`), `determinize()`
(`:78-87`), `clone_via_replay()` (`:89-95`) — goes through `CEngineAdapter(...)`, so every
independently-constructed adapter starts with an empty cache (verified by reading each method
body directly, not assumed from the plan's table).

**Verdict: CONFORMANT.** There is no rulebook or whitepaper behavior in play — this is a pure
internal-caching optimization to one class. The relevant bar is behavioral parity (the fix plan's
own G1), which holds: `_board_nodes_view()`'s cached branch constructs the identical dict shape
from the identical `build_c_board_view` call the pre-fix code made unconditionally; the only
change is *when* that call happens, not what it returns. Independently re-verified by execution in
§4 (T1's byte-identical-repeated-calls control, and this review's own live G2 repro), not read off
the diff alone.

## 3. BLAST RADIUS (derived independently)

Changed symbols: `CEngineAdapter.__slots__`, `.__init__`, `.apply()`, `._board_nodes_view()` in
`engine_c/bindings/c_adapter.py`. This is the exact same call chain F-011 added
(`private_view_json` → `_board_nodes_view` → `build_c_board_view`), so the radius mirrors F-011's
own, restricted to what a *caching* change (not a *content* change) can plausibly disturb.

**Included:**
- **T1–T5 (`test_board_view_cache.py`)** — direct target.
- **F-011 (`CONFIRMED — FIXED`, ACCEPTED-WITH-DEBT)** — this fix's entire surface is inside the
  function F-011 added. If caching served a stale board across two genuinely different states,
  F-011's own falsification test (`inv_b2.py`, INV-4b) would be the first thing to catch it.
  Included, primary.
- **INV-4a (leakage)** — a caching bug could in principle leak a *previously computed* board
  across a hidden-state-only difference if cache keys were ever shared across adapters; `__init__`
  always zeroing the cache on every independent construction (verified §2) is the reason this
  shouldn't happen, but "shouldn't" isn't "tested" — included to verify at scale.
- **INV-5 (determinization consistency + conservation)** — exercises T4's exact scenario (many
  independent determinizations/clones, each needing a correctly-fresh cache) at N=2,400, far
  beyond T4's N=2. Included.
- **F-010's `det_bot.py` (B1, node-keying reproducibility)** — `information_state_string` is the
  ISMCTS node key; G1 requires its *content* to be unchanged, but a caching bug that returned
  stale data on some calls and fresh on others could change *which* actions get explored even
  while "looking like" a speed fix. Included.
- **F-002 (`f002b.py`)** — shares no code with `c_adapter.py`'s board cache, but the fix plan's own
  radius (§7) includes it because `private_view_json`'s fingerprint use makes it cheap to
  re-confirm; matching that inclusion here rather than excluding it on a technicality.
- **Always-on regardless of radius (Hard Rule 4c):** replay determinism (INV-1), clone
  independence (INV-2 — doubly relevant here since `__init__`/`determinize`/`clone_via_replay` are
  literally in the changed-symbol list), legality (INV-3), chance mass (INV-6).

**Excluded, with reason:**
- **F-001, F-003, F-005, F-006, F-007, F-008, F-009, F-012, F-014** — none reads or is read by
  `CEngineAdapter`'s board-cache slot; each lives in `action_encoding_c.py`, chance-node handling,
  seating logic, `run_ismcts.py` argument defaults, a refuted claim, an untestable claim, hardcoded
  outcome counts, `resample_from_infostate`'s `Generator` branch, or `engine_c/actions.c`'s
  `give_insane_outcast` — none of which this diff touches or is touched by. Excluded.
- **F-004** — lives entirely in `openspiel_pyrants/game_c.py`, a file G0 explicitly forbids this
  fix from touching (confirmed zero diff there in §1); no shared code path with `c_adapter.py`.
  Also chronologically impossible to interact: `16f8712` (this fix) was committed *before*
  `3508466` (F-004's fix). Excluded.
- **INV-7/8/9 (STRENGTH rows)** — already STALE from `f010-review-01.md`/`f011-review-01.md`/
  `f004-review-01.md`, for independent reasons each sufficient on their own; this fix is a
  performance-only change to the binding, which is *also* an Hard-Rule-4c trigger ("the binding"),
  but since they are already correctly excluded from citation, no new STALE marking is needed
  (§7).
- **INV-10 (resource stability / tracemalloc)** — measures Python memory/tree-size, not
  `private_view_json` content; same exclusion reasoning `f011-review-01.md` applied. Excluded.

**Comparison to the fixing agent's declared radius:** `f013-fix-plan.md` §7 Phase 4 explicitly
lists `f013_timing.py` (G4), `inv_a.py` (G5, INV-1/2/3/6), `inv_b.py` (G5, INV-4a/5), `inv_b2.py`
(G5, INV-4b), `det_bot.py` (G5, B1), and `f002b.py` (G5, F-002) — this matches my derived radius
exactly, item for item. **Mine is not wider here** — unlike `f004-review-01.md`'s finding that the
fixing agent's radius reasoning omitted an explicit Hard-Rule-4c citation, this plan's own §2 gate
table already enumerates precisely the checks a correct radius analysis would independently
produce. Stated for the record rather than manufacturing a wider radius that wouldn't be honest.

## 4. RE-RUN

All commands run from repo root, `.venv/Scripts/python.exe -u <path>`, against `HEAD` (`d26a920`),
equivalent to `16f8712` for every path this review touches (§0).

**a. Pre-registered falsification test**

| Check | Command | N / seeds | SHA | Prior (F-011 post-fix, pre-F-013) | New (this review, post-F-013) |
|---|---|---|---|---|---|
| Mean wall-time, `num_sims=200`, fixed root | `docs/validation/harness/f011_timing.py` | N=10 searches, fixed root seed 42 + 40-step `RandomBot(131)`, per-search bot seeds 1000+i | `d26a920` | `1.5892s` (`f011_timing.post.txt`, F-011 baseline) / pre-F-011 `0.1646s` (`f011_timing.pre.txt`) | **`1.0569s`** (this run) |

Ratio vs. the pre-F-011 baseline: `1.0569 / 0.1646 = 6.42×`.

✅ Falsification test (the finding's own pre-registered criterion, "Expected if REAL: mean
wall-time ratio > 2×"): **still matches "Expected if REAL."** `6.42× > 2×`. The defect, as the
finding's own falsification test defines it, is **still present** post-fix — reduced from `9.66×`
to `~6.4×`, a real and independently-confirmed improvement, but not eliminated. This is consistent
with, not contradicted by, the ledger's own `CONFIRMED — MITIGATED` (not `FIXED`) status.

**b. Blast-radius checks**

| Check | Command | N | Prior | New |
|---|---|---|---|---|
| T1–T5 (`test_board_view_cache.py`) | `.venv/Scripts/python.exe -m pytest openspiel_pyrants/tests/test_board_view_cache.py -v` | 5 tests | N/A (new file) | **5/5 PASS**, 0.36s |
| F-011 falsification (INV-4b decisive) | `docs/validation/harness/inv_b2.py` | 403 board-differing pairs | 403/403 differ (was 403/403 identical, pre-F-011) | **403/403 differ — unchanged** |
| INV-4a (leakage) | `docs/validation/harness/inv_b.py` | N=300 | 0 violations | **0 violations — unchanged** |
| INV-5 (determinization diversity + conservation) | `docs/validation/harness/inv_b.py` (same run) | 200 info sets × K=12 = 2,400 | mean 11.11/12, min 7, max 12, singletons 0, conservation 0/2400 | **mean 11.11/12, min 7, max 12, singletons 0, conservation 0/2400 — unchanged, exact** |
| F-010 `det_bot.py` B1 | `docs/validation/harness/det_bot.py` | 10 identically-seeded searches, fixed root, num_sims 20 & 200 | 1 distinct chosen action | **1 distinct chosen action — unchanged** (also B2 root-intact, B3/B4 controls all consistent) |
| F-002 (`f002b.py`) | `docs/validation/harness/f002b.py` | 3 controlled reshuffles | 3/3 same-perm-when-fixed, 3/3 changed-on-counter, 3/3 changed-on-seed | **3/3, 3/3, 3/3 — unchanged** |

**Live manual re-verification of G2** (the fix plan's own Phase-5 checklist demands this be
"explicitly re-verified with a live repro, not just T3's pass" — done independently, not by
reading `test_board_view_cache.py`'s own helpers): wrote a standalone script
(outside the repo, in the reviewer's scratch directory) that loads the game directly, calls
`private_view_json` twice pre-move (confirms cache warms and repeats), asserts
`adapter._board_cache is not None` after the first call, applies one legal `initial_placement`
move, asserts `adapter._board_cache is None` immediately after `apply()`, then calls
`private_view_json` again and confirms the board content actually changed:
```
pre-move board hash: -8320903151743371751
applying move id 0 -> initial_placement(target_node_id='site_blingdenfire')
post-move board hash: 5082652388991587135
board changed: True
G2 LIVE REPRO: PASS - post-apply view reflects the new board, not a stale cache
```
✅ G2 independently confirmed via live repro, not merely via T3.

**T5's structural trip-wire — verification method note:** the fix plan's own Phase-5 checklist
asks the reviewer to "temporarily add [a fourth `self._state = ` site] locally, confirm T5 catches
it, revert." This review does **not** do that: Hard Rule 1 forbids any write to source, even a
reverted one. Verified instead by static reading of T5's own matcher
(`re.search(r"self\._state\s*=", line)` combined with a `def \w+` tracker for the enclosing
method) — the regex is unconditional on which method it's in and would match a textually-added
fourth site in any method body. This is a weaker substitute than a live mutation-and-revert, noted
explicitly as a deviation rather than silently presented as equivalent.

**c. Always-on regardless of radius**

| Check | Command | N | SHA | Prior | New |
|---|---|---|---|---|---|
| Replay determinism (INV-1) | `docs/validation/harness/inv_a.py` | 100 seed pairs (1-100) | `d26a920` | PASS, 0 failures | **PASS, 0 failures** |
| Clone independence (INV-2) | `docs/validation/harness/inv_a.py` (same run) | 235 probes, seeds 1-100 | `d26a920` | PASS, N=235 | **PASS, N=235, 0 failures** |
| Legality (INV-3) | `docs/validation/harness/inv_a.py` (same run) | 1,200 states, seeds 1-22 | `d26a920` | empty=0 dup=0 oor=0 | **N=1200, empty=0 dup=0 oor=0 — unchanged** |
| Chance mass (INV-6) | `docs/validation/harness/inv_a.py` (same run) | 30 nodes, seeds 1-30 | `d26a920` | 0 violations | **N=30, 0 violations — unchanged** |

Full run output archived; every field (`N`, `seeds`, `failures: []`, `pass: true`) matches
`verdict.md` §1's recorded values exactly, not merely "still passing."

**d. Previously-CONFIRMED findings inside the radius**

| Finding | Prior status | Re-run result |
|---|---|---|
| F-011 | CONFIRMED — FIXED, ACCEPTED-WITH-DEBT | INV-4b 403/403 unchanged (§4b); `_build_public_dict()` (F-011's own G4, Tier-1 cost) confirmed untouched by this diff (`git diff` empty for that method, §1) |
| F-010 | Fix logic verified, commit REJECTED-SCOPE (re-submission pending) | `det_bot.py` B1 unchanged, 1 distinct action (§4b) |
| F-002 | CONFIRMED — FIXED (not yet independently reviewed) | `f002b.py` unchanged, 3/3+3/3+3/3 (§4b) |

**e. Regression sweep beyond the declared radius**

| Command | N | Result |
|---|---|---|
| `.venv/Scripts/python.exe -m pytest openspiel_pyrants/tests/ -q` | 78 collected | **78/78 PASS**, 48.49s |
| `.venv/Scripts/python.exe -m pytest -q` (repo root, `just test` equivalent) | full suite | **3 FAILED, rest passed**: `tests/c_engine/test_card_zuggtmoy.py::test_zuggtmoy_eot_promote_two_other_cards_excludes_self`, `tests/c_engine/test_engine_c.py::test_air_elemental_option_1_focus_draw`, `tests/test_card_neogi.py::test_neogi_execution_model_deploys_four_and_random_mass_discard` |

**On the 3 full-suite failures:** identical 3 tests, identical names, to the ones
`f010-review-01.md`/`f011-review-01.md`/`f004-review-01.md` already found and attributed to an
unrelated, ongoing `engine_c` card-execution-model backlog — none touches
`engine_c/bindings/c_adapter.py`, the only production file this diff changes. No new failure
appeared; no prior failure disappeared. Not a regression from this diff.

**No regression found. No invariant reversed. No previously-CONFIRMED/FIXED finding disturbed.**
The one number that *did* move (the falsification-test ratio, `9.66×` → `6.42×`) moved in the
direction the fix intends, consistent with `MITIGATED` rather than a clean pass or a regression.

## 5. NEW FINDINGS

None. The G4-gate-characterization imprecision identified in §1 ("under the 2× gate" describing a
different ratio than the gate's own borrowed definition) is not elevated to a ledger finding: it
names no rulebook, whitepaper, or code defect, and the true `~6.4×` number is disclosed accurately
in the same sentence in both `findings.md` and `verdict.md`. It is folded into this review's
verdict as debt (§6) rather than filed separately, matching the precedent `f004-review-01.md` §1
set for the "182 matches" grep correction.

Count: **0 new findings.**

## 6. VERDICT

**ACCEPTED-WITH-DEBT** — two items:

1. **The performance regression is only partially closed, not eliminated.** The finding's own
   pre-registered falsification test, re-run today, still matches "Expected if REAL"
   (`6.42× > 2×`, §4a) — down from `9.66×`, a genuine and independently-confirmed improvement, but
   the fix plan's own G4 gate (borrowed verbatim from `f011-fix-plan.md`'s G5, itself defined
   relative to the pre-F-011 baseline) is **not cleared**. No large-scale ISMCTS throughput claim
   should be made until the narrower C-level `engine_build_board_view`-only accessor (already
   recommended by both `f011-fix-plan.md` §10 and this fix's own §11 "out of scope" section) is
   built and re-measured.
2. **The ledger's gate characterization needs a correction, not a code change.** `findings.md` and
   `verdict.md` both describe the post-fix number as "1.66× vs. the pre-fix regression, under the
   2× gate" — a ratio computed against the freshly-recaptured pre-F-013 baseline (`1.7453s`), not
   against the pre-F-011 baseline the G4 gate is actually defined against. The true, honestly-
   disclosed number in the very same sentence (`~6.4×` residual) is what should be read as "the
   gate result," and by that number G4 is not met. This is a documentation-precision debt, not a
   rejection trigger: Hard Rule 4's gaming checklist does not fire (no test or assertion was
   touched), and the overall status the ledger chose — `MITIGATED`, explicitly not `FIXED`,
   explicitly still "blocking for any large-scale ISMCTS throughput claim" — is itself honest about
   incomplete closure.

Every Hard Rule 8 component the fix can satisfy, it does: conformance is CONFORMANT (§2, no
rulebook/whitepaper concern, behavioral parity holds), zero regressions across the full blast
radius plus the always-on battery plus the full repo suite (§4), and zero out-of-scope hunks (§1).
The one component that does not cleanly resolve — "test PASS" — is exactly what `MITIGATED` (as
opposed to `FIXED`) is supposed to signal: the fix is real, verified, and correctly confined, but
the underlying defect the falsification test checks for is still measurably present. This is the
same shape of debt `f011-review-01.md` accepted for F-011's own failed G5 gate (which is the
direct ancestor of this one) — a correctness/performance fix that ships honestly short of its own
numeric target, with a named, already-scoped follow-up.

## 7. INVALIDATION CASCADE

Applying Hard Rule 4c ("any STRENGTH row ... goes STALE on ANY change to the engine, the binding,
the observation, the utilities, or the search") to `verdict.md` §1:

**Already STALE, unaffected by this review (no double-invalidation):**
- INV-7 (budget monotonicity), INV-8 (self-play calibration), INV-9 (baseline sanity) — marked
  STALE by `f010-review-01.md`, reaffirmed by `f011-review-01.md`, reaffirmed again by
  `f004-review-01.md` (three independent, already-sufficient reasons). This fix is a *fourth*
  independent trigger (a change to "the binding" itself, `engine_c/bindings/c_adapter.py`) — but
  they were already correctly excluded from citation; no new STALE marking needed.

**Newly STALE (this review, first invalidation):** None. No other STRENGTH row exists in
`verdict.md` §1 beyond INV-7/8/9.

**Not STALE:** INV-1 through INV-6 are non-strength structural/correctness checks, all
independently re-measured fresh in §4 above (not merely asserted from the diff).

**Count: 0 newly-STALE rows.** (3 rows — INV-7/8/9 — remain STALE from prior reviews; not
re-counted here as this review's own invalidation.)

## 8. RECORD

This file. See `findings.md` and `verdict.md` for the corresponding ledger/verdict entries
appended by this review.

## 9. HANDOFF

**ACCEPTED-WITH-DEBT.** Debt: (1) the residual `~6.4×` wall-time regression vs. the pre-F-011
baseline persists and the finding's own falsification test still returns "Expected if REAL" —
F-013 stays open as a tracked, non-blocking-for-2-player / blocking-for-throughput-claims item
until the narrower C-level `engine_build_board_view` accessor lands; (2) the ledger's "under the
2× gate" phrasing in `findings.md`/`verdict.md` should be read alongside the `~6.4×` figure in the
same sentence, not in isolation — recorded as a correction, not a new finding, per Hard Rule 7 the
existing text is not edited.

**Next finding in recommended order:** F-002 + F-003 (`verdict.md` §5 condition 3) — F-002's half
(reroll `shuffle_seed`/`shuffle_counter`) is already committed (`e9a2702`) and re-confirmed
undisturbed by this review (§4b/d) but has not yet had its own dedicated adversarial review; F-003
(exposing mid-game random events as real OpenSpiel chance nodes) remains the larger open design
work, with `docs/validation/harness/f003_chance_nodes.py` and
`docs/validation/baseline/f003_chance_nodes.pre.txt` already present in the working tree
(untracked) as apparent in-progress groundwork, per `git status` at the start of this session.

**Blocking findings remaining: 2** (F-002+F-003 counted together per `verdict.md` §5 condition 3,
and F-006) before GO — unchanged by this review, since F-013 was already non-blocking-for-GO
(tracked debt per `verdict.md` §5 condition 5) both before and after this fix. F-014 remains
tracked debt from `f004-review-01.md`. F-005/F-009 remain non-blocking per `verdict.md` §5
condition 5.

STOP. Not beginning the next finding; not touching source.
