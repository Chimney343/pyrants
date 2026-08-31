# IS-MCTS Observability — Phase 4: After-Game and Batch-Level Stats

## Prerequisite

Phase 2 (`1787952433270-ismcts-phase2-per-step-state-snapshots.md`) must be
merged first — every stat in this phase is computed from the Tier 1/Tier 2
snapshots phase 2 adds to `steps.jsonl`. Phase 3 is not a hard dependency,
but the batch-level `crash_report` (Task 4.4 below) needs phase 3's
structured `failures.jsonl` fields to be meaningful rather than just
counting raw tracebacks.

## Context

`game_summary` (`scripts/run_ismcts.py:446-484`) already captures solid
*bot-behavior* stats: decision latency percentiles, phase breakdown,
move-type histogram, policy entropy, chosen-action-probability stats,
info-state repeat rate. It captures almost nothing about *game strategy or
outcome mechanics* — no VP arc, no resource efficiency, no site-control
story, no breakdown of *why* a player won. `docs/tyrants-rulebook.md`
provides the exact vocabulary for what's missing: unspent Power/Influence
is lost every turn ("Resource Pool"), Control vs. Total Control changes
hands based on troop majority and spy presence ("Control"/"Total Control"),
and Final Scoring is an explicit sum of five components (site control VP,
total-control VP, trophy-hall troop count, deck/hand/discard card VP
values, inner-circle VP values, VP tokens — "Final Scoring", page 14).

Separately, the base `Move` type vocabulary
(`engine_c/bindings/ce_api.py`) doesn't include `move troop`, `place spy`,
`devour`, `supplant` as first-class move types — they only appear inside
`resolve_generic_choice` payloads' `action_id` field. Today's
`move_type_counts` (`run_ismcts.py:406-412`) buckets all of these under one
`"resolve_generic_choice"` count (or whatever the base move type string is
— confirm the exact string before implementing), hiding the actual action
mix. This phase unpacks it.

All additions in this phase are **additive** to `summary.json` — no
existing key is renamed or removed.

## Files touched

- `scripts/run_ismcts.py` (`run_one_game()` post-loop stat computation, `write_summaries()`)
- `tests/test_game_stats.py` (new)
- `tests/test_batch_reports.py` (new)

## Design (reference while writing tests/code)

Per-game additions to `game_summary`, computed from `replay_log`,
`decisions`, and the Tier 1/2 snapshots recorded in `steps.jsonl` during the
loop (no extra engine calls needed — collect the raw ingredients as
in-memory lists during the loop, same as `decisions`/`replay_log` already
are, then reduce them once at the end):

1. `vp_trajectory`: list of `{round_number, player_id, score, vp_tokens,
   trophy_hall_size, controlled_sites, total_control_sites}` sampled at each
   Tier-2 (round-boundary) snapshot, for the then-current player (and,
   where cheap, for all players via the per-player Tier-1 fields already
   captured at that same step).
2. `resource_waste`: per player, sum of `resource_power` / `resource_influence`
   values from the last Tier-1 snapshot recorded before `current_player_id`
   changes to someone else (i.e., the pool value one step before it's lost
   per the rulebook). Track "last seen resource values for the player whose
   turn is ending" as you iterate the collected step snapshots once at the
   end (don't try to detect this inline during the main loop — keep the
   loop itself simple and do this as a post-processing pass over the
   already-collected per-step state list).
3. `site_control_changes` / `most_contested_sites`: iterate consecutive
   Tier-2 board snapshots, diff each `node_id`'s derived controller
   (`_derive_site_controller`, from phase 2) between snapshots, count flips
   per node; `most_contested_sites` = top N nodes by flip count.
4. `action_semantic_counts`: merge base `move_type_counts` with unpacked
   `resolve_generic_choice` `action_id` values from `replay_log` payloads —
   produces a single dict like `{"assassinate": 3, "deploy": 12,
   "recruit": 8, "supplant_troop": 2, "devour_cost": 1, "place_spy": 4,
   "move_troop": 1, ...}`.
5. `card_play_counts` / `aspect_play_counts`: tally `card_id` from
   `play_card`/`recruit`/`promote_card` payloads in `replay_log`; join
   against the card catalog for `aspect` (reuse whatever catalog-loading
   helper `engine_c/bindings/view.py` already uses for
   `_compute_player_card_aspects`/`_make_card_view` — check
   `game_setup`'s catalog assembly entry point rather than re-parsing
   `data/cards/*.json` directly).
6. `final_score_breakdown`: per player, `site_control_vp,
   total_control_vp, trophy_hall_vp (troop_count * 1), deck_hand_discard_vp
   (sum of catalog deck_vp for cards in deck+hand+discard),
   inner_circle_vp (sum of catalog inner_circle_vp), vp_tokens` — computed
   from the final Tier-2 board snapshot plus final per-player card lists
   (available via `adapter._build_public_dict()` at game end, same as
   `final_scores_per_player` already does).
7. `turn_action_counts`: mean/p50/p90 (reuse `compute_percentiles` from
   `scripts/_obs.py`) of actions-per-turn, derived by counting
   `replay_log` entries between consecutive `current_player_id` changes.

Batch-level additions, in `write_summaries()`:

8. `deck_matchups.csv` / `.md`: group `summaries` by
   `frozenset({s["deck_a_id"], s["deck_b_id"]})` (unordered pair); for each
   group compute games played, wins per deck id, ties, mean score margin,
   mean `final_round`.
9. Game-length-in-rounds percentiles (`compute_percentiles` on
   `[s["final_round"] for s in summaries]`), added into `summary.md` and
   `metrics.json`.
10. `crash_report.md` / `.json`: read `<output_dir>/failures.jsonl` (if
    present), compute `crash_rate = crashes / (crashes + len(summaries))`,
    group by `exception_type`, group by `pending_card_id` (from phase 3's
    structured fields — falls back to `"unknown"` if a line predates phase
    3 or lacks the field), and by `attempted_move_type`.

## TDD task list

### Task 4.1 — `vp_trajectory` and `resource_waste` reflect rulebook mechanics

**RED**: In `tests/test_game_stats.py` (new), construct a small synthetic
list of Tier-1/Tier-2 step-snapshot dicts (plain Python dicts shaped like
what phase 2 produces — no need to run a real game) representing: player
p1's turn with resource_power going 0→3→0 (spent) then p2's turn starting
with p1's pool reset; a round boundary partway through. Call a new
`compute_vp_trajectory(steps)` and `compute_resource_waste(steps)` (pure
functions, take the list of parsed step dicts, return the documented
shapes) and assert:
- `vp_trajectory` has one entry per round-boundary snapshot with the
  expected `score`/`vp_tokens`/etc.
- `resource_waste["p1"]["power_wasted_total"]` equals the sum of
  power-pool values captured immediately before p1's turn ends (construct
  the synthetic data so this is a known, hand-computed number, e.g. p1
  ends a turn with `resource_power=2` unspent once — expect
  `power_wasted_total == 2`).

Confirm these **fail** first.

**GREEN**: Implement `compute_vp_trajectory` and `compute_resource_waste` as
pure functions in `scripts/run_ismcts.py` (or a new `scripts/_game_stats.py`
if you prefer keeping `run_ismcts.py` from growing further — recommended,
mirroring how `_obs.py`/`_replay_payload.py` are already split out; import
from there).

**REFACTOR**: If `run_one_game()`'s post-loop section is getting long
threading these new computations through, extract a single
`_compute_game_stats(replay_log, decisions, step_snapshots) -> dict`
orchestrator that calls each of Tasks 4.1-4.4's functions and merges their
outputs into one dict to be spread into `game_summary`. Keep each
individual compute function small and independently testable; only the
orchestrator needs to live in `run_ismcts.py`.

### Task 4.2 — `site_control_changes` counts controller flips correctly

**RED**: Construct synthetic consecutive Tier-2 board snapshots (reuse
`_derive_site_controller` from phase 2 — this task assumes phase 2's
helper is available) where node `"site_a"` flips from `"p1"` to `"p2"` once
and node `"site_b"` never changes controller. Call
`compute_site_control_changes(board_snapshots)` and assert `site_a` shows 1
flip, `site_b` shows 0, and `most_contested_sites` (with `top_n=1`) returns
`["site_a"]`. Confirm this **fails** first.

**GREEN**: Implement `compute_site_control_changes`.

**REFACTOR**: none expected.

### Task 4.3 — `action_semantic_counts` unpacks `resolve_generic_choice` action ids

**RED**: Construct a synthetic `replay_log` with a mix of base move types
(`deploy`, `recruit`) and `resolve_generic_choice` entries whose `payload`
has `action_id` values (`"assassinate_troop"`, `"supplant_troop"`,
`"deploy_troops"`). Call `compute_action_semantic_counts(replay_log)` and
assert the returned dict has separate counts for `deploy`, `recruit`,
`assassinate_troop`, `supplant_troop`, `deploy_troops` — i.e., the
`resolve_generic_choice` bucket is fully unpacked, not present as its own
key in the output. Confirm this **fails** first.

**GREEN**: Implement `compute_action_semantic_counts`. If phase 2 already
extracted a shared action-id vocabulary constant (per phase 2's optional
Task 2.3 refactor note), reuse it here instead of re-listing the action ids.

**REFACTOR**: none expected.

### Task 4.4 — batch-level `deck_matchups` and `crash_report` roll-ups

**RED**: In `tests/test_batch_reports.py` (new), construct a synthetic
`summaries` list (5-6 dicts with varying `deck_a_id`/`deck_b_id`/`winner`/
`final_round`) and a synthetic `failures.jsonl`-shaped list of dicts (2-3
entries with different `exception_type`/`pending_card_id`). Call
`write_deck_matchups(tmp_path, summaries)` and `write_crash_report(tmp_path,
failures)` and assert the output files exist and contain the expected
aggregated counts (e.g. deck pair `{"drow","dragons"}` shows 3 games, 2
wins for `"drow"`, 1 tie; crash report shows `crash_rate` computed
correctly and a `by_pending_card_id` breakdown matching the synthetic
input). Confirm these **fail** first (functions don't exist).

**GREEN**: Implement `write_deck_matchups` and `write_crash_report`, call
both from `write_summaries()` (or immediately after it, from `main()`) —
whichever keeps `write_summaries()` from growing too many responsibilities;
prefer three separate small functions called in sequence from `main()`
over one large function.

**REFACTOR**: Confirm `main()`'s call site reads cleanly as a short
sequence: `write_summaries(...)`, `write_deck_matchups(...)`,
`write_crash_report(...)` — not nested inside `write_summaries()` itself.

## Verification

```
pytest tests/test_game_stats.py tests/test_batch_reports.py -v
just ismcts num_sims=20 num_games=6 seed=42 output_dir=artifacts/ismcts/phase4_check workers=1 num_players=2
```
Inspect `artifacts/ismcts/phase4_check/game_0000/summary.json` for the new
per-game keys (`vp_trajectory, resource_waste, site_control_changes,
most_contested_sites, action_semantic_counts, card_play_counts,
aspect_play_counts, final_score_breakdown, turn_action_counts`) and confirm
`final_score_breakdown`'s components sum to (approximately) the existing
`final_scores_per_player` value for each player — this cross-check is the
real correctness proof for Task 4.1/4.2's rulebook-fidelity, not just the
unit tests. Inspect `artifacts/ismcts/phase4_check/deck_matchups.md` and
`crash_report.md` (or `.json`) for sane aggregated output.
