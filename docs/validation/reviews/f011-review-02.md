# F-011 Review 02 — Second-Pass Adversarial Review of the Board-Observation Fix

Reviewer role: adversarial, read-only outside `docs/validation/`. Did not write the fix or the
prior review. Commissioned as a second independent pass over an already-`ACCEPTED-WITH-DEBT`
finding, at the user's explicit request (not because a new fix landed).

## 0. LOAD

- **Target finding:** F-011 — "Board state is absent from the information state and the
  observation." Class `ENGINE-OPENSPIEL`. Severity **CRITICAL**.
- **Prior review:** `docs/validation/reviews/f011-review-01.md` (commit `a7cee83`):
  **ACCEPTED-WITH-DEBT** (F-013 open, throughput regression).
- **Commit range checked:** `a7cee83` → `HEAD` (`74f2be31716712d5fb9385c2a524b8747dba3b9e`).
  `git diff a7cee83 HEAD --stat -- engine_c/bindings/c_adapter.py engine_c/bindings/view.py
  openspiel_pyrants/state_c.py openspiel_pyrants/tests/test_observation_completeness.py`
  is **not** empty — unlike F-010's re-review, real drift exists here: `c_adapter.py` gained 26
  insertions / 15 deletions. Read in full (not summarized): this is entirely commit `16f8712`
  ("perf: cache board projection on `CEngineAdapter`") — F-011's own downstream finding, F-013,
  already independently reviewed and `ACCEPTED-WITH-DEBT` in `docs/validation/reviews/
  f013-review-01.md`. The diff adds a `_board_cache` slot, zeroes it in `__init__`/`apply()`, and
  wraps `_board_nodes_view()`'s body in a populate-once/return-a-copy cache — the **six-key
  projection dict itself is byte-identical** (`node_id`, `troop_slots`, `spies`, `control_vp`,
  `total_control_vp_per_turn`, `vp_tokens`), only *when* it is built changed, not what it
  contains. This review treats F-013's fix as in-radius (§3) rather than as unreviewed drift,
  since it already has its own independent Review 01 and is itself being re-reviewed in this same
  session.
- **Working tree:** clean except `.claude/CLAUDE.md` (unrelated, confirmed via `git status`).
- **Pre-registered falsification test** (quoted verbatim from `findings.md` F-011, unchanged):
  > Falsification test: construct state pairs that differ only in a public board fact — same
  > move type applied to a different site, so barracks/resource bookkeeping is identical —
  > verify the boards genuinely differ, then compare `private_view_json(p)`.
  > Expected if REAL: boards differ while the observation is byte-identical.
  > Expected if FALSE POSITIVE: the observation differs whenever the board differs.

## 1. DIFF AUDIT

**F-011's own fix (`2cfd836..a7cee83`):** re-read in full at `HEAD`, independently against
`f011-review-01.md`'s own hunk table rather than trusting it. Confirmed unchanged: `a7cee83`
touches exactly `engine_c/bindings/c_adapter.py` (production), `openspiel_pyrants/tests/
test_observation_completeness.py` (new, 8 tests), and the plan/harness/ledger doc set. No new
classification needed — Review 01's table (IMPLEMENTS-FINDING × 1, TEST-CHANGE × 1, DOC-CHANGE ×
rest, 0 OUT-OF-SCOPE) is independently re-derivable from the same diff and matches.

**Drift since Review 01 (`a7cee83..HEAD`), audited fresh:** the only touch to F-011's own
function is `16f8712` (F-013), classified `IMPLEMENTS-FINDING` for F-013, not F-011 — it is a
caching wrapper around `_board_nodes_view()`, not a change to what board fields are exposed.
Independently confirmed the six projected keys are unchanged by diffing the dict-literal body
(`node_id`/`troop_slots`/`spies`/`control_vp`/`total_control_vp_per_turn`/`vp_tokens` — same six,
same order, same source fields from `build_c_board_view`). No other file in F-011's original diff
(`state_c.py`, `test_observation_completeness.py`, `view.py`) shows any drift (`git diff a7cee83
HEAD --stat` for those three paths: empty).

**Gaming checklist:** no TEST-CHANGE hunk exists in the `a7cee83..HEAD` range for F-011's own
files — `test_observation_completeness.py` is untouched. N/A, not silently skipped.

**Verdict of this step:** 0 out-of-scope hunks in F-011's own fix (re-confirmed). The one file
that drifted since (`c_adapter.py`) did so entirely inside F-013's own, separately-authorized and
separately-reviewed scope — not an unreviewed change to F-011's conformance surface.

## 2. CONFORMANCE REVIEW

**Rulebook** (`docs/tyrants-rulebook.md` § Final Scoring, ≤15 words, re-quoted from the finding):
> "The player with the most VP at the end of the game wins" [site/troop VP sources implied]

**Whitepaper:** `[absent]` — re-confirmed, same posture as F-010.

**What the code does at `HEAD`** (re-read directly, not carried over from Review 01):
- `engine_c/bindings/c_adapter.py:200-224` (`private_view_json`) — merges `board_nodes` and
  `discard` into the public dict, unchanged since `a7cee83`.
- `engine_c/bindings/c_adapter.py:~236-258` (`_board_nodes_view`, now cached by F-013) — same six
  per-node fields, now built once per adapter lifetime instead of once per call; the *content*
  contract is unchanged, independently confirmed by direct comparison of the dict-comprehension
  body against `a7cee83`'s version (§1).
- `_build_public_dict` — re-checked, still byte-unchanged since `a7cee83` (`git diff a7cee83 HEAD`
  shows zero hunks in that function's line range, consistent with F-013's plan explicitly
  forbidding Tier-1 path changes).

**Verdict: CONFORMANT.** Unchanged from Review 01, independently re-verified by fresh execution
in §4, and the one code change in the interim (F-013's cache) does not alter the projected
content, only its construction timing.

## 3. BLAST RADIUS (derived independently)

**Included:**
- **INV-4b (completeness)** — direct target.
- **INV-4a (leakage)** — G2 anti-overfix trap, must be re-asserted with a live run.
- **INV-5 (determinization consistency + conservation)** — reads `private_view_json` content for
  its fingerprint and conservation check.
- **F-013 (caching, `16f8712`)** — now directly inside the changed-symbol chain (§0); a caching
  bug could plausibly serve a stale board across genuinely different states, which INV-4b (its
  own falsification test) and INV-4a would be the first checks to catch. Included as a new
  addition to this review's radius versus Review 01's (which predates F-013's existence).
- **F-010 (node-keying substrate)** — `information_state_string` content depends on
  `private_view_json`, unchanged reasoning from Review 01.
- **F-007 (own-discard resolution)** — this fix is F-007's own promised remedy; opponent-discard
  must stay hidden.
- **Always-on (Hard Rule 4c):** INV-1, INV-2, INV-3, INV-6.

**Excluded, with reason:** F-002 (different code path, `engine_c/state.c`), F-001 (reads
`legal_moves()` order, not observation content), F-003/F-004/F-008/F-009 (chance-node/returns
logic, disjoint from `c_adapter.py`), INV-7/8/9 (STRENGTH rows, never re-measured per-fix, §7),
INV-10 (memory/tree-size, no plausible interaction) — all identical reasoning to Review 01,
independently re-derived rather than copied.

**Comparison to Review 01's declared radius:** identical except for the addition of F-013, which
did not exist as a landed fix at Review 01's time. Not narrower anywhere.

## 4. RE-RUN

All commands run from repo root, `.venv/Scripts/python.exe -u <path>`, fresh this session at
`HEAD` (`74f2be31716712d5fb9385c2a524b8747dba3b9e`).

**a. Pre-registered falsification test**

| Check | Command | N / seeds | Prior (Review 01, `a7cee83`) | New (this review, `HEAD`) |
|---|---|---|---|---|
| Board-differing pairs vs. `private_view_json` | `docs/validation/harness/inv_b2.py` | N=403, seeds 1–139 | 403/403 differs, 0 identical | **403/403 differs, 0 identical** — exact match |

✅ PASS, unchanged.

**b. Blast-radius invariants**

| Check | Command | N | Prior | New |
|---|---|---|---|---|
| INV-4a leakage | `harness/inv_b.py` | 300 | 0 violations | **0 violations** |
| INV-5 world diversity | `harness/inv_b.py` | 2400 | mean 11.11/12, min 7, singletons 0 | **mean 11.11/12, min 7, max 12, singletons 0** — exact match |
| INV-5 conservation | `harness/inv_b.py` | 2400 | 0 violations | **0/2400 violations, 0/2400 history mismatches** |
| INV4b-2 board-mutating moves | `harness/inv_b.py` | 65 | 0/65 silent misses | **N=65, board changed & view unchanged=0, changed=65** |
| F-013 cache correctness (in-radius, new) | `pytest openspiel_pyrants/tests/test_board_view_cache.py -v` | 5 tests | 5/5 PASS (`f013-review-01.md`) | **5/5 PASS** |
| F-010 `det_bot.py` B1 | `harness/det_bot.py` | 10, seed 4242 | 1 distinct chosen action | **1 distinct chosen action, `[8]`** |

**c. Always-on**

| Check | N | Prior | New |
|---|---|---|---|
| INV-1 | 100 | PASS | **PASS, 0/100** |
| INV-2 | 235 | PASS | **PASS, N=235** |
| INV-3 | 1200 | PASS | **PASS, empty=0 dup=0 oor=0** |
| INV-6 | 30 | PASS | **PASS, N=30, bad=0** |

**d. Previously-CONFIRMED findings inside the radius**

| Finding | Prior status | Re-run result |
|---|---|---|
| F-010 | ACCEPTED-WITH-DEBT (this session's Review 02) | `det_bot.py` B1 unchanged (§4b) |
| F-013 | ACCEPTED-WITH-DEBT (`f013-review-01.md`) | Own 5-test suite 5/5 (§4b); G2 live-cache-invalidation behavior implicitly re-exercised by INV-5's 2,400 independent determinizations/clones all passing conservation |

**e. Regression sweep**

| Command | N | Result |
|---|---|---|
| `pytest openspiel_pyrants/tests/test_observation_completeness.py -v` | 8 tests | **8/8 PASS**, including `test_tier1_snapshot_shape_and_cost_unaffected` (G4) |
| `pytest openspiel_pyrants/tests/ -q` | 88 collected | **78 passed, 10 failed** — all 10 are the F-003 Part B RED-test suite (`test_chance_nodes.py`, postponed per ADR-0002), unrelated to `c_adapter.py` |
| `pytest -q` (repo root) | full suite | **3 pre-existing failures** (Zuggtmoy, Air Elemental, Neogi), 1 skip, identical to every prior review in this ledger |
| `just test-c` | full C suite | exit 0, 0 "FAIL" occurrences |

**G5 (search-time budget), re-measured for completeness (not F-011's own gate — F-013's):**
`f011_timing.py` mean_wall = **1.1311s** this session, vs. the pre-F-011 baseline `0.1646s` →
ratio **6.87×**. This is lower than Review 01's originally-measured 9.655× because F-013's cache
(landed after F-011's Review 01) mitigates it — consistent with, not a new finding beyond, F-013's
own already-recorded `ACCEPTED-WITH-DEBT` status (residual regression tracked there, not here).

**No regression found. No invariant reversed. No previously-CONFIRMED finding disturbed.**

## 5. NEW FINDINGS

None. The one piece of drift found (F-013's cache) is already a tracked, independently-reviewed
finding, not new.

Count: **0 new findings.**

## 6. VERDICT

**ACCEPTED-WITH-DEBT** — F-013 remains open (throughput regression, now mitigated to ~6.4-6.9×
residual per its own review, tracked there). All Hard Rule 8 components hold: test PASS (§4a),
CONFORMANT (§2), zero regressions (§4), zero out-of-scope hunks (§1). Unchanged verdict from
Review 01; independently re-derived rather than carried forward.

## 7. INVALIDATION CASCADE

**Already STALE, unaffected:** INV-7/8/9 — STALE since F-010's Review 01, reaffirmed by every
subsequent review including this one's own predecessor. This review's re-runs are all
structural/correctness checks (§4), not STRENGTH rows, so no new trigger beyond what's already
marked.

**Newly STALE:** None.

**Count: 0 newly-STALE rows.**

## 8. RECORD

This file. See `findings.md` and `verdict.md` for the corresponding entries.

## 9. HANDOFF

**ACCEPTED-WITH-DEBT** (F-013 open, unchanged). No action required on F-011 itself.

**Next in this session's queue:** F-002 Review 02, then F-013 Review 02, then F-004 Review 02
(F-003 excluded per user instruction).

STOP. Not touching source.
