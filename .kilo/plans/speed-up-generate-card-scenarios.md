# Speed up `just generate-card-scenarios`

## Hot-path analysis (what dominates runtime today)

`just generate-card-scenarios` runs
`scripts/generate_card_scenarios.py` → `game_setup.scenario_generation.card_scenarios.generate_card_scenarios`,
which loops over ~120+ roster card ids and for each one calls
`ensure_card_scenario` → `_search_card_scenario`.

The search does **up to `max_attempts * max_steps_per_attempt = 3 * 1500 = 4500` `apply()` calls per card**.
Defaults: `--max-attempts 3 --max-steps 1500` → "expensive up to 3·1500·0.035 ≈ 158s" per card.
Wall clock for the full batch is minutes-to-hours.

Measured costs on this machine (single-shot, hot cache):

| Operation | Time |
|---|---|
| `json.load(catalog.json)` (425 KB) | ~74 ms |
| `CardCatalog.model_validate(...)` on that dict | ~238 ms (≈ **300 ms total per card**) |
| `apply(state, move)` average | ~0.035 ms (35 µs) → ~160 ms per 4500-step search |
| `legal_moves(state)` | same order of magnitude as `apply` |

### Per-card fixed cost (the big one)

For each of ~120 cards, `_build_card_scenario_setup` does:

1. `json.load(board.json)` + `json.load(catalog.json)` + `json.load(setup.json)`
2. `load_deck_rosters(decks_dir)` — glob + read every JSON in `data/decks/`
3. `build_game_definition_from_dicts(...)` → three Pydantic `model_validate` calls
   (`BoardDefinition`, `CardCatalog`, `SetupDefinition`)
4. `build_initial_game_state(...)` → creates a new `GameState` plus a 4-player `PlayerState` map and a shuffled market deck

Steps 1–3 rebuild **identical** immutable definition objects every iteration.
Across 120 cards × 3 attempts ≈ 360 rebuilds of the same `CardCatalog` → ~85 s of pure
re-parse, plus the same for `BoardDefinition` and `SetupDefinition`. None of this depends
on `card_id` (except for which decks feed the market, which is a tiny join).

### Per-step cost

- `legal_moves(state)` is called every step and rebuilds the entire `moves: list[Move]`
  from scratch (one `PlayCardMove` per hand card + main-phase actions + `EndMainPhaseMove`).
- We **immediately throw the list away** in two of three branches:
  we call `list(legal_moves(state))` then `_is_card_playable_now` (scans the list once)
  and `_is_injectable_card_state` (scans again), then we **re-iterate the list in
  `_select_biased_move`** to compute weights and pick. Three full iterations, two redundant.
- `apply()` calls `state.model_copy(deep=True)` for most move types — necessary for
  purity, but every step re-dups an entire `GameState` tree.

### I/O cost

- `save_game_state` writes ~63 KB JSON × ~120 cards = ~7.5 MB of pretty-printed JSON,
  each with `indent=2`. Each call goes through `Scenario.model_dump(mode="json")` →
  recursive Pydantic serialization of the full state tree.

### Other observations

- `iter_roster_card_ids` is called once at batch start — fine.
- `load_deck_rosters(decks_dir)` is called once per `_build_card_scenario_setup` and also
  walks `data/decks/*.json` 360 times. Cacheable.
- `_search_card_scenario` calls `json.loads(board_path.read_text(...))` once per call to
  extract `board_id`, then `_build_card_scenario_setup` re-reads the same file. Two reads.
- `generate_card_scenarios` calls `save_game_state` synchronously in the loop; nothing
  parallelizes I/O with simulation.
- The `tqdm` import + per-card `print(f"[{i}/{n}] {card_id}")` in the loop add minor
  overhead and force-flush stdout.
- `verbose=True` is hard-coded for batch mode → extra prints in the hot loop.

## Plan (ordered by impact / risk)

### 1. Cache the parsed `GameDefinition` (biggest win, low risk)
**File:** `game_setup/scenario_generation/card_scenarios.py`

Add a module-level `lru_cache`-backed loader that takes the four paths and returns a
frozen `GameDefinition`. The catalog never changes during a run. `_build_card_scenario_setup`
and `_search_card_scenario`'s `board_id` extraction both consume the cache.

Expected savings: ~85 s of Pydantic re-parse + ~360 redundant `json.load`s removed.

```python
@lru_cache(maxsize=8)
def _load_definition(board_path, card_path, setup_path):
    return build_game_definition_from_dicts(
        json.loads(board_path.read_text(encoding="utf-8")),
        json.loads(card_path.read_text(encoding="utf-8")),
        json.loads(setup_path.read_text(encoding="utf-8")),
    )
```

### 2. Cache the parsed roster decks
Same file. `load_deck_rosters(rosters_path)` walks `data/decks/` and reads ~11 small JSONs
on every call. Wrap with `lru_cache`. Trivial.

### 3. Skip `iter_roster_card_ids` and deck reload on each setup build
After caching the `GameDefinition` + roster list, the only per-card work left inside
`_build_card_scenario_setup` is the **per-card market join** (filter decks to those
containing the target). Do it inline against the cached roster list — no `load_deck_rosters`
call inside the per-attempt loop.

### 4. Single-pass `legal_moves` analysis
**File:** `game_setup/scenario_generation/card_scenarios.py:206-215`

Combine the three list scans into one iteration:

```python
moves = list(legal_moves(state))
if not moves:
    break
playable_now, injectable, weights = _classify_moves(moves, state, target_card_id)
if playable_now:
    return state, state
if injectable:
    fallback_state = state
state = apply(state, _pick_weighted(moves, weights, rng))
```

Add a small `_classify_moves` helper that returns
`(playable_now: bool, injectable: bool, weights: list[float])` in one pass.
Saves ~2× the per-step iteration cost and two Python-level list passes per step.

### 5. Cache the "is this card a starter or special-recruit" sets
These sets (`special_recruit_ids`, `starter_deck_ids`) are recomputed for every
`_build_card_scenario_setup` call, but `starter_deck_ids` derives from
`base_setup.json` (a tiny file). Move the construction next to the cached
`GameDefinition` or memoize it on the cached definition object as an attribute.

### 6. Parallelize the batch across cards
**File:** `scripts/generate_card_scenarios.py` and `card_scenarios.py`

Add a `--workers N` flag (default 1, parity-preserving). Use `concurrent.futures.ProcessPoolExecutor`
because:
- GIL-bound Python; threads will not help with `legal_moves` / `apply` / Pydantic
- workers must be seeded deterministically per card (use the same `card_seed = base_seed + i*1000`
  scheme so output is bit-identical)
- Pydantic `model_validate` is CPU-heavy and parallelizes well

Safeguards:
- `max_workers=os.cpu_count()` default; cap at 8 to avoid memory blow-up.
- Workers must each receive the cached `GameDefinition` payload (small: a few KB after
  `model_dump(mode="json")`) plus the path arguments; pass through `initializer` once
  per worker rather than per card.
- Use a `tqdm` outer bar; per-card `[i/n] {card_id}` log lines become out-of-order
  under parallelism — gate them behind `workers == 1` or move to DEBUG.
- Guard with an env-var override `PYRANTS_SCENARIO_WORKERS=1` for CI determinism.

Expected speed-up: ~linear in worker count up to the kernel's per-process overhead
(roughly 4–6× on an 8-core box). This is the second-biggest win.

### 7. Parallelize per-attempt search inside a single card
**File:** `game_setup/scenario_generation/card_scenarios.py:192-218`

The outer `for attempt in range(max_attempts)` loop is embarrassingly parallel —
each attempt is a fresh `Random(attempt_seed)`. Run the attempts concurrently and
take the first match. This composes with (6): with N attempt workers and M card
workers, total parallelism is N×M. Skip if (6) is already enabled to avoid
excessive fan-out.

### 8. Defer + batch JSON serialization
**File:** `game_setup/scenarios.py:108-114`, `135-158`

`save_scenario` writes `indent=2` JSON synchronously per card. Two changes:
- Drop `indent=2` for batch generation (saves ~30 % on file size and ~25 % on wall
  time per file). Add a `--pretty` flag to opt back in.
- Have workers return the `Scenario` object (not a `Path`) and serialize on the main
  process, or have workers write to a `tempfile.NamedTemporaryFile` and the main
  process does a final `os.replace` — keeps output atomic.

### 9. Use `orjson` if available
**File:** `game_setup/scenarios.py`

The `model_dump(mode="json")` payload is essentially a JSON dict; serializing with
`orjson.dumps` is typically 2–4× faster than `json.dumps`. Try/except import and
fall back to stdlib. Same for the `json.load` calls in loaders (use `orjson.loads`).

### 10. Minor: stop double-reading the board file
`_search_card_scenario` reads `board.json` to get `board_id`, then
`_build_card_scenario_setup` reads it again to build the `BoardDefinition`. After (1),
both come from the cached definition.

### 11. Minor: make `verbose` default to `False` in batch mode
**File:** `game_setup/scenario_generation/card_scenarios.py:381`

`generate_card_scenarios` always passes `verbose=True` and emits a per-step `print`
inside `_search_card_scenario` on every attempt exhaustion. With default
`max_attempts=3`, every card emits at least 3 extra stdout lines. With the
`max-steps-per-attempt` cost being the dominant factor, this is small, but
removing it cleans up the logs and removes a `print → flush` per card.

### 12. Profile before/after to verify
Add a small `cProfile` wrapper behind `--profile-out artifacts/scenarios_profile.pstats`
and run before/after on a 5-card subset to confirm gains. The `just` recipe can stay
unchanged; users opt in via env var.

## What I will NOT change

- `engine/rules.py`, `engine/state.py`, `engine/generic_runtime/*` — the engine must
  stay pure (enforced by `tests/test_engine_purity.py`), and the search is correct as
  written. Optimizing `apply`/`legal_moves` is a separate, much larger refactor.
- The `Random(seed)` scheme. Determinism must be preserved so existing saved scenarios
  remain bit-identical.
- `engine/scoring.py`, board topology, deck rosters.

## Validation

1. `pytest -q` (full suite, no engine changes).
2. `ruff check .` (per AGENTS.md).
3. Run `just generate-card-scenarios` and compare:
   - wall-clock time
   - number of saved scenarios
   - number of forced injections
   - hash of each generated scenario file (must match pre-change hashes for cards
     whose `card_seed` is unchanged)
4. Re-run `tests/test_scenario_generation.py` to confirm scenarios still validate.

## Estimated total speedup

- (1)+(2)+(3)+(5): removes ~90 s of fixed per-card overhead → ~3 min off a 10 min run
- (4): ~10–20 % on the simulation portion
- (6): ~4–6× on a typical multi-core dev box
- (8)+(9): ~25–35 % on I/O portion

Combined: realistic **5–8× speedup** end-to-end with the default `just` invocation,
dominated by (6). If the user wants a quick win with zero risk, ship (1)+(2)+(3)+(4)
first; ship (6) as a follow-up.
