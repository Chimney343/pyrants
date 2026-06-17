# Plan: Additional Stats in `summary.json` for `just ismcts`

## Goal

Augment the per-game `summary.json` (and the cross-game `summary.csv` / `summary.md`)
written at the end of `scripts/run_ismcts.py` with stats that are useful for
debugging / characterising IS-MCTS runs but are not yet captured. Some are
trivial derivations from data already in scope (`move_latencies`, `decisions`,
the engine state at game-end); a few need new tracking.

## Current state

`scripts/run_ismcts.py:run_one_game()` writes `summary.json` per game with:
`run_id`, `game_index`, `shuffle_seed`, `deck_a_id`, `deck_b_id`,
`num_sims_per_move`, `uct_c`, `rollout_count`, `rollout_max_length`,
`policy_type`, `decision_count`, `wall_time_sec`, `sims_per_sec_avg`,
`returns`, `winner`, `score_diff`, `stopped_reason`, `max_rounds`
(`run_ismcts.py:352-372`). `_move_latencies` is kept in-memory only and
stripped from the dumped JSON (`run_ismcts.py:402`).

`RunMetrics` already aggregates cross-game percentiles into `metrics.json`,
but per-game percentiles / phase breakdown are missing from the per-game file.

`decisions.jsonl` already records `round`, `phase`, `current_player`,
`legal_action_ids`, `policy`, `chosen_action_id`, `chosen_move`,
`wall_time_ms`, `sims_requested` per decision — but no aggregations are
written.

## Proposed additions (grouped by source)

### 1. Latency / timing (derived from in-memory `_move_latencies`)

Add to `game_summary` in `run_one_game()`:
- `move_latency_ms`: `{count, mean, p50, p90, p95, p99, max}` — percentiles
  over the game's `move_latencies`. Reuse the same percentile helper from
  `scripts/_obs.py:RunMetrics._percentiles()`.
- `moves_per_sec_avg`: `decision_count / wall_sec` (more intuitive than
  `sims_per_sec_avg` which is dominated by sim count).

### 2. Phase breakdown (derived from decisions list, already populated)

For each game, build a `phase_breakdown` dict grouping decisions by `phase`:
```json
"phase_breakdown": {
  "start_of_turn": {"decisions": 42, "pct": 0.077},
  "main":         {"decisions": 320, "pct": 0.589},
  "end_of_turn":  {"decisions": 181, "pct": 0.333}
}
```
Iterate over `decisions` once, count `phase` occurrences, compute share.
Useful for spotting engines where one phase dominates sim cost.

### 3. Move-type / action-class breakdown (derived from `decisions`)

For each game, group `chosen_move.move_type` from `replay_log`
(replay_log already stores `move_type` per step at `run_ismcts.py:309`).
Counts of RECRUIT, PLAY, PROMOTE, KILL, CONTROL, EFFECT, END_TURN, etc.
Output as `move_type_counts: {move_type: n}` and a top-N list
`top_move_types: [[name, count], ...]`.

### 4. Information-set uniqueness / determinization coverage

- `unique_info_states`: number of distinct `info_state_sha256` values seen
  across the game's decisions. Already in `decisions.jsonl` as
  `info_state_sha256` (`run_ismcts.py:291`) — count uniques in one pass.
- `info_state_repeat_rate`: `1 - unique_info_states / decision_count`.
  A high repeat rate means the bot is revisiting similar situations —
  useful diagnostic for branching factor.

### 5. Policy entropy / decision confidence (from `decisions[].policy`)

For each decision the `policy` field is a `dict[int, float]`. Compute per-game:
- `policy_entropy_mean`: average Shannon entropy of the final policy
  (nats) over legal actions: `H = -Σ p * log(p)`.
- `policy_entropy_max`: max entropy observed.
- `chosen_action_prob_mean`: mean of `policy[chosen_action_id]` across
  decisions. Reflects how decisive the search was.
- `chosen_action_prob_p50` / `p90`: percentiles of the same.

If a move's policy dict is empty or chosen not present, skip it (defensive).

### 6. Engine-end snapshot (lightweight, no I/O)

`state._engine` is in scope at game-end. Capture:
- `final_round`: `state._engine.round_number` at terminal/cap.
- `final_scores_per_player`: dict `{player_id: score}` from
  `state._engine` score / influence view (existing structure; we already
  store `returns[0]`, `returns[1]` — this just makes the *per-player*
  names explicit). Read from `state._engine.players` score fields;
  Pydantic-typed, no I/O.
- `stopped_reason` is already present; ensure we always write
  `final_phase: <str(state._engine.phase.value)>` as well.

### 7. Determinism / replay integrity (cheap, high signal)

- `setup_data_sha256`: short sha256 of the `setup_data_json` actually
  used to load the game. Already computed for `info_state_sha256`
  via `_sha256()`; just compute once per game and stash. Lets you
  match replays across runs.
- `initial_state_sha256`: sha256 of the engine state right after
  `state.apply_action(shuffle_seed)` — anchor for reproducibility.

### 8. Tie / decisive outcome breakdown (cross-game only — leave per-game alone)

`summary.csv` / `summary.md` already record `winner` and `score_diff`.
Add a new field at the per-game level only if a game ended in a tie
(`returns[0] == returns[1]` within 1e-6):
- `outcome: "p0_win" | "p1_win" | "tie" | "truncated"`
  derived from `winner` + `stopped_reason`.

## Decisions (from user)

- **Layout:** flat, top-level keys. Each new stat is a sibling of the
  existing fields — no `analysis` sub-dict. Keeps `jq`-style queries
  trivial and matches today's shape.
- **Breakdowns:** include both the per-category dicts (`phase_breakdown`,
  `move_type_counts`) *and* the top-line aggregates. File grows by
  <2 KB per game in the worst case.
- **Stdout:** no. New stats are file-only (discoverable in `summary.json`
  / `summary.md`). Avoids duplicating the report in two places.

## What we explicitly are NOT adding (and why)

- **Per-tree MCTS stats** (UCT child stats, visit counts, value estimates):
  would require either monkey-patching `ISMCTSBot` or re-implementing the
  search. High effort, low ROI for a first pass.
- **Player-stratified breakdowns** (latency / entropy split by current
  player): possible but adds complexity for marginal signal. Defer.
- **Disk-full `policy` per decision in summary**: already in
  `decisions.jsonl`. Keep summary compact.

## Files to change

- `scripts/run_ismcts.py`
  - Extend the `game_summary` dict in `run_one_game()` (`run_ismcts.py:352`)
    with the new fields above.
  - Strip the new fields from `_move_latencies` exclusion logic
    (the exclusion is per-key prefix `_`, so the new fields will be
    written automatically — only need to ensure the helpers that
    compute them run before the write at `run_ismcts.py:401`).
  - Update `fieldnames` in `write_summaries()` (`run_ismcts.py:413`) to
    include the CSV-friendly subset (`decision_count`, `wall_time_sec`,
    `sims_per_sec_avg`, `moves_per_sec_avg`, `policy_entropy_mean`,
    `chosen_action_prob_mean`, `unique_info_states`, `final_round`,
    `outcome`, `setup_data_sha256`, `initial_state_sha256`).
  - Update the Markdown table header and rows at
    `run_ismcts.py:441-457` to surface the most useful new columns
    (keep it readable; ~12 columns max).
- `scripts/_obs.py`
  - No public API changes needed; the percentile helper stays in
    `RunMetrics._percentiles` and is reused (or we extract a small
    module-level helper so `run_ismcts.py` can import it).

## Implementation order

1. Extract `_percentiles` to a module-level helper in `_obs.py` (or
   keep it on `RunMetrics` and call it with a one-shot instance).
2. In `run_one_game()`, after the move loop, compute the new stats in
   one pass over `decisions` (for phase counts, info_state uniques,
   entropy, chosen-prob) and one pass over `move_latencies` (for
   percentiles). Both lists are already populated.
3. Add engine-end snapshot reads (final_round, final_phase, player
   scores) — pure attribute reads on `state._engine`, no extra cost.
4. Compute `setup_data_sha256` and `initial_state_sha256` once near
   the top of `run_one_game()` (after `state.apply_action(shuffle_seed)`).
5. Extend `game_summary` dict; update CSV `fieldnames`; widen the
   Markdown table by ~3 columns and document the new shape in the
   summary header comment block.
6. Run `just ismcts-quick` to confirm shape and that existing
   `tests/test_*ismcts*` (if any) still pass; otherwise run
   `just test` for the engine suite.
7. Run `ruff check .` per AGENTS.md.

## Verification

- Diff two consecutive `just ismcts-quick` runs with the same seed:
  `setup_data_sha256` and `initial_state_sha256` should be stable;
  `decision_count`, `returns`, `winner` should be identical.
- On a real `just ismcts num_sims=200 num_games=4` run, confirm
  `summary.json` parses with `json.load`, that the new fields are
  present, and that no regression in `metrics.json` shape.
- Quick `ruff check scripts/run_ismcts.py scripts/_obs.py` to make
  sure no unused imports / line length issues.

## Resolved questions

All design questions resolved (see "Decisions" above):
- Layout: flat top-level keys
- Breakdowns: aggregates + per-category dicts
- Stdout: file-only
