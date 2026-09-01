# F-013 Fix Plan — Cache the Board Projection on `CEngineAdapter`

**Defect:** `docs/validation/findings.md` § F-013 (MINOR, performance) — routing
`build_c_board_view` into `private_view_json` (landed for F-011, commit `a7cee83`) costs
~388 µs/call and regresses end-to-end ISMCTS search wall-time **9.66×** (measured:
0.1646 s → 1.5892 s per search, `num_sims=200`, N=10, `docs/validation/baseline/f011_timing.{pre,post}.txt`;
independently re-confirmed at 9.655× by `docs/validation/reviews/f011-review-01.md`).

**Hard constraint, stated by the requester and treated as a fifth mandatory process rule below,
not a suggestion: this fix must not change current simulation methods.** Concretely: zero edits
to `openspiel_pyrants/` (the OpenSpiel-facing layer — `state_c.py`, `game_c.py`,
`ismcts_factory.py`, `action_encoding_c.py`, `c_rollout_evaluator.py`), zero edits to
`scripts/run_ismcts.py`, and (trivially, since it is vendored) zero edits to the installed
`open_spiel.python.algorithms.ismcts` module. Every public method this fix touches keeps its
exact existing signature and returns byte-identical output for byte-identical input. This is a
transparent internal optimization to one class, `CEngineAdapter`, in
`engine_c/bindings/c_adapter.py` — nothing that calls it should be able to tell the difference
except by a stopwatch.

**Why this one, why now:** F-013 was opened by F-011's own G5 gate, which explicitly allowed
the correctness fix to ship ahead of the performance fix rather than block on it. It's the only
open item that isn't gated behind a bigger unresolved finding (F-004, F-002/F-003, F-006) — a
self-contained, low-risk cleanup.

---

## 0. Mandatory process constraints

The same three from `f010-fix-plan.md`/`f011-fix-plan.md`, plus one new one specific to this fix:

1. **Test-driven design is mandatory.** Every behavioural change starts as a failing test.
   Phase 2 does not begin until Phase 1's tests are written, run, and observed to **fail for the
   stated reason**.
2. **This change will be reviewed.** Phase 5 is required, not a courtesy pass.
3. **`docs/validation/verdict.md` must be updated.** Phase 6 rewrites the F-013 entry.
4. **No simulation-method changes.** Restated as Gate G0 below because it is the one condition
   under which this entire plan is void: if satisfying performance requires touching anything
   outside `engine_c/bindings/c_adapter.py` (plus this plan's own new test file and docs), stop
   and report back rather than widening scope. The narrower C-level accessor discussed in
   `docs/validation/f011-fix-plan.md` § 10 (a new `engine_build_board_view` C function) does not
   violate this constraint — it would live in `engine_c/`, not touch simulation code, and is
   explicitly **out of scope for this plan** (§ 11) regardless, because Phase 0's job is to find
   out whether caching alone is even enough before anything C-level is justified.

---

## 1. Root cause (verified, not assumed)

**The redundant call, proven from the algorithm's own code, not inferred.**
`.venv/Lib/site-packages/open_spiel/python/algorithms/ismcts.py:125-132`:

```python
root_infostate_key = self.get_state_key(state)
for _ in range(self._max_simulations):        # e.g. 200 iterations
    sampled_root_state = self.sample_root_state(state)
    assert root_infostate_key == self.get_state_key(sampled_root_state)   # <- calls information_state_string()
    self.run_simulation(sampled_root_state)
```

`sample_root_state` draws a fresh determinization every iteration — different hidden hand/deck/
discard contents each time — but never touches the board: `engine_determinize`
(`engine_c/state.c`) only reshuffles hidden zones. Site control, troop slots, and spies are
public and are never part of what a determinization changes. So this one `assert` line computes
`information_state_string()` → `private_view_json()` → `_board_nodes_view()` up to
`max_simulations` times per decision, for **the same board every time**, and keeps none of the
results. This is one proven redundant call site; deeper tree nodes revisited across multiple
simulations during UCT selection are extremely likely to repeat the same pattern (a node near
the root gets visited on most of the 200 simulations before the tree has grown enough to spread
out), though this plan does not need to prove that separately — Phase 4's timing gate measures
the aggregate effect directly rather than trying to count every redundant call site by hand.

**Where the cost actually goes.** `engine_c/bindings/c_adapter.py:225-240`
(`_board_nodes_view`, added by F-011) calls `build_c_board_view(self)`
(`engine_c/bindings/view.py:424`), which calls `_lib.engine_build_view` — one C function that
`memset`s and populates the *entire* `CGameView` struct (every player's hand/discard/played/
inner_circle/trophy_hall, the market row, three special-stack-count scans) regardless of the
fact that `_board_nodes_view` only reads back six fields per node. Confirmed cost (this
session's benchmark, mid-game state, N=2000-5000 calls): 388.1 µs/call vs. 24.1 µs/call for the
rest of `private_view_json` combined.

**The only two places `CEngineAdapter` reassigns `self._state` on an *existing* instance**
(verified via `grep -n "self\._state = " engine_c/bindings/c_adapter.py` — 3 hits total):

| Line | Site | Meaning for the cache |
|---|---|---|
| `c_adapter.py:38` | `__init__` | Not a mutation of an existing instance — every fresh/cloned/determinized adapter goes through `__init__`, so initializing the cache to empty here covers `__init__`, `__deepcopy__`, `determinize()`, and `clone_via_replay()` uniformly (all four construct via `CEngineAdapter(...)`, confirmed by reading each: `c_adapter.py:44-52`, `:70-79`, `:81-87`) |
| `c_adapter.py:111` | `apply()` | **The only place the board can change under an adapter that already has a cache.** This is the one required invalidation hook. |
| `c_adapter.py:248` | `destroy()` | Sets `_state = None`; the adapter is being torn down and is not meant to be queried again. No cache handling needed — any post-destroy call already fails elsewhere (`self._state._s` on `None`) before the cache would matter. |

This means the invalidation surface is exactly one line, not something that has to be hunted
for across the class.

**`__slots__` note.** `CEngineAdapter` declares
`__slots__ = ("_state", "_engine", "_player_ids", "_shuffle_seed", "_player_id_to_index")`
(`c_adapter.py:29`). A new attribute must be added to this tuple or assignment raises
`AttributeError` — a cheap, load-bearing detail to get right the first time, not discovered via
a failing test after the fact.

---

## 2. Acceptance gates

| Gate | Threshold |
|---|---|
| **G0 No simulation-method changes** | `git diff --stat` touches only `engine_c/bindings/c_adapter.py`, one new test file, and `docs/validation/*`. Zero diff in `openspiel_pyrants/`, `scripts/`, or anywhere under `.venv/` |
| G1 Behavioral parity | For any state, `private_view_json(pid)` returns **byte-identical** JSON before and after this fix, with or without the cache warm, for every player |
| G2 Cache invalidates on real mutation | After `apply()` of a board-mutating move, the very next `private_view_json`/`_board_nodes_view` call reflects the new board — never a stale one. This is the trap; see § 1's "the only two places" table and Phase 1's T3 |
| G3 Redundant recomputation actually drops | Across N calls to `_board_nodes_view()` on one adapter instance with no intervening `apply()`, the underlying `build_c_board_view`/`engine_build_view` call happens **once**, not N times |
| G4 Search wall-time recovers | `harness/f011_timing.py` (num_sims=200, N=10, same fixed root used for the original F-013 measurement) drops from the recorded 9.66× regression to **under 2×** (the original G5 threshold from `f011-fix-plan.md`). If it doesn't fully clear 2×, this plan still lands (it's a strict improvement either way) but Phase 6 must state the remaining gap honestly and note whether the C-level accessor (`f011-fix-plan.md` § 10) is still warranted — not overclaim a full fix |
| G5 Full regression suite unchanged, not just "passing" | Every harness script this repo has already captured a specific number for (`inv_a.py`, `inv_b.py`, `inv_b2.py`, `det_bot.py`, `f002b.py`) reproduces the **same** number, not merely a passing one — INV-1 0/100 divergent, INV-5 mean 11.11/12, `det_bot` B1 1 distinct action, F-002 3/3 unchanged. A caching bug that silently changes *which* determinizations get explored, or *which* action gets chosen, would still show "PASS" on a loose check while being a real regression; this fix has zero business changing any of these numbers, because G0 already establishes it cannot touch anything that would legitimately move them |
| G6 Existing suites green | `just openspiel-test`, `just test` — same 3 pre-existing unrelated failures as `f010-review-01.md`/`f011-review-01.md`, nothing new |

**G2 is this plan's version of the recurring trap** (F-010's G2, F-011's G2/G4): the naive
mistake here isn't leaking hidden information or collapsing world diversity, it's a cache that
looks like a clean win in benchmarks but silently serves a stale board after a real move,
because the one invalidation line got missed or misplaced. It must be asserted with a real
`apply()` call and a real board-content check, not inferred from the diff looking reasonable.

---

## 3. Phase 0 — Capture the red baseline

```
.venv/Scripts/python.exe -u docs/validation/harness/f011_timing.py > docs/validation/baseline/f013_timing.pre.txt
```

Expected content: same shape as the existing `f011_timing.post.txt` (mean ≈1.59 s, N=10,
num_sims=200) — this run's "post" from the F-011 plan is this plan's "pre." Re-capturing rather
than reusing the old file confirms the regression is still present and unchanged before this
fix touches anything (the working tree has moved since — F-004 work is in flight in parallel per
`git status`, so the baseline should be taken fresh, not assumed stale-but-still-valid).

---

## 4. Phase 1 — RED: tests first

New file: `openspiel_pyrants/tests/test_board_view_cache.py`, using the same `requires_c_engine`
fixture and `_load_c_game`/`_mid_game_state`-style helpers already established in
`test_ismcts_reproducibility.py` and `test_observation_completeness.py`.

Per the house pattern (write the anti-regression controls before the completing tests — F-010's
T6, F-011's T2/T4/T5): **T1 and T3 first**, since both describe invariants that must hold
regardless of whether caching exists yet, and G2 (T3) is the one failure mode that would look
like a passing benchmark and still be wrong.

| # | Test | Asserts | Pre-fix |
|---|---|---|---|
| T1 | `test_private_view_json_output_unchanged_by_caching` | For a fixed mid-game state, `private_view_json(pid)` returns the exact same string across 5 repeated calls with no mutation in between, for every player | **PASS** (control — currently true because every call recomputes fresh from the same unmutated state; must *stay* true once a cache is added, this is G1) |
| T3 | `test_cache_invalidates_on_board_mutating_apply` | Call `private_view_json(pid)` once, `apply()` a board-mutating move (a `deploy`/`place_spy` move, mirroring the move-type set already enumerated in `scripts/_state_snapshot.py::_BOARD_MUTATING_MOVE_TYPES`), call `private_view_json(pid)` again — the second call's `board_nodes` reflects the new occupancy, not the first call's | **PASS** (control — trivially true today, there is no cache yet to go stale; must *stay* true, this is G2, the direct answer to "what if a legal move changes the board") |
| T2 | `test_repeated_calls_hit_the_cache` | Monkeypatch/spy on `engine_c.bindings.view.build_c_board_view` (or count calls another way that doesn't touch simulation code — a `unittest.mock.patch` inside the test file only, not production code); call `private_view_json(pid)` 10 times with no intervening `apply()`; assert the underlying board-projection call happened **exactly once** | **FAIL** (currently called 10 times) |
| T4 | `test_determinize_and_clone_get_independent_fresh_caches` | `adapter.determinize(pid, seed)` and `copy.deepcopy(adapter)` each produce a new adapter whose first `private_view_json` call computes fresh (not silently inheriting the parent's cached object) — assert via identity/monkeypatch-count, not just value equality, since a bug that shares a Python list reference across instances would still pass a value-equality check | **N/A before** (no cache exists to accidentally share) — locks in the safe default chosen in § 5 |
| T5 | `test_apply_is_still_the_only_state_reassignment_site` | Guard against future drift: `grep`/`ast`-scan `c_adapter.py` for `self\._state = ` and assert it still appears at exactly the 3 known lines (`__init__`, `apply`, `destroy`) — if a future edit adds a fourth mutation site without updating the cache invalidation, this test catches it structurally instead of relying on someone remembering | **N/A before** — a structural trip-wire, not a behavior test; written now so it exists in git history before any future editor could introduce a fourth site |
| T6 | `docs/validation/harness/f013_timing.py` (script, not pytest — wall-clock is flaky in CI) | Same shape as `f011_timing.py`: N=10 searches, num_sims=200, one fixed root, mean wall-time vs. `baseline/f013_timing.pre.txt` | N/A before — **this becomes gate G4 in Phase 4** |

T1/T3/T4/T5 all pass before any production code changes (they're describing what must remain
true, not what's currently broken) — run them anyway and confirm they pass **for the right
reason** (i.e., T4/T5 aren't accidentally vacuous) before writing T2, which is the one genuinely
red test.

---

## 5. Phase 2 — GREEN: minimal implementation

Entirely confined to `engine_c/bindings/c_adapter.py`. Three edits, in this order.

**5.1 Add the cache slot.**

```python
__slots__ = ("_state", "_engine", "_player_ids", "_shuffle_seed", "_player_id_to_index",
             "_board_cache")  # NEW
```

**5.2 Initialize it in `__init__`** (covers every construction path — fresh, `__deepcopy__`,
`determinize()`, `clone_via_replay()` — since all four go through `CEngineAdapter(...)`):

```python
def __init__(self, c_state, c_engine, player_ids, shuffle_seed):
    self._state = c_state
    self._engine = c_engine
    self._player_ids = list(player_ids)
    self._shuffle_seed = shuffle_seed
    self._player_id_to_index = {pid: i for i, pid in enumerate(player_ids)}
    self._board_cache = None  # NEW — always starts empty; see f013-fix-plan.md § 1 for why
                               # clones/determinizations deliberately do NOT inherit a parent's
                               # cached value even though their board is identical at
                               # construction time (T4 locks this in as the safe default,
                               # not an oversight — see § 6 for the reviewable alternative)
```

**5.3 Cache-and-invalidate.**

```python
def apply(self, move) -> None:
    new_state = self._engine.apply(self._state, move)
    if new_state is None:
        ...  # unchanged
    self._engine.destroy(self._state)
    self._state = new_state
    self._board_cache = None  # NEW — the one required invalidation (G2)

def _board_nodes_view(self) -> list[dict]:
    if self._board_cache is None:
        from .view import build_c_board_view
        view = build_c_board_view(self)
        self._board_cache = [
            {
                "node_id": n.node_id,
                "troop_slots": list(n.troop_slots),
                "spies": list(n.spies),
                "control_vp": n.control_vp,
                "total_control_vp_per_turn": n.total_control_vp_per_turn,
                "vp_tokens": n.vp_tokens,
            }
            for n in view.board_nodes
        ]
    return list(self._board_cache)  # shallow copy — see § 6, the one judgment call
```

Nothing in `private_view_json`, `_build_public_dict`, or any signature changes. The Tier-1 path
(`_tier1_snapshot` → `_build_public_dict` directly) never calls `_board_nodes_view` and is
untouched, exactly as it was left untouched by F-011.

Run T1–T6. T2 should now pass; T1/T3/T4/T5 must still pass, unchanged in meaning, not just in
outcome.

---

## 6. Phase 3 — Guard against silent regression, and the one judgment call

**The judgment call, flagged for the reviewer rather than decided unilaterally:**
`_board_nodes_view()` returns `list(self._board_cache)` — a shallow copy of the outer list —
rather than the cached list object itself. The per-node dicts inside are still shared references
(not deep-copied). This costs a few microseconds (copying ~81 list-element references), which is
noise next to the 388 µs this fix is trying to avoid paying repeatedly. The alternative — return
`self._board_cache` directly, no copy — is marginally faster and currently just as safe, because
the only consumer today (`private_view_json`) immediately hands the result to
`json.dumps(..., sort_keys=True)`, which never mutates its input. The shallow copy is insurance
against a *future* caller that mutates the returned list in place (e.g., someone later adds
sorting, filtering, or annotation logic to a board view before serializing it) silently
corrupting the cache for every subsequent call on that adapter. Recommended default: keep the
shallow copy. Overriding it to return the bare cached list is a one-line change if the reviewer
judges the extra insurance isn't worth it.

**T5 (§ 4) is the permanent structural guard** — kept in the suite after this fix lands, not
deleted, so a future edit that adds a fourth `self._state = ` mutation site without adding a
matching `self._board_cache = None` gets caught by a failing test rather than a silent stale-read
bug discovered later during an ISMCTS run.

---

## 7. Phase 4 — Re-run the invariant battery against the gates

```
.venv/Scripts/python.exe -u docs/validation/harness/f013_timing.py  # G4 — compare to baseline/f013_timing.pre.txt
.venv/Scripts/python.exe -u docs/validation/harness/inv_a.py        # G5 — INV-1/2/3/6 must reproduce the exact recorded numbers
.venv/Scripts/python.exe -u docs/validation/harness/inv_b.py        # G5 — INV-4a/INV-5, expect mean 11.11/12 unchanged
.venv/Scripts/python.exe -u docs/validation/harness/inv_b2.py       # G5 — INV-4b, expect 403/403 unchanged
.venv/Scripts/python.exe -u docs/validation/harness/det_bot.py      # G5 — B1 must still show exactly 1 distinct chosen action
.venv/Scripts/python.exe -u docs/validation/harness/f002b.py        # G5 — F-002, previously-CONFIRMED and inside this fix's radius only incidentally (shares no code, but private_view_json's fingerprint use means it's cheap to re-confirm)
just openspiel-test                                                  # G6
just test                                                             # G6
```

**Expected results, written down before running:** every number above matches its most recently
recorded value exactly (not "still passes" — the *same number*). G4's ratio is the only number
expected to move, and it should move toward 1× (ideally landing well under the 2× gate, given
§ 1's analysis that the known redundant call alone accounts for up to 200 recomputations
collapsing to 1 per decision at the root). If G5's numbers move at all, stop — per G0, nothing
in this fix should be able to change them, so any drift means the cache is doing something more
than caching.

---

## 8. Phase 5 — Review (required gate)

Run `/code-review` on the branch diff, then a pass against this checklist:

- [ ] **G0 mechanically verified** — `git diff --stat` (or `git diff --name-only`) shows only
      `engine_c/bindings/c_adapter.py`, the new test file, `docs/validation/f013-fix-plan.md`,
      and `docs/validation/{findings.md,verdict.md}`. Anything else present is out of scope and
      must be justified or reverted before this can be accepted.
- [ ] **G2 explicitly re-verified with a live repro**, not just T3's pass — reviewer manually
      drives one `private_view_json` → `apply(board-mutating move)` → `private_view_json`
      sequence and confirms the second result differs where it should.
- [ ] Every production edit traces to a test that was red first (T2's before/after evidence
      attached).
- [ ] The shallow-copy judgment call (§ 6) is accepted or consciously overridden.
- [ ] T5's structural trip-wire genuinely fails if a fourth `self._state = ` site is added
      (reviewer temporarily adds one locally, confirms T5 catches it, reverts).
- [ ] G5's "same exact numbers, not just passing" claim is checked against the actual prior
      recorded values in `verdict.md`/`findings.md`, not eyeballed.
- [ ] G4's measured ratio is reported honestly, including if it doesn't fully clear 2×.

---

## 9. Phase 6 — Update the audit record (required)

1. **`docs/validation/verdict.md`** — update F-013's entry with the new measured ratio and
   mark it resolved (or partially resolved, honestly, if G4 doesn't fully clear) rather than
   leaving it as an open performance note.
2. **`docs/validation/findings.md`** — F-013 `Status:` becomes `**CONFIRMED — FIXED** (<commit
   sha>)` or `**CONFIRMED — MITIGATED**` if G4 lands above 1× but under 2×, keeping the
   original 9.66× evidence intact.
3. If G4 does not clear 2×, explicitly restate whether the narrower C-level accessor
   (`f011-fix-plan.md` § 10) is now recommended as a follow-up, with the residual ratio as the
   justification — don't let the record go quiet on an incomplete fix.

---

## 10. Risks

| Risk | Mitigation |
|---|---|
| Cache serves a stale board after a real move | G2 / T3, the load-bearing test, written before any implementation exists |
| A future edit adds a new mutation path to `CEngineAdapter` without updating invalidation | T5's structural trip-wire, kept permanently in the suite |
| Caching accidentally changes *which* determinizations or actions get explored (not just speed) | G5's "exact same recorded numbers" standard, stricter than "still passes" |
| Fix scope creeps into `openspiel_pyrants/`/`scripts/` to "make it easier" | G0, checked mechanically via `git diff --stat`, not by intention |
| Shallow-copy defensive return masks a future bug where a caller expects to mutate the cache in place | Explicitly documented as a judgment call (§ 6) rather than silently chosen, so a reviewer can override it deliberately |
| Caching doesn't fully close the 9.66× gap (deeper-tree unique-board calls dominate) | G4 measured honestly; Phase 6 reports the residual and whether the C-level accessor is still warranted, rather than declaring victory on a partial win |

## 11. Out of scope

The narrower C-level `engine_build_board_view` accessor (`f011-fix-plan.md` § 10) — this plan
exists specifically to find out, by measurement, whether that's still needed after the free win
here. F-002, F-003, F-004, F-006, F-012 — unrelated, each with its own plan or verdict
condition. Any change to `openspiel_pyrants/` or `scripts/run_ismcts.py` — forbidden by G0, not
merely deprioritized.
