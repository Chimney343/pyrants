# Cards With Failing Tests

Generated 2026-08-23 from `just test` (`.venv/Scripts/python.exe -m pytest`): **15 failed, 726 passed, 1 skipped, 2 errors** (2 schema failures removed — see "Removed tests" below).

## Summary

- 8 `test_card_*.py` files have at least one failing test.
- 1 non-card test file fails on cards too: `test_engine_c.py`.
- 11 distinct cards have at least one failing test.

## Failing cards

| Card | Failing tests | Failure reason |
|---|---|---|
| white_dragon | `test_white_dragon_vp_tokens_from_controlled_sites`<br>`test_white_dragon_per_rounds_down` | Expected 2 VP tokens (4 controlled sites // 2), got `vp_tokens=0`; expected 1 VP token (3 controlled sites // 2), got `vp_tokens=0` — VP tokens never awarded |
| wyrmspeaker | `test_wyrmspeaker_eot_promote_mandatory_no_skip`<br>`test_wyrmspeaker_eot_no_other_played_card_skip_allowed` | Promote targets include self (`{'wyrmspeaker', 'noble'}`); with no other played card the `promote_card` option should not exist but does |
| spectator | `test_spectator_gains_two_power_and_one_influence`<br>`test_spectator_catalog_structure` | Gains 2 influence instead of 1; catalog entry has `{'kind': 'fixed', 'value': 2}` where `value: 1` expected |
| air_elemental | `test_air_elemental_option_1_focus_draw` | Option 1 focus draw did not happen (deck 15 -> 15, expected 15 -> 14) |
| black_dragon | `test_black_dragon_vp_awarded_as_tokens` | Expected 2 VP tokens (6 white trophies // 3), got `vp_tokens=0` — VP tokens never awarded |
| cleric_of_laogzed | `test_promote_cannot_target_self` | Cleric of Laogzed is a promote target, other targets `['noble']` |
| grazzt | `test_grazzt_option_2_repeats_for_each_spy` | Cycle 1: no return-spy moves produced, `labels=[]` |
| neogi | `test_neogi_execution_model_deploys_four_and_random_mass_discard` | Timing mismatch: `'end_of_turn'` instead of `'immediate'` |
| water_elemental | `test_water_elemental_deploys_two_troops_with_focus` | Focus draw did not happen (deck 3 -> 3, expected 3 -> 2) |
| wraith | `test_wraith_assassinate_constrained_to_spy_site` | Assassinate targets at non-spy site: `['site_gauntlgrym', 'site_menzoberranzan']` |
| zuggtmoy | `test_zuggtmoy_eot_promote_two_other_cards_excludes_self` | Zuggtmoy is a promote target (`{'zuggtmoy', 'house_guard', 'soldier', 'noble'}`) |

## Non-card test files with failures

| File | Failing tests | Cards exercised |
|---|---|---|
| `tests/c_engine/test_engine_c.py` | 2 | air_elemental, water_elemental (focus draws not consuming deck) |
| `tests/test_card_neogi.py` | 1 | neogi |
| `tests/test_game_viewer.py` | 2 (errors, flaky 1–3) | — (tkinter `TclError: invalid command name "tcl_findLibrary"`, env) |

## Removed tests

- `tests/test_effect_families_schema.py` (2 tests) — **deleted** on 2026-08-23. The file validated `data/cards/effect_families.json` + `.schema.json`, which were deliberately deleted in commit `956f603` as superseded artifacts; the test was orphaned and failing with `FileNotFoundError`. Not a card bug — a fixture gap.

Including air_elemental (covered only via `test_engine_c.py`) and water_elemental (also one failure in `test_card_water_elemental.py`), that is **11 distinct cards** with at least one failing test.

## Delta vs 2026-08-22 listing

- 17 → 15 failures: `test_effect_families_schema.py` (2) removed as an orphaned test for a deleted artifact (commit `956f603`).
- All 15 remaining failures are the same card-engine tests as before — no new regressions, no new fixes.
- Error count varies 1–3 across runs (`test_deck_a_box_height`, `test_deck_b_box_height`, `test_devoured_box_height`) due to tkinter environment flakiness; 2 observed in this run.

## Fixed since 2026-08-20 listing

Cards whose tests were failing in the previous listing and now pass:

- skeletal_horde (`a0bd5e8` — devour rider: deploy 3 after devour; skip skips extra deploy)
- rath_modar (`11363fd`)
- chosen_of_lolth (`7fa379a`)
- wraith partial (`29a2e20` — `test_wraith_skip_devour_no_assassinate`; one wraith test still fails)
- marlos_urnrayle (`1f8e70e`)
- nothic (`7f1bec5`)
- vanifer (`f11027f`)
- orcus (`fac469b`)
- puppeteer (`43c1cca`)
- green_dragon (catalog fix in working tree, uncommitted at generation time)
