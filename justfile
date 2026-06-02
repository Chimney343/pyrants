set shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-Command"]

python := ".venv/Scripts/python.exe"

board-creator:
    & {{python}} -m interface.board_creator

board-creator-open board="data/boards/tyrants_of_the_underdark.json" layout="data/layouts/tyrants_of_the_underdark_layout.json":
    & {{python}} -m interface.board_creator --board-path {{board}} --layout-path {{layout}}

test:
    & {{python}} -m pytest -q

game-simulate players="p1,p2" seed="1" policy="first" policy_seed="1" max_steps="1" board="data/boards/base_game.json" card="data/cards/catalog.json" setup="data/decks/base_setup.json" replay="artifacts/replay.json":
    & {{python}} -m game_simulation --players {{players}} --seed {{seed}} --policy {{policy}} --policy-seed {{policy_seed}} --max-steps {{max_steps}} --board-path {{board}} --card-path {{card}} --setup-path {{setup}} --replay-log-path {{replay}}

game-viewer players="p1,p2" board="data/boards/tyrants_of_the_underdark.json" layout="data/layouts/tyrants_of_the_underdark_layout.json" card="data/cards/catalog.json" setup="data/decks/base_setup.json":
    & {{python}} -m interface.game_viewer --players {{players}} --board-path {{board}} --layout-path {{layout}} --card-path {{card}} --setup-path {{setup}}

replay-viewer replay="artifacts/replay.json" board="data/boards/tyrants_of_the_underdark.json" layout="data/layouts/tyrants_of_the_underdark_layout.json":
    & {{python}} -m interface.replay_viewer --replay-log-path {{replay}} --board-path {{board}} --layout-path {{layout}}

game-simulate-help:
    & {{python}} -m game_simulation --help

game-viewer-help:
    & {{python}} -m interface.game_viewer --help

replay-viewer-help:
    & {{python}} -m interface.replay_viewer --help

card-stuck-check rosters="data/decks/first_deck_rosters.json" board="data/boards/base_game.json" card="data/cards/catalog.json" setup="data/decks/base_setup.json" seed="7" seed_count="1" max_steps="120" json_out="artifacts/card_stuck_report.json":
    & {{python}} scripts/check_roster_card_stuck_states.py --rosters-path {{rosters}} --board-path {{board}} --card-path {{card}} --setup-path {{setup}} --seed {{seed}} --seed-count {{seed_count}} --max-steps {{max_steps}} --json-out {{json_out}}

card-stuck-check-ci rosters="data/decks/first_deck_rosters.json" board="data/boards/base_game.json" card="data/cards/catalog.json" setup="data/decks/base_setup.json" seed="7" seed_count="1" max_steps="120" expected_blocked="" json_out="artifacts/card_stuck_report.json":
    & {{python}} scripts/check_roster_card_stuck_states.py --rosters-path {{rosters}} --board-path {{board}} --card-path {{card}} --setup-path {{setup}} --seed {{seed}} --seed-count {{seed_count}} --max-steps {{max_steps}} --json-out {{json_out}} --ci --expected-blocked-cards {{expected_blocked}}
