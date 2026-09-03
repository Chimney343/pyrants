# F-004 Review 02 — Second-Pass Adversarial Review of the Utility-Contract Fix

Reviewer role: adversarial, read-only outside `docs/validation/`. Did not write the fix or the
prior review. Commissioned as a second independent pass over an already-`ACCEPTED-WITH-DEBT`
finding, at the user's explicit request (not because a new fix landed).

## 0. LOAD

- **Target finding:** F-004 — "`Returns()`/`UtilitySum`/`MinUtility`/`MaxUtility` contract
  violated for 3–4 player games." Class `ENGINE-OPENSPIEL`. Severity **CRITICAL**.
- **Prior review:** `docs/validation/reviews/f004-review-01.md` (working tree at base `b0f3173`,
  committed as `3508466`): **ACCEPTED-WITH-DEBT** (F-014 open — uncapped `insane_outcast`
  issuance makes `min_utility=-50.0` practical, not formally tight).
- **Commit range checked:** `3508466` → `HEAD` (`74f2be31716712d5fb9385c2a524b8747dba3b9e`).
  `git diff 3508466 HEAD --stat -- openspiel_pyrants/game_c.py
  openspiel_pyrants/tests/test_utility_contract.py` → **empty**. Zero drift.
- **Working tree:** clean except `.claude/CLAUDE.md`.
- **Pre-registered falsification test** (quoted verbatim, unchanged):
  > Falsification test: `pyspiel.load_game("python_pyrants_c", {"num_players": "4"}).new_initial_state()`,
  > play to terminal, call `.returns()`, and check `sum(returns) == 0` and `all(r >= -400 for r in returns)`
  > against the declared contract.
  > Expected if REAL: `sum(returns())` is strongly positive and no return is ever negative.
  > Expected if FALSE POSITIVE: Observed returns are numerically consistent with the declared
  > zero-sum, symmetric-bound contract.

## 1. DIFF AUDIT

No new diff since Review 01 (§0). Re-read `_build_c_game_info` directly at `HEAD`
(`openspiel_pyrants/game_c.py:65-81`), byte-identical to what Review 01 quoted:
```python
max_utility = 200.0 if num_players == 2 else 400.0
if num_players == 2:
    min_utility = -max_utility
    utility_sum = 0.0
else:
    min_utility = -50.0
    utility_sum = None
```
`returns()` (`state_c.py:171-187`) re-confirmed byte-unchanged (`git diff 3508466 HEAD --
openspiel_pyrants/state_c.py` empty). 0 out-of-scope hunks (nothing new), 0 new test changes.

## 2. CONFORMANCE REVIEW

**Rulebook** (`docs/tyrants-rulebook.md` § Final Scoring, ≤15 words, re-quoted):
> "The player with the most VP at the end of the game wins" [VP sources are additive]

**Whitepaper:** `[absent]` — unchanged, re-confirmed.

**Verdict: CONFORMANT.** Unchanged from Review 01 — this is a metadata-only correction;
`returns()` is untouched and confirmed so again at `HEAD`.

## 3. BLAST RADIUS (derived independently)

Re-derived: **Included** — T1–T5 direct target; G5 zero-production-consumers must be re-checked
live, not assumed still true; STRENGTH rows (INV-7/8/9) per Hard Rule 4c ("the utilities"),
already STALE, not re-marked. Always-on: INV-1/2/3/6.

**Excluded, with reason:** identical to Review 01's reasoning — F-001/F-002/F-003/F-005 (disjoint
code paths, incidentally unaffected), F-006/F-007/F-008 (no overlap), F-009 (same function,
different untouched line, re-confirmed), F-010/F-011/F-012/F-013 (no shared string/field —
`_build_c_game_info`'s three scalars feed no ISMCTS node key or rollout input), INV-4a/4b/5/10
(no interaction with `GameInfo` scalars).

**Comparison to Review 01's declared radius:** identical — nothing has entered or left
`_build_c_game_info`'s dependency graph since.

## 4. RE-RUN

All commands run fresh this session at `HEAD` (`74f2be31716712d5fb9385c2a524b8747dba3b9e`).

**a. Pre-registered falsification test**

| Check | Command | N / seeds | Prior (Review 01) | New (this review) |
|---|---|---|---|---|
| `num_players∈{2,3,4}` returns vs. declared contract | `harness/f004_utility.py` (T5) | N=50 games/count | contract satisfied, 0/50 out-of-bounds | **0/50 out-of-bounds; `n==2` sum==0.0 violations=0/50; `n==3` min=0.0 max=18.0; `n==4` min=0.0 max=17.0** |

✅ PASS, matches Review 01 to within expected seed-driven sample variance (both runs are N=50
random-policy games, not identically seeded replays — the underlying contract-satisfaction
property is what's being re-verified, and it holds).

**b. Blast-radius checks**

| Check | Command | N | Prior | New |
|---|---|---|---|---|
| T1–T5 suite | `pytest openspiel_pyrants/tests/test_utility_contract.py -v` | 8 tests | 8/8 | **8/8 PASS** |
| G5 zero production consumers | `grep` (Grep tool) for `\.utility_sum()\|\.min_utility()\|\.max_utility()` across `*.py` | full repo | 3 files, all `docs/validation/`/test | **same 3 files: `harness/f004_utility.py`, `harness/findings.py`, `tests/test_utility_contract.py` — zero in `scripts/`, `openspiel_pyrants/` (non-test), `engine_c/`** |
| T6 stress probe | `harness/f004_utility.py` (T6) | N=200×3 + 9 injections | worst 2p=-23.0, 3p/4p=0.0; injection bounds -30/-50/-80 | **worst 2p=-23.0, 3p=0.0, 4p=0.0; injection bounds -30/-50/-80 across all player counts — byte-identical** |

**c. Always-on**

| Check | N | Prior | New |
|---|---|---|---|
| INV-1 | 100 | PASS | **PASS, 0/100** |
| INV-2 | 235 | PASS | **PASS, N=235** |
| INV-3 | 1200 | PASS | **PASS, empty=0 dup=0 oor=0** |
| INV-6 | 30 | PASS | **PASS, bad=0** |

**d. Previously-CONFIRMED findings inside the radius**

None — same conclusion as Review 01 (§3): no previously-fixed finding shares a plausible
interaction mechanism with `_build_c_game_info`'s three scalar fields.

**e. Regression sweep**

| Command | N | Result |
|---|---|---|
| `pytest openspiel_pyrants/tests/ -q` | 88 collected | **78 passed, 10 failed** — all 10 the F-003 Part B RED-test suite, postponed, unrelated to `game_c.py` |
| `pytest -q` (repo root) | full suite | same **3 pre-existing failures**, 1 skip |

**No regression found. No invariant reversed. No previously-CONFIRMED finding disturbed.**

## 5. NEW FINDINGS

None. F-014 remains on record, `OPEN`, re-confirmed present (not re-investigated, per Hard Rule
5) via T6's byte-identical injection-bound reproduction (§4b).

Count: **0 new findings.**

## 6. VERDICT

**ACCEPTED-WITH-DEBT** — F-014 remains open, unchanged from Review 01. All Hard Rule 8
components hold: test PASS (§4a), CONFORMANT (§2), zero regressions (§4), zero out-of-scope
hunks (§1).

## 7. INVALIDATION CASCADE

**Already STALE, unaffected:** INV-7/8/9 — STALE since F-010's Review 01, reaffirmed by every
subsequent review including this one's predecessor for a third independent reason ("the
utilities"). No new trigger.

**Newly STALE:** None. **Count: 0.**

## 8. RECORD

This file. See `findings.md` and `verdict.md` for the corresponding entries.

## 9. HANDOFF

**ACCEPTED-WITH-DEBT** (F-014 open, unchanged).

This was the last finding in this session's assigned queue (F-002, F-004, F-010, F-011, F-013 —
F-003 excluded per user instruction). All five now carry a Review 02 in addition to their
existing Review 01:
- F-010: was REJECTED-SCOPE → now **ACCEPTED-WITH-DEBT** (scope resolved by `2cfd836`, itself
  reviewed here for the first time).
- F-011, F-002, F-013, F-004: were already ACCEPTED/ACCEPTED-WITH-DEBT with zero drift; Review 02
  independently re-derived the same verdicts from fresh runs rather than carrying them forward.

**Blocking findings remaining toward GO:** unchanged by any of this session's reviews —
F-002+F-003 (condition 3, F-003's half postponed per ADR-0002, out of scope this session) and
F-006 (condition 4) per `verdict.md` §5. F-013/F-014 remain tracked non-blocking debt; F-005/F-009
non-blocking; F-012 non-blocking (dormant).

STOP. Not touching source.
