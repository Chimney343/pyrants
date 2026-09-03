# F-013 Review 02 — Second-Pass Adversarial Review of the Board-View Cache

Reviewer role: adversarial, read-only outside `docs/validation/`. Did not write the fix or the
prior review. Commissioned as a second independent pass over an already-`ACCEPTED-WITH-DEBT`
finding, at the user's explicit request (not because a new fix landed).

## 0. LOAD

- **Target finding:** F-013 — "Board projection regresses `private_view_json` cost 9.66×; cache
  mitigates, narrower C accessor still warranted." Class `ENGINE-OPENSPIEL`. Severity **MINOR**
  (performance).
- **Prior review:** `docs/validation/reviews/f013-review-01.md` (commit `16f8712`):
  **ACCEPTED-WITH-DEBT** (residual ~6.4× regression vs. pre-F-011 baseline; the ledger's "under
  the 2× gate" phrasing corrected to reflect the true, borrowed G4 definition is not met).
- **Commit range checked:** `16f8712` → `HEAD` (`74f2be31716712d5fb9385c2a524b8747dba3b9e`).
  `git diff 16f8712 HEAD --stat -- engine_c/bindings/c_adapter.py
  openspiel_pyrants/tests/test_board_view_cache.py docs/validation/harness/f013_timing.py` →
  **empty**. Zero drift.
- **Working tree:** clean except `.claude/CLAUDE.md`.
- **Pre-registered falsification test** (quoted verbatim, per Review 01's own note that F-013 is
  the one ledger entry without a stated "Expected if FALSE POSITIVE" clause — Hard Rule 7,
  append-only, not remedied here either):
  > Falsification test: `python -u docs/validation/harness/f011_timing.py` before/after, compare
  > mean wall-time.
  > Expected if REAL: mean wall-time ratio > 2×.
  Per Hard Rule 3, `f011_timing.py` (the originally-registered script) is used below, not
  `f013_timing.py`.

## 1. DIFF AUDIT

No new diff since Review 01 (§0). Re-read `c_adapter.py`'s cache logic directly at `HEAD` rather
than trusting Review 01's transcription: `_board_cache` in `__slots__`, zeroed in `__init__` and
in `apply()` immediately after `self._state = new_state`, and `_board_nodes_view()` populates it
once and returns `list(self._board_cache)` (a shallow copy) on every call thereafter.
Independently re-confirmed `grep -n "self\._state = " engine_c/bindings/c_adapter.py` still
returns exactly 3 matches (`__init__`, `apply`, `destroy`) — the same invalidation-surface count
Review 01 verified, unchanged. 0 out-of-scope hunks (nothing new to audit), 0 new test changes.

## 2. CONFORMANCE REVIEW

**Rulebook / Whitepaper:** `[absent]` — re-confirmed by re-reading `findings.md` F-013 directly;
this remains a pure internal-caching performance concern with no rules anchor, the same posture
Review 01 documented.

**What the code does at `HEAD`:** unchanged from `16f8712` (§0) — populate-once cache, invalidated
on the one production mutation site (`apply()`), fresh (`None`) on every independently-constructed
adapter.

**Verdict: CONFORMANT.** Behavioral parity holds — the cached branch returns the identical
six-field dict shape the pre-fix unconditional call produced; only *when* the call happens
changed. Independently re-verified by a fresh, self-written live repro in §4 (not reused from
Review 01's script, and not merely re-reading `test_board_view_cache.py`'s own assertions).

## 3. BLAST RADIUS (derived independently)

Re-derived rather than copied: **Included** — T1–T5 (direct target), F-011 (INV-4b is the fix
whose surface this cache wraps), INV-4a (a caching bug could in principle leak a previously-
computed board across a hidden-state-only difference if cache keys were ever shared — checked
live, not assumed), INV-5 (exercises many independent determinizations/clones, each needing a
correctly-fresh cache, at N=2,400 far beyond T4's N=2), F-010's `det_bot.py` B1 (node-keying
content must stay correct, not merely fast), F-002 (`f002b.py`, matching the fix plan's own
declared radius). Always-on: INV-1/2/3/6.

**Excluded, with reason:** F-001/F-003/F-005/F-006/F-007/F-008/F-009/F-012/F-014 (no shared code
path with `CEngineAdapter`'s cache slot); F-004 (`game_c.py`, disjoint file, and chronologically
this fix predates F-004's); INV-7/8/9 (STRENGTH rows, never re-measured per-fix); INV-10
(measures Python memory/tree-size, not `private_view_json` content).

**Comparison to Review 01's declared radius:** identical — Review 01 itself already found its
radius matched the fix plan's own gate table item-for-item; nothing has changed to widen or
narrow it since.

## 4. RE-RUN

All commands run fresh this session at `HEAD` (`74f2be31716712d5fb9385c2a524b8747dba3b9e`).

**a. Pre-registered falsification test**

| Check | Command | N / seeds | Prior (Review 01) | New (this review) |
|---|---|---|---|---|
| Mean wall-time, `num_sims=200`, fixed root (seed 42, 40-step `RandomBot(131)`, per-search bot seeds 1000+i) | `harness/f011_timing.py` | N=10 searches | `1.0569s` (ratio 6.42× vs. pre-F-011 `0.1646s`) | **`1.1311s`** (ratio **6.87×**) |

✅ Still matches "Expected if REAL": `6.87× > 2×`. The wall-time number itself is a noisy
benchmark (machine-load-dependent, not seed-dependent — the search logic is deterministic per
F-010, only its wall-clock cost varies run to run); the two independent measurements (6.42×,
6.87×) bracket the same regime Review 01 already characterized as "reduced from 9.66× but not
eliminated," not a new or different finding.

**b. Blast-radius checks**

| Check | Command | N | Prior | New |
|---|---|---|---|---|
| T1–T5 | `pytest openspiel_pyrants/tests/test_board_view_cache.py -v` | 5 | 5/5 | **5/5 PASS** |
| INV-4b (F-011) | `harness/inv_b2.py` | 403 | 403/403 differ | **403/403 differ** |
| INV-4a | `harness/inv_b.py` | 300 | 0 violations | **0 violations** |
| INV-5 | `harness/inv_b.py` | 2400 | mean 11.11/12, conservation 0/2400 | **mean 11.11/12, min 7, max 12, singletons 0, conservation 0/2400** |
| F-010 `det_bot.py` B1 | `harness/det_bot.py` | 10 | 1 distinct | **1 distinct, `[8]`** |
| F-002 `f002b.py` | `harness/f002b.py` | 3 | 3/3+3/3+3/3 | **3/3+3/3+3/3 unchanged** |

**Live re-verification of G2 (cache invalidates on `apply()`), independently written this
session** (not Review 01's script, not `test_board_view_cache.py`'s own helper — a fresh
standalone repro against `docs/validation/harness/common.py`'s public `load`/`fresh` helpers):

```
pre-move board hash: 7373222101513497340
applying move id 0 -> initial_placement(target_node_id='site_blingdenfire')
post-move board hash: -1078916386420777373
board changed: True
G2 LIVE REPRO (Review 02, independent): PASS
```
Also independently confirmed `adapter._board_cache is not None` after the warming call and
`adapter._board_cache is None` immediately after `apply()`, matching T3's own assertion but
verified by a script this review wrote itself rather than trusting T3's pass.

**c. Always-on**

| Check | N | Prior | New |
|---|---|---|---|
| INV-1 | 100 | PASS | **PASS, 0/100** |
| INV-2 | 235 | PASS | **PASS, N=235** |
| INV-3 | 1200 | PASS | **PASS, empty=0 dup=0 oor=0** |
| INV-6 | 30 | PASS | **PASS, bad=0** |

**d. Previously-CONFIRMED findings inside the radius**

| Finding | Prior status | Re-run result |
|---|---|---|
| F-011 | ACCEPTED-WITH-DEBT (this session) | INV-4b unchanged (§4b) |
| F-010 | ACCEPTED-WITH-DEBT (this session) | `det_bot.py` B1 unchanged |
| F-002 | ACCEPTED (this session) | `f002b.py` unchanged |

**e. Regression sweep**

| Command | N | Result |
|---|---|---|
| `pytest openspiel_pyrants/tests/ -q` | 88 collected | **78 passed, 10 failed** — all 10 the F-003 Part B RED-test suite, postponed, unrelated to `c_adapter.py` |
| `pytest -q` (repo root) | full suite | same **3 pre-existing failures**, 1 skip |
| `just test-c` | full C suite | exit 0, 0 FAIL |

**No regression found. No invariant reversed. No previously-CONFIRMED finding disturbed.**

## 5. NEW FINDINGS

None.

## 6. VERDICT

**ACCEPTED-WITH-DEBT** — unchanged from Review 01: (1) the residual regression persists
(re-measured at 6.87× this session vs. 6.42× at Review 01 — both still well above the 2× "Expected
if REAL" threshold, run-to-run wall-clock variance, not a code change), the narrower C-level
`engine_build_board_view`-only accessor remains required before any large-scale throughput claim;
(2) the ledger's "1.66× ... under the 2× gate" phrasing (`findings.md`/`verdict.md`) still needs
to be read alongside the true ~6.4-6.9× figure disclosed in the same sentence — Review 01's
correction stands, not re-litigated here per Hard Rule 7.

## 7. INVALIDATION CASCADE

**Already STALE, unaffected:** INV-7/8/9 — STALE since F-010's Review 01, reaffirmed since. No
new trigger.

**Newly STALE:** None. **Count: 0.**

## 8. RECORD

This file. See `findings.md` and `verdict.md` for the corresponding entries.

## 9. HANDOFF

**ACCEPTED-WITH-DEBT.** Debt unchanged: narrower C-level board-only accessor remains required
before any throughput claim.

**Next in this session's queue:** F-004 Review 02 (last item; F-003 excluded per user
instruction).

STOP. Not touching source.
