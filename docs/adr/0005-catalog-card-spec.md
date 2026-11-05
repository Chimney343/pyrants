# ADR-0005: Card-specific semantics are loader-validated catalog fields

- **Status:** Active (candidate 4; first field landed)
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
- Subsequent fields: `negative`/special-card properties for `insane_outcast`,
  `option_viability` predicates for Gauth/Cloaker/Mummy Lord/Grazzt, a
  timing/trigger field for F-015, and the `custom_effect` effect-kind
  decomposition.
- The catalog JSON gains the fields; the C struct, Python ctypes mirror and
  layout probe grow with them. Move payloads, decisions and action ids do not
  change.

## Consequences

`on_discard` is validated by `engine_load_definition_json`; invalid values
return NULL and a C catalog test locks that rejection. Ambassador's discard
behavior now comes from the catalog, so its card-id branch is gone from
`helpers.c` and `rules.c`. The remaining card-id and source-fragment branches
stay until their named fields land.

`custom_effect` remains a multi-effect dispatcher and is explicitly deferred;
its 13 effect kinds are catalog data that needs its own decomposition rather
than a shallow op wrapper.
