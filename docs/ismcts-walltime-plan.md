# IS-MCTS Wall-Time Plan — Independent Options for the Teacher Corpus

Scope: shorten the wall time of the teacher runs that `docs/nn-training-data.md` asks for
(§ *How many games*, § *v3 teacher run*). Base: `5e1b14b` + working tree, 2026-09-11.
Status: **partially landed** — A1 landed 2026-09-11 and its G4 games/h was measured
2026-09-12 (**38.5 → 65.8 games/h**, see `docs/validation/a1-infostate-hash-landing.md`);
A2–A5, B1–B2, C1 proposed.

Every option below (A1–A5, B1–B2, C1) is a **separate, independently adoptable choice**.
None depends on another landing first; each has its own change set, its own gate and its own
measured expected gain. Pick any subset in any order. Where two options remove the *same* cost
(A1 subsumes A5; B1 and B2 are alternatives) or need the same *gate* (B1 and B2 share G-B), the
section says so — that is the only coupling.

---

## 0. What the requirements fix, and what that leaves as a lever

From `nn-training-data.md`:

| Requirement | Effect on wall time |
|---|---|
| 4-player games, played to `stopped_reason == "terminal"` | ~1,140 moves per game, 72 % non-forced ⇒ **~822 searched decisions per game** — fixed |
| Uniform **≥ 200 sims per seat** for teacher runs | **200 sims per searched decision** — fixed |
| Per-decision telemetry (`visit_counts`, `q_values`, `root_value`, `legal_moves_payload`, `pending_context`); `--no-steps`; observations regenerated offline | I/O is already off the hot path (`_write_jsonl_line` flushes, no fsync) — not a lever |
| Every sample carries `sims_requested`; the manifest carries `vars(args)` incl. `evaluator`, `rollout_max_length` | Any option that changes the search is provenance-tracked at the run level already |
| 1,000 games to prove the pipeline; 5k–20k before distillation | Volume is the goal, not a lever |
| Measured: **~40 games/h** (32 games, 50 min, 16 workers, 8c/16t 7800X3D; 828–1,719 s per game, mean 1,264 s) | Baseline |

So `wall = games × 822 × 200 × cost_per_sim ÷ effective_workers`. Games, decisions and sims are
pinned by the doc; the 4→16 worker pilot scaled 3.7× so the box is saturated. **The lever is
cost per simulation**, plus scheduling losses (A2) and more hardware (C1).

---

## 1. Where a simulation's time goes (measured, not assumed)

Method: one 200-sim `step_with_policy` on the runner's real market (`seed 42`, game 0, 4 players,
`random-c` evaluator, `uct_c 1.4`), at a non-forced node reached by 150 random plies ("mid",
round 6, 7 legal) and by 450 ("late", round 17, 7 legal), with `PyrantsCState` methods and
`CRolloutEvaluator.evaluate` wrapped in `perf_counter` timers. Single decisions, so treat the
figures as ±15 %.

| Component | mid | late | Per-sim detail |
|---|---|---|---|
| `evaluate` (C rollout, `engine_random_rollout`) | 4.42 ms · **67 %** | 2.69 ms · **57 %** | 1 call/sim; ~8–10 µs/step; 300–1,100 steps |
| `information_state_string` | 1.56 ms · **24 %** | 1.50 ms · **32 %** | ~105 µs avg × **14.5 calls/sim**; the key is a **13 KB** string |
| `_apply_action` + `_legal_actions` | 0.16 ms · 2.4 % | 0.14 ms · 2.9 % | ~5.9 applies + ~7.8 legal-action calls per sim (tree depth ≈ 6) |
| residual (select/expand, numpy scalar math, `deepcopy`) | ~0.5 ms · ~8 % | ~0.4 ms · ~8 % | |
| **per simulation** | **6.6 ms** | **4.7 ms** | 200 sims ⇒ 0.95–1.3 s per decision |

Supporting measurements:

- **Rollout step cost.** `engine_clone`+`engine_destroy` 1.3–2.0 µs, `engine_legal_moves`
  0.9–1.2 µs, `engine_apply` (which clones internally) 2.6–9.9 µs, ctypes floor 0.3 µs.
  `engine_clone` (`engine_c/state.c:175-185`) mallocs a **512 KB arena** and memcpys the
  **19,320-byte** `GameState` on every step; `engine_random_rollout` (`engine_c/rollout.c:39-60`)
  does that once per step.
- **Rollout length vs. `max_length`** (ms per rollout, 200 reps): fresh game 10.3 (unbounded,
  100 % terminal) / 4.2 @400 / 1.8 @200 / 0.8 @100 / 0.43 @50; mid 3.2–4.3 / 1.2 / 0.55–0.69 /
  0.29–0.49 / 0.19; late 2.9–3.2 / 1.3 / 0.64–0.79 / 0.35–0.38 / 0.19. A fresh-game 4p rollout is
  ~1,000–1,100 plies. The cut-off path scores with `compute_final_scores` (`rollout.c:66-74`).
- **Whole decision with truncated rollouts** (200 sims): mid 867 → 373 ms @200 / 592 ms @100;
  late 973 → 718 ms @200 / 540 ms @100; early (round 2) 1,189 → 457 / 397 ms.
- **Why the key is 14.5 calls/sim.** The stock `ISMCTSBot` (`open_spiel/python/algorithms/ismcts.py`)
  calls `get_state_key` twice in `lookup_node` (`:237-240`), once more in `create_new_node`
  (`:226`), and once per sim on the root assert (`:130`). Only same-state repeats hit the F-013
  `_view_cache`; every post-`apply` state is a cold ~105–200 µs `json.dumps`.
- **`_view_cache` is not inherited across `determinize`** (`engine_c/bindings/c_adapter.py:245-254`),
  even for the observing player, whose view is invariant under it by construction (the leak test's
  own invariant). The root assert is therefore a cold key every sim.
- **Wave tail.** 32 games on 16 workers is two waves; the second waits for the 1,719 s straggler.
  Ideal 2 × 1,264 s = 42 min vs. 50 min measured.

Superseded numbers: the 2026-09-04 profile's "infostate key ≈ 16 %" was taken at 10 sims on a
round-capped game; at 200 sims the tree is deeper and the key is 24–32 %.

---

## 2. Gates common to every option

- **G0 — determinism.** Same seed ⇒ byte-identical `replay.json` regardless of `--workers`
  (already true; must stay true).
- **G1 — replays verify.** `just verify-replays` (or `scripts/verify_replays.py --root <run>`) OK
  on the option's acceptance run.
- **G2 — the training profile still builds.** `just ismcts-quick` green end-to-end (2 × 4p games,
  replay-verify, `--strict` build, leak check, report).
- **G3 — test trees.** `pytest tests/` and `pytest openspiel_pyrants/tests/` as two commands; no
  failures beyond the tolerated set (F-015 ×3; F-003 ×10; F-013 G1 while F-034 keeps it red).
- **G4 — measured, not estimated.** Each option records a before/after `ms/sim` at the § 1 nodes
  (same seed, same nodes) and a `games/h` from a ≥ 16-game, 16-worker run in its landing note.
  For byte-identical options the games/h run is the **paired re-run** described under G-I below,
  so one run serves both gates.
- **G-I (identity gate, options marked *byte-identical*).** A 2-game `ismcts-quick`-shaped run
  before and after the change produces byte-identical `decisions.jsonl` and `replay.json`. This
  is the strongest possible statement that the teacher is unchanged; options A1, A3, A4, A5 claim
  it and must prove it.

  *Diagnostic (landed with A1): the paired re-run.* Re-play the `teacher_v3_32` baseline
  (`artifacts/ismcts/runs/20260911T193759Z_58e54c44a5f5`) with the candidate build, flag-for-flag
  (`--num-sims 200 --num-games 32 --seed 42 --workers 16 --num-players 4 --uct-c 1.4
  --game python_pyrants_c --no-steps`), then
  `python scripts/compare_paired_runs.py --baseline <baseline run> --candidate <new run>`.
  Because G0 makes every `game_index` do the same decisions and sims on both sides, one run yields
  (a) G-I at the real 200-sim budget — per game, `decisions.jsonl` / `replay.json` equal after
  dropping `run_id` and wall-clock fields, `final_decks.json` byte-equal — and (b) G4 as a
  *paired* per-game wall ratio plus run-level games/h, with no cross-game variance in the
  comparison. ~30 min at 16 workers after A1. The script exits non-zero on any content
  difference. A 16-game run pairs only the first wave; use 32 so the games/h figure is
  like-for-like with the baseline's.
- **G-B (strength gate, options marked *changes the search*).** Two parts, both required:
  1. *Policy-agreement re-search (no new games, ~15 min).* Sample 400 non-forced decisions from
     the `teacher_v3_32` source run (`artifacts/ismcts/runs/20260911T193759Z_58e54c44a5f5`),
     stratified by round. Reconstruct each state by replay. Run three fresh 200-sim searches per
     node: baseline with seed s₁, baseline with seed s₂, candidate with seed s₁. Report argmax
     agreement and total-variation distance of the visit distributions for (baseline s₁ vs
     baseline s₂) — the seed-to-seed noise floor — and (candidate vs baseline s₁). Pass if the
     candidate's agreement is within 0.03 argmax / 0.03 TV of the noise floor.
  2. *Seat-rotated head-to-head (24 games, ~35 min at 16 workers).* Candidate on two seats,
     baseline on the other two, rotated per game. Pass if the candidate's mean value target
     ((score − mean others)/40) is ≥ baseline − 0.05. Needs a per-seat form of the flag being
     tested (mirror `--num-sims-per-seat`), which is part of the option's change set.

  A corpus built with a G-B option records it in `manifest.config` (already automatic via
  `vars(args)`); **do not mix evaluators inside one dataset** without adding the field to the
  per-sample record the way `sims_requested` is. The dataset's `value_target` (final scores) is
  unaffected; the auxiliary `root_value`/`q_values` change meaning and must not be pooled across
  evaluators.

---

## 3. Options

Each option: what changes, where, the measured basis for the expected gain, why it stands alone,
its "done when", and its risk. Gains are for the option **alone** against the § 1 baseline.

### A1 — Key tree nodes by a hash, not a 13 KB string  · byte-identical · **≈ ×1.35**  · LANDED 2026-09-11

> **Landed.** Per-sim A/B ×1.61–1.64 (2.1–2.7 ms/sim drop). G0–G4 green. Paired 32-game
> re-run of the `teacher_v3_32` baseline (2026-09-12): **content-identical on all 32 games at
> 200 sims** (G-I at the teacher budget), **38.5 → 65.8 games/h** (run wall 49.9 → 29.2 min),
> per-game wall ratio median ×1.67 (×1.61 on the contention-free second wave), move-latency p50
> 1,237 → 681 ms. See `docs/validation/a1-infostate-hash-landing.md`.

**Change.** Add `engine_infostate_hash(const GameState*, Sym player, uint64_t out[2])` in C: a
128-bit hash over exactly the fields `CEngineAdapter.private_view_json` serialises (F-011's
contract: public summaries, board nodes, own hand/discard/played/inner circle/trophy hall,
counts, resources). In `PyrantsCState`, add `information_state_key(player)` returning
`(player, hash(tuple(history_actions)), h0, h1)`; give the bot a `get_state_key` override that
uses it (subclass in `openspiel_pyrants/ismcts_factory.py`, where the bot is already built).
`information_state_string` stays as is for `info_state_sha256` in `decisions.jsonl` (once per
decision) and for every existing test.

**Where.** `engine_c/player_view.c` (or a new `infostate_hash.c`) + `engine_c.def` + bindings;
`openspiel_pyrants/state_c.py`; `openspiel_pyrants/ismcts_factory.py`.

**Expected gain.** 1.5 ms/sim → ≈ 0.05 ms/sim (14.5 calls × ~3 µs). Per-sim 6.6 → 5.1 (mid),
4.7 → 3.25 (late): **×1.30–1.45**.

**Independence.** Touches only how nodes are *looked up*. Same tree, same RNG draws, same
visits. Makes A5 redundant (the root assert becomes a 3 µs hash) but does not require it.

**Done when.** (i) Over every state of every stored replay plus 50 determinizations per state,
`hash equal ⇔ information_state_string equal` (the equivalence classes match — the leak test's
shape, applied to the key); (ii) G-I byte-identity holds; (iii) `ms/sim` at the § 1 nodes drops
by ≥ 1.2 ms; (iv) G0–G4.

**Risk.** A hash that omits a field the string includes merges info sets (wrong tree sharing); one
that includes hidden fields splits them (IS-MCTS degrades toward per-determinization PIMC).
Gate (i) catches both. 128 bits makes accidental collision a non-issue at 200 nodes per search.

### A2 — Run the corpus as one seed stream; add `--game-index-offset`  · byte-identical · **≈ ×1.1–1.15**

**Change.** `scripts/run_ismcts.py` iterates `range(args.num_games)` (`:1263`) and derives every
game's setup and shuffle seed from `args.seed + gi`. Add `--game-index-offset N` so a run plays
game indices `[N, N + num_games)` of the same stream; record it in the manifest and in each
`summary.json`. Then play the 1,000-game corpus as one invocation (or as offset-sharded
invocations that resume where a killed run stopped) instead of 32-game batches.

**Where.** `scripts/run_ismcts.py` (arg, spec loop, manifest), `scripts/_run_layout.py`
(`build_manifest`), `interface/replay_loader.py` if it keys on game index.

**Expected gain.** The 32-game measurement lost ~16 % to its second-wave tail plus start-up
(42 min ideal vs. 50 min). With 1,000 games on 16 workers the tail is one wave in 63:
**40 → ~45 games/h** for free. The offset flag is what makes a killed 1,000-game run resumable
without re-playing (and therefore double-counting — search is deterministic per seed) games
already on disk.

**Independence.** Scheduling only; no search code touched.

**Done when.** Games `[k, k+m)` from an offset run are byte-identical to games `[k, k+m)` of an
un-offset `--num-games ≥ k+m` run with the same seed; `just ismcts-quick` passes with and without
the flag; G0–G3.

**Risk.** None to the search. Directory naming (`game_XXXX`) must use the absolute index so two
shards never collide (see F-025's mixed-run history).

### A3 — Stop mallocing a 512 KB arena per rollout step  · byte-identical · **≈ ×1.1–1.15**

**Change.** Pick one of two substitutes for the same cost:

- *(a) Arena recycling.* Keep a small per-process free-list (say 64 entries) of destroyed arenas
  in `arena_destroy`/`arena_create`; `engine_clone` reuses one instead of `malloc`ing. Applies to
  every clone in the process — rollout steps, tree-side `clone()`, `determinize`.
- *(b) In-place apply for the rollout only.* `engine_apply_inplace(GameState*, const Move*)`
  = `engine_apply` minus the clone; `engine_random_rollout` clones once, then applies in place.
  On an in-place failure (should be impossible after F-019's placeholder filter) fall back to
  re-running that rollout on the cloning path with the same seed, so the result is unchanged.

**Where.** `engine_c/arena.c` (a) or `engine_c/rules.c` + `engine_c/rollout.c` (b);
`engine_c.def` for (b).

**Expected gain.** Clone+destroy is 1.3–2.0 µs of an ~8–10 µs average step, i.e. 15–25 % of
rollout time, which is 57–67 % of the decision: **×1.10–1.17**.

**Independence.** Allocation only. Move sampling, RNG stream, scoring untouched, so rollout
results are bit-identical.

**Done when.** (i) `tests/c_engine` and the C test binaries green (incl. `test_rollout`); (ii)
ASan build (`just build-c-asan`, `just test-c-asan`) clean — this option is exactly the kind of
change ASan exists for; (iii) `engine_random_rollout(seed, …)` returns identical scores before
and after on 1,000 (state, seed) pairs; (iv) G-I; (v) per-rollout ms at the § 1 nodes drops
≥ 15 %; G0–G4.

**Risk.** (b) changes the atomicity contract of `engine_apply` (a failed apply currently leaves
`src` intact); the fallback rerun keeps rollout output identical but the code path is new.
(a) is the smaller change and helps the tree side too; prefer it unless it measures worse.

### A4 — `ISMCTSBot` subclass: remove the stock loop's Python overhead  · byte-identical · **≈ ×1.05**

**Change.** In `openspiel_pyrants/ismcts_factory.py`, subclass `ISMCTSBot` and override:
`lookup_or_create_node` to compute the key once (stock computes it 2–3×);
`check_expand` to `list(legal_actions)` instead of `copy.deepcopy`;
`_select_candidate_actions` to compute each child's UCT value once instead of twice.
Keep `np.sqrt`/`np.log`: swapping them for `math.*` can differ in the last ulp and break the
tie-tolerance comparison — only take that if G-I still holds.

**Where.** `openspiel_pyrants/ismcts_factory.py` only.

**Expected gain.** Most of the ~8 % residual plus the redundant key calls (~0.3 ms/sim of the
key cost if A1 is *not* taken): **×1.05–1.10** alone.

**Independence.** Pure-Python control flow; same RNG consumption order (the `shuffle` in
`check_expand` and the `randint` in `select_action` are kept exactly).

**Done when.** G-I byte-identity; existing `openspiel_pyrants/tests` for the bot factory green;
`ms/sim` drops measurably; G0–G4.

**Risk.** Any accidental change to the order of `_random_state` draws changes every game; G-I
is the guard.

### A5 — Inherit the observing player's `_view_cache` across `determinize`  · byte-identical · **≈ ×1.02**

**Change.** In `CEngineAdapter.determinize`, copy `self._view_cache[observing_player_id]` into
the child (only that key). `engine_determinize` reshuffles the *other* players' hidden zones;
the observing player's private view is invariant — the builder's leak test asserts exactly this.

**Where.** `engine_c/bindings/c_adapter.py:105-118` (`determinize`, `_inherit_projection`).

**Expected gain.** One cold key (~110 µs) per sim becomes a 1.3 µs hit: **≈ 2 %** of the decision.
Redundant if A1 lands (the assert becomes a 3 µs hash either way); listed because it is a
three-line change with its own guarantee.

**Independence.** Cache plumbing only.

**Done when.** A test that `private_view_json(observer)` is string-equal before and after
`determinize` for the observer and *not* served from cache for any other player; G-I; G0–G4.

**Risk.** Serving a stale view to a non-observing player would leak; the test above pins it.

### B1 — Truncate rollouts (`--rollout-max-length 200`)  · changes the search · **≈ ×1.8–2.2**

**Change.** No new mechanism: the flag exists, the cut-off path already scores with
`compute_final_scores`, and the manifest records it. Add `--rollout-max-length-per-seat` (mirror
of `--num-sims-per-seat`) so G-B part 2 can be run, then adopt `200` for teacher runs if G-B passes.

**Where.** `scripts/run_ismcts.py` (per-seat flag), `justfile` `ismcts` recipe default.

**Expected gain.** `evaluate` 2.7–4.4 ms → 0.55–0.8 ms; per-sim 6.6 → ~2.8 (mid), 4.7 → ~2.6
(late); whole decisions measured 867 → 373 ms and 973 → 718 ms: **×1.8–2.2** alone.

**What it changes.** The leaf value becomes "score if the game ended ~3 rounds from here after
random play" instead of "final score after ~1,000 random plies". At 4 players a full random
play-out is mostly noise, so this may be neutral or better — that is G-B's question, not an
assumption.

**Independence.** One CLI value; every other option is orthogonal to it.

**Done when.** G-B parts 1 and 2 pass at `max_length = 200` (also record 100 and 400 in part 1
so the choice is a curve, not a point); G0–G4; `nn-training-data.md` § *How many games* updated
with the new games/h.

**Risk.** A weaker teacher. Detected by G-B before any corpus is played with it.

### B2 — Static leaf evaluator (no play-out)  · changes the search · **≈ ×2.3–3.0**

**Change.** New `--evaluator static-c`: `evaluate` returns `compute_final_scores(state)` shaped
like `CRolloutEvaluator` (2p score difference, 3–4p raw scores) with no random steps;
`ce_api.CEngine.compute_final_scores` already exists. Per-seat evaluator flag for G-B part 2.

**Where.** `openspiel_pyrants/c_rollout_evaluator.py` (new class), `scripts/run_ismcts.py`
(`--evaluator` choice, per-seat form).

**Expected gain.** `evaluate` → ~0.01 ms; per-sim 6.6 → ~2.2 (mid), 4.7 → ~2.0 (late):
**×2.3–3.0** alone.

**What it changes.** The teacher becomes IS-MCTS over a greedy material/VP evaluation at depth
~6 rather than random play-outs. This is the same slot the NN value head will occupy later, so
the corpus design already assumes the evaluator is a parameter — but it must clear G-B like any
other change to the labels.

**Independence.** Orthogonal to every A option and to C1. B1 and B2 are *alternatives* for the
same cost (adopting both is meaningless: B2 has no rollout to truncate).

**Done when.** G-B parts 1 and 2 pass; G0–G4; doc updated.

**Risk.** A greedy leaf can bias the search toward short-horizon VP grabs; G-B part 2 is the
check that matters here.

### C1 — More hardware  · byte-identical · **linear**

**Change.** None to the code if each box uses its own `--seed`; with A2's offset flag, several
boxes can play disjoint index ranges of *one* seed stream and the union equals a single-box run.

**Expected gain.** Throughput scales with hardware threads (4→16 workers scaled 3.7× on the
7800X3D; a 64-vCPU box ≈ 4× the current one). No change to cost per simulation.

**Independence.** Nothing else needs to land. Combines multiplicatively with everything.

**Done when.** Shards verify (G1) and, if on one seed, are byte-identical to the corresponding
indices of a single-box run over a spot-checked range.

**Risk.** Mixed engine builds across boxes: the manifest's DLL sha256 must match across shards
before they are pooled into one dataset.

---

## 4. Projections

Per option alone, against the measured 40 games/h (ranges from the § 1 mid/late spread):

| Option | Kind | ms/sim after (mid / late) | games/h | 1,000 games | 20k games |
|---|---|---|---|---|---|
| baseline | — | 6.6 / 4.7 | 40 | 25 h | 21 d |
| A1 hash key | identical | 5.1 / 3.25 (measured 4.4 / 3.3) | ~54 (**measured 65.8**) | 18.5 h (measured 15.2 h) | 15 d (measured 12.7 d) |
| A2 single stream + offset | identical | — | ~45 | 22 h | 18.5 d |
| A3 arena | identical | 5.9 / 4.2 | ~45 | 22 h | 18.5 d |
| A4 bot subclass | identical | 6.2 / 4.4 | ~43 | 23 h | 19.5 d |
| A5 view-cache | identical | 6.5 / 4.6 | ~41 | 24.5 h | 20.5 d |
| B1 truncate @200 | search | 2.8 / 2.6 | ~80 | 12.5 h | 10.5 d |
| B2 static leaf | search | 2.2 / 2.0 | ~100 | 10 h | 8.5 d |
| C1 (64 vCPU) | identical | — | ~160 | 6 h | 5 d |

A1's measured 65.8 games/h beat its ~54 projection because § 1 timed only the key string's
*construction* (~1.5 ms/sim of `json.dumps`); the landing note's A/B, which removes the whole key
path (construction plus hashing and dict comparison of a 13 KB `str`), measured a 2.1–2.7 ms/sim
drop. The rows below A1 are still projections against the *original* 40 games/h baseline; re-base
them on 65.8 when stacking. If several are taken the gains multiply only approximately (they are single-decision
measurements and the phases of a game weight them differently). Reference points, for
budgeting rather than promising: **A1+A2+A3+A4 ≈ ×1.7–1.9** (~70–75 games/h; 1,000 games in
~14 h); **all A + B1 ≈ ×4–5** (~180 games/h; 1,000 in ~5.5 h, 20k in ~4.5 d); **all A + B2 ≈
×8–10** (~350 games/h; 1,000 in ~3 h, 20k in ~2.5 d). After A1 and B1/B2 the largest remaining
term is the ~0.4–0.5 ms/sim residual, which is why A4 is worth more *after* those than its
stand-alone figure suggests.

---

## 5. Not levers (so nobody spends time on them)

- **Porting the tree search to C.** It would recover only the Python share (≈ 35–43 %) that A1
  and A4 already recover, and thread-level parallelism inside one decision adds no throughput on a
  box already saturated by game-level processes.
- **Tree reuse between a seat's consecutive decisions.** Improves quality at a fixed 200 sims;
  does not cut wall time under the doc's uniform-budget requirement.
- **`--max-world-samples`** and the **`engine_build_board_view` C accessor** — withdrawn with
  measurements in `docs/validation/f013-part-b-fix-plan.md` § 9 (0.8 % and ~1 %).
- **I/O.** Per-line JSONL writes flush without fsync; `steps.jsonl` is already off for teacher runs.
- **Fewer sims on low-branching nodes.** Would break the uniform ≥ 200 requirement; the doc keys
  sample weighting on `sims_requested` precisely so budgets are not silently mixed.
- **More than 16 workers on the 8c/16t box.** Nothing left to schedule onto.

---

## 6. Risks that cut across options

1. **Byte-identity is the promise for the A options; the F-013 G1 test that would normally enforce
   it is red for an unrelated reason (F-034: its frozen reference recruits `insane_outcast`).**
   Until that reference is re-frozen, G-I is run as the paired re-run in § 2
   (`scripts/compare_paired_runs.py`), and its table pasted into the landing note. The A1 run
   (`20260912T092122Z_9d7e5da4a661`) is content-identical to the baseline and can serve as the
   baseline for the next A option.
2. **G-B is the only thing standing between a B option and a mislabelled corpus.** Part 1 alone is
   not enough — a search that agrees with the baseline on 400 nodes can still lose games; part 2
   is required.
3. **Mixed provenance.** A dataset pooled from runs with different `evaluator`/`rollout_max_length`
   values is a silent label mix; the builder must refuse it or record the field per sample.
4. **Measurement drift.** The § 1 numbers are single decisions on two positions. Each option's G4
   re-measures on the same nodes so gains are compared like with like.
