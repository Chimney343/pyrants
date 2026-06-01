# Board Creator

Date: 2026-04-27

## Purpose

The board creator is an interactive desktop app for authoring:

1. Board topology JSON (engine-facing rules data).
2. Board layout JSON (editor/view geometry data).

The app keeps these concerns separate so gameplay logic stays independent from coordinates and visual metadata.

## Launch

Run from workspace root:

```powershell
c:/Users/mkkom/pyrants/.venv/Scripts/python.exe -m interface.board_creator
```

Or with Just:

```powershell
just board-creator
```

Optional launch arguments:

```powershell
c:/Users/mkkom/pyrants/.venv/Scripts/python.exe -m interface.board_creator --board-path data/boards/base_game.json --layout-path data/layouts/base_game_layout.json
```

## Current Features

- Load board topology JSON.
- Load layout JSON (or auto-generate a starter layout if omitted).
- Load an optional canvas background image (PNG/GIF/PPM/PGM supported by Tkinter PhotoImage).
	- Layout `canvas.width` and `canvas.height` stay authoritative when loading persisted layout background paths.
	- Image dimensions are adopted only during explicit user background import.
	- Unsupported or missing persisted background paths are cleared from editor state on load.
- Add site by dragging a rectangle.
- Site popup captures site metadata.
- Site flow requires troop-slot clicks equal to troop capacity.
- Add route by clicking a point.
- Route number is auto-assigned incrementally and not entered by the user.
- Route popup captures route metadata except the route number.
- Edit route paths with Route Waypoints mode.
	- Click route to select.
	- Click empty space to add a waypoint.
	- Drag waypoint to reposition.
	- Right-click waypoint to remove.
	- Waypoint paths are rendered as straight segmented lines (no spline interpolation) when a route connects exactly two sites; route-to-route links and multi-neighbor routes keep explicit hub-style edges so each connection stays visible.
- Connect node adjacency in Connect mode with a 3-click flow.
	- Click 1 selects the first node.
	- Click 2 selects the second node and creates the connection.
	- Click 3 finalizes and clears both selections.
	- A single route may connect to multiple routes and/or sites.
	- Connections are unique; connecting the same pair again does not create duplicates.
- Move nodes by dragging in Select mode.
- Zoom in/out/reset and Ctrl+mouse-wheel zoom.
- Pan canvas with middle mouse button drag.
- Optional grid snapping for placement and drag repositioning.
- Undo/redo history for authoring actions, with dirty state computed from a saved baseline snapshot.
- Edit selected node metadata.
- Delete selected node and remove all of its edges.
- Validate package consistency before save.
- Save topology and layout as separate JSON files.

## Editor Architecture

The editor now composes focused collaborators instead of keeping all concerns in a single class:

- `interface/state_history.py` manages undo/redo stacks and baseline dirty-state checks.
- `interface/package_manager.py` handles board package load/build/save operations.
- `interface/background_manager.py` owns background image lifecycle and zoom-aware scaling.
- `interface/board_renderer.py` handles canvas drawing of grid, edges, nodes, and overlays.
- `interface/interaction_handlers.py` handles canvas press/drag/release/right-click interaction flows.
- `interface/board_creator.py` remains the Tk app orchestrator for menus, bindings, and workflow.

## Data Contract

### Topology file

Stored under `data/boards/*.json`.

Fields per node:

- `node_id`
- `kind` (`site` or `route`)
- `adjacent_to`
- `troop_capacity`
- `vp_value`
- `initial_troop_slots` (optional; length must equal `troop_capacity`; use `"white"` or `null`)
- `initial_control_marker`
- `initial_vp_tokens`

### Layout file

Stored under `data/layouts/*.json`.

Top-level fields:

- `layout_id`
- `board_id`
- `canvas.width`
- `canvas.height`
- `canvas.background_image`
- `nodes`

Layout node fields:

- `node_id`
- `label`
- `kind`
- `center`
- `bounds` (sites only)
- `troop_slots` (sites only)
- `waypoints` (routes only, optional)

## Validation Rules

Cross-file and schema validation enforces:

- `board_id` matches between topology and layout.
- Board and layout reference identical `node_id` sets.
- Node kinds match across files.
- Site troop-slot count equals site `troop_capacity`.
- Sites cannot define route waypoints.
- Route labels are numeric.
- Labels are unique across all sites and routes.
- Board adjacency is symmetric.

## Shortcuts

- `Ctrl+S`: Save
- `Ctrl+Shift+S`: Save As
- `Ctrl+Z`: Undo
- `Ctrl+Y`: Redo
- `Delete`: Delete selected node
- `E`: Edit selected node
- `G`: Toggle snap grid
- `+` / `-`: Zoom in/out
- `1`: Select mode
- `2`: Add Site mode
- `3`: Add Route mode
- `4`: Connect mode
- `5`: Route Waypoints mode

## Key Files

- `interface/board_creator.py`
- `interface/background_manager.py`
- `interface/board_renderer.py`
- `interface/interaction_handlers.py`
- `interface/package_manager.py`
- `interface/state_history.py`
- `game_setup/board_package.py`
- `game_setup/loaders.py`
- `data/layouts/base_game_layout.json`
- `tests/test_board_package.py`
- `tests/test_board_creator_collaborators.py`
