# Card Scenario Generation — Market Scoping Revision

## Goal

Replace current ad-hoc market scoping in `_build_card_scenario_setup` with a deterministic
two-deck market policy, plus persist deck provenance so the game viewer can display
which two factions populated the market.

## Current Behaviour (problem summary)

`game_setup/scenario_generation/card_scenarios.py` lines 96–169:

- `iter_roster_card_ids()` returns union of all full_deck roster card ids.
- `_build_card_scenario_setup()` filters the market to "decks containing the target card" for
  normal cards, or to "all decks" for special-recruit cards and starter cards.
- The constructed `market_deck.deck_id` is `"card_scenario_market"` — a generic id that
  does not encode which rosters contributed.
- `state.definition.setup.market_deck.deck_id` is the only field `interface/game_viewer.py:_derive_market_deck_metadata`
  uses to recover faction labels. The current generic id is parsed only because
  `game_viewer` falls back to matching the `"market_"` prefix pattern (line 917). Card
  scenarios never get that prefix, so viewer shows empty deck labels.

## Required New Behaviour

Per user spec, for each generated scenario:

1. Pick a unique target card.
2. Build market = **exactly two `full_deck` rosters**:
   - Roster A: the deck that **contains the target card**.
   - Roster B: one **randomly selected** `full_deck` roster, **excluding** the three
     special-recruit single-card stacks (`house_guard`, `priestess_of_lolth`, `insane_outcast`).
3. **Market row composition** at game start:
   - Top slots 0–2: the three special stacks (always present; these are model-level
     "anytime recruit" stacks and not part of `market_deck`).
   - Top slot 3: **Insane Outcast stack appears only if the aberrations deck is one of
     A/B** (mirrors existing `game_viewer._aberrations_in_market` rule).
   - Remaining row slots: cards drawn from the two-deck market pool.
4. **Persist deck provenance** in the saved scenario so `game_viewer` can display the
   two faction names. Existing `metadata.source_setup_id` is the natural home; expand it
   to also carry a structured deck list.

## Design

### 1. New market builder

Replace the body of `_build_card_scenario_setup` with a helper that:

- **Locate Roster A**: find the `full_deck` roster that contains the target card in
  its `entries`. If `target_card_id in SPECIAL_RECRUIT_IDS`, skip this step (handled
  in step 4 below). Raise if no roster matches a non-special target.
- **Select Roster B** from the eligible pool = all `full_deck` rosters whose
  `deck_id` is not in `SPECIAL_RECRUIT_IDS` and not equal to Roster A's id. Use
  `Random(base_seed ^ stable_hash(card_id))` so pairing is canonical per
  `(card, seed)`. **If only one `full_deck` roster exists**, use it for both A
  and B, log a warning once per batch.
- **Merge** `entries` of both rosters into the `market_deck`. Set `deck_id` to
  `f"market_{roster_a.deck_id}_{roster_b.deck_id}"` so the existing viewer parser
  (`game_viewer.py:917`) recovers labels without code change.
- **Special-recruit targets** (`house_guard`, `priestess_of_lolth`,
  `insane_outcast`): treat as force-injection. Build a normal two-deck market
  using a random Roster A and random Roster B (both chosen from the eligible
  pool, no card-roster matching required). The walk is bypassed — the target
  card is placed into the current player's hand by `_force_inject_card_into_current_hand`
  with seed `base_seed + 999_999`. The result is saved with the
  `forced_injection` tag.

### 2. Aberrations rule

- Compute `aberrations_in_market = "aberrations" in {roster_a.deck_id, roster_b.deck_id}`.
- Embed this in metadata (see below). Game viewer already handles
  `_aberrations_in_market` from parsed deck ids, so when deck_id follows the
  `market_a_b` convention the existing parser will set the flag. **Verify** in plan
  question 2.

### 3. Provenance persistence

Extend `ScenarioMetadata` in `game_setup/scenarios.py` (line 55) with two optional
fields:

- `market_deck_ids: list[str] = Field(default_factory=list)` — the two roster ids
  (`["drow", "dragon"]`).
- `special_stacks_present: list[str] = Field(default_factory=list)` — the subset of
  `["house_guard", "priestess_of_lolth", "insane_outcast"]` actually in the
  starting row (always all three except `insane_outcast` follows the aberrations rule).

`Scenario.from_game_state` (line 76) and `save_game_state` (line 158) gain a
`market_deck_ids` and `special_stacks_present` parameter so callers can pass them
through. Default empty list — backward compatible with existing scenarios.

### 4. Game viewer changes

In `interface/game_viewer.py`:

- `_derive_market_deck_metadata` (line 913): if state has empty deck labels after
  parsing, fall back to reading the new `ScenarioMetadata.market_deck_ids` field.
  Concretely: this function is currently called on **state** (not scenario). Two
  options:
  - (a) Change the call site (line 873) to pass the loaded scenario's metadata, OR
  - (b) Encode provenance into `state.definition.setup.market_deck.deck_id` using
    the `market_a_b` convention so the existing parser handles it. **Prefer (b)** —
    keeps the viewer single-source-of-truth on the state, and works for any other
    code that reads the market deck id.
- The `market_a_b` deck_id convention already drives the viewer parser (line 917), so
  implementing (b) requires no viewer change beyond verifying the parser handles the
  two-id case (it does — line 922 `sorted_ids` and 930+ loop).

### 5. Search and stop conditions

`_search_card_scenario` (line 212) is unchanged except it receives the new
provenance fields for logging/notes. The "playable now" check (line 199) — target in
current player's hand during MAIN — is the correct stop condition. No change.

### 6. Force-injection fallback

`_force_inject_card_into_current_hand` (line 272) and `ensure_card_scenario` (line 331)
remain unchanged in behaviour. Provenance is already known from the reachable search
attempt that produced the fallback state.

### 7. CLI / script surface

`scripts/generate_card_scenarios.py`: no new flag. The two-deck policy is the
default. Add a `--legacy-market` flag (off by default) that restores the old
behaviour — kept for one release to allow comparison runs.

## Files Touched

| File | Change |
|------|--------|
| `game_setup/scenario_generation/card_scenarios.py` | Replace market construction; emit `market_a_b` deck_id; compute aberrations flag; add provenance to `injection_note` |
| `game_setup/scenarios.py` | Add `market_deck_ids` and `special_stacks_present` to `ScenarioMetadata`; thread through `from_game_state` and `save_game_state` |
| `scripts/generate_card_scenarios.py` | Pass new metadata fields to `save_game_state`; add `--legacy-market` flag |
| `tests/test_state_generator.py` | Update assertions: market has two rosters, `market_deck_ids` field set, aberrations rule respected |
| New: `tests/test_card_scenario_market_policy.py` | Property tests: market contains exactly two `full_deck` rosters; second roster is not a single-card stack; aberrations gate the insane outcast slot |
| `docs/cards/` status doc | One-paragraph note on the new policy |

## Decisions (locked)

1. **Special-recruit targets** (`house_guard`, `priestess_of_lolth`, `insane_outcast`):
   **force-inject** the target directly into the current player's hand and use a
   random two-deck market for context. The walk is skipped (or runs zero steps)
   because the card is already playable. Treated as a forced-injection scenario
   with tags `["generated", "cards", "forced_injection"]` and the standard
   injection note.

2. **Insane Outcast gating**: the Insane Outcast stack appears in the market row
   only when `aberrations` ∈ {Roster A, Roster B}. House Guard and Priestess of
   Lolth stacks always appear, regardless of pairing. This matches the existing
   `game_viewer.py:1178` rule and is encoded in `special_stacks_present`.

3. **Single-roster edge**: if only one `full_deck` roster exists, duplicate it
   (Roster A = Roster B) and log a warning. The generation flow continues
   unchanged.

4. **Roster B seeding**: the RNG used to select Roster B is
   `Random(base_seed ^ stable_hash(card_id))`. One canonical pairing per
   `(card_id, base_seed)`, reproducible across runs and walk attempts, and
   independent of which walk attempt first reached the target.

## Validation

- `pytest` (full suite).
- `ruff check .` (linter).
- Smoke: `just generate-card-scenarios --workers 1 --seed 0 --attempts 1 --steps 200`
  on a single card via `--card-id aboleth`, inspect output JSON for
  `metadata.market_deck_ids` length = 2 and `metadata.special_stacks_present` set.
- Open one output in `just game-viewer` and confirm deck labels show two faction
  names and Insane Outcast slot respects the aberrations rule.

## Out of Scope

- Changing the random walk policy weights (lines 194–202).
- Changing the force-injection mechanism.
- Touching `replay_viewer.py` or `board_creator.py`.
- Adding a new card scenario kind beyond "reachable" and "forced_injection".
