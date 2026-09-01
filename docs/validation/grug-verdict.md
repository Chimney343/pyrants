# Grug Verdict — Pyrants / OpenSpiel / IS-MCTS (grug happy edition)

grug read `findings.md` friend. all numbers below come from scripts in `docs/validation/harness/`, run from repo root. grug put exact command with each row. read-only on all source outside `docs/validation/` — grug not touch other code, grug good.

**harness work before grug test anything:**
`just openspiel-smoke` → `Registered: python_pyrants_c / chance_node: True / Chance actions: 1000`, and
`just ismcts-quick` → 1 game, 464 decisions, 0.9 s, writing
`artifacts/ismcts/{metrics.json,summary.csv,summary.md,game_0000/}` — parseable, match what findings assume. grug happy, harness alive.

**Overall: grug say NO-GO for big simulate.** three bugs each bad enough alone to break results (F-011, F-004, F-002/F-003), plus un-tuned search knobs (F-006). reproducibility (F-010): fix logic grug-verified correct (runs reproduce from `--seed`), but commit that land it got **REJECTED-SCOPE** by Review 01 (`docs/validation/reviews/f010-review-01.md`) for bundling sneaky extra changes not in plan — grug treat F-010 as fix-verified-but-not-yet-merge-clean until re-submit. see §5 for what must clear first.

---

## 1. Invariant battery (grug checks)

| # | check | result | N | command |
|---|---|---|---|---|
| INV-1 | replay determinism | ✅ **PASS** | 100 seed-paired games (seeds 1–100) | `python -u docs/validation/harness/inv_a.py` |
| INV-1b | └ layer isolation (engine / loop / rollout) | ✅ PASS | 10 + 10 + 8 | `python -u docs/validation/harness/det_isolate.py` |
| INV-2 | clone independence | ✅ PASS | 235 clone probes, seeds 1–100 | `python -u docs/validation/harness/inv_a.py` |
| INV-3 | legality (non-empty, in-range, no duplicates) | ✅ PASS | 1,200 states, seeds 1–22 | `python -u docs/validation/harness/inv_a.py` |
| INV-4a | info-set leakage — hidden differs ⇒ string same | ✅ PASS | 300 info sets | `python -u docs/validation/harness/inv_b.py` |
| INV-4b | info-set completeness — observable differs ⇒ string differs | ✅ **PASS** | 403 board-differing pairs, seeds 1–139 | `python -u docs/validation/harness/inv_b2.py` |
| INV-5 | determinisation consistency + conservation | ✅ PASS | 200 info sets × K=12 = 2,400 worlds | `python -u docs/validation/harness/inv_b.py` |
| INV-6 | chance mass sums to 1 | ✅ PASS | 30 chance nodes, seeds 1–30 | `python -u docs/validation/harness/inv_a.py` |
| INV-7 | budget monotonicity | ⚠️ PASS *(STALE — Review 01)* | 32/rung × 4 rungs + 32 head-to-head | `python -u docs/validation/harness/exp2.py 32 s1|s2|s3|s5` |
| INV-8 | self-play calibration ≈ 50% | ⚠️ PASS *(STALE — Review 01)* | 48 games, seat-swapped | `python -u docs/validation/harness/exp2.py 48 s4` |
| INV-9 | baseline sanity vs uniform-random | ⚠️ PASS *(STALE — Review 01)* | 32 games, seat-swapped | `python -u docs/validation/harness/exp2.py 32 s1` |
| INV-10 | resource stability | ⚠️ PASS with note | 4 budget levels | `python -u docs/validation/harness/obs.py` |

### INV-4b detail — two directions grug report separately
- **no leakage (hidden ⇒ identical):** 300/300 pass. two determinizations of one info set produce byte-identical `information_state_string(p)`, match root's. determinization leak nothing. grug nod head.
- **completeness (observable ⇒ different):** 403/403 **pass** (was 403/403 fail). placing troop at `site_blingdenfire` vs `site_buiyrandyn` now yield different `private_view_json` in every one of 403 board-differing pairs. F-011 fix this. grug happy.

### INV-5 detail
`distinct worlds per info set: mean 11.11 / 12, min 7, max 12, singleton info sets = 0`
— comfortably above failure threshold of 1. zero conservation violations, zero history mismatches across 2,400 draws. grug like this number.

mean shift from pre-F-011 value 10.26/12 to 11.11/12 for expected, benign reason: omniscient fingerprint used to count distinct worlds (`harness/common.py::fingerprint`) now include each player's own `discard` identities via F-011 fix, so two determinizations that reshuffle opponent's discard into different contents no longer collapse onto one fingerprint. this *more* informative, not leakage — `information_state_string(p)` still show only `p`'s own discard (G3, asserted at N=300 by INV-4a, which stay at 0 violations). grug not worry.

### INV-7 detail — budget monotonicity
vs fixed uniform-random baseline, seat-swapped, N=32 per rung (seeds 300–315 × 2 seats). win rate saturate at ceiling by 100 sims, so **mean VP margin is discriminating statistic**:

| sims | win rate | W/L/T | mean margin | exact-binomial p |
|---|---|---|---|---|
| 25 | 0.828 | 26/5/1 | +9.94 | 1.9e-04 |
| 100 | 1.000 | 32/0/0 | +23.06 | 4.7e-10 |
| 400 | 0.984 | 31/0/1 | +35.47 | 9.3e-10 |
| 1600 | 1.000 | 32/0/0 | +41.25 | 4.7e-10 |

because win rate ceiling-bound against random, monotonicity re-tested **strength-vs-strength**: ISMCTS(1600) vs ISMCTS(100), seat-swapped, N=32 →
**win rate 0.859 (27/4/1), mean margin +16.97, exact binomial p = 3.4e-05 on 31 decisive games.**
search genuinely searching; more budget buy real strength. grug approve.

**deviation from requested protocol:** specified 100/1,000/10,000 ladder not run at 10,000. measured cost ~142 s per 2-player self-play game at 1,600 sims, so 10,000-sim rung roughly 15 minutes *per game* — 32-game rung would exceed 15-minute stop condition by ~30×. 25/100/400/1600 ladder plus 1600-vs-100 head-to-head answer same question within budget. `[gap]`

### INV-8 detail — self-play calibration
ISMCTS(200) vs identical ISMCTS(200), seat-swapped pairs, N=48 (seeds 500–523 × 2 seats):
**win rate 0.438 (W19/L25/T4), mean margin −1.79, exact binomial p = 0.4514 on 44 decisive games.**
not distinguishable from 50%. no seat asymmetry, no state-leak advantage detected — consistent with INV-4a passing. note this hold *despite* F-005 (first player always `p1`): deterministic seat assignment not translate into measurable first-seat edge. grug relieved.

### INV-9 detail — baseline sanity
ISMCTS(200) vs uniform-random, seat-swapped, N=32 (seeds 100–115 × 2 seats):
**win rate 0.984 (W31/L0/T1), mean margin +34.59, exact binomial p = 9.3e-10 on 31 decisive.**
decisive domination, as required. grug happy, search crush random.

### INV-10 detail — resource stability
one search from fixed mid-game root, `tracemalloc` peak delta and tree size:

| sims | wall/search | Python peak Δ | tree nodes |
|---|---|---|---|
| 25 | 0.057 s | 1,897.6 KiB* | 25 |
| 100 | 0.364 s | 737.7 KiB | 100 |
| 400 | 2.012 s | 905.2 KiB | 208 |
| 1600 | 10.923 s | 4,238.8 KiB | 1,581 |

\* first-iteration figure include one-off allocations; treat 100→1600 trend as signal. memory track node count roughly linearly — **no superlinear memory growth**. wall time mildly superlinear (4× sims → ~5.4–6.4× time), consistent with deeper trees at higher budget. not defect, but this what make 10,000-sim rung unaffordable. grug accept.

---

## 2. Confirmed defects, by severity (grug bug list)

### RESOLVED (grug fix these — grug happy)

**F-011 — board absent from observation. FIXED.**

`information_state_string` / `observation_string` contain no sites, troops, spies, or control, and player's own discard-pile contents also absent. fixed by routing existing, already-public `engine_c/bindings/view.py::build_c_board_view` into `private_view_json` (merged as `public.board_nodes`) and reading `p.discard_pile` into new `discard` key — both confined to `engine_c/bindings/c_adapter.py`. cheap Tier-1 path (`_build_public_dict`, used by `_tier1_snapshot` on every ISMCTS step) untouched; board projection added only at `private_view_json` layer via fresh `{**pub, "board_nodes": ...}` dict. grug like this — narrow change, complexity demon trapped in crystal.

post-fix evidence:
- **INV-4b (G1):** 403/403 board-differing pairs now produce different `private_view_json` (was 403/403 byte-identical) — `python -u docs/validation/harness/inv_b2.py`.
- **INV-4a (G2):** unchanged, 0 leakage violations at N=300 — `python -u docs/validation/harness/inv_b.py`.
- **own-only discard (G3):** locked in by
  `openspiel_pyrants/tests/test_observation_completeness.py::test_opponent_discard_pile_still_not_leaked`.
- **Tier-1 cost untouched (G4):** `_build_public_dict()`'s key set and cost unchanged; guarded by
  `test_tier1_snapshot_shape_and_cost_unaffected`.
- **search-time budget (G5):** FAILED — mean search wall-time at `num_sims=200` rose
  **9.66×** (0.165 s → 1.589 s, `docs/validation/harness/f011_timing.py`). per G5's own terms correctness fix still land, but follow-up finding (F-013) opened for narrower C-level board-only accessor that skip card-zone/special-stack work `engine_build_view` always do. grug frown at cost, but correctness first.

> fix plan: `docs/validation/f011-fix-plan.md`; tests `openspiel_pyrants/tests/test_observation_completeness.py`.
> post-fix repro: `python -u docs/validation/harness/inv_b2.py` (403/403 visible), `inv_b.py` (INV-4a 0/300, INV-5 mean 11.11/12).
>
> **Review 01** (`docs/validation/reviews/f011-review-01.md`, commit `a7cee83`): **ACCEPTED-WITH-DEBT**
> (F-013 open). independently re-ran falsification test (403/403 now visible), INV-4a
> (0/300 violations), INV-5 (mean 11.11/12, 0 singletons), always-on battery (INV-1/2/3/6,
> all PASS), F-010's `det_bot.py` regression check (unchanged, 1 distinct chosen action —
> larger observation string not disturb F-010's reproducibility guarantee), new 8-test
> suite (8/8 pass), full repo suite (same 3 pre-existing `engine_c`/catalog failures as
> `f010-review-01.md`, zero new failures). zero out-of-scope hunks — unlike F-010's `028ff9d`,
> this commit bundle nothing beyond plan's authorized scope. G5's 9.66× regression
> independently re-measured at 9.655×, confirming F-013 (still `OPEN`) rather than raise new
> finding.

**F-010 — determinization seeds unseeded; no run reproducible. FIX LOGIC VERIFIED, COMMIT REJECTED-SCOPE (Review 01).**
fixed by `openspiel_pyrants/ismcts_factory.py::make_ismcts_bot` (installs seeded numpy resampler via stock `ISMCTSBot.set_resampler` hook, with dedicated `RandomState(seed ^ 0x5F10)` stream decoupled from bot's `random_state`) plus guard in `openspiel_pyrants/state_c.py::resample_from_infostate` that raise `TypeError` on bare callable, so unseeded path can no longer be reached silently. `scripts/run_ismcts.py` build every seat through factory, preserving per-seat seed derivation `seed + game_index * num_players + i`. post-fix evidence: INV-1 pass at **N=100** seed-paired games (0 divergent); `det_bot.py` B1 return exactly 1 distinct chosen action across 10 identically-seeded searches (was 3–4 distinct); INV-5 world diversity unchanged (mean 10.26/12 distinct worlds, 0 singletons), confirming fix did not collapse sampling.
> fix plan: `docs/validation/f010-fix-plan.md`; post-fix repro `python -u docs/validation/harness/det_bot.py`.
>
> **Review 01** (`docs/validation/reviews/f010-review-01.md`, commit `028ff9d`): independently
> re-ran INV-1 (N=100, PASS), `det_bot.py` B1 (1/1 distinct), INV-5 (mean 10.26/12 unchanged),
> F-002 (still CONFIRMED, undisturbed), full `openspiel_pyrants` suite (100% pass) and
> repo-root suite (3 pre-existing failures, none attributable to this diff — see review for
> file-scope argument). fix logic CONFORMANT and reproducibility above confirmed accurate.
> **however commit REJECTED-SCOPE**: it bundle 3 debug-script deletions
> (`scripts/check_clone_attrs.py`, `check_ismcts_chain.py`, `trace_clone.py`) and one new doc
> (`docs/validation/grug_findings.md`) that `f010-fix-plan.md` never authorize. grug say do not treat
> F-010 as closed-by-review until re-submission resolve scope gap (see review §9). one
> new MINOR finding raised in passing: F-012 (dormant `Generator`/`.randint()` mismatch in
> new guard's accept branch).

### CRITICAL (grug reach for club)

**F-004 — `Returns()` contract violated for 3–4 players. FIXED.**
project's own default (`just ismcts` run `num_players=4`) declare `utility_sum=0.0` and `min_utility=-400.0` while returning non-negative raw VP totals summing to 4–23. fixed by `openspiel_pyrants/game_c.py::_build_c_game_info`: `n==2` byte-identical to pre-fix (`utility_sum=0.0`, `min_utility=-200.0`, `max_utility=200.0`, `ZERO_SUM` — its `returns()` genuine zero-sum margin); `n>2` now declare honest general-sum contract (`utility_sum=None`, `min_utility=-50.0`, `max_utility=400.0`, `GENERAL_SUM`). `returns()` itself untouched — this metadata correction, not reward-computation change.
> fix plan: `docs/validation/f004-fix-plan.md`; tests `openspiel_pyrants/tests/test_utility_contract.py`.
> post-fix evidence (G1–G6): `n==2` unchanged (G1); `n∈{3,4}` honest declaration (G2); N=50
> terminal random-policy games per player count, 0 out-of-bounds returns, `n==2` zero-sums 50/50
> (G3); stress probe (T6) worst return −23.0 (2p, within −200) / 0.0 (3p/4p, within −50) over
> N=200 greedy-play games per count (G4); zero production consumers of three fields (G5);
> `openspiel_pyrants` suite 70/70 pass and full repo `pytest` show same 3 pre-existing
> `engine_c`/catalog failures (Zuggtmoy, Air Elemental, Neogi), zero new (G6). T6
> direct-injection probe confirm −50 floor practical (not formally tight) —
> engine's uncapped `give_insane_outcast` issuance filed separately as **F-014** (MAJOR, OPEN).
> repro: `python -u docs/validation/harness/f004_utility.py`.
>
> **Review 01** (`docs/validation/reviews/f004-review-01.md`, working tree at base `b0f3173`):
> **ACCEPTED-WITH-DEBT** (F-014 open). independently re-ran falsification test (declared
> contract now numerically consistent with observed N=8 returns), 8-test suite (8/8 pass),
> G5's zero-production-consumer grep (confirmed, repo-wide), T5/T6 (byte-identical to
> `baseline/f004_utility.post.txt`), always-on battery (INV-1/2/3/6, all PASS), full
> repo suite (same 3 pre-existing `engine_c`/catalog failures as `f010`/`f011-review-01.md`, zero
> new). zero out-of-scope hunks. also independently corrected factual error in fix plan's own
> supporting evidence (claimed "zero matches" grep against installed `open_spiel` package was
> actually 182 matches) without disturbing plan's underlying conclusion, which hold for
> narrower, correct reason that `ISMCTSBot` itself (`ismcts.py`) has zero matches.

**F-003 — mid-game random events never chance nodes.**
134 `shuffle_counter` advances over 2,112 transitions, **0** preceded by `is_chance_node()==True`. grug scratch head — where chance nodes go?
> repro: `python -u docs/validation/harness/findings.py`

**F-002 — determinization never reroll `shuffle_seed`/`shuffle_counter`.**
141/141 determinizations inherit both fields byte-identically, and reshuffle permutation pure function of exactly those two fields (3/3 identical when held fixed; 3/3 changed when either perturbed). all sampled worlds share one reshuffle stream. grug not like — all worlds same, search blind.
> repro: `python -u docs/validation/harness/f002b.py`

### MAJOR (grug frown)

**F-005 — first player never randomized.** `p1` in 10/10 shuffle seeds. rulebook require random first player. mitigating evidence: INV-8 find no measurable first-seat advantage (N=48, seat-swapped), so this fidelity defect rather than demonstrated strength bias.
> repro: `python -u docs/validation/harness/findings.py`

**F-006 — `uct_c=1.4` untuned argparse default on wrong reward scale.**
no sweep artifact, doc, or commit anywhere in repo. measured root Q-value spread 9.22 against mean exploration bonus 1.443 — exploitation outweigh exploration 6.4:1, where paper's 0.7 assume rewards normalised to ±1. grug say knobs not tuned — big brain guess number, not measure.
> repro: `python -u docs/validation/harness/f006.py`

### MINOR (grug note, fix later)

**F-014 — `give_insane_outcast` mint without 30-copy cap; `min_utility=-50.0` practical, not tight.**

`engine_c/actions.c:698-705` append fresh `insane_outcast` copies to target's discard pile without consulting `remaining_special_stack_count` or `stack_total=30` cap (`engine_c/helpers.c:266`). direct injection drove `compute_final_scores` to −30 at 30-copy design intent and −80 at `MAX_ZONE_SIZE` (80) hard cap, so F-004 floor labeled-practical bound, not formal one. random greedy play never approach it (worst −23.0 over N=200 games). root cause C rules-correctness question in `engine_c/`, out of scope for F-004 `GameInfo` metadata fix; tracked here per `docs/validation/f004-fix-plan.md` § 11.
> repro: `python -u docs/validation/harness/f004_utility.py` (section T6, "direct injection upper bound").

**F-013 — board projection cost ~388 µs/call; `private_view_json` regress 9.66×.**

`_board_nodes_view` (added by F-011 fix) call `build_c_board_view`, which invoke monolithic `engine_build_view` that `memset` full `CGameView` and populate every card zone for every player plus three `remaining_special_stack_count` scans — ~388 µs/call — while board-only wrapper read back just `nodes`. end-to-end search wall-time rose 9.66× at `num_sims=200`. fix is narrower C-level `engine_build_board_view`-only function that skip card-zone and special-stack work. tracked, non-blocking for 2-player engine/performance work; blocking for any large-scale ISMCTS throughput claim. grug want narrow accessor — trap complexity demon in crystal, not spread across all zones.
> repro: `python -u docs/validation/harness/f011_timing.py` — mean 0.165 s → 1.589 s (baseline `.pre.txt` vs `.post.txt`).

**F-009 — `max_chance_outcomes` hardcoded at 1000.** at `shuffle_seed_count=5000` state offer 5,000 outcomes against declared 1,000, and outcome id 4999 apply without error. dormant only because no in-repo caller override default.
> repro: `python -u docs/validation/harness/f009.py`

---

## 3. Refuted findings — grug say do not re-raise

**F-001 — action-ID instability across determinizations. REFUTED.**
0 of 993 index comparisons across 251 info sets show changed move type or target, and legal-action count never differ (0/251). C engine's move-enumeration order stable across hidden-card permutations, exactly steelman finding anticipate. `ISMCTSBot`'s raw-integer action keying safe here. grug nod — this not bug.
> `python -u docs/validation/harness/findings.py`

**F-007 — discard piles wrongly treated as hidden from opponents. REFUTED.**
full scan of all 12 discard-referencing cards in `data/cards/` find no card and no rule that depend on reading opponent's discard pile; every reference to player's own pile or insertion into another player's. rulebook silence have no mechanical consequence. (scan did surface real, distinct gap — own-discard invisibility — now carried by F-011, not F-007.) grug satisfied, no bug here.
> `grep -ril "opponent.*discard|discard.*opponent" data/cards/`

---

## 4. Unresolved / untestable (grug not sure yet)

**F-008 — chance-node branching exceed paper's design range. UNTESTABLE as written.**
its pre-registered test explicitly conditional on F-003 fixed first, and F-003 confirmed unfixed, so no mid-game chance nodes to measure.
*evidence that would settle it:* expose mid-game reshuffles / forced discards as chance nodes (F-003 fix), then log `len(chance_outcomes())` at each. current supporting signal point toward REAL — single chance node that exist carry 1,000 outcomes, 250× paper's stated ≤4 range, and 134 further events per ~2,100 transitions would join it.

**not covered by this pass:** four `[unverified]` items in `findings.md` §4 (double-fire of `end_of_turn_mass_discard`, depth-16 `pending_generic` clone cap, reachability of empty `legal_actions()`, and `max_game_length=4096` reachability). INV-3 find 0 empty legal-action sets in 1,200 sampled states, weak evidence against third but not proof of unreachability.

**capability gap `[gap]`:** `scripts/run_ismcts.py` have no opponent-policy flag — every seat run same bot at same budget, so no justfile recipe can express ISMCTS-vs-random or ISMCTS-vs-ISMCTS-at-different-budget. INV-7/8/9 therefore run through `docs/validation/harness/exp2.py`, which build bots with identical construction `run_ismcts.py` use (same `ISMCTSBot` args, same `CRolloutEvaluator`, same game loop). adding `--opponent` flag would let these run through supported entry point.

---

## 5. GO / NO-GO (grug final verdict)

### 🔴 NO-GO for large-scale simulation. grug sad but honest.

search itself sound — budget monotonicity, self-play calibration, baseline sanity all pass (though these three now STALE per Review 01, §1, pending re-measurement at final gate), and legality, clone independence, chance mass, determinisation consistency, info-set completeness/leakage all clean. replay determinism fix at code level (F-010): runs reproduce from `--seed`, independently re-verified by Review 01 (`docs/validation/reviews/f010-review-01.md`) — but that review REJECTED-SCOPE commit itself for unauthorized bundled changes, so F-010 not yet closed procedurally even though fix confirmed correct. observation now the game: board and own-discard identities present in `information_state_string`/`observation_string` (F-011 fixed). problem that keep this NO-GO is remaining open defects below — mid-game chance events — not observation or 3–4 player returns contract.

conditions that must clear before GO, in dependency order:

1. ~~**F-011 (blocking).**~~ **RESOLVED — Review 01 ACCEPTED-WITH-DEBT** (`docs/validation/reviews/f011-review-01.md`,
   commit `a7cee83`; F-013 open). board occupancy and own discard-pile identities now
   flow through `private_view_json` (`public.board_nodes` + `discard`). **gate met:** INV-4b
   pass at N=403 board-differing pairs (0 invisible) while INV-4a still pass at N=300
   (0 leakage violations), both independently re-run by Review 01. search-time cost regress
   9.66× (independently re-measured at 9.655×; see F-013) — correctness first; throughput
   tracked separately. zero out-of-scope hunks in fixing commit.

2. ~~**F-004 (blocking for any 3–4 player run, i.e. project default).**~~ **RESOLVED —
   Review 01 ACCEPTED-WITH-DEBT** (`docs/validation/reviews/f004-review-01.md`, working tree at
   base `b0f3173`; F-014 open). `_build_c_game_info` now declare honest contract per player
   count: `n==2` unchanged (`utility_sum=0.0`, `min=-200.0`, `max=200.0`, `ZERO_SUM`); `n>2`
   general-sum (`utility_sum=None`, `min=-50.0`, `max=400.0`, `GENERAL_SUM`). `returns()`
   untouched. **gate met:** for `num_players` ∈ {2,3,4}, terminal returns satisfy declared
   contract over N ≥ 50 games (0 out-of-bounds; `n==2` zero-sums 50/50), independently re-run by
   Review 01. residual risk on −50 floor tracked as F-014. zero out-of-scope hunks in
   fixing diff.

3. **F-002 + F-003 (blocking for search validity).** reroll `shuffle_seed`/`shuffle_counter`
   inside `engine_determinize`, as already done for market deck. this cheap half, remove shared reshuffle stream. exposing events as real chance nodes (F-003,
   and then F-008) larger design change, can follow. **gate:** two determinizations of
   one info set no longer share `(shuffle_seed, shuffle_counter)` over N ≥ 100 pairs.

4. **F-006 (re-calibrate before trusting any strength number).** run `uct_c` sweep on this
   game's actual reward scale — measured 6.4:1 exploitation ratio suggest useful range
   far above 1.4, or that returns should be normalised before backup. **gate:** documented
   sweep artifact, with chosen value beating neighbours seat-swapped at N ≥ 200 per arm.

5. **F-005, F-009, F-013, F-014 (non-blocking).** F-005 and F-009 fidelity/API-correctness gaps
   (neither show measurable effect on results; F-005 contradicted as strength bias by
   INV-8; F-009 dormant at default configuration). F-013 throughput regression from
   F-011 fix (9.66× search wall-time at `num_sims=200`) that must close before any
   large-scale ISMCTS throughput claim, via narrower C-level board-only accessor.

**conditional partial GO.** reproducibility (F-010), observation completeness (F-011), and
3–4 player returns contract (F-004, condition 2 above) resolved; 2-player runs may proceed
for *engine and performance* work — throughput, crash-rate, memory — and 3–4 player runs may
now carry honest, non-violated `GameInfo` contract. no *strength, policy quality, or
agent-training* claim should be made until (3) and (4) above also clear, and no throughput
claim until F-013 close.

**note on § 1 win-rate figures:** INV-7/8/9 win rates (budget ladder, self-play
calibration, baseline sanity) measured *before* F-010 RNG fix, so specific
percentages superseded by RNG-stream change (bot's `random_state`, evaluator
stream, and new dedicated resampling stream now decoupled). must re-measure
before cited again; qualitative gates (monotone budget ladder, self-play ≈ 50%,
random crushed) unaffected by F-010 fix and remain acceptance criteria.

---

## Appendix — reproduction (grug show how to run)

all scripts run from repo root with `.venv/Scripts/python.exe -u <path>`:

| script | covers |
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
| `harness/f004_utility.py` | F-004 G3/G4 (returns bounds + insane_outcast stress) |
| `harness/obs.py` | F-011 own-discard, INV-10 resource stability |
| `harness/timing.py` | per-game cost at each budget (ladder sizing) |

note: `harness/f006.py` and any script that run search now reproducible from
seed — F-010 fix (see §2 RESOLVED) make every search deterministic. any remaining
variation genuine seed-to-seed variation, not harness instability.

grug happy with grug-verdict.md. complexity bad, simple language good. grug club away.
