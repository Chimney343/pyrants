# `/engine` (Python, canonical) → `/engine_c` (C, port) — Logical Diff Audit (Re-review)

## Scope

Re-audit `/engine_c` against `/engine` for **logical divergences** after the first implementation pass. Truth source: Python engine = correct. C must be a logical mirror (same observable game output for same inputs).

## Status Summary (after re-review)

| Finding | Status | Notes |
|---------|--------|-------|
| D1 — EoT effects stubbed | **FIXED ✓** | `apply_end_of_turn_effects` (`rules.c:456-499`) now implements `force_discard` + `scaled_vp`. |
| D8/D9 — ability_key/card_id arg swap | **FIXED ✓** | Move struct (`state.h:331-332`) now has both `card_id`+`ability_key`; dispatch (`rules.c:621-633`) passes both correctly. |
| D14 — mandatory promotions filtered by timing | **FIXED ✓** | `enter_end_of_turn` (`rules.c:506-516`) now promotes all non-optional non-deferred regardless of `timing`. |
| D26 — pending_generic clone | **FIXED ✓** | `engine_clone` (`state.c:172-186`) deep-copies pending_generic + option_ids arrays. |
| D10 — hand-discard ability cost | **STILL OPEN** | Expanded to 5 sub-issues (D10a–e). See below. |
| D12 — paid-ability effect_key override | **STILL OPEN** | `apply_activate_card_ability` still runs base card effect. |
| D15 — shuffle RNG parity | **NEW — HIGH** | C uses xoshiro256, Python uses Mersenne Twister. Same seed → different decks. |
| D14b — mandatory-promote played_cards guard | **NEW — LOW** | C promotes unconditionally; Python guards on `card_id in played_cards`. |
| D10e — ability_key hardcoded literal | **NEW — LOW** | C sets `ability_key = intern("paid_ability")`; Python uses card-defined key. |

## Open Critical Bugs (must fix)

### D10 — Paid-ability cost model (5 sub-issues)

Root cause: C `CardDefinition.effect_payload` is a flat `MetaEntry[]` (key→value string pairs). Python `effect_payload` is `dict[str, Any]` with a **nested** `paid_ability` sub-dict holding `cost.{power,influence,discard_count}`, `effect_key`, `effect_payload`. C's flat model cannot represent this nesting, so the runtime cannot locate paid-ability cost/override fields.

| Sub | Issue | C location | Python truth |
|-----|-------|-----------|--------------|
| D10a | `discard_count` cost never enforced. `apply_activate_card_ability` calls `pay_ability_cost(state, pid, card_id, NULL, 0)` — always 0 discards. | `rules.c:388` | `helpers.py:585-600` requires `len(discard_hand_indices) == discard_count` exactly, else `IllegalMoveError`. |
| D10b | `ability_cost_affordable` only checks the `cost` key EXISTS — returns 1 (affordable) unconditionally. Never validates power/influence/discard affordability. | `helpers.c:451-465` | Python `_ability_cost_affordable` actually verifies pool sufficiency. |
| D10c | `apply_activate_card_ability` ignores the return value of `pay_ability_cost`. If payment fails (returns -1), the ability still activates. | `rules.c:388` (no check) | Python raises `IllegalMoveError` from `_pay_ability_cost` before effect runs. |
| D10d | `pay_ability_cost` reads `power`/`influence` from the card's **main** `effect_payload` (flat), not from `paid_ability.cost`. If a gain_power card also has a paid ability, the main `power` value is misread as the ability cost. | `helpers.c:477-483` | Python reads `paid_ability["cost"]["power"]` (nested). |
| D10e | `apply_play_card` hardcodes `pending_ability->ability_key = intern("paid_ability")`. | `rules.c:300` | Python `rules.py:274` sets `ability_key = paid_ability.get("ability_key", paid_ability.get("effect_key", ""))`. |

**Net gameplay effect:** Cards with hand-discard paid-ability costs activate for free in C. Cards with unaffordable power/influence costs still activate. Cards whose paid-ability effect differs from the base effect run the wrong effect (see D12). Activate is always offered in `legal_moves` regardless of affordability.

### D12 — Paid-ability resolves base effect, not override

`apply_activate_card_ability` (`rules.c:393`) calls `apply_effect_with_wrappers(state, player_id, cd, card_id)` where `cd` is the **original catalog card** (pointer from `card_by_id_state`). Python `rules.py:516-523` clones the card definition with overridden `effect_key = paid_ability.effect_key` (or `ability_key` fallback) and `effect_payload = paid_ability.effect_payload`, then invokes the override.

**Net effect:** Every paid ability in C runs the card's main `effect_key` (e.g. `gain_power`) instead of the paid-ability effect. Combined with D10d (cost read from main payload), paid abilities are functionally broken for any card whose paid effect ≠ base effect.

### D15 — Shuffle RNG algorithm mismatch (HIGH)

- C `shuffle_deck` (`state.c:19-27`): seed = `(seed << 16) ^ counter` — **same seed formula** as Python.
- BUT C seeds a **xoshiro256** PRNG (`rng.c:14-21`, splitmix64 seeding). Python seeds Python's `random.Random` = **Mersenne Twister** (`state.py:819`).
- Both use Fisher-Yates, but `rng_randint` (`rng.c:41-44`, `lo + (int)(uniform * range)`) ≠ Python's `_randbelow` (rejection sampling).
- **Result:** identical `(seed, counter)` produces a different deck/market order in C vs Python. Replays, deterministic tests, and IS-MCTS determinization all diverge.
- Affects: initial deck shuffle, market shuffle, reshuffle-discard-into-deck, `engine_determinize`.

**Decision needed:** Is bit-identical shuffle parity a requirement for "logical mirror"? If yes → C must reimplement Python's Mersenne Twister + `_randbelow`. If no → document C's independent RNG contract and ensure no cross-engine replay/determinism assumption exists in tests.

### D14b — Mandatory-promote missing played_cards guard (LOW)

Python `_enter_end_of_turn` (`rules.py:626-628`) guards each mandatory promotion:
```python
if pending.card_id not in updated.players[updated.current_player_id].played_cards:
    continue
```
C `enter_end_of_turn` (`rules.c:507-515`) calls `promote_card(state, current_player_id, p->card_id)` unconditionally. If a mandatory promotion's `card_id` was removed from `played_cards` by a prior effect (rare), C calls `promote_card` on a possibly-absent card. Verify `promote_card` is a no-op when the card isn't in `played_cards`.

## Verified-Equivalent Findings (no action)

| # | Item | Verdict |
|---|------|---------|
| D2 | `site_control_owner` return-type/Sym comparison | Equivalent — returns leader Sym, compared as Sym. Tie→no owner both sides. |
| D3 | `is_total_control` spy check | Equivalent — both reject foreign spies. |
| D4 | Deploy empty-barracks fallback (+1 score) | Match (`rules.c:331` ≡ `rules.py:440`). |
| D5/D6/D7 | Phase transitions, round increment, setup completion | Match. |
| D13 | Deferred `repeat_while_targets` promotion | Match. |
| D19 | Return-own-spy rejection | Match. |
| D24 | Sym interning equality | Match. |
| D25 | Flat `card.actions` walk for EoT | Match (C now walks `cd->actions`, `rules.c:468`). |

## Minor / Data-Hygiene Diffs (low severity)

| # | Item | Notes |
|---|------|-------|
| D29 | `force_discard` / `scaled_vp` source_fragment matching | C uses `strcmp`/`strncmp` (no `.strip().lower()`). Python lowercases + strips. Diverges only if source_fragment has whitespace/mixed case. Verify data is canonical lowercase. |
| D30 | `engine_create_game` is a stub | `state.c:49-71` ignores `json_path`, returns minimal state. Only `engine_create_game_definition` does real setup. Confirm bindings use the definition-based constructor. |
| D31 | `pending_ability->resolved` field | Declared in `state.h:234` but never set/checked. Dead field. No logic impact. |

## Verification Plan (TDD — tests first, watch fail, then fix)

Per the TDD skill: each open bug gets a **failing test first**, then minimal fix. Use the Python engine as the oracle — fixtures built in Python, replayed through C via `engine_c/bindings/ce_api.py`, states diffed.

### Test 1 — D15 shuffle parity (decide scope first)
**If parity required:**
1. RED: fixture deck `[c0..c9]`, seed=42, counter=0. Assert C `shuffle_deck` output == Python `Random((42<<16)^0).shuffle` output. Watch fail (xoshiro256 ≠ MT).
2. GREEN: reimplement Python MT in C `rng.c`, match `random.Random.shuffle` int generation.
3. Cover: initial deck, market, reshuffle, determinization.

**If parity NOT required:** write a test asserting C's shuffle is deterministic (same seed → same output) and document the divergence. No cross-engine replay tests.

### Test 2 — D10a/b/c/d paid-ability affordability + discard
1. RED: load a card with `paid_ability.cost = {power: 2, discard_count: 1}`. Set player power=1. Assert `ActivateCardAbilityMove` NOT in C `legal_moves` (Python excludes it). Watch fail (C includes it — D10b).
2. RED: same card, power=2, hand has 1 card. Assert activating the ability discards 1 hand card to discard_pile in C. Watch fail (C discards 0 — D10a).
3. RED: card with `paid_ability.cost = {power: 5}`, player power=2. Assert C `apply(activate)` returns NULL / raises (Python raises `IllegalMoveError`). Watch fail (C activates anyway — D10c).
4. GREEN: fix `ability_cost_affordable` to check pool; thread `discard_count` from a paid-ability cost representation; check `pay_ability_cost` return in `apply_activate_card_ability`.
5. **Blocker:** requires extending C `CardDefinition` to represent nested `paid_ability` (D10d). Decide representation: either add dedicated `PaidAbility { cost_power, cost_influence, cost_discard, effect_key, effect_payload }` struct to `CardDefinition`, or a side-table keyed by card_id. Loader (`loader.c`) must populate it from JSON.

### Test 3 — D12 paid-ability effect override
1. RED: card with base `effect_key=gain_power, effect_payload={power:1}` and `paid_ability={effect_key: gain_influence, effect_payload:{influence:2}, cost:{power:1}}`. Activate the ability. Assert C resource_pool.influence += 2 (Python behavior). Watch fail (C runs gain_power — D12).
2. GREEN: in `apply_activate_card_ability`, build a temporary `CardDefinition` copy with overridden `effect_key`/`effect_payload` from the paid-ability fields (depends on D10d representation), pass that to `apply_effect_with_wrappers`.

### Test 4 — D10e ability_key provenance
1. RED: card with `paid_ability.ability_key = "shadow_strike"`. Play the card. Assert C `pending_ability.ability_key == intern("shadow_strike")`. Watch fail (C sets `"paid_ability"` literal).
2. GREEN: read ability_key from paid-ability representation in `apply_play_card` (`rules.c:300`).

### Test 5 — D14b mandatory-promote guard
1. RED: construct state with a mandatory EoT promotion whose `card_id` is NOT in `played_cards` (manually mutate). Call `enter_end_of_turn`. Assert C does not call `promote_card` on the absent card (or that `promote_card` is a safe no-op). Compare resulting state to Python.
2. GREEN: add `if (card_id in played_cards)` guard in `enter_end_of_turn` before `promote_card`, OR confirm `promote_card` already no-ops on absent cards and document.

## Open Questions for User

1. **D15 RNG parity:** Is bit-identical shuffle parity with Python required, or is an independent (but deterministic) C RNG acceptable? This determines whether D15 is a HIGH-severity blocker or a documentation task.
2. **D10d representation:** Approve adding a dedicated `PaidAbility` struct to `CardDefinition` (cleanest) vs. a side-table. The flat `MetaEntry[]` cannot represent the nested paid-ability dict.
3. **D10e ability_key:** Confirm whether the C engine needs to match Python's card-defined `ability_key` contract (needed for cross-engine move replay) or whether the internal `"paid_ability"` literal is acceptable as long as C is self-consistent.

## Out of Scope

- Bindings Python (`engine_c/bindings/*.py`) — separate audit.
- C tests under `engine_c/tests/` — left to user.
- Build artefacts (`.obj`, `.dll`, `.exe`).
- cJSON loader (`engine_c/cJSON.c`) — third-party.
- `loader.c` JSON→struct mapping — relevant only once D10d representation is decided; re-audit after.

## Files to Change (post-approval)

| File | Change |
|------|--------|
| `engine_c/state.h` | Add `PaidAbility` struct to `CardDefinition`; add `discard_hand_indices` to Move activate_ability union (D10d, D10a). |
| `engine_c/loader.c` | Populate `PaidAbility` from JSON `effect_payload.paid_ability`. |
| `engine_c/helpers.c` | Fix `ability_cost_affordable` (D10b); fix `pay_ability_cost` to read from `PaidAbility.cost` (D10d). |
| `engine_c/rules.c` | `apply_activate_card_ability`: check `pay_ability_cost` return (D10c); build override `CardDefinition` (D12); set card-defined `ability_key` (D10e); add played_cards guard in `enter_end_of_turn` (D14b). |
| `engine_c/rng.c` | (If D15 parity required) reimplement Python Mersenne Twister + `_randbelow`. |
| `engine_c/moves.c` | `make_activate_ability_move`: accept `discard_hand_indices` (D10a). |
| `tests/` | New cross-engine parity tests (Tests 1–5 above). |
