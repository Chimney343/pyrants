# Plan: Observability improvements for `just ismcts-quick`

## Context

`just ismcts-quick` invokes `python -m scripts.run_ismcts --num-sims 10 --num-games 1 --seed 42`. The script is long-running (clone ~10 ms/state × `num_sims` × ~4000 decisions/game ≈ hours at default scale, minutes at "quick" scale) and currently has effectively **zero observability**:

- No structured logging — only `tqdm.write`/stdout for game-done lines (line 382) and `print` (lines 435-438, 374-375).
- No correlation/run ID to tie worker logs to a run.
- No metric collection for the four golden signals: latency (per-move wall time is captured but only written to `decisions.jsonl` after the fact, not emitted live), traffic, errors, saturation.
- No worker-side progress at all in the parallel path — `ProcessPoolExecutor` workers have no logging either, and worker failures surface only via `future.result()` raising after completion.
- No log level configuration; debugging requires re-running.
- Sequential path uses `tqdm` (good UX but not log-able); parallel path also uses `tqdm` but workers emit nothing.
- `wall_time_ms` per decision is recorded (line 245) but there are no percentiles, no per-phase breakdowns, no slow-move warnings.

The skill `python-observability` prescribes structured logging, correlation IDs, the four golden signals, bounded-cardinality metrics, and a level scheme. The repo's engine purity rules still apply — `engine/` stays pure; observability lives in `scripts/run_ismcts.py` and the parallel worker wrapper.

## Goals

1. Make `just ismcts-quick` produce structured, level-filtered logs that explain what each worker is doing in real time, in JSON for machines and a human-friendly renderer for terminals.
2. Surface a per-run correlation/run ID on every log line and inside the per-game artifacts so post-mortems can join log lines to `decisions.jsonl`/`replay.json`.
3. Track the four golden signals minimally (counters + a small set of histograms) without taking a hard dependency on a metrics backend — store them in a `RunMetrics` dataclass dumped to `artifacts/ismcts/metrics.json` at the end of the run.
4. Catch and log worker exceptions (currently propagate uncaught and abort the run with a stack trace, no context).
5. Keep the change scoped: one file (`scripts/run_ismcts.py`) plus a tiny new helper module; no engine changes; no breaking CLI.

## Non-goals

- No Prometheus/StatsD/OpenTelemetry exporter (no project dependency on any of these; the metrics artifact is the deliverable).
- No async/await — `open_spiel` ISMCTS is CPU-bound; we keep `ProcessPoolExecutor`.
- No changes to `engine/`, `openspiel_pyrants/`, `data/`, or `tests/` test contracts. Existing `tests/` are unaffected because the public surface of `run_ismcts.py` (`run_one_game`, `write_summaries`) stays signature-compatible; `main()` is the only behavior-changing entry.
- No web dashboard.

## Proposed changes

### 1. Add a `scripts/_obs.py` helper (new, ~80 lines)

A thin observability layer that depends only on `stdlib` + `structlog` (new dep, see step 6):

- `configure_logging(level: str, json: bool, run_id: str) -> None` — sets up `structlog` with `merge_contextvars`, `add_log_level`, `TimeStamper(fmt="iso")`, `StackInfoRenderer`, `format_exc_info`, and a conditional renderer (`JSONRenderer()` for `--json-logs`, `ConsoleRenderer(colors=False)` for terminal).
- `new_run_id() -> str` — `uuid.uuid4().hex[:12]`.
- `bind_run_context(run_id, game_index, worker_pid)` helper.
- A `RunMetrics` dataclass with:
  - Counters: `moves_total`, `games_completed`, `games_failed`, `worker_exceptions`, `simulation_seconds_total` (sum of `wall_ms/1000` for `bot.step_with_policy`).
  - Histograms (bounded, list of values, capped at e.g. 4096 samples with reservoir sampling or simple ring buffer): `move_latency_ms`, `game_wall_sec`.
  - Per-phase counts: `decisions_by_phase: dict[str, int]`.
  - `to_jsonable() -> dict` for `metrics.json` dump.
- `record_move_latency(metrics, wall_ms, phase)` and `record_game_summary(metrics, summary)` methods.

Rationale: keeps the run script readable, isolates the dep on `structlog` to one file, and makes it trivial to unit-test in isolation later.

### 2. Modify `scripts/run_ismcts.py`

**Imports & wiring**
- Add `--log-level` (default `INFO`) and `--json-logs` (store_true) CLI flags.
- Generate a `run_id` in `main()` and pass it down to workers; bind it to `structlog.contextvars` so every log line carries it.

**In `run_one_game`**
- Acquire a `structlog.get_logger()` at the top; bind `game_index`, `deck_a_id`, `deck_b_id`, `shuffle_seed`.
- Replace the bare `tqdm.write` in `_build_ismcts_setup_json` (line 73) with `logger.warning("few_deck_profiles", ...)` so the warning is level-filterable and structured.
- Log per-decision at `DEBUG` with `move_latency_ms`, `round`, `phase`, `legal_action_count`, `chosen_move` (one log line per move; at `INFO` we can keep it silent to avoid noise, but the level knob lets users opt in).
- Log slow decisions at `WARNING` if `wall_ms > SLOW_MOVE_MS_THRESHOLD` (default 5000 ms) — surfaces pathological determinization costs in real time.
- Log game end at `INFO` with `decision_count`, `wall_time_sec`, `sims_per_sec_avg`, `winner`, `score_diff`.
- On exception inside the `while not state.is_terminal()` loop, `logger.exception("move_failed", ...)` and re-raise (preserves current fail-fast behavior but leaves a trail).
- Update the per-game `summary.json` and `decisions.jsonl` to include `"run_id"` field so they join with log lines.

**Worker (`_run_one_game_standalone`)**
- In the worker process, re-`configure_logging(...)` with the same level/JSON settings and bind a `worker_pid` contextvar (note: with `ProcessPoolExecutor` stdout is not piped, so workers' `PrintLoggerFactory` writes to their own stdout — `tqdm` and worker prints will interleave with the parent. We will log at `WARNING+` only inside workers, parent stays at `INFO+`, to keep noise bounded). For the `just ismcts-quick` path (1 worker) this is moot; for multi-worker it gives operators a fallback.
- Wrap the `return run_one_game(...)` in `try/except`: on failure, append a `{"error": ..., "traceback": ..., "game_index": ...}` line to `artifacts/ismcts/failures.jsonl` and log at `ERROR` with `exc_info=True` so the parent's `future.result()` re-raise is preceded by a real log entry. Currently the parallel branch (line 503-504) will crash the run with no per-game breadcrumb.

**`main()`**
- Print a structured `logger.info("run_start", ...)` line and a matching `logger.info("run_end", ...)` at the end.
- Emit `metrics.json` from the in-memory `RunMetrics` before `write_summaries` runs (or after — order doesn't matter; choose after so the metrics include the per-game latencies that were recorded).
- The four golden signals become queryable from `metrics.json`:
  - **Latency:** histograms `move_latency_ms` (p50/p95/p99 computed in the dump) and `game_wall_sec`.
  - **Traffic:** counters `moves_total`, `games_completed`.
  - **Errors:** counters `games_failed`, `worker_exceptions`.
  - **Saturation:** `cpu_count`, `workers`, `sims_per_sec_avg_overall` (derived at dump time).

### 3. Optional: `tests/test_run_ismcts_obs.py` (new, ~60 lines)

Light tests around the helper, not the full pipeline:
- `configure_logging` is idempotent and accepts a level.
- `RunMetrics.record_move_latency` correctly updates counters and the bounded ring buffer.
- A small "log at WARNING when move exceeds threshold" assertion by patching the logger (avoids pulling in `pytest-subtests` or `structlog.testing`).

Skip this in the first pass if the user prefers minimum-scope — call it out as a follow-up.

### 4. Dependency

Add `structlog >= 24.1.0` to `[project].dependencies` in `pyproject.toml` and `uv.lock`/`poetry.lock` (run `uv lock` / `poetry lock` as appropriate). Rationale: the skill specifically calls structlog out; it's small, zero transitive deps for what we use, and consistent with the skill's quick-start. `prometheus_client` is *not* added — we don't need an exporter and the skill explicitly warns against pulling in heavy backends for local scripts.

### 5. Backwards compatibility

- All existing CLI flags unchanged; new flags (`--log-level`, `--json-logs`) default to current behavior (INFO, human-readable).
- `summary.csv`, `summary.md`, `game_*/replay.json`, `game_*/decisions.jsonl`, `game_*/summary.json` keep their schemas. New fields are additive (`run_id`).
- `tests/` suite is unaffected.

## Files touched

| File | Change |
|---|---|
| `scripts/_obs.py` | **new** — logging + metrics helper |
| `scripts/run_ismcts.py` | wire helper, add CLI flags, instrument `run_one_game` + worker, dump `metrics.json`, add `run_id` to artifacts |
| `pyproject.toml` | add `structlog` dep |
| `uv.lock` / `poetry.lock` | regen |
| `tests/test_run_ismcts_obs.py` | **new** (optional, recommended) |
| `justfile` | no change — `ismcts-quick` automatically benefits |
| `docs/` | no change (behavior is CLI-driven) |

## Validation

1. `just test` — existing suite must pass unchanged.
2. `ruff check .` — must be clean.
3. `just ismcts-quick` (1 game, 10 sims) must complete and write `artifacts/ismcts/metrics.json` + `artifacts/ismcts/summary.{csv,md}` as before, plus structured log lines on stderr/stdout.
4. Manual checks:
   - `just ismcts-quick -- --log-level DEBUG --json-logs` → JSON lines, one per move.
   - `just ismcts-quick -- --workers 2 --num-games 2` → no interleaved crashes; `failures.jsonl` is created only on failure.
   - `metrics.json` round-trips via `RunMetrics.to_jsonable()` and contains p50/p95/p99 for `move_latency_ms`.

## Open questions for the user

1. **Dependency on `structlog`**: OK to add it as a runtime dep, or prefer stdlib `logging` + a custom JSON formatter to avoid any new deps? Recommendation: `structlog` — it is what the skill prescribes, and it removes ~40 lines of formatter boilerplate we'd otherwise write.
2. **Tests file**: include `tests/test_run_ismcts_obs.py` in this pass, or keep the change purely in `scripts/` and add tests as a follow-up?
3. **Worker logging verbosity**: should workers log at `INFO` (currently no logs in workers at all) or stay at `WARNING+` only (recommendation: `WARNING+`, with a `--worker-log-level` escape hatch)?
