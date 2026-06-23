# Plan: Collapse redundant `source_fragment` values in `catalog.json`

## Problem

`data/cards/catalog.json` contains **100 distinct `source_fragment` values** across 125 cards.
Of these, only **~15 are actually read by name** in the C engine (`engine_c/`). The remaining ~85
are pure documentary labels — the C engine never dispatches on them, behavior is determined
entirely by `op` and `metadata`.

Evidence of the small dispatched set (every `strcmp(sf, "...")` in the C engine):

| C engine file | source_fragment values checked by name |
|---------------|----------------------------------------|
| `engine_c/generic_runtime.c:131-135` | `local_discard`, `conditional_owner_discard`, `end_of_turn_mass_discard`, `mass_discard`, `on_opponent_discard_punish` |
| `engine_c/generic_runtime.c:142-143` | `promote_top_of_deck`, `threshold_self_promote` |
| `engine_c/actions.c:326, 336` | `promote_top_of_deck`, `threshold_self_promote` |
| `engine_c/actions.c:472, 477` | `play_from_inner_circle_without_removal`, `play` |
| `engine_c/selection.c:254` | `targeted_discard` |
| `engine_c/selection.c:391, 404` | `play_from_inner_circle_without_removal`, `play` |
| `engine_c/helpers.c:227-231` | `scaled_vp`, `scaled_vp_from_white_trophies`, `scaled_vp_from_trophies`, `scaled_vp_from_controlled_sites`, `scaled_vp_from_promoted_cards` |
| `engine_c/rules.c:496` | `end_of_turn_mass_discard` |

The other ~85 are read into the C `Action` struct but never inspected. They are labels that
travel along with the action for the benefit of humans reading the JSON, the catalog audit
script, and downstream tooling.

## Collateral readers (must be kept in sync)

| File | What it reads | Impact |
|------|---------------|--------|
| `scripts/catalog_audit.py:35-46, 47-53, 54-55, 127, 133, 153-161, 461, 608, 615` | `source_fragment` strings (allowlist sets + substring search `("anywhere", "unrestricted")`) | Will need allowlist updates if Medium/Aggressive scope chosen |
| `scripts/generate_first_deck_artifacts.py:652, 658, 681, 699, 743-2135` | `source_fragment` values are *written* into generated deck artifacts | These are generator output, not source-of-truth — fine to leave or update |
| `tests/test_card_neogi.py:29` | asserts `"end_of_turn_mass_discard"` | OK — value is preserved in all scopes |
| `tests/legacy_engine/test_rules_cards_n_z.py:306` | asserts `"end_of_turn_mass_discard"` | OK — value is preserved in all scopes |
| `tests/legacy_engine/test_generic_interpreter.py:253, 437, 467, 561, 1092, 1119, 1145, 1172, 1186, 1241, 1287` | Builds synthetic actions with `source_fragment=...` (e.g. `devour_hand`, `scaled_vp`, `play`, `play_from_inner_circle_without_removal`, `single_promote_from_multiple_zones`, `promote_from_discard`, `threshold_self_promote`) | These test the C engine, so the *dispatched* values must keep their names. The test file is independent of `catalog.json` content, so no edit needed. |

## Three scope options (pick one)

### Option A — Conservative: remove pure-noise fragments only

**What changes:** ~15 of the 100 values are set to `""` (empty string) because they are
neither dispatched by the C engine nor referenced by `catalog_audit.py` allowlists.
**Estimated actions affected:** ~30 (every action using one of the noise values).

Pure-noise values identified (not in any of the dispatch lists or audit allowlists above):

```
hand_devour, devour_from_hand, self_devour, devour, optional_devour_market_card,
optional_market_devour, optional_self_devour, devour_market_card_and_self_replace,
inner_circle_devour, take_from_devour_pile, draw, draw_cards, focus_draw,
on_opponent_discard_draw, on_opponent_discard_punish (NOTE: this IS dispatched — keep),
mill_deck, gain_4_power, gain_power, gain_influence, gain_power_and_influence,
gain_power_from_devour, focus_gain_power, focus_influence_bonus, focus_power_bonus,
conditional_influence_from_promoted_cards, conditional_influence_if_enemy_troop_present,
conditional_power_from_trophies, conditional_power_if_enemy_troop_present,
conditional_power_if_spy_present, conditional_owner_discard (DISPATCHED — keep),
scaled_power_from_trophy_hall, give_negative_card, give_negative_card_to_each_opponent,
give_insane_outcast_to_player_with_presence_at_deployed_site, move_enemy_troop,
move_enemy_troops, return_units, return_other_player_unit, return_unit, return_enemy_unit,
return_spy, return_own_spy, return_enemy_spy, return_spy_draw, return_spy_for_cards,
return_spy_for_influence, return_spy_for_influence_with_focus_bonus,
return_spy_for_power, return_spy_for_power_and_influence, return_spy_for_site_supplant,
return_spy_to_recruit_multiple_low_cost_cards, redeploy_captured_units, extra_deploy,
redeploy_captured_units, focus_spy, focus_deploy_troops, focus_spy, assassinate,
assassinate_troop, assassinate_there, assassinate_step_1, assassinate_step_2,
assassinate_step_3, assassinate_white_troop, assassinate_white_troop_step_1,
assassinate_white_troop_step_2, repeated_white_troop_assassinate,
repeated_white_troop_assassinate_by_controlled_sites, white_troop_assassinate,
triggered_promote, triggered_promote_aspect_filtered, triggered_multi_promote,
triggered_multi_promote_by_tag, promote_from_discard, promote_top_of_deck (DISPATCHED),
single_promote_from_multiple_zones, threshold_self_promote (DISPATCHED),
recruit_negative_card, recruit_aspect_filtered_card_by_cost, mass_negative_recruit,
supplant, supplant_white_troop, supplant_white_troop_anywhere, multi_supplant,
mass_supplant_white, gain_influence_per_troop_removed_by_effect, self_purge_to_supply,
self_devour_multi_white_assassinate_single_site, select_site, play (DISPATCHED),
play_from_inner_circle_without_removal (DISPATCHED)
```

**Files touched:** `data/cards/catalog.json` only.  
**Audit/test impact:** Zero. The audit allowlists and the C-engine tests reference the ~15
dispatched values which are kept intact.  
**Risk:** Lowest. Some human-readable labels disappear from the JSON.

### Option B — Medium: collapse aliases into a canonical vocabulary

**What changes:** Apply Option A, plus merge groups of values that are aliases of each other
(identical C-engine + audit behavior) into one canonical name per group.

Proposed canonical group table:

| Canonical (kept) | Aliases collapsed → canonical | Total usages |
|------------------|-------------------------------|--------------|
| `place_spy` | `spy`, `spy_place`, `place_spy_step_1`, `place_spy_step_2`, `focus_spy` | 68 |
| `deploy_troops` | `deploy`, `deploy_troop`, `deploy_troops_step_1/2/3`, `focus_deploy_troops`, `deploy_troops_with_focus_draw`, `extra_deploy`, `redeploy_captured_units` | 46 |
| `gain_resource` | `gain_power`, `gain_influence`, `gain_power_and_influence`, `gain_4_power`, `focus_gain_power`, `gain_power_from_devour`, `focus_influence_bonus`, `focus_power_bonus`, `conditional_influence_from_promoted_cards`, `conditional_influence_if_enemy_troop_present`, `conditional_power_from_trophies`, `conditional_power_if_enemy_troop_present`, `conditional_power_if_spy_present`, `gain_influence_per_troop_removed_by_effect`, `scaled_power_from_trophy_hall` | ~135 |
| `draw_cards` | `draw`, `draw_cards`, `focus_draw`, `on_opponent_discard_draw` | ~25 |
| `assassinate_troop` | `assassinate`, `assassinate_troop`, `assassinate_there`, `assassinate_step_1/2/3`, `assassinate_white_troop`, `assassinate_white_troop_step_1/2`, `repeated_white_troop_assassinate`, `repeated_white_troop_assassinate_by_controlled_sites`, `white_troop_assassinate` | ~62 |
| `return_spy` | `return_spy`, `return_own_spy`, `return_enemy_spy`, `return_spy_draw`, `return_spy_for_cards`, `return_spy_for_influence`, `return_spy_for_influence_with_focus_bonus`, `return_spy_for_power`, `return_spy_for_power_and_influence`, `return_spy_for_site_supplant`, `return_spy_to_recruit_multiple_low_cost_cards` | ~36 |
| `return_unit` | `return_unit`, `return_units`, `return_enemy_unit`, `return_other_player_unit` | ~16 |
| `devour` (already `op=devour_cost`) | `hand_devour`, `devour_from_hand`, `self_devour`, `devour`, `optional_devour_market_card`, `optional_market_devour`, `optional_self_devour`, `devour_market_card_and_self_replace`, `inner_circle_devour`, `take_from_devour_pile`, `self_devour_multi_white_assassinate_single_site` | ~46 |
| `force_discard` (op) + preserved dispatched fragments | collapses except the 5 C-dispatched + `targeted_discard` | ~14 - 7 = 7 |
| `supplant_troop` (op) | `supplant`, `supplant_white_troop`, `supplant_white_troop_anywhere`, `multi_supplant`, `mass_supplant_white` | ~32 |
| `move_troop` (op) | `move_enemy_troop`, `move_enemy_troops` | 6 |
| `recruit_card` (op) | `recruit_aspect_filtered_card_by_cost`, `recruit_negative_card`, `mass_negative_recruit` | 12 |
| `custom_effect` (op) + preserved `effect_kind` | `give_negative_card`, `give_negative_card_to_each_opponent`, `give_insane_outcast_to_…`, `self_purge_to_supply`, `select_site` | ~12 |
| `promote_card` (op) + preserved dispatched fragments | `triggered_promote`, `triggered_promote_aspect_filtered`, `triggered_multi_promote`, `triggered_multi_promote_by_tag`, `promote_from_discard`, `single_promote_from_multiple_zones` | ~50 |
| `grant_vp` (op) | (the 5 `scaled_vp*` keep their names per dispatch table) | 0 new |

Result: ~100 distinct `source_fragment` values → ~20 (15 dispatched + canonical group names).

**Files touched:** `data/cards/catalog.json` (all action source_fragments rewritten).
**Audit impact:** `scripts/catalog_audit.py` allowlists must be updated:
- `SUPPORTED_IMMEDIATE_PROMOTE_FRAGMENTS` → keep `promote_top_of_deck`, `threshold_self_promote`, `promote_from_discard`, `single_promote_from_multiple_zones` (all in dispatched or alias group).
- `SUPPORTED_END_OF_TURN_PROMOTE_FRAGMENTS` → keep `triggered_promote`, `triggered_promote_aspect_filtered`, `triggered_multi_promote`, `triggered_multi_promote_by_tag` (also via alias group).
- `SCALED_VP_SOURCE_FRAGMENTS` → unchanged.
- Line 133 `play` / `play_from_inner_circle_without_removal` → unchanged.
- Line 158 `ANYWHERE_SOURCE_TOKENS` substring check on `anywhere`/`unrestricted` — **the only
  real risk**: the substring search would break if `supplant_white_troop_anywhere` is renamed
  to plain `supplant_troop` since "anywhere" is no longer in the name. Either (a) keep the
  suffix in the canonical name for that group (e.g. `supplant_troop_anywhere` for the
  superset), or (b) replace the substring check with a more explicit metadata flag check.
**Test impact:** None (tests only assert the ~15 dispatched values).  
**Risk:** Medium — audit script needs a small refactor on the anywhere-detection path.

### Option C — Aggressive: Option B + rename the field itself

Apply Option B, then rename `source_fragment` → `effect_label` (or `effect_variant`) to
better reflect that the field is a documentary/audit label, not a code-dispatch key.

**Files touched (in addition to Option B):**
- `engine_c/loader.c:115` — field name read
- `engine_c/state.h:67` — struct field name `Sym source_fragment;`
- `engine_c/generic_runtime.c:71, 130, 141, 344, 379, 422, 466, 619, 644`
- `engine_c/rules.c:493`
- `engine_c/selection.c:251, 390`
- `engine_c/actions.c:325, 468`
- `engine_c/helpers.c:215`
- `engine_c/tests/test_generic_actions.c:16, 30, 57, 96`
- `engine_c/bindings/engine_bindings.py:89` — Python-facing field name
- `scripts/catalog_audit.py:127, 133, 153-161, 461, 608, 615`
- `scripts/generate_first_deck_artifacts.py` (string literals in 60+ generated cards)
- `data/cards/catalog.json` (every action)
- `data/scenarios/*.json` — if they embed `source_fragment` (grep confirmed: **no scenarios reference it**, so safe).
- Tests that build actions: `tests/legacy_engine/test_generic_interpreter.py:22, 34, 253, 437, 467, 561, 1092, 1119, 1145, 1172, 1186, 1208, 1241, 1287`

**Rebuild required:** `just build-c` to recompile `engine_c.dll`.  
**Test impact:** tests need field renames (10+ sites in `test_generic_interpreter.py`).  
**Risk:** Highest. Touches 30+ files, requires rebuild, more diff noise. Worth it only if the
field is going to keep growing in confusion.

## Recommendation

**Option B (Medium)**. It gives the bulk of the cleanup without the field-rename blast
radius. The audit script's `ANYWHERE_SOURCE_TOKENS` substring check is the one wrinkle to
handle explicitly — propose handling it by (a) keeping the `*_anywhere` suffix as part of
the canonical name for supplant/assassinate, OR (b) replacing the substring check with a
proper `metadata.unrestricted_target: true` flag.

## Execution steps (for whichever option is chosen)

1. **Confirm the chosen option with the user.**
2. If Option B/C: update `scripts/catalog_audit.py` allowlists first (this is the only
   in-tree change to non-JSON files outside Option C's C-engine rename).
3. Build the field-rename table for `catalog.json` (old value → new value).
4. Apply the renames to `catalog.json` using a single-pass script (preserve indentation;
   use a small Python transformer script, not manual edits, to avoid line drift in 14k
   lines of JSON).
5. **Re-validate:** run
   - `just build-c` (rebuild the C engine — confirms `loader.c` still parses the file)
   - `just test-c-python` (C-binding tests)
   - `just test` (Python pytest, esp. `test_card_neogi.py:29` and
     `test_rules_cards_n_z.py:306` which assert specific `source_fragment` values)
   - `python scripts/catalog_audit.py` (or whatever the audit invocation is)
   - `ruff check .`
6. If any test fails because it pinned a value that was collapsed, the test should be
   updated to the new canonical name (these are mechanical changes, not logic changes).
7. If Option C was chosen: re-run C-engine unit tests
   (`engine_c/tests/test_generic_actions.c` etc.) after the field rename.

## Open question for the user

- Which option (A / B / C)?
- For Option B: keep `*_anywhere` suffix as part of canonical supplant/assassinate names, or
  switch the audit's "anywhere" detection to a metadata flag?
- Are the deck-artifact generator outputs (`scripts/generate_first_deck_artifacts.py`)
  considered source of truth, or can they be regenerated from the cleaned catalog? (If they
  are independent outputs, the generator's hard-coded strings can stay until regenerated.)
