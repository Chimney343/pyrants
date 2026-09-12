# A2 landing note — one seed stream + `--game-index-offset`

Status: **landed** 2026-09-12; diagnostic run the same day.
Plan: [`docs/ismcts-walltime-plan.md`](../ismcts-walltime-plan.md) § A2.

A2 adds `--game-index-offset N` to `scripts/run_ismcts.py` so a run plays the
*absolute* game indices `[N, N + num_games)` of one seed stream instead of
always starting at 0. It changes nothing about the search: every seed derived
from `game_index` (deck pair, default shuffle seed, per-seat bot seeds) is
computed from the absolute index, so an offset-sharded run reproduces exactly
the games an un-offset run would have played over the same indices. That is
what makes it safe to play the corpus as one very large invocation, or as a
handful of large, crash-resumable shards, instead of many small ones.

## Change set

| File | Change |
|---|---|
| `scripts/run_ismcts.py` | `_build_game_specs(..., game_index_offset=0)` factored out of `main()`; `--game-index-offset` CLI flag; `game_index_offset` threaded through `run_one_game`, `_run_one_game_standalone`, `_base_game_summary` (recorded in `summary.json`) and `build_manifest` (recorded in `manifest.config`) |
| `tests/test_run_ismcts_game_index_offset.py` | spec-level seed-derivation invariants (offset slice == un-offset slice; explicit `--shuffle-seed` still overrides; zero-offset identity) plus one real-engine `main()` run pinning absolute directory naming (`game_0003`, not `game_0000`) and summary/manifest fields |

## Why this is a wall-time lever at all

`scripts/run_ismcts.py` submits every game to a `ProcessPoolExecutor` up
front; a worker takes the next queued game the instant it frees up. With `W`
workers and `G` games, total wall is the greedy-scheduling *makespan* of `G`
job durations over `W` machines, plus a fixed per-invocation overhead
(imports, catalog load, pool spin-up/teardown — measured at **~0.6–0.7 s** via
a minimal `--num-games 1 --workers 1` invocation, so it does not matter at
these game durations). The corpus has been played as repeated **32-game**
invocations (`teacher_v3_32`'s own name). At `G = 32`, `W = 16`, each worker
only gets ~2 games, so the run's total wall is set by whichever worker draws
the two slowest games — a "wave tail" that is a large fraction of the total.
At `G = 1{,}000`, each worker gets ~63 games and the same tail is amortized to
~1.6% of the run. A2 does not change the per-simulation cost; it changes how
much of that structural tail loss the corpus pays.

## Diagnostic

Re-running real games at corpus scale to observe this would cost hours. The
scheduling policy above is fully determined by (a) each game's wall time and
(b) worker count, both already on disk from the A1 landing run
(`artifacts/ismcts/runs/20260912T092122Z_9d7e5da4a661`, 32 games,
`docs/validation/a1-infostate-hash-landing.md`). `scripts/simulate_batch_scheduling.py`
(new) replays that real per-game `wall_time_sec` list through the identical
earliest-free-worker greedy assignment `ProcessPoolExecutor` performs, so it
reproduces the actual scheduling — not an idealized `Σ/W` or a hand-waved
"two waves" estimate.

**Calibration.** Simulating the source run's own size (32 games) and worker
count (16) against its *own* measured wall (manifest `created_utc` → last
file write) is the check that the simulator isn't fooling itself:

```
python scripts/simulate_batch_scheduling.py \
    --run-dir artifacts/ismcts/runs/20260912T092122Z_9d7e5da4a661 \
    --workers 16 --batch-size 32 --target-games 1000
```

```
Calibration (simulate the source run's own size/workers vs. its measured wall):
  simulated wall : 1749.0s
  measured wall  : 1749.8s  (simulation error -0.0%)
```

Simulation error **-0.0%** — the greedy makespan model is exact for this
scheduler, so its extrapolation to corpus scale is trustworthy.

**Projection at the 1,000-game teacher-corpus target**, current practice
(32-game batches) vs. A2 (one continuous stream), extending the real 32-sample
duration list to 1,000 games:

| Policy | Invocations | Wall | games/h |
|---|---|---|---|
| batched (today: 32 × 32-game invocations) | 32 | 15.34 h | 65.2 |
| streamed (A2: 1 invocation) | 1 | 13.18 h | **75.9** |
| **ratio** | | | **×1.164** |

This lands at the top of the plan's `≈×1.1–1.15` estimate (§ 3, A2) and is
consistent with the pre-A1 baseline's own projection style ("40 → ~45 games/h
for free" was the same mechanism at the pre-A1 speed).

**Practical sharding curve.** A literal single 1,000-game invocation isn't
crash-resumable mid-run; A2's actual recommendation is "one invocation, *or*
offset-sharded invocations that resume where a killed run stopped." Sweeping
`--batch-size` shows how much of the gain survives sharding for resumability:

| Batch size | Invocations | games/h | Ratio to streamed |
|---|---|---|---|
| 32 (today) | 32 | 65.2 | ×1.164 |
| 64 | 16 | 69.1 | ×1.098 |
| 100 | 10 | 69.9 | ×1.085 |
| 200 | 5 | 73.3 | ×1.036 |
| 250 | 4 | 73.9 | ×1.027 |
| 500 | 2 | 75.0 | ×1.012 |
| 1000 (streamed) | 1 | 75.9 | ×1.000 |

Sharding into four 250-game offset-sharded invocations — a reasonable
crash-resumability granularity — already captures **97%** of the full gain
(73.9 vs 75.9 games/h). This is the operational recommendation: use
`--game-index-offset` with shards of a few hundred games, not 32.

## Gates

| Gate | Result |
|---|---|
| G0 determinism | `test_offset_specs_equal_unoffset_slice` / `test_offset_specs_use_absolute_index_for_seeds` / `test_zero_offset_is_identity`: offset specs' `game_index`, `shuffle_seed`, `deck_a_id`, `deck_b_id` are identical to the corresponding slice of an un-offset run |
| G1/G2/G3 (pipeline) | `pytest tests/test_run_ismcts_game_index_offset.py` and the full `run_ismcts`-adjacent test set (`test_build_nn_dataset`, `test_crash_diagnostics`, `test_run_ismcts_crash_capture`, `test_run_ismcts_decision_telemetry`, `test_run_ismcts_generic_context`, `test_run_ismcts_layer0`, `test_run_ismcts_replay_payload`, `test_run_ismcts_state_snapshots`, `test_run_ismcts_write_summaries`, `test_uct_sweep`) all green, no regressions; `ruff check` clean on the changed/new files |
| Real-engine offset run | `test_main_offset_writes_absolute_game_dir_and_summary`: `--game-index-offset 3 --num-games 1` writes `game_0003/` (not `game_0000/`), `summary.json["game_index"] == 3`, `manifest.json["config"]["game_index_offset"] == 3`, `manifest.json["games"][0]["shuffle_seed"] == 45` (= 42 + 3) |
| Throughput (supplementary, this note) | calibrated-simulation projection above: **×1.164** at the 1,000-game target, batch-size 32 vs streamed |

A2's own "done when" in the plan requires G0–G3 only (no G4/G-I — a pure
scheduling change has no per-sim cost or search output to compare). The
throughput projection above goes beyond that bar to answer the practical
question ("was the wall-time claim actually true?") without paying for a
multi-hour corpus-scale run.

## Risk

None to the search — offsets only change *which* absolute indices a process
computes, not how. The risk named in the plan (directory-naming collisions
across shards) is exercised by the real-engine test, which asserts the
written directory is `game_0003`, keyed by the absolute index.
