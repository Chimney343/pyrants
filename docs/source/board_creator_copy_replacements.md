# Board Creator Copy Replacements

Date: 2026-04-28

This is an exhaustive replacement map for user-facing literals in the board creator surface.
Scope includes strings passed to status bar updates, dialogs, and input prompts in `interface/board_creator.py` and `interface/interaction_handlers.py`.

## Status And In-Flow Messages

| Current text | Proposed replacement |
|---|---|
| Ready | Ready to edit board data |
| Mode: {MODE_STATUS_LABELS[self.mode]} | Mode: {MODE_STATUS_LABELS[self.mode]} |
| Grid snapping {state} | Grid snapping {state}. |
| Zoom: {self.zoom_level:.2f}x | Zoom: {self.zoom_level:.2f}x |
| Created a new board package | Started a new board package |
| Loaded board '{self.board_id}' | Loaded board '{self.board_id}'. |
| Saved board package: {board_path.name} + {layout_path.name} | Saved board package: {board_path.name} and {layout_path.name}. |
| Updated canvas size | Canvas size updated |
| Loaded background image | Background image loaded |
| Cleared background image | Background image cleared |
| Site creation cancelled | Site creation canceled |
| Site '{metadata.label}' created. Click {metadata.troop_capacity} troop slots inside the site. | Site '{metadata.label}' created. Click {metadata.troop_capacity} troop slots inside the site bounds. |
| Route creation cancelled | Route creation canceled |
| Route {label} created | Route {label} created. |
| Troop slot must be inside the site rectangle | Troop slot must be inside the site bounds. |
| Captured slot. {remaining} remaining. | Troop slot added. {remaining} remaining. |
| Site '{node.label}' completed | Site '{node.label}' completed. |
| Dragging route waypoint | Dragging route waypoint. |
| Route selected. Click to add a waypoint. | Route selected. Click to add a waypoint. |
| Select a route first, then click to add a waypoint | Select a route first, then click to add a waypoint. |
| Added route waypoint | Route waypoint added. |
| Connection finalized | Connection finalized. |
| Connect selection cleared | Connection selection cleared. |
| Select a node to connect | Select the first node to connect. |
| Connecting from '{self.nodes[clicked_node_id].label}'. Select another node. | Connecting from '{self.nodes[clicked_node_id].label}'. Select the second node. |
| Select a different second node | Select a different second node. |
| '{first.label}' and '{second.label}' are already connected. Click once to finalize selection. | '{first.label}' and '{second.label}' are already connected. Click once to clear selection. |
| Connected '{first.label}' and '{second.label}'. Click once more to finalize selection. | Connected '{first.label}' and '{second.label}'. Click once more to clear selection. |
| Site edit cancelled | Site edit canceled |
| Site updated. Add {troop_capacity - len(node.troop_slots)} more troop slots. | Site updated. Add {troop_capacity - len(node.troop_slots)} more troop slots. |
| Site updated | Site updated. |
| Route edit cancelled | Route edit canceled |
| Route {node.label} updated | Route {node.label} updated. |
| Node deleted | Node deleted. |
| Nothing to undo | Nothing to undo. |
| Undo | Undid last change. |
| Nothing to redo | Nothing to redo. |
| Redo | Redid last change. |
| Moved node | Node moved. |
| Moved route waypoint | Route waypoint moved. |
| Site rectangle is too small | Site rectangle is too small. |
| Updated route waypoint | Route waypoint updated. |
| Select a route first to remove waypoints | Select a route first to remove waypoints. |
| Right-click near a waypoint to remove it | Right-click near a waypoint to remove it. |
| Removed route waypoint | Route waypoint removed. |

## Dialog Titles And Messages

| Current text | Proposed replacement |
|---|---|
| Board ID | Board ID |
| Board ID: | Board ID: |
| Invalid Board ID | Invalid Board ID |
| Board ID is required. | Enter a board ID. |
| Layout ID | Layout ID |
| Layout ID: | Layout ID: |
| Load layout | Load layout |
| Load an existing layout JSON for this board? | Load an existing layout JSON for this board? |
| Invalid board package | Invalid board package |
| Validation failed | Validation failed |
| Validation | Validation |
| Board package is valid. | Board package is valid. |
| Canvas width | Canvas width |
| Canvas width (pixels): | Canvas width (pixels): |
| Canvas height | Canvas height |
| Canvas height (pixels): | Canvas height (pixels): |
| Unsupported image | Unsupported image |
| Tk PhotoImage supports PNG/GIF/PPM/PGM by default. | Supported formats are PNG, GIF, PPM, and PGM. |
| Duplicate label | Duplicate label |
| A node with that label already exists. | A node with this label already exists. |
| Site Label | Site label |
| Site label: | Site label: |
| Invalid label | Invalid label |
| Site label is required. | Enter a site label. |
| Site Troop Capacity | Site troop capacity |
| Troop capacity: | Troop capacity: |
| Site VP Value | Site VP value |
| VP value: | VP value: |
| Site Initial Control Marker | Site initial control marker |
| Initial control marker (optional): | Initial control marker (optional): |
| Site Initial VP Tokens | Site initial VP tokens |
| Initial VP tokens: | Initial VP tokens: |
| Route VP Value | Route VP value |
| Route Initial Control Marker | Route initial control marker |
| Route Initial VP Tokens | Route initial VP tokens |
| Edit node | Edit node |
| Select a node first. | Select a node first. |
| Edit Site Label | Edit site label |
| Edit Site Troop Capacity | Edit site troop capacity |
| Edit Site VP Value | Edit site VP value |
| Edit Site Control Marker | Edit site control marker |
| Edit Site Initial VP Tokens | Edit site initial VP tokens |
| Edit Route VP Value | Edit route VP value |
| Edit Route Control Marker | Edit route control marker |
| Edit Route Initial VP Tokens | Edit route initial VP tokens |
| Delete node | Delete node |
| Delete '{node.label}' and remove all of its connections? | Delete '{node.label}' and remove all connections? |
| Unsaved changes | Unsaved changes |
| You have unsaved changes. Continue to {action_label} and discard them? | You have unsaved changes. Discard them and continue to {action_label}? |

## Notes

- Dynamic validation errors surfaced from `ValueError` payloads are intentionally not rewritten here.
- If adopted, these replacements should be paired with small behavior checks in collaborator tests.
