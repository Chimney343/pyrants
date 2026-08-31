# IS-MCTS Observability — Phase 2: Per-Step Game-State Snapshots

## Prerequisite

Phase 1 (`1787952432270-ismcts-phase1-crash-safe-streaming-step-log.md`) must
be merged first — this phase adds a `"state"` key to the `"step"` lines
phase 1 introduced in `steps.jsonl`.

## Context

Today, `replay.json`/`decisions.jsonl`/`steps.jsonl` (post phase 1) record
*what move was chosen* at each step, but never *what the resulting game
state looked like*. To answer "what was this bot's VP/resources/board
position when it made this decision?" today requires re-running the whole
game through the engine — exactly what the reconstruction goal (see phase 5)
is meant to avoid.

Two existing, already-proven mechanisms should be reused rather than
building new state-serialization code:

- `CEngineAdapter._build_public_dict()` (`engine_c/bindings/c_adapter.py:134-174`)
  — cheap, per-player-only: `resource_power`/`resource_influence` (the
  shared, per-turn-only resource pool — per `docs/tyrants-rulebook.md`'s
  "Resource Pool" section, unspent Power/Influence is lost at end of turn,
  never carried over), `market_row`, and per-player `hand_size, deck_size,
  discard_size, played_size, inner_circle_size, trophy_hall_size, barracks,
  spies_available, vp_tokens, score`.
- `build_c_game_view()` (`engine_c/bindings/view.py:365-525`) — the same
  board-state mechanism `interface/game_viewer.py` (the interactive GUI)
  already depends on for rendering. Returns `board_nodes`
  (`NodeOccupancyView`: `node_id, kind, adjacent_to, control_vp,
  total_control_vp_per_turn, troop_slots, spies, vp_tokens`) plus
  `current_player_controlled_sites/total_control_sites/control_vp/total_control_vp`.
  This is pricier (iterates every board node) and should **not** be called
  every step — reserve it for round boundaries and board-mutating moves.

Do **not** use the `PublicView`/`PublicNodeView` C struct in
`engine_c/state.h` (lines 363-410) — `c_adapter.py`'s own module docstring
explains this struct has ctypes struct-layout mismatches with the Python
bindings and is deliberately unused; `build_c_game_view()` is the working
alternative.

`NodeOccupancyView` has no `controller_id` field. To determine who controls
a site, derive it from `troop_slots` per the rulebook's "Control" rule
(`docs/tyrants-rulebook.md`, "Control" section): the player with strictly
more troops at the site than any other single color controls it (ties =
no controller); "Total Control" additionally requires every troop slot to
be filled by that player's own troops and zero enemy `spies` present. Write
this as a small pure helper, since phase 4's site-control-change stats will
need the same derivation.

## Files touched

- `scripts/run_ismcts.py` (`run_one_game()` — add snapshot-building calls into the step-writing path built in phase 1)
- `scripts/_obs.py` or a new `scripts/_state_snapshot.py` (pure helper functions — keep them import-light so they stay testable without `pyspiel`)
- `tests/test_state_snapshot.py` (new)

## Design (reference while writing tests/code)

- `_tier1_snapshot(adapter) -> dict`: wraps `adapter._build_public_dict()`,
  returning exactly the fields listed above (Context). Called on **every**
  successful step.
- `_derive_site_controller(node: NodeOccupancyView) -> str | None`: pure
  function, no engine calls — takes the already-fetched node view, counts
  `troop_slots` by non-`None` owner, returns the owner with a strict
  plurality (`None` if tied or empty), independent of total-control status.
- `_derive_total_control(node: NodeOccupancyView, controller: str | None) -> bool`:
  `controller is not None and all(slot == controller for slot in
  node.troop_slots if slot is not None) and len(node.spies) == 0` — matches
  the rulebook's Total Control definition (majority *and* every filled slot
  is that player's *and* no enemy spies present). Note: an *empty* troop
  slot doesn't disqualify total control per the rulebook (only enemy troops
  or spies do) — confirm this reading against `docs/tyrants-rulebook.md`'s
  "Total Control" section before implementing, and write a test case for a
  site with some empty slots to lock in the interpretation either way.
- `_tier2_snapshot(adapter) -> dict`: calls `build_c_game_view(adapter)`,
  then maps each `board_nodes` entry through the two helpers above to
  produce `{"board_nodes": [{"node_id":..., "controller": ..., "total_control": bool, "troop_slots": [...], "spies": [...], "control_vp": ..., "total_control_vp_per_turn": ..., "vp_tokens": ...}, ...], "current_player_controlled_sites": ..., "current_player_total_control_sites": ..., "current_player_control_vp": ..., "current_player_total_control_vp": ...}`.
- `_is_board_mutating(move_type: str, payload: dict) -> bool`: returns
  `True` when `move_type in {"assassinate", "deploy", "return_spy"}` or
  (`move_type == "resolve_generic_choice"` and
  `payload.get("action_id") in {"deploy_troops", "assassinate_troop",
  "supplant_troop", "place_spy", "move_troop", "return_unit"}`) — action-id
  vocabulary confirmed against the card table in
  `docs/ismcts-generic-resolution-bugs.md`.
- In `run_one_game()`'s step-writing code (phase 1's `"step"` event
  construction), attach `"state"` as:
  ```python
  state_snapshot = _tier1_snapshot(state._adapter)
  if round_changed or _is_board_mutating(move_type, payload):
      state_snapshot["board"] = _tier2_snapshot(state._adapter)
  step_line = {..., "state": state_snapshot}
  ```
  where `round_changed = state._engine.round_number != previous_round_number`
  (track `previous_round_number` across loop iterations, initialized before
  the loop starts).

## TDD task list

### Task 2.1 — site controller derivation matches rulebook rules

**RED**: In `tests/test_state_snapshot.py` (new, no `pyspiel` import needed —
construct plain `NodeOccupancyView`-shaped test doubles, e.g. a
`namedtuple` or `SimpleNamespace` with `troop_slots`/`spies` attributes, so
this stays a pure unit test), write parametrized cases against
`_derive_site_controller` and `_derive_total_control`:
- 2 slots both `"p1"`, 0 spies → controller `"p1"`, total control `True`.
- 2 slots `"p1", "p2"` (tied) → controller `None`, total control `False`.
- 3 slots `"p1", "p1", "p2"` → controller `"p1"`, but total control `False`
  (not all slots are p1's).
- 2 slots both `"p1"`, 1 spy owned by `"p2"` → controller `"p1"`, total
  control `False` (enemy spy present).
- 2 slots `"p1", None` (one empty), 0 spies → controller `"p1"`; total
  control per your locked-in reading of the rulebook (document which and
  why in a comment above `_derive_total_control`).
- 0 slots filled → controller `None`.

Confirm these **fail** first (the functions don't exist yet).

**GREEN**: Implement `_derive_site_controller` and `_derive_total_control`.

**REFACTOR**: none expected — these should stay small pure functions.

### Task 2.2 — Tier 1 snapshot has exactly the documented fields, cheaply

**RED**: Using a real (not mocked) minimal `CEngineAdapter` — reuse whatever
fixture-building helper existing tests use to stand up a session (check
`tests/c_engine/card_test_helpers.py::make_card_test_session` or
equivalent for the OpenSpiel/C-adapter layer), write a test asserting
`_tier1_snapshot(adapter)` returns a dict with exactly the keys:
`resource_power, resource_influence, market_row, players` (or your chosen
per-player key name) where `players` maps each player id to a dict with
`hand_size, deck_size, discard_size, played_size, inner_circle_size,
trophy_hall_size, barracks, spies_available, vp_tokens, score`. Confirm it
**fails** (function doesn't exist).

**GREEN**: Implement `_tier1_snapshot` as a thin wrapper over
`adapter._build_public_dict()`, reshaping/renaming only if needed for
consistency with the key names above (or use `_build_public_dict()`'s
existing key names directly if they already match — prefer reusing them
verbatim over inventing new ones, to minimize translation code).

**REFACTOR**: none expected.

### Task 2.3 — Tier 2 (board) snapshot only fires on round-change or board-mutating moves

**RED**: Extend `tests/test_run_ismcts_crash_capture.py`'s (or a new
integration test's) short-game fixture from phase 1: run a couple of steps
where you control (via a small scripted/mocked bot or a fixed move
sequence) which moves are applied — include at least one `play_card` (not
board-mutating), one `deploy` (board-mutating), and one round boundary.
Assert that the resulting `steps.jsonl` lines have `"board"` present in
`"state"` only for the `deploy` step and the round-boundary step, and
absent for the `play_card` step. Confirm this **fails** (no such
conditional logic exists yet — either no board data is ever attached, or
if you implement naively it might be attached to every step).

**GREEN**: Implement `_is_board_mutating` and the round-boundary tracking,
wire into the step-writing code as described in Design.

**REFACTOR**: If `_is_board_mutating`'s action-id set duplicates a
vocabulary list needed elsewhere (phase 4's `action_semantic_counts` will
need the same `resolve_generic_choice` action-id vocabulary) — extract a
single shared constant/module (e.g. `scripts/_action_vocabulary.py` with a
`BOARD_MUTATING_GENERIC_ACTIONS` frozenset) rather than duplicating the
list when phase 4 is implemented. It's fine to leave this as a local
constant in this phase and only extract it when phase 4 actually needs it
(don't speculatively factor for a future phase that isn't written yet).

## Verification

```
pytest tests/test_state_snapshot.py tests/test_run_ismcts_crash_capture.py -v
just ismcts-quick
```
Inspect `artifacts/ismcts/game_0000/steps.jsonl`: confirm every `"step"`
line has a `"state"` key with Tier 1 fields, and that `"board"` only
appears on lines corresponding to round changes or board-mutating moves
(spot-check a handful by eye — e.g. `python -c "import json; [print(json.loads(l).get('move_type'), 'board' in json.loads(l)['state']) for l in open('artifacts/ismcts/game_0000/steps.jsonl')]" | sort | uniq -c`
should show `board` present roughly matching the count of
assassinate/deploy/return_spy/relevant-resolve_generic moves plus one per
round).
