# Unified Market Setup Component

## Goal

Extract a single shared module that builds the 80-card combined-market setup used by the game-viewer, IS-MCTS runner, scenario generator, and random-walk script. Each call site keeps its own selection policy (user-picked, target-card-driven, random) but delegates the "given two 40-card rosters, build the combined market + aberration flag" work to one place.

After the change:
- `scripts/run_ismcts.py` runs games with the same rules as the game-viewer (~80-card market, special stacks, aberration-gated outcast).
- `engine/rules.py::is_terminal` no longer fires after 4 recruits; games run their natural length.
- The four near-duplicate implementations of the same logic collapse into one tested module.

## Design

**Module:** `game_setup/market_setup.py` (new file)

**Public surface** — module of pure functions returning a small frozen dataclass. KISS-first, no class hierarchy.

```python
@dataclass(frozen=True)
class MarketSetup:
    setup_id: str                       # e.g. "drow_dragon"
    market_deck_id: str                 # e.g. "market_drow_dragon"
    market_deck_entries: tuple[tuple[str, int], ...]   # combined card counts
    market_row_size: int                # copied from base_setup.json
    special_stacks: tuple[str, ...]     # ("house_guard","priestess_of_lolth",) or (...,"insane_outcast",)

    def to_setup_data(self) -> dict[str, object]:
        """Serialize into the dict shape accepted by build_game_definition_from_dicts."""

ABERRATIONS_DECK_ID = "aberrations"
SPECIAL_RECRUIT_IDS: frozenset[str] = frozenset({"house_guard", "priestess_of_lolth", "insane_outcast"})

def discover_full_deck_profiles(decks_dir: Path) -> tuple[DeckProfile, ...]:
    """40-card 'kind: full_deck' rosters, excluding special-recruit single-card stacks."""

def is_aberrations_in_market(deck_a_id: str, deck_b_id: str) -> bool:
    return ABERRATIONS_DECK_ID in {deck_a_id, deck_b_id}

def compute_special_stacks(deck_a_id: str, deck_b_id: str) -> tuple[str, ...]:
    """('house_guard','priestess_of_lolth') plus 'insane_outcast' if aberrations present."""

def combine_two_deck_market_setup(
    base_setup: dict[str, object],
    deck_a: DeckProfile,
    deck_b: DeckProfile,
) -> MarketSetup:
    """Build the MarketSetup for two given 40-card rosters + base_setup.json metadata."""

def pick_random_pair(profiles: Sequence[DeckProfile], rng: Random) -> tuple[DeckProfile, DeckProfile]:
    """Random distinct pair. Used by random_walk and (by default) IS-MCTS."""

def pick_pair_for_target(
    profiles: Sequence[DeckProfile],
    target_card_id: str,
    rng: Random,
) -> tuple[DeckProfile, DeckProfile]:
    """Pick a deck containing target_card_id; pair with a random distinct deck.
    Used by ensure_card_scenario for the reachable-search path."""
```

The existing `DeckProfile` dataclass currently lives in `interface/game_viewer.py` lines 235-247. To avoid creating a dependency from `game_setup` → `interface` (or duplicating the type), the plan moves `DeckProfile` into `game_setup/market_setup.py` and re-exports it from `interface.game_viewer` for back-compat.

`SpecialRecruitStack` policy lives in **one** place: the `compute_special_stacks` function. The engine's existing `SPECIAL_RECRUIT_STACKS` constant in `engine/helpers.py` and `_is_aberrations_enabled()` are unchanged — they continue to drive legality. The shared component just sets up `market_deck_id` so that the engine's id-name check works.

## OpenSpiel integration (`setup_data_json` param)

In `openspiel_pyrants/game.py`:

1. Add `"setup_data_json": ""` to both `_DEFAULT_PARAMS` and `_GAME_TYPE.parameter_specification`.
2. In `PyrantsGame.__init__` (and `_init_attrs`):
   - After resolving `board_path` / `card_path` / `setup_path`, check if `setup_data_json` is non-empty.
   - If so: parse the JSON and call `build_game_definition_from_dicts(board_data, card_data, parsed_setup_data)`.
   - Else: keep current behavior — `build_game_definition_from_files(...)`.
3. Expose `get_definition()` unchanged.

In `scripts/run_ismcts.py`:

1. New module-level helper (uses the shared component):
   ```python
   def _build_ismcts_setup_json(
       *, setup_path: Path, decks_dir: Path, base_seed: int, game_index: int,
   ) -> tuple[str, str, str]:
       """Return (setup_data_json, deck_a_id, deck_b_id) for a given IS-MCTS game."""
   ```
2. `run_one_game` (and `_run_one_game_standalone`) accept a `setup_data_json: str` argument and pass it to `pyspiel.load_game("python_pyrants", {"setup_data_json": ...})`.
3. `main()`: for each game, auto-pick two distinct `DeckProfile`s via `pick_random_pair` seeded by `base_seed + game_index`, build the `MarketSetup`, serialize to JSON. Logs the chosen pair to per-game output for reproducibility.

The IS-MCTS summary gains a `"deck_a_id"` / `"deck_b_id"` field so the artifacts record which market was used.

## Migration of call sites

| File | Current | New |
|---|---|---|
| `interface/game_viewer.py` (line 302) | `build_setup_from_market_selection` | Delegates to `combine_two_deck_market_setup` + `MarketSetup.to_setup_data`. `DeckProfile` re-exported. `load_market_deck_profiles` re-implemented via `discover_full_deck_profiles`. Public API unchanged. |
| `game_setup/scenario_generation/card_scenarios.py` (lines 47-94, 154-208) | `_resolve_two_deck_pairing` + `_build_card_scenario_setup` | `_resolve_two_deck_pairing` becomes a thin wrapper that uses `discover_full_deck_profiles` + `pick_pair_for_target` + `combine_two_deck_market_setup`. `_build_card_scenario_setup` calls the same shared function. The legacy variant (line 211) gets the same treatment. |
| `scripts/random_walk.py` (line 33) | `_build_roster_market_setup` | Replaced by calls to `discover_full_deck_profiles` + `pick_random_pair` + `combine_two_deck_market_setup` + `MarketSetup.to_setup_data`. |
| `scripts/run_ismcts.py` | Hardcoded `base_setup.json` via `PyrantsGame` defaults | New `setup_data_json` param populated by the shared component. |
| `game_setup/__init__.py` | — | Re-exports `MarketSetup`, `discover_full_deck_profiles`, `combine_two_deck_market_setup`, `pick_random_pair`, `pick_pair_for_target`, `compute_special_stacks`, `is_aberrations_in_market`, `DeckProfile`. |

`engine/helpers.py::SPECIAL_RECRUIT_STACKS` and `engine/rules.py::is_terminal` are **not** modified by this plan. The 80-card market fixes the symptom (games reach natural length) without changing the engine's terminal logic. A separate task can revisit `is_terminal` semantics.

## Edge cases handled

- Only one full_deck available → `pick_random_pair` raises `ValueError`; `pick_pair_for_target` falls back to repeating the only deck (matching current scenario-gen fallback at `card_scenarios.py:79-87`).
- `decks_dir` missing/empty → `discover_full_deck_profiles` returns `()`; `combine_two_deck_market_setup` is the only entry point that always succeeds, taking explicit decks.
- Same deck passed as both `deck_a` and `deck_b` → `pick_random_pair` enforces distinct picks; `combine_two_deck_market_setup` allows same-deck twice (caller's choice, useful when only one roster exists).
- Aberrations in both decks → `compute_special_stacks` returns all three specials.
- The shared component never reads `base_setup.json` for `market_deck` — it uses only `starter_deck` and `market_row_size` (matching current game-viewer behavior).

## Tests

New: `tests/test_market_setup.py`

- `discover_full_deck_profiles` returns 40-card rosters, excludes single-card stacks
- `combine_two_deck_market_setup` produces 80 total cards, correct `setup_id` and `market_deck_id`
- `combine_two_deck_market_setup` with same deck twice yields 80 cards (40 doubled)
- `is_aberrations_in_market` true only when aberrations deck present
- `compute_special_stacks` returns expected tuples for all 4 combinations (none/aberrations_a/aberrations_b/aberrations_both)
- `pick_random_pair` is deterministic given a seed and returns distinct decks
- `pick_pair_for_target` contains `target_card_id` in the chosen deck's entries when possible
- `MarketSetup.to_setup_data` round-trips through `build_game_definition_from_dicts` and produces a `GameDefinition` whose `market_deck_id` triggers the engine's `_is_aberrations_enabled()` correctly
- Recruit-slot legality from `engine.rules.legal_moves` with an aberrations market includes `INSANE_OUTCAST_RECRUIT_SLOT`; without aberrations, it does not (covers both `test_game_viewer_setup.py::test_special_recruit_slots_include_*` cases via the shared module)

Existing tests remain valid:

- `test_game_viewer_setup.py::test_build_setup_from_market_selection_combines_two_decks` — still passes (game_viewer re-exported function)
- `test_game_viewer_setup.py::test_create_hotseat_session_uses_selected_market_decks` — still passes
- `test_game_viewer_setup.py::test_special_recruit_slots_include_house_guard_and_priestess` and `*_outcasts_with_aberrations_market` — still pass
- `test_card_scenario_market_policy.py` (all 7) — still pass; the underlying logic is the shared component

New test for IS-MCTS:

- `tests/test_ismcts_market_setup.py` (or extend `openspiel_pyrants/tests/test_ismcts_smoke.py`)
  - Build `MarketSetup` from `drow+dragon`, serialize JSON, call `PyrantsGame(params={"setup_data_json": json})`, verify `game.get_definition().setup.market_deck_id == "market_drow_dragon"` and market row has 6 cards + 74 in deck.
  - Verify same `setup_data_json` for two `PyrantsGame` instances with the same seed produces the same initial state.
  - Verify an aberrations market enables `INSANE_OUTCAST_RECRUIT_SLOT` in `legal_moves`.

## File-by-file change list

1. **New:** `game_setup/market_setup.py` — `MarketSetup` dataclass + all public functions + `DeckProfile` (moved from game_viewer).
2. **Edit:** `game_setup/__init__.py` — re-export shared symbols.
3. **Edit:** `interface/game_viewer.py` — `DeckProfile` re-imported from `game_setup.market_setup`; `build_setup_from_market_selection` and `load_market_deck_profiles` re-implemented as thin wrappers over the shared module; `create_hotseat_session` unchanged.
4. **Edit:** `game_setup/scenario_generation/card_scenarios.py` — `_resolve_two_deck_pairing` and `_build_card_scenario_setup[_legacy]` delegate to shared module.
5. **Edit:** `scripts/random_walk.py` — `_build_roster_market_setup` removed; `main()` uses shared module.
6. **Edit:** `openspiel_pyrants/game.py` — add `setup_data_json` parameter; build definition from JSON when present.
7. **Edit:** `scripts/run_ismcts.py` — `_build_ismcts_setup_json` helper; pass `setup_data_json` to `pyspiel.load_game`; record `deck_a_id` / `deck_b_id` in `game_summary`.
8. **New:** `tests/test_market_setup.py` — unit tests for the shared module.
9. **Edit:** `openspiel_pyrants/tests/test_ismcts_smoke.py` (or new test file) — verify OpenSpiel param path produces expected state.

## Validation

- `pytest` — all existing tests + new tests pass.
- `ruff check .` — no new lints.
- Manual: `just ismcts num_sims=20 num_games=2` — confirm games now span more than 2 rounds and `summary.json` records the deck pair.
- Manual: `just game-viewer` — confirm selecting two decks still works.
- Manual: `just generate-card-scenarios aboleth` — confirm scenario still produced, `market_deck_id` reflects combined decks.

## Out of scope

- Changing `engine/rules.py::is_terminal` semantics (current check is correct given a 80-card market; no longer triggers prematurely).
- Changing the `SPECIAL_RECRUIT_STACKS` table in `engine/helpers.py`.
- Adding a 4-deck market mode.
- Migrating `bench_simulation.py` (uses prebuilt scenarios, no market construction).
- Adding a CLI argument to IS-MCTS for manual `--deck-a`/`--deck-b` selection. The plan keeps auto-pick for the simplest UX; a follow-up can add overrides.
