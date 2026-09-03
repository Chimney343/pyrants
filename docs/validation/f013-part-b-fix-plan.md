# F-013 Part B Fix Plan — Make the Board Projection Cheap, Not Just Cached

**Defect:** `docs/validation/findings.md` § F-013 (MINOR, performance), still **OPEN** after the
Part A cache landed in `16f8712`. Part A cut end-to-end IS-MCTS search wall-time from 1.7453 s to
1.0500 s per search (`docs/validation/baseline/f013_timing.{pre,post}.txt`, num_sims=200, N=10),
leaving a **6.38×** residual over the pre-F-011 reference of 0.1646 s
(`baseline/f011_timing.pre.txt`). Part A's own § 9 recommended a narrower C-level
`engine_build_board_view` accessor as the follow-up.

**This plan supersedes that recommendation.** Measurement (§ 1) shows the C call is **0.8%** of the
cost the accessor was meant to remove. The remaining 99.2% is Python-side projection and
serialization, and it is fixable without touching a line of C.

**Hard constraint, carried over from Part A § 0.4 and treated as Gate G0:** this fix must not change
current simulation methods. Zero behavioural diff in `openspiel_pyrants/` (test files excepted),
`scripts/`, or `engine_c/*.c`. Every touched method keeps its signature and returns byte-identical
output for byte-identical input.

---

## 0. Mandatory process constraints

The four from `f013-fix-plan.md` § 0, unchanged:

1. **Test-driven design is mandatory.** Every behavioural change starts as a failing test. A GREEN
   phase does not begin until its RED tests are written, run, and observed to **fail for the stated
   reason**.
2. **This change will be reviewed.** Phase 7 is required.
3. **`docs/validation/verdict.md` and `findings.md` must be updated.** Phase 7.
4. **No simulation-method changes.** Restated as G0. If clearing a gate requires touching anything
   outside the file set in G0, stop and report rather than widen scope.

Plus one specific to this plan:

5. **Every phase lands independently.** Phases 2–5 are four separate levers, ordered by measured
   value per unit of risk. Each is a complete change with its own gate. Stopping after any phase
   leaves the tree correct and faster than before.

---

## 1. Root cause (measured, not assumed)

All numbers below were taken on the `f013_timing.py` root (`fresh(game, 42)` + 40 `RandomBot(131)`
moves, 2 players), `.venv` CPython 3.13, **no profiler attached**. Phase 0 re-captures them.

### 1.1 The C call is not the cost

| Component | Cost | Share of `build_c_board_view` |
|---|---|---|
| `engine_build_view` (the C call, reusing an output buffer) | **3.1 µs** | 0.8% |
| `CGameView()` allocation (83,064 B, ctypes-zeroed) | 0.9 µs | 0.2% |
| `_build_board_nodes` — the Python projection loop | ~393 µs | **99%** |
| **`build_c_board_view` total** | **397.5 µs** (507.3 µs at move 120) | 100% |

The 83 KB `memset` and the "populates every card zone + 3 special-stack scans" cited in F-013's
original write-up are real, and together they cost 3.1 µs. **A narrower C accessor can save at most
~3 µs of ~400.** Part A § 9's recommended follow-up is therefore withdrawn (§ 9).

### 1.2 Where the ~393 µs actually goes

`_build_board_nodes` (`engine_c/bindings/view.py:388`) makes **422 `_sym_str` calls per projection**,
each a ctypes `intern_str` plus a `bytes.decode`:

| Symbol group | Calls per projection | Read by `_board_nodes_view`? |
|---|---|---|
| `node_id` | 81 | yes — but **board-static** |
| `adjacent_to` | **196** | **no — discarded** |
| `troop_slots` | 145 | yes, dynamic |
| `spies` | 0 (this state) | yes, dynamic |
| **total** | **422** | |

`_board_nodes_view` (`c_adapter.py:235`) reads six fields — `node_id`, `troop_slots`, `spies`,
`control_vp`, `total_control_vp_per_turn`, `vp_tokens`. It never reads `adjacent_to` or `kind`. So
**46% of the symbol decoding is for a field the consumer throws away**, plus 81 frozen
`NodeOccupancyView` dataclasses per call that exist only to be immediately re-boxed into dicts, plus
81 `node_id` decodes and 162 int reads that cannot change during a game (they come from
`state->definition->board`, which is immutable — see `engine_c/view.c:60-85`).

A prototype that reads `CGameView` straight into the six output fields, memoizes sym-to-str, and
hoists the board-static fields produces **byte-identical output at 71.2 µs** — a **7.1×** reduction,
in pure Python. Verified byte-identical against the current implementation over 344 states across 5
seeds (§ 4.1, T3 — note the coverage gap that check exposed).

### 1.3 The cache's hit set is exactly the repeat-read set

Census of one `num_sims=200` search from the `f013_timing` root, keyed on
`(adapter identity, generation, player_id)` with adapter identities pinned so `id()` cannot recycle:

```
reads = 1952        distinct (adapter, generation, player) = 876
read multiplicity histogram: {2: 676 states, 3: 200 states}     <- never 1
adapters constructed = 201      apply-generations = 675
board-cache builds = 876        board-cache hit rate = 55.1%
```

Two things follow, and they reframe the problem:

- **Every distinct state is read 2× or 3×, never once.** OpenSpiel's `lookup_or_create_node` calls
  `get_state_key` twice on a miss (`ismcts.py:237,242`), and the per-simulation
  `assert root_infostate_key == self.get_state_key(sampled_root_state)` (`ismcts.py:128`) adds a
  third read on each of the 200 determinized roots.
- **The board cache's 55.1% hit rate is precisely that repeat-read rate.** The cache never survives
  an adapter's construction, so it captures the repeat reads and nothing else. The 876 "cold misses"
  are not a cache that is failing — they are 876 genuinely distinct states, of which only 201 come
  from a clone/determinize and 675 come from an `apply()` that legitimately invalidated.

Per-search cost decomposition (876 cold × 510 µs + 1076 warm × 112 µs):

| Path | Cost per search | Share |
|---|---|---|
| Cold `private_view_json` (projection + serialization) | 447 ms | 79% |
| Warm `private_view_json` (`_build_public_dict` + `json.dumps`) | 120 ms | 21% |
| **Total in `private_view_json`** | **567 ms** | ~74% of the search |

And on *every* read, warm or cold, `json.dumps(result, sort_keys=True)` costs 89.5 µs, of which
**79.7 µs (89%) is the `board_nodes` array**.

### 1.4 The four levers, sized

| # | Lever | Saving per search | Risk |
|---|---|---|---|
| **L3** | Cheap projection: drop unused fields, hoist board-static fields, memoize sym-to-str | **−286 ms** | low — pure refactor, byte-identity is mechanically checkable |
| **L1** | Cache the whole `private_view_json` string per `(adapter, player_id)` | **−120 ms** | low — same single invalidation site the board cache already uses |
| **L4** | Cache the `board_nodes` JSON fragment instead of re-serializing it | **−70 ms** | medium — needs sentinel splicing |
| **L2** | Propagate the board projection across `clone`/`determinize` | −79 ms alone, **−14 ms after L3** | medium — depends on an engine invariant that must be locked down first |

**The lever this plan was opened for — L2, the cold-cache-on-clone path — is the smallest of the
four, and shrinks by 5.6× once L3 lands.** It is still worth doing (it is cheap and removes a real
redundancy), but it is Phase 4, not Phase 2. Sequencing it first would spend the riskiest review
budget on the smallest win.

Projected residual after all four: `876 × (71 µs projection + ~25 µs public dict) ≈ 84 ms`, i.e.
**567 ms → ~84–162 ms**, and end-to-end search wall-time roughly halved. Honest projection for G5:
the 6.38× regression falls to **~3×**, *not* under Part A's aspirational 2× — see § 8.

---

## 2. Acceptance gates

| Gate | Threshold |
|---|---|
| **G0 No simulation-method changes** | `git diff --stat` touches only `engine_c/bindings/{c_adapter,view,engine_bindings}.py`, `openspiel_pyrants/tests/test_board_view_cache.py`, `engine_c/bindings/test_label_enrich.py`, new harness/test files, and `docs/validation/*`. **Zero** diff in `openspiel_pyrants/*.py` (non-test), `scripts/`, `engine_c/*.c`, `.venv/` |
| **G1 Byte-identity** | For a corpus of ≥300 states across ≥5 seeds **including ≥20 states with spies on the board**, `private_view_json(pid)` returns a byte-identical string to the pre-fix implementation, for every player, cache warm and cold. Every phase must re-clear this gate |
| **G2 Invalidation on mutation** | After `apply()` of a board-mutating move, the next `private_view_json`/`_board_nodes_view` reflects the new board. After `destroy()`, calls fail as they do today rather than serving a cached string |
| **G3 Projection cost** | Cold `_board_nodes_view()` drops from 397–507 µs to **≤ 120 µs** on the same states |
| **G4 Read census** | `harness/f013b_census.py` at num_sims=200: repeat reads served without re-serialization rise from 0 to **1076** (L1); board projections drop from 876 to **≤ 700** (L2) |
| **G5 Search wall-time** | `harness/f013_timing.py` mean drops **≥ 40%** from the recorded 1.0500 s. State the resulting ratio against the 0.1646 s pre-F-011 reference plainly; do not claim "fixed" if it is above 2× |
| **G6 Invariant battery reproduces the same numbers** | `inv_a.py`, `inv_b.py`, `inv_b2.py`, `det_bot.py`, `f002b.py` reproduce the **same** values, not merely a pass: INV-1 0/100 divergent, INV-5 mean 11.11/12, `det_bot` B1 1 distinct action, F-002 3/3. G0 already establishes this fix cannot legitimately move any of them |
| **G7 Suites green** | `just openspiel-test`, `just test`, `just test-c` — same pre-existing failures as F-014's record (Zuggtmoy, Air Elemental, Neogi; plus the 10 postponed F-003 Part B RED tests), nothing new |

**G1 is this plan's trap.** Part A's trap was a stale cache; this plan's is a projection that is
*almost* identical — `spies` is `tuple(sorted(...))` with falsy entries filtered in the current code
(`view.py:404-408`), while `troop_slots` keeps its `None`s unsorted and unfiltered. A rewrite that
forgets the sort, or filters the wrong list, produces output that is equal on every state a random
playout reaches and wrong the moment a spy lands on the board.

---

## 3. Phase 0 — Capture the red baseline

Two artefacts, both re-captured rather than reused (the tree has moved since Part A — F-014 landed
and F-003 Part B tests are in flight):

```
.venv/Scripts/python.exe -u docs/validation/harness/f013_timing.py  > docs/validation/baseline/f013b_timing.pre.txt
.venv/Scripts/python.exe -u docs/validation/harness/f013b_census.py > docs/validation/baseline/f013b_census.pre.txt
```

**New harness script — `docs/validation/harness/f013b_census.py`.** Not a pytest (wall-clock and
call counts are environment-sensitive). It must emit, for one `num_sims=200` search from the
`f013_timing` root:

1. `private_view_json` reads, distinct `(adapter, generation, player)` triples, and the multiplicity
   histogram. **Adapter identities must be pinned** — hold a reference to every constructed adapter.
   Without that, `id()` recycles and the distinct count collapses to a meaningless 16.
2. Board projections performed, split between generation-0 projections (clone/determinize — L2's
   addressable set) and post-`apply` projections (not addressable).
3. Micro-timings: `engine_build_view` alone, `CGameView()` alone, `build_c_board_view`,
   `_board_nodes_view` cold, `private_view_json` warm, and `json.dumps` with and without
   `board_nodes`.

Expected pre-fix content: the § 1.3 census and the § 1.1/§ 1.2 timings. If the census differs
materially from § 1.3, **stop and re-derive § 1.4's sizing before writing any code** — the phase
ordering depends on those ratios.

---

## 4. Phase 1 — RED: tests first

One new file, `openspiel_pyrants/tests/test_board_projection.py`, plus edits to the existing
`test_board_view_cache.py` (§ 4.2). House pattern: controls before completing tests.

### 4.1 New tests

| # | Test | Asserts | Pre-fix |
|---|---|---|---|
| T1 | `test_private_view_json_byte_identical_to_reference` | **The G1 differential.** For every state in the corpus (§ 4.3) and every player, `private_view_json(pid)` equals a frozen reference string captured from the pre-fix implementation. Reference vectors are generated once in Phase 0 into `docs/validation/baseline/f013b_view_vectors.jsonl` and committed, so the comparison survives the implementation being replaced | **PASS** (control — trivially true against itself; must *stay* true through all four phases) |
| T2 | `test_board_projection_matches_build_c_board_view` | The new projection equals the six fields derived from `view.build_c_board_view`, over the same corpus. Pins the new fast path to the general-purpose API that three other consumers still use (`test_observation_completeness.py`, `scripts/_state_snapshot.py`) | **N/A** (no new projection yet) |
| T3 | `test_projection_corpus_covers_spies_and_full_troop_slots` | **Coverage guard, written before T1/T2 are trusted.** Asserts the corpus holds ≥20 states with ≥1 spy on the board and ≥20 with a fully occupied troop-slot list. Without it, T1/T2 are vacuous on two of the six fields | **FAIL** — 344 states sampled across 5 random playouts contained **zero** spy states. The corpus must be built deliberately (§ 4.3), not sampled |
| T4 | `test_projection_makes_exactly_one_engine_build_view_call` | One `_board_nodes_view()` on a cold adapter triggers exactly one `_lib.engine_build_view` and **zero** `view.build_c_board_view` calls | **FAIL** (currently one `build_c_board_view`) |
| T5 | `test_board_static_fields_survive_applies` | `node_id`/`control_vp`/`total_control_vp_per_turn` recomputed fresh after 60 `apply()`s equal the template hoisted at move 0. This is the invariant L3's hoisting rests on | **PASS** (control — must stay true) |
| T6 | `test_sym_cache_is_invalidated_by_intern_destroy` | After `intern_destroy()` and a re-intern that reassigns sym ids, the memo does not serve a stale string. `engine_c/bindings/test_label_enrich.py:343` really does call `_lib.intern_destroy()`, so this is a live hazard, not a hypothetical | **FAIL** (no memo yet — write it now so the memo cannot land unguarded) |
| T7 | `test_repeated_private_view_json_serializes_once` | 10 calls with the same `(adapter, pid)` and no intervening `apply()` trigger exactly one projection **and one `json.dumps`**. A second player id on the same adapter triggers a second serialization (per-player keying, not a single-slot cache) | **FAIL** (currently 10 serializations) |
| T8 | `test_destroyed_adapter_does_not_serve_a_cached_view` | Warm the cache, `destroy()`, then call `private_view_json` — it raises as it does today rather than returning the cached string | **PASS** (control — currently raises `AttributeError` on `self._state._s`; L1 must not turn that into a silent stale read) |
| T9 | `test_determinize_does_not_change_board_occupancy` | **The invariant L2 depends on.** For K≥50 seeds across ≥10 roots, a determinized child's `_board_nodes_view()` equals its parent's. Written and passing *before* propagation is implemented, never after | **PASS** (control — `engine_c/state.c:271-318` touches only `hand`/`deck`/`discard_pile`, `market.deck`, `shuffle_seed`, `shuffle_counter`) |
| T10 | `test_engine_determinize_does_not_reference_board_state` | Structural trip-wire, same shape as the existing T5: scan `engine_determinize`'s body in `engine_c/state.c` and assert it contains no `->nodes`, `node_count`, `troop_slot`, or `spy` reference. If a future edit makes determinize board-touching, L2's propagation goes silently unsound; this catches it in C, where the invariant actually lives | **PASS** — a trip-wire, written now so it precedes any future editor |
| T11 | `test_clone_and_determinize_inherit_the_parent_projection` | After L2: a warm parent's `determinize()` and `deepcopy()` children perform **zero** fresh projections on their first view. **Replaces** `test_determinize_and_clone_get_independent_fresh_caches`, which asserts the opposite (§ 4.2) | **FAIL** (currently two fresh projections) |
| T12 | `test_inherited_projection_is_not_aliased_across_adapters` | Mutating the list — and the dicts inside it — returned by a child's `_board_nodes_view()` does not change what the parent or a sibling subsequently returns. `_board_nodes_view` currently returns `list(self._board_cache)`, a shallow copy whose inner dicts are shared: harmless within one adapter, a real hazard once shared across a family | **N/A before** — locks in the safe choice L2 forces |

### 4.2 Existing tests this plan invalidates

Both live in `openspiel_pyrants/tests/test_board_view_cache.py` and must be **edited with the
rationale in the docstring**, not silently deleted:

- `test_determinize_and_clone_get_independent_fresh_caches` asserts `spy.call_count == 2` —
  precisely the behaviour L2 removes. It is superseded by **T11**, and the reason it is safe to
  invert is **T9 + T10**, which lock down the engine invariant the old test was hedging against.
  Deleting it without landing T9/T10 first would trade a guarantee for an assumption.
- `test_repeated_calls_hit_the_cache` spies on `view.build_c_board_view`, which the adapter stops
  calling in Phase 2. It would pass vacuously at `call_count == 0`. Re-point it at the new
  projection entry point, and **verify it can still fail** by reverting the cache locally once.

`test_apply_is_still_the_only_state_reassignment_site` stays as-is — Phase 3 adds a cache clear to
`destroy()`, which does not add a `self._state =` site.

### 4.3 The corpus (T3's answer)

Random playouts do not place spies — 0 in 344 sampled states. Build the corpus from three sources
and assert its composition in T3 before trusting any differential:

1. Random playouts across ≥5 seeds (breadth, cheap).
2. Scenarios from `data/scenarios/` generated with `--require-spy-on-board`
   (`just generate-card-scenario <card_id> true`), which exists precisely for this.
3. Directed playouts that prefer `place_spy`/`deploy`/`assassinate`/`return_spy` when legal — the
   `_BOARD_MUTATING_MOVE_TYPES` set already defined in `test_board_view_cache.py:31`.

---

## 5. Phases 2–5 — GREEN, one lever per phase

### Phase 2 — L3: make the projection cheap (−286 ms, biggest lever)

Confined to `engine_c/bindings/c_adapter.py`, plus a memo in `view.py`/`engine_bindings.py`.

1. **Memoize sym-to-str.** One dict, one lookup. Sound because `intern_str` reads a global
   append-only `sym_strs` table (`engine_c/intern.c:79-82`) — a sym's string never changes for the
   life of the process. The three duplicate `_sym_str` definitions (`view.py:42`,
   `c_adapter.py:262`, `ce_api.py:75`) should share it; the profile shows 1,211,562 + 116,876 +
   43,795 calls in one short run. Expose `clear_sym_cache()` and wire it into a Python
   `intern_destroy()` wrapper — **T6**.
2. **Add a private `_project_board_nodes()` to `CEngineAdapter`** that reads `CGameView` directly
   into the six output fields. Do **not** modify `view.build_c_board_view` — it has three other
   consumers whose `adjacent_to`/`kind` fields are load-bearing (§ 4.2).
   - Preserve `spies` semantics exactly: filter falsy, then **sort**. Skip both when
     `spy_count == 0` (the common case, and worth 36 µs).
   - Preserve `troop_slots` semantics exactly: keep `None` entries, do not filter, do not sort.
3. **Hoist the board-static template** (`node_id`, `control_vp`, `total_control_vp_per_turn`) into a
   new `_board_static` slot. Store it **on the adapter**, not in a module-level dict keyed by node
   count — two boards can share a node count, and a definition pointer can be freed and reused.
   `_board_static` survives `apply()` (the definition is immutable) and propagates in Phase 4
   alongside the projection; `clone_via_replay` and `__init__` start it empty, since `create_game`
   may build a different definition. **T5** is the guard.
4. **Allocate a fresh `CGameView` per call.** Reusing a module-level 83 KB buffer saves 0.9 µs and
   introduces shared mutable state. Not worth it.

**Gate:** G1 (T1/T2), G3 (≤120 µs), G7. Re-run `f013b_census.py`.

### Phase 3 — L1: cache the serialized view per player (−120 ms)

`private_view_json(pid)` is a pure function of the C state and `pid`. The state changes only through
`apply()` — a property the existing structural trip-wire already enforces. So:

1. Add a `_view_cache` dict keyed by `player_id`, holding the finished JSON string. Keep
   `_board_cache` as the inner layer: Phase 4 propagates it, while the string cache cannot propagate
   because determinize *does* change hand/deck/discard.
2. Clear `_view_cache` in `apply()` **and in `destroy()`** — T8. Part A only needed the `apply()`
   site because a stale board after `destroy()` was unreachable; a cached full string is not.

**Gate:** G1, G2 (incl. T8), G4 (1076 repeat reads served without re-serialization), G7.

### Phase 4 — L2: propagate the projection across clone and determinize (−14 ms)

Only now, with T9/T10 landed and the projection already cheap:

1. `__deepcopy__` uses `engine_clone`, a byte copy; the child's board is identical by construction.
   Pass `_board_cache` and `_board_static` to the child.
2. `determinize` clones and then touches only hidden card zones, the market deck, and the shuffle
   seed (`state.c:271-318`). Pass both.
3. `clone_via_replay` replays from `create_game`; propagate **neither**.
4. Return an immutable projection (or a deep-enough per-call copy) so the shared structure cannot be
   mutated through one family member — **T12**.

**Gate:** G4 (≤700 projections per search), G1, G2, G6 — G6 matters most here, since this is the one
phase that could plausibly change *which* determinizations get explored if the invariant were wrong.

### Phase 5 — L4: stop re-serializing `board_nodes` (−70 ms) — conditional

Take this phase **only if** Phase 2–4's measured G5 leaves search wall-time above the § 1.4
projection. It is the only phase with real fragility.

Cache `json.dumps(board_nodes, sort_keys=True)` as a string alongside the projection, build the
result dict with a sentinel that JSON escapes deterministically and cannot occur in engine output
(assert its absence across the whole corpus first), then splice. G1's frozen reference vectors make
this mechanically verifiable — but if T1 cannot be made to pass on the first attempt, drop the phase
rather than negotiate with it.

---

## 6. Phase 6 — Re-run the battery against the gates

```
.venv/Scripts/python.exe -u docs/validation/harness/f013_timing.py  > docs/validation/baseline/f013b_timing.post.txt   # G5
.venv/Scripts/python.exe -u docs/validation/harness/f013b_census.py > docs/validation/baseline/f013b_census.post.txt   # G3, G4
.venv/Scripts/python.exe -u docs/validation/harness/inv_a.py    # G6 — INV-1 0/100 divergent
.venv/Scripts/python.exe -u docs/validation/harness/inv_b.py    # G6
.venv/Scripts/python.exe -u docs/validation/harness/inv_b2.py   # G6 — INV-5 mean 11.11/12
.venv/Scripts/python.exe -u docs/validation/harness/det_bot.py  # G6 — B1 1 distinct action
.venv/Scripts/python.exe -u docs/validation/harness/f002b.py    # G6 — 3/3
just openspiel-test ; just test ; just test-c                   # G7
git diff --stat                                                 # G0
```

Also re-run `just ismcts-perf 2 "--num-sims 200 --max-rounds 30"` and confirm
`information_state_string` is no longer the top cumulative entry. Note that cProfile inflates
Python-call-heavy paths relative to ctypes calls, and that its frame accounting is unreliable across
the pybind boundary (`c_rollout_evaluator.prior` reports `ncalls=3` against 1180 real calls) — use it
for ranking, and `f013b_census.py` for numbers.

---

## 7. Phase 7 — Review and update the record

1. **Review pass** — `docs/validation/reviews/f013-review-03.md`, same format as reviews 01/02.
2. **`findings.md`** — F-013 `Status:` becomes `CONFIRMED — FIXED (<sha>)` only if G5 clears;
   otherwise `CONFIRMED — MITIGATED` with the residual ratio stated. Keep the original 9.66×
   evidence intact.
3. **`verdict.md`** — record the measured post-fix ratio, and **correct the record on the C-level
   accessor**: § 9 is a factual reversal of a recommendation this repo has carried since
   `f011-fix-plan.md` § 10, and the reason (3.1 µs of 397 µs) belongs in the audit trail.
4. **Update `MEMORY.md` / `ismcts-performance-levers`** — item 1 currently tells a future session to
   "lead with F-013's narrow board-view accessor". That is now wrong and must be rewritten.

---

## 8. Honest projection for G5

| Configuration | Mean wall per search | vs. 0.1646 s reference |
|---|---|---|
| Pre-F-011 (no board in the info-state) | 0.1646 s | 1.00× |
| F-011 landed, no cache | 1.7453 s | 10.6× |
| Part A cache (current `HEAD`) | 1.0500 s | 6.38× |
| **Projected after Phases 2–4** | **~0.50–0.65 s** | **~3.0–3.9×** |
| Projected after Phase 5 | ~0.45–0.58 s | ~2.7–3.5× |

**This plan does not get under 2×, and should not claim it will.** The residual above 1× is the
irreducible cost of F-011's correctness fix: the info-state key legitimately contains the board and
the player's own discard, so 876 distinct states per search must each be projected and serialized at
all. Driving below 2× would mean changing what the key contains — an F-011 correctness question, not
a performance one, and out of scope here.

---

## 9. Withdrawn: the narrower C-level accessor

`f011-fix-plan.md` § 10, `f013-fix-plan.md` § 9, and `MEMORY.md`'s `ismcts-performance-levers` all
name a new `engine_build_board_view` C function as the recommended follow-up, reasoning that
`engine_build_view` "memsets a full `CGameView` and populates every card zone for every player + 3
special-stack scans, just to read `nodes`."

That reasoning is correct and the conclusion does not follow. Measured: the entire C call is
**3.1 µs**, and the `CGameView()` allocation another **0.9 µs**, against a **397.5 µs** total. A
perfect C-level accessor — zero memset, zero card zones, zero stack scans — could save at most
**0.8%** of the cost it was proposed to remove, while adding a C function, a header, a ctypes
binding, and a compile step to the maintenance surface.

**Recommendation: do not build it.** Revisit only if Phases 2–5 land and profiling then shows
`engine_build_view` among the top costs, which § 1.1 makes very unlikely.

---

## 10. Risks

| Risk | Mitigation |
|---|---|
| The rewritten projection differs on a field random playouts never exercise (`spies` is the live one — 0 of 344 sampled states had a spy) | T3 asserts corpus composition *before* T1/T2 are trusted; corpus built deliberately from `--require-spy-on-board` scenarios and directed playouts (§ 4.3) |
| The sym memo serves a stale string after `intern_destroy()` | T6, plus `clear_sym_cache()` wired into a Python `intern_destroy()` wrapper. The one live caller is `engine_c/bindings/test_label_enrich.py:343` |
| Hoisted board-static fields go stale if a card mutates node VP mid-game | T5 across 60 applies; the fields are read from `state->definition->board` (immutable) in `engine_c/view.c:74-76`. If T5 ever fails, drop the hoisting — it is 36 µs of the 326 µs saving, not the bulk |
| L2's propagation becomes unsound if `engine_determinize` later touches the board | T9 (behavioural, K≥50 seeds) **and** T10 (structural, reads `state.c` directly). Both land before the propagation |
| A shared projection mutated through one adapter corrupts a sibling | T12; return an immutable projection |
| L1 masks a genuine state change from a mutation site added later | The existing `test_apply_is_still_the_only_state_reassignment_site` trip-wire already fails on a fourth `self._state =` site |
| Phase 5's sentinel splice produces subtly different JSON | Frozen reference vectors (T1) make it mechanically checkable; the phase is conditional and droppable |
| Wall-clock gates are flaky | G5 lives in a harness script compared against a committed baseline, never in pytest — same convention as Part A |
