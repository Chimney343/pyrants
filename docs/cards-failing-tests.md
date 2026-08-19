# Cards With Failing Tests

Generated 2026-08-19 from `just test` (`.venv/Scripts/python.exe -m pytest -q`): **48 failed, 1 error**.

## Summary

- 19 `test_card_*.py` files have at least one failing test.
- 2 non-card test files fail on cards too: `test_engine_c.py`, `test_generic_actions.py`.
- 20 distinct cards have at least one failing test.

## Failing cards

| Card | Failing tests |
|---|---|
| rath_modar | 5 |
| green_dragon | 4 |
| chosen_of_lolth | 3 |
| marlos_urnrayle | 3 |
| vanifer | 3 |
| nothic | 2 |
| orcus | 2 |
| puppeteer | 2 |
| skeletal_horde | 2 |
| spectator | 2 |
| white_dragon | 2 |
| wraith | 2 |
| wyrmspeaker | 2 |
| black_dragon | 1 |
| cleric_of_laogzed | 1 |
| grazzt | 1 |
| neogi | 1 |
| water_elemental | 1 |
| zuggtmoy | 1 |
| air_elemental | 1 |

## Non-card test files with failures

| File | Failing tests | Cards exercised |
|---|---|---|
| `tests/c_engine/test_engine_c.py` | 2 | air_elemental, water_elemental |
| `tests/c_engine/test_generic_actions.py` | 3 | rath_modar (draw_cards) |
| `tests/test_deck_rosters.py` | 1 | — (deck roster totals) |
| `tests/test_effect_families_schema.py` | 2 | — (catalog schema) |
| `tests/test_game_viewer.py` | 1 (error) | — (tkinter TclError, env) |

Including air_elemental (covered only via `test_engine_c.py`) and water_elemental (also one failure in `test_engine_c.py`), that is **20 distinct cards** with at least one failing test.
