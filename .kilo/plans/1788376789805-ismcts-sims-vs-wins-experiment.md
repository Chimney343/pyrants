# IS-MCTS Sims-vs-Wins Experiment (4 players, rotating budget ladder)

## Goal

Answer "does a larger IS-MCTS simulation budget win more games in 4-player pyrants?" with a statistically sound, reproducible experiment: seats get budgets of 50/100/200/400 sims per move, the ladder rotates across seats between games, and every game records which seat had which budget.

## Design decisions (resolved)

- **Per-seat budgets**: `run_one_game` currently applies one scalar `num_sims` to every bot. Extend it to accept a per-seat list (backward compatible: int still works).
- **Rotation ON by default** (user decision): game `g`, seat `i` gets `budgets[(i + g) % num_players]`. Over any 4 consecutive games every budget occupies every seat exactly once, deconfounding seat order (seat 0 always moves first — `engine_c/state.c:68`) from budget strength. `--no-rotate-seats` restores the fixed mapping (P1=50, P2=100, P3=200, P4=400).
- **Per-game metadata** (user requirement): each game's `summary.json` (and the run CSV) records `num_sims_per_seat` — index = seat, value = that seat's budget for that game.
- **Experiment name/directory**: `artifacts/ismcts/experiments/sims_vs_wins/<UTC-timestamp_run_id>/` so repeated runs never clobber each other.
- **Analysis deps**: numpy + stdlib only (no scipy/matplotlib in `pyproject.toml`). Trend test is a seeded within-game permutation test.
- **No C engine changes**; everything is Python-side (`scripts/`, `openspiel_pyrants/tests/`).

## Tasks

### 1. Extend `scripts/run_ismcts.py` for per-seat budgets

- `run_one_game`: change `num_sims: int` → `num_sims: int | Sequence[int]`. Normalize internally to `sims_per_seat` (list of length `num_players`; scalar becomes `[num_sims] * num_players`). Validate length match, all values ≥ 1, else raise `ValueError` early.
- Bot loop: `make_ismcts_bot(..., num_sims=sims_per_seat[i], ...)` (factory already accepts any value; per-seat seed derivation `seed + game_index * num_players + i` unchanged).
- Decision records: `sims_requested` = the acting player's budget (currently the global scalar).
- Sims accounting: accumulate `total_sims += sims_per_seat[cp]` per decision; compute `sims_per_sec` from that (currently `num_sims * decision_count / wall_sec`, wrong for mixed budgets).
- Summaries: add `num_sims_per_seat: list[int]`; keep scalar `num_sims_per_move` = mean of the list (backward compat for existing CSV/tests).
- CLI: add `--num-sims-per-seat "50,100,200,400"` (comma list, length must equal `--num-players`, mutually exclusive with `--num-sims`; error cleanly otherwise).
- `write_summaries`: add a `num_sims_per_seat` CSV column (comma-joined string).
- `_run_one_game_standalone`: pass the list through (lists pickle fine for `ProcessPoolExecutor`).

### 2. New pure helper module `scripts/_sims_vs_wins.py`

No pyspiel/numpy-at-import side effects (mirror the `_obs.py` / `_replay_payload.py` testability pattern):

- `parse_sims_spec(spec: str, num_players: int) -> list[int]` — parse/validate the budget list.
- `seat_budgets_for_game(base: list[int], game_index: int, rotate: bool) -> list[int]` — fixed returns `base`; rotated shifts by `game_index % len(base)`.
- `analyze(summaries: list[dict], *, n_players: int, n_permutations: int = 10_000, seed: int = 0) -> dict`:
  - Wins by **budget** (primary): wins attributed to the winning seat's budget / decided games (terminal + unique winner). Wilson 95% CIs.
  - Wins by **seat** (confound check): raw per-seat win rates so seat effects are visible.
  - Mean final VP per budget, mean rank per budget.
  - Trend test: statistic = mean over games of Spearman correlation between `log2(budget)` and final VP, using each game's `num_sims_per_seat` + `returns`. Null: within each game, permute the budget→seat assignment (preserves each game's score multiset and seat structure); `n_permutations` seeded permutations; one-sided p = fraction ≥ observed.
  - Exclusions reported explicitly: ties, `round_cap` truncations, `error` games (from `GameRunFailedError` partial summaries) are excluded from primary win rates but counted; if decided games < 80% of total, include a `low_effective_n: true` warning in the output.

### 3. New experiment script `scripts/run_ismcts_sims_vs_wins.py`

Thin orchestrator reusing `run_ismcts.py` machinery (`_build_ismcts_setup_json`, `_run_one_game_standalone`, `write_summaries`, `RunMetrics`, `record_game_failure`, `_load_game_or_die`, `_resolve_policy`).

Defaults (all overridable):

| Param | Default |
|---|---|
| `--num-sims-per-seat` | `50,100,200,400` |
| `--num-players` | `4` (list length must match) |
| `--num-games` | `120` |
| `--rotate-seats` / `--no-rotate-seats` | rotate ON |
| `--evaluator` | `random-c` (~19× faster; essential at these budgets) |
| `--uct-c` | `1.4` |
| `--max-world-samples` | `-1` (unlimited) |
| `--final-policy` | `visited` |
| `--rollout-count` / `--rollout-max-length` | `1` / `0` |
| `--max-rounds` | `0` |
| `--seed` / `--shuffle-seed` | `42` / `0` (0 → `seed + game_index`, as today) |
| `--workers` | `0` (auto = CPU count) |
| `--log-level` / `--json-logs` / `--worker-log-level` | `INFO` / off / `WARNING` |
| `--output-dir` | `artifacts/ismcts/experiments/sims_vs_wins` |

Expose every IS-MCTS parameter `run_ismcts.py` exposes today except `--game` (pinned to `python_pyrants_c`) and the vestigial `--no-plots` (no plotting code exists to disable).

Output per run: `game_XXXX/{steps.jsonl, decisions.jsonl, replay.json, summary.json}` (unchanged layout; `summary.json` now carries `num_sims_per_seat`), plus run-level `summary.csv`, `summary.md`, `metrics.json`, `analysis.json`, `analysis.md` (human-readable table: budget | wins | games | win% | 95% CI | mean VP | mean rank; plus per-seat table and trend p-value), and `experiment_config.json` (all args + the full per-game seat→budget assignment table). Warn (not fail) if `num_games % num_players != 0` under rotation.

Docstring must carry the compute warning from `run_ismcts.py` (clone ~10 ms/state with random-py; random-c is the only sane default here) and the pilot-first workflow.

### 4. Justfile recipes

```
ismcts-sims-vs-wins-pilot workers="16":            # 8-game calibration run
ismcts-sims-vs-wins num_games="120" workers="16" *args:
```

Mirroring the existing `ismcts` recipe style (venv python, `--game python_pyrants_c` implied).

### 5. Tests

- `openspiel_pyrants/tests/test_run_ismcts_runner.py` (extend) + new pure-helper test file:
  - Arg parsing: `--num-sims-per-seat` default absent; length-mismatch error; mutual-exclusion error with `--num-sims`; non-integer error (mirror `TestParseArgsDefaults` style, no engine needed).
  - `run_one_game` with per-seat budgets (requires_c_engine, tiny budgets like `1,2,2,4`, `max_rounds=5`): summary contains correct `num_sims_per_seat`; behavior otherwise unchanged.
  - `seat_budgets_for_game`: fixed identity; rotation shifts correctly; over `4k` games each budget hits each seat exactly `k` times.
  - `analyze` on synthetic summaries (no engine): strong monotone effect → small p; null data → large p; ties/truncations/errors excluded from primary but counted; Wilson CI sanity.
  - Existing scalar-`num_sims` tests must keep passing unchanged (backward compat).

### 6. Validation sequence

1. `just build-c` (DLL must exist for any C-backend tooling).
2. `ruff check .`
3. `just test` and `just openspiel-test` (new tests included).
4. Pilot: `just ismcts-sims-vs-wins-pilot` (8 games) — calibrate wall-time/game and confirm zero crashes; inspect `analysis.md` renders correctly.
5. Main run: `just ismcts-sims-vs-wins` (120 games) — verify `analysis.md` + per-game `num_sims_per_seat` metadata.

## How many games? (the statistical answer)

Under the null (budgets don't matter), each seat wins ~25% (minus ties). Power at 80%, α=0.05, binomial test of one seat vs 25%:

| True win rate of 400-sim seat | Games needed |
|---|---|
| 45% | ~40 |
| 40% | ~70 |
| 35% | ~155 |
| 30% | ~580 |

The trend test (all four budgets, full VP ranks — every game is a randomized block containing all budgets) is stronger: detects per-game budget↔rank correlation of 0.10 with ~37 games, 0.07 with ~76, 0.05 with ~150.

**Recommendation: 8-game pilot, then 120 games as the default main run.** At 120 games: 95% CI ≈ ±8 points per budget's win rate (±7 at p=0.25), 30 games per budget×seat cell under rotation, solid power for moderate effects (400-sim seat ≥ ~38%, or rank correlation ≥ ~0.07). Compute estimate: mean budget 187.5 sims/decision (sum 750 vs 800 for today's uniform-200 default), ~16 core-hours total → roughly 1–2 h wall on 16 workers with `random-c`. If the pilot shows a strong effect already, 60–80 games is enough; if results are marginal, extend to 200 (CI ±6) rather than peeking repeatedly (repeated optional stopping invalidates p-values; one pre-planned interim check after 60 games is acceptable).

Ties/truncations/failures shrink effective N — `analysis.json` reports decided-game count and flags `low_effective_n` below 80%.

## Risks / edge cases

- **Wall-time uncertainty**: the 2.2 h/game figure in `run_ismcts.py`'s docstring is for the slow `random-py` evaluator; `random-c` is ~19× faster. The pilot exists precisely to calibrate before committing to 120 games.
- **Crash classes** (`docs/ismcts-generic-resolution-bugs.md`): runner already salvages artifacts and continues; analysis excludes failed games. If pilot failure rate > 10%, fix engine/bot issues before the main run.
- **Windows process pool**: lists pickle fine; `GameRunFailedError` already round-trips (see its pickle note). Keep passing only picklable args through `_run_one_game_standalone`.
- **Seed discipline**: seat seeds stay `seed + game_index * num_players + i` regardless of budget assignment, so rotation changes nothing about RNG streams — budgets are the only moving part.
- **Backward compat**: every existing `run_one_game` caller/test passes an int and must behave identically.

## Out of scope

- C engine changes, OpenSpiel wrapper changes, plotting (no matplotlib dependency), changing existing `just ismcts` behavior beyond the additive `--num-sims-per-seat` flag.
