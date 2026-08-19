# Remove the legacy Python engine (`engine/`) — keep only the C engine (`engine_c/`)

## Goal

Sever every import and reference of the deprecated Python engine package `engine/` from active code, then delete `engine/` and its legacy-only consumers entirely. The C engine at `engine_c/` (via `engine_c/bindings/`) becomes the only engine. No legacy tools are ported — the owner will rebuild what is needed later.

Already confirmed with user:
- **End state:** `engine/` is deleted (git history is the reference).
- **Tool migration:** none. Legacy-only tools are deleted, not ported.

## Current coupling (verified)

- **Root controllers (legacy-only):** `game_session.py` (`GameSession`), `game_view.py` (`build_game_view`), `game_simulation.py`.
- **`interface/`:** `game_viewer.py` is dual-backend (`--engine c|python`, env `PYRANTS_ENGINE` defaults `"python"`; C mode = `CSession` + `build_c_game_view`, but still imports `engine.moves` slot constants, `engine.scoring` helpers, `engine.state` types). Legacy-only: `cli.py`, `parser.py`, `display.py`, `replay_viewer.py`. Renderers/board files (`board_renderer.py`, `board_view.py`, `game_renderer.py`, `shared_board_renderer.py`, `board_creator.py`) only need `NodeKind`.
- **`game_setup/`:** `loaders.py`, `board_package.py` import Pydantic definition models + `NodeKind` from `engine.state`; `scenarios.py` (scenario save/load on legacy `GameState` payloads), `random_state_search.py`, `scenario_generation/card_scenarios.py` are legacy engine code; `state_generator.py` is a re-export shim. **The C scenario search (`engine_c/bindings/scenario_search.py`) imports data helpers (`StopConditions`, `_resolve_two_deck_pairing`, `iter_roster_card_ids`) from the legacy `card_scenarios.py`** — transitive legacy coupling.
- **`openspiel_pyrants/`:** legacy backend (`game.py`, `state.py`, `observer.py`, `action_encoding.py`, `determinization.py`, registered as `python_pyrants`) alongside C twins (`*_c.py`, `python_pyrants_c`). `__init__.py` registers both. `scripts/run_ismcts.py` defaults to the legacy game; `scripts/_replay_payload.py` has a lazy `engine.scoring` fallback.
- **Scripts (legacy-only):** `random_walk.py`, `bench_simulation.py`, `regenerate_canonical_scenarios.py`, `check_roster_card_stuck_states.py`; `generate_card_scenarios.py` has a `--engine python` mode + legacy imports.
- **Tests:** `tests/legacy_engine/` (28 files incl. `test_engine_purity.py`, which only guards `engine/`), `tests/scenario_helpers.py`, `tests/test_game_simulation.py`, `tests/test_game_renderer.py` (legacy session/view based), `openspiel_pyrants/tests/` partly legacy (`test_resample.py` uses `engine.player_view`), and `tests/c_engine/test_engine_c.py` (mixed: cross-validation oracle tests import `engine.*`; pure-C tests use only `CSession`).
- **Key non-coupling facts:** `engine_c/bindings/` has no direct `engine/` imports; C engine serializes/deserializes scenario JSON directly (`CSession.save/load`, `save_c_scenario`) and already loads all `data/scenarios/**` files (proven by `tests/c_engine` tests). Top-level `tests/test_card_{neogi,mercenary_squad,conjurer}.py` are already C-only and survive unchanged.

## Design decisions

1. **Neutral shared types move to `game_setup`** (the surviving data layer):
   - New `game_setup/types.py`: `NodeKind` and the engine-agnostic Pydantic models (`BoardDefinition`, `SetupDefinition`, `CardCatalog`, `GameDefinition`) moved out of `engine/state.py`.
   - Recruit-slot constants (`HOUSE_GUARD_RECRUIT_SLOT`, `PRIESTESS_RECRUIT_SLOT`, `INSANE_OUTCAST_RECRUIT_SLOT`) move to `game_setup/market_setup.py` (single source — alias `SPECIAL_RECRUIT_IDS` if values coincide; do not duplicate literals).
   - Shared scenario/roster helpers (`StopConditions`, `_resolve_two_deck_pairing`, `iter_roster_card_ids`, `write_forced_injection_notes`) move to a new legacy-free `game_setup/scenario_generation/rosters.py`.
   - During phases 1–4, `engine/state.py` and `engine/moves.py` re-export from the new homes so the repo stays green; the re-exports die in phase 5.
2. **Viewer becomes C-only:** remove `--engine` flag and `PYRANTS_ENGINE`; `CSession` everywhere; scenario save/load via `CSession.save` / `CSession.load`. Any `engine.scoring` helper still needed on the C path (`_cards_vp`, `_is_total_control`, `_site_control_owner`) is re-implemented minimally against `CGameView`/C structs (the VP breakdown already reads C structs directly).
3. **OpenSpiel:** delete the legacy backend; register only `PyrantsCGame` as `python_pyrants_c` (keep the short name — scripts/justfile already use it); `run_ismcts.py` defaults to `--game python_pyrants_c`; `_replay_payload.py` drops the Python fallback branch.
4. **No data migration:** `data/scenarios/**` stay as-is (C deserializer reads them today); new saves use the C serializer.
5. **Oracle tests are deleted, not ported** (accepted loss of the C-vs-Python conformance net per user decision). Pure-C tests inside `test_engine_c.py` are kept.

## Implementation phases

Each phase is one focused PR, green after merge: `ruff check .` + `just test` (plus `just build-c`/`just test-c-python` when touching `engine_c` or bindings, `just openspiel-test` for phase 3).

### Phase 1 — Extract engine-agnostic types into `game_setup`
1. Create `game_setup/types.py` with `NodeKind` + definition models moved from `engine/state.py`; `engine/state.py` re-exports them (temporary).
2. Move recruit-slot constants to `game_setup/market_setup.py`; `engine/moves.py` re-exports (temporary).
3. Create `game_setup/scenario_generation/rosters.py` with the shared helpers currently imported from `card_scenarios.py`; make `card_scenarios.py` import them from there; repoint `engine_c/bindings/scenario_search.py` and `scripts/generate_card_scenarios.py` (C path) at the new module.
4. Repoint `game_setup/loaders.py`, `game_setup/board_package.py`, and the six `interface/` renderer/board modules at `game_setup/types.py`.
5. In `loaders.py`, keep `create_game_state_from_files`/legacy-state builders importing `engine` only where unavoidable (they die in phase 5); everything else uses neutral models.

### Phase 2 — Interface layer C-only
1. `interface/game_viewer.py`: remove `--engine`, `PYRANTS_ENGINE`, `GameSession`, `from_scenario_file`, `save_game_state` usage → `CSession.from_files` / `CSession.load` / `CSession.save`; drop `engine.*` imports; re-home/re-implement the scoring helpers per decision 2.
2. Delete `interface/cli.py`, `parser.py`, `display.py`, `replay_viewer.py`.
3. Port `tests/test_game_renderer.py` onto `CSession` + `build_c_game_view` (renderer itself is active UI code; keep its coverage).
4. Update `interface/_session_protocol.py` docstring (C-only) or delete it if nothing else uses it.

### Phase 3 — Root controllers + OpenSpiel
1. Delete `game_session.py`, `game_view.py`, `game_simulation.py`, `tests/test_game_simulation.py`.
2. `openspiel_pyrants/`: delete `game.py`, `state.py`, `observer.py`, `action_encoding.py`, `determinization.py`; `__init__.py` registers only the C game; port/trim `openspiel_pyrants/tests/` to the C backend (delete `test_resample.py` or port to `deterimization_c.py`; make `test_action_encoding.py` use `action_encoding_c`/`PyrantsCGame`).
3. `scripts/run_ismcts.py`: default `--game python_pyrants_c`. `scripts/_replay_payload.py`: remove the `engine.scoring` fallback branch; adjust `tests/test_run_ismcts_replay_payload.py` accordingly.

### Phase 4 — Scripts + justfile
1. Delete `scripts/random_walk.py`, `scripts/bench_simulation.py`, `scripts/regenerate_canonical_scenarios.py`, `scripts/check_roster_card_stuck_states.py`, `tests/test_check_roster_card_stuck_states.py`, root `_check_wraith.py`.
2. `scripts/generate_card_scenarios.py`: drop `--engine python` mode and legacy imports (`game_setup.state_generator` shim, `save_game_state`, legacy `ensure_card_scenario`/`generate_card_scenarios`); C path imports only `engine_c.bindings.scenario_search` + `game_setup/scenario_generation/rosters.py`.
3. Justfile: remove `game-viewer-py`, `replay-viewer(-help)`, `game-simulate(-help)` (or repoint `game-simulate` at the C `run_c_simulation` to keep the entry-point name), `card-stuck-check(-ci)`, `random-walk(-run)`, `regenerate-canonical-scenarios`; make `ismcts`/`ismcts-quick`/`ismcts-perf` use `--game python_pyrants_c`.

### Phase 5 — Delete `engine/` + legacy tests + docs
1. Verify zero remaining importers (`rg "^(from engine[\. ]|import engine$)"` → no hits outside `engine/` and `tests/legacy_engine/`), then delete: `engine/`, `tests/legacy_engine/`, `tests/scenario_helpers.py`, `game_setup/scenarios.py`, `game_setup/random_state_search.py`, `game_setup/scenario_generation/card_scenarios.py`, `game_setup/state_generator.py`.
2. `tests/c_engine/test_engine_c.py`: delete the cross-validation tests that import `engine.*`; keep pure-C tests (`test_quaggoth_*`, `test_marilith_*`, etc.).
3. Update `AGENTS.md`: directory map, entry points, testing, debugging sections — remove legacy-engine references, `game-viewer-py`, `game-simulate`, `replay-viewer`, `card-stuck-check`, IS-MCTS Python-backend wording, and reword the engine-purity paragraph (C engine purity is inherent; `tests/test_engine_purity.py` no longer exists). Update `docs/` status docs that reference the Python engine.
4. Final gates:
   - `rg "from engine\.|import engine\b"` over `*.py` → zero hits.
   - `rg "game-viewer-py|game-simulate|replay-viewer|card-stuck-check|random-walk|regenerate-canonical" justfile AGENTS.md docs/` → only intentional mentions.
   - `ruff check .`, `just test`, `just build-c`, `just test-c-python`, `just openspiel-test` all green.

## Risks / notes

- **Viewer surgery:** `game_viewer.py` is ~2600 lines; make surgical edits (flag removal, session swap, import re-homing), no behavior redesign.
- **Conformance net lost:** deleting the oracle tests means future C-engine rule changes have no Python reference — accepted by user.
- **`test-c-python` dependency chain:** it runs `generate-test-card-scenarios` first; after phase 4 the generation is C-only — verify the target still populates `data/scenarios/test_card_generation/` identically enough for the suite.
- **Slot-constant duplication:** ensure a single source of truth for recruit-slot ints (alias, don't copy) or the viewer's special-slot mapping can silently drift.
- **Do not touch** `engine_c/` C sources, `data/` content, or the deprecated-port warnings until the final docs pass; keep engine/UI/script changes in separate PRs per repo guidelines.
