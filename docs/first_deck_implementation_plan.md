# First Deck Families and Catalog Plan

Derive a canonical finite effect-family registry from `docs/first_deck_review.md`, use that registry to replace `data/cards/catalog.json` with loader-compatible normalized card data, and produce an engine coverage report that maps every final family to current engine support. The family registry has to be frozen first because both catalog generation and engine-gap review depend on the same stable action vocabulary.

## Steps

1. Freeze the source input from `docs/first_deck_review.md`. Parse the 125 reviewed card blocks, validate required fields, confirm there are no blocked or deferred entries, and capture cards whose notes preserve corrected or truncated workbook text. This becomes the only source of truth for downstream family and card generation.
2. Define the final family-registry schema for `data/cards/effect_families.json`. Each family record should include a stable family id, a canonical human-readable description, machine-readable action sequence, required targets, conditions, state reads, state writes, and card-specific parameter slots. Resolve exact duplicates and intentional near-duplicate merges here so the family list is finite and stable. This step blocks steps 3 and 4.
3. Map each card to the final family registry and design the normalized card entry shape for `data/cards/catalog.json`. Keep the current loader-facing `CardDefinition` envelope intact: `card_id`, `name`, `cost`, `aspect`, `deck_vp`, `inner_circle_vp`, `effect_key`, and `effect_payload`. Put card-specific parameters, thresholds, filters, modal branches, and per-card state or action descriptors into `effect_payload`. Preserve secondary workbook taxonomy such as `aspect_2` only through an intentional model change if engine behavior truly needs it; otherwise keep it in the machine-readable payload or metadata layer. Depends on step 2.
4. Build the engine coverage matrix from the final families against the current engine. Compare each family's required state or action contract to `engine/state.py` (`CardDefinition`, `BoardState`, `PlayerState`, `GameState`), `engine/moves.py` (move variants), and `engine/rules.py` (`legal_moves`, `apply`, registered effect handlers). Mark each family supported, partial, or unsupported, and classify each gap as a state-representation, move-generation, or rule-application problem. Depends on step 2 and can run in parallel with step 3.
5. Reconcile any loader or model constraints that block direct replacement of `data/cards/catalog.json`. If normalized data requires fields or payload structure the current loader or model cannot safely retain, update the plan slice around `engine/state.py` and `game_setup/loaders.py` before the catalog swap so no semantics are silently dropped. Depends on steps 3 and 4.
6. Produce the deliverables together: the canonical registry in `data/cards/effect_families.json`, the replaced `data/cards/catalog.json`, and a written engine gap report with phased remediation ordering and targeted tests. The report should explicitly flag the critical missing primitives already identified in discovery: devour-pile state, white-troop distinction, modal choice moves, targeted spy placement, supplant, move-enemy-troop, discard mechanics, scaling math, and effect composition or sequencing. Depends on steps 4 and 5.
7. Validate the generated data and audit outputs. Load the generated catalog through `game_setup/loaders.py` using `build_game_definition_from_dicts` or `build_game_definition_from_files`, run focused setup, rules, and scoring tests, and confirm every final family used in the catalog has a corresponding support status in the engine gap report. Depends on step 6.

## Relevant Files

- `docs/first_deck_review.md` — reviewed source semantics, provisional families, and note corrections to preserve
- `data/cards/catalog.json` — direct replacement target for normalized card data
- `data/decks/base_setup.json` — deck and card-id reference validation surface during catalog replacement
- `engine/state.py` — `CardDefinition`, `CardCatalog`, `BoardState`, `PlayerState`, `GameState` constraints
- `engine/moves.py` — current move primitives to compare against family action requirements
- `engine/rules.py` — effect registry, legal move generation, and application boundaries
- `game_setup/loaders.py` — loader/build chain used to validate normalized data
- `tests/test_setup.py` — loader and data-reference validation
- `tests/test_rules.py` — existing move or effect execution coverage and future family-gap tests
- `tests/test_scoring.py` — scoring or VP validation surface for scaling families

## Verification

1. Validate parsing against `docs/first_deck_review.md`: 125 reviewed cards, 0 blocked or deferred, required fields present, and exactly one family assignment per card.
2. Validate `data/cards/effect_families.json` invariants: unique family ids, no orphan cards, one canonical description per family, and complete machine-readable state, action, and condition definitions.
3. Validate the replaced `data/cards/catalog.json` through `game_setup/loaders.py` and confirm all card ids remain unique and loader-compatible.
4. Run `tests/test_setup.py` plus the focused portions of `tests/test_rules.py` and `tests/test_scoring.py` that exercise data loading, existing effect handlers, and scoring shape.
5. Cross-check the engine gap report against the final catalog so every family used in the catalog has a support status and every unsupported or partial family cites the blocking state field, move type, or rule boundary.

## Decisions

- Canonical human-readable family descriptions plus machine-readable state or action definitions will live in `data/cards/effect_families.json`.
- `data/cards/catalog.json` is replaced directly, but it must keep the current loader-facing `CardDefinition` envelope so `game_setup/loaders.py` and existing tests remain usable.
- Engine review output includes both gap flags and a phased remediation or test plan.
- Preserve secondary taxonomy such as `aspect_2` only if it is needed for engine legality or execution; otherwise keep it as machine-readable metadata rather than forcing an immediate engine schema change.
- Scope includes deriving families, generating normalized card data, and flagging engine capability gaps. Scope excludes implementing new engine mechanics unless the task is expanded.
- Scope also excludes rebuilding deck composition in `data/decks/base_setup.json` unless validation shows card-reference changes are required or the task expands to full first-deck setup wiring.
