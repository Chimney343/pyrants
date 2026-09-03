# F-002 Review 02 — Second-Pass Adversarial Review of the Shuffle-Stream Reroll

Reviewer role: adversarial, read-only outside `docs/validation/`. Did not write the fix or the
prior review. Commissioned as a second independent pass over an already-`ACCEPTED` finding, at
the user's explicit request (not because a new fix landed).

## 0. LOAD

- **Target finding:** F-002 — "`engine_determinize` never rerolls `shuffle_seed`/
  `shuffle_counter`, so post-determinization chance events collapse across worlds." Class
  `OPENSPIEL-ISMCTS`. Severity **CRITICAL**.
- **Prior review:** `docs/validation/reviews/f002-review-01.md` (commit `e9a2702`): **ACCEPTED**,
  no debt.
- **Commit range checked:** `e9a2702` → `HEAD` (`74f2be31716712d5fb9385c2a524b8747dba3b9e`).
  `git diff e9a2702 HEAD --stat -- engine_c/state.c engine_c/test_engine.c
  openspiel_pyrants/tests/test_determinize_reshuffle_independence.py` → **empty**. Zero drift on
  every file F-002's fix touches. (Review 01 itself already checked this same range at its own
  time, `d26a920`; this review re-checks at the current, later `HEAD` independently rather than
  trusting that check still holds.)
- **Working tree:** clean except `.claude/CLAUDE.md` (unrelated).
- **Pre-registered falsification test** (quoted verbatim from `findings.md` F-002, unchanged):
  > From one information-state root, produce two adapters via
  > `CEngineAdapter.determinize(player_id, seed1)` and `determinize(player_id, seed2)`,
  > seed1≠seed2. Confirm both report identical `shuffle_seed`/`shuffle_counter` (they must, since
  > `engine_determinize` never writes them). Drive each to the same `shuffle_counter` value via a
  > reshuffle-triggering draw and record the **relative permutation** `rng_shuffle` applies.
  > Expected if REAL: identical permutation indices between the two worlds.
  > Expected if FALSE POSITIVE: permutation indices differ.
  Post-fix, per Review 01's own note, the finding's operative post-fix gates are GA1/GA3 from
  `f002-f003-fix-plan.md` § 3, re-run below.

## 1. DIFF AUDIT

No new diff exists for F-002's own production/test files since Review 01 (§0). Re-read
`e9a2702`'s single production hunk directly at `HEAD` rather than trusting Review 01's quoted
text:

```c
// engine_c/state.c:308-316 (current HEAD, byte-identical to e9a2702)
clone->shuffle_seed = rng_next(&rng);
clone->shuffle_counter = 0;
```

Confirmed placement: still the last consumer of `rng` in `engine_determinize`, after the
opponent-zone reshuffle loop and the market-deck block, both independently re-diffed as
byte-identical to pre-fix (`git diff b0f3173 HEAD -- engine_c/state.c` shows exactly this one
hunk, nothing else — same result Review 01 got at `d26a920`, reproduced fresh at the later
`HEAD`). 0 out-of-scope hunks, 0 test changes since Review 01 — nothing to run the gaming
checklist against beyond what Review 01 already cleared (re-confirmed by inspection: both test
files identical byte-for-byte).

## 2. CONFORMANCE REVIEW

**Rulebook** (`docs/tyrants-rulebook.md` § Draw a Card, line 328, ≤15 words):
> "shuffle your discard pile to re-form your deck" [the reshuffle is a real, rule-governed event]

**Whitepaper** (`docs/ismcts-paper.md` § III-C-2, ≤15 words):
> "chance nodes do occur under certain circumstances ... they cannot be ignored completely"

**What the code does at `HEAD`:** identical to Review 01's finding (§1) — the reroll is placed
after every prior `rng` draw, so `clone->shuffle_seed` is a deterministic function of `seed`
(preserving F-010's reproducibility) while differing across determinize seeds (restoring the
paper's determinization premise). No rulebook site's behavior changes; only which hidden stream
a sampled world consults changes.

**Verdict: CONFORMANT.** Unchanged from Review 01, independently re-verified by fresh execution
in §4.

## 3. BLAST RADIUS (derived independently)

Re-derived rather than copied, checking specifically whether anything has entered the radius
since Review 01 (F-013's cache landed before Review 01 and was already included there; nothing
newer touches `engine_determinize`'s callers):

**Included:** GA1/GA3 (direct target), INV-1 (replay determinism — reroll must not break
seed-pair replay), INV-2 (clone independence), INV-4a/4b + INV-5 (world diversity/conservation —
the fix changes world diversity by design, and conservation would catch a corrupted reroll),
F-010's `det_bot.py` B1 (reroll must draw from the seeded stream, not defeat same-seed
reproducibility), F-002's own market-deck control (T-A5/`f002b.py`), F-013's board-cache suite
(transitively, via the full OpenSpiel run). Always-on: INV-1/2/3/6.

**Excluded, with reason:** F-003/Part B (chance-node exposure untouched, `state_c.py` has zero
diff in the fix's range), F-004/F-011/F-013 (the reroll writes two scalars on a fresh clone; it
cannot change returns, observation content, or adapter caching — F-011's INV-4 battery is re-run
anyway as always-on collateral), F-001/F-005/F-006/F-009/F-014 (no mechanism connects a
determinize-time scalar reroll to action-ID stability, seating, UCT calibration, chance-outcome
limits, or insane-outcast minting).

**Comparison to Review 01's declared radius:** identical. No new code has entered F-002's
downstream call graph since.

## 4. RE-RUN

All commands run fresh this session at `HEAD` (`74f2be31716712d5fb9385c2a524b8747dba3b9e`).

**a. Pre-registered falsification test, post-fix form (GA1/GA3)**

| Check | Command | N / seeds | Prior (Review 01) | New (this review) |
|---|---|---|---|---|
| GA1: pairs preserving root `(shuffle_seed, shuffle_counter)` | `harness/f002_reroll.py` | N=100 pairs, determinize seeds `RandomState(101)`/`(202)` | 0/100 | **0/100** |
| GA3: first-reshuffle deck order across determinize seeds | same script | 3 pairs (seeds 3/31/37) | 3/3 changed | **3/3 changed** |

✅ Both gates met, exact match.

**b. Blast-radius checks**

| Check | Command | N | Prior | New |
|---|---|---|---|---|
| GA2 same-seed reproducibility (C) | `engine_c/test_engine.c::test_determinize_shuffle_stream_deterministic_per_seed` (`just test-c`) | seed 1111 | PASS | **PASS** — `"PASS: determinize shuffle stream deterministic per seed"` |
| T-A3/T-A4/T-A5 | `pytest openspiel_pyrants/tests/test_determinize_reshuffle_independence.py -v` | 3 | 3/3 | **3/3, 0 skipped** |
| F-002 permutation control | `harness/f002b.py` | 3 controlled reshuffles | 3/3+3/3+3/3 | **3/3+3/3+3/3 — unchanged** |
| F-010 `det_bot.py` B1 | `harness/det_bot.py` | 10, seed 4242 | 1 distinct | **1 distinct, `[8]`** |

**c. Always-on**

| Check | N | Prior | New |
|---|---|---|---|
| INV-1 | 100 | PASS | **PASS, 0/100** |
| INV-2 | 235 | PASS | **PASS, N=235** |
| INV-3 | 1200 | PASS | **PASS, empty=0 dup=0 oor=0** |
| INV-6 | 30 | PASS | **PASS, bad=0** |
| INV-4a | 300 | 0 violations | **0 violations** |
| INV-4b (key-collision form) | 618 states | 618 unique, 0 collisions | **618 unique, 0 collisions** |
| INV-5 | 2400 | mean 11.11/12, conservation 0/2400 | **mean 11.11/12, min 7, max 12, singletons 0, conservation 0/2400** |

**d. Previously-CONFIRMED findings inside the radius**

| Finding | Prior status | Re-run result |
|---|---|---|
| F-010 | ACCEPTED-WITH-DEBT (this session) | `det_bot.py` B1 unchanged |
| F-011 | ACCEPTED-WITH-DEBT (this session) | INV-4a/4b/5 exact-match |
| F-013 | ACCEPTED-WITH-DEBT (own review pending in this session) | `test_board_view_cache.py` 5/5 within combined suite run; `c_adapter.py` unrelated to F-002's diff |

**e. Regression sweep**

| Command | N | Result |
|---|---|---|
| `just test-c` | full C suite | **exit 0, 0 FAIL**, incl. both F-002 C tests: `"PASS: determinize rerolls shuffle stream"`, `"PASS: determinize shuffle stream deterministic per seed"` |
| `pytest openspiel_pyrants/tests/ -q` | 88 collected | **78 passed, 10 failed** — all 10 are the F-003 Part B RED-test suite, postponed per ADR-0002, unrelated to `engine_c/state.c` |
| `pytest -q` (repo root) | full suite | same **3 pre-existing failures** (Zuggtmoy, Air Elemental, Neogi), 1 skip |

**No regression found. No invariant reversed. No previously-CONFIRMED finding disturbed.**

## 5. NEW FINDINGS

None.

## 6. VERDICT

**ACCEPTED.** No debt. Every Hard Rule 8 component holds: GA1/GA3 re-run fresh and met (§4a),
CONFORMANT (§2), zero regressions (§4), zero out-of-scope hunks (§1). Unchanged from Review 01,
independently re-derived.

## 7. INVALIDATION CASCADE

**Already STALE, unaffected:** INV-7/8/9 — STALE since F-010's Review 01, reaffirmed by every
subsequent review. No new trigger from this review (nothing in the radius changed since Review
01, which already applied the "fifth independent trigger" reasoning for this same fix).

**Newly STALE:** None. **Count: 0.**

## 8. RECORD

This file. See `findings.md` and `verdict.md` for the corresponding entries.

## 9. HANDOFF

**ACCEPTED.** F-002 remains closed; condition 3a stays struck. Condition 3b (F-003) remains open
and out of scope for this session per user instruction.

**Next in this session's queue:** F-013 Review 02, then F-004 Review 02.

STOP. Not touching source.
