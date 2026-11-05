# A3 landing note — arena recycling (option a)

Status: **landed** 2026-09-12.
Plan: [`docs/ismcts-walltime-plan.md`](../ismcts-walltime-plan.md) § A3, option (a).

`engine_random_rollout` advances its private chain of clones one `engine_apply`
at a time, and every apply is `engine_apply = engine_clone + apply_*` (the
no-op `engine_clone_cow` wrapper was removed in the 0.4 cleanup).
`engine_clone` (`engine_c/state.c:175`) calls `arena_create(512 * 1024)`, so the
hot loop paid one 512 KiB `malloc` per step and one `free` of the previous
step's arena, ~1.3–2.0 µs inside an ~8–10 µs step. Option (a) replaces the
allocator round trip with a small per-process free-list of destroyed hot-path
arenas, without changing a single rollout decision.

## Change set

| File | Change |
|---|---|
| `engine_c/arena.c` | Per-thread pool of up to `ARENA_POOL_CAP` (64) destroyed single-block `ARENA_POOL_BLOCK_SIZE` (512 KiB) arenas. `arena_destroy` parks a matching arena instead of freeing it; `arena_create` pops the most recent one and restarts the bump pointer; everything else (grown arenas, definition/test-sized blocks) is freed as before. Added `arena_free`, `arena_pool_count`, `arena_pool_clear`. |
| `engine_c/arena.h` | `ARENA_POOL_CAP` / `ARENA_POOL_BLOCK_SIZE` and the pool diagnostics/cleanup declarations, with the contract and the thread-local ownership documented. |
| `engine_c/tests/test_rollout.c` | Five new tests: reuse of a destroyed arena, reset of a reused block's bump pointer, bounded pool + clear, non-hot-path arenas not retained, and rollout scores independent of pool state. Tested under the normal and ASan builds. |

Pool policy: only a single-block arena whose capacity is exactly 512 KiB is
retained, so the pool is bounded at 64 × 512 KiB ≈ 32 MiB and the 2 MiB/16 MiB
definition/test arenas are never held. The pool is thread-local, so each thread
recycles its own arenas and a threaded host cannot hand one arena to two live
states.

## Byte-identity

Gate (iii) — 1000 `(state, seed)` pairs through `engine_random_rollout`
(unbounded 2p from seed-varied fresh states) run on the pre-change and
post-change `libengine.lib`:

```
CHECKSUM 2375144156626933491   (before)
CHECKSUM 2375144156626933491   (after)
FC: no differences encountered
```

The pool tests also pin that a reused block's bump pointer restarts at the base
and that a rollout's scores do not depend on pool state.

## Per-rollout A/B

`clock()` over 300 unbounded 4-player rollouts from one fresh state
(`seed 42`), same binary harness before/after:

| | total (ms) | ms/rollout | vs before |
|---|---|---|---|
| before | 1651.0 | 5.5033 | — |
| after (A3a) | 1241.0 | 4.1367 | **×1.330** (−24.8 %) |

That is the rollout path alone, which § 1 puts at 57–67 % of a decision, so the
whole-decision lever is the games/h figure below.

## Paired run (G-I + G4)

Re-played the A1 landing run (`artifacts/ismcts/runs/20260912T092122Z_9d7e5da4a661`,
the byte-identical teacher baseline) flag-for-flag: `--num-sims 200
--num-games 32 --seed 42 --workers 16 --num-players 4 --uct-c 1.4
--game python_pyrants_c --no-steps`, then
`scripts/compare_paired_runs.py`. Candidate:
`artifacts/ismcts/runs/20260912T205526Z_681b301037a3`.

**G-I — content identical on all 32 paired games: True.** Per game
`decisions.jsonl` and `replay.json` match after dropping `run_id`/wall-clock
fields and `final_decks.json` is byte-equal. The only search-relevant config
difference is `game_index_offset` (A2 added the key after the baseline run was
recorded; it defaults to 0 and does not touch the search).

**G4 — throughput:**

| | baseline (A1) | candidate (A3a) | ratio |
|---|---|---|---|
| run wall | 1749.8 s | 1584.8 s | ×1.104 |
| games/h (run wall) | 65.8 | **72.7** | ×1.105 |
| games/h (ideal, Σ game wall / workers) | 76.9 | **87.6** | ×1.139 |
| per-game wall ratio (median / mean / sum) | — | — | ×1.126 / ×1.139 / ×1.138 |

Per-game ratios span 0.97–1.48 (one game at 0.97 is scheduler noise inside the
paired run); `sims_per_sec_avg` rises across the board, e.g. game 0
326.1 → 347.1. The measured ×1.10–1.14 sits at the top of the plan's estimated
`×1.10–1.17`.

## Gates

| Gate | Result |
|---|---|
| (i) C tests | `just build-c` / `just test-c` green; `test_rollout` includes the five new pool tests |
| (ii) ASan | `compile_asan.bat` (all C binaries) clean, including the pool tests |
| (iii) rollout equivalence | 1000 pairs identical (checksum above) |
| (iv) G-I | 32/32 paired games content-identical |
| (v) G4 | ×1.33 per rollout; 65.8 → 72.7 games/h run wall |
| G0/G1/G2 | `just ismcts-quick`: 2 × 4p replays OK, strict dataset build, leak check 0 mismatches |
| G3 | `just test-all`: 14 failures = the tolerated set exactly — F-015 ×3 (`test_card_zuggtmoy`, `test_engine_c` air elemental, `test_card_neogi`), F-003 ×10 (`test_chance_nodes`), F-013 G1 (`test_private_view_json_byte_identical_to_reference`, red while F-034 stands) |

## Review follow-up

A local review raised two non-blocking items, both fixed before commit: the
reuse path's overflow-block drop loop was unreachable (the pool admits
single-block arenas only) and is now replaced by an `assert(head->next == NULL)`;
and the pool statics became thread-local (`__declspec(thread)` / `_Thread_local`)
so a threaded host cannot hand one arena to two live states. Re-verified after
the fixes: the 1000-pair dump is still byte-identical, the per-rollout A/B
re-measures 4.00 ms/rollout (vs. 5.50 before), and the ASan suite is still clean.

## Risk

The one way to get this wrong is to reuse an arena without resetting it, which
would leak stale bytes into a clone and move scores; the reset path and the
pool-state rollout test cover it, and the 32-game paired run is the end-to-end
proof. The pool is thread-local and holds ≤ 32 MiB per thread until
`arena_pool_clear()`/process exit. Separately, `engine_c/compile_asan.bat` is
checked out with LF line endings in the current working tree, so `cmd` garbles
it; it was run via a CRLF copy for this note. That is pre-existing and
unrelated to A3.
