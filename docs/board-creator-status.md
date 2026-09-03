# Board Creator Status

Use this file for the current board-authoring surface: implemented editor behavior, pending polish, and remaining contract notes. As of 2026-08-30.

## Source Of Truth

Implementation:
- `interface/board_creator.py`
- `interface/background_manager.py`
- `interface/board_renderer.py`
- `interface/package_manager.py`
- `interface/state_history.py`
- `interface/interaction_state.py`
- `game_setup/board_package.py`
- `game_setup/loaders.py`

Data and checks:
- `data/boards/tyrants_of_the_underdark.json`
- `data/layouts/base_game_layout.json`
- `tests/test_board_creator_collaborators.py`
- `tests/test_board_package.py`

## Done

- The editor loads and saves topology and layout files separately, so rules data stays separate from view geometry.
- Core authoring flows are in place: add site, add route, connect nodes, edit metadata, move nodes, delete nodes, and validate before save.
- Route waypoint editing, zoom, pan, grid snapping, and undo/redo history are all implemented.
- Background-image handling and canvas sizing are split into dedicated collaborators instead of one large UI class.
- The board data contract already includes `initial_troop_slots`, and the renderer shows white-enabled slots distinctly.

## Awaiting

- The board creator still has a pending UX-copy sweep. The replacement inventory (`docs/source/board-creator-copy-replacements.md`) exists, but it has not been applied to the live strings.
- A tighter manual or automated check for user-facing messages would help once that copy pass lands.
- Older phase notes still mention planned graphical-board and layout-editor work. Those notes are now historical, not the current status.

## Unclear

- Older docs referred to `interface/interaction_handlers.py`, but the current collaborator file is `interface/interaction_state.py`.
- The layout and package contract now lives mainly in code and tests, not in one large prose guide.
- Some older backlog notes still describe board topology and layout as missing inputs even though the repo already contains working base-game files.

## Related Files

- Archived board creator notes live in `docs/archive/`; the pending copy-sweep inventory lives in `docs/source/`.
- Use the files listed above for exact behavior and validation rules.
