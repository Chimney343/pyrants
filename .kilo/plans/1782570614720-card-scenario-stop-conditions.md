# Plan: Pluggable stop conditions for `just generate-card-scenario`

## Goal

Let `just generate-card-scenario` accept additional stop conditions for the
random reachable-state search, layered (AND) on top of the always-on
`playable_now` condition (target card in the **current** player's hand AND a
legal `play_card` move for it exists).

### New, optional stop conditions (current-player scoped)

- **Spy on board now** — at least one spy belonging to the current player
  sits on any board node at stop time.
- **Aspect count in hand** — the current player's hand holds ≥ N cards whose
  primary `aspect` (from `data/cards/catalog.json`) matches a given aspect
  string (e.g. `guile:2`).

### Combination / scope rules (locked decisions)

- **AND** of all selected conditions. A condition is "selected" by passing its
  flag; omitting a flag means the condition is not required.
- `playable_now` is **always** required and cannot be turned off.
- Both new conditions apply to the **current player** (the player whose turn
  it is, who holds the target card). No per-condition player flag.
- Spy semantics: **spy on board now** (read `state._s.nodes[i].spies[]`),
  not "a spy was placed via a move this game".
- Aspect semantics: match against the card's primary `aspect` field in the
  catalog (existing `_catalog_cache()` in `engine_c/bindings/view.py:145`
  loads `data/cards/catalog.json` → `{card_id: {"aspect": ...}}`).

## Affected files

| File | Change |
|------|--------|
| `engine_c/bindings/scenario_search.py` | Primary (default engine). Add `StopConditions` dataclass + predicate evaluation; thread through `_classify_moves_c`, `_search_card_scenario_c`, `ensure_card_scenario_c`, `generate_card_scenarios_c`. |
| `game_setup/scenario_generation/card_scenarios.py` | Mirror the same plumbing for `--engine python` (`_classify_moves`, `_search_card_scenario`, `ensure_card_scenario`, `generate_card_scenarios`). |
| `scripts/generate_card_scenarios.py` | Add `--require-spy-on-board` (flag) and `--require-aspect ASPECT:COUNT` (e.g. `guile:2`) CLI args; parse and pass through to both engines. |
| `justfile` | Add `spy="false"` and `aspect=""` params to `generate-card-scenario` (and `generate-card-scenarios` batch, defaults off); add a comment block documenting usage. |
| `tests/` (C-binding test, e.g. `tests/test_engine_c.py` or a new `tests/test_scenario_search_conditions.py`) | Assert a generated scenario satisfies spy/aspect conditions when the flags are set. |

## Implementation steps

### 1. Define `StopConditions` (engine_c/bindings/scenario_search.py)

```python
@dataclass
class StopConditions:
    require_spy_on_board: bool = False
    require_aspect: str | None = None      # e.g. "guile"
    require_aspect_count: int = 0          # e.g. 2
```

Add a helper `_evaluate_stop_conditions(state, conditions) -> bool` that:

- spy: iterate `state._s.nodes[i]` for `i in range(state._s.node_count)`,
  read `node.spy_count` / `node.spies[j]`, compare `== current_player_sym`
  (intern current player id via `_lib.intern`). True if any match.
- aspect: build (cached per-search) `card_id -> aspect` map from
  `_catalog_cache()`; count hand cards (`state.player_hand(current_idx)`)
  whose aspect == `require_aspect`; True iff count >= `require_aspect_count`.
- Return `True` if every **selected** condition holds (unselected ones are
  skipped — they don't constrain).

Cache the card_id→aspect map once per search (build inside
`_search_card_scenario_c` after the catalog is available, pass into the
evaluator) to avoid re-reading the catalog each step.

### 2. Generalize `_classify_moves_c` / `_search_card_scenario_c`

- `_classify_moves_c(...)` keeps producing `playable_now` exactly as today
  (this is the always-on card condition). It does **not** need the new
  conditions — those are evaluated separately against the state, not against
  the move list.
- In `_search_card_scenario_c`, replace the bare `if playable_now: return`
  with `if playable_now and _evaluate_stop_conditions(state, conditions):
  return`. Keep the existing `injectable`/`fallback_state` logic unchanged.
- Thread `conditions: StopConditions | None = None` (defaulting to a no-op
  `StopConditions()`) through `_search_card_scenario_c`,
  `ensure_card_scenario_c`, and `generate_card_scenarios_c`.

### 3. Mirror in Python engine (game_setup/scenario_generation/card_scenarios.py)

Same shape: add `StopConditions` (or import the C one), `_evaluate_stop_conditions`
operating on `GameState` (spies via `state.board.nodes[...].spies`, aspect via
catalog lookup against `state.definition.catalog`), thread through
`_search_card_scenario` / `ensure_card_scenario` / `generate_card_scenarios`.
Keep the Python and C evaluators behaviorally identical.

### 4. CLI (scripts/generate_card_scenarios.py)

Add to `_parse_args`:

- `--require-spy-on-board` (store_true)
- `--require-aspect` (str, format `ASPECT:COUNT`, e.g. `guile:2`; default `None`)

Parse `--require-aspect` into `(aspect, count)` with a small validator
(split on `:`, count must be a positive int). Build a `StopConditions` and
pass to `ensure_card_scenario_c` / `generate_card_scenarios_c` (and the
Python equivalents). Default `StopConditions()` = today's behavior, so
omitting flags is a no-op for the existing batch flow.

### 5. justfile

Update `generate-card-scenario` (line ~100) and `generate-card-scenarios`
(line ~94) to accept `spy="false"` and `aspect=""`. Map to CLI flags
conditionally (only emit `--require-spy-on-board` when `spy == "true"`;
only emit `--require-aspect {{aspect}}` when `aspect != ""`). Add a comment
block above the recipe documenting:

```
# generate-card-scenario <card_id> [seed] [attempts] [steps] [spy] [aspect]
#   spy:   "true" to require the current player to have a spy on the board.
#   aspect: "ASPECT:COUNT" to require COUNT cards of ASPECT in hand (e.g. "guile:2").
#   Both are AND-combined with the always-on "target card playable now" condition.
# Examples:
#   just generate-card-scenario aboleth
#   just generate-card-scenario aboleth 4 30 3000 true
#   just generate-card-scenario aboleth 4 30 3000 false guile:2
#   just generate-card-scenario aboleth spy=true aspect=guile:2
```

### 6. Tests

- New `tests/test_scenario_search_conditions.py` (or extend
  `tests/test_engine_c.py`):
  - Pick a card id known to be reachable quickly (e.g. a cheap starter card).
  - `ensure_card_scenario_c(..., conditions=StopConditions(require_spy_on_board=True))`
    → assert the returned state has ≥1 current-player spy on the board.
  - `ensure_card_scenario_c(..., conditions=StopConditions(require_aspect="guile", require_aspect_count=2))`
    → assert the current player's hand has ≥2 guile-aspect cards.
  - Combined: both flags → both assertions hold.
  - Sanity: no flags → behavior unchanged (equivalent to today).
- Add the equivalent assertion path for the Python engine if
  `--engine python` is exercised, but C engine is the priority.
- Run `just test` and `just test-c-python` after changes; run
  `ruff check .` before commit.

## Risks & mitigations

- **Search takes longer / fails more often** with extra AND constraints.
  Mitigation: defaults stay off (no behavior change for the existing batch
  generation); the existing force-injection fallback path still applies when
  all attempts are exhausted. Document in the justfile comment that extra
  constraints may require raising `--max-attempts` / `--max-steps`.
- **Aspect catalog mismatch** between the C engine's loaded catalog and the
  JSON `_catalog_cache()`. Mitigation: the C engine is initialized from the
  same `data/cards/catalog.json`; use `_catalog_cache()` (already used by
  view.py / label_enrich.py) so the source of truth is identical.
- **Backward compat**: passing no new flags must reproduce today's output.
  Verified by step 6 sanity test and by keeping `_evaluate_stop_conditions`
  returning `True` for an empty/default `StopConditions`.

## Validation

1. `just build-c` (rebuild DLL after any C-side touch — none expected here,
   all changes are in Python bindings, but rebuild to be safe).
2. `ruff check .`
3. `just test` (full pytest, including the new test file)
4. `just test-c-python` (C-binding tests)
5. Manual smoke:
   - `just generate-card-scenario aboleth` (unchanged behavior)
   - `just generate-card-scenario aboleth spy=true` (spy present in result)
   - `just generate-card-scenario aboleth aspect=guile:2` (≥2 guile cards in hand)
   - `just generate-card-scenario aboleth spy=true aspect=guile:2` (both)

## Out of scope

- Per-condition player targeting (locked to current player).
- OR combination of conditions.
- Relaxing `playable_now` to "card-in-hand only".
- Conditions file / JSON spec (CLI flags only).
- Changes to the deprecated `engine/` Python port beyond the `game_setup/`
  scenario-generation mirror (which is not the deprecated engine itself).
