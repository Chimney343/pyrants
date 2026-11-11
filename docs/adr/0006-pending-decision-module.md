# ADR-0006: One module owns the pending decision stack

- **Status:** Active (candidate 2 complete for the promotion stacks; `pending_ability` and `pending_generic` storage deferred — retargeted by ADR-0011 to an engine brief after lane D)
- **Date:** 2026-11-06
- **Decision owner:** maintainers
- **Supersedes:** -
- **Superseded by:** -

## Context

Four mechanisms make the engine wait for a player decision: the
`pending_immediate[16]` promotion stack, the `pending_eot[16]` promotion stack,
`pending_ability`, and `pending_generic` (25 fields plus a parent chain capped
at 16). Their priority was encoded only as branch order in `rules.c`, clone,
save, hash, describe and the Python bindings each handled a different subset,
and F-035 recorded that a save taken while a decision was pending reloaded as a
different game: `engine_serialize_state` refused only `pending_generic`, wrote
none of the pending records, dropped `shuffle_seed`/`shuffle_counter`, and the
loader rebuilt the game with seed 42.

The move payloads, `decisions.jsonl` schema and NN action ids are frozen. The
scenario document is a data format, not a wire format, and the scenario loader
must keep reading the committed schema-v1 documents.

## Decision

- `engine_c/pending.c` is the single owner of the pending decision stack. It
  owns the ordering (`pending_peek`, `pending_priority`), the promotion stack
  operations (`pending_promotion_count/at/mut/push/pop/set_count`), clone,
  hash, describe, and JSON save/load.
- `PendingKind` and `PendingDecision` stay internal to C. No mirrored ctypes
  struct is added: ADR-0011's game handle owns the Python-facing decision
  record, which C renders as one JSON document (`engine_pending_decision_json`).
- `PENDING_CHANCE` is reserved for ADR-0002's postponed F-003 frame and is not
  built.
- The scenario document gains `schema_version: 2` at the root and, under
  `state`, a `pending` object (`kind`, `priority`, `count`, and the four
  pending payloads) plus `shuffle_seed` and `shuffle_counter`.
- A document without `pending` is schema v1: it loads with no pending decision,
  and the loader keeps seed 42 and the setup's shuffle counter. The committed
  `data/scenarios/*.json` files are v1 and keep loading, except two:
  `tests/c_engine/test_engine_c.py` rewrites
  `test_card_generation/_ae_opt1_test.json` and `_we_focus_test.json` on every
  run, so they are saved as v2 and were committed that way in `f6470c4`.
- The serializer no longer refuses to save a state with a pending generic
  choice. The loader restores the generic frame's `current_actions` from the
  catalog by `source_card_id` and `current_option_id`, for the whole parent
  chain; the restored allocations live in the state's own arena, so
  `engine_destroy` frees them.
- The loader rebuilds the game with the document's `shuffle_seed` and then
  restores `shuffle_counter`, so the RNG stream continues where the save left
  it.

## Consequences

`rules.c`, `helpers.c` and `generic_runtime.c` no longer read or write the
pending arrays directly: every promotion push, pop, count and head lookup goes
through the module. The branch order that encoded the priority now lives in
one table, and `pending_peek` is the single answer to "what is the engine
waiting on?". F-035 is fixed: a pending immediate promotion, an end-of-turn
promotion, a paid ability and a generic choice all survive a save/load round
trip, together with the shuffle stream.

The module is a deep one: the interface is a dozen functions over a kind
enum, and the deletion test concentrates the ordering, the stack mechanics and
the four pending record shapes back into `rules.c`, `helpers.c`,
`generic_runtime.c` and `saveload.c` rather than making them vanish. Its
limits are deliberate: `pending_ability` and `pending_generic` still live in
`GameState` and are reached directly outside the module, so the module owns
their clone, hash, describe and persistence but not yet their storage. That
migration was deferred to candidate 8; ADR-0011 retargets it to a separate
engine brief after lane D. Once the Python side reads the handle's JSON decision
record, no Python code reads pending storage at all, so where it lives stops
touching the Python interface: it becomes a C-internal refactor, and lane D's
`custom_effect` split will first remove many of its reach-ins (42 of about 95
outside `pending.c` are in `generic_runtime.c`).

The scenario schema changed, so a scenario written by this engine and read by
an older build loses the pending state; the frozen artifacts (`decisions.jsonl`,
`replay.json`, NN action ids) are untouched.

## Speed

Measured after the fact, on 2026-11-06. The paired 32-game run (200 sims,
4 players, 16 workers, `--uct-c 1.4`, seed 42) compares `57e0883`, the last
engine commit before this candidate, against `f355e4f`, which has the same
engine as `f6470c4`. Baseline run `20261106T164410Z_f5f647468a20`, candidate
run `20261106T191411Z_bda107c0eaf4`:

- All 32 games are content-identical, so the decision stack does not change
  search.
- Run-wall games/h went from 83.7 to 86.8. The per-game wall ratio has a
  median of ×1.015 (range 0.964–1.076).

That is no regression, and the gain is within the noise between repeat runs of
one build, which is up to about 6% in run-wall games/h.

Dirty flags, DLL hashes and per-game numbers for this pair are in
`docs/architecture-review/speed-records.md`, which is the durable record:
`artifacts/` is gitignored. Both trees were dirty here; baseline DLL
`1899a19f2ca3…`, candidate `69e80052d0fb…`.
