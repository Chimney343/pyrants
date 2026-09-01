# F-011 Fix Plan — Board State in the Observation

**Defect:** `docs/validation/findings.md` § F-011 (CRITICAL) — the entire board (sites, troops,
spies, control) and a player's own discard-pile contents are absent from
`information_state_string`/`observation_string`. 403/403 board-differing state pairs produced a
byte-identical observation.

**Why this one next:** `docs/validation/verdict.md` § 5 names F-011 condition 1, the first
blocking gate for GO, and its own framing of the overall NO-GO is this finding's headline:
*"what the search is searching over is still not the game."* F-010 (fixed, `028ff9d` +
`2cfd836`, pending re-review) made results reproducible; F-011 is the first defect that
reproducibility now lets us actually verify a fix for.

---

## 0. Mandatory process constraints

Same three as `f010-fix-plan.md`, restated because they are non-negotiable, not
finding-specific:

1. **Test-driven design is mandatory.** Every behavioural change starts as a failing test.
   Phase 2 does not begin until Phase 1's tests are written, run, and observed to **fail for the
   stated reason**.
2. **This change will be reviewed.** Phase 5 is required, not a courtesy pass.
3. **`docs/validation/verdict.md` must be updated.** Phase 6 rewrites the F-011 entry, the
   INV-4b row, and the § 5 GO/NO-GO conditions. A fix that lands without the verdict update
   leaves the audit record lying.

---

## 1. Root cause (verified, not assumed)

Two separate absences, confirmed by reading the installed source this session, both inside the
same two functions:

**(a) Board is never read.** `engine_c/bindings/c_adapter.py:158-198`
(`CEngineAdapter._build_public_dict`) builds its dict entirely from `self._state._s` — round,
phase, current player, market row, resource pool, and per-player *counts*
(`hand_count`/`deck_count`/`discard_pile_count`/...). It never touches `self._state._s.nodes`
(the board — sites, routes, troop slots, spies). `private_view_json`
(`c_adapter.py:200-222`) wraps that same dict and adds only the requesting player's own `hand`
and zone-content lists (`played_cards`, `inner_circle`, `trophy_hall`) — never the board.
`state_c.py:212-232` (`information_state_string`/`observation_string`) both route through
`private_view_json` verbatim, so the board is absent from the OpenSpiel-facing API too, not
just an internal struct.

A full board projection **already exists** and is fully public:
`engine_c/bindings/view.py:424-439` (`build_c_board_view`), backed by the C function
`engine_c/view.c::engine_build_view` (`engine_c/view.h:68`). It is already used today by
`scripts/_state_snapshot.py::_tier2_snapshot` for the per-round observability log — confirmed
by `docs/validation/harness/inv_b.py`/`inv_b2.py`, which both call it (via
`scripts._state_snapshot._tier2_snapshot`) to build the "omniscient" fingerprint that proves the
board differs between states even though `private_view_json` does not. **No new C code and no
new board-projection logic is needed** — the projection exists; it simply was never routed into
the observation.

**(b) Own discard-pile identities are never read.** `private_view_json` builds `hand` from
`p.hand`/`p.hand_count` (`c_adapter.py:206`) but only reads `p.discard_pile_count`
(`c_adapter.py:212`), never `p.discard_pile` itself. The struct field exists and is the exact
same shape as `hand`: `engine_c/bindings/engine_bindings.py:206` —
`("discard_pile", Sym * MAX_ZONE_SIZE), ("discard_pile_count", c_int)`, parallel to
`engine_bindings.py:205`'s `("hand", Sym * MAX_ZONE_SIZE), ("hand_count", c_int)`. This is
distinct from F-007 (REFUTED): F-007 asked whether an *opponent's* discard pile should be
visible and found no rule ever depends on it. This is a player's own discard, which 12 cards in
`data/cards/*.json` require selecting a card *from* — confirmed present in F-011's own citation.

**Load-bearing detail #1 — do not touch the shared function.**
`_build_public_dict()` has **two callers**, not one: `private_view_json` (the one that needs
fixing) and `scripts/_state_snapshot.py::_tier1_snapshot` (`c_adapter.py` is called directly as
`adapter._build_public_dict()`), which is the **cheap, every-successful-step** streaming
snapshot built in the ISMCTS crash-safety/logging work (`bfc8c15`, `3b6b23d`). Its own docstring
states the two-tier split exists *because* `_tier2_snapshot` (which wraps `build_c_board_view`)
is "pricier ... callers should only invoke it on round boundaries and board-mutating moves."
Measured this session (`.venv/Scripts/python.exe`, mid-game state, N=2000-5000 calls,
`time.perf_counter`):

| Call | Cost |
|---|---|
| `adapter._build_public_dict()` (current) | **7.8 µs/call** |
| `adapter.private_view_json(pid)` (current) | **24.1 µs/call** |
| `build_c_board_view(adapter)` | **388.1 µs/call** — ~16× `private_view_json`'s current cost |

Reading `engine_c/view.c::engine_build_view` explains the gap: it is one monolithic C function
that `memset`s the entire `CGameView` struct and unconditionally populates **every** zone for
**every** player (hand/discard/played/inner_circle/trophy_hall, sized
`MAX_PLAYERS(4) × MAX_ZONE_SIZE(80)`, `engine_c/state.h:14-17`) plus every board node
(`MAX_NODES(128)`) and three `remaining_special_stack_count` scans — regardless of the fact that
`build_c_board_view`'s Python wrapper only reads the `nodes`/aggregate fields back out.
`build_c_board_view` is not a "cheap board-only" C call; it is the full state projection with
most of the output discarded on the Python side.

If board data is added to `_build_public_dict()` directly, `_tier1_snapshot`'s per-step cost
rises from 7.8 µs to something like the 388 µs figure above — a ~50× regression on a path that
runs every single ISMCTS step, defeating the two-tier design that was built specifically to
avoid this. **The fix must add board data at the `private_view_json` layer only, leaving
`_build_public_dict()` and `_tier1_snapshot` byte-for-byte unchanged.** This is Guard G4 below.

**Load-bearing detail #2 — do not embed the current-player-scoped aggregates.**
`CBoardViewData` (`view.py:90-97`) carries `current_player_controlled_sites` /
`current_player_total_control_sites` / `current_player_control_vp` /
`current_player_total_control_vp` alongside `board_nodes`. These four are computed in
`engine_build_view` (`view.c:87-108`) strictly relative to `state->current_player_id` — **not**
the `player_id` argument `private_view_json(player_id)` is called with. `private_view_json` is
called once per player as observer (confirmed: `information_state_string(player)` is called for
every `player` OpenSpiel asks about, not only the current mover). Embedding these four fields
verbatim would silently report the *current* player's control stats inside every *other*
player's observation — a new, self-inflicted correctness bug. **Only the per-node raw occupancy
array (`board_nodes`: `node_id`, `troop_slots`, `spies`, `control_vp`,
`total_control_vp_per_turn`, `vp_tokens`) is player-agnostic and safe to embed as-is** — it is
ground truth every player already sees at the table; any consumer that wants "sites player X
controls" can derive it from `troop_slots`/`spies`, the same way
`scripts/_state_snapshot.py::_derive_site_controller` already does for the human-facing GUI/log
path (left untouched — this fix does not need or reuse that derivation, only the raw node data
one layer below it).

---

## 2. Acceptance gates

From `verdict.md` § 5 condition 1, plus guards this plan adds for the two traps found above:

| Gate | Threshold |
|---|---|
| G1 Completeness | INV-4b passes at **N ≥ 400** board-differing pairs (`harness/inv_b2.py`) |
| G2 No new leakage | INV-4a still passes at **N ≥ 300** (`harness/inv_b.py`) — two determinizations of one information set must still produce an identical observation for the *same* observing player |
| G3 Own-only discard | The observing player's own discard-pile identities appear in their own `private_view_json`; a *different* player's `private_view_json` never contains them (only `discard_size`, as today) |
| G4 Tier-1 cost untouched | `_build_public_dict()` returns the exact same key set as before this fix, and its measured per-call cost stays within run-to-run noise of the **7.8 µs** baseline captured in § 1 (no `board_nodes` key, no cost regression) |
| G5 Search-time budget | End-to-end ISMCTS wall-time at a fixed `num_sims`, measured before/after, does not regress by more than **2×**. If it does, this plan still lands (correctness first) but Phase 6 must open a follow-up finding for a narrower C-level board accessor rather than silently shipping the slowdown |
| G6 Existing suites green | `just openspiel-test`, `just test`, and `tests/test_state_snapshot.py` (unaffected — not touched by this fix) all pass |

**G2 is the trap**, in the same shape as F-010's G2: the naive over-fix here isn't collapsing
world diversity, it's leaking *hidden* information while fixing the *observed* gap — e.g.
routing something determinization-sensitive into the board dict by accident, or (see § 1 detail
#2) embedding a field that varies by more than just the board. G2 must be asserted with a real
run, not assumed from reading the diff.

---

## 3. Phase 0 — Capture the red baseline

```
.venv/Scripts/python.exe -u docs/validation/harness/inv_b.py   > docs/validation/baseline/inv_b.pre.txt   # already exists from F-010; re-capture to confirm unchanged
.venv/Scripts/python.exe -u docs/validation/harness/inv_b2.py  > docs/validation/baseline/inv_b2.pre.txt  # NEW capture — F-011's own decisive test was never saved as a baseline file
```

Expected content: INV-4a PASS N=300 (0 violations); INV-4b-DECISIVE **N=403, 403/403
`private_view_json` IDENTICAL (board invisible)** — this is the number G1 must move off of.
Also record the § 1 timing table above as `docs/validation/baseline/f011_timing.pre.txt` (a new,
small timing script — see Phase 1 T6) so Phase 4's G5 comparison has a saved "before".

---

## 4. Phase 1 — RED: tests first

New file: `openspiel_pyrants/tests/test_observation_completeness.py`, using the same
`requires_c_engine` fixture (`openspiel_pyrants/tests/conftest.py`) and `_load_c_game` /
`_mid_game_state` helper pattern as `test_ismcts_reproducibility.py`. Write all eight, run them,
confirm the expected-fail set fails **for the right reason**, before writing any production
code.

Per the house pattern established in `f010-fix-plan.md` § 4 (T6 there): **write the anti-overfix
controls (T2, T4, T5 here) before the completeness tests (T1, T3, T7, T8)**, so the invariants
they lock in exist in git history before the fix that could break them.

| # | Test | Asserts | Pre-fix |
|---|---|---|---|
| T2 | `test_determinization_does_not_change_own_observation` | INV-4a-shaped control: for one info set, two `resample_from_infostate` calls with different `RandomState` seeds produce identical `private_view_json(observing_player)` | **PASS** (control — board isn't there yet, so trivially identical; must *stay* identical post-fix for the real reason: board is public and doesn't vary within an information set) |
| T4 | `test_opponent_discard_pile_still_not_leaked` | Player A's `private_view_json` contains no card identity from player B's discard pile — only `discard_size` for B, everywhere B is described | **PASS** (control — vacuously true today since no one's discard is shown; must stay true post-fix when A's *own* discard becomes visible) |
| T5 | `test_tier1_snapshot_shape_and_cost_unaffected` | `set(adapter._build_public_dict().keys())` is unchanged from a captured pre-fix key set, and its measured per-call cost stays under (baseline × 3) over 500 calls (loose bound — this is a shape/regression guard, not a micro-benchmark) | **PASS** (control — nothing has touched `_build_public_dict` yet; must stay passing, this is gate G4) |
| T1 | `test_board_visible_when_only_site_differs` | Mirrors `inv_b2.py`'s decisive check directly at the `private_view_json` layer: two clones of one state, same move *type*, different target site, boards genuinely differ (`board_fp` differs) ⇒ `private_view_json(p)` differs too | **FAIL** |
| T3 | `test_own_discard_pile_identities_visible` | Force a known card into a player's discard pile (via direct `resolve_generic`/scenario setup, mirroring `tests/c_engine` card-test helpers), assert its card_id appears in that player's own `private_view_json` | **FAIL** |
| T7 | `test_information_state_string_reflects_board` | Same as T1 but through the public `pyspiel.State` API (`state.information_state_string(p)` / `state.observation_string(p)`), not the adapter directly — this is the end-to-end contract OpenSpiel and any future consumer actually relies on | **FAIL** |
| T8 | `test_board_nodes_order_is_deterministic` | Two independent builds of the identical state (same clone, called twice) produce `board_nodes` in identical list order — guards the "list order isn't sorted by `sort_keys=True`" hazard noted in § 1, since `information_state_string` is used as an ISMCTS node key and must be stable | **FAIL** (key doesn't exist yet) |
| T6 | `docs/validation/harness/f011_timing.py` (script, not pytest — wall-clock assertions are flaky in CI) | End-to-end `make_bot` search wall-time at fixed `num_sims=200`, N=10 searches from one mid-game root, mean wall-time vs. the Phase-0-captured baseline | N/A before (nothing to compare yet) — **this becomes gate G5 in Phase 4** |

---

## 5. Phase 2 — GREEN: minimal implementation

Two edits, in this order, both confined to `engine_c/bindings/c_adapter.py`. Neither touches
`_build_public_dict()`.

**5.1 Own discard-pile identities.** In `private_view_json`, next to the existing `hand` line:

```python
hand = [_sym_str(p.hand[i]) for i in range(p.hand_count)]
discard = [_sym_str(p.discard_pile[i]) for i in range(p.discard_pile_count)]  # NEW

result = {
    "public": pub,
    "hand": hand,
    "discard": discard,  # NEW — own identities; discard_size (below) is kept for compatibility
    "deck_size": p.deck_count,
    "discard_size": p.discard_pile_count,
    ...
}
```

**5.2 Board occupancy, at the `private_view_json` layer only.**

```python
def private_view_json(self, player_id: str) -> str:
    pub = self._build_public_dict()          # UNCHANGED call, UNCHANGED cost
    ...
    result = {
        "public": {**pub, "board_nodes": self._board_nodes_view()},  # NEW, merged here only
        "hand": hand,
        "discard": discard,
        ...
    }
    return json.dumps(result, sort_keys=True)

def _board_nodes_view(self) -> list[dict]:
    """Player-agnostic raw board occupancy. Only the per-node fields — never the
    current-player-scoped aggregates on CBoardViewData, which are relative to
    state->current_player_id, not whichever player_id is asking. See f011-fix-plan.md § 1."""
    from .view import build_c_board_view
    view = build_c_board_view(self)
    return [
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
```

`{**pub, "board_nodes": ...}` builds a **new** dict at the `private_view_json` call site instead
of mutating whatever `_build_public_dict()` returned in place — `_tier1_snapshot`, which calls
`_build_public_dict()` directly and never sees this new key, is untouched by construction, not
by convention. `kind`/`adjacent_to` are left out of the projection: both are static board
topology fixed at game setup, carry no per-state information, and are already implicit in the
board definition any consumer can load from `data/boards/*.json` — omitting them keeps the
per-call payload smaller without losing anything actually observable.

Run T1–T8 (T6 as a script, not part of the pytest run). All should now pass except whatever T6
reports for G5, which is a measurement, not a pass/fail assertion at this phase.

---

## 6. Phase 3 — Guard against silent regression

Unlike F-010, there is no single "unreachable without raising" guard to add here — the defect
was an *omission*, not a bypassable fallback path, so there is no equivalent of F-010's `raise
TypeError`. The regression risk here is different in kind: **a future edit that adds a new field
to `_build_public_dict()` for a legitimate Tier-1 reason could silently re-couple the two
tiers' costs again**, or a future edit to `private_view_json` could reintroduce a
current-player-scoped field (§ 1 detail #2) by copying from `CBoardViewData` wholesale instead
of the per-node array. Two structural guards, both cheap to keep green forever:

- T5 (shape/cost guard on `_build_public_dict()`) stays in the permanent suite, not deleted
  after this fix lands — it is the guard against tier re-coupling.
- Add one more locked-in assertion inside T7 (or a dedicated T9, reviewer's call): that
  `private_view_json`'s `board_nodes` entries contain none of `current_player_controlled_sites`
  / `current_player_total_control_sites` / `current_player_control_vp` /
  `current_player_total_control_vp` as keys anywhere in the payload — a direct trip-wire for § 1
  detail #2 recurring.

---

## 7. Phase 4 — Re-run the invariant battery against the gates

No new harness scripts needed for G1/G2 — `inv_b.py`/`inv_b2.py` already implement exactly
these checks (they were written to detect this defect in the first place) and just need
re-running against the fixed code:

```
.venv/Scripts/python.exe -u docs/validation/harness/inv_b2.py   # G1 — INV-4b, N>=400 (widen from 403 to >=400 if the loop cap needs raising)
.venv/Scripts/python.exe -u docs/validation/harness/inv_b.py    # G2 — INV-4a must stay PASS at N>=300; also re-confirms INV-5 (F-010's gate) is undisturbed
.venv/Scripts/python.exe -u docs/validation/harness/f011_timing.py  # G5 — compare to baseline/f011_timing.pre.txt
just openspiel-test                                              # G6
just test                                                         # G6
```

**Expected post-fix results** — written down before running, any mismatch is unresolved, not a
pass:

- INV-4b: PASS, 0 board-differing-but-observationally-identical pairs at N ≥ 400 (was 403/403
  fail).
- INV-4a: unchanged, PASS at N ≥ 300, 0 violations.
- INV-5 (F-010's world-diversity gate, in the same script): unchanged, mean ≈10.26/12,
  0 singletons — this fix touches a different code path but INV-5 shares a harness file with
  INV-4a/4b, so re-confirm it wasn't disturbed as a byproduct.
- `_build_public_dict()` cost: within noise of 7.8 µs/call; no `board_nodes` key present.
- Search wall-time: report the actual ratio. Under 2× → G5 clears cleanly. Over 2× → land the
  correctness fix anyway (per G5's own text) and open a follow-up finding at Phase 6 for a
  narrower `engine_build_board_view`-only C function that skips the card-zone and
  special-stack-count work `engine_build_view` currently always does.
- F-002, F-010 (both previously touched/CONFIRMED, sharing no code with this fix): not expected
  to move; not re-measured here beyond the INV-5 byproduct check above — out of this plan's
  radius.

---

## 8. Phase 5 — Review (required gate)

Run `/code-review` on the branch diff, then a pass against this checklist:

- [ ] Every production edit traces to a test that was red first (Phase 1 evidence attached).
- [ ] **G2 explicitly re-verified** — reviewer confirms no hidden-information leakage was
      introduced. This is the failure mode most likely to look like a fix and still be wrong.
- [ ] **G4 explicitly re-verified** — `_build_public_dict()` diff is empty; `_tier1_snapshot`'s
      output and cost are unchanged. Grep confirms `board_nodes` appears nowhere except inside
      `private_view_json`'s own merged dict.
- [ ] **The current-player-aggregate omission (§ 1 detail #2) is confirmed deliberate** — reviewer
      checks that `CBoardViewData.current_player_*` fields are not present anywhere in
      `private_view_json`'s output for any player.
- [ ] G5's measured ratio is reported, whichever side of 2× it lands on, and if over, a
      follow-up finding was actually opened, not just mentioned in a comment.
- [ ] T8 (node-order determinism) genuinely exercises two independent builds, not the same
      Python list re-serialized twice.
- [ ] Pre/post harness outputs (`inv_b.pre/post.txt`, `inv_b2.pre/post.txt`,
      `f011_timing.pre/post.txt`) are attached to the review.

---

## 9. Phase 6 — Update the audit record (required)

1. **`docs/validation/verdict.md`**
   - § 1: flip the INV-4b row to ✅ PASS with the new N and command; note INV-4a/INV-5 were
     re-confirmed as a byproduct of the same harness run.
   - § 2 CRITICAL: move F-011 into a resolved section with the fixing commit and post-fix
     INV-4a/4b evidence, following the same format F-010 used.
   - § 5: strike condition 1, promote conditions 2–4 (F-004; F-002+F-003; F-006), restate
     GO/NO-GO. Verdict likely **stays NO-GO** — F-004 (3–4 player `Returns()` contract) and
     F-002/F-003 (shared reshuffle stream) are unaffected by this fix and remain open.
   - If G5's ratio exceeded 2×, add the follow-up finding here and cross-reference it.
2. **`docs/validation/findings.md`** — F-011 `Status:` becomes `**CONFIRMED — FIXED** (<commit
   sha>)`, original observed evidence kept intact.
3. Note explicitly (mirroring F-010's F-002 cross-reference) that this fix changes
   `information_state_string`'s **string value** for every non-terminal state (board is now
   part of it) — any saved fingerprint, hash, or `artifacts/ismcts/` run predating this commit is
   not byte-comparable to a post-fix run, even though the *game* is unchanged. This is expected
   and does not itself invalidate any STRENGTH row beyond what F-010's own fix already did.

---

## 10. Risks

| Risk | Mitigation |
|---|---|
| Board data leaks something hidden-per-determinization | G2 (INV-4a), asserted at N≥300 before this is considered done, not assumed from the fact that troops/spies are "supposed to be" public |
| Fix silently re-couples Tier-1 and Tier-2 costs | G4 + T5, kept as a permanent regression guard, not a one-time check |
| `current_player_*` aggregate fields get embedded by a future refactor | Phase 3's trip-wire assertion, kept in the permanent suite |
| ISMCTS search throughput regresses materially | G5 measured explicitly; a >2× regression still ships (correctness first) but forces a tracked follow-up rather than silent acceptance |
| `board_nodes` list order varies run-to-run, corrupting the node-key use of `information_state_string` | T8, locks in determinism; root cause (fixed C array iteration order) already makes this unlikely, but "unlikely" isn't "tested" |
| Historical fingerprints/hashes built from `private_view_json` change | Expected and stated explicitly in Phase 6.3, same posture F-010 took for `artifacts/ismcts/` runs |

## 11. Out of scope

F-002, F-003, F-004, F-006, F-008, F-009 — each has its own verdict condition, do not bundle.
The narrower C-level `engine_build_board_view` accessor (only if G5 fails) is explicitly a
follow-up, not part of this plan's Phase 2. Re-measuring INV-7/8/9 (STRENGTH rows, already STALE
from the F-010 review) is not this plan's job either — it belongs to the final gate once every
blocking finding is fixed.
