# Plan: Rewrite `just generate-card-scenarios` to use the C engine

## Goal

Make `just generate-card-scenarios` (and the underlying `scripts/generate_card_scenarios.py` entry point it invokes) run its reachable-search and save pipeline on the C engine in `engine_c/`, with **100% the same functional output** as today: same scenario file shape, same filename pattern, same `forced_injections.json`, same `runtime.txt`, same CLI flags, same progress / logging.

## Current behaviour (what we must preserve)

Invoked from `justfile:41-42`:

```just
generate-card-scenarios workers="1" seed="4" attempts="30" steps="3000":
    $sw = [System.Diagnostics.Stopwatch]::StartNew(); $outDir = "data/scenarios/batch_card_generation";
    & {{python}} scripts/generate_card_scenarios.py --output-dir $outDir --base-seed {{seed}} \
        --max-attempts {{attempts}} --max-steps {{steps}} --workers {{workers}};
    ...
    Set-Content -Path (Join-Path $outDir "runtime.txt") -Value "Runtime: ${elapsed}s"
```

`scripts/generate_card_scenarios.py` delegates to `game_setup.scenario_generation.card_scenarios`:

- For each card id (from `iter_roster_card_ids(rosters_path)`):
  1. `ensure_card_scenario(card_id, ...)`:
     - `_resolve_two_deck_pairing(rosters_path, target_card_id, base_seed)` → `(roster_a_id, roster_b_id, special_stacks)`
     - `_build_card_scenario_setup(..., roster_a_id, roster_b_id)` builds a `GameState` whose `SetupDefinition.market_deck` is the combined two-deck market.
     - `_search_card_scenario(...)` runs up to `max_attempts` random walks (`max_steps_per_attempt` each) and detects a "playable now" moment via `_classify_moves` (Recruit=8, PlayCard=4, else=1 weights).
     - If reachable: returns the playable state.
     - If exhausted: returns the last fallback state; `_force_inject_card_into_current_hand` mutates one of the current players' hands (round-robin by `cycle`, random `hand_index`) and returns an `injection_note`.
  2. `save_game_state(state, output_dir / f"{padded_index:03d}_seed_{base_seed}_{card_id}.json", scenario_id=f"card_{card_id}", description=..., tags=[...], card_under_test=card_id, market_deck_ids=[roster_a_id, roster_b_id], special_stacks_present=special_stacks, pretty=...)`.
- After all cards:
  - `write_forced_injection_notes(output_dir, forced_injections)` writes `forced_injections.json` (sorted by `card_id` in the parallel branch).
  - stdout: `Saved: N`, `Injected: N`, `Missing: N`, `Notes: ...`, optionally `Missing cards: ...`.
  - Non-zero exit if any card is missing.

CLI flags we must keep: `--output-dir`, `--board-path`, `--card-path`, `--setup-path`, `--rosters-path`, `--players`, `--base-seed`, `--max-attempts`, `--max-steps`, `--card-id`, `--list-ids`, `--quiet`, `--workers`, `--pretty`, `--legacy-market`.

`--legacy-market` keeps the ad-hoc roster-coverage path on the Python engine (no change — out of scope; the rewrite default uses the C engine, legacy stays Python).

## Why the C engine can do this 1:1

`engine_c/bindings/ce_api.py` already exposes every primitive the workflow needs:

- `CEngine.initialize(catalog_path, board_path, setup_path, setup_data_json=...)` — applies a **custom `SetupDefinition` JSON** to the loaded definition, so we can pass the combined two-deck market setup that `combine_two_deck_market_setup(...).to_setup_data()` produces (`engine_c/loader.c:429` `engine_apply_setup_json` is the underlying C call).
- `CEngine.create_game(player_ids, seed)` — builds the initial `CState`.
- `CEngine.legal_moves(state)` — returns `CMoveWrapper` list; we can read `move_type` and `data` to classify Recruit vs PlayCard vs other, and to detect "playable now" (PlayCard whose `card_id == target_card_id` while in current player's hand).
- `CEngine.apply(state, move)` — advances; returns new `CState`. Old state must be `engine.destroy()`-ed (caller must track ownership).
- `CEngine.is_terminal(state)` / `phase` / `current_player_id` / `player_hand(index)` — read-only access used by `_classify_moves`, the playable-now test, the inject step, and the save metadata.
- `CSession.save(path)` (`engine_c/bindings/session.py:137`) already round-trips a `CState` to a scenario JSON identical in shape to what `save_game_state` produces today. We will reuse that writer (or re-call `engine_serialize_state` directly) and then post-process the JSON to set `metadata.scenario_id`, `description`, `tags`, `card_under_test`, `market_deck_ids`, `special_stacks_present`, `move_count`, `is_terminal` — exactly the fields the Python `save_game_state` writes.

The reachable-search algorithm itself is engine-agnostic: build state, list moves, weighted-random pick, apply, repeat. It is the same loop, just with `CEngine.legal_moves`/`CEngine.apply` instead of `engine.rules.legal_moves`/`engine.rules.apply`.

The force-injection step (mutate one card in the current player's hand) is a **direct array write** into the `CState`'s `players[i].hand[hand_index]` (the `CState` wrapper exposes `player_hand(index)`; we'll add a tiny `set_hand_card(index, hand_index, card_id)` helper on the Python side that interns the string and writes the `Sym` field — same way `engine_c/bindings/ce_api.py:_sym_str` reads it back). This preserves the existing semantics exactly (same hand-index RNG, same round-robin `cycle` over `turn_order`).

`_advance_through_setup` becomes: while `state.phase == "setup"`, list `initial_placement` moves and apply the first one; then if `state.phase == "draw"`, list the legal `resolve_end_of_turn`-equivalent (the C engine advances through DRAW automatically when its single legal draw move is taken — we'll detect and apply it the same way the Python engine does via `engine.phases.advance_phase`). Concretely: after initial placements, if `state.phase == "draw"`, look for a `resolve_end_of_turn` move (or the engine's draw-resolution move) and apply it once; the resulting phase is `main`.

## Design

### New module: `engine_c/bindings/scenario_search.py`

A small C-engine-only search module that mirrors the public surface of `game_setup.scenario_generation.card_scenarios` for the parts we need:

- `class CSearchEngine`: wraps a `CEngine`; holds a process-lifetime arena + definition (one definition per process, matching how the Python engine caches via `lru_cache`).
- `CARD_SCENARIO_PICK_WEIGHTS = {"recruit": 8.0, "play_card": 4.0, "other": 1.0}` (module-level constant, identical to `_classify_moves`).
- `ensure_card_scenario_c(card_id, *, board_path, card_path, setup_path, rosters_path, player_ids, base_seed, max_attempts, max_steps_per_attempt, legacy_market=False) -> tuple[CState, dict | None, list[str], list[str]]`
  - Same two-deck pairing via `pick_pair_for_target` + `combine_two_deck_market_setup(...).to_setup_data()` (these are **pure Python over JSON**, not engine code, so we reuse them unchanged).
  - `serialise_setup_data = json.dumps(setup_data)` → `CEngine.initialize(..., setup_data_json=...)` (one engine per process; re-init on first use, reuse after).
  - For each attempt, `state = engine.create_game(player_ids, attempt_seed)`.
  - For each step: list moves; if any `play_card` with `card_id == target_card_id` while the target is in `engine.player_hand(current_player_index)` → return playable state.
  - Otherwise update `fallback_state`, weighted-pick a move, apply.
  - If exhausted: `_force_inject_into_hand(fallback_state, target_card_id, injection_seed)`; return injected state + note.
- `_force_inject_into_hand(state, target_card_id, injection_seed)`:
  - Advance through setup (initial placements + draw) the same way the Python path does.
  - Round-robin `cycle` over `turn_order` (read from `state.player_ids`).
  - For the first player with a non-empty hand, pick `rng.randrange(hand_count)`, build a new `CState` whose hand has the target card swapped in, return `(new_state, note_dict)`.
  - Build the new state via `engine.clone(state)` (`engine_clone` exists in `engine_c/bindings/engine_bindings.py:379`) and write the Sym into the clone's `players[idx].hand[hand_index]`.
- Helpers on `CState` (or thin wrappers in this module):
  - `set_hand_card(state, player_index, hand_index, card_id_sym)` — write to `state._s.players[player_index].hand[hand_index]` using `intern("...")`.
  - `current_player_index(state)` — derived from `state.player_ids.index(state.current_player_id)`.
  - `is_special_recruit(card_id)` — same `SPECIAL_RECRUIT_IDS` frozenset (re-imported from `game_setup.market_setup`).

The output of this module is a `CState` + the same `injection_note` dict shape that the Python version returns, so the CLI side stays untouched.

### Rewrite: `scripts/generate_card_scenarios.py`

The CLI layer stays structurally identical. Two changes:

1. The `ensure_card_scenario` / `generate_card_scenarios` imports switch to the new C-backed functions when the C engine is available (always — we are forcing the C path by default). The legacy `--legacy-market` branch keeps the Python engine call (no behaviour change there).
2. Saving: instead of `save_game_state(pydantic_state, path, ...)`, we use the C engine's `engine_serialize_state` (via `CSession.save`-style helper) to produce the scenario JSON, then read it back, set/overwrite `metadata.{scenario_id, description, tags, card_under_test, market_deck_ids, special_stacks_present, move_count, is_terminal}` to the same values `save_game_state` would set, and re-emit. **Output byte-for-byte identical** to today (modulo the `created_at` timestamp field, which is already non-deterministic in the Python version).

A small helper `scripts/c_scenario_writer.py` (or a function in `engine_c/bindings/scenario_search.py`) handles:

```python
def save_c_scenario(
    c_state: CState,
    path: Path,
    *,
    scenario_id: str,
    description: str,
    tags: list[str],
    card_under_test: str,
    market_deck_ids: list[str],
    special_stacks_present: list[str],
    move_count: int,
    is_terminal: bool,
    pretty: bool,
) -> None:
    raw = CSession.save_to_string(c_state, move_count=move_count, is_terminal=is_terminal)  # new helper
    payload = json.loads(raw)
    meta = payload.setdefault("metadata", {})
    meta["scenario_id"] = scenario_id
    meta["description"] = description
    meta["tags"] = tags
    meta["card_under_test"] = card_under_test
    meta["market_deck_ids"] = market_deck_ids
    meta["special_stacks_present"] = special_stacks_present
    # created_at, version, catalog_version, board_id left as serialised by C engine (already present)
    path.write_text(json.dumps(payload, indent=2) + "\n" if pretty else json.dumps(payload))
```

A `CSession.save_to_string` is added next to `CSession.save` (refactor: extract the `engine_serialize_state` call from `CSession.save` so we can post-process).

### Parallel / worker safety

`generate_card_scenarios` uses `ProcessPoolExecutor` when `workers > 1`. The C engine has a global `intern_init` / `register_default_effects` and a per-process arena. **Each worker process re-runs its own `_lib.intern_init(4096)` and `register_default_effects()` in its `CEngine.__init__`** (already idempotent under the global lock in `ce_api.py:294-298`), and each gets its own arena + definition. This is exactly how the existing `engine_c/bindings/c_adapter.py` and `session.py` already operate under multiprocessing in `scripts/run_ismcts.py`. No new locking or IPC needed — the rewrite just calls the same `CEngine` from worker processes.

### `justfile` change

`justfile:41-42` stays byte-identical. The `--engine c` switch the user wants lives inside the script via the new default branch — no justfile edit needed beyond confirming the existing recipe still works.

## TDD plan (TDD is mandatory)

Per the active TDD skill:

1. **RED** — Add a new test file `tests/test_generate_card_scenarios_c.py` with one focused test per behaviour the rewrite must preserve, importing the new C-backed entry points. Each test must call a real (not mocked) `CEngine` and assert on the produced `CState`. Initial tests:
   - `test_ensure_card_scenario_c_starter_card_is_instant` — mirrors `test_find_card_scenario_starter_card_is_instant`, asserts the returned `CState` has `phase == "main"`, `current_player_id` in `player_ids`, target card in that player's hand, and at least one legal `play_card` move.
   - `test_ensure_card_scenario_c_force_injects_after_exhausted_search` — mirrors the existing `test_ensure_card_scenario_force_injects_after_exhausted_search`, asserts the note dict shape and that the target is in the current player's hand.
   - `test_generate_card_scenarios_c_small_subset` — mirrors `test_generate_card_scenarios_small_subset`, asserts saved file count, file existence, target-in-hand after re-load via the C engine (`CSession.load`), and the same `forced_injections.json` shape.
   - `test_generate_card_scenarios_c_writes_forced_injection_notes` — mirrors the existing test, asserts the JSON file structure and `notes[0].card_id`.
2. **Verify RED** — run `pytest tests/test_generate_card_scenarios_c.py -q`; all four must fail because `engine_c.bindings.scenario_search` does not exist yet.
3. **GREEN** — implement `engine_c/bindings/scenario_search.py` and the C-aware branch of `scripts/generate_card_scenarios.py` minimally, just enough for the four tests to pass.
4. **Verify GREEN** — re-run; all pass; full `pytest -q` still green (no regressions in `tests/test_state_generator.py`, `tests/test_card_scenario_market_policy.py`, `tests/test_engine_c.py`).
5. **REFACTOR** — extract `CSession.save_to_string`, name helpers, deduplicate weight tables. Keep tests green.
6. **End-to-end smoke** — `just generate-card-scenarios workers=1 seed=4 attempts=2 steps=50` produces a `data/scenarios/batch_card_generation/` directory with files for a few cards, no crash. Compare the new JSON to the old JSON shape via `diff <(jq 'keys' old.json) <(jq 'keys' new.json)` for one or two cards (keys must match; metadata subset must match).

## Out of scope

- Performance tuning beyond what the C engine already gives for free.
- Touching the Python engine path, `--legacy-market`, the OpenSpiel wrapper, or any other script.
- Re-running the full 125-card batch as part of this change (smoke test only on a small subset; full batch stays a user action).

## Files to change

- **New** `engine_c/bindings/scenario_search.py` — C-backed `ensure_card_scenario_c`, `generate_card_scenarios_c`, `save_c_scenario`, helpers.
- **Edit** `engine_c/bindings/session.py` — extract `CSession.save_to_string` from `CSession.save` (small refactor, behaviour-preserving for the existing `save` caller).
- **Edit** `scripts/generate_card_scenarios.py` — switch the default batch / single-card path to the C-backed functions; leave the `--legacy-market` branch on the Python engine; the `--list-ids` path is engine-agnostic and stays.
- **New** `tests/test_generate_card_scenarios_c.py` — TDD-first test file as above.
- **No change** to `justfile` (recipe already invokes the script with the same flags).

## Risks / unknowns

- The C engine's `engine_apply_setup_json` reuses the same setup-parser as the Python path; the combined two-deck setup JSON produced by `combine_two_deck_market_setup(...).to_setup_data()` was originally consumed by `SetupDefinition.model_validate`. We will pass the same dict through `json.dumps` and verify the C engine accepts it (it parses the same `setup_id` / `starter_deck` / `market_deck` / `market_row_size` schema — see `engine_c/loader.c:parse_setup` and the existing `test_engine_c` use of `engine_apply_setup_json`).
- The C engine's `apply` returns `None` on failure; we treat that the same way the Python wrapper does (skip the move, count it as a no-op step) and bound the loop by `max_steps_per_attempt`. If the C engine rejects a move the Python engine would accept, the search will simply exhaust attempts earlier and fall through to the force-inject path — same fallback semantics as today.
- `engine_serialize_state` writes a `created_at` timestamp on each call. The Python path also writes a `created_at` (via `Scenario.from_game_state`). Both are non-deterministic; the rewrite is "same shape" not "same bytes".
