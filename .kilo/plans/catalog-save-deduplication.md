# Plan: Catalog Versioned Reference for Saved Game States (Hybrid)

## Goal

Save files should NOT embed the full 125-card `CardCatalog` (currently ~259 KB per file, ~89-98% of every scenario file). Instead they store a `catalog_id` plus a `catalog_version` fingerprint. The engine resolves the catalog from `data/cards/catalog.json` on load and validates the version matches what was recorded. This:

- Prevents drift: card fixes in `catalog.json` are picked up by existing saves (or rejected with a clear error if the version changed).
- Eliminates duplication: ~34 MB of redundant catalog data across 130+ scenario files.
- Preserves reproducibility metadata: a save file records exactly which rules version produced it.

## Context: the use case

Pyrants uses save files for **both** test scenarios (130+ files under `data/scenarios/cards/`) **and** replays. Card definitions are **frequently changing** during development. The status quo (full embedded catalog) gives reproducibility at the cost of duplication and maintenance burden. The simple refactor (catalog_id only) gives maintainability but loses drift detection. The **hybrid** approach below gets both.

## Design

### High-level shape

1. **Catalog gets a version field.** `CardCatalog` model gains a `version: str` field (e.g. `"1.0.0"`). `data/cards/catalog.json` is updated to include it.
2. **Save side:** `Scenario.from_game_state` strips the catalog from `state_payload` (same as before) and writes `catalog_id` + `catalog_version` into `ScenarioMetadata`. The metadata already has `source_catalog_id` (`game_setup/scenarios.py:22`); we add `source_catalog_version` next to it.
3. **Load side:** `to_game_state` requires a `catalog_registry` (mapping `catalog_id` → `CardCatalog`). It resolves the catalog by id and **compares versions**:
   - **Match** → inject catalog, validate, return.
   - **Mismatch** → raise `CatalogVersionMismatchError` (a new typed exception) listing the expected and actual versions and suggesting remedies.
4. **No backward compatibility for the file format.** Legacy saves (with embedded catalog) are rejected with a clear error. Committed fixtures must be regenerated.
5. **In-memory shape unchanged.** All 24 `card_index(state.definition.catalog)` call sites stay the same. Engine remains pure. Only the persistence boundary changes.

### Why "version" specifically (not just hash)

A version string:
- Is human-readable: "save was made with catalog 1.2.0" is meaningful to a developer.
- Is bump-on-purpose: a maintainer changes the version when they intend to invalidate old saves.
- Maps cleanly to the existing `source_catalog_id` field — same conceptual slot.

A content hash would detect any silent change but would change on every save (e.g. formatting-only edits in `catalog.json`) and provide no hint to the user about *why* a save is stale.

Both could co-exist, but a version string is the simpler and more developer-friendly choice. The plan recommends **semver string only** for v1; a hash could be added later if more rigor is needed.

### What happens on version mismatch

The `to_game_state` path raises `CatalogVersionMismatchError` with a message like:

> Saved scenario was created with catalog `base_catalog` version `1.0.0`, but the loaded catalog is version `1.1.0`. The card definitions have changed since this save was made. To proceed, either (a) revert `data/cards/catalog.json` to version `1.0.0`, or (b) regenerate the save file, or (c) pass `force=True` to override (loads with current catalog, drift accepted).

`force=True` is a deliberate escape hatch for replays: a user can explicitly say "I know the rules changed, just play this old game with the new rules." It is **not** the default behavior.

## Step-by-Step Implementation

### Step 1: Add `version` to `CardCatalog`

`engine/state.py:159-172` — `CardCatalog` gains a `version: str = Field(min_length=1)` field next to `catalog_id`. The existing `_validate_unique_card_ids` model validator stays as-is.

Update `data/cards/catalog.json` to include `"version": "1.0.0"`.

Tests that construct `CardCatalog` programmatically (e.g. `tests/test_setup.py:24-32`) need a `version` value supplied; default for fixtures and tests should be `"1.0.0"`.

### Step 2: Add `CatalogRegistry` to `game_setup/loaders.py`

```python
def load_card_catalog(card_path: Path) -> CardCatalog:
    """Load a single card catalog from a JSON file."""

def build_catalog_registry(cards_dir: Path) -> dict[str, CardCatalog]:
    """Load every .json file in cards_dir, parse as CardCatalog, key by catalog_id."""

def resolve_catalog(catalog_id: str, registry: dict[str, CardCatalog]) -> CardCatalog:
    """Return the catalog for a given id; raise with a clear message if missing."""

def default_catalog_registry() -> dict[str, CardCatalog]:
    """Build a registry from the project-default data/cards/ directory."""
```

`build_catalog_registry` mirrors the existing `load_deck_rosters` pattern (`game_setup/loaders.py:32-50`).

### Step 3: Add `CatalogVersionMismatchError` to `game_setup/scenarios.py`

```python
class CatalogVersionMismatchError(ValueError):
    """Raised when a saved scenario's catalog version differs from the on-disk catalog."""

    def __init__(self, catalog_id: str, saved_version: str, current_version: str) -> None:
        super().__init__(
            f"Saved scenario was created with catalog '{catalog_id}' version "
            f"'{saved_version}', but the loaded catalog is version '{current_version}'. "
            f"To proceed, revert the catalog, regenerate the save, or pass force=True."
        )
        self.catalog_id = catalog_id
        self.saved_version = saved_version
        self.current_version = current_version
```

### Step 4: Add `source_catalog_version` to `ScenarioMetadata`

`game_setup/scenarios.py:14-25` — add `source_catalog_version: str = ""` next to `source_catalog_id`. Default empty for legacy-shape detection; new saves always write the version.

### Step 5: Strip catalog on save in `game_setup/scenarios.py`

Modify `Scenario.from_game_state` (line 35):

```python
@classmethod
def from_game_state(
    cls,
    state: GameState,
    *,
    scenario_id: str = "",
    description: str = "",
    tags: list[str] | None = None,
    card_under_test: str | None = None,
    move_count: int = 0,
    is_terminal: bool = False,
    catalog_version: str | None = None,  # NEW
) -> Scenario:
    return cls(
        metadata=ScenarioMetadata(
            scenario_id=scenario_id or state.definition.definition_id,
            description=description,
            tags=tags or [],
            card_under_test=card_under_test,
            source_board_id=state.definition.board.board_id,
            source_catalog_id=state.definition.catalog.catalog_id,
            source_catalog_version=catalog_version or state.definition.catalog.version,  # NEW
            source_setup_id=state.definition.setup.setup_id,
            move_count=move_count,
            is_terminal=is_terminal,
        ),
        state_payload=state.model_dump(mode="json", exclude={"definition": {"catalog": True}}),
    )
```

The result: `state_payload.definition` does **not** contain a `catalog` key. The `metadata.source_catalog_id` + `metadata.source_catalog_version` are the references.

### Step 6: Rehydrate + version-check on load in `game_setup/scenarios.py`

Modify `Scenario.to_game_state` (line 62):

```python
def to_game_state(
    self,
    *,
    catalog_registry: dict[str, CardCatalog],
    force: bool = False,
) -> GameState:
    payload = self.state_payload
    catalog_id = self.metadata.source_catalog_id
    saved_version = self.metadata.source_catalog_version
    catalog = resolve_catalog(catalog_id, catalog_registry)
    if not force and saved_version and catalog.version != saved_version:
        raise CatalogVersionMismatchError(catalog_id, saved_version, catalog.version)
    payload["definition"]["catalog"] = catalog
    return GameState.model_validate(payload)
```

`load_game_state_from_scenario(path, *, catalog_registry, force=False)` (catalog_registry required, force optional, default False).

### Step 7: Plumb registry through `GameSession`

`game_session.py:62-65` — `GameSession.from_scenario_file(path)` becomes `GameSession.from_scenario_file(path)`. Inside, it builds the registry by calling `default_catalog_registry()` and passes it to `load_game_state_from_scenario`. The `catalog_registry` parameter on the lower-level loaders is required.

`GameSession.from_files(...)` already does the right thing (it uses the live catalog from the file path); no change there.

### Step 8: Update call sites

| File | Lines | What changes |
|------|-------|--------------|
| `tests/test_scenarios.py` | 120, 135, 143, 160, 229, 246, 263, 276, 300, 305, 311, 319, 325, 336 | Tests that load fixture files under `data/scenarios/`. Pass `catalog_registry=...` (built from a known path in the test, e.g. `data/cards/catalog.json`). |
| `tests/test_state_generator.py` | 12, 201, 204, 225 | Same. |
| `interface/game_viewer.py` | 875 (`GameSession.from_scenario_file(Path(path))`) | Auto-resolves via the internal default registry. If a user loads an old replay with a different catalog version, the error message points them at `--force` or how to revert. |
| `interface/cli.py` | uses `from_files` | Unaffected. |

### Step 9: Tests

Add new tests in `tests/test_scenarios.py`:

1. `test_save_strips_catalog_from_payload` — saved JSON's `state_payload.definition` does not contain a `catalog` key.
2. `test_save_records_catalog_version` — saved `metadata.source_catalog_version` reflects the on-disk catalog's version.
3. `test_load_with_registry_rehydrates_catalog` — round-trip save → load with explicit registry yields `state.definition.catalog` populated.
4. `test_load_with_matching_version_succeeds` — happy path: same version recorded and on disk.
5. `test_load_with_mismatched_version_raises` — recording version `1.0.0` but disk has `1.1.0` raises `CatalogVersionMismatchError` with both versions in the message.
6. `test_load_with_force_overrides_version_mismatch` — `force=True` loads the current catalog despite a recorded mismatch.
7. `test_save_file_size_drops_significantly` — regression guard: new payload is dramatically smaller than the embedded-catalog version.
8. `test_legacy_save_with_embedded_catalog_raises_clear_error` — a fixture file with `state_payload.definition.catalog` populated is rejected (the message names the offending field and points at regeneration).

### Step 10: Regenerate committed fixtures (required)

After implementing, regenerate:

- The four canonical scenarios under `data/scenarios/`: `initial_two_player.json`, `mid_turn_two_player.json`, `pending_modal_choice.json`, `scoring_test.json`.
- The 130+ batch-generated files under `data/scenarios/cards/`.

Use `just generate-card-scenarios` and `just generate-card-scenario <id>` for the batch file; canonical fixtures may need a dedicated regen command (TBD — check if there's a script for canonical scenarios).

The new files will:
- Have `state_payload.definition.catalog` removed.
- Have `metadata.source_catalog_id = "base_catalog"`.
- Have `metadata.source_catalog_version = "1.0.0"` (or whatever the catalog version is at the time).

The repo size drops from ~34 MB of catalog duplication to a few hundred KB.

## Files Touched

| File | Change |
|------|--------|
| `engine/state.py` | Add `version: str` to `CardCatalog` |
| `data/cards/catalog.json` | Add `"version": "1.0.0"` |
| `game_setup/loaders.py` | Add `load_card_catalog`, `build_catalog_registry`, `resolve_catalog`, `default_catalog_registry` |
| `game_setup/__init__.py` | Re-export new helpers |
| `game_setup/scenarios.py` | Add `CatalogVersionMismatchError`, `source_catalog_version` field, strip catalog on save, rehydrate + version-check on load, add `force` parameter |
| `game_session.py` | `from_scenario_file(path)` builds registry internally and passes to `load_game_state_from_scenario` |
| `tests/test_scenarios.py` | Add new tests; update existing scenario-loading tests to pass a registry |
| `tests/test_state_generator.py` | Update scenario-loading tests to pass a registry |
| `tests/test_setup.py` | Supply `version` when constructing `CardCatalog` programmatically |
| `data/scenarios/*.json` | Regenerate (4 files) |
| `data/scenarios/cards/*.json` | Regenerate (~130 files) |

## Files NOT touched (key invariants preserved)

- All 24 `card_index(state.definition.catalog)` call sites in `engine/`, `interface/`, `game_view.py`, etc. — no change. At runtime, `state.definition.catalog` is still a fully populated `CardCatalog`; the change is only at the persistence boundary.
- `engine/rules.py`, `engine/helpers.py`, `engine/scoring.py`, `engine/generic_runtime/*` — no change. Engine remains pure.
- `game_setup/loaders.py:80-93` — `build_game_definition_from_files` unchanged.
- `game_setup/loaders.py:96-118` — `create_game_state_from_files` unchanged.
- `game_simulation.py`, `interface/cli.py`, `interface/replay_viewer.py`, `interface/board_creator.py` — all use the from-files path, not the from-scenario path. Unaffected.
- `interface/game_viewer.py` save-loading code — only the registry plumbing changes internally; the user-facing API (`--replay-log-path`) is unaffected. Version-mismatch errors surface to the user as clear messages.

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| `data/cards/catalog.json` missing at load time → save files fail to load | `resolve_catalog` raises `ValueError` with a clear message naming the missing `catalog_id` and searched paths |
| Tests that don't run from project root → `default_catalog_registry()` fails | Tests that load scenarios pass an explicit registry constructed from a known path |
| Version mismatch on a saved replay that the user wants to play with current rules | `force=True` is provided as an explicit escape hatch; default behavior is strict |
| Catalog changes (typo fix, balance) silently break behavior in old test scenarios | Strict version check fails loudly; tests must be regenerated to pick up the new version |
| Replays from old versions of the game become unplayable | `force=True` lets the user opt in to playing old replays with new rules. For a true archival use case, snapshots of the catalog at each version can be kept in `data/cards/v1.0.0/catalog.json`, `data/cards/v1.1.0/catalog.json`, etc. — the registry scans the directory, so this works out of the box. |
| `source_catalog_version` is empty string (old save) | Empty saved_version is treated as "no version recorded" — load proceeds without check. New saves always record the version. |
| `card_id` referenced in save file not present in current catalog | Pre-existing concern. With `force=True`, drift is accepted. Without `force=True`, the model validator at `GameState.model_validate` fails loudly. |

## Open Questions

1. **Versioning scheme.** Semver (`"1.0.0"`)? Calver (`"2026.06"`)? Just `"draft"` until release? Recommend semver for forward-compatibility; the project is pre-release so `0.x.y` is fine.
2. **Where to keep old catalog snapshots.** If the project wants true archival replays (replay an old game with the exact rules it was played under), the catalog should be versioned and old versions kept. The directory-scan registry design supports this: drop `data/cards/v1.0.0/catalog.json` in, it auto-registers. This is **not** part of the refactor; it's a future option enabled by the registry design.
3. **Should `force=True` be exposed in `GameSession.from_scenario_file`?** Yes — power users (replay viewers, debuggers) need it. The internal `default_catalog_registry()` build stays, but `force` is a kwarg.
4. **Should there be a "regenerate canonical scenarios" just command?** Check for existing scripts; if none, add one as part of the refactor. Canonical scenarios are likely hand-tuned, not batch-generated, so they need a specific entry point.

## Implementation Order

1. Add `version` field to `CardCatalog` model. Update `data/cards/catalog.json`. Update tests that build `CardCatalog` programmatically.
2. Add registry helpers to `game_setup/loaders.py` (+ re-exports in `game_setup/__init__.py`).
3. Add `CatalogVersionMismatchError` to `game_setup/scenarios.py`.
4. Add `source_catalog_version` to `ScenarioMetadata`.
5. Update `Scenario.from_game_state` to strip catalog and record version. Add `catalog_version` parameter to `save_game_state` for overrides.
6. Update `Scenario.to_game_state` and `load_game_state_from_scenario` to require a `catalog_registry`, version-check, support `force=True`. No legacy-shape branching.
7. Update `GameSession.from_scenario_file` to build registry internally and pass it down. Add `force` kwarg.
8. Update test call sites to pass an explicit registry (built from a known path).
9. Add new tests (no legacy-shape compatibility test — only a test that the legacy shape is *rejected*).
10. Run the full test suite.
11. **Regenerate** all committed save fixtures — both the canonical scenarios under `data/scenarios/` and the 130+ batch-generated files under `data/scenarios/cards/`. Any pre-refactor save file must be deleted and regenerated.
12. Spot-check file sizes: `data/scenarios/cards/001_aboleth.json` should drop from ~292 KB to ~33 KB (mostly board topology + state).

## Verification

- `pytest -q` passes (no behavioral change to engine rules).
- `ruff check .` passes.
- `data/scenarios/cards/*.json` sizes verified reduced ~89% after regeneration.
- `GameSession.from_scenario_file("data/scenarios/initial_two_player.json")` works after regenerating the canonical fixture.
- A newly-saved scenario loads correctly via `load_game_state_from_scenario(path, catalog_registry=...)`.
- Loading a legacy save file (one that still embeds the full catalog) fails fast with a clear error.
- Loading a save file recorded with version `1.0.0` against a catalog at version `1.1.0` raises `CatalogVersionMismatchError` with both versions in the message.
- Loading the same save file with `force=True` succeeds (catalog at `1.1.0` is used despite the recorded `1.0.0`).
