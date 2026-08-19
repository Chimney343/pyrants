# Catalog execution_model & C engine op-handler map

This is the lookup table the validator skill points to when diagnosing a card.
Keep it in sync with `data/cards/*.json` and `engine_c/generic_runtime.c`.

## Catalog entry shape (`data/cards/*.json`)

Each card object has, among display fields (`card_id`, `name`, `cost`, `aspect`,
`deck_vp`, `inner_circle_vp`, `rules_text`, `notes`), an `execution_model`:

```jsonc
{
  "card_id": "aboleth",
  "execution_model": {
    "kind": "modal_choice",          // modal_choice | simple | ...
    "selection": "exactly_one",      // for modal_choice
    "options": [
      {
        "option_id": "option_1",
        "actions": [
          {
            "action_id": "option_1_action_1",
            "op": "place_spy",       // see op table below
            "target_scope": "board_site",
            "timing": "immediate",
            "optional": false,
            "quantity": { "kind": "fixed", "value": 1 },
            "filters": [],
            "source_fragment": "spy_place",
            "metadata": {}           // e.g. { "count_from": "spies_on_board" }
          }
        ]
      }
    ]
  }
}
```

Common `op` values seen in the catalog: `place_spy`, `draw_cards`,
`assassinate_troop`, `recruit`, `deploy_troop`, `gain_resources`,
`return_card`, `promote`, `destroy_troop`, `swap`, `reveal`, `force_discard`.
When a card misbehaves, the first question is always: **does the catalog
`op` for this action have a matching applier registered in the C engine?**

## C engine entry points (`engine_c/generic_runtime.c` / `.h`)

- `resolve_generic_execution(state, player_id, card, source_card_id)` — kicks off
  a card's execution_model from a `PlayCardMove`.
- `apply_generic_action(state, player_id, card, source_card_id, action,
  sel_keys, sel_vals, sel_count)` — dispatches one `CardAction` to its applier.
- `register_generic_actions()` — registers the `ActionApplier` function table
  keyed by op name. **This is where an unsupported op shows up as a no-op or
  NULL dispatch.**
- `register_selection_handlers()` — registers `SelectionGenerator` functions
  that produce legal target-selection moves per `target_scope` / filters.
- `legal_generic_target_selection_moves(...)` — what the GUI pulls to show
  clickable targets.
- `auto_resolve_pending_generic(state, player_id)` — auto-resolves forced/
  non-optional pending actions.
- `apply_resolve_generic_choice(state, move)` — applies a
  `ResolveGenericChoiceMove` (option pick or target selection).

Helpers worth reusing (don't reinvent): `resolve_action_count`,
`resolve_runtime_action_count` (reads `metadata.count_from`:
`controlled_sites` / `spies_on_board` / `assassinations_by_source_effect`),
`count_controlled_sites`, `card_by_id_gr`, `find_selection`,
`find_selection_int`. More in `engine_c/helpers.c` / `helpers.h`.

## Selection / pending state

`PendingGenericChoiceState` (in `engine_c/state.h`) carries the active
`CardAction`, accumulated `selection_keys`/`selection_values`, and
`counter_keys`/`counter_values` (used by effects that count across an
execution, e.g. assassinate-then-draw). If a multi-step card stalls, inspect
whether the pending state is being advanced/cleared by
`auto_resolve_pending_generic` and whether the selection handler is emitting
moves.

## How to find a sibling card that already works

For a given `op` or `target_scope`, grep the catalog for other cards using the
same op, then check `generic_runtime.c` for their applier. Example workflow:

1. `rg '"op": "place_spy"' data/cards/*.json` → list of cards using it.
2. `rg 'place_spy' engine_c/generic_runtime.c` → the applier + any
   scope-specific branching.
3. Pick the closest sibling (same scope, same quantity kind, similar filters)
   and mirror its handling for the broken card.

## GUI rendering path (what the human is looking at)

`interface/game_viewer.py` with `--engine c`:
- Loads a scenario via `CSession.load(path)` (File → Load, default dir
  `data/scenarios`).
- Builds the view with `engine_c.bindings.view.build_c_game_view(session)`.
- Legal targets come from the C engine's
  `legal_generic_target_selection_moves`; if the GUI shows no clickable
  target where one should exist, the bug is usually in the **selection
  handler**, not the renderer. If the renderer itself mislabels a value
  (wrong spy count, wrong VP), check `engine_c/view.c` / `describe.c` and
  the Python `game_view.py` projection.

## Test placement cheat-sheet

- Python behavior test against the **C engine**: `tests/test_engine_c.py`
  style — use `engine_c.bindings.session.CSession` +
  `engine_c.bindings.ce_api.CEngine`, drive with `PlayCardMove` /
  `ResolveGenericChoiceMove`, assert on `CState` projections.
- Python behavior test against the deprecated Python engine (only if the
  card is supposed to match across both): `tests/test_first_ten_cards.py`
  / `test_rules_cards_a_m.py` / `test_rules_cards_n_z.py` style.
- C-level test: `engine_c/tests/` or `engine_c/test_generic.c` — add a
  case, rebuild with `just build-c`, run with `just test-c`.
- Scenario generation / loading: `tests/test_generate_card_scenarios_c.py`
  uses `ensure_card_scenario_c` from `engine_c/bindings/scenario_search.py`.

## Binding API gotchas (learned from driving cards headless)

When you drive the C engine via `CSession` / `CMoveWrapper` to write a test,
the `resolve_generic` move shape is not symmetric — read the field carefully:

- **Option pick** (modal_choice): `action_id` = the option id
  (e.g. `"option_1"`), `target_id` = `None`, `selection_index` = 0.
- **Target selection** (place_spy / deploy / etc.): the chosen node id is in
  **`action_id`**, **not** `target_id` (`target_id` is `None` for site
  targets). `selection_index` = 0. So to find a target move for node
  `site_x`, match `move.move_type == "resolve_generic" and
  move.data["action_id"] == "site_x"`.

When inspecting the resulting state for assertions, use
`build_c_game_view(session)` and read:
- `view.board_nodes[i].spies` — tuple of player ids with a spy on that node
  (use to assert spies placed / removed).
- `view.board_nodes[i].troop_slots` — troop owner per slot (assassinate /
  deploy / destroy assertions).
- `view.player_summaries[j].spies_available`, `.barracks`, `.score`,
  `.hand_count`, `.deck_count` (resource / supply / draw assertions).
- `view.current_player_hand` / `current_player_discard` for draw / discard
  assertions.
- `view.resource_power` / `resource_influence` for resource-gain assertions.

The current player index is `state.player_ids.index(state.current_player_id)`;
`state.player_hand(idx)` returns the hand list.
