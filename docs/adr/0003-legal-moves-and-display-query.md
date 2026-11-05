# ADR-0003: Legal moves are applicable only; a display query serves the viewer

- **Status:** Active
- **Date:** 2026-11-05
- **Decision owner:** maintainers
- **Supersedes:** -
- **Superseded by:** -

## Context

`engine_legal_moves` used to emit two kinds of UI-only entries alongside real
moves:

- `resolve_generic` placeholders tagged `target_id = "unavailable"` for modal
  options that could not be chosen in the current state; and
- `MOVE_END_MAIN_PHASE` whenever the main-phase free-choice branch ran.

Five consumers compensated for that mixed contract: `engine_apply` rejected
placeholders, the C rollout compacted them, the old action-encoding helper
filtered them, `view.py` greyed them out, and `view.py` re-implemented a
deferred-promotion rule for end-main. F-019 showed the cost: sampling the unfiltered
list aborted 85-93% of rollouts onto a constant leaf value.

The move payloads, `decisions.jsonl` schema and NN action ids are frozen. The
OpenSpiel action map was already `enumerate()` over the filtered applicable
list, so removing placeholders preserves the relative order and the ids.

## Decision

- `engine_legal_moves` returns only moves that `engine_apply` accepts.
- `engine_display_moves(state, out, applicable, max)` returns the viewer's
  ordered list. `applicable[i]` is 1 for a legal move and 0 for a display-only
  entry: a non-viable modal option, or an end-main-phase entry carrying the
  deferred-promotion hint.
- Python exposes the same split: `legal_moves()` returns applicable moves;
  `display_moves()` returns `(move, applicable)` pairs. The viewer uses
  `display_moves()`.
- The end-main deferred-promotion rule is a display hint, not engine
  legality. `engine_apply` still accepts end-main and the player may then skip
  the promotion; the old `view.py` re-implementation is deleted.
- The old action-encoding helper module is deleted. Action ids are `_indexed_moves(adapter)`
  in `state_c.py`: the applicable list in native order, falling back to the
  display entries only when no applicable move exists (the old
  `compute_c_action_map` safety net, so a non-terminal state never exposes an
  empty action list). `NUM_DISTINCT_ACTIONS = 1024` lives in `game_c.py`.
- `engine_apply` keeps its placeholder guard as a defensive check against a
  caller that tries to apply a display-only entry.

## Consequences

Consumers no longer filter or re-derive legality. Tests that assert a greyed
option use `display_moves()`; tests that play or search use `legal_moves()`.
The C rollout no longer compacts placeholders. The frozen payloads, decisions
schema and action ids are unchanged: the display list keeps the old order, and
the applicable list is the same sequence the old filter produced. Candidate 4
can move card-specific legality metadata into the catalog without changing
this interface.
