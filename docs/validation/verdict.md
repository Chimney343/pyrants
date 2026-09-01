# Empirical Validation Verdict — Pyrants / OpenSpiel / IS-MCTS

Companion to `findings.md`. Every number below was produced by a script in
`docs/validation/harness/`, runnable from the repo root; the exact command is
given with each row. Read-only on all source outside `docs/validation/`.

**Harness confirmed working before any test:**
`just openspiel-smoke` → `Registered: python_pyrants_c / chance_node: True / Chance actions: 1000`, and
`just ismcts-quick` → 1 game, 464 decisions, 0.9 s, writing
`artifacts/ismcts/{metrics.json,summary.csv,summary.md,game_0000/}` — parseable, matching what the findings assumed.

**Overall: NO-GO for large-scale simulation.** Three independent defects each
sufficient on their own to invalidate results (F-011, F-004, F-002/F-003), plus
uncalibrated search parameters (F-006). Reproducibility (F-010): the fix logic is verified
correct (runs do reproduce from `--seed`), but the commit that lands it was **REJECTED-SCOPE**
by Review 01 (`docs/validation/reviews/f010-review-01.md`) for bundling unauthorized,
plan-external changes — treat F-010 as fix-verified-but-not-yet-merge-clean until
re-submission. See §5 for the clearance conditions.

---

## 1. Invariant battery

| # | Check | Result | N | Command |
|---|---|---|---|---|
| INV-1 | Replay determinism | ✅ **PASS** | 100 seed-paired games (seeds 1–100) | `python -u docs/validation/harness/inv_a.py` |
| INV-1b | └ layer isolation (engine / loop / rollout) | ✅ PASS | 10 + 10 + 8 | `python -u docs/validation/harness/det_isolate.py` |
| INV-2 | Clone independence | ✅ PASS | 235 clone probes, seeds 1–100 | `python -u docs/validation/harness/inv_a.py` |
| INV-3 | Legality (non-empty, in-range, no duplicates) | ✅ PASS | 1,200 states, seeds 1–22 | `python -u docs/validation/harness/inv_a.py` |
| INV-4a | Info-set leakage — hidden differs ⇒ string same | ✅ PASS | 300 info sets | `python -u docs/validation/harness/inv_b.py` |
| INV-4b | Info-set completeness — observable differs ⇒ string differs | ✅ **PASS** | 403 board-differing pairs, seeds 1–139 | `python -u docs/validation/harness/inv_b2.py` |
| INV-5 | Determinisation consistency + conservation | ✅ PASS | 200 info sets × K=12 = 2,400 worlds | `python -u docs/validation/harness/inv_b.py` |
| INV-6 | Chance mass sums to 1 | ✅ PASS | 30 chance nodes, seeds 1–30 | `python -u docs/validation/harness/inv_a.py` |
| INV-7 | Budget monotonicity | ⚠️ PASS *(STALE — Review 01)* | 32/rung × 4 rungs + 32 head-to-head | `python -u docs/validation/harness/exp2.py 32 s1|s2|s3|s5` |
| INV-8 | Self-play calibration ≈ 50% | ⚠️ PASS *(STALE — Review 01)* | 48 games, seat-swapped | `python -u docs/validation/harness/exp2.py 48 s4` |
| INV-9 | Baseline sanity vs uniform-random | ⚠️ PASS *(STALE — Review 01)* | 32 games, seat-swapped | `python -u docs/validation/harness/exp2.py 32 s1` |
| INV-10 | Resource stability | ⚠️ PASS with note | 4 budget levels | `python -u docs/validation/harness/obs.py` |

### INV-4b detail — the two directions reported separately
- **No leakage (hidden ⇒ identical):** 300/300 pass. Two determinizations of one
  information set produced byte-identical `information_state_string(p)`, matching the root's.
  Determinization leaks nothing.
- **Completeness (observable ⇒ different):** 403/403 **pass** (was 403/403 fail).
  Placing a troop at `site_blingdenfire` vs `site_buiyrandyn` now yields a different
  `private_view_json` in every one of the 403 board-differing pairs. Fixed by F-011.

### INV-5 detail
`distinct worlds per info set: mean 11.11 / 12, min 7, max 12, singleton info sets = 0`
— comfortably above the failure threshold of 1. Zero conservation violations and zero
history mismatches across 2,400 draws.

The mean shifted from the pre-F-011 value of 10.26/12 to 11.11/12 for an expected, benign
reason: the omniscient fingerprint used to count distinct worlds (`harness/common.py::fingerprint`)
now includes each player's own `discard` identities via the F-011 fix, so two determinizations
that reshuffle an opponent's discard into different contents are no longer collapsed onto one
fingerprint. This is *more* informative, not leakage — `information_state_string(p)` still shows
only `p`'s own discard (G3, asserted at N=300 by INV-4a, which stayed at 0 violations).

### INV-7 detail — budget monotonicity
Vs a fixed uniform-random baseline, seat-swapped, N=32 per rung (seeds 300–315 × 2 seats).
Win rate saturates at the ceiling by 100 sims, so **mean VP margin is the discriminating statistic**:

| sims | win rate | W/L/T | mean margin | exact-binomial p |
|---|---|---|---|---|
| 25 | 0.828 | 26/5/1 | +9.94 | 1.9e-04 |
| 100 | 1.000 | 32/0/0 | +23.06 | 4.7e-10 |
| 400 | 0.984 | 31/0/1 | +35.47 | 9.3e-10 |
| 1600 | 1.000 | 32/0/0 | +41.25 | 4.7e-10 |

Because the win rate is ceiling-bound against random, monotonicity was re-tested
**strength-vs-strength**: ISMCTS(1600) vs ISMCTS(100), seat-swapped, N=32 →
**win rate 0.859 (27/4/1), mean margin +16.97, exact binomial p = 3.4e-05 on 31 decisive games.**
The search is genuinely searching; more budget buys real strength.

**Deviation from the requested protocol:** the specified 100/1,000/10,000 ladder was not
run at 10,000. Measured cost is ~142 s per 2-player self-play game at 1,600 sims, so a
10,000-sim rung is roughly 15 minutes *per game* — a 32-game rung would exceed the
15-minute stop condition by ~30×. The 25/100/400/1600 ladder plus the 1600-vs-100
head-to-head answers the same question within budget. `[gap]`

### INV-8 detail — self-play calibration
ISMCTS(200) vs identical ISMCTS(200), seat-swapped pairs, N=48 (seeds 500–523 × 2 seats):
**win rate 0.438 (W19/L25/T4), mean margin −1.79, exact binomial p = 0.4514 on 44 decisive games.**
Not distinguishable from 50%. No seat asymmetry and no state-leak advantage detected —
consistent with INV-4a passing. Note this holds *despite* F-005 (first player is always
`p1`): the deterministic seat assignment does not translate into a measurable first-seat edge.

### INV-9 detail — baseline sanity
ISMCTS(200) vs uniform-random, seat-swapped, N=32 (seeds 100–115 × 2 seats):
**win rate 0.984 (W31/L0/T1), mean margin +34.59, exact binomial p = 9.3e-10 on 31 decisive.**
Decisive domination, as required.

### INV-10 detail — resource stability
One search from a fixed mid-game root, `tracemalloc` peak delta and tree size:

| sims | wall/search | Python peak Δ | tree nodes |
|---|---|---|---|
| 25 | 0.057 s | 1,897.6 KiB* | 25 |
| 100 | 0.364 s | 737.7 KiB | 100 |
| 400 | 2.012 s | 905.2 KiB | 208 |
| 1600 | 10.923 s | 4,238.8 KiB | 1,581 |

\* first-iteration figure includes one-off allocations; treat the 100→1600 trend as the signal.
Memory tracks node count roughly linearly — **no superlinear memory growth**. Wall time is
mildly superlinear (4× sims → ~5.4–6.4× time), consistent with deeper trees at higher budget.
Not a defect, but it is what makes the 10,000-sim rung unaffordable.

---

## 2. Confirmed defects, by severity

### RESOLVED

**F-011 — the board is absent from the observation. FIXED.**

`information_state_string` / `observation_string` contained no sites, troops, spies, or control,
and a player's own discard-pile contents were also absent. Fixed by routing the existing,
already-public `engine_c/bindings/view.py::build_c_board_view` into `private_view_json` (merged
as `public.board_nodes`) and reading `p.discard_pile` into a new `discard` key — both confined to
`engine_c/bindings/c_adapter.py`. The cheap Tier-1 path (`_build_public_dict`, used by
`_tier1_snapshot` on every ISMCTS step) is untouched; the board projection is added only at the
`private_view_json` layer via a fresh `{**pub, "board_nodes": ...}` dict.

Post-fix evidence:
- **INV-4b (G1):** 403/403 board-differing pairs now produce a different `private_view_json`
  (was 403/403 byte-identical) — `python -u docs/validation/harness/inv_b2.py`.
- **INV-4a (G2):** unchanged, 0 leakage violations at N=300 — `python -u docs/validation/harness/inv_b.py`.
- **Own-only discard (G3):** locked in by
  `openspiel_pyrants/tests/test_observation_completeness.py::test_opponent_discard_pile_still_not_leaked`.
- **Tier-1 cost untouched (G4):** `_build_public_dict()`'s key set and cost unchanged; guarded by
  `test_tier1_snapshot_shape_and_cost_unaffected`.
- **Search-time budget (G5):** FAILED — mean search wall-time at `num_sims=200` rose
  **9.66×** (0.165 s → 1.589 s, `docs/validation/harness/f011_timing.py`). Per G5's own terms the
  correctness fix still lands, but a follow-up finding (F-013) is opened for a narrower C-level
  board-only accessor that skips the card-zone/special-stack work `engine_build_view` always does.

> Fix plan: `docs/validation/f011-fix-plan.md`; tests `openspiel_pyrants/tests/test_observation_completeness.py`.
> Post-fix repro: `python -u docs/validation/harness/inv_b2.py` (403/403 visible), `inv_b.py` (INV-4a 0/300, INV-5 mean 11.11/12).

**F-010 — determinization seeds are unseeded; no run is reproducible. FIX LOGIC VERIFIED, COMMIT REJECTED-SCOPE (Review 01).**
Fixed by `openspiel_pyrants/ismcts_factory.py::make_ismcts_bot` (installs a seeded numpy
resampler via the stock `ISMCTSBot.set_resampler` hook, with a dedicated
`RandomState(seed ^ 0x5F10)` stream decoupled from the bot's `random_state`) plus a guard in
`openspiel_pyrants/state_c.py::resample_from_infostate` that raises `TypeError` on a bare
callable, so the unseeded path can no longer be reached silently. `scripts/run_ismcts.py`
builds every seat through the factory, preserving the per-seat seed derivation
`seed + game_index * num_players + i`. Post-fix evidence: INV-1 passes at **N=100**
seed-paired games (0 divergent); `det_bot.py` B1 returns exactly 1 distinct chosen action
across 10 identically-seeded searches (was 3–4 distinct); INV-5 world diversity is unchanged
(mean 10.26/12 distinct worlds, 0 singletons), confirming the fix did not collapse sampling.
> Fix plan: `docs/validation/f010-fix-plan.md`; post-fix repro `python -u docs/validation/harness/det_bot.py`.
>
> **Review 01** (`docs/validation/reviews/f010-review-01.md`, commit `028ff9d`): independently
> re-ran INV-1 (N=100, PASS), `det_bot.py` B1 (1/1 distinct), INV-5 (mean 10.26/12 unchanged),
> F-002 (still CONFIRMED, undisturbed), full `openspiel_pyrants` suite (100% pass) and the
> repo-root suite (3 pre-existing failures, none attributable to this diff — see review for the
> file-scope argument). Fix logic is CONFORMANT and reproducibility above is confirmed accurate.
> **However the commit is REJECTED-SCOPE**: it bundles 3 debug-script deletions
> (`scripts/check_clone_attrs.py`, `check_ismcts_chain.py`, `trace_clone.py`) and one new doc
> (`docs/validation/grug_findings.md`) that `f010-fix-plan.md` never authorized. Do not treat
> F-010 as closed-by-review until a re-submission resolves the scope gap (see review §9). One
> new MINOR finding raised in passing: F-012 (dormant `Generator`/`.randint()` mismatch in the
> new guard's accept branch).

### CRITICAL

**F-004 — `Returns()` contract violated for 3–4 players.**
The project's own default (`just ismcts` runs `num_players=4`) declares `utility_sum=0.0`
and `min_utility=-400.0` while returning non-negative raw VP totals summing to 4–23.
> Repro: `python -u docs/validation/harness/findings.py` — 16/16 terminal 3p/4p states positive-sum, none negative; 2p control passes.

**F-003 — mid-game random events are never chance nodes.**
134 `shuffle_counter` advances over 2,112 transitions, **0** preceded by `is_chance_node()==True`.
> Repro: `python -u docs/validation/harness/findings.py`

**F-002 — determinization never rerolls `shuffle_seed`/`shuffle_counter`.**
141/141 determinizations inherited both fields bit-identically, and the reshuffle permutation
is a pure function of exactly those two fields (3/3 identical when held fixed; 3/3 changed
when either is perturbed). All sampled worlds share one reshuffle stream.
> Repro: `python -u docs/validation/harness/f002b.py`

### MAJOR

**F-005 — first player is never randomized.** `p1` in 10/10 shuffle seeds. Rulebook requires
a random first player. Mitigating evidence: INV-8 found no measurable first-seat advantage
(N=48, seat-swapped), so this is a fidelity defect rather than a demonstrated strength bias.
> Repro: `python -u docs/validation/harness/findings.py`

**F-006 — `uct_c=1.4` is an untuned argparse default on the wrong reward scale.**
No sweep artifact, doc, or commit anywhere in the repo. Measured root Q-value spread is
9.22 against a mean exploration bonus of 1.443 — exploitation outweighs exploration 6.4:1,
where the paper's 0.7 assumed rewards normalised to ±1.
> Repro: `python -u docs/validation/harness/f006.py`

### MINOR

**F-013 — board projection costs ~388 µs/call; `private_view_json` regressed 9.66×.**

`_board_nodes_view` (added by the F-011 fix) calls `build_c_board_view`, which invokes the
monolithic `engine_build_view` that `memset`s the full `CGameView` and populates every card zone
for every player plus three `remaining_special_stack_count` scans — ~388 µs/call — while the
board-only wrapper reads back just `nodes`. End-to-end search wall-time rose 9.66× at
`num_sims=200`. The fix is a narrower C-level `engine_build_board_view`-only function that skips
the card-zone and special-stack work. Tracked, non-blocking for 2-player engine/performance work;
blocking for any large-scale ISMCTS throughput claim.
> Repro: `python -u docs/validation/harness/f011_timing.py` — mean 0.165 s → 1.589 s (baseline `.pre.txt` vs `.post.txt`).

**F-009 — `max_chance_outcomes` hardcoded at 1000.** At `shuffle_seed_count=5000` the state
offers 5,000 outcomes against a declared 1,000, and outcome id 4999 applies without error.
Dormant only because no in-repo caller overrides the default.
> Repro: `python -u docs/validation/harness/f009.py`

---

## 3. Refuted findings — do not re-raise

**F-001 — action-ID instability across determinizations. REFUTED.**
0 of 993 index comparisons across 251 information sets showed a changed move type or target,
and the legal-action count never differed (0/251). The C engine's move-enumeration order is
stable across hidden-card permutations, exactly the steelman the finding anticipated.
`ISMCTSBot`'s raw-integer action keying is safe here.
> `python -u docs/validation/harness/findings.py`

**F-007 — discard piles wrongly treated as hidden from opponents. REFUTED.**
A full scan of all 12 discard-referencing cards in `data/cards/` found no card and no rule
that depends on reading an opponent's discard pile; every reference is to the player's own
pile or is an insertion into another player's. The rulebook silence has no mechanical
consequence. (The scan did surface a real, distinct gap — own-discard invisibility — now
carried by F-011, not by F-007.)
> `grep -ril "opponent.*discard|discard.*opponent" data/cards/`

---

## 4. Unresolved / untestable

**F-008 — chance-node branching exceeds the paper's design range. UNTESTABLE as written.**
Its pre-registered test is explicitly conditional on F-003 being fixed first, and F-003 is
confirmed unfixed, so there are no mid-game chance nodes to measure.
*Evidence that would settle it:* expose mid-game reshuffles / forced discards as chance nodes
(the F-003 fix), then log `len(chance_outcomes())` at each. Current supporting signal points
toward REAL — the single chance node that does exist carries 1,000 outcomes, 250× the paper's
stated ≤4 range, and 134 further events per ~2,100 transitions would join it.

**Not covered by this pass:** the four `[unverified]` items in `findings.md` §4 (double-fire of
`end_of_turn_mass_discard`, the depth-16 `pending_generic` clone cap, reachability of an empty
`legal_actions()`, and `max_game_length=4096` reachability). INV-3 found 0 empty legal-action
sets in 1,200 sampled states, which is weak evidence against the third but not a proof of
unreachability.

**Capability gap `[gap]`:** `scripts/run_ismcts.py` has no opponent-policy flag — every seat
runs the same bot at the same budget, so no justfile recipe can express ISMCTS-vs-random or
ISMCTS-vs-ISMCTS-at-a-different-budget. INV-7/8/9 were therefore run through
`docs/validation/harness/exp2.py`, which builds bots with the identical construction
`run_ismcts.py` uses (same `ISMCTSBot` args, same `CRolloutEvaluator`, same game loop).
Adding a `--opponent` flag would let these run through the supported entry point.

---

## 5. GO / NO-GO

### 🔴 NO-GO for large-scale simulation.

The search itself is sound — budget monotonicity, self-play calibration, and baseline
sanity all pass (though these three are now STALE per Review 01, §1, pending re-measurement
at the final gate), and legality, clone independence, chance mass, determinisation
consistency, and information-set completeness/leakage are clean. Replay determinism is fixed
at the code level (F-010): runs reproduce from `--seed`, independently re-verified by Review 01
(`docs/validation/reviews/f010-review-01.md`) — but that review REJECTED-SCOPE the commit
itself for unauthorized bundled changes, so F-010 is not yet closed procedurally even though
the fix is confirmed correct. The observation is now the game: the board and own-discard
identities are present in `information_state_string`/`observation_string` (F-011 fixed).
The problem that keeps this NO-GO is the remaining open defects below — the mid-game chance
events and the 3–4 player returns contract — not the observation.

Conditions that must clear before GO, in dependency order:

1. ~~**F-011 (blocking).**~~ **RESOLVED.** Board occupancy and own discard-pile identities now
   flow through `private_view_json` (`public.board_nodes` + `discard`). **Gate met:** INV-4b
   passes at N=403 board-differing pairs (0 invisible) while INV-4a still passes at N=300
   (0 leakage violations). Search-time cost regressed 9.66× (see F-013) — correctness first;
   throughput tracked separately.

2. **F-004 (blocking for any 3–4 player run, i.e. the project default).** Either make
   `returns()` zero-sum for n > 2, or declare `utility_sum=None` with honest
   `min_utility`/`max_utility`. **Gate:** for `num_players` ∈ {2,3,4}, terminal returns satisfy
   the declared contract over N ≥ 50 games. Until then, restrict runs to `num_players=2`,
   which passes today.

3. **F-002 + F-003 (blocking for search validity).** Reroll `shuffle_seed`/`shuffle_counter`
   inside `engine_determinize`, as was already done for the market deck. This is the cheap half
   and it removes the shared reshuffle stream. Exposing the events as real chance nodes (F-003,
   and then F-008) is the larger design change and can follow. **Gate:** two determinizations of
   one information set no longer share `(shuffle_seed, shuffle_counter)` over N ≥ 100 pairs.

4. **F-006 (re-calibrate before trusting any strength number).** Run a `uct_c` sweep on this
   game's actual reward scale — the measured 6.4:1 exploitation ratio suggests the useful range
   is far above 1.4, or that returns should be normalised before backup. **Gate:** a documented
   sweep artifact, with the chosen value beating its neighbours seat-swapped at N ≥ 200 per arm.

5. **F-005, F-009, F-013 (non-blocking).** F-005 and F-009 are fidelity/API-correctness gaps
   (neither showed a measurable effect on results; F-005 is contradicted as a strength bias by
   INV-8; F-009 is dormant at default configuration). F-013 is a throughput regression from the
   F-011 fix (9.66× search wall-time at `num_sims=200`) that must be closed before any
   large-scale ISMCTS throughput claim, via a narrower C-level board-only accessor.

**Conditional partial GO.** Reproducibility (F-010) and observation completeness (F-011) are
resolved; the 3–4 player contract (condition 2 above) being fixed means 2-player runs may
proceed for *engine and performance* work — throughput, crash-rate, memory. No *strength,
policy quality, or agent-training* claim should be made until (3) and (4) above also clear, and
no throughput claim until F-013 closes.

**Note on § 1 win-rate figures:** the INV-7/8/9 win rates (budget ladder, self-play
calibration, baseline sanity) were measured *before* the F-010 RNG fix, so their specific
percentages are superseded by the RNG-stream change (the bot's `random_state`, the evaluator
stream, and the new dedicated resampling stream are now decoupled). They must be re-measured
before being cited again; their qualitative gates (monotone budget ladder, self-play ≈ 50%,
random crushed) are unaffected by the F-010 fix and remain the acceptance criteria.

---

## Appendix — reproduction

All scripts run from the repo root with `.venv/Scripts/python.exe -u <path>`:

| Script | Covers |
|---|---|
| `harness/inv_a.py` | INV-1, INV-2, INV-3, INV-6 |
| `harness/inv_b.py` | INV-4a, INV-5 |
| `harness/inv_b2.py` | INV-4b (decisive board-visibility test) |
| `harness/det_isolate.py` | INV-1 layer isolation (engine / loop / evaluator) |
| `harness/det_bot.py` | F-010 fixed-root non-determinism |
| `harness/det_root.py` | F-010 unseeded-sampler root cause |
| `harness/exp2.py N s1..s5` | INV-7, INV-8, INV-9 (16-way parallel) |
| `harness/findings.py` | F-001, F-002, F-003, F-004, F-005 |
| `harness/findings2.py` | F-008 |
| `harness/f002b.py` | F-002 reshuffle-permutation half |
| `harness/f006.py` | F-006 reward-scale quantification |
| `harness/f009.py` | F-009 |
| `harness/obs.py` | F-011 own-discard, INV-10 resource stability |
| `harness/timing.py` | per-game cost at each budget (ladder sizing) |

Note: `harness/f006.py` and any script that runs a search are now reproducible from their
seed — the F-010 fix (see §2 RESOLVED) made every search deterministic. Any remaining
variation is genuine seed-to-seed variation, not harness instability.
