set shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-Command"]

python := ".venv/Scripts/python.exe"

# ── C Engine ────────────────────────────────────────────────────────────────

build-c:
    cmd /c "engine_c\\compile.bat"

# AddressSanitizer build: catches C memory-safety bugs (buffer overflows,
# use-after-free) that a normal build and test run can't see. Produces
# separate engine_c_asan.dll / *_asan.exe artifacts; does not touch the
# normal build-c output.
build-c-asan:
    cmd /c "engine_c\\compile_asan.bat"

build-game players="p1,p2" board="data/boards/tyrants_of_the_underdark.json" layout="data/layouts/tyrants_of_the_underdark_layout.json" card="data/cards" setup="data/decks/base_setup.json": build-c
    & {{python}} -m interface.game_viewer --players {{players}} --board-path {{board}} --layout-path {{layout}} --card-path {{card}} --setup-path {{setup}}

simulate-c players="p1,p2" seed="42" max_steps="200":
    & {{python}} -c "import sys; sys.path.insert(0, 'engine_c/bindings'); from engine_c.bindings.session import run_c_simulation; r = run_c_simulation('{{players}}'.split(','), seed={{seed}}, max_steps={{max_steps}}, verbose=True); print('Result:', r)"

# ── Tests ────────────────────────────────────────────────────────────────────

test:
    & {{python}} -m pytest -q

test-c:
    & .\engine_c\test_engine.exe
    & .\engine_c\test_view.exe
    & .\engine_c\test_describe.exe
    & .\engine_c\test_generic_actions.exe
    & .\engine_c\test_saveload.exe
    & .\engine_c\test_catalog_assembly.exe
    & .\engine_c\test_rollout.exe

test-c-python: generate-test-card-scenarios
    & {{python}} -m pytest tests/c_engine -v

# Run the C-engine test suite through the AddressSanitizer build instead of
# the normal one, to surface memory-safety bugs the functional tests can't
# see on their own. Slower than test-c-python; run it periodically, not on
# every commit.
test-c-asan: build-c-asan generate-test-card-scenarios
    $env:PYRANTS_ENGINE_DLL = (Resolve-Path "engine_c/engine_c_asan.dll").Path; & {{python}} -m pytest tests/c_engine -v

# ── Game Interface ───────────────────────────────────────────────────────────

board-creator:
    & {{python}} -m interface.board_creator

board-creator-open board="data/boards/tyrants_of_the_underdark.json" layout="data/layouts/tyrants_of_the_underdark_layout.json":
    & {{python}} -m interface.board_creator --board-path {{board}} --layout-path {{layout}}

game-viewer players="p1,p2" board="data/boards/tyrants_of_the_underdark.json" layout="data/layouts/tyrants_of_the_underdark_layout.json" card="data/cards" setup="data/decks/base_setup.json":
    & {{python}} -m interface.game_viewer --players {{players}} --board-path {{board}} --layout-path {{layout}} --card-path {{card}} --setup-path {{setup}}

game-viewer-help:
    & {{python}} -m interface.game_viewer --help

replay-viewer:
    & {{python}} -m interface.replay_viewer

replay-viewer-open game="artifacts/ismcts/game_0000":
    & {{python}} -m interface.replay_viewer --game-dir {{game}}

verify-replays:
    & {{python}} scripts/verify_replays.py

# ── IS-MCTS (C engine backend) ───────────────────────────────────────────────

ismcts num_sims="200" num_games="4" seed="42" output_dir="artifacts/ismcts" workers="16" num_players="4" uct_c="1.4":
    & {{python}} -m scripts.run_ismcts --num-sims {{num_sims}} --num-games {{num_games}} --seed {{seed}} --output-dir {{output_dir}} --workers {{workers}} --num-players {{num_players}} --uct-c {{uct_c}} --game python_pyrants_c

ismcts-quick workers="1" num_players="2" uct_c="1.4":
    & {{python}} -m scripts.run_ismcts --num-sims 2 --num-games 1 --seed 42 --workers {{workers}} --num-players {{num_players}} --uct-c {{uct_c}} --game python_pyrants_c

# Sims-vs-wins experiment: does a bigger IS-MCTS budget win more games?
# Rotates a per-seat budget ladder (50/100/200/400) across seats each game.
ismcts-sims-vs-wins-pilot workers="16":
    & {{python}} -m scripts.run_ismcts_sims_vs_wins --num-games 8 --workers {{workers}}

ismcts-sims-vs-wins num_games="120" workers="16" *args:
    & {{python}} -m scripts.run_ismcts_sims_vs_wins --num-games {{num_games}} --workers {{workers}} {{args}}

# UCT sweep experiment: does the UCB1 exploration constant (uct_c) affect
# win rate, end-game VP share, and final deck variety? Rotates a per-seat
# uct ladder (0.3/0.8/1.4/2.5) across seats each game. Run the 8-game
# pilot first to calibrate wall-time and the decided fraction before the
# 240-game main run (per-arm win-rate CI ~±5.4pp).
ismcts-uct-pilot workers="16":
    & {{python}} -m scripts.run_ismcts_uct_sweep --num-games 8 --workers {{workers}}

ismcts-uct num_games="240" workers="16" *args:
    & {{python}} -m scripts.run_ismcts_uct_sweep --num-games {{num_games}} --workers {{workers}} {{args}}

bench-rollout engine="py" num_rollouts="200" seed="42" warmup_steps="10":
    & {{python}} -m scripts.bench_rollout --engine {{engine}} --num-rollouts {{num_rollouts}} --seed {{seed}} --warmup-steps {{warmup_steps}}

ismcts-perf num_players="2" *args:
    powershell -NoProfile -Command "New-Item -ItemType Directory -Force -Path artifacts/ismcts/performance_testing | Out-Null"
    & {{python}} -m cProfile -o artifacts/ismcts/performance_testing/cprofile.pstats -m scripts.run_ismcts --num-sims 10 --num-games 1 --seed 42 --num-players {{num_players}} --max-rounds 10 --output-dir artifacts/ismcts/performance_testing --workers 1 --game python_pyrants_c {{args}}
    & {{python}} -c "import pstats; p = pstats.Stats('artifacts/ismcts/performance_testing/cprofile.pstats'); p.sort_stats('cumulative').print_stats(40); p.sort_stats('tottime').print_stats(20)" > artifacts/ismcts/performance_testing/cprofile_top.txt
    powershell -NoProfile -Command "Get-Content artifacts/ismcts/performance_testing/cprofile_top.txt"

# ── OpenSpiel ────────────────────────────────────────────────────────────────

openspiel-test:
    & {{python}} -m pytest openspiel_pyrants/tests/ -q

openspiel-smoke:
    & {{python}} -c "import openspiel_pyrants; import pyspiel; g = pyspiel.load_game('python_pyrants_c'); print('Registered:', g.get_type().short_name); s = g.new_initial_state(); print('State created, chance_node:', s.is_chance_node()); actions = s.legal_actions(); print('Chance actions:', len(actions)); s._apply_action(42); print('After chance:', str(s)[:120])"

# ── Scenario Generation ─────────────────────────────────────────────────────
#
# generate-card-scenarios [workers] [spy] [aspect] [seed] [attempts] [steps]
#   workers:  number of parallel workers (default 1).
#   spy:      "true" to require the current player to have a spy on the board;
#             "false" (default) means spy does NOT matter.
#   aspect:   "ASPECT:COUNT" to require COUNT cards of ASPECT in hand (e.g. "guile:2");
#             empty (default) means aspect does NOT matter.
#   seed:     base RNG seed (default 4).
#   attempts: max reachable-search attempts per card (default 30).
#   steps:    max steps per attempt (default 3000).
#   Conditions are AND-combined with the always-on "target card playable now"
#   condition. To ignore a condition, omit it (trailing) or pass "false"/"".
# Examples:
#   just generate-card-scenarios
#   just generate-card-scenarios 1 true
#   just generate-card-scenarios 1 false guile:2
#   just generate-card-scenarios 1 true guile:2

generate-card-scenarios workers="1" spy="false" aspect="" seed="4" attempts="30" steps="3000":
    $sw = [System.Diagnostics.Stopwatch]::StartNew(); $outDir = "data/scenarios/batch_card_generation"; $flags = @('--output-dir', $outDir, '--base-seed', '{{seed}}', '--max-attempts', '{{attempts}}', '--max-steps', '{{steps}}', '--workers', '{{workers}}'); if ('{{spy}}' -eq 'true') { $flags += @('--require-spy-on-board') }; if ('{{aspect}}' -ne '') { $flags += @('--require-aspect', '{{aspect}}') }; & {{python}} scripts/generate_card_scenarios.py $flags; $exit = $LASTEXITCODE; $sw.Stop(); $elapsed = [math]::Round($sw.Elapsed.TotalSeconds, 1); Write-Host "Runtime: ${elapsed}s"; Set-Content -Path (Join-Path $outDir "runtime.txt") -Value "Runtime: ${elapsed}s"; if ($exit -ne 0) { exit $exit }

generate-test-card-scenarios workers="1" seed="4" attempts="30" steps="3000":
    $sw = [System.Diagnostics.Stopwatch]::StartNew(); $outDir = "data/scenarios/test_card_generation"; if ((Test-Path -LiteralPath $outDir) -and (Get-ChildItem -LiteralPath $outDir -Filter "*_seed_4_*.json" | Select-Object -First 1)) { Write-Host "Test scenario folder already populated; skipping regeneration." } else { $flags = @('--output-dir', $outDir, '--base-seed', '{{seed}}', '--max-attempts', '{{attempts}}', '--max-steps', '{{steps}}', '--workers', '{{workers}}'); & {{python}} scripts/generate_card_scenarios.py $flags; $exit = $LASTEXITCODE; $sw.Stop(); $elapsed = [math]::Round($sw.Elapsed.TotalSeconds, 1); Write-Host "Runtime: ${elapsed}s"; Set-Content -Path (Join-Path $outDir "runtime.txt") -Value "Runtime: ${elapsed}s"; if ($exit -ne 0) { exit $exit } }

# generate-card-scenario <card_id> [spy] [aspect] [seed] [attempts] [steps]
#   spy:      "true" to require the current player to have a spy on the board;
#             "false" (default) means spy does NOT matter.
#   aspect:   "ASPECT:COUNT" to require COUNT cards of ASPECT in hand (e.g. "guile:2");
#             empty (default) means aspect does NOT matter.
#   seed:     base RNG seed (default 4).
#   attempts: max reachable-search attempts per card (default 30).
#   steps:    max steps per attempt (default 10000).
#   Conditions are AND-combined with the always-on "target card playable now"
#   condition. To ignore a condition, omit it (trailing) or pass "false"/"".
# Examples:
#   just generate-card-scenario noble
#   just generate-card-scenario noble true
#   just generate-card-scenario noble false guile:2
#   just generate-card-scenario noble true guile:2

generate-card-scenario card_id spy="false" aspect="" seed="4" attempts="30" steps="10000":
    $sw = [System.Diagnostics.Stopwatch]::StartNew(); $outDir = "data/scenarios/random_card_generation"; $flags = @('--output-dir', $outDir, '--base-seed', '{{seed}}', '--max-attempts', '{{attempts}}', '--max-steps', '{{steps}}', '--card-id', '{{card_id}}'); if ('{{spy}}' -eq 'true') { $flags += @('--require-spy-on-board') }; if ('{{aspect}}' -ne '') { $flags += @('--require-aspect', '{{aspect}}') }; & {{python}} scripts/generate_card_scenarios.py $flags; $exit = $LASTEXITCODE; $sw.Stop(); $elapsed = [math]::Round($sw.Elapsed.TotalSeconds, 1); Write-Host "Runtime: ${elapsed}s"; if ($exit -ne 0) { exit $exit }

# ── Analysis & Tooling ───────────────────────────────────────────────────────

review-workbook:
    & {{python}} scripts/build_review_workbook.py

move-label-templates *args:
    & {{python}} -m scripts.generate_move_label_templates {{args}}

card-complexity *args:
    & {{python}} -m scripts.card_complexity_review {{args}}

docs-check *args:
    & {{python}} scripts/check_docs_freshness.py {{args}}
