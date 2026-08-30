# IS-MCTS Observability — Phase 3: Structured Crash Diagnostics

## Prerequisite

Phase 1 (`1787952432270-ismcts-phase1-crash-safe-streaming-step-log.md`) must
be merged first — this phase fills in the `"game_crashed"` line content and
`.crash_record` shape that phase 1 stubbed out. Phase 2 is not a hard
dependency but should land first if both are being done, since a crashed
game's last-known state (Tier 1/2 snapshots) is useful context alongside the
crash diagnosis.

## Context

`CEngineAdapter.apply()` (`engine_c/bindings/c_adapter.py:92-111`, note: at
time of writing this diagnostic-message logic is present in the working
tree but uncommitted — verify it's still there before starting) already
builds a rich diagnostic message when a move fails to apply:
`pending_card_id` (via `_sym_str(pg.contents.source_card_id)`), `phase`,
`round_number`, `current_player_id`, `is_terminal`, and up to 10
`legal_moves` strings — but only as free text *inside* the `RuntimeError`'s
message string. Today that string only ever ends up embedded in a full
Python traceback dumped into `failures.jsonl`'s `error` field (or, for
single-worker runs prior to phase 1, printed to stderr and lost) — never as
structured, queryable fields.

Critically, `CEngineAdapter.apply()` does **not** mutate `self._state` when
it fails (`c_adapter.py:94-111`: the `raise RuntimeError(...)` happens
*before* `self._engine.destroy(self._state); self._state = new_state`). This
means the adapter remains valid and queryable *after* the exception
propagates — a caller in `run_ismcts.py` can independently re-ask
`adapter.phase()`, `adapter.round_number()`, `adapter.current_player_id()`,
`adapter.is_terminal()`, `adapter.legal_moves()` post-failure, without
parsing anything out of the exception's message string. This phase builds
that independent, structured diagnosis.

This directly serves the reconstruction goal: the two known crash classes
in `docs/ismcts-generic-resolution-bugs.md` should become identifiable from
`pending_card_id` alone (`elder_brain` and 31 same-shaped cards for "demon
one"; `kobold`/`ettin`/`weaponmaster` for "demon two") without ever opening
a raw traceback.

## Files touched

- `scripts/run_ismcts.py` (`_diagnose_apply_failure`, `_build_crash_record` — new helpers; wire into the except block phase 1 built)
- `scripts/_obs.py` (`record_game_failure()` — new)
- `tests/test_crash_diagnostics.py` (new)

## Design (reference while writing tests/code)

- `_diagnose_apply_failure(adapter) -> dict`, wrapped in its own
  `try/except Exception` internally (a failure to introspect must never mask
  or replace the original exception being handled):
  ```python
  def _diagnose_apply_failure(adapter) -> dict:
      try:
          legal = adapter.legal_moves()
          pg = adapter._state._ptr.contents.pending_generic
          pending_card_id = _sym_str(pg.contents.source_card_id) if pg else None
          return {
              "pending_card_id": pending_card_id,
              "phase_at_failure": adapter.phase(),
              "round_number_at_failure": adapter.round_number(),
              "current_player_at_failure": adapter.current_player_id(),
              "is_terminal_at_failure": adapter.is_terminal(),
              "legal_moves_count_at_failure": len(legal),
              "legal_moves_at_failure": [str(m) for m in legal][:10],
          }
      except Exception as diag_exc:
          return {"diagnosis_failed": str(diag_exc)}
  ```
  Note this reads `adapter._state._ptr.contents.pending_generic` — the same
  "private" attribute `c_adapter.py` itself reads internally. This is a
  deliberate, minimal, read-only coupling (no changes to
  `engine_c/bindings/*` in this series) rather than plumbing a new public
  property through — acceptable per the observability plan's explicit
  constraint to leave those files untouched; a future cleanup could promote
  `pending_generic` extraction to a public `CEngineAdapter.pending_card_id`
  property, but that's out of scope here.
- `_build_crash_record(exc, state, step_index, attempted_move_label, attempted_move_type, attempted_payload) -> dict`:
  ```python
  def _build_crash_record(exc, state, step_index, attempted_move_type, attempted_move_label, attempted_payload) -> dict:
      record = {
          "exception_type": type(exc).__name__,
          "exception_message": str(exc),
          "traceback": traceback.format_exc(),
          "step_index": step_index,
          "attempted_move_type": attempted_move_type,
          "attempted_move_label": attempted_move_label,
          "attempted_payload": attempted_payload,
      }
      adapter = getattr(state, "_adapter", None)
      if adapter is not None:
          record.update(_diagnose_apply_failure(adapter))
      return record
  ```
  This replaces phase 1's stub `.crash_record` content
  (`{"exception_type": ..., "exception_message": ...}`) with the full
  version. `attempted_move_type`/`attempted_move_label`/`attempted_payload`
  come from the `chosen_move_obj`/`chosen_move_str` values already computed
  earlier in the loop iteration (available at `run_ismcts.py`'s
  `bot.step_with_policy(state)` call site) — pass them through to wherever
  the except block is.
- Wire `_build_crash_record(...)`'s result into both:
  - the `"game_crashed"` `steps.jsonl` line (phase 1's stub → real content).
  - `GameRunFailedError.crash_record`.
- `record_game_failure(output_dir, run_id, game_index, exc, crash_record=None, worker_pid=None) -> dict`
  in `scripts/_obs.py` (co-located with `RunMetrics`): builds the
  `failures.jsonl` line — start from the existing shape
  `{"run_id": run_id, "game_index": game_index, "worker_pid": worker_pid,
  "error": traceback.format_exc()}` and merge in `crash_record`'s fields
  additively (keep the `error` key verbatim for anything that greps for it
  today). Appends the line to `Path(output_dir) / "failures.jsonl"` and
  also returns the dict (useful for the `main()` single-worker path, which
  doesn't currently have a `failures.jsonl`-writing helper at all).
- Use `record_game_failure()` from **both**:
  - `_run_one_game_standalone()`'s except block (`run_ismcts.py:676-690`) —
    replace its inline `failures_path.open("a")` block, passing
    `getattr(exc, "crash_record", None)` when `exc` is a
    `GameRunFailedError` (it will be, per phase 1, for any failure inside
    `run_one_game` itself; keep the generic fallback for failures raised
    outside it, e.g. `_load_game_or_die`).
  - `main()`'s `workers == 1` except block (added in phase 1) — call
    `record_game_failure(args.output_dir, run_id, gi, exc,
    crash_record=exc.crash_record)` there too, so both code paths produce
    identical `failures.jsonl` shapes.

## TDD task list

### Task 3.1 — `_diagnose_apply_failure` extracts structured fields from a still-valid post-failure adapter

**RED**: In `tests/test_crash_diagnostics.py` (new), construct a real
minimal C-engine session (reuse existing fixture helpers, e.g.
`tests/c_engine/card_test_helpers.py`) in a state where you can force
`adapter.apply(move)` to fail — the simplest reproduction is likely to
directly call `adapter.apply()` with a `CMoveWrapper` you know is illegal
for the current state (e.g. an `assassinate` move with no valid target), or
— better, since it's a real documented repro — set up the `elder_brain`
sequence-card scenario from `docs/ismcts-generic-resolution-bugs.md` (an
existing scenario fixture may already exist under
`data/scenarios/random_card_generation/` for `elder_brain`; check first
before building a new one) and drive it to the exact stuck confirm-move.
After the caught `RuntimeError`, call `_diagnose_apply_failure(adapter)` and
assert:
- `pending_card_id == "elder_brain"` (if using that repro) or matches
  whatever card you staged.
- `phase_at_failure`, `round_number_at_failure`, `current_player_at_failure`
  match values independently read from `adapter` before the failed call.
- `legal_moves_at_failure` is a non-empty list of strings.

Confirm this **fails** first (function doesn't exist).

**GREEN**: Implement `_diagnose_apply_failure` as in Design.

**REFACTOR**: If constructing the `elder_brain` repro scenario for this test
is heavy, consider extracting a `_force_apply_failure(adapter) -> RuntimeError`
test helper that constructs a minimal artificial illegal move instead
(simpler, doesn't require reproducing a specific card bug) — reserve the
real `elder_brain` repro for phase 5's end-to-end verification instead of
duplicating it here. Prefer whichever keeps this test fast and focused on
`_diagnose_apply_failure`'s field-extraction logic, not on reproducing the
bug itself.

### Task 3.2 — a diagnosis failure never masks the original exception

**RED**: Write a test where `_diagnose_apply_failure` is called with an
adapter whose `.legal_moves()` (or `._state._ptr`) is monkeypatched to
raise. Assert `_diagnose_apply_failure` returns
`{"diagnosis_failed": "<message>"}` rather than propagating. Confirm this
**fails** first (no internal try/except exists yet).

**GREEN**: Add the internal `try/except Exception as diag_exc` as in
Design.

**REFACTOR**: none expected.

### Task 3.3 — `_build_crash_record` merges exception info with adapter diagnosis and attempted-move context

**RED**: Using a mocked `state` object with a mocked `_adapter` (unit-test
level, no real engine needed here — `_diagnose_apply_failure` itself is
already covered by Task 3.1/3.2 against the real engine), assert
`_build_crash_record(exc, state, step_index=5,
attempted_move_type="resolve_generic", attempted_move_label="resolve_generic(...)",
attempted_payload={...})` returns a dict containing `exception_type,
exception_message, traceback, step_index, attempted_move_type,
attempted_move_label, attempted_payload` plus everything
`_diagnose_apply_failure` (mocked to return a known dict) contributes.
Confirm this **fails** first.

**GREEN**: Implement `_build_crash_record` as in Design.

**REFACTOR**: none expected.

### Task 3.4 — `failures.jsonl` carries structured fields, and both worker paths (single and multi) write the identical shape

**RED**: Extend `tests/test_run_ismcts_crash_capture.py` (from phase 1):
after the single-worker-path crash test (Task 1.3) and a multiprocess-path
equivalent (may need a small new test using `_run_one_game_standalone`
directly with a monkeypatched failure), assert that both produce a
`failures.jsonl` line with the same keys present:
`run_id, game_index, worker_pid, error, exception_type, exception_message,
step_index, attempted_move_type, pending_card_id, phase_at_failure,
round_number_at_failure, ...` (whatever `_build_crash_record` produces,
merged into the base shape). Confirm this **fails** first (today only the
multiprocess path writes `failures.jsonl` at all, and only with `{run_id,
game_index, worker_pid, error}`).

**GREEN**: Implement `record_game_failure()` in `scripts/_obs.py` and wire
it into both call sites as described in Design.

**REFACTOR**: Once both call sites use `record_game_failure()`, confirm no
inline `failures_path.open("a")` code remains duplicated anywhere in
`run_ismcts.py`.

## Verification

```
pytest tests/test_crash_diagnostics.py tests/test_run_ismcts_crash_capture.py -v
```
Then run a batch sized to actually reproduce one of the two known crash
classes (see phase 5's verification for the exact recipe) and confirm the
resulting `failures.jsonl` line's `pending_card_id` (or, for the "both doors
nailed shut" class, the two offered moves' `target_id`) correctly identifies
which documented demon fired — this is the real proof that structured
diagnosis works, not just the unit tests.
