# ADR-0005: Card-specific semantics are loader-validated catalog fields

- **Status:** Active (candidate 4 runtime/card-id branches complete; op-selection variants and `custom_effect` deferred)
- **Date:** 2026-11-05
- **Decision owner:** maintainers
- **Supersedes:** -
- **Superseded by:** -

## Context

The engine still branches on card ids (`gauth`, `cloaker`, `mummy_lord`,
`grazzt`, `ambassador`, `insane_outcast`), on many `source_fragment` strings,
and on the `custom_effect` dispatcher. The same semantics are also duplicated
in JSON metadata and described in card notes. F-015 (Neogi's double discard)
is a symptom: timing and trigger behavior lives outside the catalog.

The move payloads, `decisions.jsonl`, and NN action ids are frozen. Catalog
JSON is data and may gain validated fields; the runtime must interpret them
without card-id checks.

## Decision

- Card-specific semantics move into named, loader-validated catalog fields.
  Fields use a fixed vocabulary; the loader rejects unknown values.
- The runtime reads the field from the loaded `CardDefinition`/`CardAction`
  instead of comparing `Sym` card ids or untyped `source_fragment` strings.
- Migrate one branch at a time, with a loader-rejection test and a behavior
  test at the new field interface.
- First field: `CardDefinition.on_discard`. `"inner_circle"` replaces the
  `ambassador` card-id checks in `discard_hand_card` and `apply_cleanup`;
  `SYM_NULL` means the discard pile. The loader rejects any other value.
- Second field: `CardDefinition.negative`. It replaces the `insane_outcast`
  card-id checks in promotion, devour and the negative-card grant path; the
  helper `negative_card_id` locates the catalog's negative card.
- Third field: `CardOption.viability`, a named predicate. The loader accepts
  `allow_without_targets` (Gauth option 2), `own_spy_and_other_troop`
  (Cloaker option 2), `enemy_white_trophy` (Mummy Lord option 2) and
  `own_spy_anywhere` (Graz'zt option 2). The four card-id viability branches
  are gone; the predicates are evaluated for both modal and repeat options.
- Fourth field: `CardAction.timing` is loader-validated to `immediate` or
  `end_of_turn`. End-of-turn actions are deferred to the EOT phase rather than
  executing inline during pending-generic resolution; the EOT phase applies
  promotions, force discard and scaled VP once. This fixes F-015.
- Fifth field: `CardAction.variant`, a loader-mapped enum for the compared
  `source_fragment` families. The six `force_discard` modes, six `scaled_vp`
  sources and two `on_*` triggers are typed; the descriptive string stays for
  labels and compatibility. Remaining family: op-selection variants.
- Remaining: the `custom_effect` effect-kind decomposition.
- The catalog JSON gains the fields; the C struct, Python ctypes mirror and
  layout probe grow with them. Move payloads, decisions and action ids do not
  change.

## Deferred after candidate 4

- The remaining op-selection `source_fragment` modes in the play/promote/
  devour/return_unit op modules are selection metadata inside the op table,
  not runtime card-id branches. They can be typed later without changing the
  catalog contract.
- `custom_effect` remains the 13-effect-kind dispatcher deferred from
  candidate 1. It needs a catalog-declared effect-kind table, not a shallow
  per-op wrapper.

## Consequences

`on_discard` is validated by `engine_load_definition_json`; invalid values
return NULL and a C catalog test locks that rejection. Ambassador's discard
behavior now comes from the catalog, so its card-id branch is gone from
`helpers.c` and `rules.c`. `negative` is a loader-read boolean; promotion,
devour and the Insane Outcast grant path use the loaded property instead of
the card id. `option_viability` is a loader-validated predicate; the
Gauth/Cloaker/Mummy Lord/Graz'zt card-id branches are gone, and a catalog
test rejects unknown predicate names. `timing` is validated to
`immediate`/`end_of_turn`; end-of-turn actions no longer execute inline, so
Neogi discards once (F-015). `CardAction.variant` types the six
`force_discard` modes, six `scaled_vp` sources and two `on_*` triggers; the
loader rejects unknown modes/triggers and the runtime switches on the enum
instead of `source_fragment` in the force op, needs-selection rules, EOT
phase, VP-count and reactive-trigger paths. The op-selection variants remain
until their named variants/fields land.

`custom_effect` remains a multi-effect dispatcher and is explicitly deferred;
its 13 effect kinds are catalog data that needs its own decomposition rather
than a shallow op wrapper.
