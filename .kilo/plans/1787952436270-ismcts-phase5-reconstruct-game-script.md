# IS-MCTS Observability — Phase 5: `reconstruct_game.py` (the actual reconstruction deliverable)

## Prerequisite

Phases 1-3 (`1787952432270`, `1787952433270`, `1787952434270`) must be
merged first — this script is a pure reader over the files those phases
produce (`steps.jsonl` with Tier 1/2 state, structured `game_crashed`
lines). Phase 4 is not a hard dependency for the script to run, but its
output enriches the footer this script prints when `summary.json` is
available.

## Context

This is the deliverable that actually fulfills "reconstruct it from logs...
log by log, step by step, action by action, error by error" without
re-running the engine. Everything in phases 0-4 exists to make this script
possible; this script is where a human actually reads the result.

It must be a **pure log reader** — no `pyspiel`, no C-engine import, no
dependency on the game being re-runnable. This matters specifically because
it needs to work on a *crashed, partial* game directory, where re-running
anything is either impossible (the engine state that caused the crash is
gone) or exactly what we're trying to avoid.

Acceptance test for the whole five-phase series: run it against a game
directory produced by reproducing one of the two documented crash classes
in `docs/ismcts-generic-resolution-bugs.md`, and confirm the printed trace
correctly names which one fired — purely from what's on disk.

## Files touched

- `scripts/reconstruct_game.py` (new)
- `tests/test_reconstruct_game.py` (new)
- `justfile` (optional: add an `ismcts-reconstruct game_dir=...` recipe once the script exists and is verified — do this last, after manual verification, not as a TDD task)

## Design (reference while writing tests/code)

CLI (using `argparse`, matching the style of `scripts/run_ismcts.py`):

```
python -m scripts.reconstruct_game --game-dir artifacts/ismcts/game_0000
python -m scripts.reconstruct_game --output-dir artifacts/ismcts --game-index 0
python -m scripts.reconstruct_game --game-dir ... --with-policy
python -m scripts.reconstruct_game --game-dir ... --json
```

- `--game-dir <path>`: direct path to a `game_NNNN` directory. Mutually
  exclusive with `--output-dir` + `--game-index` (which compute the path
  the same way `_game_dir()` in `run_ismcts.py` does — reuse that function
  if importable without pulling in `pyspiel`; otherwise duplicate the
  one-line format string, since it's genuinely trivial: don't import a
  heavy module just for a path join).
- `--with-policy`: also loads `decisions.jsonl`, keyed by `step_index`
  (`node` field in `decisions.jsonl`'s existing schema — confirm the exact
  key name by re-reading a sample file before implementing), and appends
  `policy_entropy`/`chosen_action_prob` to each printed step line.
- `--json`: emit one JSON object per input event instead of formatted text
  (useful for piping into `jq` or another tool) — essentially a filtered
  passthrough of `steps.jsonl` with the optional decision-join merged in.
- Default (human-readable) output, streaming `steps.jsonl` line by line:
  - `"step"` event →
    ```
    Round {round_number} | {player_id} | {phase} | {label}
        VP={score} Power={resource_power} Influence={resource_influence} Hand={hand_size} Deck={deck_size} Discard={discard_size}
    ```
    plus, only when `"board"` is present in `"state"`, one line per node
    whose derived `controller` differs from the last board snapshot seen:
    ```
        Site {node_id}: control {old_controller or '-'} -> {new_controller or '-'}
    ```
    (track "last board snapshot seen" across the stream so this diff works
    even though board snapshots are sparse per phase 2's design).
  - `"game_crashed"` event → a clearly delimited block:
    ```
    === GAME CRASHED HERE (step {step_index}) ===
    Exception: {exception_type}: {exception_message}
    Attempted move: {attempted_move_label}
    Pending card: {pending_card_id}
    At failure: phase={phase_at_failure} round={round_number_at_failure} player={current_player_at_failure} is_terminal={is_terminal_at_failure}
    Legal moves at failure ({legal_moves_count_at_failure}): {legal_moves_at_failure}
    ```
  - `"game_end"` event → footer:
    ```
    === GAME END ===
    Winner: {winner_id}   Stopped reason: {stopped_reason}
    Final scores: {final_scores}
    ```
    then, if a sibling `summary.json` exists, print a short "Additional
    stats" section pulling in phase 4's `final_score_breakdown` and
    `action_semantic_counts` (guard with `if "final_score_breakdown" in
    summary: ...` so this degrades gracefully against pre-phase-4 summaries).
- Exit code: `0` on a game that ended normally, `1` on a game whose
  `steps.jsonl` ends with a `"game_crashed"` event (i.e., the script's own
  exit code can be used by a batch-scanning wrapper to find crashed games
  without parsing output — nice-to-have, include if it's a small addition,
  skip if it complicates the streaming design).

## TDD task list

### Task 5.1 — reads and formats a normal (non-crashed) game's steps

**RED**: In `tests/test_reconstruct_game.py` (new), write a small
`steps.jsonl` fixture by hand (a temp file with 3-4 `"step"` lines and one
`"game_end"` line, matching phases 1-2's exact schema — copy the shape from
a real file produced by `just ismcts-quick` after phases 1-2 are merged, to
guarantee the fixture isn't drifted from reality). Call the script's core
formatting function (e.g. `format_steps_jsonl(path) -> list[str]` or
similar — design it as an importable, testable function; the CLI's `main()`
should be a thin wrapper printing what this function yields) and assert the
output contains the expected `Round ... | ... | ... | ...` lines with
correct VP/resource values, and the `=== GAME END ===` footer with the
correct winner/scores. Confirm this **fails** first (function doesn't
exist).

**GREEN**: Implement the core formatter for `"step"` and `"game_end"`
events.

**REFACTOR**: none expected yet — Task 5.2 will add the crash-formatting
branch.

### Task 5.2 — crash block correctly identifies a known demon from a synthetic crash record

**RED**: Add to the fixture (or a second fixture) a `steps.jsonl` that ends
with a `"game_crashed"` line shaped exactly like phase 3's
`_build_crash_record` output for the `elder_brain` case (`pending_card_id:
"elder_brain"`, an empty-ish attempted move, etc. — construct this by hand
based on phase 3's documented shape, or better, capture a real one once
phase 3 is merged and the `elder_brain` scenario can be driven to failure).
Assert the formatted output contains the
`=== GAME CRASHED HERE (step N) ===` block with `Pending card: elder_brain`
visible. Do the same for a synthetic `kobold`/`ettin`/`weaponmaster`-style
crash record (two `"unavailable"`-tagged options). Confirm both **fail**
first.

**GREEN**: Implement the `"game_crashed"` formatting branch.

**REFACTOR**: If the human-readable formatter and a `--json` passthrough
mode share significant structure, extract a shared "parse one line into a
typed event" step that both the text formatter and the JSON mode consume,
rather than branching on `--json` deep inside formatting logic.

### Task 5.3 — `--with-policy` joins `decisions.jsonl` correctly by step index

**RED**: Extend the Task 5.1 fixture with a matching `decisions.jsonl`
(same step indices, with `policy`/`chosen_action_id` fields per its
existing real schema). Run with `--with-policy` and assert the formatted
step lines include the joined policy/entropy info, and that a step present
in `steps.jsonl` but missing from `decisions.jsonl` (simulate a schema
mismatch) degrades gracefully (prints the step without policy info,
doesn't crash the reconstruction tool itself — the reconstruction tool
crashing while reconstructing a crash would be a bad look). Confirm this
**fails** first.

**GREEN**: Implement the `decisions.jsonl` join.

**REFACTOR**: none expected.

### Task 5.4 — works on a *partial* (crashed, mid-game) directory with no `summary.json`/`replay.json`

**RED**: Build a fixture directory containing only a partial `steps.jsonl`
(a few `"step"` lines + one `"game_crashed"` line, no trailing
`"game_end"`) and no `summary.json` at all (matching what phase 1's crash
path actually leaves behind). Run the script against this directory and
assert it does not raise, prints all available steps plus the crash block,
and simply omits the "Additional stats" section (no `summary.json` to pull
from) instead of erroring. Confirm this **fails** first if the current
implementation assumes `summary.json` always exists.

**GREEN**: Guard the summary.json read with existence check /
try-except-and-skip, as already planned in Design.

**REFACTOR**: none expected.

## Verification

```
pytest tests/test_reconstruct_game.py -v
```

Then the full end-to-end proof for this entire five-phase series:

1. Reproduce a known crash with a batch sized toward the documented failure
   rates in `docs/ismcts-generic-resolution-bugs.md` (that doc's own repro
   recipe: `just ismcts 30 20 42 artifacts/ismcts/card_id_probe 8 4` — or an
   equivalent smaller batch, e.g.
   `just ismcts num_sims=50 num_games=8 seed=42 output_dir=artifacts/ismcts/repro_check workers=4 num_players=2`,
   adjusted upward if 8 games doesn't reliably reproduce one).
2. Find a crashed game directory (one whose `steps.jsonl` ends in
   `"game_crashed"`, or cross-reference `failures.jsonl`).
3. `python -m scripts.reconstruct_game --game-dir artifacts/ismcts/repro_check/game_000N`
4. Confirm the printed `=== GAME CRASHED HERE ===` block correctly names
   `pending_card_id` as `elder_brain` (or another card from the same-shape
   list in `docs/ismcts-generic-resolution-bugs.md`) for "demon one", or
   shows both attempted moves as `target_id='unavailable'` with
   `pending_card_id` in `{kobold, ettin, weaponmaster}` for "demon two" —
   entirely from what's printed, no source reading, no re-running.
5. Cross-check the same facts appear in the corresponding `failures.jsonl`
   line (phase 3's structured fields) as a consistency check between the
   two crash-record sinks.
6. Only after this manual verification succeeds, add the
   `just ismcts-reconstruct game_dir=...` recipe to `justfile` for
   convenience.
