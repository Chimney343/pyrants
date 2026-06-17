# Plan: Diagnose why 298f153a3b56 games end "without reaching terminal state"

## Observed Symptom

For every game in `artifacts/ismcts_c/298f153a3b56/`, the replay JSON shows:

```json
{
  "stopped_reason": "terminal",
  "is_terminal": true,
  "winner_id": "p1" or "p2",
  "final_scores": {},
  "replay_log": [ ... ends mid-turn, e.g. last entry is `deploy` in `main` phase ]
}
```

So the C engine **does** declare the game terminal and reports a winner, but:

1. `final_scores` is hard-coded to `{}` when the replay JSON is written.
2. The replay log stops at the last `apply_action` mid-turn with no terminal-state marker.
3. The C engine's `engine_winner()` and `compute_final_scores()` exist (`engine_c/bindings/ce_api.py:320,326`) and are reachable via `_adapter.final_scores()` / `state._game.get_player_ids()`-based winner lookup, but the values are **never persisted** to the replay payload.

The "ended without reaching terminal state" framing therefore most likely refers to the **replay artifact** not reflecting a true end-of-game record (empty `final_scores`, no end-of-game step), not to the engine itself.

## Root Cause (confirmed by code reading)

In `scripts/run_ismcts.py`:

- **Line 453–456 (Python-engine path) and line 1089–1092 (C-engine path)** correctly compute `final_scores` into a local variable.
- **Line 523 and line 1160** then build the replay payload with a hard-coded literal:

  ```python
  "final_scores": {},
  ```

  The `final_scores` value is silently dropped.

- **Line 522 and line 1159** compute `winner_id` from the OpenSpiel wrapper (`state._game.get_player_ids()[winner]`) instead of using the C engine's own `winner()` / `winner_id()` that is already exposed via the session/adapter. This works only when `is_terminal()` is true and the wrapper exposes `returns()`; if the C engine and wrapper ever disagreed, the wrapper path would silently drop the C engine's authoritative winner.

- **No terminal-step record** is appended to `replay_log` when the loop exits. The last logged entry is whatever the last `apply_action` produced (often `deploy` in `main` phase), so the replay has no explicit "game ended here" boundary.

## Verification Steps (TDD — write the failing test first)

1. **RED — write a failing test** in `tests/test_run_ismcts_replay_payload.py` that exercises the replay-payload-building code path with a stub state and asserts:
   - `final_scores` in the emitted `replay.json` matches `_compute_final_scores(state)` (non-empty dict when terminal, `{}` when non-terminal but the loop exited for other reasons).
   - `winner_id` matches the C-engine `adapter.winner(state)` (or the wrapper's authoritative path) when `is_terminal` is true.
   - When the game ends on a `terminal` stopped reason, the final `replay_log` contains a synthetic terminal marker entry (e.g. `{"move_type": "__terminal__", "round_number": final_round, "phase": final_phase}`) so consumers can detect the end.

2. **Verify RED** — run the new test, watch it fail for the right reason (assertion error on `final_scores == {}` after the fix-shaped assertion).

3. **GREEN — fix `scripts/run_ismcts.py`** at the two duplicate locations (lines 516–534 for the Python path, lines 1153–1171 for the C/wrapper path):
   - Replace `"final_scores": {}` with `final_scores` (use the local already computed at line 454 / 1090).
   - Prefer the C-engine adapter's `winner()` when present; fall back to the OpenSpiel wrapper path otherwise.
   - When `stopped_reason == "terminal"`, append a single terminal marker to `replay_log` so the replay file has a clear end boundary.

4. **Verify GREEN** — re-run the new test, the existing `tests/test_run_ismcts*.py` (if any) and `tests/test_game_simulation.py` and `just test`. All green, no warnings.

5. **REFACTOR** — extract a small helper `_build_replay_payload(state, ..., final_scores, winner_id, replay_log)` shared by both code paths to prevent the two sites from drifting again.

6. **Re-run a small IS-MCTS batch (2 games)** to regenerate replays with non-empty `final_scores` and confirm the new terminal marker is present. Sanity-check via the replay-viewer smoke test or a simple JSON load.

## Files Touched

- `scripts/run_ismcts.py` (two near-duplicate sites, lines ~516–534 and ~1153–1171) — fix payload builder.
- `tests/test_run_ismcts_replay_payload.py` (new) — failing test first, then green.
- No engine, no schema changes; the existing replay JSON schema gets two populated fields instead of empty placeholders.

## Out of Scope

- Changing the C engine's terminal-detection logic (the engine is correct; only the recorder is dropping the snapshot).
- Replaying the 298f153a3b56 runs (the user only asked to *figure out why*).
- Touching the replay viewer (the previous "simplify the replay viewer" ask is parked unless the user reopens it after this fix).
