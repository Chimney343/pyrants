set shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-Command"]

python := ".venv/Scripts/python.exe"

board-creator:
    & {{python}} -m interface.board_creator

board-creator-open board="data/boards/tyrants_of_the_underdark.json" layout="data/layouts/tyrants_of_the_underdark_layout.json":
    & {{python}} -m interface.board_creator --board-path {{board}} --layout-path {{layout}}

test:
    & {{python}} -m pytest -q

game-simulate players="p1,p2,p3,p4" seed="1" policy="first" policy_seed="1" max_steps="10000" board="data/boards/base_game.json" card="data/cards/catalog.json" setup="data/decks/base_setup.json" replay="artifacts/replay.json":
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

card-stuck-check decks="data/decks" board="data/boards/base_game.json" card="data/cards/catalog.json" setup="data/decks/base_setup.json" seed="7" seed_count="1" max_steps="120" json_out="artifacts/card_stuck_report.json":
    & {{python}} scripts/check_roster_card_stuck_states.py --decks-dir {{decks}} --board-path {{board}} --card-path {{card}} --setup-path {{setup}} --seed {{seed}} --seed-count {{seed_count}} --max-steps {{max_steps}} --json-out {{json_out}}

card-stuck-check-ci decks="data/decks" board="data/boards/base_game.json" card="data/cards/catalog.json" setup="data/decks/base_setup.json" seed="7" seed_count="1" max_steps="120" expected_blocked="" json_out="artifacts/card_stuck_report.json":
    & {{python}} scripts/check_roster_card_stuck_states.py --decks-dir {{decks}} --board-path {{board}} --card-path {{card}} --setup-path {{setup}} --seed {{seed}} --seed-count {{seed_count}} --max-steps {{max_steps}} --json-out {{json_out}} --ci --expected-blocked-cards {{expected_blocked}}

generate-card-scenarios workers="1" seed="0" attempts="3" steps="1500":
    $sw = [System.Diagnostics.Stopwatch]::StartNew(); $outDir = "data/scenarios/batch_card_generation"; & {{python}} scripts/generate_card_scenarios.py --output-dir $outDir --base-seed {{seed}} --max-attempts {{attempts}} --max-steps {{steps}} --workers {{workers}}; $exit = $LASTEXITCODE; $sw.Stop(); $elapsed = [math]::Round($sw.Elapsed.TotalSeconds, 1); Write-Host "Runtime: ${elapsed}s"; Set-Content -Path (Join-Path $outDir "runtime.txt") -Value "Runtime: ${elapsed}s"; if ($exit -ne 0) { exit $exit }

regenerate-canonical-scenarios:
    & {{python}} scripts/regenerate_canonical_scenarios.py

random-walk:
    & {{python}} scripts/random_walk.py

random-walk-run seed policy_seed max_steps run_id:
    & {{python}} scripts/random_walk.py --seed {{seed}} --policy-seed {{policy_seed}} --max-steps {{max_steps}} --run-id {{run_id}}

review-workbook:
    & {{python}} scripts/build_review_workbook.py

openspiel-test:
    & {{python}} -m pytest openspiel_pyrants/tests/ -q

openspiel-smoke:
    & {{python}} -c "import openspiel_pyrants; import pyspiel; g = pyspiel.load_game('python_pyrants'); print('Registered:', g.get_type().short_name); s = g.new_initial_state(); print('State created, chance_node:', s.is_chance_node()); actions = s.legal_actions(); print('Chance actions:', len(actions)); s._apply_action(42); print('After chance:', str(s)[:120])"

ismcts num_sims="200" num_games="4" seed="42" output_dir="artifacts/ismcts":
    & {{python}} -m scripts.run_ismcts --num-sims {{num_sims}} --num-games {{num_games}} --seed {{seed}} --output-dir {{output_dir}}

ismcts-quick:
    & {{python}} -m scripts.run_ismcts --num-sims 50 --num-games 2 --seed 42
