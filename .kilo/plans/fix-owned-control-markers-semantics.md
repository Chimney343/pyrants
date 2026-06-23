# Fix `owned_control_markers` Count to Match Original Game Semantics

## Problem

`Green Dragon` (catalog.json:6396) grants "1 VP for each site control marker you have", and its card notes (catalog.json:6397, first_deck_review.md:396) explicitly say:

> The VP clause counts literal site control markers you own, not all sites you currently control.

In the original *Tyrants of the Underdark* board game, a **physical control marker** is only placed on a site that awards per-turn VP for total control. Other sites can still be troop-majority controlled but do not receive a marker.

The current engine maps `count_from="owned_control_markers"` to `_count_controlled_sites_by_troops()` (`engine/generic_runtime/_utils.py:62`, `engine/helpers.py:160-177`), which counts **every** site where the player has a unique non-white troop majority — including sites with `total_control_vp_per_turn == 0`. That is a different concept and over-counts relative to the printed card.

Quaggoth's `controlled_sites` count stays unchanged — its card notes (`first_deck_review.md:246`) explicitly say "counts all sites currently under your control, not only sites with a control marker present."

## Confirmed Decisions

1. **Marker definition** — A site is considered to have a control marker for the owner if and only if `node_definition.kind == SITE` AND the player has a unique non-white troop majority at that site AND `node_definition.total_control_vp_per_turn > 0`. Only one site in `data/boards/tyrants_of_the_underdark.json` (line 323, control_vp=5, total_control_vp_per_turn=1) currently satisfies this — the new semantics will return 1 for the controlling player, 0 for all others.
2. **Quaggoth is unchanged** — `count_from="controlled_sites"` continues to count all majority-controlled sites.
3. **Two engines stay in sync** — Python and C engines both implement the new rule.

## Success Criteria

1. `_count_owned_control_markers(state, player_id)` (new Python helper) returns the count of sites where the player has troop-majority control AND `node_definition.total_control_vp_per_turn > 0`.
2. The C engine has a corresponding `count_owned_control_markers(state, player_id)` function used for `count_from="owned_control_markers"` in card actions.
3. `data/cards/catalog.json` Green Dragon modal action still uses `count_from: "owned_control_markers"` and now grants the correct (lower) VP in tests.
4. Quaggoth's `count_from: "controlled_sites"` is untouched and still returns the majority-control count.
5. New C-engine regression test under `tests/c_engine/test_card_green_dragon.py` locks in: p1 controls the one VP-per-turn site → 1 VP awarded by Green Dragon's modal action; p1 controls only zero-VP-per-turn sites → 0 VP.
6. Existing Python tests for `controlled_sites_by_troops` and the engine-c `test_quaggoth_assassinate_count_snapshotted` scenario remain green.
7. `ruff check .` and `just test` / `just build-c` / `just test-c-python` pass.

## Files Touched

### Engine C
- `engine_c/helpers.c` — add `count_owned_control_markers()` next to existing `count_controlled_sites()` (line 125).
- `engine_c/helpers.h` — add prototype.
- `engine_c/actions.c:30-60` — extend `resolve_count()` to map `"owned_control_markers"` to the new function.
- `engine_c/generic_runtime.c:30-90` — extend the equivalent `count_from` handler in the generic-runtime entrypoint (whichever path Green Dragon modal action takes through the C side).

### Engine Python
- `engine/helpers.py` — add `_count_owned_control_markers(state, player_id)` next to the existing helpers at line 160.
- `engine/generic_runtime/_utils.py:62-63` — change `count_from == "owned_control_markers"` to call the new helper (do not touch the `controlled_sites` branch at line 59-60).

### Card data
- `data/cards/catalog.json:6465, 6529` — no change. The `count_from` value remains `"owned_control_markers"`; only its meaning changes.
- `scripts/generate_first_deck_artifacts.py:716` — regenerate the artifact after the engine change so the derived card JSON still matches. (No metadata change to the catalog entry; the script just resyncs.) If the artifact generator does not need to change, leave it.

### Tests
- `tests/c_engine/test_card_green_dragon.py` (new) — mirror `test_card_black_dragon.py` structure:
  - **test_green_dragon_vp_equals_sites_with_per_turn_vp_under_control** — build a session with p1 holding the only per-turn-VP site (site_menzoberranzan, line 323) and one other majority-controlled site with `total_control_vp_per_turn == 0`. Play Green Dragon's modal option 2, complete supplant + return_spy, end main, resolve end-of-turn. Assert score increased by exactly 1.
  - **test_green_dragon_zero_markers_gives_zero_vp** — build session with p1 controlling only zero-VP-per-turn sites. Assert score unchanged after playing Green Dragon option 2.
  - **test_green_dragon_controlled_site_without_per_turn_vp_does_not_count** — explicit assertion that a majority-controlled site with `total_control_vp_per_turn == 0` is NOT counted, locking in the semantic difference from `controlled_sites`.

### Docs
- `docs/source/first_deck_review.md:396` — note already says "literal site control markers". Optionally add a parenthetical "(sites with `total_control_vp_per_turn > 0`)" so the meaning is unambiguous, but only if the user requests it.

## Implementation Plan

1. **Add C engine helper** (`engine_c/helpers.c`).
   ```c
   int count_owned_control_markers(const GameState *state, Sym player_id) {
       int total = 0;
       for (int i = 0; i < state->definition->board.node_count; i++) {
           const NodeDefinition *nd = &state->definition->board.nodes[i];
           if (strcmp(intern_str(nd->kind), "site") != 0) continue;
           if (nd->total_control_vp_per_turn <= 0) continue;
           // same majority-troop-counting + unique-leader + non-white check
           // as count_controlled_sites(), then add 1 if player == leader
       }
       return total;
   }
   ```
   Factor out the shared majority-counting inner loop into a `static int` helper (e.g. `site_majority_owner`) to avoid duplicating the logic between the two functions. Add prototype to `engine_c/helpers.h`.

2. **Wire into C action resolution** (`engine_c/actions.c`).
   In `resolve_count()` (line 30-60), add a third branch:
   ```c
   if (strcmp(v, "owned_control_markers") == 0)
       return count_owned_control_markers(state, player_id);
   ```
   Apply the same branch in `engine_c/generic_runtime.c` `resolve_runtime_action_count`-equivalent if Green Dragon's modal action resolves through the generic_runtime path. Verify by tracing which C path the Green Dragon modal option 2 grant_vp action takes.

3. **Add Python helper** (`engine/helpers.py`).
   ```python
   def _count_owned_control_markers(state, player_id):
       board_definitions = board_index(state.definition.board)
       total = 0
       for node_id, node_def in board_definitions.items():
           if node_def.kind != NodeKind.SITE:
               continue
           if node_def.total_control_vp_per_turn <= 0:
               continue
           node_state = state.board.nodes[node_id]
           counts: dict[str, int] = {}
           for occupant in node_state.troop_slots:
               if occupant is not None:
                   counts[occupant] = counts.get(occupant, 0) + 1
           if not counts:
               continue
           max_count = max(counts.values())
           leaders = [o for o, c in counts.items() if c == max_count]
           if len(leaders) == 1 and leaders[0] != "white" and leaders[0] == player_id:
               total += 1
       return total
   ```

4. **Update Python dispatch** (`engine/generic_runtime/_utils.py:62`).
   Change the branch body from `_count_controlled_sites_by_troops` to the new `_count_owned_control_markers`. Do not touch the `controlled_sites` branch above it.

5. **Card JSON / artifact** (`data/cards/catalog.json`, `scripts/generate_first_deck_artifacts.py`).
   - No metadata change needed. The `count_from` value stays `"owned_control_markers"`.
   - If the artifact generator emits a derived structure that includes the resolved count, regenerate it so downstream data stays consistent. Otherwise skip.

6. **Add regression tests** (`tests/c_engine/test_card_green_dragon.py`).
   Use the existing `tests/c_engine/card_test_helpers.py::make_card_test_session` pattern. The session needs to put p1 troops on `site_menzoberranzan` (or whichever node_id maps to line 323 of the board JSON) and at least one other site with `total_control_vp_per_turn == 0`. Walk Green Dragon's modal option 2: place spy / return spy → supplant → scaled grant_vp → end main → resolve end-of-turn. Assert the score delta.

7. **Verification**.
   ```bash
   just build-c
   just test-c-python
   .venv/Scripts/python.exe -m pytest tests/c_engine/test_card_green_dragon.py -v
   .venv/Scripts/python.exe -m pytest tests/c_engine/test_card_black_dragon.py -v
   .venv/Scripts/python.exe -m pytest tests/c_engine/test_quaggoth_assassinate_count_snapshotted -v 2>&1 | head -50
   .venv/Scripts/python.exe -m pytest -q
   ruff check .
   ```

## Risks and Watch-Outs

- **C engine has no current path for `owned_control_markers`** — `engine_c/actions.c:30-60` and `engine_c/generic_runtime.c` both only handle `controlled_sites` and a couple of other count sources. The Green Dragon modal action is currently broken or silently mis-handled on the C side. Implementing the new branch in the C engine may surface latent test failures that were previously masked.
- **Refactor opportunity** — `_count_controlled_sites` and `_count_controlled_sites_by_troops` in `engine/helpers.py:140-177` have identical bodies. The fix is a good time to delete the duplicate, but the plan keeps that out of scope to minimize the diff. Note in code review if user wants to clean it up.
- **Card notes doc** — `docs/source/first_deck_review.md:396` already says "literal site control markers". The new engine semantics will finally make that note accurate at runtime.
- **Quaggoth tests** — `tests/c_engine/test_engine_c.py::test_quaggoth_assassinate_count_snapshotted` (line 478) and the `017_seed_4_quaggoth.json` scenario rely on the existing `controlled_sites` count from the seed. They must remain green.
- **Multiple call sites for `count_from` dispatch** — Both `_utils.py:62` and `engine/helpers.py:290` mention `owned_control_markers`. The `helpers.py:290` branch is inside `_scaled_vp_award_count()` and is what Green Dragon actually uses for its `grant_vp` action — make sure BOTH branches dispatch to the new helper so the behavior is consistent if any future card uses the same count source via a different code path.

## Recommended Implementation Order

1. Add `count_owned_control_markers()` to C engine and wire into both `actions.c` and `generic_runtime.c`.
2. Add `_count_owned_control_markers()` to Python engine and update BOTH dispatch points (`engine/generic_runtime/_utils.py:62` and `engine/helpers.py:290`).
3. Build C engine (`just build-c`).
4. Add `tests/c_engine/test_card_green_dragon.py` regression test.
5. Run targeted Python tests, then full suite.
6. `ruff check .`.
7. Update `docs/source/first_deck_review.md` note (only if requested).
