# ADR-0004: One op module and a typed target behind one op table

- **Status:** Active (candidate 1 complete for 13 of 14 ops; `custom_effect` deferred to candidate 4)
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
  `assassinate_troop`, `supplant_troop`, `force_discard`, `recruit_card`,
  `devour`, `devour_cost`, `play_card`, and `promote_card`. A C test at the
  op-table interface asserts the descriptor is complete, the legacy dispatcher
  reaches it, the typed target round-trips, apply matches card behavior, and
  unmigrated ops still fall back.
- Op describe callbacks receive the viewer's node-id/label arrays so target
  labels are produced by the op without duplicating node naming in each op.

## Deferred: custom_effect

`custom_effect` is not a leaf op. It dispatches 13 effect kinds across 14
cards, with a 453-line target selector and a 168-line apply function, and its
needs-selection rule varies by effect kind. Wrapping that in one `CardOp`
descriptor with a boolean `needs_selection` would be a shallow move, not a
deep one: the complexity would simply move behind the descriptor.

Candidate 4 (the catalog as the whole card spec) owns the real decomposition:
declare the effect kinds and their targets as catalog fields, validate them in
the loader, and let the op/effect table dispatch from that data. Until then
`custom_effect` remains on the legacy selector/apply/describe path, and the
op-table completeness test records the exception explicitly.

## Consequences

`return_spy`, `place_spy`, `return_unit`, `deploy_troops`, `move_troop`,
`assassinate_troop`, `supplant_troop`, `force_discard`, `recruit_card`,
`devour`, `devour_cost`, `play_card` and `promote_card` now answer from the op
table; their selection, target derivation, apply and describe callbacks live
in `engine_c/ops/return_spy.c`, `engine_c/ops/place_spy.c`,
`engine_c/ops/return_unit.c`, `engine_c/ops/deploy_troops.c`,
`engine_c/ops/move_troop.c`, `engine_c/ops/assassinate_troop.c`,
`engine_c/ops/supplant_troop.c`, `engine_c/ops/force_discard.c`,
`engine_c/ops/recruit_card.c`, `engine_c/ops/devour.c` (shared by the
devour/devour_cost descriptors), `engine_c/ops/play_card.c` and
`engine_c/ops/promote_card.c`. The legacy
`sel_return_spy`/`apply_return_spy_gen`, `sel_place_spy`/`apply_place_spy`,
`sel_return_unit`/`apply_return_unit`, `sel_deploy`/`apply_deploy_troops`,
`sel_move_troop`/`apply_move_troop`, `apply_assassinate_troop`,
`apply_supplant_troop`, `sel_force_discard`,
`sel_recruit`/`apply_recruit_card_gen`, the `devour`/`devour_cost` registries,
`apply_devour`, and `sel_play_card`/`apply_play_card_nested` are removed for
those ops. `promote_card` keeps its no-selection forms (top-of-deck,
threshold-self, end-of-turn) on the legacy apply and its special needs-
selection checks ahead of the op lookup; only its selection forms are
op-dispatched. The shared `legal_assassinate_supplant_moves`,
`legal_devour_moves` and `legal_promote_card_moves` selectors are used by the
migrated op modules. `force_discard` keeps its `target_scope="opponent"`
auto-apply cases ahead of the op lookup and keeps the legacy auto-apply path;
only its selection-requiring forms are op-dispatched. `place_spy` keeps its
rulebook decline as a valid null target; `deploy_troops` keeps its
empty-barracks decline (which grants the VP) as a valid null target; and all
thirteen reproduce the legacy `last_selection` records so follow-up actions
keep working. The pending counter key/increment helpers moved from `actions.c`
to `helpers.c` so op modules can share them, and `engine_card_name` exposes the
catalog display name to op describe callbacks. The colon parser and
`find_sel`/`atoi` code now remain only for the deferred `custom_effect`
dispatcher; candidate 4 owns its decomposition.

The op describe now owns both the modal option label and the generic
move-target label for migrated ops; `engine_node_label` is the shared
node-label helper.

## Op descriptor cache (`57e0883`)

`op_lookup` is a name scan over the op table: `intern_str` plus one `strcmp`
per descriptor. With one migrated op that was harmless. With thirteen it sits
on the legal-move path, which the C rollout runs at every step:
`action_requires_selection` (`generic_runtime.c`) and
`legal_generic_target_selection_moves` (`selection.c`) resolve the op for each
pending action, as do `apply_resolve_generic_choice` and the three describe
sites.

`57e0883` resolves the descriptor once, when the loader parses the catalog
(`loader.c`: `a.op_impl = op_lookup(a.op)`), and stores the pointer on
`CardAction.op_impl`. Callers use `card_op_for(action)`, which returns the
cached pointer and falls back to the scan for an action built outside the
loader, where `op_impl` is NULL. The pointer refers to a static `const`
descriptor in the DLL, so it stays valid for the life of the process wherever
the action is copied. It is never serialized: a reloaded generic frame points its `current_actions` back
into the catalog (`pending.c`), and the catalog's actions carry the pointer.
`op_impl` is part of the mirrored `CardAction` layout, so `engine_bindings.py`
and the layout probe (`layout.c`) list it.

The cache does not change behaviour: the 32-game runs before and after it are
content-identical on all 32 games (see Speed).

## Speed

Measured after the fact, on 2026-11-06, with paired 32-game runs: 200 sims,
4 players, 16 workers, `--uct-c 1.4`, seed 42, compared with
`scripts/compare_paired_runs.py`. The `--uct-c 1.4` flag is required: the
default is now 5.0, and the earlier baselines used 1.4.

| Change | Baseline → candidate | Runs | Content | Run-wall games/h | Per-game median |
|---|---|---|---|---|---|
| 13 op migrations | `a985208` → `a03768f` | `20261106T193628Z_ca5eea69c707` → `20261106T195809Z_5513a9602b65` | identical decisions on all 32 games | 88.6 → 89.5 | ×1.031 |
| Op descriptor cache | `53cf800` → `57e0883` (pre-commit tree) | `20261106T105757Z_b6be8d1087e6` → `20261106T112844Z_df41f11c7216` | identical on all 32 games | 83.2 → 86.2 | ×1.031 |

Both runs of the op-migration pair were built in separate git worktrees, so
each `replay.json` records a different absolute data path in
`replay_context`. That is the only field that differs. `decisions.jsonl` and
`final_decks.json` match on every game.

Neither step is a regression, and both gains are within the noise between
repeat runs of one build, which is up to about 6% in run-wall games/h. A
committed `57e0883` rerun (`20261106T164410Z_f5f647468a20`) measured 83.7.

HEAD against `a985208` directly (`f355e4f`, run
`20261106T191411Z_bda107c0eaf4`) measures 88.6 → 86.8 games/h, per-game median
×0.979. It is not a measurement of this candidate. Between the two commits the
F-015 fix (`2163a45`, ADR-0005) changed the rules, so the games differ and HEAD
plays 2.5% more decisions (38,550 against 37,596). Per decision, HEAD's summed
game wall is about 1% higher, which is within noise.
