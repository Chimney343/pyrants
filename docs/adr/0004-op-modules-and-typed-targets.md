# ADR-0004: One op module and a typed target behind one op table

- **Status:** Active (migration in progress)
- **Date:** 2026-11-05
- **Decision owner:** maintainers
- **Supersedes:** -
- **Superseded by:** -

## Context

A card op's knowledge was split across three registries
(`register_generic_actions`, `register_selection_handlers` and
`action_requires_selection`), an untyped `kind:a:b:c` target string, and four
separate readers of that string (`apply_resolve_generic_choice`, `actions.c`,
`describe.c`, `label_enrich.py`/`nn/actions.py`). Card fixes repeatedly touch
several of those places, and a single op's target semantics can drift between
them.

The move payload strings, `decisions.jsonl` and NN action ids are frozen. The
change must keep every op's observable move set, payload and card execution
identical.

## Decision

- Each migrated op lives in its own `engine_c/ops/<op>.c` module.
- A `CardOp` descriptor owns `needs_selection`, `enumerate`,
  `target_from_move`, `apply` and `describe`.
- One central `op_table` in `engine_c/ops/op.c` dispatches migrated ops.
  Unmigrated ops continue through the legacy registries until they are
  migrated.
- The typed `OpTarget` record is built from the frozen `Move` payload at the
  apply boundary. The `Move` string remains the wire format; no payload,
  decisions or action-id change is allowed.
- Migration is one leaf op at a time, starting with `return_spy`. A C test at
  the op-table interface asserts the descriptor is complete, the legacy
  dispatcher reaches it, the typed target round-trips, apply matches card
  behavior, and unmigrated ops still fall back.

## Consequences

`return_spy` now answers from the op table; its selection, target derivation,
apply and option-label describe are in `engine_c/ops/return_spy.c`. The legacy
`sel_return_spy`, `apply_return_spy_gen` registry entries are removed for that
op. The colon parser and `find_sel`/`atoi` code remain for the other ops until
their migrations.

`op_lookup` is a small name scan. It is called on the selection/apply paths;
the table is small and this is not a hot-loop concern for the first op. The op
describe currently owns the modal option label; the generic move-label path can
adopt it as more ops migrate.
