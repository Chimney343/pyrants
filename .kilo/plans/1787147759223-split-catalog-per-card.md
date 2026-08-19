# Plan: Split catalog.json into one JSON per card

## Goal

Replace the single 434 KB `data/cards/catalog.json` (125 cards, #1 churn hotspot) with **one JSON file per card placed directly in `data/cards/`** — no subdirectory. `catalog.json` is **deleted**; every consumer assembles the catalog from the per-card files at runtime (decided with user).

Key decisions (confirmed with user):
- **catalog.json is removed entirely** — no generated combined artifact, checked in or otherwise.
- **Per-card files live flat in `data/cards/`** next to `manifest.json` and the existing `cards_OCR.json` (not in a `cards/` subdirectory).
- **C tests** obtain the catalog via a **platform-specific directory reader in test code** (`#ifdef _WIN32` `FindFirstFileA` / POSIX `dirent`) — *not* in library sources, respecting the AGENTS.md purity rule for `engine_c/` library code.
- Production bindings assemble catalog JSON in Python and pass it to a new string-based C entry point.
- **Hard requirement (user-mandated): whole-catalog assembly for the C engine is covered by dedicated tests at both layers** — a new C test executable (`engine_c/tests/test_catalog_assembly.c`) validating the directory reader + `engine_load_definition_json` load of every card, and a new pytest (`tests/c_engine/test_catalog_assembly.py`) validating the production Python-assembly → C-engine path. Not optional, not incidental coverage.

## Target layout

```
data/cards/
  manifest.json              # NEW — {"catalog_id": "base_catalog"}
  aboleth.json               # NEW — exact card object from the old cards[] array
  advance_scout.json
  ... (125 per-card files, filename = <card_id>.json)
  cards_OCR.json             # unchanged (OCR source artifact — top-level array, not engine data)
```

- Per-card file = the verbatim card object (`card_id`, `name`, `cost`, ..., `effect_payload`).
- Serialization style matches the old file exactly: `json.dumps(..., indent=2)` + trailing newline, LF (no `.gitattributes`; git index is LF today).
- **Card-file discrimination rule** (used identically by the Python assembler and the C test reader): among `*.json` in the directory, a card is a JSON **object containing a `card_id` string key**. Everything else is skipped — `manifest.json` (has `catalog_id`, no `card_id`), `cards_OCR.json` (top-level array), and the legacy `catalog.json` during transition (has `catalog_id`/`cards`, no `card_id`). No hardcoded filename lists.
- **Directory detection**: a directory passed as a card path is a card dir iff it contains `manifest.json` with a `catalog_id`; otherwise raise a clear `ValueError` (so e.g. `data/decks` fails loudly, not silently empty).
- Card order = sorted filenames = sorted `card_id` (old catalog is already alphabetical; enforced by the round-trip gate below).
- The "card path" concept is **dir-or-file**: `data/cards` (dir, primary) or a legacy single catalog file (keeps external/temp single-file catalogs working, e.g. `tests/test_run_ismcts_replay_payload.py`'s `/tmp/catalog.json` mocks).

## Why the C changes look like this

- `engine_c/loader.c:430` `engine_load_definition(catalog_path, ...)` `fopen()`s the single file; `parse_catalog()` already takes a JSON **string** (`loader.c:311`).
- `engine_c/saveload.c:141` `engine_deserialize_state()` re-loads the catalog **by path** embedded in save JSON (`definition.catalog_path`, `saveload.c:73`, resolution at `saveload.c:187-193`), with an alt-path fallback. ~345 scenario files under `data/scenarios/**` embed `"catalog_path": "data/cards/catalog.json"`.
- Portable directory iteration is impossible in C11/MSVC without platform-specific code, which AGENTS.md forbids in library sources → C library gets **JSON-in-memory entry points**; only *test* sources get a directory reader.

## Implementation steps

Sequenced so the tree stays green at every commit (one PR, `[engine-c]` + `[data]`-style focused commits):

### 1. Python assembler (game_setup/loaders.py)

- Add `DEFAULT_CARDS_DIR = <repo>/data/cards`.
- Add `assemble_catalog_payload(cards_path: Path) -> dict[str, Any]`:
  - If `cards_path` is a **dir**: require `manifest.json` with `catalog_id`; scan `*.json` sorted, keep objects with a `card_id` key; return `{"catalog_id": ..., "cards": [...]}`.
  - If it's a **file**: current behavior (`_read_json`) — legacy/external single-file catalogs.
- Add `assemble_catalog_text(cards_path: Path) -> str` (json.dumps of the payload; `@lru_cache` on resolved path) for the C bindings.
- Rework `load_card_catalog(path)` and `build_game_definition_from_files(card_path=...)` on top of the assembler. Keep kwarg name `card_path`/`catalog_path` everywhere (value becomes dir-or-file) to minimize caller churn; update docstrings.
- `build_catalog_registry` / `default_catalog_registry` (exported via `game_setup/__init__.py`, no in-repo callers): `default_catalog_registry()` detects `manifest.json` in `data/cards` and returns `{catalog_id: assembled_catalog}`; scanning logic treats a manifest-bearing dir as one catalog instead of testing each `*.json` as a standalone `CardCatalog` (which would now hit 125 card files + OCR array). Minimal coherent rework — no removal.
- Unit tests: assembler on `data/cards` returns 125 unique ids and validates as `CardCatalog`; skips `cards_OCR.json`/`manifest.json`; assembler accepts a legacy single-file catalog written to `tmp_path`; clear error when given a dir without `manifest.json`.

### 2. C engine: string-based catalog entry points

- `engine_c/loader.{c,h}`: add `GameDefinition *engine_load_definition_json(const char *catalog_json, const char *board_path, const char *setup_path, Arena *arena)` — same as `engine_load_definition` but calls `parse_catalog(catalog_json, ...)` directly (buffer is caller-owned; parse interns into the arena, mirroring `engine_apply_setup_json` ownership).
- `engine_c/saveload.{c,h}`: change `engine_deserialize_state(json, catalog_path_override, arena, out)` second param to `catalog_json` (the assembled catalog JSON string, required non-NULL from bindings/tests). Drop the path resolution + alt-path fallback at `saveload.c:187-193`; build the definition from injected catalog JSON + board/setup paths from the save (those files remain single-file). The embedded `definition.catalog_path` stays in the save format as **informational metadata only**.
- `engine_serialize_state`: signature unchanged — it just writes the string it's given; callers now pass `"data/cards"` as the metadata value.
- Remove the now-unused `engine_load_definition` export (no remaining callers after steps 3-4); update `engine_c.def`. Risk: any hypothetical external DLL consumer breaks — accepted for this research repo.
- Rebuild: `just build-c` must compile clean (`/W3 /std:c11`).

### 3. C test directory reader + test migration

- New header-only helper `engine_c/tests/catalog_dir.h` (header-only = zero compile.bat/Makefile wiring changes):
  - `static char *test_load_catalog_json(const char *cards_dir)` → malloc'd `{"catalog_id": ..., "cards": [...]}`.
  - Enumerates `*.json` (Win32 `FindFirstFileA` under `#ifdef _WIN32`, else `opendir`/`readdir`), `qsort`s filenames (determinism: readdir order is arbitrary), reads each with `fopen`, cJSON-parses (cJSON already linked via libengine), keeps objects with a `card_id` key, skips others (manifest/OCR/legacy), reads `catalog_id` from `manifest.json`, joins bodies with commas.
  - Pure test-side code: platform-specific calls allowed here, not in library sources.
- Include from both `engine_c/` root and `engine_c/tests/` exes (compile.bat already uses `/I.`); add include to the GCC `Makefile` test targets if needed.
- Migrate the 8 catalog-loading C test files + `profile_runner.c` (`test_engine.c`, `test_generic.c`, `test_game.c`, `test_death_tyrant.c`, `test_dt_ched.c`, `tests/test_view.c`, `tests/test_describe.c`, `tests/test_saveload.c`; verified: `tests/test_generic_actions.c` builds synthetic actions and never loads the catalog — no change expected, confirm during implementation): replace each `engine_load_definition("../data/cards/catalog.json", ...)` / `"data/cards/catalog.json"` try-both pattern with `test_load_catalog_json("../data/cards")` → fallback `"data/cards"`, then `engine_load_definition_json(...)`. `engine_deserialize_state(json, NULL, ...)` calls pass the re-assembled catalog JSON.

### 3b. HARD REQUIREMENT — C test for whole-catalog assembly (`engine_c/tests/test_catalog_assembly.c`, new file)

The directory reader and the JSON-based load path must be validated by a dedicated C test that assembles the **entire** catalog and loads it into the engine — not just trusted because other tests happen to consume it:

1. **Assembly**: `test_load_catalog_json("../data/cards")` (fallback `"data/cards"`) returns non-NULL.
2. **Assembled-JSON contents** (cJSON-parse the string): `catalog_id == "base_catalog"`; `cards` is an array of exactly **125** objects (pin the count as a tripwire — update the constant when cards are added); every element has a non-empty string `card_id`; all ids unique and in sorted order (adjacent comparison — filenames sort as card_ids).
3. **Truncation spot-checks**: first card `aboleth` (name "Aboleth", cost 7, aspect "guile") and last card `zuggtmoy` present — catches off-by-one/partial directory reads.
4. **Engine load**: `engine_load_definition_json(assembled, board_path, setup_path, arena)` returns non-NULL; `def->catalog.card_count == 125`; **every** `def->catalog.cards[i].card_id != SYM_NULL` (all cards interned); engine-resolved `aboleth` definition matches the JSON (name, cost).
5. **Negative**: `test_load_catalog_json("data/decks")` fails (no `manifest.json`) — directory detection rule enforced; also verifies non-card JSON (deck rosters are objects without `card_id`) is never picked up.

**Build wiring** (without this the test doesn't run — it is part of the requirement):
- `engine_c/compile.bat`: build + run `test_catalog_assembly.exe` alongside the other test exes; add its `.obj` to the `del` cleanup line before the DLL link.
- `justfile` `test-c` recipe: add `& .\engine_c\test_catalog_assembly.exe`.
- GCC `Makefile` `test` target: add the same test.

### 4. Python bindings migration

- `engine_c/bindings/engine_bindings.py`: add/adjust ctypes prototypes (`engine_load_definition_json`; `engine_deserialize_state` param semantics — type stays `c_char_p`).
- `engine_c/bindings/ce_api.py`: `CEngine.initialize(catalog_path=...)` default → `data/cards`; assemble text via `game_setup.loaders.assemble_catalog_text`; call `engine_load_definition_json`; keep `self._catalog_json` (replace/augment `self._catalog_path`) for deserialize. Import direction is fine: bindings already import `game_setup` (`scenario_search.py`).
- `engine_c/bindings/session.py`: `save_to_string(catalog_path="data/cards")` default (metadata written into new saves); `save()` uses `self._engine._catalog_json`; `load()` calls the new `engine_deserialize_state(json, catalog_json, ...)` — old scenario files keep working because the embedded path is ignored.
- `engine_c/bindings/view.py:137` `_load_catalog()` and `engine_c/bindings/label_enrich.py:54`: assemble from `data/cards` via the assembler (keep `lru_cache`).
- `engine_c/bindings/scenario_search.py:260`: `cp` default → `"data/cards"`.
- **HARD REQUIREMENT — pytest for the production whole-catalog path** (`tests/c_engine/test_catalog_assembly.py`, new file, runs via `just test-c-python`):
  1. `assemble_catalog_payload(data/cards)` → `CardCatalog.model_validate` passes; 125 unique ids; `catalog_id == "base_catalog"`; `assemble_catalog_text(...)` == `json.dumps(payload, indent=2) + "\n"` (byte-identical formatting contract).
  2. ctypes-level: `engine_load_definition_json(assembled_text, board_path, setup_path, arena)` returns a valid definition — the entire assembled catalog loads into the C engine through the exact production path.
  3. `CEngine()` default `initialize()` (no args → `data/cards`) + `create_game(["p1", "p2"])` smoke — proves the default path assembles and loads end-to-end.
  4. Old-save compatibility as a permanent test: `CSession.load` one pre-existing scenario from `data/scenarios/cards/` (legacy embedded `"catalog_path": "data/cards/catalog.json"` is ignored) — locks in backward compat instead of a one-off manual check.

### 5. Python consumers migration (mechanical path updates)

- `game_setup/scenario_generation/rosters.py:28` `DEFAULT_CARD_PATH` → `data/cards` (exported via `game_setup/__init__.py`).
- `interface/game_viewer.py:42` `DEFAULT_CARD_PATH`; `--card-path` default. **Code change required at `game_viewer.py:1065-1074`**: `self.card_path.parent / ".." / "boards"` breaks when `card_path` is `data/cards` (`.parent` is `data` → `data/../boards`). Replace both derivations with the existing `DATA_DIR` constant (line 39).
- `openspiel_pyrants/game_c.py:17` `_DEFAULT_CARDS` → `data/cards` (dir).
- Scripts: `scripts/catalog_audit.py:12`, `scripts/generate_catalog_execution_audit.py`, `scripts/generate_card_scenarios.py`, `scripts/run_ismcts.py:494`, `scripts/diagnose*.py`, `scripts/find_lich.py`, `scripts/find_sym512.py`, `scripts/enrich_catalog.py` (input side).
- Tests: `tests/test_card_neogi.py`, `test_card_mercenary_squad.py`, `test_card_conjurer.py` (replace raw `json.loads(CATALOG_PATH)` with `assemble_catalog_payload`), `test_deck_rosters.py`, `test_game_viewer.py`, `test_game_renderer.py`, `test_scenario_search_conditions.py`; re-grep `tests/c_engine/` for defaults.
- Root throwaways (`_review_script*.py`, `.kilo/tmp_card_audit.py`): leave as-is (broken if run) — out of scope.
- justfile: `card="data/cards/catalog.json"` defaults in `build-game` and `game-viewer` → `card="data/cards"`.

### 6. One-off split script + data migration

`scripts/split_catalog.py` (kept in repo for provenance):
1. Read `data/cards/catalog.json`; assert: 125 cards, unique ids, ids sorted, top-level keys exactly `{catalog_id, cards}`.
2. Write `data/cards/manifest.json` and the 125 per-card files **directly into `data/cards/`** (formatting per "Target layout"; coexists temporarily with `catalog.json` and `cards_OCR.json`).
3. **Round-trip gate**: reassemble the payload from the new files (applying the card_id discrimination rule) and assert `json.dumps(payload, indent=2) + "\n"` is byte-identical to the original file after CRLF→LF normalization (else abort — flags formatting/ordering drift; keep `ensure_ascii` matching the original bytes since OCR-enriched flavor text may be non-ASCII).
4. Rewrite embedded references: targeted **text** replacement `"data/cards/catalog.json"` → `"data/cards"` inside `data/scenarios/**/*.json` (~345 files; preserves formatting — do not json round-trip them).
5. `git rm data/cards/catalog.json` (perform the delete only after step 5's suite is green against the new dir — see ordering note below).

### 7. Docs

- `AGENTS.md` (data dir table, hotspots note, directory map), `.kilo/skills/card-execution-validator/SKILL.md` + `references/catalog_and_engine_map.md` (rg recipes → `data/cards/*.json` per-card files), `docs/` status docs mentioning `catalog.json`, `engine_c/bindings/view.py` module docstring.

### Ordering note (keeps every commit green)

Run the split script's *write* phase (manifest + 125 files into `data/cards/`) **first**, keep `catalog.json` in place, migrate all code with dir-or-file defaults pointing at `data/cards` (the assembler's card_id rule ignores the coexisting `catalog.json` during transition), validate. Then delete `catalog.json` + migrate scenario paths + re-validate. Final sweep: `rtk rg "catalog\.json"` must return only intentional hits (plans, artifacts, throwaways, `cards_OCR` history).

## Validation plan

- `ruff check .`
- `just test` (full pytest)
- `just build-c` (compiles + runs all C tests **including the new `test_catalog_assembly`** with the new dir reader)
- `just test-c` — verify `test_catalog_assembly.exe` is in the run list and green
- `just test-c-python` — includes `tests/c_engine/test_catalog_assembly.py`; `just openspiel-test`
- `just ismcts-quick` (exercises CEngine init + workers with assembled catalog)
- `just game-viewer` manual smoke.
- Split script's round-trip gate + `CardCatalog.model_validate` on assembled payload.

## Risks / failure modes

- **Formatting/ordering drift** in per-card files → caught by the round-trip gate before deletion.
- **Directory-reader determinism**: unsorted `readdir`/`FindFirstFile` order → qsort filenames in C, `sorted(glob)` in Python; enforced byte-exact by the round-trip gate.
- **Stray non-card JSON dropped into `data/cards/`** would be silently included if it has a `card_id` — acceptable (that's the file's meaning); objects without `card_id` are skipped.
- **C API break** (`engine_load_definition` removed, `engine_deserialize_state` param re-purposed): all in-repo callers updated in the same PR; external DLL consumers (if any exist) break — accepted.
- **Old saves**: only loadable through the JSON-injecting path; the legacy path-based branch is gone. Scenario files under `data/scenarios/` are migrated textually, and the bindings ignore the embedded path anyway.
- **Pinned card count (125) in the assembly tests**: intentional tripwire — silently losing/duplicating a per-card file fails the suite; the cost is updating one constant when cards are added (matches the repo's stable 125-card roster; the split script and existing 125-scenario corpus pin the same number).
- **Threading**: `assemble_catalog_text` cached per process; `run_ismcts` worker processes each assemble once (~127 small reads) — negligible.

## Out of scope

- Catalog `version` fingerprinting for saves (see existing plan `.kilo/plans/catalog-save-deduplication.md`; `manifest.json` is the natural future home for it).
- `cards_OCR.json` cleanup, root `_review_script*.py` throwaways.
- Python-side `engine/` remnants (already removed from repo).
