# F-013 Review 03 — Part B: the board projection is cheap now, not just cached

Reviewer role: adversarial, read-only outside `docs/validation/`. Did not write the Part B fix or
the Phase 7 record edits. Commissioned as the mandatory review pass over
`docs/validation/f013-part-b-fix-plan.md` (Phases 1-6) that fixes the residual F-013 debt Review
01/02 left open.

## 0. LOAD

- **Target finding:** F-013 — "Board projection regresses `private_view_json` cost 9.66×; Part A
  cache + Part B cheap pure-Python projection close the residual." Class `ENGINE-OPENSPIEL`.
  Severity **MINOR** (performance, non-blocking for 2-player work; blocking for any large-scale
  ISMCTS throughput claim until closed).
- **Prior reviews:** Review 01 (`16f8712`) **ACCEPTED-WITH-DEBT** and Review 02
  (`74f2be31`) **ACCEPTED-WITH-DEBT** — both held the residual ~6.4-6.9× regression open and both
  named the narrower C-level `engine_build_board_view` accessor as the required follow-up.
- **Fix under review:** `docs/validation/f013-part-b-fix-plan.md` — five commits:
  `fddfe8c` (Phase 0 baselines + corpus + frozen reference vectors), `87af42d` (Phase 1 RED
  tests), `1564bdd` (Phase 2 / L3 cheap projection + sym memo + static hoisting),
  `13c3fe4` (Phase 3 / L1 per-player string cache), `f9157a4` (Phase 4 / L2 clone-determinize
  propagation), `0b68248` (Phase 6 post baselines).
- **Falsification test carried forward:** `f013_timing.py` mean wall-time vs. the pre-F-011
  `0.1646 s` baseline. "Expected if REAL" was `> 2×`; this review checks whether Part B gets the
  measured ratio **under 2×** (the plan's honest gate, § 8) without moving any invariant.

## 1. DIFF AUDIT (G0)

`git diff 675c4db..HEAD --stat` touches only:

- `engine_c/bindings/c_adapter.py`, `engine_c/bindings/view.py`,
  `engine_c/bindings/engine_bindings.py`, `engine_c/bindings/test_label_enrich.py`
- `openspiel_pyrants/tests/test_board_view_cache.py` (edited),
  `openspiel_pyrants/tests/test_board_projection.py` (new),
  `openspiel_pyrants/tests/_f013b_corpus.py` (new)
- `docs/validation/harness/f013b_census.py`, `f013b_gen_vectors.py` (new)
- `docs/validation/baseline/f013b_*.{pre,post}.txt` + `f013b_view_vectors.jsonl` (new)
- `docs/validation/*`

**Zero** diff in `openspiel_pyrants/*.py` (non-test), `scripts/`, `engine_c/*.c`, `.venv/`.
Re-verified `grep -n "self\._state = " engine_c/bindings/c_adapter.py` still returns exactly 3
sites (`__init__`, `apply`, `destroy`), so the F-013 T5 structural trip-wire and the
single-invalidation-site assumption both still hold. 0 out-of-scope hunks.

Read the production diff in full rather than trusting the plan: the new `_project_board_nodes`
preserves the `spies` sort-and-filter and the unfiltered `troop_slots` semantics exactly; the
`_board_static` hoist reads `state->definition->board` fields; `_view_cache` is keyed per player
and cleared on `apply()` **and** `destroy()`; `_inherit_projection` shares by reference, safe
because `_board_nodes_view()` returns a deep copy and projections are only ever replaced whole,
never mutated in place. The G1 trap the plan called out (a rewrite that sorts the wrong list, or
filters `troop_slots`) is not present: T1/T2 hold over the whole corpus including 130 spy states.

## 2. CONFORMANCE REVIEW

**Rulebook / Whitepaper:** `[absent]` — unchanged posture; pure engine-binding performance
concern with no rules anchor.

**What the code does at `HEAD`:** `private_view_json(pid)` is now: (1) a per-player string-cache
hit, else (2) build the Tier-1 public dict + project the board through `_project_board_nodes`
(a direct `CGameView` read into the six output fields, using the memoised `sym_str` and the
hoisted `_board_static`) + `json.dumps`, cached per player. Clones/determinizations inherit the
parent's projection; `apply()` and `destroy()` invalidate both caches; `_board_static` survives
`apply()`.

**Verdict: CONFORMANT** — byte-identical output for byte-identical input, verified across the
whole 302-state corpus (G1, T1), not just a spot sample.

## 3. BLAST RADIUS

**Included:** T1-T12 (direct target), F-011 (INV-4a/4b/5 — the observation fix whose surface
this code wraps), F-010 (`det_bot.py` B1 — node-keying content must stay correct, not merely
fast), F-002 (`f002b.py`), always-on INV-1/2/3/6. The corpus itself covers board-static
hoisting (T5), sym-memo invalidation (T6, in a subprocess — an in-process `intern_destroy` would
corrupt the shared C intern table), determinize board-invariance (T9/T10, the invariant L2's
propagation rests on), and aliasing (T12).

**Excluded, with reason:** F-001/F-003/F-005/F-006/F-007/F-008/F-009/F-012/F-014/F-015 (no
shared code path with `c_adapter.py`'s view caches); INV-7/8/9 (STRENGTH rows, never re-measured
per-fix); INV-10 (measures tree/memory, not view content).

## 4. RE-RUN (all fresh, at the Part B code tip)

**a. Pre-registered falsification test / G5**

| Check | Command | Prior (Review 02) | New (post-Part B) |
|---|---|---|---|
| Mean wall-time, `num_sims=200`, fixed root | `harness/f013_timing.py` | 1.1311 s (**6.87×**) | `f013b_timing.pre` 0.7144 s → `f013b_timing.post` **0.2643 s** = **1.61× vs 0.1646 s** |

✅ Under the plan's honest 2× gate — better than the plan's own § 8 projection (3.0-3.9×),
because the freshly re-captured pre-fix baseline (0.7144 s) is already well below Part A's
1.0500 s (the tree moved since Part A: F-014 and other work landed).

**b. Census (G3 / G4)**

| Metric | Pre-Part B | Post |
|---|---|---|
| Cold projection (`board_nodes_view_cold`) | 443.5 µs | **107.3 µs** (≤120 ✓) |
| Board projections per search | 876 (gen0 201) | **676** (gen0 1, ≤700 ✓) |
| Repeat reads served w/o re-serialization | 0 | **1076** ✓ |
| `json.dumps` per search | 1952 | **876** |

**c. G1 / G2 / G3 controls**

- T1 byte-identity vs frozen Phase-0 vectors: **PASS** (302 states / 918 vectors, incl. 130 spy
  states and 302 full-slot states).
- T2 fast projection == `build_c_board_view` six fields over the whole corpus: **PASS**.
- T4 exactly one `engine_build_view` + zero `build_c_board_view` on cold `_board_nodes_view()`:
  **PASS**.
- T5 board-static fields survive 60 applies: **PASS**. T8 destroyed adapter never serves a
  cached string: **PASS** (raises `AttributeError`/`RuntimeError` as pre-fix). T9 determinize
  board-invariance over 10 roots × 50 seeds: **PASS**. T10 structural trip-wire on
  `engine_determinize`: **PASS**. T12 inherited projection not aliased: **PASS**.

**d. G6 invariants — environment-drift check**

Recorded values drifted from the historical ledger (INV-5 mean 11.48 min 8 vs. recorded 11.11
min 7; inv_b sample 776 vs 618). Because the same DLL is used throughout, this could only be
caused by this fix if the view-cache code changed determinize outcomes — so this review ran the
invariant battery on a **pre-change temp worktree** (`87af42d`, same engine DLL) and compared:

| Check | Pre-change (same env) | Post-Part B |
|---|---|---|
| INV-1 | PASS | PASS (0 violations) |
| INV-4a | 0/300 | 0/300 |
| INV-4b | 776 unique/776 | 776 unique/776, 0 same-key-different-board |
| INV-4b-2 | 62 changed / 0 unchanged | 62 changed / 0 unchanged |
| INV-5 | mean 11.48, min 8, cons 0/2400 | mean 11.48, min 8, cons 0/2400 |
| F-010 `det_bot.py` B1 | 1 distinct | 1 distinct |
| F-002 `f002b.py` | 8/8 controls | 8/8 controls |

Identical. The drift from the ledger's 11.11/7 record is **not this fix**.

**e. Regression sweep (G7)**

| Command | Result |
|---|---|
| `pytest openspiel_pyrants/tests/` | only the 10 pre-existing postponed F-003 Part B RED failures (all in `test_chance_nodes.py`); all F-013B tests green. Note: in this environment the F-003 chance-node tests also drop pytest's final counts line at process teardown — reproduced identically on a pre-change worktree (`87af42d`), pre-existing, not caused by this fix |
| `pytest -q` (repo root, `tests/`) | same 3 pre-existing failures (Zuggtmoy, Air Elemental, Neogi), nothing new |
| `just test-c` | exit 0, all C suites PASS |

**No regression found. No invariant reversed. No previously-CONFIRMED finding disturbed.**

## 5. NEW FINDINGS

None. (The withdrawn C-accessor recommendation is a record correction, not a finding: measured
at 3.1 µs of ~400 µs, a C-level accessor could save at most 0.8% of the cost it was proposed to
remove — see `f013-part-b-fix-plan.md` § 9.)

## 6. VERDICT

**ACCEPTED.** F-013 is closed as **CONFIRMED — FIXED**: the measured post-fix ratio is 1.61× vs
the pre-F-011 baseline, under the plan's own honest 2× gate and far under the `> 2×` "Expected if
REAL" falsification threshold. All six gates (G0-G6) clear on freshly re-captured numbers, and G6
was verified against a pre-change run in the same environment rather than against stale ledger
records.

## 7. INVALIDATION CASCADE

**Already STALE, unaffected:** INV-7/8/9. **Newly STALE:** None. **Count: 0.**

## 8. RECORD

This file, plus `findings.md` F-013 (Status → CONFIRMED — FIXED) and `verdict.md` F-013 entry,
both updated in this phase. `MEMORY.md` / `ismcts-performance-levers` (named by plan § 7.4) does
not exist anywhere in this repo or its git history; the record correction that item was meant to
carry now lives in `verdict.md`'s F-013 "Audit correction" block instead.

## 9. HANDOFF

**ACCEPTED.** F-013 closed. Debt retired: the narrower C-level board-only accessor is withdrawn
with measured justification.

STOP. Not touching source outside the Phase 7 doc set.
