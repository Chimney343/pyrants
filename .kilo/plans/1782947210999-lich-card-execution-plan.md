# Lich card execution plan

## Goal
Make `Lich` (catalog `data/cards/catalog.json`, card_id `lich`) execute the
behavior agreed with the human reviewer:

> Place a spy. If another player has a troop at the chosen site, choose 2
> trophies from **that same opponent's** trophy hall and deploy them
> anywhere on the board, regardless of presence.

> **Rule correction (2026-08-15):** the human confirmed the troops deploy
> anywhere, ignoring presence — matching `rules_text` ("regardless of
> presence"). The original "requires presence" reading below was wrong.

If no enemy troop is at the chosen site, the second clause is skipped. If
multiple enemies have a troop at the site, the player picks one of them, then
takes 2 trophies from that single opponent. Both trophies must come from the
same opponent.

## Current state (where it is wrong)

| Layer | Problem |
|-------|---------|
| Catalog `rules_text` / `notes` | Says "troop there". The human confirmed "troop" is the correct trigger (was a typo in our earlier exchange; do not change to "spy"). |
| Catalog `execution_model` | Only `place_spy` + a single `deploy_troops`. No conditional gate, no trophy source, no scoping to a single opponent, no repeat. |
| C engine | No applier / selection handler for the needed flow. Closest siblings (`steal_from_selected_trophy`, `select_trophy_hall`) either (a) enumerate every player's trophies or (b) ignore presence. Neither matches Lich. |
| Scenario `114_seed_4_lich.json` | Already generated. May need regeneration after the engine fix to seed a state with two enemies + spy site. |
| Tests | None for Lich in `tests/`. |

## Fix layers (reuse-before-write)

### 1. Catalog — `data/cards/catalog.json` (card_id `lich`)

Replace the two-action `sequence` with a `sequence` that mirrors `Orcus`'s
shape plus our new effect kinds. Draft:

```jsonc
"execution_model": {
  "kind": "sequence",
  "actions": [
    {
      "action_id": "action_1",
      "op": "place_spy",
      "target_scope": "board_site",
      "timing": "immediate",
      "optional": false,
      "quantity": { "kind": "fixed", "value": 1 },
      "filters": [],
      "source_fragment": "place_spy",
      "metadata": {}
    },
    {
      "action_id": "action_2",
      "op": "custom_effect",
      "target_scope": "self",
      "timing": "immediate",
      "optional": true,
      "quantity": { "kind": "fixed", "value": 1 },
      "filters": [],
      "source_fragment": "lich_select_target_player",
      "metadata": {
        "effect_kind": "lich_select_target_player",
        "gate": "selected_node_has_other_player_troop",
        "skip_advance_to_index": "3"
      }
    },
    {
      "action_id": "action_3",
      "op": "custom_effect",
      "target_scope": "self",
      "timing": "immediate",
      "optional": false,
      "quantity": { "kind": "fixed", "value": 1 },
      "filters": [],
      "source_fragment": "lich_take_trophy",
      "metadata": {
        "effect_kind": "deploy_from_trophy_hall_with_presence",
        "trophy_source_player": "lich_target_player",
        "trophy_color_filter": "any"
      }
    },
    {
      "action_id": "action_4",
      "op": "custom_effect",
      "target_scope": "self",
      "timing": "immediate",
      "optional": false,
      "quantity": { "kind": "fixed", "value": 1 },
      "filters": [],
      "source_fragment": "lich_take_trophy",
      "metadata": {
        "effect_kind": "deploy_from_trophy_hall_with_presence",
        "trophy_source_player": "lich_target_player",
        "trophy_color_filter": "any"
      }
    }
  ]
}
```

Notes:
- `action_2` is `optional: true` with `gate: selected_node_has_other_player_troop`. When the gate is false, the engine skips it (via the new `action_gate_met` predicate — see C engine section) and `skip_advance_to_index: 3` jumps to the end of the trophy phase. Same `skip_advance_to_index` mechanism already used by Orcus / Mummy Lord.
- `actions` (the duplicate flattened list the runtime also reads) must mirror the same shape.
- `global_conditions` keeps `conditional_gate` (already present).
- `state_contract.writes` adds `player.trophy_hall` (taken from) and keeps `board.troop_slots`, `board.spies`, `player.spies_available`.

### 2. C engine — extend the generic interpreter

Three additions, all in existing files. No new files; no per-card special case.

#### 2a. New gate predicate — `engine_c/generic_runtime.c`
Add `static bool action_gate_met(state, player_id, card, action)` that looks
at `action.metadata.gate`:
- `selected_node_has_other_player_troop` → resolve the last-selected node
  from `pending_generic.last_selection[*].target_node_id` (i.e. the spy
  site) and check `has_other_player_troop(state, player_id, node)`.
- Unknown gate names → return `true` (fail-open; existing focus gate uses
  the same pattern).

Wire it into `auto_resolve_pending_generic` right after the focus check
(~line 335):
```c
if (!action_gate_met(state, player_id, card, action)) {
    int skip_to = -1;
    /* honour existing skip_advance_to_index metadata for optional skip */
    for (...) { ... }
    if (skip_to >= 0) p->next_action_index = skip_to;
    else p->next_action_index++;
    continue;
}
```

This keeps the gate generic for any future card.

#### 2b. New effect_kind `lich_select_target_player` — `engine_c/selection.c` and `engine_c/actions.c`
- **Selection handler** (extend `sel_custom_effect`): if
  `effect_kind == "lich_select_target_player"`, enumerate distinct enemy
  player ids found in the **last-selected node's troop slots** (the spy
  site, looked up the same way `requires_last_selected_node` does). Emit
  one `MOVE_RESOLVE_GENERIC` per distinct enemy, `action_id = enemy_pid`.
  If zero enemies, emit zero moves; the parent gate will skip action_2
  anyway, but emit nothing so the engine knows to advance.
- **Applier** (in `apply_custom_effect` in `actions.c`): on
  `lich_select_target_player`, store `pending.last_selection.source_player_id = chosen_pid`
  (or extend pending with a new key `target_owner_id` — whichever fits the
  existing schema; `source_player_id` already exists for Orcus). Reuse the
  same selection-key mechanism; no new struct field needed.

#### 2c. New effect_kind `deploy_from_trophy_hall_with_presence` — `engine_c/selection.c` and `engine_c/actions.c`
- **Selection handler** (extend `sel_custom_effect`):
  1. Read `trophy_source_player` from action metadata. If it equals
     `"lich_target_player"`, use the stored
     `pending.last_selection.source_player_id` (set by step 2b).
  2. For that player, enumerate their trophy hall slots (no white-only
     filter by default; respect `trophy_color_filter` if set: `any` |
     `white_only` | `player_only`).
  3. For each offered trophy, emit a sub-target list of board sites where
     the acting player has presence **and** the chosen slot is empty.
     Encode the chosen site + slot as `target_id` (same shape as
     `steal_from_selected_trophy`'s `"sp:ti:nid:slot"` so the applier can
     parse it uniformly).
- **Applier** (in `apply_custom_effect`): mirror `steal_from_selected_trophy`
  (actions.c:706), but additionally verify
  `has_presence(state, player_id, target_node_id)` before placing the
  trophy. Same removal-from-trophy-hall + place-on-board semantics.

These three additions are the **only** C-engine changes.

### 3. Scenario — `data/scenarios/batch_card_generation/114_seed_4_lich.json`

Keep the file but regenerate it after the engine fix so it has a clean
precondition for testing both branches:
- An enemy troop at the chosen spy site (so the gate passes).
- ≥2 trophies in that enemy player's trophy hall (mix of player-color and
  white).
- The acting player (`p4`) has presence at least one empty site.
- A control branch also exists in the scenario file (or a second scenario)
  with no enemy troop at the spy site, to exercise the gate-skip path.

Regenerate via:
```bash
just generate-card-scenario card_id=lich
```
If `ensure_card_scenario_c` does not produce the desired precondition, edit
the file by hand and commit it next to the engine fix.

### 4. Tests — `tests/`

Add `tests/test_card_lich.py` (style mirrors `tests/test_engine_c.py` /
`tests/test_first_ten_cards.py`). Drive via `CSession` + `CEngine` /
`PlayCardMove` + `ResolveGenericChoiceMove`. Cases:

1. `test_lich_no_enemy_troop_at_spy_site_skips_trophy_phase` — place spy at a
   site with no other troop; assert board has 1 spy added, zero trophies
   moved, zero troops placed.
2. `test_lich_single_enemy_troop_takes_two_trophies_to_presence_site` —
   spy site has one enemy troop; that enemy has ≥2 trophies; acting player
   has presence at an empty site; after two `resolve_generic` picks, two
   trophies leave the enemy's trophy hall and land on the chosen board site;
   both trophies are owned by the same enemy.
3. `test_lich_multiple_enemies_pick_target_then_trophies` — spy site has
   troops from two different enemies; the move stream is
   `place_spy → lich_select_target_player(p_enemy_1) → trophy_1 →
   trophy_2`; assert trophies only come from `p_enemy_1`'s hall.
4. `test_lich_cannot_deploy_without_presence` — acting player lacks
   presence at every open site; selection handler offers no moves; engine
   skips the deploy rather than violating the rule.

Run after implementation:
```bash
just build-c
uv run pytest tests/test_card_lich.py -v
just test-c
ruff check .
```

### 5. Don't forget
- Rebuild C engine (`just build-c`) before any Python re-test.
- Keep `tests/test_engine_purity.py` green (no I/O in `engine_c/`).
- Do not touch the deprecated `engine/` Python port.
- Once human accepts the card in the GUI and the new tests pass, **stop**
  — this plan covers exactly one card.

## Out of scope
- Changing `rules_text` / `notes` wording (the human confirmed "troop" is the
  correct trigger; current text is fine).
- Renaming or refactoring `select_trophy_hall` / `steal_from_selected_trophy`
  — they're used by Orcus and Mummy Lord; leave them alone.
- Any UI changes to `interface/game_viewer.py` — the engine state is the
  source of truth; if the GUI mislabels anything after the fix, that's a
  separate card-execution review.

## Risks
- **Gate-skip regression.** If `skip_advance_to_index` is wrong, action_3/4
  could fire when the gate is false. Lock with test 1.
- **Presence leak.** If `deploy_from_trophy_hall_with_presence` forgets to
  re-check presence in the applier (only checks in the selection handler), a
  scripted state could still bypass it. Lock with test 4.
- **Multi-enemy scoping.** If `lich_select_target_player` enumerates sites
  instead of players, the player picks a site again. Lock with test 3.
- **Trophy color filter.** Lich accepts both player-color and white. If the
  filter accidentally restricts to one, test 2 with mixed trophies catches
  it.

## Definition of done
- [ ] Catalog entry matches the JSON draft above.
- [ ] Three C-engine additions implemented; `just build-c` clean.
- [ ] Scenario regenerated to cover both branches.
- [ ] Four pytest cases in `tests/test_card_lich.py` pass.
- [ ] `just test-c` passes.
- [ ] `ruff check .` clean.
- [ ] Human confirms behavior in the C-backend viewer on the regenerated
  scenario.