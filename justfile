set shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-Command"]

python := ".venv/Scripts/python.exe"

board-creator:
    & {{python}} -m interface.board_creator

board-creator-open board="data/boards/tyrants_of_the_underdark.json" layout="data/layouts/tyrants_of_the_underdark_layout.json":
    & {{python}} -m interface.board_creator --board-path {{board}} --layout-path {{layout}}

test:
    & {{python}} -m pytest -q

game-simulate players="p1,p2,p3,p4" seed="1" policy="first" policy_seed="1" max_steps="10000" board="data/boards/tyrants_of_the_underdark.json" card="data/cards/catalog.json" setup="data/decks/base_setup.json" replay="artifacts/replay.json":
    & {{python}} -m game_simulation --players {{players}} --seed {{seed}} --policy {{policy}} --policy-seed {{policy_seed}} --max-steps {{max_steps}} --board-path {{board}} --card-path {{card}} --setup-path {{setup}} --replay-log-path {{replay}}

game-viewer players="p1,p2" board="data/boards/tyrants_of_the_underdark.json" layout="data/layouts/tyrants_of_the_underdark_layout.json" card="data/cards/catalog.json" setup="data/decks/base_setup.json":
    & {{python}} -m interface.game_viewer --players {{players}} --board-path {{board}} --layout-path {{layout}} --card-path {{card}} --setup-path {{setup}} --engine c

game-viewer-py players="p1,p2" board="data/boards/tyrants_of_the_underdark.json" layout="data/layouts/tyrants_of_the_underdark_layout.json" card="data/cards/catalog.json" setup="data/decks/base_setup.json":
    & {{python}} -m interface.game_viewer --players {{players}} --board-path {{board}} --layout-path {{layout}} --card-path {{card}} --setup-path {{setup}} --engine python

replay-viewer replay="artifacts/replay.json" board="data/boards/tyrants_of_the_underdark.json" layout="data/layouts/tyrants_of_the_underdark_layout.json":
    & {{python}} -m interface.replay_viewer --replay-log-path {{replay}} --board-path {{board}} --layout-path {{layout}}

game-simulate-help:
    & {{python}} -m game_simulation --help

game-viewer-help:
    & {{python}} -m interface.game_viewer --help

replay-viewer-help:
    & {{python}} -m interface.replay_viewer --help

card-stuck-check decks="data/decks" board="data/boards/tyrants_of_the_underdark.json" card="data/cards/catalog.json" setup="data/decks/base_setup.json" seed="7" seed_count="1" max_steps="120" json_out="artifacts/card_stuck_report.json":
    & {{python}} scripts/check_roster_card_stuck_states.py --decks-dir {{decks}} --board-path {{board}} --card-path {{card}} --setup-path {{setup}} --seed {{seed}} --seed-count {{seed_count}} --max-steps {{max_steps}} --json-out {{json_out}}

card-stuck-check-ci decks="data/decks" board="data/boards/tyrants_of_the_underdark.json" card="data/cards/catalog.json" setup="data/decks/base_setup.json" seed="7" seed_count="1" max_steps="120" expected_blocked="" json_out="artifacts/card_stuck_report.json":
    & {{python}} scripts/check_roster_card_stuck_states.py --decks-dir {{decks}} --board-path {{board}} --card-path {{card}} --setup-path {{setup}} --seed {{seed}} --seed-count {{seed_count}} --max-steps {{max_steps}} --json-out {{json_out}} --ci --expected-blocked-cards {{expected_blocked}}

generate-card-scenarios workers="1" seed="4" attempts="30" steps="3000":
    $sw = [System.Diagnostics.Stopwatch]::StartNew(); $outDir = "data/scenarios/batch_card_generation"; & {{python}} scripts/generate_card_scenarios.py --output-dir $outDir --base-seed {{seed}} --max-attempts {{attempts}} --max-steps {{steps}} --workers {{workers}}; $exit = $LASTEXITCODE; $sw.Stop(); $elapsed = [math]::Round($sw.Elapsed.TotalSeconds, 1); Write-Host "Runtime: ${elapsed}s"; Set-Content -Path (Join-Path $outDir "runtime.txt") -Value "Runtime: ${elapsed}s"; if ($exit -ne 0) { exit $exit }

generate-card-scenario card_id seed="4" attempts="30" steps="3000":
    $sw = [System.Diagnostics.Stopwatch]::StartNew(); $outDir = "data/scenarios/random_card_generation"; & {{python}} scripts/generate_card_scenarios.py --output-dir $outDir --base-seed {{seed}} --max-attempts {{attempts}} --max-steps {{steps}} --card-id {{card_id}}; $exit = $LASTEXITCODE; $sw.Stop(); $elapsed = [math]::Round($sw.Elapsed.TotalSeconds, 1); Write-Host "Runtime: ${elapsed}s"; if ($exit -ne 0) { exit $exit }

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

ismcts num_sims="200" num_games="4" seed="42" output_dir="artifacts/ismcts" workers="16" num_players="4":
    & {{python}} -m scripts.run_ismcts --num-sims {{num_sims}} --num-games {{num_games}} --seed {{seed}} --output-dir {{output_dir}} --workers {{workers}} --num-players {{num_players}}

ismcts-quick workers="1" num_players="2":
    & {{python}} -m scripts.run_ismcts --num-sims 2 --num-games 1 --seed 42 --workers {{workers}} --num-players {{num_players}}

ismcts-perf num_players="2" *args:
    powershell -NoProfile -Command "New-Item -ItemType Directory -Force -Path artifacts/ismcts/performance_testing | Out-Null"
    & {{python}} -m cProfile -o artifacts/ismcts/performance_testing/cprofile.pstats -m scripts.run_ismcts --num-sims 10 --num-games 1 --seed 42 --num-players {{num_players}} --max-rounds 10 --output-dir artifacts/ismcts/performance_testing --workers 1 {{args}}
    & {{python}} -c "import pstats; p = pstats.Stats('artifacts/ismcts/performance_testing/cprofile.pstats'); p.sort_stats('cumulative').print_stats(40); p.sort_stats('tottime').print_stats(20)" > artifacts/ismcts/performance_testing/cprofile_top.txt
    powershell -NoProfile -Command "Get-Content artifacts/ismcts/performance_testing/cprofile_top.txt"

# ── IS-MCTS with C engine backend ────────────────────────────────────────

ismcts-c num_sims="200" num_games="16" seed="42" output_dir="artifacts/ismcts_c" workers="16" num_players="2":
    & {{python}} -m scripts.run_ismcts --num-sims {{num_sims}} --num-games {{num_games}} --seed {{seed}} --output-dir {{output_dir}} --workers {{workers}} --num-players {{num_players}} --game python_pyrants_c

ismcts-c-quick workers="1" num_players="2":
    & {{python}} -m scripts.run_ismcts --num-sims 50 --num-games 1 --seed 42 --workers {{workers}} --num-players {{num_players}} --game python_pyrants_c

ismcts-c-perf top_n="30":
    & scripts/run_ismcts_c_perf.ps1 -TopN {{top_n}}

# ── C engine ────────────────────────────────────────────────────────────

build-c:
    cmd /c "engine_c\\compile.bat"

test-c:
    & engine_c/test_engine.exe
    & engine_c/test_view.exe
    & engine_c/test_describe.exe
    & engine_c/test_saveload.exe

test-c-python:
    & {{python}} -m pytest tests/test_engine_c.py -v

simulate-c players="p1,p2" seed="42" max_steps="200":
    & {{python}} -c "import sys; sys.path.insert(0, 'engine_c/bindings'); from engine_c.bindings.session import run_c_simulation; r = run_c_simulation('{{players}}'.split(','), seed={{seed}}, max_steps={{max_steps}}, verbose=True); print('Result:', r)"
 