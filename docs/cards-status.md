# Cards Status

Use this file for the current state of card modeling, catalog generation, and first-deck coverage.

## Source Of Truth

Runtime behavior:
- `data/cards/*.json`
- `engine_c/` (C engine runtime)
- `game_setup/loaders.py`

Pipeline inputs and reports:
- `docs/source/first_deck_review.md`
- `docs/generated/catalog_execution_audit.md`
- `docs/generated/engine_action_gap_report.md`
- `scripts/generate_first_deck_artifacts.py`
- `scripts/generate_catalog_execution_audit.py`
- `scripts/catalog_audit.py`

Checks:
- `tests/c_engine/` (per-card C-binding tests)

## Done

- The first-deck review pass is complete for 125 cards.
- The review log is now treated as a source artifact, not a status note.
- Runtime card behavior lives in `data/cards/*.json` through structured per-card definitions.
- The generic interpreter in the C engine covers the core action set used by the current catalog.
- The current generated audit is clean: 125 audited cards, 125 clean cards, 0 rules-text mismatches, 0 runtime gaps, and 0 heuristic-only findings.
- First-ten special cases now live in card metadata and generic execution models rather than card-id conditionals.

## Awaiting

- Some families are still partial or unsupported in `docs/generated/engine_action_gap_report.md` even though the current catalog runs.
- Some advanced effects still depend on coarse metadata such as `custom_effect`, `conditional_bonus`, or `source_fragment`.
- Deck-variant support works through file selection, but there is no smaller profile-level selection flow yet.
- The card pipeline is still script-driven and spread across several regeneration and audit steps.

## Unclear

- Older planning docs still make `data/cards/effect_families.json` sound like the long-term runtime model, but the project now treats it as analysis-only data.
- Generic interpreter coverage can look broader than it is because some semantics are encoded in metadata rather than in explicit top-level operations.
- When you need the real support boundary, use the generated gap report rather than archived narrative docs.

## Related Files

- Archived plans and dated sweep notes live in `docs/archive/`.
- Detailed source and generated card artifacts live in `docs/source/` and `docs/generated/`.
