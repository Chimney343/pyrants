# IS-MCTS Observability — Phase 1: Crash-Safe Streaming Step Log

## Prerequisite

Phase 0 (`1787952431270-ismcts-phase0-wire-replay-payload-and-log-ordering.md`)
must be merged first — this phase restructures the same `run_one_game()` loop
and depends on the `replay_log` append-after-apply ordering fixed there.

## Context

`run_one_game()` (`scripts/run_ismcts.py:194-534`) accumulates `decisions` and
`replay_log` as in-memory Python lists and only writes `replay.json` /
`decisions.jsonl` / `summary.json` to disk *after* the
`while not state.is_terminal():` loop exits cleanly (`run_ismcts.py:521-532`).
`docs/ismcts-generic-resolution-bugs.md` documents two real, reproducible
crash classes that this exact IS-MCTS harness hits (`state.apply_action`
raising a `RuntimeError` from `CEngineAdapter.apply()`). When either fires,
every step of that game's history is lost — nothing is written.

Worse, `main()`'s `workers == 1` branch (`run_ismcts.py:722-765` — this is
the code path `just ismcts-quick` uses) has **no try/except at all** around
the per-game call, so one bad move kills the entire batch process. The
multiprocess path (`_run_one_game_standalone`, `run_ismcts.py:618-690`,
used only when `--workers > 1`) does catch exceptions, but only writes an
unstructured `traceback.format_exc()` string to `failures.jsonl` — no
step-by-step trail leading up to the crash survives anywhere.

This phase makes both `steps.jsonl` (new) and `decisions.jsonl` (existing)
genuinely streaming — write-and-flush per event, not batch-dumped at the
end — and makes `run_one_game()` degrade gracefully on exception instead of
losing everything or (for single-worker runs) taking the whole process down.
Structured crash-record *content* (what exactly gets written into the
`"game_crashed"` line) is phase 3's job — this phase only builds the
plumbing: the file, the flush discipline, the try/except, and the partial
data structure exceptions carry back out.

## Files touched

- `scripts/run_ismcts.py` (`run_one_game()`, `main()`'s `workers == 1` branch, `_run_one_game_standalone()`)
- `tests/test_run_ismcts_crash_capture.py` (new)
- `openspiel_pyrants/tests/test_run_ismcts_runner.py` (extend: assert `steps.jsonl` exists on a successful run)

## Design (reference while writing tests/code — not itself a task)

- New per-game file `game_NNNN/steps.jsonl`, opened once near the top of
  `run_one_game()` (right after `game_out.mkdir(parents=True, exist_ok=True)`
  at `run_ismcts.py:222`), in `"w"` mode, kept open for the duration of the
  loop. One JSON object per line, written + `.flush()`ed immediately:
  - `{"event": "step", ...}` — after each successful `state.apply_action(...)`.
  - `{"event": "game_crashed", ...}` — written from the except block (phase 3 fills in the `...`; phase 1 just needs the write to happen).
  - `{"event": "game_end", ...}` — written once, on the success path, right before the function returns.
- `decisions.jsonl` also opened once up front in `"w"` mode; each decision
  dict is written + flushed immediately when built (right after
  `decisions.append({...})` at `run_ismcts.py:306-321`), **unconditionally**
  — even if the subsequent `apply_action` fails. The bot's decision is valid
  telemetry regardless of what happens next; remove the current end-of-loop
  bulk-dump (`run_ismcts.py:525-527`).
- The whole `while not state.is_terminal(): ...` body is wrapped in
  `try/except Exception as exc:`. On exception:
  1. Write the `"game_crashed"` steps.jsonl line (content stubbed in this
     phase — just enough shape to test the plumbing; phase 3 fleshes it out).
  2. Build a best-effort partial `game_summary` (same top-level keys as a
     successful summary where derivable — e.g. `decision_count`,
     `wall_time_sec` — with `stopped_reason="error"` and other
     not-yet-computable fields omitted or zeroed; do not attempt to compute
     `final_scores`/`returns`/`policy_entropy_*` etc. from a game that never
     reached a terminal or well-defined state).
  3. Write whatever `replay.json`/`summary.json` can be salvaged (using the
     phase-0-wired `build_replay_payload` with `is_terminal=False`,
     `stopped_reason="error"`).
  4. Raise a new `GameRunFailedError(exc)` (defined in `run_ismcts.py`,
     subclassing `Exception`, `from exc` to preserve the original
     traceback) carrying `.game_summary` (the partial dict from step 2) and
     `.crash_record` (empty/stub dict in this phase — phase 3 populates it;
     for now it can just be `{"exception_type": type(exc).__name__,
     "exception_message": str(exc)}` so phase 1's tests have something
     concrete to assert on).
- `main()`'s `workers == 1` loop (`run_ismcts.py:725-765`): wrap the
  `run_one_game(...)` call in `try/except GameRunFailedError as exc:` —
  append `exc.game_summary` to `summaries`, increment
  `metrics.games_failed`, log via `logger.exception("game_failed",
  game_index=gi)`, and `continue` to the next game instead of propagating.
- `_run_one_game_standalone()` (`run_ismcts.py:676-690`): its existing
  `except Exception:` block should specifically catch `GameRunFailedError`
  first (to get `.crash_record`/`.game_summary` when available) before the
  generic `except Exception:` fallback for anything raised outside
  `run_one_game`'s own try (e.g. game-loading failures) — keep writing to
  `failures.jsonl` here for now; phase 3 restructures *what* gets written.

Durability note to carry into the code as a comment and into this repo's
eventual documentation: per-line `.flush()` survives a Python exception or a
graceful Ctrl+C; it does **not** survive a hard process kill or segfault
(that would need `os.fsync()` per line, at real per-move cost). Both known
crash classes in `docs/ismcts-generic-resolution-bugs.md` are ordinary
Python `RuntimeError`s, so flush-only is the right tradeoff — don't add
fsync in this phase.

## TDD task list

### Task 1.1 — `steps.jsonl` is written incrementally during a successful game, not batch-dumped at the end

**RED**: In `tests/test_run_ismcts_crash_capture.py` (new file), write a
test that runs a short game (use the smallest feasible fixture — e.g.
`--num-sims 1 --num-games 1` against `python_pyrants_c` with 2 players, or
whatever minimal setup existing tests in `openspiel_pyrants/tests/` use to
keep it fast) and, **during** the run (e.g. by monkeypatching
`state.apply_action` to check file state on a specific call, or by running
in a subprocess and polling), asserts that `game_0000/steps.jsonl` exists
and has at least one `"step"` line *before* the game finishes. Confirm this
**fails** against current code (the file doesn't exist until the loop is
fully done, if at all with the current all-at-once write pattern).

*(If polling mid-run proves too flaky/slow for a unit test, an acceptable
alternative: assert the file handle is opened and written to line-by-line by
directly unit-testing a refactored-out helper — see Task 1.2 — rather than
the full `run_one_game` integration path. Prefer the integration-style test
if it's not painful; fall back to the helper-level test only if needed.)*

**GREEN**: Implement the streaming `steps.jsonl`/`decisions.jsonl` writes as
described in Design, above.

**REFACTOR**: If the write-a-line-and-flush logic is duplicated for `"step"`,
`"game_crashed"`, `"game_end"` events, extract a tiny `_write_jsonl_line(fh,
obj)` helper (`fh.write(json.dumps(obj) + "\n"); fh.flush()`) used by all
three call sites and by `decisions.jsonl`'s writes.

### Task 1.2 — an exception mid-loop does not lose prior steps, and raises `GameRunFailedError`

**RED**: In `tests/test_run_ismcts_crash_capture.py`, monkeypatch the
OpenSpiel state object (or the underlying `state.apply_action`) so that the
Nth call raises `RuntimeError("simulated demon bite")`. Run `run_one_game(...)`
directly (not through `main()`) and assert:
- `pytest.raises(GameRunFailedError)` around the call.
- The raised exception's `.game_summary` is a `dict` containing at least
  `decision_count == N - 1` (or whatever count reflects steps that
  succeeded before the raise) and `stopped_reason == "error"`.
- `game_0000/steps.jsonl` exists on disk and contains exactly `N - 1`
  `"step"` lines followed by one `"game_crashed"` line.
- `game_0000/decisions.jsonl` contains `N` lines (the bot's Nth decision was
  recorded even though applying it failed).

Confirm this **fails** against current code (no `GameRunFailedError` class
exists yet; the loop currently propagates the raw `RuntimeError` and writes
nothing).

**GREEN**: Implement `GameRunFailedError`, the try/except around the loop,
and the partial-artifact writes as described in Design, above.

**REFACTOR**: If the partial-`game_summary`-building logic and the
successful-path `game_summary`-building logic (`run_ismcts.py:446-484`)
share meaningful structure, consider extracting a small `_base_game_summary(...)`
helper for the fields both paths can compute (`run_id, game_index,
shuffle_seed, deck_a_id, deck_b_id, num_players, num_sims_per_move, uct_c,
rollout_count, rollout_max_length, policy_type, decision_count,
wall_time_sec`) — but don't force this if it makes either path harder to
read; simple duplication of a handful of dict keys is acceptable per this
repo's existing style (see `docs/ismcts-generic-resolution-bugs.md`'s own
observation about this codebase already having some duplicated
payload-building logic — don't add a third variant, but don't over-abstract
either).

### Task 1.3 — single-worker (`ismcts-quick`) path survives a crash and continues to the next game

**RED**: In `tests/test_run_ismcts_crash_capture.py`, write a test that
calls `main()`'s single-worker code path (extract the `workers == 1` loop
body into a small testable function if it isn't already, e.g.
`_run_games_single_worker(args, run_id, metrics) -> list[dict]`, as a minor
refactor-for-testability) with `--num-games 3` where game index 1 (the
middle one) is set up to crash (via the same monkeypatch technique as Task
1.2, scoped to only fire on that game). Assert:
- All 3 games appear in the returned `summaries` list (games 0 and 2 with
  normal `stopped_reason`, game 1 with `stopped_reason == "error"`).
- `metrics.games_failed == 1` and `metrics.games_completed == 2`.
- The process does not raise — `main()` completes and writes
  `metrics.json`/`summary.csv`/`summary.md` covering all 3 games.

Confirm this **fails** against current code (today, an exception in game 1
propagates out of `main()` entirely — games 2 is never attempted, and no
`metrics.json` is written).

**GREEN**: Wrap the `workers == 1` branch's per-game call in
`try/except GameRunFailedError as exc:` as described in Design, appending
`exc.game_summary`, incrementing `metrics.games_failed`, logging via
`logger.exception(...)`, and `continue`-ing.

**REFACTOR**: Confirm the multiprocess path (`_run_one_game_standalone` /
the `ProcessPoolExecutor` branch, `run_ismcts.py:766-823`) already exhibits
equivalent continue-on-failure behavior (it does, via its existing
`except Exception:` around `future.result()`) — no change needed there in
this phase, just verify by reading, don't duplicate work.

## Verification

```
pytest tests/test_run_ismcts_crash_capture.py openspiel_pyrants/tests/test_run_ismcts_runner.py -v
just ismcts-quick
```
Confirm `artifacts/ismcts/game_0000/steps.jsonl` exists after a normal run,
with one `"step"` line per successful decision plus a trailing
`"game_end"` line.

Manually interrupt a longer run (`just ismcts num_sims=50 num_games=4 workers=1`,
Ctrl+C partway through) and confirm the in-flight game's `steps.jsonl` is a
valid, readable, non-truncated-mid-line JSONL file up to the interruption
point (proves flush-level durability — do not expect it to survive `kill -9`
or a segfault; that's out of scope per the Design note above).
