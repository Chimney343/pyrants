# IS-MCTS Perf Optimization Plan

Profile source: `just ismcts-perf` (num-sims 3, num-games 1, max-rounds 2, workers 1).
Run = 105.1s, 25 decisions, 252M function calls.
Raw data: `artifacts/ismcts/performance_testing/cprofile_top.txt` + `cprofile.pstats`.

## Profile findings (tottime, top of run)

| Rank | Function | tottime | cumtime | ncalls | meaning |
|------|----------|---------|---------|--------|---------|
| 1 | `engine/state.py:32 _copy_field` | 37.56s | 84.42s | 66.8M | per-field clone recursion |
| 2 | `engine/state.py:72 _model_deepcopy_fields` | 30.74s | 82.12s | 10.7M | submodel clone |
| 3 | `dict.get` | 8.66s | 8.66s | 79.6M | `_TYPE_DISPATCH.get(type(value))` in `_copy_field` |
| 4 | `builtins.any` | 2.79s | 4.49s | 6.47M | troop-slot scans |
| 5 | `set.copy` | 1.99s | 1.99s | 10.9M | spies set clone |
| - | `engine/state.py:473 __deepcopy__` (GameState) | 0.99s | 85.55s | 124k | top clone entry |
| - | `openspiel_pyrants/state.py:58 _apply_action` | 0.89s | 100.44s | 48.3k | wrapper apply (≈95% of run) |
| - | `helpers.py:84 _player_has_any_troops_on_board` | 1.37s | 4.62s | 260k | full board scan per node |
| - | `helpers.py:91 _can_deploy_to_node` | 0.43s | 6.43s | 430k | deploy legality |
| - | `action_encoding.py:74 compute_action_map` | 0.07s | 9.42s | 48.3k | rebuild+JSON-sort moves per apply |

## Root cause

**~65% of runtime is full structural deep-copy of `GameState`.** Every
`engine.rules.apply` calls `state.model_copy(deep=True)` (rules.py:141, 393,
425, ...) → `GameState.__deepcopy__` (state.py:473) → `_copy_field` /
`_model_deepcopy_fields`. This clones the **entire** ~81-node `BoardState`
(each `NodeState` = `troop_slots` list + `spies` set), both `PlayerState`
zones, and market on *every* move — even when a move mutates only 1-2 nodes.

IS-MCTS amplifies this: `num_sims` simulations × rollout depth, each step =
one full clone. `_apply_action` is called 48,262 times for a 25-decision,
3-sim game.

Two secondary costs ride on top:
1. **`compute_action_map` recomputed eagerly after every apply** (state.py:74),
   re-running `legal_moves` and sorting by `model_dump_json` (9.4s, 228k
   `to_json` calls).
2. **`_player_has_any_troops_on_board` re-scans the whole board for each
   candidate deploy node** inside `_can_deploy_to_node` (helpers.py:99) — an
   invariant recomputed O(nodes) times per `legal_moves` call (260k scans).

## Proposed changes (ranked by impact / effort)

### Change 1 — Copy-on-write board/player clone (biggest win, ~50-60s)

**Files:** `engine/state.py`, `engine/rules.py`, `engine/helpers.py`,
`engine/generic_runtime/*`, `engine/scoring.py`.

**Idea:** Stop deep-cloning unchanged sub-state. `GameState.__deepcopy__`
already shares the frozen `definition`. Extend the same principle to mutable
containers via copy-on-write:

- Clone `GameState` with **shallow** container copies: new `dict` for
  `board.nodes` and `players` that *reuse* the existing `NodeState` /
  `PlayerState` object references; reuse `market`, `resource_pool`, list/set
  fields by reference.
- Add a small helper that mutators call before writing a node/player:
  `node = _mutable_node(state, node_id)` which, if the node is still shared
  (identity-equal to a parent's), replaces it with a fresh
  `node.model_copy()` in `state.board.nodes` and returns the private copy.
  Same for players (`_mutable_player`).
- Convert in-place mutation sites in `rules.py` / `helpers.py` /
  `generic_runtime` to go through these accessors. Reads stay direct.

This reduces per-apply copy cost from O(all nodes + all zones) to O(nodes
actually touched), which for most moves is 1-2 nodes.

**Tradeoff / risk:** This is the invasive change. The engine purity contract
(`apply(state, move) -> state'` never mutates input) must be preserved —
that is exactly why COW accessors are mandatory at *every* write site. Risk
of an aliased mutation leaking into the parent state if a write site is
missed. Mitigation:
- Audit every `updated.board.nodes[...]`, `updated.players[...]`, and
  `.troop_slots`/`.spies`/`.hand`/`.deck`/... mutation in `engine/`.
- Keep `tests/test_engine_purity.py` green; add an explicit test that applying
  a move does not mutate the source state's touched-and-untouched nodes
  (assert parent node objects unchanged by identity + value).

**Decision:** Full COW chosen (user, this pass). Implement behind the
engine-purity test net; audit every write site.

### Change 1b — Cheaper alternative: node/player-level shallow share only

If full COW is too risky, a localized version: in `GameState.__deepcopy__`,
keep deep-cloning but **short-circuit `NodeState` clones for nodes with empty
`spies` and a `troop_slots` of all-immutable** — already partly done. The
larger lever is still avoiding the per-node allocation. Lower payoff than
Change 1; only pursue if Change 1 is rejected.

### Change 2 — Lazy action-map recompute in wrapper (~5-9s)

**File:** `openspiel_pyrants/state.py:74`.

Replace the eager `self._cached_indexed_moves = compute_action_map(self._engine)`
after each apply with `self._cached_indexed_moves = None` and let
`_legal_actions` build it lazily (it already does, lines 54-56). Avoids
recomputing the sorted move map for states that are applied then discarded
without ever querying legal actions.

### Change 3 — Cheaper move sort key (~part of the 9.4s)

**File:** `openspiel_pyrants/action_encoding.py:35`.

`_move_sort_key` serializes each move to JSON purely for deterministic
ordering (228k `to_json` calls). Replace with a cheap tuple key over the
move's discriminating fields (e.g. `(move.move_type, target_node_id or "",
hand_index or -1, market_slot or -1, ...)`). Must preserve a total,
deterministic ordering so action ids stay stable across equal states.

**Risk — INVESTIGATED, low.** No external/persisted dependence on exact
action-id assignment found:
- `openspiel_pyrants/tests/test_action_encoding.py` only checks *roundtrip*
  consistency (`enumerate_legal_actions` / `action_to_move` /
  `move_to_action_id`) — order-agnostic as long as one key is used in all
  three (they all share `_move_sort_key`).
- Replays persist move payloads via `_move_to_payload` (`run_ismcts.py:150`),
  not action ids.
- `run_ismcts` decodes ids against the same live state ordering.

Requirement: the new tuple key must give a **total, deterministic** order with
no ties between distinct legal moves (Python's stable sort then falls back to
enumerate order, still deterministic). Include all discriminating fields
(`move_type`, node/target ids, hand_index, market_slot, slot_index,
spy_owner_id, option_id). Keep `_move_sort_key` the single source used by
`enumerate_legal_actions`, `action_to_move`, `move_to_action_id`,
`compute_action_map`.

### Change 4 — Hoist invariant out of deploy loop (~4-6s)

**File:** `engine/rules.py:332` + `engine/helpers.py:91`.

`_player_has_any_troops_on_board(state, player_id)` is invariant across the
deploy-candidate loop. Compute it once in `_legal_main_phase_actions` and
pass the bool into a refactored `_can_deploy_to_node(state, player_id,
node_id, has_troops_on_board)`. Removes 260k redundant full-board scans.

### Change 5 — Tighten `_copy_field` dispatch (~3-8s, only if COW kept)

**File:** `engine/state.py:32`.

`_TYPE_DISPATCH.get(type(value))` runs 79.6M times (8.66s). If Change 1 lands,
call count drops massively and this may not matter. If still hot, micro-opt:
hoist the dict's `.get` to a local, or branch on `type(value)` with `is`
checks for the 2-3 dominant field types (str, int, list) before the dict
lookup. Measure before/after — keep only if it pays.

## Suggested implementation order

1. Change 4 (localized, safe, immediate measurable win).
2. Change 2 + Change 3 (wrapper-level, low risk).
3. Re-profile to confirm copy still dominates.
4. Change 1 (COW) behind the engine-purity test net — the headline win.
5. Change 5 only if `_copy_field` still shows up post-COW.

## Validation

- `just test` green after each change (esp. `tests/test_engine_purity.py`,
  rules/scoring/generic-interpreter suites).
- `ruff check .`.
- Re-run `just ismcts-perf` after each change; compare total wall + per-line
  tottime against `cprofile_top.txt`. Target: deep-copy share of runtime
  drops from ~65% to a small fraction; overall wall down multiple ×.
- Sanity: `just ismcts-quick` still produces a valid game (same winner /
  decision_count for a fixed seed before vs. after, to confirm no behavior
  drift — ordering changes from Change 3 may shift this; verify intentionally).

## Open questions

(resolved) Change 1 scope → **full COW + Changes 2-5**, this pass.
(resolved) Action-id stability → investigated, **not relied on externally**;
Change 3 safe with a total-order tuple key.
