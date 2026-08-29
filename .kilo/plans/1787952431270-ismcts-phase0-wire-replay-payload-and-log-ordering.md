# IS-MCTS Observability — Phase 0: Housekeeping (wire up `_replay_payload.py`, fix log-ordering bug)

## Prerequisite

None. This is the first phase and should land before phases 1-5 in this series
(`1787952432270` … `1787952436270`), since phase 1 restructures the same
`run_one_game()` loop this phase touches.

## Context

`scripts/run_ismcts.py::run_one_game()` builds `replay.json`'s payload inline
(lines ~427-523) even though `scripts/_replay_payload.py` already contains a
tested, equivalent implementation (`build_replay_payload`,
`compute_final_scores`, `resolve_winner_id`) that is never imported anywhere
except its own test file (`tests/test_run_ismcts_replay_payload.py`). Two
grugs built the same club; only one gets used. Wire the tested one in and
delete the duplicate.

Separately, `replay_log.append(...)` (`run_ismcts.py:323`) happens *before*
`state.apply_action(int(chosen))` (`run_ismcts.py:335`) is even attempted. If
`apply_action` raises (this is the normal failure mode for both crash classes
documented in `docs/ismcts-generic-resolution-bugs.md`), the replay log
already contains an entry claiming the move succeeded. This must be fixed
before phase 1 adds crash-safe persistence, or the persisted log will lie
about what happened.

Finally, `write_summaries()`'s CSV writer (`scripts/run_ismcts.py:554-558`)
uses `extrasaction="ignore"` but no `restval`, so a game summary dict missing
a fieldname (which phase 1's partial/crashed-game summaries will produce)
raises `KeyError` instead of writing a blank cell.

## Files touched

- `scripts/run_ismcts.py` (`run_one_game()`, `write_summaries()`)
- `tests/test_run_ismcts_replay_payload.py` (existing — should already pass; extend only if `build_replay_payload`'s signature needs to grow to match what `run_one_game` currently passes)
- `openspiel_pyrants/tests/test_run_ismcts_runner.py` (regression coverage for the ordering fix)

## TDD task list

### Task 0.1 — `replay_log` entry only recorded after `apply_action` succeeds

**RED**: In `openspiel_pyrants/tests/test_run_ismcts_runner.py` (or a new
`tests/test_run_ismcts_step_ordering.py` if the runner test file doesn't
easily support monkeypatching `state.apply_action`), write a test that:
1. Monkeypatches/wraps the OpenSpiel state's `apply_action` so the *second*
   call raises `RuntimeError("boom")`.
2. Runs (a minimal slice of) `run_one_game()` — or directly exercise the
   loop body if `run_one_game` isn't yet easily unit-testable at this point
   (that's fine, this test can be a `pytest.raises` around the whole call for
   now; phase 1 will give you a cleaner seam).
3. Asserts that whatever `replay_log`/`decisions` state existed *before* the
   raise contains exactly the entries for moves that actually succeeded — no
   entry for the move that raised.

Run it, confirm it **fails** against current code (the failing move's replay
entry is present, since `replay_log.append` runs before `apply_action`).

**GREEN**: In `run_one_game()`, move the `replay_log.append({...})` block
(currently `run_ismcts.py:323-333`) to *after* the `state.apply_action(int(chosen))`
call (currently line 335) succeeds. Keep `decisions.append(...)` where it is
(it should record the bot's decision regardless of whether the apply
succeeds — that ordering is intentionally different and is finalized in
phase 1, not here; for this task, just don't change `decisions`' position).

Re-run the test, confirm it passes.

**REFACTOR**: none expected — this is a one-line-move fix.

### Task 0.2 — `run_one_game()` uses `scripts/_replay_payload.py` instead of an inline duplicate

**RED**: `tests/test_run_ismcts_replay_payload.py` already exists and tests
`build_replay_payload`/`compute_final_scores`/`resolve_winner_id` in
isolation — confirm it currently passes (it should; it's testing the
orphaned module directly, not `run_ismcts.py`). Add one new test in that
file (or a new `tests/test_run_ismcts_uses_replay_payload.py`) that asserts
`scripts.run_ismcts` actually imports `build_replay_payload` from
`scripts._replay_payload` — e.g. `import scripts.run_ismcts as m; import
scripts._replay_payload as rp; assert m.build_replay_payload is
rp.build_replay_payload` (adjust the exact import name to whatever you pick
in GREEN). Confirm this test **fails** first (the import doesn't exist yet).

**GREEN**: In `run_ismcts.py`, add `from scripts._replay_payload import
build_replay_payload, compute_final_scores, resolve_winner_id` and replace:
- the inline final-scores/winner computation (around `run_ismcts.py:427-434`
  region — check current line numbers after task 0.1's shift) with calls to
  `compute_final_scores(state)` / `resolve_winner_id(state, winner,
  num_players)` — note these two helpers expect an object with `_adapter`
  and (for the fallback path) `_game.get_player_ids()`; confirm `state` (the
  OpenSpiel `PyrantsCState`) satisfies that shape before wiring — it does,
  per `openspiel_pyrants/state_c.py`.
- the inline `replay_payload = {...}` dict construction with a call to
  `build_replay_payload(run_id=..., stopped_reason=..., max_rounds=...,
  step_count=decision_count, is_terminal=state.is_terminal(),
  winner_id=winner_id, final_scores=final_scores, replay_log=replay_log,
  shuffle_seed=shuffle_seed, deck_a_id=deck_a_id, deck_b_id=deck_b_id,
  board_path=..., card_path=..., setup_path=..., player_ids=player_ids,
  final_round_num=final_round_num, final_phase=final_phase)`.

Delete the now-dead inline code. Re-run both the new import-check test and
the existing `test_run_ismcts_replay_payload.py` suite; confirm all pass.

**REFACTOR**: Run `just ismcts-quick` once and diff the resulting
`replay.json` byte-for-byte (modulo the `run_id`/timestamps that are
expected to differ) against a `replay.json` produced by the pre-change code,
to confirm the switch is a pure refactor with no schema change.

### Task 0.3 — CSV writer tolerates missing fields

**RED**: In a new or existing test for `write_summaries()` (add
`tests/test_run_ismcts_write_summaries.py` if none exists), construct a
`summaries` list where one dict is missing a field from `fieldnames` (e.g.
simulate a phase-1 partial/crashed summary by omitting `"policy_entropy_mean"`),
call `write_summaries(tmp_path, summaries, "run123")`, and assert it does
not raise and the CSV row for that game has an empty cell in that column.
Confirm this **fails** (raises `KeyError`) against current code.

**GREEN**: Add `restval=""` to the `csv.DictWriter(...)` call at
`scripts/run_ismcts.py:555`.

**REFACTOR**: none expected.

## Verification

```
pytest tests/test_run_ismcts_replay_payload.py tests/test_run_ismcts_write_summaries.py openspiel_pyrants/tests/test_run_ismcts_runner.py -v
just ismcts-quick
```
Confirm `artifacts/ismcts/game_0000/replay.json` still has the same shape
(`run_id, stopped_reason, max_rounds, step_count, is_terminal, winner_id,
final_scores, replay_log, replay_context`) as before this phase.
