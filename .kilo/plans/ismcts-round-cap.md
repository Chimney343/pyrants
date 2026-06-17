# Plan: Engine-Round Cap for `scripts/run_ismcts.py`

## Goal
Add a knob to `scripts/run_ismcts.py` that **artificially terminates** a game
after a configurable number of **engine rounds** (not bot decisions, not
replay steps). The cap must be recorded in all artifact files so a cut game
is clearly distinguishable from a naturally completed one, enabling
performance profiling (e.g. via `cProfile`) without waiting for a full
~4000-decision game to finish.

A new `just` recipe `ismcts-perf` wraps the script with sensible defaults
and a hard-coded output dir of `artifacts/ismcts/performance_testing`.

User confirmed:
- Cut unit = **engine `round_number`** (`state._engine.round_number`)
- Mark in **all** artifact files: `summary.json`, `replay.json`,
  `summary.csv`, `summary.md`, `metrics.json`

## Files Touched
- `scripts/run_ismcts.py` — add CLI flag, plumb through, write cap info.
- `scripts/_obs.py` — add `games_truncated` counter to `RunMetrics`.
- `justfile` — add `ismcts-perf` recipe.

## No new files. No new tests (no existing test file for `run_ismcts.py`;
adding one is out of scope per Surgical Changes).

---

## 1. `scripts/run_ismcts.py`

### 1a. New CLI flag
In `_parse_args` (line ~97):
```python
parser.add_argument("--max-rounds", type=int, default=0,
                    help="Cap engine round_number; 0 = unlimited. "
                         "When the cap is hit the game is recorded as "
                         "stopped_reason='round_cap'.")
```

### 1b. Plumb through call sites
Three call paths use `run_one_game`; the cap must reach all of them so the
worker-pool path stays in sync with the in-process path:

- `run_one_game(...)` signature gains `max_rounds: int = 0`
- `main()` (single-worker branch, line ~569) passes
  `max_rounds=args.max_rounds`
- `_run_one_game_standalone(...)` signature gains `max_rounds: int = 0`,
  `main()` (multi-worker branch, line ~602) passes
  `max_rounds=args.max_rounds`, and the `run_one_game` call inside the
  worker forwards it.

### 1c. Cut logic in `run_one_game`
Inside the `while not state.is_terminal()` loop (line 239), at the **top**
of each iteration (before `bot.step_with_policy` so we never start an
expensive sims batch we won't use), add:
```python
if max_rounds > 0 and state._engine.round_number > max_rounds:
    break
```
> Note: `>` (not `>=`) — round 0 is the chance/initial state, the
> meaningful first engine round is 1, and we want the cap to mean
> "play through round N inclusive".

### 1d. `stopped_reason` (line 361)
Replace the existing line:
```python
"stopped_reason": "terminal" if state.is_terminal() else "unknown",
```
with:
```python
"stopped_reason": (
    "terminal" if state.is_terminal()
    else ("round_cap" if max_rounds > 0 else "unknown")
),
"max_rounds": max_rounds,
```
Add `"is_terminal": state.is_terminal()` (already present, keep).
When truncated: `winner = None`, `score_diff = 0.0`,
`final_scores = {}` (already `{}`). Per-game `summary.json` writes the
same `stopped_reason` / `max_rounds` keys (add them to the
`game_summary` dict at line ~339 so they pass through the `summary.json`
filter, which strips keys starting with `_` but keeps everything else).

### 1e. Per-game log line
At the `game_end` `logger.info(...)` call (line ~330) add a `stopped_reason`
field so the log line clearly says `"stopped"` vs `"truncated"`.

---

## 2. `scripts/_obs.py`

Add counter to `RunMetrics`:
```python
games_truncated: int = 0
```
(no default-reset issues — dataclass with `field(default=0)` style by
adding the line to the existing field list).

Add helper method (mirroring `record_game_wall` style):
```python
def record_game_truncated(self) -> None:
    self.games_truncated += 1
```

Expose in `to_jsonable()` under `"counters"`:
```python
"games_truncated": self.games_truncated,
```

Call sites in `main()`:
- Single-worker branch, after `summaries.append(summary)` (line ~588):
  if `summary.get("stopped_reason") == "round_cap"`:
  `metrics.record_game_truncated()`
- Multi-worker branch, inside the `as_completed` block (line ~625):
  same check on the result summary.

---

## 3. `justfile`

Append after the `ismcts-quick` recipe (after line 63):
```just
ismcts-perf num_sims="200" num_games="1" seed="42" max_rounds="3" workers="1":
    & {{python}} -m scripts.run_ismcts --num-sims {{num_sims}} --num-games {{num_games}} --seed {{seed}} --max-rounds {{max_rounds}} --output-dir artifacts/ismcts/performance_testing --workers {{workers}}
```

Defaults rationale:
- `num_games=1` — first profiling run, then scale up.
- `max_rounds=3` — small enough to finish in seconds even at `--num-sims 200`,
  large enough to exercise several bot decisions and reveal where time
  goes (rollout vs determinization vs clone). User can override.

---

## Verification

Manual smoke test:
```bash
just ismcts-perf num_sims=50 max_rounds=2
```
After it runs, check:
1. `artifacts/ismcts/performance_testing/summary.json` →
   `stopped_reason == "round_cap"`, `max_rounds == 2`,
   `decision_count` is small, `winner == null`.
2. `artifacts/ismcts/performance_testing/replay.json` →
   `stopped_reason == "round_cap"`, `is_terminal == false`.
3. `artifacts/ismcts/performance_testing/summary.csv` → has a new
   `stopped_reason` column (or whatever shape results from the simplest
   field set — see step 4).
4. `artifacts/ismcts/performance_testing/summary.md` → row shows
   `round_cap` in the markdown table.
5. `artifacts/ismcts/performance_testing/metrics.json` →
   `counters.games_truncated == 1`, `counters.games_completed == 0`.
6. End-to-end: `just ismcts-perf` with `max_rounds=0` (or just
   `just ismcts`) should still produce `stopped_reason: "terminal"`,
   confirming the flag is no-op when unset.

Profiling workflow the user actually wants:
```bash
python -m cProfile -o /tmp/ismcts.prof -m scripts.run_ismcts \
    --num-sims 200 --num-games 1 --max-rounds 5 \
    --output-dir artifacts/ismcts/performance_testing
```
Then `python -m pstats /tmp/ismcts.prof` → `sort cumtime` → confirm
where time is spent (hypothesis: inside `RandomRolloutEvaluator`'s
rollout calls invoked from `ISMCTSBot.step_with_policy`).

## Open Question for User
None — all answered. Two minor notes (not blocking):
- `RunMetrics.simulation_seconds_total` (defined line 108, never written)
  is a pre-existing dead field. Per Surgical Changes I will not touch it,
  but if the profiling goal later becomes "attribute seconds to
  sim vs non-sim", a separate instrumentation pass would be the right
  fix — and `metrics.json` already has the counter slot reserved.
- `--rollout-max-length 0` already exists and is unrelated to the new
  `--max-rounds`; keep them clearly named.
