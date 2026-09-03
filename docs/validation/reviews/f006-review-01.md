# F-006 — Review 01 (adversarial)

**Date:** 2026-09-03
**Finding:** F-006 — *Default `uct_c=1.4` diverges from the paper's calibrated `0.7`*
**Class:** PAPER-CODE · **Severity:** MAJOR
**Base:** `0266851c835bcfd126032a9ccb9533e30c94d69a`
**Fix range:** `25c600b896e8131bcc00329fd2d1869435e6fba3` (evidence) + `ca6499139619e32a6baf5511f5962fc108318457` (code)
**Review head:** `c6a7ee84684475489e03f991565c67109186c0a2`
**Prior reviews:** none — this is the first.

---

## 0. LOAD

### Preconditions — two stop conditions were tripped before the review could start

The review was invoked with **no target finding named** and against a **dirty working tree**
(54 `git status` entries; 23 tracked files, +528/−119; 31 untracked paths). Both are STOP
conditions. The review halted and put the question to the owner rather than proceeding.

**Target derivation.** F-006 was the only finding whose ledger status claimed a fix while no
review document existed (`CONFIRMED — CALIBRATED (default kept at 1.4, 2026-09-02)`, no
`f006-review-*.md`). F-014 is a second unreviewed fix but is cleanly committed at `675c4db` and
separable. Owner confirmed the target as **F-006, then F-014**.

**Tree resolution.** Owner directed *"You commit, you review."* The working tree was therefore
committed **verbatim** — no file content authored or edited by this review — into seven
attributed commits so that F-006's change could be anchored to a SHA per Hard Rule 5. Attribution
was derived from the diff, not from the commit messages that resulted:

| Commit | Workstream | Basis for attribution |
|---|---|---|
| `25c600b` | validation evidence | all paths under `docs/validation/` + the F-014 plan `findings.md` cites |
| `2ce8f0e` | replay viewer | `replay_viewer.py:71,261` consume `autostart` / `_suppress_score_dialog`, both introduced by the `game_viewer.py` diff |
| `a0ac02e` | sims-vs-wins + UCT sweep experiments | `.kilo/plans/1788376789805`, `1788421146967`; `run_ismcts.py` per-seat ladders |
| `9e81d6d` | docs freshness checker | prerequisite of the `docs-check` recipe |
| **`ca64991`** | **F-006** | **the `uct_c` recipe parameters** |
| `3ea0c1f` | docs rename/citation campaign | 7 renames + citation updates |
| `c6a7ee8` | vendored skills | `skills-lock.json` + skill dirs |

Note on a prior review's attribution: `f013-review-04.md` § 9 item 4 treated
`interface/game_viewer.py` as an orphan hunk to be dropped. It is not — it is a load-bearing part
of the replay-viewer feature (`2ce8f0e`). That item is superseded on the facts.

### Pre-registered falsification test (verbatim, `findings.md` F-006)

> **Falsification test:** Search the repo (`docs/`, commit history, `.kilo/plans/`) for evidence
> that `1.4` was chosen via an empirical sweep for this game, versus being the untouched argparse
> factory default.
>
> **Expected if REAL:** No tuning evidence exists for `1.4`; it is simply `argparse`'s default,
> and reward magnitudes were never re-derived against the paper's guidance.
>
> **Expected if FALSE POSITIVE:** A doc, scenario file, or commit shows `1.4` was deliberately
> chosen after empirical comparison for this specific game.

### Note on `register.md`

The protocol's steps 0 and 7 reference `docs/validation/register.md`. **No such file exists**
(`find docs/validation -iname "*register*"` → empty). Prior reviews recorded staleness as
`⚠️ PASS *(STALE — Review NN)*` annotations on the `verdict.md` § 1 invariant rows. This review
follows that established convention; § 7 below is written against `verdict.md` § 1.

---

## 1. DIFF AUDIT

Every hunk in F-006's scope, classified.

| # | Hunk | Commit | Class |
|---|---|---|---|
| H1 | `replay-viewer`, `replay-viewer-open`, `verify-replays` recipes | `ca64991` | **OUT-OF-SCOPE (carried)** → `2ce8f0e` |
| H2 | `ismcts` gains `uct_c="1.4"`, forwarded `--uct-c {{uct_c}}` | `ca64991` | **IMPLEMENTS-FINDING** |
| H3 | `ismcts-quick` gains `uct_c="1.4"`, forwarded `--uct-c {{uct_c}}` | `ca64991` | **IMPLEMENTS-FINDING** |
| H4 | `ismcts-sims-vs-wins-pilot`, `ismcts-sims-vs-wins` recipes | `ca64991` | **OUT-OF-SCOPE (carried)** → `a0ac02e` |
| H5 | `ismcts-uct-pilot`, `ismcts-uct` recipes | `ca64991` | **OUT-OF-SCOPE (carried)** → `9e81d6d`/`a0ac02e` |
| H6 | `docs-check` recipe | `ca64991` | **OUT-OF-SCOPE (carried)** → `9e81d6d` |
| H7 | `docs/validation/f006-fix-plan.md` (new, 16.1K) | `25c600b` | DOC-CHANGE |
| H8 | `docs/validation/harness/f006_sweep.py` (new, 2.7K) | `25c600b` | **IMPLEMENTS-FINDING** |
| H9 | `docs/validation/harness/f006_sweep_results.json` (new) | `25c600b` | DOC-CHANGE (evidence) |

### On the four out-of-scope hunks

H1/H4/H5/H6 are **carried, not authored by the F-006 fix**. They are additive new `just` recipes
belonging to three other workstreams that happened to share the `justfile`. They could not be
separated into their own commit without editing file content, which a reviewer may not do
(Hard Rule 1). They touch neither `ismcts` nor `ismcts-quick` and cannot affect F-006's behaviour.
They are recorded here rather than charged against the fix author, because in the tree as
delivered F-006's own two hunks were physically inseparable from them.

### Rule 4 gaming checklist

**F-006's scope contains zero TEST-CHANGE hunks** — nothing under `tests/` or
`openspiel_pyrants/tests/` appears in `ca64991` or `25c600b`. The checklist was nonetheless run
against the whole commit range, item by item:

| Gaming pattern | Cleared? | Evidence |
|---|---|---|
| Weakened assertion | ✅ cleared | no assertion modified anywhere in range |
| Deleted or skipped test | ✅ cleared | `a0ac02e` test diffs are `+171/−0` and `+35/−0` — purely additive new classes |
| Widened tolerance | ✅ cleared | no tolerance constant touched |
| Reduced N | ✅ cleared | sweep ran N=200/arm against the plan's own N≥200 floor |
| Seed pinned to a passing seed | ✅ cleared | seeds 1000–1099, a contiguous block, derived in-code as `1000 + i//2` — not enumerable/cherry-picked |
| Special case on test input | ✅ cleared | none |
| Swallowed exception | ✅ cleared | none |
| Removed invariant check | ✅ cleared | `inv_a.py`/`inv_b*.py` untouched |
| Disabled warning | ✅ cleared | none |

### Diff vs. plan

**Authorised and delivered:** the `justfile` layer (plan § 3, Phase 1) and a new self-contained
harness script (plan § 4, G2). `ismcts-perf` correctly left untouched —
`git diff 0266851 HEAD -- justfile | grep ismcts-perf` is empty, matching the plan's explicit
reasoning that inserting a named parameter before its `*args` would break the documented
passthrough.

**Plan § 9 out-of-scope respected:** `ca64991` touches no `engine_c/`, no `openspiel_pyrants/`,
and no `scripts/run_ismcts.py`. (`run_ismcts.py` *is* modified in the range, at `a0ac02e` — that
is the experiments workstream, not F-006, and is committed separately precisely so it cannot be
misattributed. Its interaction with F-006's evidence is assessed in § 3.)

**Promised but absent:** the plan's Phase 4 step 3 requires re-running the always-on battery
(`inv_a.py`) as a G4 sanity check. **No G4 result is recorded anywhere in the ledger.** This
review ran it (§ 4c).

---

## 2. CONFORMANCE REVIEW

**Rulebook anchor:** `[absent]` — F-006 is a paper-vs-code finding with no rulebook bearing.

**Whitepaper anchor** (`docs/ismcts-paper.md` § IV-A, re-read at source, not via the finding's
summary), 15 words:

> "The value of 0.7 was thus used for all algorithms in all experiments."

**The finding's paraphrase is materially incomplete.** The same section, two sentences earlier
(`docs/ismcts-paper.md:316-322`), states:

> "It was observed that **none of the algorithms are particularly sensitive to the coefficient
> value** for these games, although performance does decrease outside the range […]"

The paper's actual claim is *insensitivity within a band*, with `0.7` as its chosen point inside
that band — not that `0.7` is uniquely correct. F-006 as filed reads the paper as mandating
`0.7`; the paper does not.

*Documented limitation:* `docs/ismcts-paper.md` is a lossy extraction — the numeric range bounds
at lines 314 and 318 were dropped with the surrounding formulae ("with exploration constant
⟨blank⟩", "decrease outside the range ⟨blank⟩"). It is therefore **not possible to verify from
this repo's copy of the paper** whether `1.4` falls inside the paper's stated band. That is
exactly why an empirical sweep on this game — not a citation — is the right instrument, and the
plan required one.

**What the code now does** (at `ca64991`):

- [justfile:72-73](../../../justfile#L72-L73) — `ismcts` takes trailing `uct_c="1.4"`, forwarded as `--uct-c {{uct_c}}`.
- [justfile:75-76](../../../justfile#L75-L76) — `ismcts-quick` takes trailing `uct_c="1.4"`, forwarded identically.
- [justfile:99-101](../../../justfile#L99-L101) — `ismcts-perf` unchanged; reaches `--uct-c` via its pre-existing `*args`.
- The runtime default is unchanged: `scripts/run_ismcts.py:151` was already `--uct-c` `default=1.4`
  at base `0266851`, so passing `--uct-c 1.4` explicitly is value-identical to omitting the flag.

**Verdict: CONFORMANT.**

The substantive defect F-006 alleged was that `1.4` was **uncalibrated** — "no doc, scenario file,
or commit shows `1.4` was ever compared empirically for this game." That defect is cured: a
seat-swapped sweep at N=200/arm on this game's own reward scale now exists. The measured outcome
— no separation among {0.7, 1.4, 2.8} (p=0.66, p=0.89) and sharp degradation at 8.0 (p≈6e-13) —
**reproduces the paper's own reported behaviour** (insensitive within a band, degrading outside
it) on a new domain. Keeping `1.4` is conformant with what § IV-A actually says.

It also refutes the finding's own mechanism: the 6.4:1 exploitation-to-exploration ratio measured
at root nodes predicted that a much larger constant (~8.9) should help. It does not — 8.0 loses
overwhelmingly. The root-node Q-spread does not model the outcome function's compression.

### One conformance caveat, carried into the verdict as debt

The plan's **G3 gate is quoted as "`verdict.md` § 5 condition 4, verbatim"** and reads:

> "Chosen value **beats** its immediate neighbours, seat-swapped, N ≥ 200 per arm, with
> exact-binomial significance reported."

`1.4` does **not** beat its immediate neighbours. It **ties** them: vs `0.7` p=0.663, vs `2.8`
p=0.886. It beats only `8.0`, which is not an immediate neighbour in the sorted candidate set
`[0.7, 1.4, 2.8, 8.0]`.

`verdict.md` § 5 condition 4 asserts **"Gate met: … with the chosen value beating its
neighbours"** and then, in the same paragraph, states **"it ties 0.7 … and 2.8"**. Those two
clauses contradict each other. The close is legitimate — but under the *plan's* constraint 4
("beats **or ties** its neighbours … is a legitimate, honest close"), which was pre-registered
before the sweep ran and is therefore not post-hoc goalpost-moving. It is **not** legitimate
under condition 4's own "beats" wording, which the plan claimed to be quoting verbatim while
in fact relaxing.

This is a wording defect in a GO/NO-GO blocking condition, not a measurement defect: the numbers
are disclosed correctly and completely one clause later. Per Hard Rule 7 the existing text is not
edited; § 8 appends the correction.

---

## 3. BLAST RADIUS (derived independently)

Changed symbols in F-006's scope: two `just` recipe signatures, and one new standalone harness
script. **No runtime code path is modified** — not the engine, the bindings, the observation, the
utilities, or the search.

| Item | In radius? | One-clause justification |
|---|---|---|
| INV-1 replay determinism | **In** (always-on) | mandatory regardless of radius |
| INV-2 clone independence | **In** (always-on) | mandatory regardless of radius |
| INV-3 legality | **In** (always-on) | mandatory regardless of radius |
| INV-6 chance mass | **In** (always-on) | mandatory regardless of radius |
| INV-7/8/9 strength rows | **In, conceptually** | they are the rows a change of default `uct_c` would invalidate — but the default did **not** change |
| INV-4a/4b info-set leakage & completeness | Out | observation layer untouched; `justfile` cannot reach `private_view_json` |
| INV-5 determinisation consistency | Out | `engine_determinize` untouched |
| INV-10 resource stability | Out | no allocation path touched |
| F-002, F-011, F-013 | Out | engine/binding/observation fixes; no shared symbol with a `just` recipe |
| F-010 reproducibility | **In, indirectly** | the sweep's reproducibility claim ("reproduced identically across two runs") *depends on* F-010 being fixed; § 4 re-tests this |
| F-004 utility contract | Out | `Returns()`/`GameInfo` untouched |

**Insulation check, run rather than assumed.** INV-7/8/9 are produced by
`docs/validation/harness/exp2.py` → `exp.py` → `common.py::make_bot`, which imports
`openspiel_pyrants.ismcts_factory` **directly**. `grep -ln "run_ismcts" docs/validation/harness/*.py`
matches only `common.py`, and only inside a docstring ("Mirrors scripts/run_ismcts.py's loop") —
**no harness script imports `run_ismcts`**. Therefore `a0ac02e`'s changes to `run_ismcts.py`
cannot move any invariant measurement. `exp.py:10` calls `make_bot(g, spec, bseed)` with no
`uct_c`, so every INV-7/8/9 arm ran at `common.py:37`'s `uct_c=1.4` default — the calibrated
value, unchanged by this fix.

**Comparison with the fixing agent's declared radius.** The plan's G4 declared: "This plan touches
no production simulation code … The always-on battery (INV-1/2/3/6) and existing suites are
expected to be completely unaffected." **My radius is wider on one axis** and I record that
explicitly: the fixing agent did not consider that the summary `uct_c` column it nominated as its
G1 verification instrument would have its **semantics changed** by a sibling workstream. At
`a0ac02e`, `_base_game_summary` now writes `uct_c` as `round(mean(uct_c_per_seat), 6)` rather than
the scalar. For F-006's own uniform-seat runs the mean equals the scalar, so the G1 evidence still
holds (verified in § 4b) — but the column no longer means what F-006's close says it means for any
per-seat run. Their radius was narrow on this point; mine includes it.

---

## 4. RE-RUN

All runs at review head `c6a7ee8` unless stated. Every row: command / N / seeds / SHA / prior /
new.

### a. Pre-registered falsification test

**Command:**
```
grep -rnE "uct_c|uct-c|exploration constant" --include=*.md docs/ .kilo/
git log --all --oneline -S"uct_c" -- scripts/run_ismcts.py
```
**N:** whole-repo doc/plan search + full commit history · **Seeds:** n/a

| SHA | Result |
|---|---|
| `0266851` (state the fix author left) | `git ls-tree -r 0266851 -- docs/validation/harness/` → **only `f006.py`**; `f006_sweep.py`, `f006_sweep_results.json`, `f006-fix-plan.md` **absent from the tree at every commit**. `git show 0266851:docs/validation/findings.md \| grep -c "uct_c=0.7 vs uct_c=1.4"` → **1**. |
| `c6a7ee8` (review head) | `docs/validation/f006-fix-plan.md` present with the full sweep design and results; harness + results artifact present. |

**✅ Pre-registered test: PASS — matches "Expected if FALSE POSITIVE" (i.e. the defect condition
is cleared) — but ONLY at `25c600b` or later.**

**This must be read with its qualifier.** At `0266851`, the last commit the fix author produced,
the ledger asserted the sweep numbers while the harness that generated them, the results
artifact, and the fix plan existed **at no commit in history**. Run at that SHA the
pre-registered test still returns *Expected if REAL*. The evidence entered history only at
`25c600b`, **a commit this review created** under owner direction. The fix author did not
satisfy their own finding's falsification test. Filed as **F-016**.

### b. G1 — flag actually reaches the bot (plan's own nominated instrument)

**Command:** `just ismcts 2 1 42 <scratch> 1 2 <uct_c>` → parse `summary.csv`
**N:** 4 runs · **Seeds:** shuffle seed 42 · **SHA:** `c6a7ee8`

| Run | `uct_c` | `uct_c_per_seat` | winner | decisions | verdict |
|---|---|---|---|---|---|
| explicit `0.7`, workers=1 | `0.7` | `0.7,0.7` | 1 | 517 | ✅ |
| omitted, workers=1 | `1.4` | `1.4,1.4` | 1 | 517 | ✅ default preserved |
| explicit `1.4`, workers=1 | `1.4` | `1.4,1.4` | 1 | 517 | ✅ identical to omitted |
| explicit `0.7`, **workers=2**, 2 games | `0.7` | `0.7,0.7` | 1 / 0 | 517 / 568 | ✅ multi-worker path |

Omitted and explicit-`1.4` runs produced identical `initial_state_sha256`
(`619b25fd38d519f8`), identical winner, identical decision count — differing only in `run_id`
and wall-time. Combined with `run_ismcts.py:151`'s pre-existing `default=1.4` at base, **plan
constraint 1 (additive-only, byte-identical omitted path) is satisfied.**

**✅ G1: PASS, N=4 runs, was: dry-run-verified only for `ismcts-perf`; now live-verified for
`ismcts` single- and multi-worker.**

### c. G4 / always-on battery — the check the plan required and never recorded

**Command:** `.venv/Scripts/python.exe -u docs/validation/harness/inv_a.py` · **SHA:** `c6a7ee8`

| Check | Result | N | Seeds | Prior (`verdict.md` § 1) |
|---|---|---|---|---|
| INV-1 replay determinism | ✅ **PASS** | 100 | 1–100 | PASS, 100 |
| INV-2 clone independence | ✅ **PASS** | **277** probes | 1–100 | PASS, 235 probes |
| INV-3 legality (empty=0, dup=0, oor=0) | ✅ **PASS** | 1,200 | **1–20** | PASS, 1,200, "seeds 1–22" |
| INV-6 chance mass | ✅ **PASS** | 30 | 1–30 | PASS, 30 |

**✅ Always-on battery: 4/4 PASS.**

Two ledger-vs-harness drifts, both pre-dating this review and neither a regression:
INV-2's probe count is **277, not the 235** recorded in `verdict.md` § 1 (probe count tracks game
trajectories and moved with the F-013 Part B clone/determinize changes at `1564bdd`/`13c3fe4`/`f9157a4`);
INV-3's harness reports **seeds `1..20`** where `verdict.md` § 1 says "seeds 1–22". Per Hard Rule 7
neither prior measurement is edited — recorded here as observations.

### d. Regression suite

**Command:** `.venv/Scripts/python.exe -m pytest -q --tb=no --no-header` · **SHA:** `c6a7ee8`
**N:** 928 collected across 156 files → **923 passed, 4 failed, 1 skipped**

| Failure | Status |
|---|---|
| `tests/c_engine/test_card_zuggtmoy.py::test_zuggtmoy_eot_promote_two_other_cards_excludes_self` | pre-existing, documented tolerated (`findings.md` F-014 resolution) |
| `tests/c_engine/test_engine_c.py::test_air_elemental_option_1_focus_draw` | pre-existing, documented tolerated |
| `tests/test_card_neogi.py::test_neogi_execution_model_deploys_four_and_random_mass_discard` | pre-existing, documented tolerated (this is **F-015**, OPEN) |
| `tests/test_replay_player.py::test_decision_at_matches_step` | **NEW** — from `2ce8f0e` (replay viewer), **outside F-006's blast radius**. Filed as **F-018**. |

**✅ Regressions attributable to F-006: NONE.** The one new failure is in a feature workstream
that shares no symbol with F-006's change.

### e. Previously-CONFIRMED findings inside the blast radius

Only **F-010** (reproducibility) is in-radius, and only indirectly: the sweep's headline
reproducibility claim depends on it. Tested in § 4f.

### f. Independent reproduction of the headline evidence

**Command:** `.venv/Scripts/python.exe -u docs/validation/harness/f006_sweep.py "1.4,2.8" 200 200`
**N:** 200 games (100 seeds × 2 seats) · **Seeds:** 1000–1099 · **SHA:** `c6a7ee8`
**Prior (committed artifact):** `1.4_vs_2.8` → N=200, W98/L95/T7, p=0.8855779994131153, mean_margin=+0.715

**New result (elapsed 502 s):**
```
uct_c=1.4 vs uct_c=2.8: N=200 winrate=0.507 (W98/L95/T7) exact-binom p=0.8856 on 193 decisive mean_margin=+0.71
```
Re-read from the written JSON: `p=0.8855779994131153`, `mean_margin=0.715`.

**✅ Reproduction: PASS — bit-identical.** W, L, T, the full-precision `p` and `mean_margin` all
match the committed artifact exactly. This is now the **third** independent computation of this
pairing (the ledger records two prior runs producing W98/L95/T7). The headline evidence backing
F-006's close is sound, and **F-010's determinism fix holds** under an independent 200-game
re-run at seeds 1000–1099.

**✅ F-010 (in-radius, previously CONFIRMED–FIXED): PASS, N=200, was PASS.**

**Side effect, and it is a finding.** That single documented command **overwrote the evidence
file with only its own pairing**: `git diff --stat` → `2 insertions(+), 30 deletions(-)`; three
of the four recorded pairings and the `_note` field were destroyed. The committed artifact was
restored with `git checkout --` and verified byte-intact (all 5 keys present). Filed as
**F-017** — see § 5.

---

## 5. NEW FINDINGS

Three surfaced by this review. Filed to `findings.md` under the original schema, Status OPEN, and
**not investigated further and not fixed**, per protocol step 5.

- **F-016** — the ledger's committed close text cites evidence that exists at no commit.
- **F-017** — `f006_sweep_results.json` cannot be regenerated by any documented command; the
  harness opens it `"w"` and writes only the current invocation's adjacent pairs, yet the
  committed file holds four pairings plus a `_note` key the script never emits.
- **F-018** — `tests/test_replay_player.py::test_decision_at_matches_step` fails at `c6a7ee8`:
  `decision_at` returns a decision whose `chosen_move` disagrees with the step label at the same
  index.

**Count: 3.**

---

## 6. VERDICT

# ACCEPTED-WITH-DEBT

The fix is substantively correct, conformant, reproducible, and free of regressions. It does not
qualify for a clean ACCEPTED because Hard Rule 8 requires *zero* out-of-scope hunks and *test PASS
at the fix's own commit*, and neither holds strictly. The debt is enumerated and none of it
undermines the finding's close.

**What is solid:**

1. The pre-registered falsification test passes at review head, and its supporting evidence
   reproduces **bit-identically** on an independent 200-game re-run (§ 4a, § 4f).
2. Conformance is **CONFORMANT** — and on re-reading the paper directly, *better* founded than the
   finding itself argued: § IV-A claims insensitivity within a band, which is exactly what the
   sweep measured on this domain (§ 2).
3. Zero regressions attributable to F-006. Always-on battery 4/4 PASS; 923/928 tests pass with
   the only new failure in an unrelated workstream (§ 4c, § 4d).
4. Constraint 1 (additive-only, byte-identical default path) verified live on single- **and**
   multi-worker paths, going beyond the plan's own dry-run verification (§ 4b).
5. Zero cascade — the default did not change and no runtime code was touched (§ 7).

**The debt, in descending order of importance:**

| # | Debt | Anchor |
|---|---|---|
| D1 | **Evidence existed at no commit when the finding was closed.** At `0266851` the ledger asserted the sweep numbers while the harness, results artifact and fix plan were untracked. The fix author's own falsification test still returned *Expected if REAL* at their last commit. Resolved only by `25c600b`, created by this review under owner direction. | § 4a → **F-016** |
| D2 | **`verdict.md` § 5 condition 4 states "Gate met: … with the chosen value beating its neighbours" while its own data says `1.4` ties 0.7 (p=0.663) and 2.8 (p=0.886).** The close is valid under the plan's pre-registered constraint 4 ("beats **or ties**") but not under condition 4's "beats", which the plan claimed to quote verbatim while relaxing. | § 2 → corrected in `verdict.md`, § 8 |
| D3 | **The evidence artifact is not regenerable.** Any documented command destroys 2–3 of its 4 pairings. Confirmed live. | § 4f → **F-017** |
| D4 | **Four carried out-of-scope hunk groups** in `ca64991` (H1/H4/H5/H6). Not authored by the F-006 fix; physically inseparable in the tree as delivered without editing content, which a reviewer may not do. | § 1 |
| D5 | The plan's **G4 was never run or recorded** by the fix author. This review ran it; it passes. | § 4c |

**Why not REJECTED-SCOPE.** D4's hunks belong to three sibling workstreams that shared the
`justfile`; charging them to F-006 would be a false attribution, which is precisely the error
`f013-review-04.md` § 9 item 4 made with `game_viewer.py`. F-006's own two hunks (H2, H3) are
clean and plan-authorised.

**Why not REJECTED-NONCONFORMANT.** D2 is a defect in how a gate's satisfaction was *worded*, not
in the measurement. The contradicting numbers are disclosed one clause later in the same
paragraph. Nothing was hidden.

**Why not UNRESOLVED.** The output matched a pre-registered expectation exactly — *Expected if
FALSE POSITIVE* — at review head.

---

## 7. INVALIDATION CASCADE

**Newly STALE: none. Count: 0.**

F-006's change (`ca64991`) touches the `justfile` and one standalone harness script. It modifies
no engine, no binding, no observation, no utility, and no search code, and it leaves the runtime
default at `1.4`. The STRENGTH-row cascade rule ("any STRENGTH row goes STALE on ANY change to the
engine, the binding, the observation, the utilities, or the search") is therefore **not**
triggered by this fix.

**Already STALE, unchanged by this review:** INV-7, INV-8, INV-9 — stale since Review 01 of
F-010, pending re-measurement at the final gate. This review does **not** re-measure them; per the
protocol they belong to the final GO gate.

**Considered and excluded:** `a0ac02e` modifies `scripts/run_ismcts.py`, which is a *runner*, not
the search. INV-7/8/9 are produced by `harness/exp2.py` → `common.py`, which does not import
`run_ismcts` (§ 3). No cascade from it either.

---

## 8. RECORD

This file. `findings.md` gains an F-006 `Review 01` block and three new findings (F-016, F-017,
F-018). `verdict.md` gains a one-line F-006 review annotation plus a correction note on § 5
condition 4's "Gate met … beating its neighbours" wording; no prior measurement is edited
(Hard Rule 7).

---

## 9. HANDOFF

**ACCEPTED-WITH-DEBT — no fix-agent action is required to close F-006.** The debt is recorded as
findings, not as rework: D1 → F-016, D3 → F-017, D2 → corrected in `verdict.md` by this review,
D4/D5 → recorded here.

**Next finding in recommended order: F-014** (`give_insane_outcast` mints without its 30-copy
special-stack cap) — because it is the only other finding carrying a fix that has never been
reviewed, its fix is already cleanly committed at `675c4db`, and its `min_utility` claim is
load-bearing for F-004's accepted close.

**Blocking findings remaining: 0.** All four original GO conditions are cleared and F-003 is
formally postponed by ADR-0002. F-014, F-015, F-016, F-017 and F-018 are non-blocking; the final
GO gate remains gated on re-measuring the STALE INV-7/8/9 STRENGTH rows at a single clean SHA,
which is a separate invocation.

STOP. No source touched by this review; no fix authored or repaired.
