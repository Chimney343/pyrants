# Enhanced Replay Viewer Plan

## Goal

Upgrade `interface/replay_viewer.py` to match the game-viewer's visual capabilities while remaining a read-only replay stepper. Support the ISMCTS `replay.json` format natively.

## Current State

The replay viewer (`ReplayViewerApp`) is minimal:
- Single canvas (no zoom/pan) for the board map
- Step slider with Prev/Next buttons
- Text-only sidebar with move info, prompts, and player summaries
- No market row, hand cards, played cards, or detailed scoring

The game viewer (`GameViewerApp`) has:
- Zoomable/scrollable map canvas with Fit button
- Market row with special cards (House Guard, Priestess, Insane Outcast)
- Current player hand as rendered cards
- Current player played cards as rendered cards
- VP breakdown (controlled sites, trophy hall, deck VP, inner circle VP, etc.)
- Card hover popups with details
- Discard pile, inner circle, trophy hall dropdowns

The ISMCTS `replay.json` format includes `replay_context` with file paths, player IDs, and seed, which is already handled by `replay_views_from_payload()`.

## Changes

### 1. Add map zoom/pan to replay viewer

Bring over from game_viewer:
- Zoom in/out/Fit buttons above the map
- Mouse wheel zoom (Ctrl+wheel)
- Middle-button pan
- Scroll bars (horizontal + vertical)
- `_min_zoom` / `_max_zoom` / `zoom_level` state
- `_auto_fit_zoom()` and `_change_zoom()` methods

Files: `interface/replay_viewer.py`

### 2. Add market row panel

Port the market row rendering from game_viewer:
- `market_canvas` with scrollbar showing House Guard, Priestess, Insane Outcast special slots + regular market row cards
- Compact card rendering (`_draw_card_row` method)
- Market metadata line (deck A/B labels, market deck count, discard count)
- Detect aberrations in market from replay views (check if any market card has aspect matching aberrations)

Since this is a read-only viewer, no click-to-select interaction needed, but hover popups showing card details are useful.

### 3. Add current player hand + played cards panels

Port from game_viewer:
- Hand canvas showing current player's hand as rendered cards
- Played cards canvas showing cards played this phase
- Card hover popups for both

No selection or double-click-to-play needed (read-only), but visual display of card details is essential.

### 4. Add detailed scoring sidebar

Replace the simple player summary text with structured scoring matching game_viewer:
- VP breakdown line (score + controlled sites + total control + trophy + tokens + deck VP + inner circle VP + total)
- Starter pile summaries (House Guard, Priestess counts)

Port `_set_vp_breakdown` and `_starter_pile_summary` logic. Since replay viewer has `GameView` objects (not raw state), we need the `GameState` from the session or reconstruct from the view. The `replay_views_from_payload` only produces `GameView` tuples, not the session/state. We'll need access to the state for full VP breakdown.

### 5. Refactor to expose GameState alongside GameView

Problem: `replay_views_from_payload` returns `tuple[GameView, ...]` but VP breakdown, market metadata, and starter pile summaries need `GameState`. The current architecture rebuilds a `GameSession` internally and throws it away.

Options:
- **A**: Change `replay_views_from_payload` to also return the `GameSession` snapshots (or state objects) alongside each view. This gives full state access.
- **B**: Store the session itself and step through it on each render.

**Choice A** is cleaner. Add a parallel function or modify the existing one to return `list[tuple[GameView, GameSession]]` or similar. Actually, `GameView` is built from `GameSession` via `build_game_view()`, so we can just keep the session object and rebuild the view on each step change. This is what the function already does internally.

**Best approach**: Store the `GameSession` as a member, and on step change, replay moves up to the current index to rebuild state, then call `build_game_view()`. This gives us full `GameState` access.

Implementation detail: Instead of pre-computing all views upfront (which is memory-heavy for long replays), store the session and replay moves on demand. For 1001 steps, pre-computing all GameView objects is reasonable but wasteful. Change to lazy step-through:

```python
self.session = ...  # fresh session
self.replay_moves = [step["payload"] for step in replay_log]
# On step change, replay up to current_index from scratch
```

This also means we can call `build_game_view(session, node_names=...)` for full detail, and access `session.state` for VP breakdown, starter pile summaries, etc.

### 6. Support ISMCTS replay format

The ISMCTS `replay.json` includes `replay_context` with full paths, player IDs, seed, and deck IDs. This is already handled by `_resolve_replay_context`. However, the ISMCTS format also includes `deck_a_id` and `deck_b_id` in the context, which the standard replay doesn't. This doesn't break anything, but we should use the context's file paths.

The replay viewer CLI already has `--card-path` and `--setup-path` args. When `replay_context` is present in the payload, those paths take precedence. No change needed here.

### 7. Structural layout

New layout (matching game_viewer's structure, adapted for read-only replay):

```
+-------------------------------+--------------------+
| Controls: Prev Next Slider   | Status bar         |
+-------------------------------+--------------------+
| Market Row (House Guard,     |                    |
|  Priestess, Insane Outcast,   |  Sidebar:          |
|  market cards)                |  - Move info       |
+-------------------------------+  - Scoring         |
| Map (zoomable, scrollable)    |  - VP breakdown    |
|                               |  - Player summaries |
|                               |  - Prompts          |
+-------------------------------+  - Discard/IC/etc  |
| Current Player                |                    |
|   Hand cards                  |                    |
|   Played cards               |                    |
+-------------------------------+--------------------+
```

## Implementation Steps

1. **Rewrite `ReplayViewerApp.__init__`** to store the session instead of pre-computed views. Replay moves on step change.
2. **Add import constants** from game_viewer (card dimensions, special card IDs/tints, etc.) to avoid duplication.
3. **Add `_build_ui`** matching game_viewer's layout: market row, map with zoom, current player panel, sidebar.
4. **Add `_render_step`** that: rebuilds GameView from session state, renders map, market, hand, played, scoring.
5. **Add zoom/pan methods**: `_zoom_in`, `_zoom_out`, `_auto_fit_zoom`, `_change_zoom`, `_on_canvas_click` for node selection.
6. **Add card rendering**: `_draw_card_row`, `_sync_market_row`, `_sync_hand_row`, `_sync_played_row` (simplified, read-only).
7. **Add card hover popups**: `_show_card_popup`, `_hide_card_popup`, `_set_hover_card`.
8. **Add scoring**: `_set_vp_breakdown`, `_starter_pile_summary` ported from game_viewer.
9. **Add ISMCTS format handling**: Ensure the CLI loads ISMCTS replay files correctly via `replay_context`.
10. **Add keyboard shortcuts**: Left/Right arrow for step navigation, +/- for zoom.

## Files Modified

- `interface/replay_viewer.py` — major rewrite (the only file changed)

## Key Design Decisions

- **Static view list vs. lazy replay**: Switch from pre-computing all `GameView` objects to keeping the `GameSession` and replaying up to the current step on each render. This gives full `GameState` access for VP breakdown and avoids O(n) memory for long replays. Cost: O(k) per step change where k is current step index. Acceptable for interactive use.
- **No card selection / no move submission**: This is a read-only viewer. Cards are displayed but not clickable for move submission. Hover popups remain useful for card detail inspection.
- **Card rendering reuse**: Port `_draw_card_row` as a standalone method rather than extracting to a shared module. The method is ~120 lines and tightly coupled to the viewer state. Easier to maintain a copy in replay_viewer than create a shared abstraction.
- **Market aberrations detection**: Check `replay_context` for `deck_a_id`/`deck_b_id` to enable Insane Outcast slot, falling back to checking market cards.