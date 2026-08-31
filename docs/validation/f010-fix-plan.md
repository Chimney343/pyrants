# F-010 Fix Plan — Reproducible IS-MCTS Determinization

**Defect:** `docs/validation/findings.md` § F-010 (CRITICAL) — IS-MCTS determinization seeds
are drawn from an unseeded RNG, so `--seed` does not reproduce a run.

**Why this one first:** F-010 is the gating defect in `docs/validation/verdict.md` § 5. Until
runs reproduce, no fix to F-002, F-003, F-004, F-006 or F-011 can be *verified*, because there
is no way to tell a real improvement from run-to-run noise. Every other repair depends on this.

---

## 0. Mandatory process constraints

These three are requirements on *how* this work is done, not suggestions. A change that
satisfies the acceptance gates but skips any of them is not complete.

1. **Test-driven design is mandatory.** Every behavioural change in this plan starts as a
   failing test. Phase 2 must not begin until Phase 1's tests are written, executed, and
   observed to **fail for the stated reason** — a test that fails on an import error or a typo
   has not demonstrated the defect. No production line is edited before its test is red.
2. **This change will be reviewed.** Phase 5 is a required review gate, not a courtesy pass.
   The change does not merge on green tests alone.
3. **`docs/validation/verdict.md` must be updated.** Phase 6 rewrites the F-010 entry, the
   INV-1 row of the invariant battery table, and the § 5 GO/NO-GO conditions to reflect the
   post-fix state. A fix that lands without the verdict update leaves the audit record lying.

---

## 1. Root cause (verified, not assumed)

Two facts, both confirmed by reading the installed source this session:

- `.venv/Lib/site-packages/open_spiel/python/algorithms/ismcts.py:219-225`
  ```python
  def resample_from_infostate(self, state):
      if self._resampler_cb:
          return self._resampler_cb(state, state.current_player())
      else:
          return state.resample_from_infostate(
              state.current_player(), pyspiel.UniformProbabilitySampler(0., 1.))
  ```
  The fallback constructs a **fresh, unseeded** C++ sampler on every call and ignores the bot's
  own `self._random_state`.

- `openspiel_pyrants/state_c.py:307-321`
  ```python
  if hasattr(rng, 'shuffle'):        # numpy RandomState / Generator -> reproducible
      hi = rng.randint(0, 2**31 - 1); lo = rng.randint(0, 2**31 - 1)
      seed = (int(hi) << 31) | int(lo)
  elif callable(rng):                # UniformProbabilitySampler lands HERE
      seed = int(rng() * 2**63)
  else:
      seed = 0
  ```
  `UniformProbabilitySampler` is callable and has no `.shuffle`, so it takes the middle branch
  and every determinization seed comes from an unseeded global stream.

**Load-bearing detail for the fix:** `ismcts.py:234` exposes a public setter,
`set_resampler(cb)`, and the callback is invoked as `cb(state, player)`. No monkey-patching,
vendoring, or upstream fork is required.

---

## 2. Acceptance gates

From `verdict.md` § 5, condition 1, plus two guards this plan adds:

| Gate | Threshold |
|---|---|
| G1 Replay determinism | INV-1 passes at **N ≥ 100** seed-paired games |
| G2 World diversity preserved | INV-5 still shows **> 1 distinct world** per info set (mean ≥ 8 of K=12), 0 singleton info sets |
| G3 Seeds still separate runs | Different `--seed` values still produce different games at N ≥ 20 |
| G4 No silent regression path | An unseeded sampler cannot reach `determinize()` without raising |
| G5 Existing suites green | `just openspiel-test` and `just test` pass |

**G2 is the trap.** The naive over-fix — hardcoding a constant seed, or deriving the seed from
the state rather than from a stream — makes replay pass while collapsing every determinization
to a single world. That silently converts IS-MCTS into determinized UCT against one fixed world
and would be far worse than the current defect. G2 must be asserted, not assumed.

---

## 3. Phase 0 — Capture the red baseline

Record current behaviour before touching anything, so the review has a before/after pair.

```
.venv/Scripts/python.exe -u docs/validation/harness/inv_a.py        > docs/validation/baseline/inv_a.pre.txt
.venv/Scripts/python.exe -u docs/validation/harness/det_bot.py      > docs/validation/baseline/det_bot.pre.txt
.venv/Scripts/python.exe -u docs/validation/harness/inv_b.py        > docs/validation/baseline/inv_b.pre.txt
```

Expected content: `INV1 replay determinism: FAIL` on 10/10 seeds; fixed-root search returning
2–3 distinct actions across identically seeded bots; INV-5 mean distinct worlds ≈ 10.26/12.
That last number is the pre-fix value G2 must not regress from.

---

## 4. Phase 1 — RED: tests first

New file: `openspiel_pyrants/tests/test_ismcts_reproducibility.py`.

Write all seven, run them, and confirm the expected-fail set actually fails **for the right
reason** before writing any production code. Keep `num_sims` small (8–16) and games short so
the suite stays in CI budget.

| # | Test | Asserts | Pre-fix |
|---|---|---|---|
| T1 | `test_resample_with_random_state_is_deterministic` | Same `RandomState(123)` → identical determinized state fingerprint, 5 repeats | **PASS** (control — proves the good branch already works; guards against breaking it) |
| T2 | `test_unseeded_sampler_is_rejected` | `resample_from_infostate(p, pyspiel.UniformProbabilitySampler(0.,1.))` raises `TypeError` | **FAIL** |
| T3 | `test_search_reproducible_from_fixed_root` | Two identically seeded bots on one cloned root → identical chosen action *and* identical policy, 5 repeats | **FAIL** |
| T4 | `test_full_game_replay_is_deterministic` | Same seed, two full games → identical action sequence and identical `returns()`, 5 seeds | **FAIL** |
| T5 | `test_different_seeds_diverge` | Different seeds → different action sequences (anti-over-fix) | PASS before and after |
| T6 | `test_determinizations_remain_diverse` | Over one search, ≥ 8 distinct determinized worlds per info set out of 12 draws; 0 singletons | PASS before, **must stay passing** — this is gate G2 |
| T7 | `test_cli_run_is_reproducible` | `scripts.run_ismcts` twice, same `--seed`, into two temp dirs → identical `chosen_action_id` sequence in `decisions.jsonl` and identical `summary.csv` outcome column | **FAIL** |

T6 is the one that makes this plan safe. Write it before T2/T3/T4 so the diversity property is
locked in *before* the reproducibility work can compromise it.

T7 is the end-to-end test that matches how the tool is actually used, and it is the one that
would have caught F-010 originally.

---

## 5. Phase 2 — GREEN: minimal implementation

Two edits, in this order.

**5.1 A factory that always installs a seeded resampler.**
New: `openspiel_pyrants/ismcts_factory.py`

```python
def make_ismcts_bot(game, *, seed, num_sims, uct_c, max_world_samples,
                    final_policy_type, evaluator, resample_rng=None):
    """Build an ISMCTSBot whose world sampling is reproducible from `seed`."""
    rng = np.random.RandomState(seed)
    bot = ISMCTSBot(game=game, evaluator=evaluator, uct_c=uct_c,
                    max_simulations=num_sims, max_world_samples=max_world_samples,
                    random_state=rng, final_policy_type=final_policy_type)
    # The stock bot's fallback resampler uses an UNSEEDED pyspiel sampler (F-010).
    # Route world sampling through a seeded numpy stream instead.
    r_rng = resample_rng if resample_rng is not None else np.random.RandomState(seed ^ 0x5F10)
    bot.set_resampler(lambda state, player: state.resample_from_infostate(player, r_rng))
    return bot
```

*Design decision — a dedicated resampling stream.* `resample_rng` defaults to a **separate**
`RandomState` rather than reusing the bot's `random_state`. Sharing one stream with the
evaluator would make determinization seeds shift whenever anyone changes how many draws the
evaluator consumes, so an unrelated evaluator tweak would silently break replay of old runs.
A dedicated stream decouples them. Flag this to the reviewer — it is the one judgement call
in the fix, and the alternative (reuse `random_state`, fewer moving parts) is defensible.

**5.2 Route `scripts/run_ismcts.py` through the factory.**
Replace the inline `ISMCTSBot(...)` construction at `scripts/run_ismcts.py:386-399` with a
`make_ismcts_bot(...)` call, preserving the existing per-seat seed derivation
`seed + game_index * num_players + i`.

Run T1–T7. T2 will still fail — that is Phase 3's job.

---

## 6. Phase 3 — Guard against silent regression (G4)

Make the defective path unreachable rather than merely unused. In
`openspiel_pyrants/state_c.py:resample_from_infostate`, replace the `elif callable(rng)` branch:

```python
if hasattr(rng, 'shuffle'):
    ...  # unchanged, reproducible
raise TypeError(
    "resample_from_infostate requires a seeded numpy RandomState/Generator. "
    "A bare callable (e.g. pyspiel.UniformProbabilitySampler) makes the run "
    "irreproducible — see docs/validation/findings.md F-010. "
    "Build bots via openspiel_pyrants.make_ismcts_bot()."
)
```

**Known blast radius — all seven sites must be handled in this same change.**
`grep -rn "ISMCTSBot(" --include=*.py . | grep -v .venv` returns **seven** construction sites.
Every one builds a bare bot with no resampler, so every one currently reaches the fallback path
and **will start raising** under this guard:

| Site | Kind | Action |
|---|---|---|
| `scripts/run_ismcts.py:390` | production entry point | route through factory (§ 5.2) |
| `openspiel_pyrants/tests/test_ismcts_smoke_c.py:35` | test | switch to `make_ismcts_bot` |
| `openspiel_pyrants/tests/test_determinize_c.py:180` | test | switch to `make_ismcts_bot` |
| `openspiel_pyrants/tests/test_c_rollout_evaluator.py:67` | test | switch to `make_ismcts_bot` |
| `scripts/check_bot_keys.py:15` | dev/debug script | switch to `make_ismcts_bot` |
| `scripts/test_ismcts_minimal.py:21` | dev/debug script | switch to `make_ismcts_bot` |
| `scripts/trace_ismcts.py:15` | dev/debug script | switch to `make_ismcts_bot` |

Converting all seven is the correct outcome, not busywork — each becomes reproducible. But this
makes Phase 3 a wider change than Phase 2, so **budget for it**: if the three `scripts/*.py`
debug tools turn out to be dead, deleting them is an acceptable alternative to converting them,
decided at review rather than unilaterally.

*Sequencing note:* land § 5.2 (the `run_ismcts.py` conversion) and the test conversions
**before** enabling the guard, so the suite never goes simultaneously red on seven files. The
guard is the last edit in the change, not the first.

Verified as *not* affected: all six `resample_from_infostate` call sites in
`openspiel_pyrants/tests/test_resample_c.py` already pass `np.random.RandomState(123)`.

T2 now passes. Full suite should be green.

---

## 7. Phase 4 — Re-run the invariant battery against the gates

```
.venv/Scripts/python.exe -u docs/validation/harness/inv_a.py     # G1 — raise seed range to N>=100
.venv/Scripts/python.exe -u docs/validation/harness/inv_b.py     # G2 — distinct-world count
.venv/Scripts/python.exe -u docs/validation/harness/det_bot.py   # fixed-root reproducibility
just openspiel-test                                              # G5
just test                                                        # G5
```

`inv_a.py`'s INV-1 block currently runs 10 seeds; widen to ≥ 100 for G1 and save output to
`docs/validation/baseline/inv_a.post.txt`.

**Expected post-fix results** — write these down *before* running, and treat any mismatch as
an unresolved result rather than a pass:

- INV-1: PASS, 0 divergent seeds out of ≥ 100.
- INV-5: mean distinct worlds still ≈ 10/12, 0 singleton info sets. **A drop to 1.0 means the
  fix collapsed world sampling — stop and revert.**
- `det_bot.py` B1: exactly 1 distinct chosen action across 10 identically seeded searches.
- INV-2, INV-3, INV-4a, INV-6: unchanged (PASS).
- INV-7/8/9 win rates: *expected to shift numerically*, since the RNG stream changes. They must
  still satisfy their qualitative gates (monotone budget ladder, self-play ≈ 50%, random
  crushed) — but the specific percentages in `verdict.md` become stale and must be re-measured
  or explicitly marked superseded.

---

## 8. Phase 5 — Review (required gate)

Run `/code-review` on the branch diff, then a human pass against this checklist:

- [ ] Every production edit is traceable to a test that was red first (Phase 1 evidence attached).
- [ ] **G2 explicitly re-verified** — reviewer confirms world diversity did not collapse. This
      is the failure mode most likely to pass CI and still be wrong.
- [ ] The dedicated-`resample_rng` decision (§ 5.1) is accepted or consciously overridden.
- [ ] `test_ismcts_smoke_c.py` update is a genuine improvement, not a test weakened to pass.
- [ ] The `TypeError` message names F-010 and points to the factory.
- [ ] All seven `ISMCTSBot(` construction sites are converted or deleted
      (`grep -rn "ISMCTSBot(" --include=*.py . | grep -v .venv` — expect only `ismcts_factory.py`).
- [ ] Decision recorded on the three `scripts/*.py` debug tools: converted, or deleted as dead.
- [ ] Pre/post harness outputs are attached to the review.

---

## 9. Phase 6 — Update the audit record (required)

1. **`docs/validation/verdict.md`**
   - § 1 table: flip the INV-1 row to ✅ PASS with the new N and command.
   - § 2 CRITICAL: move F-010 out of the confirmed-defect list into a resolved section, with
     the fixing commit and the post-fix INV-1 evidence.
   - § 5: strike condition 1, promote conditions 2–5, and restate the GO/NO-GO. **The verdict
     stays NO-GO** — F-011, F-004, F-002/F-003 and F-006 are all still open; this fix only
     unblocks the ability to verify them.
   - Add a note that the § 1 win-rate figures predate the RNG change and are superseded.
2. **`docs/validation/findings.md`** — F-010 `Status:` becomes
   `**CONFIRMED — FIXED** (<commit sha>)`, keeping the original observed evidence intact so the
   audit trail survives.
3. Note in the F-002 entry that this fix **unmasks** it: hidden-zone draws now vary per
   simulation, which makes the shared `shuffle_seed`/`shuffle_counter` stream the next
   correctness limit on world sampling.

---

## 10. Risks

| Risk | Mitigation |
|---|---|
| Over-fix collapses world sampling to one world | T6 + G2, asserted before the fix is written |
| Fix works in the factory but a caller bypasses it | Phase 3 guard makes the bad path raise; review checklist greps for stray call sites |
| All historical `artifacts/ismcts/` runs become non-comparable | Expected and acceptable — they were never reproducible. State it in the verdict update |
| Evaluator changes later break replay of old runs | Dedicated `resample_rng` (§ 5.1) decouples the two streams |
| Upstream OpenSpiel changes `set_resampler` | Pinned dependency; T3/T4 fail loudly if the hook stops being honoured |

## 11. Out of scope

F-002, F-003, F-004, F-006, F-008, F-011 — each has its own verdict condition. Do not bundle.
The one permitted overlap is the documentation note in Phase 6.3 recording that F-002 is now
the binding constraint on world sampling.
