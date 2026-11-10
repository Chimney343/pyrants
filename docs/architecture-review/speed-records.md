# Speed records

Durable transcription of every speed claim in the ADRs. Run directories live
under `artifacts/`, which is gitignored, so the numbers below — not the
directories — are the record.

Re-verified 2026-11-09 with `scripts/compare_paired_runs.py` (B1). Every
number the ADRs report for a paired run reproduced from the run directories;
the only claims not re-run are the micro-benchmarks, marked as such.

## Method and how to read a pair

- A paired run is 32 games (or the quick check's 8) at a fixed seed; the two
  sides must use the same config or the pair is not a measurement.
- `scripts/compare_paired_runs.py` compares `decisions.jsonl`,
  `final_decks.json` and `replay.json` per game. `replay_context` records
  absolute data paths, so a pair built in separate worktrees always differs
  there; that field is not a behaviour signal.
- **Identity is the DLL sha256 when the tree is dirty.** `engine_git_sha` alone
  does not distinguish two builds from the same commit with different
  uncommitted changes; the DLL hash does. Every row below carries both.
- The same-build noise floor is not negligible. Two runs of one DLL
  (`20261105T095031Z_2cce3444a48a` → `20261105T112058Z_2951188cc189`, both
  `f3fd1f11c746…`) measure 77.6 → 82.4 run-wall games/h — a 6.2 % spread from
  run-to-run alone, and a per-game median ratio of 1.074 (range 0.976–1.183).
  Treat differences under roughly 8 % as noise and compare only paired runs.
- `--uct-c 1.4` is required for anything compared against these records: the
  `scripts/run_ismcts.py` default is 5.0.

## Run inventory

All rows verified against each run's `manifest.json` on 2026-11-09. "engine
dirty" is `engine_git_dirty`; "repo dirty" is `repo_git_dirty`.

| run id | engine sha | engine dirty | repo dirty | DLL sha256 (12) | created (UTC) | config |
|---|---|---|---|---|---|---|
| `20261106T103544Z_7bd2f09610e6`¹ | none | False | False | `5174b755135c` | 2026-11-06T10:35:45Z | 32g/200s/16w/uct1.4/seed42 |
| `20261106T105757Z_b6be8d1087e6` | `53cf800340a5` | True | True | `cc7e66c611c9` | 2026-11-06T10:57:57Z | 32g/200s/16w/uct1.4/seed42 |
| `20261106T112844Z_df41f11c7216` | `53cf800340a5` | True | True | `59a163d27084` | 2026-11-06T11:28:45Z | 32g/200s/16w/uct1.4/seed42 |
| `20261106T164410Z_f5f647468a20` | `57e0883f0616` | True | True | `1899a19f2ca3` | 2026-11-06T16:44:10Z | 32g/200s/16w/uct1.4/seed42 |
| `20261106T191411Z_bda107c0eaf4` | `f355e4fe255a` | True | True | `69e80052d0fb` | 2026-11-06T19:14:11Z | 32g/200s/16w/uct1.4/seed42 |
| `20261106T193628Z_ca5eea69c707` | `a985208ebf8d` | False | False | `6be54e859db7` | 2026-11-06T19:36:29Z | 32g/200s/16w/uct1.4/seed42 |
| `20261106T195809Z_5513a9602b65` | `a03768faab1e` | False | False | `4ad07bc29cc8` | 2026-11-06T19:58:10Z | 32g/200s/16w/uct1.4/seed42 |
| `20261106T223242Z_2a13dd651080` | `ff42ad67a7dd` | False | False | `0925afcdebaa` | 2026-11-06T22:32:43Z | 8g/50s/8w/uct1.4/seed42 |
| `20261106T223244Z_c81a938a83de` | `f9bec9bed55c` | True | True | `5c79d21ddec7` | 2026-11-06T22:32:44Z | 8g/50s/8w/uct1.4/seed42 |
| `20261109T123044Z_59d40db79464`² | `aa04bb03e51f` | False | True | `a7ca31cd3e04` | 2026-11-09T12:30:44Z | 8g/50s/8w/uct1.4/seed42 |
| `20261109T123258Z_f86a57cd3aaf`² | `aa04bb03e51f` | True | True | `065182538c6a` | 2026-11-09T12:32:59Z | 8g/50s/8w/uct1.4/seed42 |
| `20261109T145355Z_c0d69d87c9c2` | `f68fb8801c2e` | False | True | `5e6ecfb53d19` | 2026-11-09T14:53:55Z | 8g/50s/8w/uct1.4/seed42 |
| `20261109T145118Z_524e06781560` | `f68fb8801c2e` | True | True | `3ac2087ab621` | 2026-11-09T14:51:18Z | 8g/50s/8w/uct1.4/seed42 |
| `20261110T201057Z_d19383e1047a`³ | `76dc1d44a4f1` | False | False | `d26c8d89246f` | 2026-11-10T20:10:57Z | 8g/50s/8w/uct1.4/seed42 |
| `20261110T201336Z_9045b5ad3a86`³ | `76dc1d44a4f1` | True | True | `9ad79f459a64` | 2026-11-10T20:13:36Z | 8g/50s/8w/uct1.4/seed42 |

¹ The baseline `7bd2f09610e6` is **outside the repo**, under
`%TEMP%\kilo\a985208_runs\`; its manifest is schema v2 and has no
`engine_git_sha`. It cannot be tied to a commit, so any comparison against it
is indicative only.

² The A1 quick-check pair lives **outside the repo**, under
`%TEMP%\kilo\a1\runs\`. The numbers are transcribed here because the directory
is not durable.

³ The B2 baseline ran from the `C:\Users\mkkom\pyrants-b2-base` worktree at the
parent commit, so its `replay_context` differs from the candidate's; both
manifests record engine sha `76dc1d44a4f1` (the candidate's tree is dirty only
by the B2 edit itself). The run directories are under
`artifacts/ismcts/b2_quickcheck/`.

## ADR-0004: 13 op migrations (`a985208` → `a03768f`)

Claim: "identical decisions on all 32 games", 88.6 → 89.5 run-wall games/h,
per-game median ×1.031.

| | baseline | candidate |
|---|---|---|
| engine git sha | `a985208ebf8d` | `a03768faab1e` |
| run id | `20261106T193628Z_ca5eea69c707` | `20261106T195809Z_5513a9602b65` |
| tree dirty | engine False / repo False | engine False / repo False |
| DLL sha256 | `6be54e859db7…` | `4ad07bc29cc8…` |
| run wall | 1300.3 s | 1286.8 s |
| games/h (run wall) | 88.6 | 89.5 |
| games/h (ideal) | 106.2 | 107.7 |

- `decisions.jsonl` identical on 32/32 games; `final_decks.json` identical on
  32/32; 37,596 decisions on both sides.
- `replay.json` differs on 32/32 games **only** in `replay_context` — the two
  runs were built in separate worktrees with different absolute data paths.
- Per-game wall ratio median 1.031, mean 1.015, range 0.686–1.089; sum-wall
  ratio 1.014.
- **Verdict: the ADR claim holds.**

## ADR-0004: op descriptor cache (`53cf800` → `57e0883` pre-commit tree)

Claim: "identical on all 32 games", 83.2 → 86.2 run-wall games/h, per-game
median ×1.031. This is the claim the 2026-11-07 audit called unsupported.

| | baseline | candidate |
|---|---|---|
| engine git sha | `53cf800340a5` | `53cf800340a5` |
| run id | `20261106T105757Z_b6be8d1087e6` | `20261106T112844Z_df41f11c7216` |
| tree dirty | engine True / repo True | engine True / repo True |
| DLL sha256 | `cc7e66c611c9…` | `59a163d27084…` |
| run wall | 1384.0 s | 1336.7 s |
| games/h (run wall) | 83.2 | 86.2 |
| games/h (ideal) | 98.5 | 101.8 |

- Both runs are from a dirty tree at the same commit (`53cf800`); the cache
  was the uncommitted change later committed as `57e0883`. Identity is the
  DLL hash, and the two hashes differ.
- `decisions.jsonl`, `final_decks.json` **and** `replay.json` are identical on
  32/32 games; 38,550 decisions on both sides.
- Per-game wall ratio median 1.031, mean 1.034, range 0.958–1.090; sum-wall
  ratio 1.033.
- **Verdict: the ADR claim holds.** The audit's "Unsupported / Contradicted"
  came from pairing each candidate against a third baseline (`7bd2f09`), not
  against each other; those files compare different builds and naturally show
  search differences.

## ADR-0004: committed `57e0883` rerun

`20261106T164410Z_f5f647468a20` (`57e0883f0616`, dirty, DLL `1899a19f2ca3…`)
measured 83.7 run-wall games/h. Verified.

## ADR-0004: HEAD against `a985208` (not a candidate measurement)

| | `a985208` | HEAD `f355e4f` |
|---|---|---|
| run id | `20261106T193628Z_ca5eea69c707` | `20261106T191411Z_bda107c0eaf4` |
| DLL sha256 | `6be54e859db7…` | `69e80052d0fb…` |
| games/h (run wall) | 88.6 | 86.8 |
| games/h (ideal) | 106.2 | 102.5 |
| decisions | 37,596 | 38,550 |

- Per-game wall ratio median 0.979, mean 0.971, range 0.766–1.307.
- HEAD plays 2.5 % more decisions (38,550 / 37,596 = 1.025), because F-015
  (`2163a45`, ADR-0005) changed the rules between the two commits; the games
  are not the same, so this is not a speed regression.
- Per decision, summed game wall is 466.5 ms against 461.7 ms — 1.04 % higher,
  inside noise.

## ADR-0006: pending decision module (`57e0883` → `f355e4f`)

Claim: all 32 games content-identical; 83.7 → 86.8 run-wall games/h; per-game
median ×1.015 (range 0.964–1.076).

| | baseline | candidate |
|---|---|---|
| engine git sha | `57e0883f0616` | `f355e4fe255a` |
| run id | `20261106T164410Z_f5f647468a20` | `20261106T191411Z_bda107c0eaf4` |
| tree dirty | engine True / repo True | engine True / repo True |
| DLL sha256 | `1899a19f2ca3…` | `69e80052d0fb…` |
| run wall | 1376.3 s | 1326.9 s |
| games/h (run wall) | 83.7 | 86.8 |
| games/h (ideal) | 100.4 | 102.5 |

- `decisions.jsonl`, `final_decks.json` and `replay.json` identical on 32/32
  games; 38,550 decisions on both sides.
- Per-game wall ratio median 1.015, mean 1.020, range 0.964–1.076.
- **Verdict: the ADR claim holds.**

## ADR-0007 step 1: visibility module, quick check

Claim: `decisions.jsonl` and `final_decks.json` identical on 8/8 games, 9,368
decisions, only `replay_context` differs.

| | pre-candidate | step 1 |
|---|---|---|
| engine git sha | `ff42ad67a7dd` | `f9bec9bed55c` |
| run id | `20261106T223242Z_2a13dd651080` | `20261106T223244Z_c81a938a83de` |
| tree dirty | engine False / repo False | engine True / repo True |
| DLL sha256 | `0925afcdebaa…` | `5c79d21ddec7…` |

- 8 games at 50 sims, 8 workers, `--uct-c 1.4`, seed 42.
- `decisions.jsonl` identical on 8/8; `final_decks.json` identical on 8/8;
  9,368 decisions; `replay.json` differs on 8/8 only in `replay_context`.
- **Verdict: the ADR claim holds.**

The ADR also reports micro-benchmarks on 118 playout states: tree-key hash
1.45 µs/call against 1.05 µs for the hand-written hash, and a cold view of
about 57 µs against 107 µs for the Python projection. **Reported, not
re-verified**: the hand-written hash and the Python projection it was compared
against have both been removed, so the comparison cannot be re-run. The
~1 ms of an average ~466 ms decision figure is the delta (0.4 µs × ~2,500
calls), not the absolute cost.

## ADR-0007 A1: no player's search knows its own deck order

Claim: games/h 225.8 → 222.4 run wall, ideal 298.2 → 271.5, per-game median
0.954, mean 0.912; decisions change on every game (expected).

| | parent `aa04bb0` | A1 |
|---|---|---|
| run id | `20261109T123044Z_59d40db79464` | `20261109T123258Z_f86a57cd3aaf` |
| tree dirty | engine False / repo True | engine True / repo True |
| DLL sha256 | `a7ca31cd3e04…` | `065182538c6a…` |
| run wall | 127.5 s | 129.5 s |
| games/h (run wall) | 225.8 | 222.4 |
| games/h (ideal) | 298.2 | 271.5 |

- 8 games at 50 sims, 8 workers, `--uct-c 1.4`, seed 42. Both trees at
  `aa04bb0`; the candidate had A1 uncommitted, hence different DLL hashes.
- Decisions differ on 8/8 games with `policy`, `visit_counts`, `q_values`
  differing from line 0 — the expected result of resampling the observer's
  deck. Per-game wall ratio median 0.954, mean 0.912, range 0.610–1.173.
- **Verdict: the ADR claim holds.**

Determinization micro-benchmarks (`scripts/bench_determinize.py`, 118 playout
states, 6,000 calls, three runs per build): mean 3.96–4.23 µs → 4.68–5.56 µs,
median 3.2–3.3 µs → 3.9–4.1 µs. **Reported, not re-run.**

## ADR-0008: owners' visibility rule (A2)

Claim: 214.1 → 202.9 run-wall games/h, ideal 263.0 → 250.7, per-game median
0.933, mean 0.974; content differs on every game (expected).

| | parent `f68fb88` | A2 |
|---|---|---|
| run id | `20261109T145355Z_c0d69d87c9c2` | `20261109T145118Z_524e06781560` |
| tree dirty | engine False / repo True | engine True / repo True |
| DLL sha256 | `5e6ecfb53d19…` | `3ac2087ab621…` |
| run wall | 134.5 s | 141.9 s |
| games/h (run wall) | 214.1 | 202.9 |
| games/h (ideal) | 263.0 | 250.7 |

- 8 games at 50 sims, 8 workers, `--uct-c 1.4`, seed 42; 9,559 decisions.
- Content differs on 8/8 games with `info_state_sha256` differing from
  decision line 0, as expected: determinization now leaves visible discards in
  place and pools only hand + deck. Per-game wall ratio median 0.933, mean
  0.974, range 0.743–1.319.
- **Verdict: the ADR claim holds.**

Micro-benchmarks (`scripts/bench_view_hash.py`, 118 playout states, 3,000
timed calls, three runs per build): `engine_player_view_json` mean
43.3–45.3 µs → 42.5–46.2 µs (median 38.8–39.0 → 39.6–40.2); `engine_infostate_hash`
mean 1.91–2.26 µs → 2.02–2.16 µs (median 1.9 → 1.9–2.0). **Reported, not
re-run.**

## ADR-0004 B2: delete the unreachable per-op branches

Claim: content-identical on 8/8 games. Deleting dead code must not change
behaviour.

| | parent `76dc1d4` | B2 `f3aa4db` |
|---|---|---|
| run id | `20261110T201057Z_d19383e1047a` | `20261110T201336Z_9045b5ad3a86` |
| tree dirty | engine False / repo False | engine True / repo True |
| DLL sha256 | `d26c8d89246f…` | `9ad79f459a64…` |
| run wall | 150.5 s | 150.2 s |
| games/h (run wall) | 191.3 | 191.7 |
| games/h (ideal) | 236.8 | 234.1 |

- 8 games at 50 sims, 8 workers, `--uct-c 1.4`, seed 42; 9,900 decisions.
- `decisions.jsonl` identical on 8/8 once `run_id` and `wall_time_ms` are
  ignored; `final_decks.json` byte-identical on 8/8; `replay.json` differs on
  8/8 only in `replay_context`, because the baseline ran from the
  `C:\Users\mkkom\pyrants-b2-base` worktree. Per-game wall ratio median 0.993,
  mean 0.988, range 0.97–0.999.
- Unreachability was proven first: a temporary `abort()` probe for all thirteen
  migrated op names inside the deleted range fired zero times across
  `just test-c`, `just test-c-python` (747 passed, 2 failed), `just test-all`
  (1111 passed, 2 failed, 11 skipped; openspiel 110 passed, 10 failed) and a
  9,900-move 8-game quick-check run. The probe introduced no decision change
  either: the probe run is content-identical to B2.
- **Verdict: the ADR claim holds.**

## Audit run table, re-checked

The 2026-11-07 audit transcribed 14 runs and called them "all 14 run
manifests". Each row matches the manifest it names (sha, engine dirty, DLL
prefix, date, config), and the 14 are exactly the runs in
`artifacts/ismcts/runs/`. Three of its statements do not follow:

- Those 14 are not all the manifests: `artifacts/` held 44 on 2026-11-09
  (42 under `ismcts/`, counting `quick/`, `performance_testing/`,
  `probe_fallback/` and `intern_probe/`, plus 2 under `a2_quick/`). The table
  is the 32-game and 8-game run set, not every run.
- "Only two runs in the whole set are clean-tree and paired" is true only of
  that table: the A1/A2 quick-check baselines also have a clean engine tree
  (dirty repo only), and the op-cache A/B pair is a matching pair even though
  both trees were dirty — a dirty tree does not invalidate a pair whose
  identity is the DLL hash.
- "Everything else is either dirty-tree or has no matching counterpart" is
  what led it to reject the cache claim. The cache pair is a matching pair:
  same commit, different DLLs, content-identical on all 32 games (above).
