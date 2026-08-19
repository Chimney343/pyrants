# Engine Status

Use this file for the current engine surface, the active gameplay backlog, and the main unresolved rules questions.

## Source Of Truth

Implementation:
- `engine_c/` (C engine: state, rules, moves, phases, scoring, generic_runtime)
- `engine_c/bindings/` (Python bindings to `engine_c.dll`)
- `interface/game_viewer.py`

Checks:
- `engine_c/tests/` (C unit tests)
- `tests/c_engine/` (C-binding tests)

Supporting status files:
- `docs/cards-status.md`
- `docs/generated/engine_action_gap_report.md`

## Done

- The core turn loop exists: setup (mandatory free troop placement), draw, main phase, end of turn, cleanup, and game over are all in place.
- Each player places one free troop on a site during the SETUP phase before any hand is dealt. Only after every player has placed does the game draw 5 cards per player and enter MAIN.
- The engine uses pure state models, legal-move generation, and move application as its main control flow.
- Generic-card execution is live in the C engine, including targeted, modal, and repeat selection flows.
- Headless session, simulation, and scenario save/load are in place through `engine_c/bindings/session.py` and the viewer tools.
- The current test suite is green, so the implemented behavior is consistent at the present coverage level.
- Initial placement moves are legal only during SETUP and target site nodes with empty troop slots. Routes are excluded.

## Awaiting

- Cleanup reshuffle still needs a true shuffle path that stays deterministic under seed control.
- Site-control scoring still needs one authoritative rule path so end-of-turn and final scoring cannot diverge.
- Coverage should expand around reshuffle behavior, control-source consistency, and other rule-sensitive edge cases.
- Richer board-driven play and cleaner setup-variant support still need follow-up work outside the core rules loop.

## Unclear

- Several project-level rule questions remain open: tie-break policy, no-legal-move handling, simultaneous-effect ordering, visibility rules, and exact endgame timing on market depletion.
- Older rules notes mix implemented clarifications with still-open policy questions, so they should be read as history, not as the live spec.
- Site control remains the most important unresolved rules question because it affects both running score and final scoring.

## Related Files

- Archived rules briefs, phase reviews, and backlog notes live in `docs/archive/`.
- For card-execution breadth, use `docs/cards-status.md` and the generated gap report.
