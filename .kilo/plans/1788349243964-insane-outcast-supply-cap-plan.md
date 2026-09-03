# Insane Outcast Shared-Supply Cap + JSON-Driven Special Stacks

Engine rules-correctness fix in `engine_c/` for the gap tracked per
`docs/validation/f004-fix-plan.md` § 11, plus the data-driven special-stack
refactor. OpenSpiel `GameInfo` metadata is **not** touched (see D3).

## 0. Directives (user, 2026-09-02)

1. **Cap the injection.** `give_insane_outcast` (`engine_c/actions.c:698-705`) appends
   fresh `insane_outcast` copies to a target's discard pile without consulting
   `remaining_special_stack_count` or the 30-copy supply — measured floor −80
   (`MAX_ZONE_SIZE`) vs the −30 design intent. There are exactly **30 Insane Outcasts
   in the game**; a forced grant when the board stack is empty still executes but adds
   no card.
2. **Totals from JSON.** The C engine hardcodes 15/15/30 (`helpers.c:263-268`,
   `view.c:110-112`); totals must be read from JSON instead.
3. **Return-to-stack counting.** Outcasts returned via the card's own ability
   (discard-a-card ▸ return to supply), devour replacement, or promote replacement go
   back to the board stack — the shared supply cycles; it does not monotonically deplete.

## 1. Verified root cause (facts, with citations)

- **Injection site:** four effect kinds (`give_insane_outcast_to_each_opponent`,
  `_to_self`, `_to_selected_player`, `_to_player_with_presence_on_last_selected_node`)
  all funnel into `give_insane_outcast` (`actions.c:698-705`, callers `718-729`), bounded
  only by `MAX_ZONE_SIZE=80` (`state.h:16`). Six injector cards: derro, demogorgon,
  ghoul, gibbering_mouther, myconid_adult, myconid_sovereign — **all in
  `data/decks/demons.json`**.
- **Hardcode + dead gate:** `special_stack_config` (`helpers.c:263-268`) hardcodes
  100=house_guard/15, 101=priestess_of_lolth/15, 102=insane_outcast/30. Call sites:
  `rules.c:187-200` (move gen; slot 102 gated by `is_aberrations_enabled`
  `helpers.c:257-261` — dead in practice, since composed setup ids are
  `"a_b"`/`"market_a_b"`, never `"aberrations"`), `rules.c:686-689` (recruit slot
  resolution), `helpers.c:495-547` (`apply_recruit`/`apply_recruit_free`),
  `view.c:110-112` (view fields, consumed via ctypes mirror
  `engine_c/bindings/engine_bindings.py:376-377` → `bindings/view.py:572-574`).
- **Data never reaches C:** neither `data/decks/base_setup.json` nor
  `MarketSetup.to_setup_data()` (`game_setup/market_setup.py:49-61`) emits stack data.
  Both setup entry points — `engine_load_definition_json` (`loader.c:430-459`, setup
  file) and `engine_apply_setup_json` (`loader.c:461-465`, `setup_data_json` from
  `interface/game_viewer.py:385-408`, `scripts/run_ismcts.py:126-141`,
  `bindings/scenario_search.py:278-287`, `openspiel_pyrants/game_c.py` passthrough) —
  funnel `parse_setup` (`loader.c:403-428`).
- **Return-to-supply already implemented and tested:** `self_purge_to_supply`
  (`actions.c:829-845`; `tests/c_engine/test_card_insane_outcast.py`), devour
  replacement for hand/played_self/market/inner_circle (`actions.c:591-639`,
  `651-663`), promote replacement (`helpers.c:372-388`; `actions.c:509-510`). Because
  returned copies leave player zones, the derived count
  `remaining = total − owned-across-all-players` (`helpers.c:270-289`) is exact once
  injection is capped. No new return path is needed — only replenishment tests.
- **Gating contradiction:** rulebook `docs/tyrants-rulebook.md:133` — *"If you're
  playing with the Demons half-deck, put the Insane Outcast cards face up"* — but code
  and tests gate on aberrations (`market_setup.py:109-117`;
  `tests/test_card_scenario_market_policy.py:38-58`).
- **Rules for exhaustion order:** `docs/tyrants-rulebook.md:355` — when multiple
  outcasts are recruited and the supply would run out, they are allocated **clockwise
  starting with the player whose turn it is**.
- **Scoring floor:** `insane_outcast` is the only negative `deck_vp` card (−1;
  `inner_circle_vp` 0); every other `compute_final_scores` component
  (`scoring.c:90-126`) is non-negative (mutation audit in `f004-fix-plan.md` § 1).
  Formal legal-play floor after the cap = **−30.0**. `min_utility=-50.0` is currently
  live (`openspiel_pyrants/game_c.py:65-81`).
- **Test-fixture constraint:** injector card tests run on scenarios whose definition
  uses `setup_path=data/decks/base_setup.json` (`tests/c_engine/card_test_helpers.py:50`,
  e.g. `test_card_derro.py`) — `base_setup.json` must therefore declare the insane
  stack or those tests break.
- **Serialization:** saves embed definition **paths**, not the definition
  (`bindings/session.py:140-176`), so no save-format migration is needed.

## 2. Decisions

- **D1 — Demons gating (user-confirmed).** The insane_outcast stack exists iff the
  demons roster is one of the two market half-decks (rulebook :133). Updates
  `compute_special_stacks`, deletes `is_aberrations_enabled`, rewrites
  `test_aberrations_gates_insane_outcast_slot` as a demons-gating test.
  `base_setup.json` declares **all three** stacks (universal test/scenario fixture).
- **D2 — Legacy fallback (user-confirmed).** When a setup JSON lacks
  `special_stacks`, `parse_setup` fills a legacy default table 15/15/30 — the *only*
  remaining place the constants live, documented as a compatibility fallback.
- **D3 — Defer `min_utility` tightening (user-confirmed).** Keep `-50.0` and the
  existing `test_utility_contract.py` assertions; the −30.0 formalization is a
  separate metadata pass with its own ledger cycle (follow-up note in § 7).
- **D4 — Return-to-stack semantics (grounded, not asked).** "Discarded outcasts
  return to the stack" = the card's existing implemented paths: optional paid ability
  (`self_purge_to_supply`), devour replacement, promote replacement (catalog
  `data/cards/insane_outcast.json` rules_text; rulebook :228). No automatic return on
  end-of-turn cleanup — the engine already conforms; this plan locks it with tests.
- **D5 — Slots stay 100/101/102.** They are engine-internal routing constants carried
  per-stack in the setup JSON; no card↔slot mapping remains hardcoded in C. Recruit
  moves encode `card_id` only, so OpenSpiel action encoding is unaffected.
- **D6 — Undefined insane stack** (composed non-demons market, or hand-written JSON
  omitting it): outcast grants are no-ops — "no stack in this game". Injector cards
  cannot be bought in such markets; only scenario hand-injection can surface one.

## 3. Target design

Setup JSON (both `base_setup.json` and `to_setup_data()` output) gains:

```json
"special_stacks": [
  {"market_slot": 100, "card_id": "house_guard", "stack_total": 15},
  {"market_slot": 101, "card_id": "priestess_of_lolth", "stack_total": 15},
  {"market_slot": 102, "card_id": "insane_outcast", "stack_total": 30}
]
```

(insane entry present **iff demons in market** for composed setups; base_setup
declares all three). Totals are sourced from the `single_card_stack` rosters
(`data/decks/house_guard.json` 15, `priestess_of_lolth.json` 15, `insane_outcast.json`
30 — already asserted by `tests/test_deck_rosters.py`).

C engine:
- `state.h`: `#define MAX_SPECIAL_STACKS 3`;
  `typedef struct { Sym card_id; int market_slot; int stack_total; } SpecialStackDef;`
  `SetupDefinition` gains `SpecialStackDef special_stacks[MAX_SPECIAL_STACKS]; int special_stack_count;`
- `loader.c` `parse_setup`: parse the array; absent → legacy default table (D2);
  skip invalid entries (duplicate slot, missing card_id) like the rest of the loader.
- `helpers.c`: `special_stack_config(const GameState *, int market_slot, ...)` and new
  `special_stack_total_for_card(const GameState *, Sym card_id)` (−1 when undefined)
  read `state->definition->setup.special_stacks`; `remaining_special_stack_count`
  derives its total via lookup (callers stop passing literals); keep the existing
  market-deck/row availability fallback unchanged.
- `rules.c:187-200`: iterate the definition's stacks (replaces the `{100,101,102}`
  array and the `is_aberrations_enabled` line — gating becomes "stack is defined");
  `rules.c:686-689`, `helpers.c:495-547`, `view.c:110-112`: pass `state`, drop
  literals. Delete `is_aberrations_enabled` (`helpers.c:257-261`, `helpers.h` decl).
  View field *names* stay (presentation-layer conveniences, values definition-driven;
  undefined stack → 0).
- `actions.c` `give_insane_outcast`: total via `special_stack_total_for_card`;
  per target grant `min(count, remaining)` re-evaluated per copy;
  `give_insane_outcast_to_each_opponent` iterates opponents **clockwise from the
  current player** (seat order: current index +1, wrapping, skip current) per
  rulebook :355. Undefined stack (D6) or empty supply → grant nothing; the effect and
  the rest of the card still resolve. **No move-generation change**: injector effects
  remain playable at zero supply (the no-op is execution-side).

Python:
- `game_setup/market_setup.py`: `compute_special_stacks(deck_a_id, deck_b_id)` →
  demons-gated (`"demons" in {deck_a_id, deck_b_id}`), returns specs with counts
  loaded from the roster files (new helper, e.g. `load_special_stack_counts`); the
  insane entry carries its 30 from `data/decks/insane_outcast.json`.
  `MarketSetup.special_stacks` carries counts; `to_setup_data()` emits
  `special_stacks`. Remove/stop exporting `is_aberrations_in_market`
  (`game_setup/__init__.py:26-83`) after usages are gone.
- `game_setup/scenario_generation/rosters.py:83` and `bindings/scenario_search.py`:
  adapt to the new `special_stacks` shape.
- `data/decks/base_setup.json`: add the three-stack array.
- `engine_c/bindings/engine_bindings.py:178-183`: mirror `SetupDefinition` exactly
  (new fields at the same position — `GameDefinition` layout shifts); rebuild DLL.

## 4. Phase 1 — RED tests (write first, observe failing)

New `tests/c_engine/test_insane_outcast_supply.py` (uses `make_card_test_session`;
extend `tests/c_engine/card_test_helpers.py` with a `setup_data_json` passthrough —
`CEngine.initialize` already supports it):

| # | Test | Asserts |
|---|---|---|
| T1 | `test_give_insane_outcast_respects_supply_cap` | Pre-fill players' zones to 30 owned outcasts total; play injector (ghoul/demogorgon scenario) → zero new copies; the card's other effects still resolve |
| T2 | `test_give_insane_outcast_partial_grant_clockwise` | 29 owned; demogorgon (2/opponent) → grants allocate clockwise from current player; the last opponent in order gets the remainder/none (rulebook :355) |
| T3 | `test_return_paths_replenish_supply` | After `self_purge_to_supply`, devour, and promote of outcasts, remaining increases and a subsequent grant succeeds (extends `test_card_insane_outcast.py` coverage) |
| T4 | `test_special_stack_totals_read_from_setup_json` | Inline setup with non-standard `stack_total` (e.g. house_guard 3) → only 3 recruitable, 4th recruit move absent |
| T5 | `test_legacy_setup_without_special_stacks_falls_back` | Inline setup without the field → 15/15/30 observable via view remaining fields / recruit availability |
| T6 | `test_insane_stack_gated_on_demons_market` | Composed demons+X market: slot-102 recruit offered while supply > 0 (first time reachable); composed aberrations+X: not offered |

New `tests/test_market_setup.py` (data-level, no DLL):
`compute_special_stacks` demons gating + counts from rosters; `to_setup_data()`
emits `special_stacks`; `base_setup.json` declares all three matching the roster files.

Update `tests/test_card_scenario_market_policy.py::test_aberrations_gates_insane_outcast_slot`
→ demons gating (T7).

Regression controls (must stay green): `test_card_derro/ghoul/demogorgon/gibbering_mouther/myconid_*`,
`test_card_insane_outcast.py`, `test_deck_rosters.py`.

## 5. Phase 2 — GREEN implementation (ordered)

1. `state.h` structs (§ 3).
2. `loader.c` parse + legacy default table.
3. `helpers.c` lookups + `remaining_special_stack_count` signature.
4. Call sites `rules.c` / `helpers.c` / `view.c`; delete `is_aberrations_enabled`.
5. `actions.c` `give_insane_outcast` cap + clockwise iteration.
6. Python `market_setup.py` + `rosters.py` + `scenario_search.py` + `__init__.py` exports.
7. `data/decks/base_setup.json`.
8. `engine_bindings.py` struct mirror.
9. `just build-c` (DLL rebuild is mandatory before running Python tests).

## 6. Phase 3 — Validation battery

```
just build-c            # struct change + DLL rebuild
just test-c-python      # c_engine suite incl. new supply tests
just test               # full pytest (market policy, rosters, renderer, bindings)
just test-c             # C unit tests
just openspiel-test     # wrapper contract
ruff check .
just ismcts-quick       # smoke: slot-102 recruit moves appear in demons markets
just game-viewer        # manual smoke: remaining counts render from definition
```

## 7. Ledger / docs

- `docs/validation/findings.md`: file the new finding for the `give_insane_outcast`
  over-issuance per F-004 § 11's contingency ("`give_insane_outcast` does not respect
  its own 30-copy special-stack cap"), falsification test = T1, status
  **CONFIRMED — FIXED** with commit sha; keep F-004's own entry append-only.
- `docs/validation/verdict.md`: add the resolved entry per house process.
- Record the deferred follow-up (D3): tighten `_build_c_game_info` `min_utility`
  −50.0 → −30.0 + `test_utility_contract.py` T4 + ledger note that the T6
  direct-struct-surgery probe no longer represents reachable (legal-play) states.

## 8. Acceptance gates

| Gate | Threshold |
|---|---|
| G1 Cap | Legal play cannot create a 31st concurrent outcast game-wide; direct struct surgery still can (probe only, not legal play) |
| G2 No-op | Injector effect at empty/undefined supply resolves with zero granted; sibling effects on the same card still apply |
| G3 Order | Exhaustion allocates clockwise from the current player |
| G4 Data-driven | Custom `stack_total` in setup JSON honored; 15/15/30 appears **only** in the loader legacy fallback |
| G5 Gating | Demons-gated composed markets; base_setup declares all three stacks |
| G6 Suites | `just test`, `just test-c-python`, `just test-c`, `just openspiel-test` green (only the 3 pre-existing tolerated failures from f010/f011 reviews); `ruff check .` clean |

## 9. Risks

| Risk | Mitigation |
|---|---|
| ctypes struct desync (`SetupDefinition` layout shifts inside `GameDefinition`) | Mirror lands in the same change; rebuild + run binding tests first |
| Slot-102 recruit newly reachable in demons markets (cost 0) — larger action space for IS-MCTS | Rules-legal (rulebook :354-355); T6 locks it; `just ismcts-quick` smoke |
| Scenario replays owning ≥30 outcasts collectively (generated during the unbounded era) — grants become no-ops | Audit the 6 injector scenario tests first; adjust expectations only where the old behavior was itself the bug |
| Each-opponent order change (array order → clockwise from current) | Only observable under exhaustion; T2 covers |
| Legacy fallback keeps constants reachable | Documented (D2) for a future cleanup pass once all setups carry the field |
| Market-deck/row fallback in `remaining_special_stack_count` interacting with new totals | Semantics unchanged (base_setup priestess ×10 composes to 15 total: 10 market + 5 stack-derived); T5 sanity check |

## 10. Out of scope

`min_utility` −30.0 tightening (D3, separate pass); F-002/F-003/F-005/F-006/F-008/F-009/F-013;
`session.save` setup-path fidelity for combined-market games (existing limitation);
regenerating `data/scenarios/` artifacts.
