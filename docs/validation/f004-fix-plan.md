# F-004 Fix Plan — `Returns()`/`UtilitySum`/`MinUtility`/`MaxUtility` Contract for 3–4 Player Games

**Defect:** `docs/validation/findings.md` § F-004 (CRITICAL) — `PyrantsCGame` declares
`utility_sum=0.0` and `min_utility=-max_utility` unconditionally for every `num_players`, but
`PyrantsCState.returns()` only actually zero-sums the `n==2` case; for `n>2` it returns raw,
non-negative VP totals whose sum is the total VP awarded (never 0) and which are never negative
(contradicting the declared `-400.0` floor).

**Why this one next:** `docs/validation/verdict.md` § 5 names F-004 condition 2, the first
still-open blocking gate after F-011 (Review 01, `docs/validation/reviews/f011-review-01.md`,
ACCEPTED-WITH-DEBT) closed condition 1. F-004 blocks the project's own default configuration —
`just ismcts` runs `num_players=4` (`justfile:63`) — so every default invocation of the training
entry point currently carries a violated API contract.

---

## 0. Mandatory process constraints

Same three as `f010-fix-plan.md` and `f011-fix-plan.md`, restated because they are
non-negotiable, not finding-specific:

1. **Test-driven design is mandatory.** Every behavioural change starts as a failing test.
   Phase 2 does not begin until Phase 1's tests are written, run, and observed to **fail for the
   stated reason**.
2. **This change will be reviewed.** Phase 5 is required, not a courtesy pass.
3. **`docs/validation/verdict.md` must be updated.** Phase 6 rewrites the F-004 entry and the
   § 5 GO/NO-GO conditions. A fix that lands without the verdict update leaves the audit record
   lying.

---

## 1. Root cause (verified, not assumed)

**(a) The declaration.** `openspiel_pyrants/game_c.py:65-75` (`_build_c_game_info`):

```python
def _build_c_game_info(num_players: int) -> pyspiel.GameInfo:
    max_utility = 200.0 if num_players == 2 else 400.0
    return pyspiel.GameInfo(
        ...
        min_utility=-max_utility,
        max_utility=max_utility,
        utility_sum=0.0,
        ...
    )
```

`min_utility`/`utility_sum` do not vary with `num_players`, even though `_build_c_game_type`
(`game_c.py:33-38`, unchanged, not part of this fix) already correctly declares
`GameType.Utility.GENERAL_SUM` for `num_players > 2` — the type-level declaration is right; only
the two `GameInfo` scalar fields that should track it are wrong.

**(b) The actual behaviour.** `openspiel_pyrants/state_c.py:171-187` (`PyrantsCState.returns`):

```python
if n == 2:
    s0 = scores.get(player_ids[0], 0)
    s1 = scores.get(player_ids[1], 0)
    return [float(s0 - s1), float(s1 - s0)]
return [float(scores.get(pid, 0)) for pid in player_ids]
```

`n==2` returns a genuine zero-sum margin (`s0-s1`/`s1-s0`, always symmetric, always within
`[-200,200]` given `max_utility=200` for `n==2`). `n>2` returns each player's *raw* score —
correct per the rulebook (VP is additive; nothing in `docs/tyrants-rulebook.md` § Final Scoring,
line 398, subtracts VP), but incompatible with a `0.0`/`-max_utility` declaration.

**(c) This was a deliberate, documented choice — and it was already flagged as provisional.**
`.kilo/plans/4-player-ismcts.md` (the original N-player generalization plan, predating the C
engine port) § "Confirmed Choices" line 210: **"`utility_sum=0.0` always."** — reasoned at
line 77-81: *"Recommended: always `GENERAL_SUM`, but `utility_sum=0.0` only when N==2` (matches
today's invariant). For N>2, leave `utility_sum=0.0` (the field documents the 'best-case' sum;
for general-sum games OpenSpiel doesn't enforce it)."* This is F-004's own steelman, already on
record before the finding existed: the field was believed to be inert metadata OpenSpiel
wouldn't check. Grepping the entire installed `open_spiel` Python package
(`.venv/Lib/site-packages/open_spiel/python/`) for `utility_sum`, `min_utility`, `max_utility`,
`UtilitySum`, `MinUtility`, `MaxUtility` returns **zero matches** — confirmed fresh this session,
not assumed from the plan's own claim. `ISMCTSBot`'s backup step (`ismcts.py:383`) uses raw
`returns()[cur_player]` with no normalization by any of these three fields, matching F-004's own
steelman in `findings.md`. **The field is inert for every search this repo currently runs** —
this fix is a pure API-contract correction with zero effect on `scripts/run_ismcts.py` behaviour.

**(d) `utility_sum=None` is the standard, documented convention — not a workaround.**
`.kilo/skills/openspiel-custom-games/references/game-implementation.md:52`, this repo's own
reference material for building OpenSpiel games:
`utility_sum=0.0,  # only for constant-sum games; omit for general-sum`. Confirmed live against
the installed binding this session: `pyspiel.GameInfo.__init__`'s signature is
`utility_sum: SupportsFloat | SupportsIndex | None = None` — `None` is literally the parameter's
own default, not a special case grafted on. A live round-trip (`pyspiel.load_game` with a
monkey-patched `_build_c_game_info` returning `utility_sum=None` for `num_players>2`) confirms
`game.utility_sum()` returns `None` cleanly, `game.get_type().utility` still reports
`Utility.GENERAL_SUM`, and full games play to terminal with no error. This settles the finding's
own two-option framing (`verdict.md` § 5 condition 2: *"Either make `returns()` zero-sum for
n > 2, or declare `utility_sum=None` with honest `min_utility`/`max_utility`"*) in favor of the
**second** option: forcing `returns()` to be zero-sum for `n>2` would require inventing a
relative-score transform (e.g. score minus the mean of opponents) that the rulebook does not
describe — VP in Tyrants is an absolute race, not a relative one, for any player count. Changing
`returns()` would change what every consumer (search backup, any future analysis) actually
receives; changing `GameInfo`'s declaration changes only metadata to match reality.

**Load-bearing detail — `min_utility=0.0` is *not* an honest bound; the true floor needs its own
derivation.** The natural first guess (`min_utility=0.0`, since `n>2` returns are raw VP totals)
was checked against the engine, not assumed. Every direct mutation of `PlayerState.score` and
`PlayerState.vp_tokens` across `engine_c/*.c` is `+=` (`scoring.c:86`, `helpers.c:449`,
`rules.c:354,554`, `actions.c:255,557` — grepped in full, zero `-=` sites for either field). But
`compute_final_scores` (`scoring.c:90-126`) also adds `cards_vp(...)`, which sums each held
card's `deck_vp` — and one card is **not** additive:
`data/cards/insane_outcast.json`: `"deck_vp": -1`, the *only* negative `deck_vp`/`inner_circle_vp`
value across all 127 per-card JSON files (scanned in full this session). Its own `"notes"` field
confirms this is intentional: *"a negative-VP card opponents can force into your deck."* Six
cards carry a `give_insane_outcast_*` effect (`ghoul.json`, `demogorgon.json`, `derro.json`,
`gibbering_mouther.json`, `myconid_adult.json`, `myconid_sovereign.json`), implemented by
`engine_c/actions.c:698-705` (`give_insane_outcast`), which appends `"insane_outcast"` directly
to a target's `discard_pile` up to `MAX_ZONE_SIZE` (80, `state.h:16`) per zone, for each of
`hand`/`deck`/`discard_pile` (`scoring.c:117-119` concatenates all three into `cards_vp`'s input).
The card also has a **nominal** shared-supply cap: `engine_c/helpers.c:266`
(`special_stack_config`, `market_slot==102`) declares `stack_total=30` — but
`give_insane_outcast` (`actions.c:698-705`) never calls `remaining_special_stack_count` or
checks that cap before minting a fresh symbol into a zone; the 30-copy figure governs only the
shared *market* supply's replenishment display, not what the four `give_insane_outcast_*` effect
handlers can mint. **This means the engine does not currently enforce a hard ceiling on how
negative one player's `deck_vp` contribution can go**, and deriving the *true*, tight,
rules-intended worst case would require either fixing that engine-level gap (out of scope — it
is a C rules-correctness question, `engine_c/actions.c`, not an OpenSpiel `GameInfo` metadata
question) or an exhaustive reachability proof across `max_game_length=4096` actions (out of
scope, matching `findings.md` § 5's existing "Exhaustive per-card rulebook conformance... out of
scope" and "Resource/deck/card-count conservation proofs... not audited end-to-end" posture).

**Decision:** do not chase a formally tight bound (none exists cheaply, and `max_utility=400.0`
itself was never formally derived either — it is already a generous, un-disputed round figure
relative to the ~10–25 raw VP totals observed in `findings.md`'s own N=8 sample). Declare a
**conservative, explicitly-labeled-as-practical** `min_utility=-50.0` for `num_players>2` —
comfortably below the nominal 30-copy design intent, verified empirically in Phase 0/4 against
both ordinary random play and a dedicated stress probe (T6) that deliberately maximizes
`insane_outcast` issuance. If Phase 0/4's stress probe ever produces a return below −50.0, this
plan's contingency is to **raise a new ledger finding** for the engine-level over-issuance gap
(candidate title: "`give_insane_outcast` does not respect its own 30-copy special-stack cap") —
**not** to silently widen `min_utility` further inside this fix. `n==2` is unaffected either way:
its `returns()` is a *difference* of two scores, and — newly noted here, not previously checked
by F-004 or any prior review — the existing `-200/+200` bound was **never verified against
individual return magnitude**, only against the zero-sum *property* (`findings.md` F-004:
`"sum(returns)==0.0 in 8/8"`). This plan adds a due-diligence regression guard for that (T2/T7
below) without changing the `n==2` declaration, since no evidence currently shows it violated.

---

## 2. Acceptance gates

| Gate | Threshold |
|---|---|
| G1 `n==2` unchanged | `game.utility_sum()==0.0`, `min_utility()==-200.0`, `max_utility()==200.0`, `game.get_type().utility==ZERO_SUM` — byte-identical to pre-fix |
| G2 `n>2` honest declaration | `game.utility_sum() is None`, `min_utility()==-50.0`, `max_utility()==400.0` (unchanged), `game.get_type().utility==GENERAL_SUM` (unchanged) for `num_players` ∈ {3,4} |
| G3 Contract compliance under ordinary play | For `num_players` ∈ {2,3,4}, over **N ≥ 50** terminal games (random policy), every observed `returns()` entry satisfies `min_utility <= r <= max_utility`, and for `n==2` additionally `sum(returns)==0.0` — matches `verdict.md` § 5 condition 2's own gate text verbatim |
| G4 Contract compliance under `insane_outcast` stress | A dedicated stress probe (T6) that forces heavy `insane_outcast` accumulation on one player does not produce a return below the declared `min_utility` for that player count. If it does, **do not adjust `min_utility` inside this fix** — file the engine-level gap as a new finding instead (§ 11) and re-open this gate |
| G5 Zero production consumers disturbed | `grep -rn "\.utility_sum()\|\.min_utility()\|\.max_utility()" --include=*.py` (excluding `docs/validation/`) still returns zero matches in `scripts/`, `openspiel_pyrants/`, `engine_c/` after the fix — confirms the fix cannot regress `run_ismcts.py` behaviour, since nothing there reads these fields either before or after |
| G6 Existing suites green | `just openspiel-test`, `just test` both pass; the 3 pre-existing `engine_c`/catalog failures already on record (`f010-review-01.md` § 4e, `f011-review-01.md` § 4e) are the only tolerated failures |

---

## 3. Phase 0 — Capture the red baseline

The existing N=8-per-player-count capture is already immutable ledger content
(`findings.md` F-004 `Observed:` block) — not re-captured here, per Hard Rule 7 (append-only,
never re-run to overwrite a prior measurement). Phase 0 instead captures a **new**, wider
baseline at the gate's own N (≥50), so Phase 4's post-fix numbers have an apples-to-apples
pre-fix comparison at the same N:

```
.venv/Scripts/python.exe -u docs/validation/harness/f004_utility.py > docs/validation/baseline/f004_utility.pre.txt
```

(`f004_utility.py` is new — see Phase 1 T5/T6 for its two sections. It is a script, not a
pytest module, matching the `f011_timing.py` precedent for wall-clock/large-N measurements that
don't belong in the pytest suite's normal budget.)

Expected content: `utility_sum=0.0` for `n=2` (already correct, unchanged), `utility_sum=0.0` for
`n=3,4` (**still wrong, pre-fix** — this is the red signal); `min(returns)` values non-negative
in ordinary play at this N (consistent with the N=8 sample) but the stress probe (T6) is expected
to show a genuinely negative return, since nothing before this fix changes `insane_outcast`
issuance — the stress probe's result should be identical pre- and post-fix (it is a probe of
*engine* behaviour, not of the `GameInfo` declaration being fixed), and its purpose is to inform
what `min_utility` value G2 should assert.

---

## 4. Phase 1 — RED: tests first

New file: `openspiel_pyrants/tests/test_utility_contract.py`, using the same `requires_c_engine`
fixture and `_load_c_game`-style helper pattern as `test_observation_completeness.py`. Per the
house pattern established in both prior fix plans: **write the regression/due-diligence controls
(T1, T2) before the completeness assertions (T3, T4)**, so the guards against breaking what
already works exist in git history before the change that could break them.

| # | Test | Asserts | Pre-fix |
|---|---|---|---|
| T1 | `test_two_player_contract_unchanged` | `num_players=2`: `game.utility_sum()==0.0`, `min_utility()==-200.0`, `max_utility()==200.0`, `get_type().utility==ZERO_SUM` | **PASS** (control — already correct today; must *stay* passing, this is gate G1) |
| T2 | `test_two_player_returns_within_declared_bounds` | Over N=50 random-policy 2-player games, every `returns()` entry is in `[-200,200]` and `sum(returns)==0.0` | **PASS** (control — new due-diligence check on a claim the original F-004 finding never verified at the magnitude level, only the zero-sum property; expected to already hold, locks it in either way) |
| T3 | `test_three_and_four_player_utility_sum_is_none` | `num_players` ∈ {3,4}: `game.utility_sum() is None` | **FAIL** (currently `0.0`) |
| T4 | `test_three_and_four_player_min_utility_is_honest` | `num_players` ∈ {3,4}: `min_utility()==-50.0`, `max_utility()==400.0` (unchanged), `get_type().utility==GENERAL_SUM` (unchanged) | **FAIL** (`min_utility` currently `-400.0`) |
| T5 | `test_three_and_four_player_returns_within_declared_bounds` | Over N=50 random-policy games per player count ∈ {3,4}, every `returns()` entry is in `[-50,400]` | **PASS even pre-fix** at the *engine* level (returns are already what they are; only the *declaration* is fixed by this change) — included as a gate for G3, not expected to flip red→green, but must be captured pre-fix as part of G4's baseline reasoning |
| T6 | `test_insane_outcast_stress_does_not_exceed_min_utility` (in `f004_utility.py`, script not pytest — mirrors `f011_timing.py`'s reasoning: this is a large-N, potentially-slow stress probe, not a unit test) | Force-inject `insane_outcast` into one player's `hand`/`deck`/`discard_pile` (direct struct surgery, mirroring `test_observation_completeness.py::_force_discard`) up to a count derived from repeatedly applying every `give_insane_outcast_*` card in a scripted sequence if reachable within `max_game_length`, else via direct injection as an upper-bound proxy; call `final_scores()`/`returns()` and report the resulting value against `-50.0` | N/A pre-fix — this measures engine behaviour Phase 0 already captured; used to **validate** the `-50.0` choice, not to flip red→green |

T3/T4 are the RED tests proper (fail today because the declaration is wrong). T1/T2/T5 are
controls. T6 is validation evidence for the `min_utility` value itself, captured in Phase 0 and
re-confirmed unchanged in Phase 4 (the fix touches no engine code, so T6's result must be
identical before and after).

---

## 5. Phase 2 — GREEN: minimal implementation

One edit, confined to `openspiel_pyrants/game_c.py::_build_c_game_info`. Does not touch
`state_c.py::returns()`, `_build_c_game_type`, or any `engine_c/` file.

```python
def _build_c_game_info(num_players: int) -> pyspiel.GameInfo:
    max_utility = 200.0 if num_players == 2 else 400.0
    if num_players == 2:
        min_utility = -max_utility          # UNCHANGED — n==2 returns() is a genuine margin
        utility_sum = 0.0                   # UNCHANGED — margin always sums to 0
    else:
        min_utility = -50.0                 # NEW — honest floor; see f004-fix-plan.md § 1
        utility_sum = None                  # NEW — general-sum, no fixed sum; OpenSpiel's own
                                             # documented convention (omit for general-sum)
    return pyspiel.GameInfo(
        num_distinct_actions=NUM_DISTINCT_ACTIONS,
        max_chance_outcomes=1000,
        num_players=num_players,
        min_utility=min_utility,
        max_utility=max_utility,
        utility_sum=utility_sum,
        max_game_length=4096,
    )
```

Run T1–T5. All should now pass. T6 (script) should report an unchanged value from its Phase 0
capture, since nothing this phase touches affects it.

---

## 6. Phase 3 — Guard against silent regression

- T1/T2 (n==2 contract, including the newly-added magnitude check) stay in the permanent suite
  — the guard against a future edit accidentally merging the two branches of the new
  `if num_players == 2` back together.
- T5 (n>2 magnitude bound over N=50) stays in the permanent suite — the guard against a future
  card addition (a second negative-`deck_vp` card, a new `give_*`-style penalty effect) silently
  pushing a return below `-50.0` without anyone noticing. This is the one guard this fix can add
  that actually protects against the real risk identified in § 1's load-bearing detail: the
  engine has no structural cap on `insane_outcast` issuance, so this is a live, not theoretical,
  regression surface.
- No `raise`-style guard is applicable here (unlike F-010's `TypeError` guard) — this is a
  metadata-declaration fix, not a code path with an unsafe fallback to make unreachable.

---

## 7. Phase 4 — Re-run the invariant battery against the gates

```
.venv/Scripts/python.exe -u docs/validation/harness/f004_utility.py > docs/validation/baseline/f004_utility.post.txt   # G3/G4
.venv/Scripts/python.exe -u docs/validation/harness/findings.py                                                        # re-confirm F-004's own original N=8 section, for continuity with the ledger's existing Command
pytest openspiel_pyrants/tests/test_utility_contract.py -v                                                             # G1/G2/G3
just openspiel-test                                                                                                    # G6
just test                                                                                                              # G6
```

**Expected post-fix results** — written down before running, any mismatch is unresolved, not a
pass:

- `n==2`: `utility_sum=0.0`, `min_utility=-200.0`, `max_utility=200.0` — byte-identical to
  Phase 0's capture (G1).
- `n∈{3,4}`: `utility_sum=None`, `min_utility=-50.0`, `max_utility=400.0` (G2).
- G3: 0 out-of-bounds returns across N=50×3 player-counts.
- G4 (T6 stress probe): unchanged from Phase 0's capture (this fix touches no engine code) — if
  Phase 0 already showed a value at or below `-50.0`, **stop and revisit § 1's chosen bound
  before Phase 5**, do not paper over it in the review.
- G5: `grep` for the three method calls outside `docs/validation/` still returns zero matches.
- G6: same 3 pre-existing failures as `f010-review-01.md`/`f011-review-01.md` (Zuggtmoy, Air
  Elemental, Neogi), zero new failures — this fix touches `openspiel_pyrants/game_c.py` only,
  disjoint from `engine_c/rules.c`/`data/cards/catalog.json`, which those three exercise.
- Always-on regardless of radius (replay determinism, clone independence, legality, chance mass —
  `docs/validation/harness/inv_a.py`): not expected to move: `GameInfo` metadata is not consulted
  by `apply_action`/`legal_actions`/`clone`/`chance_outcomes` anywhere in `state_c.py` (confirmed
  by reading the file in full during this plan's investigation — the only place `GameInfo`'s
  three fields are read at all, in-repo, is the validation harness). Re-run anyway per Hard
  Rule/Step 4c, not skipped on the strength of that reading alone.
- F-002, F-010, F-011 (unrelated code paths — `engine_c/state.c` RNG streams, `ismcts_factory.py`,
  `c_adapter.py`): not expected to move; not re-measured here beyond what the always-on battery
  already covers.

---

## 8. Phase 5 — Review (required gate)

Run `/code-review` on the branch diff, then a pass against this checklist:

- [ ] Every production edit traces to a test that was red first (Phase 1 evidence attached).
- [ ] **`n==2`'s branch is byte-identical to pre-fix** — reviewer diffs
      `openspiel_pyrants/game_c.py` and confirms the `if num_players == 2:` branch's three
      values (`-200.0`/`200.0`/`0.0`) are untouched, not just re-derived to the same numbers by
      coincidence.
- [ ] **The `-50.0` `min_utility` choice is justified in the diff or its accompanying doc, not a
      bare magic number** — reviewer confirms § 1's `insane_outcast`/`give_insane_outcast`
      reasoning is either inline (docstring/comment) or citable via this fix plan, and that T6's
      stress-probe result is attached and is ≥ −50.0.
- [ ] **G5 is re-verified independently** — reviewer re-runs the `grep` for
      `.utility_sum()`/`.min_utility()`/`.max_utility()` outside `docs/validation/`, does not
      trust the plan's own claim of zero call sites.
- [ ] `state_c.py::returns()` diff is empty — this fix must not touch the actual reward
      computation, only the declared metadata.
- [ ] If T6/G4 ever produced a value below `-50.0` anywhere in the process, confirm a new
      finding was actually filed for the `give_insane_outcast` over-issuance gap (§ 11), not
      silently absorbed by widening `min_utility` without a paper trail.
- [ ] Pre/post harness outputs (`f004_utility.pre/post.txt`) are attached to the review.

---

## 9. Phase 6 — Update the audit record (required)

1. **`docs/validation/verdict.md`**
   - § 2: move F-004 into a resolved section, following the same format F-010/F-011 used —
     fixing commit, the chosen `-50.0`/`None` values, G1–G6 evidence.
   - § 5: strike condition 2, promote conditions 3–4 (F-002+F-003; F-006), restate GO/NO-GO.
     Verdict likely **stays NO-GO** — F-002/F-003 and F-006 are unaffected by this fix and
     remain open.
2. **`docs/validation/findings.md`** — F-004 `Status:` becomes `**CONFIRMED — FIXED** (<commit
   sha>)`, original N=8 observed evidence kept intact (append-only, per Hard Rule 7).
3. If Phase 4's G4 stress probe found a return at or below `-50.0` at any point during
   implementation (even if later mitigated by choosing a different bound), file the candidate
   finding named in § 11 now, with its own falsification test — do not fold it into F-004's own
   entry.

---

## 10. Risks

| Risk | Mitigation |
|---|---|
| `min_utility=-50.0` is still theoretically violable given `give_insane_outcast`'s uncapped issuance (§ 1 load-bearing detail) | T6 stress probe measures this directly before the bound is finalized; explicit contingency (§ 11) to file a new finding rather than silently re-widen the bound if violated |
| A future card adds a second negative-`deck_vp`/`inner_circle_vp` value, invalidating `-50.0` silently | T5 stays in the permanent suite (Phase 3) as an N=50 magnitude regression guard, not a one-time check |
| `n==2` branch accidentally merged with the `n>2` branch during the edit | T1/T2 regression controls; Phase 5 checklist item requires an explicit byte-diff confirmation |
| Some out-of-repo or future OpenSpiel algorithm added to this project later reads `utility_sum()` and mishandles `None` for a `GENERAL_SUM` game | This is the documented, standard OpenSpiel convention (`.kilo/skills/openspiel-custom-games/references/game-implementation.md:52`), not a project-specific workaround; any future consumer that mishandles the documented API contract is a bug in that consumer, not in this fix |
| Historical `artifacts/ismcts/` runs or saved comparisons that read `GameInfo` fields become stale | None found in-repo (G5 confirms zero consumers); no equivalent of F-010/F-011's fingerprint-invalidation note is needed here |

## 11. Out of scope

F-002, F-003, F-005, F-006, F-008, F-009, F-013 — each has its own verdict condition, do not
bundle. **`state_c.py::returns()`'s actual reward computation** is explicitly out of scope — this
plan fixes the declared contract to match existing, rulebook-conformant behaviour, not the other
way around. **The `give_insane_outcast` uncapped-issuance gap found during this investigation**
(`engine_c/actions.c:698-705` never consults `remaining_special_stack_count`/the 30-copy
`special_stack_config` cap before minting `insane_outcast` instances) is explicitly out of scope
for this plan — it is a C rules-correctness question in a completely different layer
(`engine_c/`) than the OpenSpiel `GameInfo` metadata this plan touches, and fixing it would
require its own root-cause/test/review cycle. If Phase 4's T6 stress probe shows it is actually
reachable at a magnitude that threatens `min_utility=-50.0`, raise it as a new ledger finding at
Phase 6 rather than folding an engine-layer fix into this OpenSpiel-layer plan.
