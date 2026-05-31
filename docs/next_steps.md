# Next Steps

Date: 2026-04-27

## Quick Answer: Different Decks

Yes, different decks are supported today [inferred].

- Setup model supports both starter deck and market deck definitions: [engine/state.py](engine/state.py#L121), [engine/state.py](engine/state.py#L127), [engine/state.py](engine/state.py#L128)
- Loader accepts an external setup file path: [game_setup/loaders.py](game_setup/loaders.py#L63), [game_setup/loaders.py](game_setup/loaders.py#L66)
- CLI allows selecting alternate setup, card, and board files at launch: [interface/cli.py](interface/cli.py#L109), [interface/cli.py](interface/cli.py#L110), [interface/cli.py](interface/cli.py#L111)

Current limitation [gap]: one game run uses one chosen setup file (one starter deck definition + one market deck definition). There is no in-session deck switching UI yet.

## What You Provide Next (User)

1. Canonical board topology data [gap]
- Full sites and routes list, node ids, node kind, troop capacity, VP values, and adjacency links.
- Confirm any initial markers or VP token placements.

2. Board visual layout data for a graphical board [inferred]
- For each node id, provide screen coordinates (x, y).
- Optional: route bend points or edge waypoints if straight lines are not enough.
- Optional: board background image and target canvas size.

3. Canonical card catalog [gap]
- Full card metadata for all cards.
- Effect key for each card and any card-specific parameters.

4. Deck variants [inferred]
- One setup file per variant you want to support, for example base, expansion A, expansion B.
- For each setup file: starter composition, market composition, market row size.

5. Rule clarifications needed to unblock full rules engine [gap]
- Assassinate, Deploy, Recruit, Return Spy exact legality and resolution.
- Focus and paid ability timing.
- Promote timing and optionality.
- Tie-break policy, no-legal-move behavior, and endgame timing details.

## What I Do Next (Assistant)

1. Fix Phase 6 high-risk issues first
- Implement true shuffle behavior during cleanup draw cycle.
- Unify site-control source of truth between end-of-turn scoring and final scoring.

2. Harden deck-variant support
- Add a small profile registry under data/profiles so selecting deck variants is one flag instead of three paths.
- Add tests that run the same engine flow against at least two distinct setup files.

3. Add graphical board rendering
- Create interface renderer for nodes and edges using layout coordinates.
- Render sites and routes distinctly and show occupancy state on top of nodes.

4. Add placement tool for sites and routes
- Build a layout editor where each node can be moved and saved back to layout JSON.
- Keep this fully in interface layer so engine stays pure.

5. Wire renderer to game state
- Select node and execute allowed actions through the same move parser and rules apply path.
- Keep gameplay authority in engine and treat UI as a view/controller only.

## Suggested Implementation Order

1. Rule and scoring fixes.
2. Add layout schema and sample full-board layout file.
3. Implement read-only graphical renderer.
4. Implement node placement editor.
5. Bind graphical actions to engine moves.
6. Expand deck profiles and variant tests.
