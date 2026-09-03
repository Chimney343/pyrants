# UCT Sweep Experiment: does per-seat `uct_c` affect win rate, VP share, and final deck variety?

## Goal

Run IS-MCTS simulations where each seat gets a different UCB1 exploration constant (`uct_c`), rotating the ladder across seats between games, and analyze whether `uct_c` affects:

1. **Win rate** per uct arm (Wilson 95% CI)
2. **Average end-game VP ratio** — VP share = seat final VP ÷ total table VP (baseline 0.25 in 4p); raw mean VP reported alongside
3. **Final deck variation** — (confirmed with user) **primary**: within-deck diversity per player (unique card-type ratio, normalized Shannon entropy, Simpson index) over the full final deck (draw pile + hand + discard + played + inner circle + trophy hall); **secondary**: across-game spread (sd) of these metrics per uct arm

**Design (confirmed with user):** 4 players, wider uct ladder default `0.3,0.8,1.4,2.5`, rotating across seats per game (1.4 is the current engine default; 0.3/2.5 are the extreme arms); main run **240 games** (pilot 8), `random-c` evaluator at a uniform 200 sims so uct_c is the only varying factor.

## Answers to the discover questions

### How many games are required?

**No stored run artifacts exist** (`artifacts/ismcts/` is currently empty), so there is no empirical tie-rate or wall-time to calibrate against — the pilot measures both. The numbers below are analytic (hand-verified Wilson math).

Design leverage: with 4 seats and a rotating 4-value ladder, **every game contributes one observation per uct arm**, and arms are compared within-game. Let N = *decided* games (terminal, unique winner); each arm gets N win-rate observations.

**Win rate — the precision bottleneck.** Wilson 95% CI half-width per arm at the 25% null baseline:

| Decided games (N) | Per-arm CI half-width | Detects win-rate deviation ≥ |
|---|---|---|
| 60  | ±10.7pp | ~11pp |
| 80  | ±9.3pp  | ~9pp  |
| 110 | ±8.0pp  | 8pp   |
| 120 | ±7.7pp  | ~8pp  |
| 160 | ±6.7pp  | ~7pp  |
| 200 | ±6.0pp  | 6pp   |
| 240 | ±5.4pp  | ~5pp  |
| 288 | ±5.0pp  | 5pp   |

Required per-arm decided N: **±10pp → 70; ±8pp → 110; ±5pp → 288.**

**Trend tests — the primary hypothesis test.** Seeded within-game permutation test on mean per-game Spearman(uct, outcome). Per-game ρ over 4 seats has null sd √(1/3) ≈ 0.577; one-sided α=0.05 with 80% power detects mean per-game ρ ≥ 1.434/√N: N=60 → ρ≥0.19, N=120 → ρ≥0.13, N=240 → ρ≥0.09. (Spearman is rank-based, so the uct scale — linear vs log — is irrelevant.)

**Continuous metrics (VP share, deck diversity).** Far tighter than win rate: with per-game sd ≈ 0.08 for VP share, N=120 gives ±1.4pp on the mean. **N is driven by win-rate CI width, not these.**

**Total-games inflation.** Ties/errors reduce the decided fraction: total games ≈ required-N ÷ decided fraction. The **8-game pilot** measures the decided fraction (plus wall-time and zero-crash); `analysis.md` prints achieved N, required-N for ±10/±8/±5pp targets, and the projected total games at the observed decided fraction.

**Decision (user): pilot 8 → main 240 games default.** 240 buys per-arm CI ±5.4pp (near the ±5pp target; ~216 decided at a 90% decided fraction) and trend-test power for mean ρ ≥ 0.09 at 80% — resolving smaller effects than 120 up front, at ~2× the wall time (minutes per 4p game at 200 sims; across 16 workers ≈ an extended overnight run — the pilot calibrates the real number). If the pilot's decided fraction comes in low, the games-needed projection in `analysis.md` states exactly how many more to add; extend with a second run and merge via `--analyze-only`.

### How to calculate deck variety

Full final deck per seat is read from the C `PlayerState` struct (all zones exposed: `deck[]`, `hand[]`, `discard_pile[]`, `played_cards[]`, `inner_circle[]`, `trophy_hall[]` — engine_c/state.h:221-232) via `state._adapter._state._s.players[i]` + `_sym_str`. The full deck is the union of these six zones (cards can leave it via the shared devour pile, so size ≤ 10 + recruits).

**Starter-deck dilution:** every player starts with the identical 7× noble + 3× soldier (data/decks/base_setup.json) — a fixed low-diversity block (unique_ratio starts at 0.2 regardless of play). Metrics are therefore computed **twice**:

- **`recruited`** (primary comparison): full multiset minus the starter multiset — the clean signal for how uct_c shapes deck-building choices
- **`full`** (kept for the literal "final deck" reading): all zones combined

Metrics per card-id multiset (size n, k unique types, proportions p_i):

- `unique_ratio` = k / n (1.0 = all cards distinct)
- `shannon_entropy` = H(p) in bits; `normalized_entropy` = H / log2(n) (define 0.0 for n < 2)
- `simpson` = 1 − Σp_i² (probability two random draws differ)
- Across-game spread: sd of each metric per uct arm over games

### How to change uct per simulated player

`make_ismcts_bot` (openspiel_pyrants/ismcts_factory.py:23) already takes `uct_c` per bot, and `run_one_game` builds one bot per seat (scripts/run_ismcts.py:444-457) — but currently accepts only a scalar `uct_c`. Extend `run_one_game` to accept `float | Sequence[float]` and normalize to a per-seat list, exactly mirroring the existing `num_sims` / `num_sims_per_seat` pattern (including `_normalize_sims_per_seat` at scripts/run_ismcts.py:376 and the per-seat summary field).

## Implementation tasks (ordered)

### 1. `scripts/run_ismcts.py` — per-seat uct + final-deck capture (modify)

Keep all changes additive and backward compatible (scalar `uct_c` callers — including the whole sims-vs-wins experiment and 4 existing test files — must behave identically).

- New helper `_normalize_per_seat_uct(uct_c, num_players) -> list[float]`: scalar → `[uct_c] * num_players`; sequence → validate length == num_players and every value > 0 (mirror `_normalize_sims_per_seat`).
- `run_one_game`: change `uct_c` param type to `float | Sequence[float]`; normalize once; in the bot loop pass `uct_c=uct_per_seat[i]` to `make_ismcts_bot`.
- `_base_game_summary`: add required `uct_c_per_seat: list[float]` param; keep the existing `uct_c` field as the mean of the per-seat values (backward compat with CSV writer, mirrors `num_sims_per_move`). Update both call sites (success + crash-partial paths in `run_one_game`).
- New helper `_final_deck_card_ids(state) -> list[list[str]]`: for each seat, concatenate card ids from all six zones using `state._adapter._state._s.players[i]` counts + `_sym_str` (read counts, never full fixed arrays).
- New helper `_final_deck_metrics(per_seat_decks) -> list[dict]` calling `deck_variety_metrics` from `scripts/_uct_sweep.py` (import inside function to keep module import-light), passing `starter_counts` derived from the already-cached `_base_setup()["starter_deck"]["entries"]` (7× noble + 3× soldier — the starter deck is identical across players and invariant under `combine_two_deck_market_setup`, which only varies the market).
- After the main loop ends without exception (terminal **or** round_cap): write `final_decks.json` into the game dir — `{"player_ids": [...], "per_seat": [[card ids], ...]}` — and add to the game summary:
  - `player_ids` (seat-ordered, from `state._game.get_player_ids()`)
  - `final_vp_per_seat` (seat-ordered ints, from `compute_final_scores(state)` keyed by player id)
  - `final_deck_metrics` (per-seat list of metric dicts)
  - `uct_c_per_seat` (list)
- `_run_one_game_standalone`: no signature change needed (forwards `uct_c`; lists are picklable).
- `write_summaries`: add `uct_c_per_seat` to CSV fieldnames, serialized like `num_sims_per_seat` (comma-joined).

### 2. `scripts/_uct_sweep.py` — pure analysis helpers (new, stdlib only)

Mirror `scripts/_sims_vs_wins.py` structure. Import `_spearman`, `_rank_desc`, `_wilson_ci` from `scripts._sims_vs_wins`; reuse `seat_budgets_for_game` from there (it is generic over list element type).

- `parse_uct_spec(spec: str, num_players: int) -> list[float]` — comma-separated floats > 0; ValueError on empty segment / non-float / length mismatch / value ≤ 0.
- `deck_variety_metrics(card_ids: list[str], starter_counts: dict[str, int] | None = None) -> dict` — returns `{"full": {...}, "recruited": {...}, "recruited_degraded": bool}`; each sub-dict carries `unique_count`, `deck_size`, `unique_ratio`, `shannon_entropy`, `normalized_entropy`, `simpson`. `recruited` = full multiset minus `starter_counts` (clamped; if any starter count exceeds the observed count — should not happen — set `recruited_degraded: true` and fall back to full metrics for that seat).
- `required_decided_games(target_half_width: float, p: float = 0.25, z: float = 1.96) -> int` — smallest n such that the Wilson half-width at p is ≤ target (bisection over the exact Wilson formula, not the normal approximation).
- `analyze_uct(summaries, *, n_players, n_permutations=10_000, seed=0) -> dict` — mirrors `analyze()` but keyed on `uct_c_per_seat` (arms = sorted unique floats):
  - win rate + Wilson CI per uct arm (decided games only) and per seat (confound check)
  - mean VP share (guard: total table VP == 0 → share 0.0 and flag the game), mean raw VP, mean rank per arm. **VP share requires `final_vp_per_seat`**; the `returns` fallback is valid only for rank/trend ordering — for n>2 `returns` is raw VP, but for n==2 it is a zero-sum margin (openspiel_pyrants/tests/test_utility_contract.py:4-5), so share means never fall back to `returns`
  - deck variety per arm: mean ± sd for both the `full` and `recruited` metric sets, from games with valid `final_deck_metrics`
  - permutation trend tests (within-game seat permutation, one-sided): uct vs VP share; uct vs `recruited.normalized_entropy`
  - exclusions (ties / round_cap / errors / other), `effective_n_frac`, `low_effective_n` warning
  - `games_needed` block: achieved n_decided, required-N for ±10pp / ±8pp / ±5pp targets, and projected **total** games at the observed decided fraction

### 3. `scripts/run_ismcts_uct_sweep.py` — experiment runner (new)

Mirror `scripts/run_ismcts_sims_vs_wins.py` structurally (ProcessPoolExecutor, tqdm, metrics.json, write_summaries, experiment_config.json with `uct_ladder_by_game` map, `_experiment_dir` timestamped subdir).

- Args: `--uct-per-seat` (default `"0.3,0.8,1.4,2.5"`), `--num-players` (default 4, must equal ladder length), `--num-sims` (default 200), `--num-games` (default 240), `--rotate-seats` / `--no-rotate-seats`, `--evaluator` (default `random-c`), plus the usual passthroughs (`--seed`, `--shuffle-seed`, `--workers`, `--max-world-samples`, `--final-policy`, `--rollout-count`, `--rollout-max-length`, `--max-rounds`, log-level flags).
- `--analyze-only <run_dir> [<run_dir> ...]`: skip simulation entirely; read `experiment_config.json` + every `game_*/summary.json` from the given run dir(s) and regenerate `analysis.json` / `analysis.md` (written into the first dir). Enables (a) re-analysis after tweaking metrics without re-simulating, and (b) merging an extension run with the original when the first batch's CIs were too wide.
- `DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "ismcts" / "experiments" / "uct_sweep"` — per-run dir `<UTC-ts>_<run_id>/` with `game_XXXX/` subdirs inside (satisfies "save all simulations into ismcts/experiments folder").
- Per game: `seat_uct = seat_budgets_for_game(ladder, gi, rotate)`; submit `_run_one_game_standalone(..., uct_c=seat_uct, num_sims=args.num_sims, ...)`.
- After the run: `analyze_uct(summaries, n_players=...)` → `analysis.json` + `analysis.md` (render win-rate table per uct arm with CIs, mean VP share, full + recruited deck diversity mean±sd, trend p-values, and the games-needed projection block).

### 4. `tests/test_uct_sweep.py` — unit tests (new, pure stdlib, no engine)

Mirror `tests/test_sims_vs_wins.py`:

- `parse_uct_spec`: valid list, whitespace stripping, non-float / empty segment / length mismatch / zero / negative → ValueError.
- `deck_variety_metrics`: all-unique deck → `unique_ratio == 1.0`, `normalized_entropy == 1.0`; identical-card deck → low entropy/ratio, correct Simpson; n < 2 → `normalized_entropy == 0.0`; empty deck edge case; starter subtraction (full deck with 7× noble + 3× soldier removed → `recruited` correct, `recruited_degraded: false`); starter count exceeding observed → `recruited_degraded: true` and recruited == full.
- `required_decided_games`: ±10pp → 70, ±8pp → 110, ±5pp → 288 (assert exact or ±1); monotonic in target width.
- `analyze_uct` on synthetic summaries: win attribution per arm; VP share means; VP share with zero total table VP → share 0.0 and game flagged, excluded from share means; deck metric aggregation (full + recruited) with sd; tie/round_cap/error exclusions; planted monotone uct→VP effect → trend p small; null data → p large; rotation of a float ladder balances seats over 4k games.
- `seat_budgets_for_game` with float ladder (regression that the reused helper is type-agnostic).
- `--analyze-only` path: two tmp run dirs with synthetic `game_*/summary.json` + `experiment_config.json` → merged analysis written into the first dir, no simulation invoked (mock/absent game engine must not be touched).

### 5. Engine-runner integration tests (extend `openspiel_pyrants/tests/test_run_ismcts_runner.py`)

Follow the existing `test_run_one_game_per_seat_budgets` / `test_run_one_game_scalar_backward_compat` / `test_run_one_game_invalid_length_raises` pattern (uses `requires_c_engine` fixture, `tmp_path`):

- per-seat `uct_c` list → summary carries `uct_c_per_seat` and mean `uct_c`; `final_decks.json` written; `final_vp_per_seat` seat-ordered; `final_deck_metrics` present
- scalar `uct_c` backward compat → `uct_c_per_seat == [c, c]`, behavior unchanged
- per-seat list of wrong length / non-positive value → ValueError

### 6. `justfile` — new commands (modify)

Add after the `ismcts-sims-vs-wins` block (same comment style):

```just
# UCT sweep experiment: does the UCB1 exploration constant (uct_c) affect
# win rate, end-game VP share, and final deck variety? Rotates a per-seat
# uct ladder (0.3/0.8/1.4/2.5) across seats each game. Run the 8-game
# pilot first to calibrate wall-time and the decided fraction before the
# 240-game main run (per-arm win-rate CI ~±5.4pp).
ismcts-uct-pilot workers="16":
    & {{python}} -m scripts.run_ismcts_uct_sweep --num-games 8 --workers {{workers}}

ismcts-uct num_games="240" workers="16" *args:
    & {{python}} -m scripts.run_ismcts_uct_sweep --num-games {{num_games}} --workers {{workers}} {{args}}
```

All simulation artifacts land under `artifacts/ismcts/experiments/uct_sweep/<ts>_<run_id>/`.

## Validation plan

1. `ruff check .`
2. `.venv/Scripts/python.exe -m pytest tests/test_uct_sweep.py tests/test_sims_vs_wins.py tests/test_run_ismcts_crash_capture.py tests/test_run_ismcts_state_snapshots.py -q` (new + regression on all `run_one_game` callers)
3. `just openspiel-test` (covers `openspiel_pyrants/tests/test_run_ismcts_runner.py` incl. new integration tests)
4. Requires `just build-c` first (engine_c.dll must exist).
5. Pipeline smoke (fast, ~minutes): `.venv/Scripts/python.exe -m scripts.run_ismcts_uct_sweep --num-games 1 --num-sims 2 --workers 1` → verify `game_0000/final_decks.json`, `summary.csv` (`uct_c_per_seat` column), `analysis.json/md`, `experiment_config.json` all written and well-formed.
6. Real pilot: `just ismcts-uct-pilot` → confirm zero crashes and a sane decided fraction; then `just ismcts-uct` for the main run.

## Risks and notes

- `scripts/run_ismcts.py` and its tests are churn hotspots — keep edits strictly additive; the existing sims-vs-wins experiment and all four existing test files calling `run_one_game` must pass unchanged (scalar path is a no-op refactor).
- Summary `uct_c` must remain the **mean** of per-seat values so the existing CSV/summary consumers stay valid (same convention as `num_sims_per_move`).
- `returns()` semantics (verified): n>2 → raw non-negative VP totals; n==2 → zero-sum margin. VP-share means must therefore come from `final_vp_per_seat` (`compute_final_scores`), never from `returns`; `returns` is only a fallback for rank/trend ordering.
- Deck/VP metrics are only meaningful on games that end without error; error games already carry no terminal scores and are excluded by the analysis (same semantics as `analyze()`). Round_cap games get deck dumps but are excluded from win rates; flag them in analysis counts.
- No empirical calibration data exists (`artifacts/ismcts/` is empty) — tie-rate and wall-time come from the 8-game pilot; the games-needed projection in `analysis.md` is the honest feedback loop for extending the run.
- Read zone *counts*, never the full `MAX_ZONE_SIZE` fixed arrays.
- Wall time: 4p × 200 sims with the `random-c` evaluator is on the order of minutes per game (per the sims-vs-wins docstring); the 240-game default across 16 workers is roughly 2× the 120-game cost — hence the mandatory pilot for calibration, and `num-games` stays overridable on the just command.
- Determinism is preserved: seat seeds (`seed + game_index*num_players + i`), deck-pair selection per `game_index`, and the recorded `uct_ladder_by_game` map make every game reproducible.

## Out of scope

- No C engine changes (all data needed is already exposed via ctypes structs).
- No changes to the plain `just ismcts` runner CLI (per-seat uct is consumed programmatically by the experiment runner).
- No replay-viewer changes for `final_decks.json` (artifact is analysis input, not UI).
