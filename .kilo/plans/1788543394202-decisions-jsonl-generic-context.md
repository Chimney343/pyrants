# Plan: Enrich `decisions.jsonl` with card/effect context for `resolve_generic`

## Problem

`decisions.jsonl` (written in `scripts/run_ismcts.py`, loop at lines 601–620) records
`chosen_move` via `state.move_to_str(...)`, which for the C backend is just
`CMoveWrapper.__str__` — the raw `resolve_generic(action_id='route_6', target_id=None,
selection_index=…)` string. From a decision line alone you cannot tell:

- **which card** the pending generic choice belongs to (Gauth vs Death Knight), or
- **what the choice actually does** (gain 2 influence vs supplant at `route_6`).

The information exists *before* `apply_action` in the engine's `pending_generic`
state and in the card catalog, but the runner never captures it.

## Decisions (resolved with the user)

1. **Placement:** write-time, additive. Capture at decision-write time in the runner,
   in the already-existing pre-`apply_action` window. No backfill for old files.
2. **Shape:** additive fields, keep `chosen_move` raw. Add `chosen_label` (human string)
   and a structured `generic` object; existing consumers and grep-over-raw-string
   workflows stay untouched.

## Key facts from the code

- `state._adapter._state._ptr.contents.pending_generic` is a
  `PendingGenericChoiceState` (ctypes struct in `engine_c/bindings/engine_bindings.py`
  lines 297–313) exposing `source_card_id`, `awaiting_option`, `current_option_id`,
  `next_action_index`, and `current_actions` (array of `CardAction`, lines 138–146,
  with `op` / `action_id` / `optional`).
- The runner *already* reads this pointer pre-apply (`run_ismcts.py` lines 622–628 via
  `CEngineAdapter.pending_generic_op()`), then advances/clears it on `apply_action`.
  That is the only safe window; post-apply the context is gone.
- `engine_c/bindings/view.py::_build_c_legal_moves` (lines 248–265) contains an inline
  walk of the same struct to feed `label_enrich.enrich_label`. That walk is duplicated
  logic — the fix extracts it once.
- `engine_c/bindings/label_enrich.py::enrich_label` already produces the desired labels:
  - Gauth option choice → `Gauth: Gain 2 influence` (branch 1a → `_describe_option` →
    `_describe_single_action` on `gain_resource` fixed 2).
  - Death Knight supplant → returns the raw `describe.c` label
    (`Supplant <owner> troop at <node>`), which needs `_describe_c_move` to compute.
- `enrich_label` requires a raw describe label as input for the target-selection case;
  that raw label comes from `view.py::_describe_c_move(state_ptr, move_wrapper)` (line 337).
- `interface/replay_loader.py` (`_load_decisions`) tolerates unknown/malformed fields and
  lines; `interface/replay_viewer.py::_update_decision_panel` (line 345) shows
  `chosen_move` verbatim and can be upgraded to prefer the new label.

## Proposed schema (resolve_generic decisions only)

Two new fields, both present **only** on `resolve_generic` lines so non-generic lines are
byte-for-byte unchanged:

```jsonc
{
  // ... existing fields unchanged (chosen_move stays raw) ...
  "chosen_label": "Gauth: Gain 2 influence",       // or "Supplant p2 troop at route_6"
  "generic": {
    "source_card_id": "gauth",            // card being resolved
    "op": "gain_resource",                // active CardAction op (null while awaiting option)
    "card_action_id": "option_1_action_1",// active CardAction action_id (null while awaiting)
    "current_option_id": "option_1",      // pg.current_option_id (null while awaiting)
    "awaiting_option": true,              // pg.awaiting_option
    "optional": false,                    // active action .optional (false while awaiting)
    "move_action_id": "option_1",         // move.data.action_id (option id when awaiting, else selection target)
    "move_target_id": null,               // move.data.target_id
    "selection_index": 0                  // move.data.selection_index
  }
}
```

`move_action_id` vs `card_action_id` are deliberately distinct names — the move's
`action_id` and the executing `CardAction.action_id` are different things (the same
ambiguity already documented in `scripts/_state_snapshot.py` lines 19–29).

## Tasks

### Task 1 — Extract shared pending-generic context reader

**New file `engine_c/bindings/pending_context.py`:**

- `read_pending_generic_context(state_ptr) -> dict | None`
  - `None` when `state_ptr` is null or `state_ptr.contents.pending_generic` is null.
  - Otherwise decode `PendingGenericChoiceState` + the active `CardAction`
    (`current_actions[next_action_index]`, guarded by index bounds; `NULL` active action
    when `awaiting_option`) into:
    `source_card_id`, `op`, `card_action_id`, `current_option_id`, `awaiting_option`,
    `optional` (all `None`-safe, decoded via `engine_bindings.sym_str`).
  - No pyspiel, no engine import beyond the existing ctypes structs — mirrors the
    import-light style of `scripts/_state_snapshot.py`.

**Refactor `engine_c/bindings/view.py::_build_c_legal_moves`** (lines 248–265): replace
the inline `try/except` walk with a call to `read_pending_generic_context`, keeping the
exact same `enrich_label` inputs (`source_card_id`, `card_action_id`, `is_option_choice`,
`is_optional_action`, `current_option_id`). This is the single-source-of-truth move.

**RED test** — `tests/c_engine/test_pending_context.py` (new):
- Using `make_card_test_session` (from `tests.c_engine.card_test_helpers`) with `gauth`,
  play the card, assert `read_pending_generic_context` returns `awaiting_option=True`,
  `source_card_id=="gauth"`, `op is None`, `card_action_id is None`.
- After choosing `option_1`, assert no pending → returns `None`.
- Use `death_knight` (or a sequence card with a selection) to assert a non-awaiting case
  yields a concrete `op` + `card_action_id`.
- Mark `requires_c_engine`.

### Task 2 — Runner writes `chosen_label` + `generic`

**In `scripts/run_ismcts.py`**, inside the loop, before `state.apply_action`:

- Compute `ctx = read_pending_generic_context(state._adapter._state._ptr)` when
  `chosen_move_obj.move_type == "resolve_generic"` (else `ctx = None`).
- Derive `pending_op = (ctx or {}).get("op")` and reuse it for the existing
  `_is_board_mutating(...)` call, **replacing** the current
  `state._adapter.pending_generic_op()` read (lines 622–628) so there is exactly one
  struct read per decision.
- When `ctx` is not None, build the `generic` dict (merge `ctx` with the move's
  `action_id`→`move_action_id`, `target_id`→`move_target_id`, `selection_index` from
  `chosen_move_obj.data`).
- Compute `chosen_label`:
  - `raw_label = _describe_c_move(state._adapter._state._ptr, chosen_move_obj)`
    (import `_describe_c_move` from `engine_c.bindings.view`).
  - `chosen_label = enrich_label("resolve_generic", raw_label, chosen_move_obj.data,
    source_card_id=ctx["source_card_id"], card_action_id=ctx["card_action_id"],
    is_option_choice=ctx["awaiting_option"], is_optional_action=ctx["optional"],
    current_option_id=ctx["current_option_id"])`
    (import `enrich_label` from `engine_c.bindings.label_enrich`).
- Add `"chosen_label"` and `"generic"` to the `decision` dict **only** for
  `resolve_generic` decisions. `chosen_move` stays raw; every other move type is
  byte-for-byte unchanged.

**RED test** — extend `openspiel_pyrants/tests/test_run_ismcts_runner.py` (or a new
`tests/test_run_ismcts_generic_context.py`):
- A focused unit test: build a `gauth` pending session directly (via
  `make_card_test_session`), construct the `resolve_generic` option move, and assert a
  small pure helper produces `chosen_label == "Gauth: Gain 2 influence"` and
  `generic["source_card_id"] == "gauth"` / `generic["awaiting_option"] is True`.
- A smoke test: run `run_one_game` (`requires_c_engine`, small `max_rounds`), load
  `decisions.jsonl`, and assert (a) every `resolve_generic`-typed line carries
  `chosen_label` + `generic`, (b) non-generic lines do not gain the fields, and (c) the
  file still parses line-by-line.

To keep the unit test pure, expose a small `_enrich_resolve_generic(adapter,
move_obj) -> dict` (or equivalent) in `run_ismcts.py` / `_generic_context` that the test
can call without running the whole game.

### Task 3 — Surface enriched label in the replay viewer

**`interface/replay_viewer.py::_update_decision_panel`** (line 345): prefer
`decision.get("chosen_label")` when present, else `chosen_move`. Append a short second
line from `generic` when present, e.g.
`"{source_card_id} · op={op} · target={move_action_id}"` (omit nulls).

**RED test** — add a pure helper `_decision_display_label(decision) -> str` (or similar)
and unit-test it: returns `chosen_label` when present; falls back to `chosen_move`;
formats the `generic` footer; ignores missing fields. Place in
`interface/replay_viewer.py` as an importable function and test in
`tests/test_replay_loader.py` (already Tk-free) or a small new test module.

### Task 4 — Docs / schema citations

- `interface/replay_loader.py` module docstring (lines 8–11): document the two additive
  fields (`chosen_label`, `generic`) on `resolve_generic` lines.
- `docs/openspiel-integration.md` (line 119) and the viewer plan field table
  `.kilo/plans/1788388431546-ismcts-replay-viewer.md` (line 126): note the new fields as
  additive. (Plan doc edit is optional; code docstring is required.)

## Non-goals

- No C-engine changes, no `engine_c.dll` rebuild.
- No enrichment of `legal_moves` (file stays lean; policy panel uses them as fallback
  labels only).
- No post-hoc backfill for existing `game_*` dirs.
- No friendly board names (`node_names`) — labels show internal node ids (`route_6`),
  matching the user's current expectation. `player_spy_count` /
  `player_available_aspects` are passed as defaults, so a few labels degrade to the
  unfiltered description (documented limitation, not a correctness issue).

## Risks

- `enrich_label` loads the catalog via `_catalog_cache()` (lru-cached, read-only
  `data/cards/`) — no per-decision I/O cost, already used by the GUI.
- Reading `pending_generic` via ctypes mirrors code already exercised in `view.py` and
  `c_adapter.py`; all reads are index/bounds-guarded and `try/except`-wrapped so a decode
  failure degrades to `None` rather than crashing the run.
- Additive-only fields cannot break `replay_loader`, `replay_viewer`, or the existing
  `node`/`round`/`phase`-keyed tests.

## Validation

1. `ruff check .`
2. `just test-c-python` (runs `pytest tests/c_engine -v`) and `just test` (full suite).
   No `just build-c` needed — C is untouched.
3. New tests:
   - `pytest tests/c_engine/test_pending_context.py -v`
   - `pytest tests/test_run_ismcts_generic_context.py -v` (or the runner test module)
   - `pytest tests/test_replay_loader.py -v`
4. Manual: `just ismcts-quick`, then inspect `artifacts/ismcts/game_0000/decisions.jsonl`
   — `resolve_generic` lines must carry `generic.source_card_id` + `chosen_label`
   (`Gauth: Gain 2 influence`, `Supplant … troop at route_6`, etc.), and non-generic
   lines must be unchanged.
