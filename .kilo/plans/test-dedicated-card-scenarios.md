# Plan: Test-Dedicated Card Scenarios Folder + test-c-python Integration

## Goal
Two pytest tests currently load scenario JSONs from `data/scenarios/batch_card_generation/`
and fail (or get skipped on missing-file detection) when that folder is absent:

- `tests/test_engine_c.py::test_quaggoth_assassinate_count_snapshotted`
  loads `017_seed_4_quaggoth.json` (line 485)
- `tests/test_card_mindwitness.py::test_mindwitness_assassinate_labels`
  loads `013_seed_4_mindwitness.json` (line 17)

Today the user must manually run `just generate-card-scenarios workers=1 seed=4 attempts=30 steps=3000`
to populate that folder, otherwise these tests break.

We want a dedicated test folder populated automatically by `just test-c-python`,
without forcing a regeneration every time, and without disturbing `batch_card_generation`.

## User-Confirmed Decisions
- New folder: `data/scenarios/test_card_generation/` (full 125-card mirror).
- Regenerate **only when the folder is missing** or empty. If present, skip generation and run tests directly. This makes subsequent test runs fast while still self-healing for fresh clones.
- `just test-c-python` should:
  1. Ensure `data/scenarios/test_card_generation/` exists & is non-empty.
  2. If not, run the generator with the same parameters (`workers=1 seed=4 attempts=30 steps=3000`).
  3. Then run `pytest tests/test_engine_c.py tests/test_card_mindwitness.py -v` (or equivalent) so the test-c-python suite actually covers the two tests that need scenarios. Today it only runs `tests/test_engine_c.py`.
- `batch_card_generation` and `just generate-card-scenarios` are left untouched.

## Proposed Changes

### 1. `justfile` — add one new recipe, modify one existing recipe

Add new recipe `generate-test-card-scenarios` that mirrors `generate-card-scenarios`
exactly but writes to the test folder. It uses an existence/emptiness guard so
calling it twice is idempotent.

```
generate-test-card-scenarios workers="1" seed="4" attempts="30" steps="3000":
    $sw = [System.Diagnostics.Stopwatch]::StartNew(); $outDir = "data/scenarios/test_card_generation"; if ((Test-Path -LiteralPath $outDir) -and (Get-ChildItem -LiteralPath $outDir -ErrorAction SilentlyContinue | Where-Object { -not $_.PSIsContainer -or $_.Name -notin @('runtime.txt') } | Select-Object -First 1)) { Write-Host "Test scenario folder already populated; skipping regeneration." } else { & {{python}} scripts/generate_card_scenarios.py --output-dir $outDir --base-seed {{seed}} --max-attempts {{attempts}} --max-steps {{steps}} --workers {{workers}}; $exit = $LASTEXITCODE; $sw.Stop(); $elapsed = [math]::Round($sw.Elapsed.TotalSeconds, 1); Write-Host "Runtime: ${elapsed}s"; Set-Content -Path (Join-Path $outDir "runtime.txt") -Value "Runtime: ${elapsed}s"; if ($exit -ne 0) { exit $exit } }
```

Modify `test-c-python` to first invoke the generator (which is a no-op when the folder is already populated), then run both test files:

```
test-c-python: generate-test-card-scenarios
    & {{python}} -m pytest tests/test_engine_c.py tests/test_card_mindwitness.py -v
```

Note: removing the `generate-test-card-scenarios` dependency and instead
inlining a single PowerShell block inside `test-c-python` is also fine and a
bit shorter; the dependency form above is preferred because it keeps the
generator command independently runnable and matches the existing
`build-game`-style pattern in the same file.

### 2. `tests/test_engine_c.py` — point to test folder

Change the one scenario path at `tests/test_engine_c.py:485`:

- Before: `"data/scenarios/batch_card_generation/017_seed_4_quaggoth.json"`
- After:  `"data/scenarios/test_card_generation/017_seed_4_quaggoth.json"`

The filename (`017_seed_4_quaggoth.json`) and seed (`4`) are preserved exactly,
so the regenerated scenario is byte-equivalent (the generator is seed-deterministic).

### 3. `tests/test_card_mindwitness.py` — point to test folder

Change the `SCENARIO_PATH` at `tests/test_card_mindwitness.py:17`:

- Before: `data/scenarios/batch_card_generation/013_seed_4_mindwitness.json`
- After:  `data/scenarios/test_card_generation/013_seed_4_mindwitness.json`

### 4. No changes needed to:
- `scripts/generate_card_scenarios.py` — already accepts `--output-dir`; we
  just point it at the new folder.
- `data/scenarios/batch_card_generation/` — left alone so the existing
  manual workflow (`just generate-card-scenarios`) continues to work for the
  broader card-execution-validator use case.
- `AGENTS.md` — no convention-level change.

## Why a "presence + non-empty" guard, not just "presence"?
A previous broken run could leave a folder that exists but contains zero
scenario files (only `runtime.txt` from a failed invocation). The guard treats
that as "not populated" and regenerates. We exclude `runtime.txt` from the
emptiness check to avoid that edge case.

## Validation
After implementation:

1. Fresh-clone simulation:
   - `Remove-Item -Recurse -Force data/scenarios/test_card_generation`
   - `just test-c-python` → generator runs, both tests pass.
2. Re-run:
   - `just test-c-python` → generator logs "skipping regeneration", tests run fast.
3. Sanity:
   - `just generate-card-scenarios workers=1 seed=4 attempts=30 steps=3000`
     still writes to `data/scenarios/batch_card_generation/` unchanged.
   - `ruff check .` clean.

## Risks / Caveats
- The full 125-card generation can take several minutes on first run. This
  is the same cost as the existing `generate-card-scenarios` recipe and is
  documented behavior; subsequent runs are free.
- The two tests depend on the existence of specific scenario files. If the
  generator ever fails to produce them, the test suite will surface a clear
  `FileNotFoundError` from `CSession.load`, pointing at the new folder.
- The existing `tests/test_engine_c.py` import lines and `test_c_create` /
  fixture logic are unchanged; only the hardcoded path string changes.

## Files Touched
- `justfile` (2 recipe changes: add `generate-test-card-scenarios`, modify `test-c-python`)
- `tests/test_engine_c.py` (1 path string on line 485)
- `tests/test_card_mindwitness.py` (1 path string on line 17)

## Out of Scope
- Migrating every other test that references `batch_card_generation`
  (the only ones in `tests/` are the two above; the others under
  `tests/test_generate_card_scenarios_c.py`, `tests/test_card_scenario_market_policy.py`,
  `tests/test_state_generator.py` call `generate_card_scenarios(...)` directly
  with their own `tmp_path` output dirs and do not load from `batch_card_generation/`).
- Modifying `scripts/generate_card_scenarios.py`.
- Touching `data/scenarios/batch_card_generation/`.
