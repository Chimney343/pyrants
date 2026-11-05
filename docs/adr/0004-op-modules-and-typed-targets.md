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
- Migration is one leaf op at a time, starting with `return_spy`, then
  `place_spy`, `return_unit`, `deploy_troops`, `move_troop`,
  `assassinate_troop`, `supplant_troop`, `force_discard`, and `recruit_card`.
  A C test at the op-table interface asserts the descriptor is complete, the
  legacy dispatcher reaches it, the typed target round-trips, apply matches
  card behavior, and unmigrated ops still fall back.
- Op describe callbacks receive the viewer's node-id/label arrays so target
  labels are produced by the op without duplicating node naming in each op.

## Consequences

`return_spy`, `place_spy`, `return_unit`, `deploy_troops`, `move_troop`,
`assassinate_troop`, `supplant_troop`, `force_discard` and `recruit_card` now
answer from the op table; their selection, target derivation, apply and
describe callbacks live in `engine_c/ops/return_spy.c`,
`engine_c/ops/place_spy.c`, `engine_c/ops/return_unit.c`,
`engine_c/ops/deploy_troops.c`, `engine_c/ops/move_troop.c`,
`engine_c/ops/assassinate_troop.c`, `engine_c/ops/supplant_troop.c`,
`engine_c/ops/force_discard.c` and `engine_c/ops/recruit_card.c`. The legacy
`sel_return_spy`/`apply_return_spy_gen`, `sel_place_spy`/`apply_place_spy`,
`sel_return_unit`/`apply_return_unit`, `sel_deploy`/`apply_deploy_troops`,
`sel_move_troop`/`apply_move_troop`, `apply_assassinate_troop`,
`apply_supplant_troop`, `sel_force_discard` and
`sel_recruit`/`apply_recruit_card_gen` registry entries are removed for those
ops. The shared `legal_assassinate_supplant_moves` selector is used by both op
modules through their `enumerate` wrappers. `force_discard` keeps its
`target_scope="opponent"` auto-apply cases ahead of the op lookup and keeps the
legacy auto-apply path; only its selection-requiring forms are op-dispatched.
`place_spy` keeps its rulebook decline as a valid null target;
`deploy_troops` keeps its empty-barracks decline (which grants the VP) as a
valid null target; and all nine reproduce the legacy `last_selection` records
so follow-up actions keep working. The pending counter key/increment helpers
moved from `actions.c` to `helpers.c` so op modules can share them, and
`engine_card_name` exposes the catalog display name to op describe callbacks.
The colon parser and `find_sel`/`atoi` code remain for the other ops until
their migrations.

`op_lookup` is a small name scan. It is called on the selection/apply paths;
the table is small and this is not a hot-loop concern for the first ops. The op
describe now owns both the modal option label and the generic move-target label
for migrated ops; `engine_node_label` is the shared node-label helper.
