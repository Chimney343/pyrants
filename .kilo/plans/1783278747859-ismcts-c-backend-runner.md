# Plan: IS-MCTS runner → C backend (default), N-player support

## Goal

Make `scripts/run_ismcts.py` actually use the C engine backend (`python_pyrants_c`) by default, fix the broken `just ismcts*` recipes, and wire `--num-players` end-to-end (2–4). This unblocks real RL bot runs (the Python backend is ~10 ms/clone → ~2.2 h/game per the script's own docstring; the C path uses `engine_clone` memcpy + C determinize) and aligns the IS-MCTS path with the active ADR "Adopt C as the engine source of truth."

## Confirmed problem

- `run_ismcts.py::_parse_args` defines **no `--game` and no `--num-players`** flags.
- The `justfile` recipes `ismcts`, `ismcts-quick`, `ismcts-c`, `ismcts-c-quick` all pass `--num-players`; the `*c` recipes also pass `--game python_pyrants_c`. All four therefore crash with argparse "unrecognized arguments".
- `run_one_game` hardcodes `pyspiel.load_game("python_pyrants", load_params)` at lines 611 and 691 — `--game` would be ignored even if it parsed.
- The runner is hard-coupled to the deprecated `engine/` Python port at ~5 sites that assume a Pydantic `GameState`:
  - `from openspiel_pyrants.action_encoding import action_to_move` → `action_to_move(state._engine, aid)` calls `engine.rules.legal_moves`.
  - `str(chosen_move_obj)` — `CMoveWrapper` has **no `__str__`** (default repr is useless).
  - `_move_to_payload(move)` calls `move.model_dump(mode="json")` — `CMoveWrapper` has **no `.model_dump()`**.
  - `compute_final_scores(state._engine)` — Python-only; C terminal scores come from `adapter.final_scores()`.
  - `_legal_moves_strings(state._engine, legal_ids)` loops calling `action_to_move`.
- `python_pyrants_c` registration in `openspiel_pyrants/__init__.py` is wrapped in `except (ImportError, OSError): pass` → if the DLL is missing, `pyspiel.load_game("python_pyrants_c")` raises an opaque "game not found" rather than a useful "run `just build-c`".
- Underlying C OpenSpiel path already works for raw pyspiel bot loops (`test_ismcts_smoke_c.py` parameterizes 2/3/4 players); only `run_ismcts.py` is broken.

## Backend divergence to respect (C vs Python)

- `CMoveWrapper`: has `.move_type` and `.data` (dict), no `.model_dump()`, no `__str__`, `__deepcopy__` returns `self` (shared ref).
- Move-type names differ:
  - C: `activate_ability`, `decline_ability`, `resolve_generic`
  - Python: `activate_card_ability`, `decline_card_ability`, `resolve_generic_choice`
- C action order is the engine's native order (no sort) — `action_encoding_c.compute_c_action_map` already used by `PyrantsCState`.
- `PyrantsState.returns()` and `PyrantsCState.returns()` already handle zero-sum (n==2) vs general-sum (n>2).

## Approach

### 1. CLI flags (`scripts/run_ismcts.py::_parse_args`)
- Add `--game` with `choices=["python_pyrants", "python_pyrants_c"]`, default `python_pyrants_c`.
- Add `--num-players`, `type=int`, default `2`, validated `2 <= n <= 4` (reuse the `_parse_num_players` pattern from `game.py`).
- Do **not** change other flags.

### 2. Route `load_game` through the flags (`run_ismcts.py::main` + `_run_one_game_standalone`)
- Both `pyspiel.load_game("python_pyrants", load_params)` sites → `pyspiel.load_game(args.game, load_params)`.
- Pass `num_players` into `load_params`: `{"num_players": str(args.num_players), "setup_data_json": setup_json}` (registration expects a string).
- Wrap `load_game` in a helper `_load_game_or_die(name, params)`:
  - On `pyspiel.GameNotFoundError`/`ValueError` when `name == "python_pyrants_c"`, check `engine_c/engine_c.dll` existence; if absent, raise a clear `RuntimeError("C engine DLL not found — run `just build-c`")`.
  - Re-raise other errors verbatim.

### 3. Backend-agnostic state interface (add to both `openspiel_pyrants/state.py` and `state_c.py`)
Add these methods to both `PyrantsState` and `PyrantsCState` (cheap — reuses existing `_cached_indexed_moves` / `_adapter`):

- `decode_action(aid) -> Move|CMoveWrapper` — return `self._cached_indexed_moves[aid][1]` (recompute via `compute_action_map`/`compute_c_action_map` if cache is None).
- `move_to_str(move) -> str` — Python: `str(move)`. C: `str(move)` after `CMoveWrapper.__str__` is added (see step 4).
- `move_to_payload(move) -> dict` — Python: `move.model_dump(mode="json")`. C: `move.to_payload()` (see step 4).
- `final_scores() -> dict[str, int|float]` — Python: `compute_final_scores(self._engine)`. C: `self._adapter.final_scores()` (terminal) / per-player `player_score` (non-terminal).

### 4. `CMoveWrapper` additions (`engine_c/bindings/ce_api.py`)
- Add `__str__(self)` returning a human-readable label (e.g. `f"{move_type} {data}"` minimally; match Python `Move.__str__` shape as feasible).
- Add `to_payload(self) -> dict` returning `{"move_type": <normalized_name>, **self.data}`.
- **Name normalization map** (translate C → Python move_type names) so replay payloads stay consistent with `interface/replay_viewer.py` and `build_replay_payload`:
  - `activate_ability` → `activate_card_ability`
  - `decline_ability` → `decline_card_ability`
  - `resolve_generic` → `resolve_generic_choice`
  - others: identity.
- Add a test asserting the normalization map covers every `_MOVE_TYPE_MAP` value.

### 5. Rewrite the runner call sites (`run_ismcts.py::run_one_game`)
Replace:
- `action_to_move(state._engine, int(chosen))` → `state.decode_action(int(chosen))`.
- `_legal_moves_strings(state._engine, legal_ids)` → a new local helper that calls `state.decode_action(aid)` and `state.move_to_str(...)`.
- `str(chosen_move_obj)` → `state.move_to_str(chosen_move_obj)`.
- `_move_to_payload(chosen_move_obj)` → `state.move_to_payload(chosen_move_obj)`.
- `compute_final_scores(state._engine)` → `state.final_scores()`.
- `state._engine.round_number` / `state._engine.phase.value` / `state._engine.players` access for telemetry: keep as-is (both states already expose `.round_number`, `.phase.value`, `.players` — `PyrantsCState` via the `_EngineShim`). No change.
- Drop the `from openspiel_pyrants.action_encoding import action_to_move` import (no longer used).

### 6. N-player in `run_one_game`
- `bots = [ISMCTSBot(...) for _ in range(num_players)]` using per-player `rng_i = np.random.RandomState(seed + game_index*num_players + i)`.
- Replace `if cp < 0 or cp >= 2: break` with `if cp < 0 or cp >= num_players: break`.
- Generalize winner logic:
  - n==2: keep existing zero-sum diff check (`abs(ret[0]-ret[1]) > 1e-6`).
  - n>2 (general-sum): `winner = max(range(n), key=lambda i: ret[i])` if the top score is unique else `None` (tie).
- `outcome` mapping: extend for n>2 (`p0_win`/`p1_win` generalize to `p{i}_win`).
- Pass `num_players` through `_run_one_game_standalone` and `main`'s single-worker path.
- `build_replay_payload` already takes `player_ids=list(state._game.get_player_ids())` and `winner_id` — confirm it handles n>2 (verify during impl; extend if needed).

### 7. Justfile
- Recipes already pass `--num-players` and `--game` for the `*c` ones; once args exist, `just ismcts` (C default), `just ismcts-quick`, `just ismcts-c`, `just ismcts-c-quick` all work as written.
- Verify `just ismcts` defaults map to C (no `--game` needed; argparse default is `python_pyrants_c`).
- No AGENTS.md changes (recipe names/semantics unchanged).

### 8. Tests
Add `openspiel_pyrants/tests/test_run_ismcts_runner.py`:
- Parametrize `game_name in ("python_pyrants", "python_pyrants_c")` × `num_players in (2,3,4)` × tiny `num_sims=2`, `max_rounds=10` to keep it fast.
- Drive `run_one_game` directly (not `main`) and assert: `decision_count > 0`, `len(final_scores) == num_players`, `returns` zero-sum for n==2, no exceptions, replay/decisions files written.
- Use the existing `requires_c_engine` fixture (from `openspiel_pyrants/tests/conftest.py`) to skip the C cases when the DLL is missing.
- Add a unit test for the `CMoveWrapper.to_payload()` name normalization map (all `_MOVE_TYPE_MAP` values resolve to a known Python name).
- Keep `just openspiel-test` and `just test` green. Confirm `tests/test_engine_purity.py` stays green (no edits to `engine_c/` library sources or `engine/`).

## Validation

- `just build-c` (DLL must be present for C tests).
- `just openspiel-test` — new runner test passes for 2/3/4 players × both backends.
- `just test` — full pytest suite green, including `tests/test_engine_purity.py`.
- `just ismcts-quick` (C default, 2p) completes a 1-game, 2-sim run without argparse/AttributeError.
- `just ismcts-c-quick` (explicit C, 2p) completes identically.
- `just ismcts num_sims=4 num_games=1 num_players=4` (C default, 4p) completes a 4-player game.
- Manual: confirm `artifacts/ismcts/game_0000/replay.json` `move_type` fields use Python-normalized names for both backends.

## Risks / open items to verify during impl

- **Replay-payload name compatibility**: `interface/replay_viewer.py` and `scripts/_replay_payload.build_replay_payload` may depend on Python move-type names. Confirm and adjust the C normalization map accordingly; add a replay-viewer smoke if it doesn't already cover C.
- **`CMoveWrapper.__deepcopy__` returns `self`**: the runner stores `chosen_move_obj` in `replay_log`. CMoveWrapper data is extracted lazily and cached; confirm no later mutation of the underlying C struct invalidates cached `.data` after the state advances (C moves are snapshots — should be safe, but verify).
- **`_EngineShim.players`** returns a fresh dict each access and only `.score` per player — sufficient for the runner's `final_scores` fallback; confirm non-terminal `outcome`/scoring telemetry still works for n>2.
- **`max_world_samples` / IS-MCTS bot `num_players`**: confirm `ISMCTSBot` accepts the game for n>2 (it does — `test_ismcts_smoke_c.py` already runs it).

## Boundaries

- **In scope**: `scripts/run_ismcts.py`, `openspiel_pyrants/state.py`, `openspiel_pyrants/state_c.py`, `engine_c/bindings/ce_api.py` (CMoveWrapper only), `openspiel_pyrants/tests/test_run_ismcts_runner.py` (+ normalize-map unit test).
- **Out of scope**: retiring the `python_pyrants` registration, observation/info-state tensors, partial/top-of-deck determinization, self-play/training pipeline, changes to `engine_c/` C sources, changes to `engine/`.