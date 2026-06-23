# Site rendering: VP label, control border, total-control hatching

## Scope
Only `interface/game_renderer.py` (the Tkinter canvas game view). The CLI text
renderer `interface/display.py` and the `game_viewer`/`replay_viewer` side panels
are out of scope (those "Control VP" strings are not site-rectangle interior
labels).

## Current behavior (`game_renderer.py:_draw_site`)
- Interior text: `f"Owner: {owner}  Control VP: {occupancy.control_vp}"`, font
  `("Segoe UI", 9)` (not bold). Drawn below the troop row.
- Border: only **total** control (`_total_control_owner`) recolors the outline to
  the player's color; majority-only control does NOT change the border.
- No hatching for total control.

## Target behavior
1. Remove the `"Owner: x"` portion from the site interior text.
2. Replace `"Control VP: x"` with `"VP: x"` rendered in **bold**.
3. **Control** (troop majority, via `_derive_control_owner`) → site rectangle
   border becomes that player's color (`PLAYER_COLORS[owner]`).
4. **Total control** (via `_total_control_owner`) → additionally draw **hatching**
   (diagonal lines) inside the rectangle in a colour **one shade lighter** than
   the player's color. Total control implies control, so the border stays the
   player's color and hatching is added on top of the fill.

### Semantics decisions (to lock in)
- "control" = `_derive_control_owner` (strict troop-majority owner, ignoring
  spies). "total control" = `_total_control_owner` (all troop slots same player
  AND no enemy spies).
- `white`-only troops: `_derive_control_owner` returns `None` for white, so white
  "control" → default border (no recolor). Treated as non-player.
- Border color for both control and total control uses the (same) player's
  `PLAYER_COLORS` entry; hatching uses a lightened variant of that same color.
- Hatching style: 45° diagonal line segments, fully clipped inside the
  rectangle bounds, drawn after the base rectangle and before the VP/troop
  overlays. Lighten factor ~1.25 (channels scaled, clamped to 255).

## TDD steps (Red → Green → Refactor), all tests in `tests/test_game_renderer.py`

The file already has `_CanvasStub` (records `create_line/rectangle/text/oval`)
and helper tests for `_derive_control_owner`/`_total_control_owner`. New tests
drive `_draw_site` **directly** with a synthetic `BoardNodeView` +
`NodeOccupancyView` so specific control states are easy to construct (crafting
these via a real session is impractical).

### Step 1 — VP label change (update existing test + new direct test) [RED]
- Update the existing `test_site_rectangle_uses_bounds_and_site_label_above`
  (lines 118–120): replace the `Owner:`/`VP:` assertion with:
  - no interior text contains `"Owner:"`
  - at least one interior text starts with `"VP:"`
  - that VP text's `font` tuple contains `"bold"`
  Run → **fails** (current text has `Owner:` and is not bold).
- Add `test_site_vp_label_is_bold_without_owner` (direct `_draw_site` call,
  occupancy `control_vp=3`): assert the only bottom text is `"VP: 3"` and its
  font has `"bold"`. Run → **fails**.

### [GREEN]
- In `_draw_site`: replace `site_text` with `f"VP: {occupancy.control_vp}"`
  and font `("Segoe UI", 9, "bold")`; drop the `owner = _derive_control_owner(...)
  or "none"` usage for the label (the `_derive_control_owner` call stays for the
  border logic in Step 2). Run → both pass.

### Step 2 — Control-colored border [RED]
- Add `test_site_majority_control_border_is_player_color`: direct `_draw_site`
  with `troop_slots=("p1","p1",None)` (majority p1, NOT total), `spies=()`.
  Assert the `create_rectangle` call's `outline` kwarg ==
  `PLAYER_COLORS["p1"]`, and assert **no** `create_line` calls (no hatching).
  Run → **fails** (current border stays default for non-total control).
- Add `test_site_no_control_border_is_default`: `troop_slots=("p1","p2",None)`
  (tie). Assert `outline == DEFAULT_SITE_OUTLINE`, no `create_line`. Run →
  **passes already** (keep as regression guard).

### [GREEN]
- In `_draw_site`, replace the border decision:
  ```python
  control_owner = _derive_control_owner(occupancy.troop_slots)
  total_owner = _total_control_owner(occupancy.troop_slots, occupancy.spies)
  if control_owner is not None:
      outline = PLAYER_COLORS.get(control_owner, DEFAULT_SITE_OUTLINE)
  elif is_highlighted:
      outline = "#1e62c7"
  else:
      outline = DEFAULT_SITE_OUTLINE
  ow = 3 if (is_highlighted or control_owner is not None) else None
  ```
  Run → passes.

### Step 3 — Lighten helper [RED]
- Add `test_lighten_color_produces_lighter_valid_hex`:
  - `_lighten_color("#000000")` → each channel strictly greater, 6-hex string.
  - `_lighten_color("#2f72c4")` → each output channel >= input channel and <= 255.
  - `_lighten_color("#ffffff")` → stays `"#ffffff"` (clamp).
  Run → **fails** (no `_lighten_color`).

### [GREEN]
- Add `_lighten_color(hex_color, factor=1.25) -> str` in `game_renderer.py`:
  parse `#rrggbb`, scale each channel by `factor`, clamp to 255, return
  `#rrggbb` lowercase. Run → passes.

### Step 4 — Total-control hatching [RED]
- Add `test_site_total_control_draws_lighter_hatching_inside_bounds`: direct
  `_draw_site`, `troop_slots=("p1","p1","p1")`, `spies=()` → total control p1.
  Assert:
  - at least one `create_line` call with `fill` kwarg ==
    `_lighten_color(PLAYER_COLORS["p1"])`
  - for every such lighter-colored `create_line`, all 4 numeric endpoints lie
    within the rectangle bounds (x in [left, left+w], y in [top, top+h])
  - the rectangle `outline` kwarg == `PLAYER_COLORS["p1"]` (border still player
    color)
  Run → **fails** (no hatching drawn).

### [GREEN]
- Add a hatching routine in `_draw_site` (or a small local helper) that, when
  `total_owner is not None`, draws 45° diagonal line segments inside the rect
  bounds using `_lighten_color(PLAYER_COLORS[total_owner])` as `fill`. Generate
  intercept-stepped lines, clip each segment to the rectangle. Draw right after
  `draw_site_base(...)`, before the VP label. Run → passes.

### Step 5 — Regression / refactor
- Run full `tests/test_game_renderer.py` and `ruff check
  interface/game_renderer.py`. Keep the existing
  `test_total_control_site_gets_player_colored_border` (still true: some sites
  have no control → default outline present).
- Refactor only if hatching line generation duplicates logic; otherwise leave
  inline. No new behavior beyond the tests.

## Notes for implementation
- `BoardNodeView` and `NodeOccupancyView` are frozen dataclasses; construct
  directly in tests with matching `troop_slot_points` length (>= troop_slots
  length) and `bounds=(left, top, w, h)`.
- `_CanvasStub` already records `create_line` (line 34) — hatching tests can
  inspect line calls. Direct `_draw_site` tests have no `draw_edges` lines, so
  all `create_line` calls in those tests are hatching only.
- Do not touch `interface/display.py`, `game_viewer.py`, `replay_viewer.py`, or
  `board_creator.py` — their "Control VP" strings are unrelated side-panel /
  CLI text.
- After edits: `ruff check .` and `python -m pytest tests/test_game_renderer.py`.
