# Plan: More Complexity Demons — Beyond generic_runtime

## What This Plan Addresses

Previous refactor split `generic_runtime.py` (2279 lines) into a 7-file package. But grug now look around and find more demons hiding. Plan covers 4 demons, ordered by grug's pain level.

## Demons Found (Read-Only Inspection)

| File | Lines | Demon |
|------|-------|-------|
| `interface/game_viewer.py` | 1973 | `GameViewerApp` class is **1560 lines** (line 368 to ~1928) — bigger than the old `generic_runtime.py` was |
| `interface/board_creator.py` | 1680 | `BoardCreatorApp` class is **~1500 lines** (line 88 to ~1660) — same shape |
| `engine/generic_runtime/_actions.py` | 925 | 13 inline `if x < 0 or x >= len(...)` checks; created `_validate_slot_bounds()` in Phase 4 but only used in **1 of 14 sites** |
| `tests/test_rules.py` | 2756 | 100+ `def test_*` functions in one file. Bigger than any source file. New God File. |
| `engine/state.py` | 543 | 27 Pydantic models. The `ExecutionModel` still has `Literal["sequence", "modal_choice", "repeat_choice"]` even though runtime only emits "sequence"/"repeat_choice" now (Phase 3 normalization) |
| `game_view.py` | 654 | Has 26 functions, mostly `_describe_*_label` and `_describe_*_option` — repetitive string-formatting helpers for UI |

## Goals (80/20, grug says)

1. Break `GameViewerApp` God Class into focused sub-objects
2. Break `BoardCreatorApp` God Class into focused sub-objects
3. Apply the `_validate_slot_bounds()` helper to remaining 13 sites in `_actions.py`
4. Split `tests/test_rules.py` into one test file per card-family / per rule-area
5. Remove dead `modal_choice` literal from `ExecutionModel` type (Pydantic `Literal`) after updating test data fixtures

## Non-Goals

- NOT splitting `engine/_actions.py` (925 lines). Game rules ARE complex. grug already said this.
- NOT splitting `engine/state.py` (543 lines). Well-organized Pydantic models, not a god file.
- NOT splitting `game_view.py` (654 lines). Repetitive but not god-class shape — each function is small and focused.
- NOT touching `interface/cli.py`, `parser.py`, `dialogs.py` — all small.

## Why This Is Different From Previous Plan

The previous plan was about the engine runtime. This plan is about:
- **UI/Application layer** (the two God Classes) — these affect every developer's daily friction
- **Test organization** (test file too big) — affects every test author
- **Cleanup of incomplete work** (apply validators everywhere) — pay debt from last refactor
- **Type literal hygiene** (dead enum value) — small win, big clarity

---

## Phase 1: Apply `_validate_slot_bounds()` Everywhere (DONE LAST TIME, INCOMPLETE)

**Why:** Phase 4 added `_validate_slot_bounds()` and `_validate_node_exists()` to `_utils.py` but only applied `_validate_node_exists` + one slot check. 12 more slot-bounds checks in `_actions.py` still use the old inline form.

**Changes in `engine/generic_runtime/_actions.py`:**

For each of these line ranges, replace inline `if idx < 0 or idx >= len(...)` with `_validate_slot_bounds(seq, idx, "field_name")`:

- Line 80 — hand_index check in `_apply_devour_once` (hand)
- Line 88 — inner_circle_index in `_apply_devour_once` (inner_circle)
- Line 104 — market_slot in `_apply_devour_once` (market)
- Line 313 — target_slot_index in `_apply_generic_assassinate_troop` (already done — verify)
- Line 462 — target_slot_index in `_apply_generic_return_unit`
- Line 526, 528 — source/target slot_index in `_apply_generic_move_troop`
- Line 571 — hand_index in `_apply_generic_force_discard`
- Line 625, 633, 649 — hand/discard indices in `_apply_generic_promote_card` (multiple)
- Line 728, 738 — inner_circle/market indices in `_apply_generic_play_card`

Also: node-existence checks (`if node_id not in state.board.nodes`) — use `_validate_node_exists()`:
- Lines around 315 (assassinate — already done)
- Line 388, 460 (supplant, return_unit)
- Line 590 (return_spy free path)
- Line 721 (steal_white_trophy in custom_effect)
- Line 808 (play_card with market_slot)

**Estimated impact:** ~20 line reductions, one fewer source of "did you remember to validate" mistakes.

**Test gate:** `pytest tests/test_generic_interpreter.py tests/test_state_machine.py tests/test_scenarios.py tests/test_rules.py`

---

## Phase 2: Remove Dead `modal_choice` Literal

**Why:** After Phase 3 normalization, runtime never produces `execution_kind="modal_choice"`. The Pydantic `Literal` in `engine/state.py` line 337 still allows it (for backward compat with test fixtures that we already updated). Dead enum value = cognitive noise.

**Changes:**

1. `engine/state.py` line 337:
   ```python
   execution_kind: Literal["sequence", "modal_choice", "repeat_choice"]
   ```
   becomes
   ```python
   execution_kind: Literal["sequence", "repeat_choice"]
   ```
   
2. Verify no test fixture still produces `modal_choice` in `execution_kind` (we already updated test_scenarios.py at line 233).

3. Verify `catalog.json` has no `execution_kind: "modal_choice"` (the catalog uses `kind: "modal_choice"` on `ModalChoiceExecutionModel` instances, which is a different field — `ExecutionModel.kind`, not `PendingGenericChoiceState.execution_kind`).

**Estimated impact:** ~1 line. Forces a check that nothing's left.

**Test gate:** `pytest tests/`

---

## Phase 3: Split `tests/test_rules.py` (2756 lines → ~5 files)

**Why:** 100+ test functions in one file. New God File. Test files should be focused so:
- Tests for a feature live near the code they test (LoB principle)
- When adding tests, you know which file
- Test failures tell you which area broke

**Current organization:** Tests are roughly by card name (alphabetical: bounty_hunter, deathblade, dragon_cultist, ...). Many are "test_X_does_Y" — fine, but file is too big.

**Proposed split (by rule area, not by card name):**

```
tests/
    test_rules_basics.py          # ~200 lines  — play_card, deploy, assassinate, recruit, end-of-turn
    test_rules_promotion.py      # ~300 lines  — all promote-related tests
    test_rules_ability.py        # ~300 lines  — paid ability activate/decline
    test_rules_focus.py          # ~250 lines  — focus requirement tests
    test_rules_cards_a_m.py      # ~600 lines  — cards starting A-M (alphabetical split #1)
    test_rules_cards_n_z.py      # ~700 lines  — cards starting N-Z (alphabetical split #2)
    test_rules_softlock.py        # ~200 lines  — softlock / stuck state tests
    test_rules.py                 # DELETED
```

**Estimated impact:** File sizes drop from 2756 to ~300-700 each. Easier navigation. Same test count, same coverage.

**Risk:** Pytest discovers them automatically. Just need to move the file contents.

**Test gate:** `pytest tests/` — must still pass with same count.

**Note on `test_first_ten_cards.py` (385 lines):** This already exists and seems to test a different aspect (card catalog, perhaps). Don't merge with above split.

---

## Phase 4: Break `GameViewerApp` God Class (1973 lines, class from line 368)

**Why:** This is the worst demon. Single Tkinter class does:
- UI construction (`_build_ui` line 495, 291 lines)
- Game state sync (`_sync_*` methods, ~300 lines)
- Mouse/keyboard event handling (20+ `_on_*_click`, `_on_*_hover`, `_on_*_key_*` methods, ~500 lines)
- Zoom, layout, responsive sizing (~200 lines)
- Move application, filter management (~100 lines)
- Card popup display, hover details (~150 lines)
- File save/load (~80 lines)

**Grug approach:** Extract 4-5 focused objects with narrow interfaces. Each object owns one concern.

**Proposed split:**

```python
# interface/game_viewer.py — shrinks from 1973 to ~500 lines
class GameViewerApp:
    """Thin coordinator. Builds UI, wires components, runs mainloop."""

    def __init__(self, ...): ...
    def _build_ui(self) -> None: ...  # mostly delegates
    def mainloop(self) -> None: ...

# interface/viewer/state_syncer.py — new, ~400 lines
class StateSyncer:
    """Owns: refreshing the displayed state from GameState."""
    def sync(self, state: GameState, view: GameView) -> None: ...
    def _sync_market_row(self, ...) -> None: ...
    def _sync_played_row(self, ...) -> None: ...
    def _sync_hand_row(self, ...) -> None: ...
    def _sync_other_player_discard_boxes(self, ...) -> None: ...
    def _sync_option_box(self, ...) -> None: ...
    def _set_vp_breakdown(self, ...) -> None: ...

# interface/viewer/event_router.py — new, ~500 lines
class EventRouter:
    """Owns: all mouse/keyboard event handlers."""
    def __init__(self, syncer, state_provider, ...): ...
    def on_canvas_click(self, event): ...
    def on_hand_canvas_click(self, event): ...
    # all 20+ on_* methods
    def _card_index_at_point(self, ...): ...
    def _node_id_at_point(self, ...): ...

# interface/viewer/zoom_controller.py — new, ~200 lines
class ZoomController:
    """Owns: zoom level, fit-to-screen, responsive layout."""
    def zoom_in(self) -> None: ...
    def zoom_out(self) -> None: ...
    def zoom_reset(self) -> None: ...
    def auto_fit(self) -> None: ...
    def on_resize(self) -> None: ...

# interface/viewer/card_popup.py — new, ~150 lines
class CardPopup:
    """Owns: hover popup, tooltip-like display."""
    def show(self, card: CardView, x: int, y: int) -> None: ...
    def hide(self) -> None: ...
```

**Estimated impact:**
- `GameViewerApp` shrinks from 1560 to ~500 lines (3x reduction)
- Each new class has one job, narrow interface
- Test coverage possible per class (currently untestable as monolith)

**Risk:** Tkinter's tight coupling between widgets and event handlers makes some extractions awkward. The event handlers reference `self.foo` all over the place. Will need to pass dependencies in.

**Test gate:** Manual smoke test (launch viewer, play one turn, save/load). Tkinter apps are hard to unit-test. May need to add 1-2 smoke tests that check the viewer starts.

---

## Phase 5: Break `BoardCreatorApp` God Class (1680 lines, class from line 88)

**Why:** Same shape as GameViewerApp. Single Tkinter class does:
- Board editing UI (`_build_ui` line 153, 153 lines)
- Drawing, mouse handling (`_on_canvas_*` methods, ~250 lines)
- File save/load (`_save*` methods, ~80 lines)
- Undo/redo (`_undo`, `_redo`, snapshot management, ~100 lines)
- Node editing (`_edit_selected_*`, `_prompt_*_metadata`, ~400 lines)
- Shortcut key bindings (12 `_shortcut_*` methods, ~80 lines)
- Zoom/grid (`_zoom_*`, `_on_grid_*`, ~80 lines)
- Background image management (`_load_background_image_dialog`, etc., ~200 lines)

**Proposed split:**

```python
# interface/board_creator.py — shrinks from 1680 to ~400 lines
class BoardCreatorApp:
    """Thin coordinator. Builds UI, wires components."""
    def __init__(self, ...): ...
    def _build_ui(self) -> None: ...  # mostly delegates
    def mainloop(self) -> None: ...

# interface/board_creator/canvas_editor.py — new, ~300 lines
class CanvasEditor:
    """Owns: drawing, mouse drag, node creation."""
    def on_canvas_press(self, event): ...
    def on_canvas_drag(self, event): ...
    def on_canvas_release(self, event): ...
    def on_canvas_double_click(self, event): ...
    def _create_site_node(self, ...): ...
    def _create_route_node(self, ...): ...

# interface/board_creator/node_editor.py — new, ~400 lines
class NodeEditor:
    """Owns: site/route metadata dialogs, node selection, editing."""
    def edit_selected_node(self): ...
    def _edit_selected_site(self, ...): ...
    def _edit_selected_route(self, ...): ...
    def _prompt_site_metadata(self): ...
    def _prompt_route_metadata(self): ...

# interface/board_creator/undo_manager.py — new, ~120 lines
class UndoManager:
    """Owns: snapshot stack, undo/redo, dirty tracking."""
    def __init__(self): ...
    def push(self, snapshot, message): ...
    def undo(self) -> dict | None: ...
    def redo(self) -> dict | None: ...
    def mark_saved_baseline(self): ...
    def is_dirty(self) -> bool: ...

# interface/board_creator/background_manager.py — already exists at 134 lines
# (existing file, no change needed but maybe move to package)

# interface/board_creator/shortcut_handler.py — new, ~80 lines
class ShortcutHandler:
    """Owns: keyboard shortcut bindings."""
    def bind_all(self, root): ...
    # 12 _shortcut_* methods
```

**Estimated impact:**
- `BoardCreatorApp` shrinks from ~1500 to ~400 lines (4x reduction)
- `UndoManager` becomes testable (snapshot/restore logic is pure)
- `NodeEditor` becomes testable (metadata dialogs could be mocked)

**Risk:** Same Tkinter coupling. Less than GameViewer because most of the methods are smaller.

**Test gate:** Manual smoke test + 2-3 unit tests for UndoManager (pure logic).

---

## Execution Order & Test Gates

| Phase | Description | Risk | Test Gate |
|-------|-------------|------|-----------|
| 1 | Apply `_validate_slot_bounds` everywhere | Low | `pytest` |
| 2 | Remove dead `modal_choice` literal | Low | `pytest` |
| 3 | Split `test_rules.py` | Low (file moves only) | `pytest` same count |
| 4 | Break `GameViewerApp` | Medium (Tkinter coupling) | Manual smoke + pytest |
| 5 | Break `BoardCreatorApp` | Medium (Tkinter coupling) | Manual smoke + pytest |

Phases 1-3 are pure cleanup / no-logic-change. Safe.
Phases 4-5 are structural. Each is independently shippable.

---

## Key Files Changed

### Phase 1
- `engine/generic_runtime/_actions.py` (use shared validators everywhere)

### Phase 2
- `engine/state.py` (narrow Literal)

### Phase 3
- Delete `tests/test_rules.py`
- Create `tests/test_rules_basics.py`, `test_rules_promotion.py`, `test_rules_ability.py`, `test_rules_focus.py`, `test_rules_cards_a_m.py`, `test_rules_cards_n_z.py`, `test_rules_softlock.py`

### Phase 4
- `interface/game_viewer.py` (slim down)
- Create `interface/viewer/state_syncer.py`, `event_router.py`, `zoom_controller.py`, `card_popup.py`

### Phase 5
- `interface/board_creator.py` (slim down)
- Create `interface/board_creator/canvas_editor.py`, `node_editor.py`, `undo_manager.py`, `shortcut_handler.py`

---

## What grug NOT Do (and why)

- **NOT** split `engine/generic_runtime/_actions.py` further. 925 lines for 18 game actions is fine — game rules are inherently complex. Splitting would spread the complexity, not trap it.
- **NOT** split `engine/state.py`. 543 lines of well-organized Pydantic models. The shape is already clear.
- **NOT** split `engine/helpers.py` (620 lines). Module already has clear section headers (`# ── board helpers ──`, `# ── counting helpers ──`, etc.). Adding 8 module files creates more import ceremony than it removes.
- **NOT** add a `interface/viewer/__init__.py` and a `interface/board_creator/` package when 4 new files in the same directory would do. Don't over-organize.

---

## Done Criteria

- `interface/game_viewer.py` < 600 lines
- `interface/board_creator.py` < 500 lines
- `tests/test_rules.py` does not exist (replaced by 7 focused files)
- 0 inline `if idx < 0 or idx >= len(...)` patterns in `_actions.py` (all use `_validate_slot_bounds`)
- 0 Pydantic validators allow `"modal_choice"` in `PendingGenericChoiceState.execution_kind`
- All existing tests still pass (no test count regression)
- `pytest` clean
- `ruff check` clean in modified paths
