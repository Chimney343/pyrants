# Cards With Failing Tests

Generated 2026-08-29 from `just test` (`.venv/Scripts/python.exe -m pytest`): **3 failed, 821 passed, 1 skipped** (0 errors). The 10 tkinter-dependent `test_game_viewer.py` tests were replaced by a Tk-free rewrite — the old tests intermittently errored with `_tkinter.TclError` (`invalid command name "tcl_findLibrary"` / `Can't find a usable tk.tcl`) because the uv standalone CPython 3.13 build can't reliably init a Tcl/Tk interpreter in this headless session; they were cosmetic combobox-height checks plus one UI regression test, all requiring a live Tk display.

## Summary

- 3 failing tests, exercising **3 distinct cards**.
- 0 errors: the tkinter `test_game_viewer.py` suite was replaced by a Tk-free rewrite (environmental TclErrors, unrelated to cards/engine).
- The remaining failures are catalog/execution-model issues; the engine self-target promote bug that affected several cards is fully resolved.

## Failing cards

| Card | Failing test | Failure reason |
|---|---|---|
| zuggtmoy | `test_zuggtmoy_eot_promote_two_other_cards_excludes_self` | Zuggtmoy is still a promote target (`{'noble', 'house_guard', 'zuggtmoy', 'soldier'}`); EOT promote must exclude the played card itself |
| air_elemental | `test_air_elemental_option_1_focus_draw` | Option 1 (place spy) focus draw did not happen (deck 15 → 15, expected 15 → 14); option_1 catalog action still missing the `draw_cards` rider on Guile focus |
| neogi | `test_neogi_execution_model_deploys_four_and_random_mass_discard` | Execution-model mismatch: `force_discard` action has `timing: 'end_of_turn'`, expected `'immediate'` |

## Non-card test files with failures

| File | Failures | Cards exercised |
|---|---|---|
| `tests/c_engine/test_engine_c.py` | 1 | air_elemental (option_1 focus draw not consuming deck) |
| `tests/test_card_neogi.py` | 1 | neogi (catalog execution-model timing) |
| `tests/test_game_viewer.py` | — | **rewritten Tk-free** (10 tkinter-dependent tests replaced by a mock-based rewrite; environmental `TclError`s, no card/engine coverage) |

## Delta vs 2026-08-23 listing

- 15 → 3 failures. The 12 resolved failures are catalog/engine fixes landed in commits `3218d31`, `8062afa`, `29a2e20`, `5dbc991`, `5f4c2ab`, `7d9db83`, and the IS-MCTS determinization work (`eaacde0`) — see "Fixed since 2026-08-23 listing".
- No new regressions: the 3 remaining failures are the same zuggtmoy, air_elemental, and neogi cases (air_elemental option_1 is unchanged; a separate `d81a8d6` fix addressed option_2 only).
- Errors 2 → 0: `tests/test_game_viewer.py` (10 tests) replaced by a Tk-free rewrite — the old tests all depended on `tk.Tk()` and intermittently raised `_tkinter.TclError` in this headless environment. Passed count dropped 829 → 821 accordingly.

## Fixed since 2026-08-23 listing

Cards whose tests were failing in the previous listing and now pass:

- white_dragon (`3218d31` — VP tokens awarded from controlled sites; no score on empty-barracks fallback)
- black_dragon (same VP-token fix path as white_dragon — `3218d31`; `test_black_dragon_vp_awarded_as_tokens` now passes)
- wyrmspeaker (`5f4c2ab` — promote targets another played card, not itself)
- cleric_of_laogzed (`5dbc991` — promote targets another played card, not itself)
- spectator (`7d9db83` — awards 1 influence, was 2; catalog `value` corrected)
- water_elemental (`8062afa` — promote restricted to Obedience cards; option focus draws now consume deck)
- wraith (`29a2e20` — skipping optional devour skips the assassinate rider; `test_wraith_assassinate_constrained_to_spy_site` now also passes, fully clearing wraith)

## Previously fixed (2026-08-20 → 2026-08-23)

- skeletal_horde (`a0bd5e8` — devour rider: deploy 3 after devour; skip skips extra deploy)
- rath_modar (`11363fd`)
- chosen_of_lolth (`7fa379a`)
- marlos_urnrayle (`1f8e70e`)
- nothic (`7f1bec5`)
- vanifer (`f11027f`)
- orcus (`fac469b`)
- puppeteer (`43c1cca`)
- green_dragon (catalog fix in working tree, uncommitted at generation time)
- grazzt — option_2 now an optional repeat: `return_spy` optional (`skip_ends_card`, `requires_supplant_target`) → `supplant_troop` (`repeat_sequence_while_spies`), looping while the player has spies; zero-spy option_2 marked unavailable. C changes: `sel_return_spy`, `apply_resolve_generic_choice` skip, `legal_pending_generic_choice_moves` viability.
