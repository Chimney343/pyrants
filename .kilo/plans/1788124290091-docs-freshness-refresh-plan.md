# /docs Freshness Refresh Plan

## Context

A review of `docs/` (2026-08-30) verified every doc against the tree, catalog data, engine sources, tests, and justfile. The three "status" files and the two dated snapshots are broadly current, but several docs reference removed files or contradict each other. This plan covers **docs-only edits** — no engine, catalog, or test changes.

## Findings inventory (verified)

**Broken references:**
- `docs/game_manual.md` — cited (with line numbers) by `Tyrants of the Underdark Final Scoring Verification Checklist.md`; file gone from repo.
- `data/boards/base_game.json` — cited by `board-creator-status.md`; only `data/boards/tyrants_of_the_underdark.json` exists.
- `scripts/generate_first_deck_artifacts.py` — cited by `cards-status.md`; script gone.
- `data/cards/catalog.json` — cited in `docs/generated/catalog_execution_audit.md` header; replaced by per-card files + `manifest.json`.

**Stale artifacts:**
- `docs/generated/engine_action_gap_report.md` — references the removed Python `engine/` package; its 2/43/68 coverage split predates the C engine; no generator script exists anymore; contradicts the current audit (125/125 clean).
- `docs/generated/catalog_execution_audit.md` — regenerable via `scripts/generate_catalog_execution_audit.py` (which now reads the `data/cards` dir), but was generated pre-split; header shows the old catalog.json path.

**Superseded / resolved docs:**
- `ismcts-generic-resolution-bugs.md` (2026-08-28) — both bugs fixed: demon one at `engine_c/generic_runtime.c:761` (closes the pending resolution instead of destroy-and-NULL), demon two via play-time gating `card_play_modal_options_viable()` (`generic_runtime.c:1244`, called from `rules.c:243` and `rules.c:302`, tested in `engine_c/tests/test_generic_actions.c:472-481`). Doc still reads "not fixed yet."
- `Tyrants of the Underdark OpenSpiel Integration Checklist (IS-MCTS Support).md` — all-unchecked aspirational checklist; every item is implemented and tested (see `openspiel_integration.md`, `openspiel_pyrants/tests/`).
- `openspiel-architecture.md` Action Encoding section — describes the old Python-wrapper sort (`model_dump_json`, exclude `player_id`); the actual C path (`openspiel_pyrants/action_encoding_c.py`) uses native engine order, no sort, and filters `unavailable` placeholder moves. `openspiel_integration.md` has the correct description.

**Contradiction:**
- `engine-status.md` line 27 ("The current test suite is green") vs `cards-failing-tests.md` (2026-08-29: 3 failed). Verified still live today: `tests/test_card_neogi.py:29` asserts `timing == "immediate"` while `data/cards/neogi.json` has `end_of_turn`.
- `cards-failing-tests.md` says `tests/test_game_viewer.py` was "removed (commit pending)" — the file now exists as a rewritten Tk-free suite; the note and the 821-passed count are superseded.

**Organizational smell:**
- `docs/archive/board_creator_copy_replacements.md` is the live inventory for a *pending* UX-copy sweep referenced by `board-creator-status.md`, but lives in the history folder.

## Tasks (docs-only, in order)

1. **Retire the gap report.** Move `docs/generated/engine_action_gap_report.md` to `docs/archive/` with a one-line banner ("pre-C-engine analysis; superseded by catalog_execution_audit.md"). Update the two references to it in `engine-status.md` (line 18) and `cards-status.md` (lines 15, 34) to point to `docs/generated/catalog_execution_audit.md` instead. *(Open question below if a C-engine gap view is wanted instead.)*
2. **Regenerate the audit.** Run `.venv/Scripts/python.exe scripts/generate_catalog_execution_audit.py` to refresh `docs/generated/catalog_execution_audit.md` with the post-split `data/cards` source path and current catalog state. Requires the C DLL present only if re-probing; the script reads `artifacts/card_stuck_report.json` if it exists and otherwise proceeds without probe data.
3. **Fix broken references.**
   - `board-creator-status.md`: `data/boards/base_game.json` → `data/boards/tyrants_of_the_underdark.json`.
   - `cards-status.md`: drop `scripts/generate_first_deck_artifacts.py` from the pipeline list; reword the pipeline description to the surviving scripts (`generate_catalog_execution_audit.py`, `catalog_audit.py`, `split_catalog.py` as history).
   - Final Scoring Checklist: re-anchor the two `docs/game_manual.md` citations (lines ~2, 12) — restate the divergences citing `data/boards/tyrants_of_the_underdark.json` fields and `engine_c/scoring.c` behavior instead of `game_manual.md` line numbers. Do not restore the deleted manual.
4. **Resolve the green-vs-failures contradiction.** In `engine-status.md`, replace "The current test suite is green…" with a dated pointer: "See `docs/cards-failing-tests.md` for the latest dated test snapshot." Keep the 3 failing cards themselves out of scope (separate engine/catalog work).
5. **Mark the grug bug-hunt resolved.** Add a short resolution note at the top of `ismcts-generic-resolution-bugs.md` (demon one fixed at `generic_runtime.c:761`; demon two fixed via play-gating `card_play_modal_options_viable` — prevented at play time, not fizzled; tests in `test_generic_actions.c`), then move the file to `docs/archive/`.
6. **Archive the superseded OpenSpiel checklist.** Move `Tyrants of the Underdark OpenSpiel Integration Checklist (IS-MCTS Support).md` to `docs/archive/` (all items implemented and tested; `openspiel_integration.md` is the live doc).
7. **Fix `openspiel-architecture.md`.** Rewrite the Action Encoding section to describe the actual C path: native engine order, no sort, `unavailable` placeholder filtering, 1024 as static bound. Cross-check the "Shuffle Determinism" section against `engine_c` seeding and tighten if still vague.
8. **Update `cards-failing-tests.md` postscript.** Correct the `test_game_viewer.py` account: the suite was replaced by a Tk-free rewrite (not removed); drop the "commit pending" note. Optionally add an "as-of" date line to all three status files so future drift is detectable.
9. **Relocate the live copy-sweep inventory.** Move `docs/archive/board_creator_copy_replacements.md` → `docs/source/` and update the `board-creator-status.md` pointer (it is a pending-sweep input, not history).
10. **Low priority:** refresh `repo_structure.md` entry-points table with the newer justfile tasks (`build-game`, `bench-rollout`, `ismcts-perf`, `card-complexity`, `review-workbook`, `generate-card-scenario*`).

## Out of scope

- Fixing the 3 failing cards (zuggtmoy EOT self-promote, air_elemental option_1 focus draw, neogi force_discard timing) — engine/catalog work, separate task.
- Restoring `docs/game_manual.md` from git history.
- AGENTS.md drift (mentions the removed `engine/`, `data/cards/catalog.json` hotspot, "Game manual") — flagged to the user separately.
- Writing a new C-engine action-gap generator.

## Validation

- `grep` repo-wide for the removed references after edits: `game_manual`, `base_game.json`, `generate_first_deck_artifacts`, `catalog.json` within `docs/` — expect zero live hits (archived copies may retain historical mentions).
- Re-read `docs/README.md` against the new `docs/` layout; update the index if files moved.
- Docs-only change: `just test` and `ruff check .` should be unaffected; run `ruff check .` anyway since one script (`generate_catalog_execution_audit.py`) is executed in task 2.

## Open questions

1. Gap report: retire (recommended, per task 1) or regenerate against the C engine's op coverage (requires writing a new generator)?
2. Should the status files adopt a formal "as-of" date header (recommended, cheap) or stay undated prose?
