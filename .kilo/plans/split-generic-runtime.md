# Plan: Simplify Card Action Execution

## Problem Summary

`engine/generic_runtime.py` is a 2279-line monolith containing:
- 18 action applier functions
- 14 target selection generators
- 9 custom effect handlers
- 3 execution model initialization paths
- The central `_auto_resolve_pending_generic()` while-loop
- Selection validation helpers

Call stack depth for one card play: 12-15 levels. Developer must read 14 files (~40K lines) to understand a single card action. `helpers.py` was extracted from `rules.py` to break a circular import — a sign module boundaries are wrong.

## Goals

1. **Split `generic_runtime.py`** into one file per action category (~200 lines each)
2. **Unify execution models** — collapse `sequence` and `modal_choice` into `repeat_choice` semantics
3. **Kill the `custom_effect` middle-dispatch** — register custom effects as first-class `op` values
4. **Fix circular import** — proper module boundaries so `helpers.py` isn't a dumping ground
5. **Reduce redundant validation** — action appliers should trust their target selection generators

## Constraints

- **125 unique cards** in `catalog.json` must keep working after every phase
- All 1325 lines of `test_generic_interpreter.py` must continue passing
- `engine/__init__.py` public API (`apply`, `legal_moves`, `is_terminal`, `winner`) must not change
- `data/cards/catalog.json` shape is sacred — card JSON must not change
- Only 1 card uses `repeat_choice` (`mummy_lord`), 89 use `sequence`, 35 use `modal_choice`

---

## Phase 1: Split `generic_runtime.py` into Package

**Goal:** Break the 2279-line monolith into `engine/generic_runtime/` package with focused sub-modules. No logic changes — pure file reorganization. All existing tests must pass after this phase.

### New Package Structure

```
engine/generic_runtime/          # was: engine/generic_runtime.py
    __init__.py                   # re-exports public API (same symbols that rules.py imports)
    _resolve.py                   # _resolve_generic_execution, _auto_resolve_pending_generic,
                                  #   _apply_resolve_generic_choice, _resolve_card_option_actions,
                                  #   _pending_generic_card_definition, _pending_generic_active_action,
                                  #   _available_repeat_option_ids, _pending_action_counter_key,
                                  #   _pending_action_counter_value, _action_requires_additional_choice,
                                  #   _resolve_runtime_action_count, _threshold_self_promote_enabled,
                                  #   _action_focus_requirement_met, _action_requires_selection,
                                  #   _generic_choice_move, _option_is_currently_selectable
    _selection.py                 # _legal_pending_generic_choice_moves,
                                  #   _legal_generic_target_selection_moves,
                                  #   all _legal_selection_* functions (14),
                                  #   _LEGAL_TARGET_HANDLERS dict
    _actions.py                   # _apply_generic_action, _GENERIC_ACTION_APPLIERS dict,
                                  #   all _apply_generic_* functions (18),
                                  #   _apply_devour_once, _require_selection_string, _require_selection_int,
                                  #   _action_requires_additional_choice (already in _resolve — leave there)
    _custom_effects.py            # _apply_generic_custom_effect, _CUSTOM_EFFECT_HANDLERS dict,
                                  #   all _custom_effect_* functions (9)
    _promotion_helpers.py         # _promote_from_deck_top, _promote_from_multiple_zones,
                                  #   _promote_from_discard, _promote_requires_other_card,
                                  #   _promote_required_aspect, _promote_required_secondary_aspect,
                                  #   _legal_recruit_card_for_action,
                                  #   (currently in generic_runtime.py, lines 96-209)
```

### Implementation Steps

1. Create `engine/generic_runtime/` directory and `__init__.py`
2. Move functions to sub-modules, preserving all internal import paths
3. `__init__.py` re-exports the 4 symbols that `rules.py` imports:
   ```python
   from engine.generic_runtime._resolve import (
       _action_requires_selection,
       _apply_resolve_generic_choice,
       _legal_pending_generic_choice_moves,
       _resolve_generic_execution,
   )
   ```
4. Update `rules.py` import: `from engine.generic_runtime import (...)` (no change needed if `__init__.py` re-exports correctly)
5. Update `helpers.py` import path if needed (it only imports from `engine.helpers`, not from `generic_runtime`)
6. Run `pytest` — all 1325 lines of test_generic_interpreter.py must pass

### Estimated File Sizes After Split

| File | Estimated Lines |
|------|-----------------|
| `__init__.py` | ~15 |
| `_resolve.py` | ~250 |
| `_selection.py` | ~400 |
| `_actions.py` | ~900 |
| `_custom_effects.py` | ~250 |
| `_promotion_helpers.py` | ~120 |

`_actions.py` at ~900 is still big — it's the 18 action handlers. Phase 4 addresses this.

---

## Phase 2: Flatten `custom_effect` into First-Class Ops

**Goal:** Eliminate the two-level dispatch (`_GENERIC_ACTION_APPLIERS["custom_effect"]` → `_CUSTOM_EFFECT_HANDLERS["steal_white_trophy_to_board"]`). Each custom effect becomes its own `op` value.

### Current Flow (2 hops)

```
GENERIC_ACTION_APPLIERS["custom_effect"]
  → _apply_generic_custom_effect()
    → _CUSTOM_EFFECT_HANDLERS["steal_white_trophy_to_board"]
```

### Target Flow (1 hop)

```
GENERIC_ACTION_APPLIERS["steal_white_trophy_to_board"]
  → _apply_generic_steal_white_trophy_to_board()
```

### Implementation Steps

1. **Add new `op` values to `_LEGAL_TARGET_HANDLERS` and `_GENERIC_ACTION_APPLIERS`:**
   - `scaled_resource_from_player_zone` → `_apply_generic_scaled_resource_from_player_zone`
   - `give_insane_outcast_to_player_with_presence_on_last_selected_node` → rename action op in catalog JSON? NO — we can't change the data. Instead: register these as `"custom_effect:steal_white_trophy_to_board"` or keep the `custom_effect` op but add a `_LEGAL_TARGET_HANDLERS` entry that dispatches to the right selection generator.
   
   **Better approach:** Since the `op` field in `CardAction` is free-text and comes from `catalog.json`, we can't change the JSON. Instead:
   - Keep `op: "custom_effect"` in the data
   - In `_apply_generic_action`, after the main dispatch lookup fails, try `_CUSTOM_EFFECT_HANDLERS` as a fallback
   - Remove the `_apply_generic_custom_effect` indirection function
   - Or simpler: just leave `_CUSTOM_EFFECT_HANDLERS` as-is but move it into `_actions.py` alongside `_GENERIC_ACTION_APPLIERS`
   
   **Actually simplest:** Keep `custom_effect` as an op in the dispatch, but move `_CUSTOM_EFFECT_HANDLERS` into `_actions.py` clearly. The 2-hop is minimal complexity — it's just a dict lookup. The real problem was it being buried in a 2279-line file. After Phase 1, it's already in its own 250-line file.

   **Revised decision:** The double-dispatch is fine once it's in a small, focused file. The complexity demon was the 2279-line monolith, not the two dict lookups. Skip this step — the cost of changing 8 cards' `op` field in catalog.json to new op values (and updating `_action_requires_selection`) outweighs the benefit.

2. **Update `_action_requires_selection`** — already handles `custom_effect` with effect_kind checks; no change needed.

**Verdict on Phase 2:** DEFERRED. The real complexity problem is file size, not dispatch depth. Two dict lookups in a 250-line file is perfectly fine. Removing the hop would require changing `catalog.json` actions for 8 cards and updating the `_action_requires_selection` branching logic. Not worth it.

---

## Phase 3: Unify Execution Models

**Goal:** Collapse `sequence` and `modal_choice` into `repeat_choice` semantics so there's one execution model instead of three.

### Current State

| Model | Count | Semantics |
|-------|-------|-----------|
| `sequence` | 89 cards | Fixed list of actions, no player choice |
| `modal_choice` | 35 cards | Pick one option from N |
| `repeat_choice` | 1 card | Pick options N times, optionally repeat same option |

### Key Insight

- `sequence` = A single `option` with `repeat_count=1`, `allow_repeat=false`, containing all actions.
- `modal_choice` = `repeat_count=1`, `allow_repeat=false`, with N options.
- `repeat_choice` = General case with variable `repeat_count` and `allow_repeat`.

So `sequence` and `modal_choice` are special cases of `repeat_choice`.

### Plan

**DO NOT DO THIS IN CATALOG.JSON.** Instead:

1. **In `_resolve_generic_execution()`**, normalize `sequence` and `modal_choice` cards into `repeat_choice`-compatible `PendingGenericChoiceState`:
   - `sequence`: Create one synthetic option containing all actions, set `awaiting_option=True`, `remaining_repeats=1`.
   - `modal_choice`: Already has options; set `remaining_repeats=1`, `allow_repeat=False`.
   
   This way the `_auto_resolve_pending_generic()` loop handles all three uniformly.

2. **Keep the Pydantic models** (`SequenceExecutionModel`, `ModalChoiceExecutionModel`, `RepeatChoiceExecutionModel`) in `state.py` — they're part of the data contract with `catalog.json`. The normalization happens at runtime only.

3. **Simplify `_auto_resolve_pending_generic()`** by removing `execution_kind` branching:
   - After normalization, `PendingGenericChoiceState.execution_kind` is always `"repeat_choice"`.
   - Remove `if pending.execution_kind == "repeat_choice"` branches in `_available_repeat_option_ids` and `_apply_resolve_generic_choice`.
   - Remove `if pending.execution_kind == "modal_choice"` branch in `_resolve_card_option_actions`.

4. **Update `PendingGenericChoiceState.execution_kind`** to accept the new normalized value or keep the literal for backward compat with tests. (Tests construct `PendingGenericChoiceState` directly — they'll need updating.)

### Risks

- **125 cards tested.** The normalization must be exactly equivalent.
- `_resolve_card_option_actions()` must handle sequence→option normalization.
- Tests that directly construct `PendingGenericChoiceState` with `execution_kind="sequence"` need updating to use normalized form.

### Implementation Steps

1. Add normalization function in `_resolve.py`:
   ```python
   def _normalize_to_pending(
       state, player_id, card, source_card_id
   ) -> PendingGenericChoiceState:
       em = card.execution_model
       if isinstance(em, SequenceExecutionModel):
           # Wrap all actions in a single synthetic option
           ...
       elif isinstance(em, ModalChoiceExecutionModel):
           # Already option-based, just set remaining_repeats=1
           ...
       else:  # RepeatChoiceExecutionModel
           # Passed through as-is
           ...
   ```
2. Replace the 3-branch block in `_resolve_generic_execution()` with call to `_normalize_to_pending()`.
3. Simplify `_auto_resolve_pending_generic()` — remove `execution_kind` checks.
4. Update tests.
5. Run `pytest`.

---

## Phase 4: Reduce Redundant Validation

**Goal:** Action appliers should trust their target selection generators, not re-validate everything.

### Current Problem

`_legal_selection_assassinate_supplant()` checks:
- `white_only` filter
- `allow_white_troop` filter
- `requires_returned_spy_site`
- `requires_last_selected_node`
- `has_presence`

Then `_apply_generic_assassinate_troop()` re-checks:
- `white_only` flag
- `requires_last_selected_node`
- Slot bounds
- Node existence

### Plan

1. **Add a `_validate_selection()` helper** that each action applier calls, extracting common validation (node existence, slot bounds, occupant not-self) into shared functions.
2. **Remove duplicate complaint-specific checks** from action appliers that are already guaranteed by the selection generator.
3. **Keep safety-critical checks**: node existence, slot bounds. Remove business-logic duplication (e.g., `white_only` filter).

### Implementation Steps

1. Create `_validate_node_exists(state, node_id)` and `_validate_slot_bounds(node_state, slot_index)` in `_actions.py`.
2. Refactor `_apply_generic_assassinate_troop`, `_apply_generic_supplant_troop`, `_apply_generic_place_spy`, `_apply_generic_move_troop`, `_apply_generic_return_spy` to use shared validators.
3. Remove `white_only` / `allow_white_troop` re-checks from appliers — the selection generators already filter.
4. Run `pytest` after each applier refactor.

---

## Phase 5: Fix Circular Import & Reorganize `helpers.py`

**Goal:** Give `helpers.py` a proper name and clear purpose, or split it into focused modules.

### Current Problem

`helpers.py` docstring says: *"Extracted from rules.py to eliminate the lazy `_get_rules()` circular import in generic_runtime.py."*

It contains an incoherent grab-bag:
- `WHITE_TROOP_OWNER` constant
- `SPECIAL_RECRUIT_STACKS` constant
- `_EFFECT_REGISTRY` and `register_effect`
- Board helpers (`has_presence`, `_can_deploy_to_node`)
- Counting helpers (`_count_controlled_sites`, `_count_runtime_cards_by_aspect`)
- Focus helpers
- Effect wrapper (`_apply_effect_with_wrappers`)
- Promotion system (`_promote_card`, `_apply_promote_instruction`)
- Resource utility (`_grant_resource`)
- Free actions (`_apply_free_assassinate`, `_apply_free_deploy`, `_apply_free_return_spy`, `_apply_recruit`)
- Paid ability checks and costs
- Deferred promotion helpers
- Scaled VP helpers

### Plan

Split into focused modules:

```
engine/
    _registry.py          # _EFFECT_REGISTRY, register_effect, CardEffect type
    _board.py             # has_presence, _can_deploy_to_node, _player_has_any_troops_on_board,
                          #   board_index (from state.py? or keep), WHITE_TROOP_OWNER
    _counting.py          # _count_controlled_sites, _count_controlled_sites_by_troops,
                          #   _count_runtime_cards_by_aspect, _scaled_vp_award_count
    _focus.py             # _focus_requirement_met, _focus_requirement_met_for_aspect,
                          #   _action_focus_requirement_met (move from generic_runtime)
    _resources.py         # _grant_resource, _reshuffle_discard_into_deck
    _promotion.py         # _promote_card, _apply_promote_instruction,
                          #   _deferred_promotion_target_ids
    _free_actions.py      # _apply_free_assassinate, _apply_free_deploy,
                          #   _apply_return_spy, _apply_recruit,
                          #   _special_stack_config, _remaining_special_stack_count,
                          #   _is_aberrations_enabled, SPECIAL_RECRUIT_STACKS
    _paid_ability.py      # _ability_cost_affordable, _pay_ability_cost,
                          #   _can_activate_pending_ability
    rules.py              # keep _apply_play_card, _apply_assassinate, etc.
    generic_runtime/       # package from Phase 1
```

### Implementation Steps

1. Create each new `_*.py` module
2. Move functions from `helpers.py` to appropriate module
3. Update all imports in `rules.py`, `generic_runtime/` sub-modules, and any test files that import from `helpers`
4. Delete `helpers.py`
5. `pytest` must pass

**Important:** Private modules (prefixed with `_`) signal "internal to engine, not public API." The public API stays in `engine/__init__.py`.

---

## Execution Order & Test Gates

| Phase | Description | Risk | Test Gate |
|-------|-------------|------|-----------|
| 1 | Split `generic_runtime.py` into package | Low — pure reorganization | `pytest` full pass |
| 3 | Unify execution models | Medium — normalization must be exact | `pytest` full pass |
| 4 | Reduce redundant validation | Low — simplification | `pytest` full pass |
| 5 | Split `helpers.py` into focused modules | Low — pure reorganization | `pytest` full pass |
| 2 | Flatten custom_effect | **DEFERRED** — cost > benefit | N/A |

Phase 2 is explicitly deferred — the double-dispatch is harmless once files are small.

---

## What Changes for `catalog.json`

**Nothing.** The 125 cards' JSON data is not modified. All normalization happens at runtime in `_resolve_generic_execution()`.

---

## Key Files Changed Per Phase

### Phase 1
- **Delete:** `engine/generic_runtime.py`
- **Create:** `engine/generic_runtime/__init__.py`, `_resolve.py`, `_selection.py`, `_actions.py`, `_custom_effects.py`, `_promotion_helpers.py`
- **Modify:** `engine/rules.py` (import path may change if package import differs)

### Phase 3
- **Modify:** `engine/generic_runtime/_resolve.py` (normalization function, unified `_auto_resolve_pending_generic`)
- **Modify:** `tests/test_generic_interpreter.py` (PendingGenericChoiceState construction)

### Phase 4
- **Modify:** `engine/generic_runtime/_actions.py` (shared validators, simplified appliers)

### Phase 5
- **Delete:** `engine/helpers.py`
- **Create:** `engine/_registry.py`, `_board.py`, `_counting.py`, `_focus.py`, `_resources.py`, `_promotion.py`, `_free_actions.py`, `_paid_ability.py`
- **Modify:** `engine/rules.py`, `engine/generic_runtime/_resolve.py`, `_selection.py`, `_actions.py`, `_custom_effects.py` (import paths)