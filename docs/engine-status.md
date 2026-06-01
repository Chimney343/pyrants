# Engine Status

Use this file for the current engine surface, the active gameplay backlog, and the main unresolved rules questions.

## Source Of Truth

Implementation:
- `engine/state.py`
- `engine/moves.py`
- `engine/rules.py`
- `engine/scoring.py`
- `game_session.py`
- `game_view.py`
- `game_simulation.py`

Checks:
- `tests/test_rules.py`
- `tests/test_state_machine.py`
- `tests/test_scoring.py`
- `tests/test_game_session.py`
- `tests/test_game_simulation.py`
- `tests/test_game_view.py`

Supporting status files:
- `docs/cards-status.md`
- `docs/generated/engine_action_gap_report.md`

## Done

- The core turn loop exists: main phase, end of turn, cleanup, and draw-up behavior are all in place.
- The engine uses pure state models, legal-move generation, and move application as its main control flow.
- Generic-card execution is live in `engine/rules.py`, including targeted, modal, and repeat selection flows.
- Headless session, simulation, and replay support are in place through `game_session.py`, `game_simulation.py`, and the viewer tools.
- The current test suite is green, so the implemented behavior is consistent at the present coverage level.

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
