# A1 landing note — key IS-MCTS tree nodes by a 128-bit hash

Status: **landed** 2026-09-11; G4 games/h and G-I at 200 sims measured 2026-09-12
(§ *Paired 32-game re-run*). Base: `5e1b14b` + working tree.
Plan: [`docs/ismcts-walltime-plan.md`](../ismcts-walltime-plan.md) § A1.

A1 replaces the IS-MCTS tree key from
`information_state_string()` (a ~13 KB `json.dumps`, ~105 µs cold, called
~14.5×/sim) with a 128-bit C fingerprint of the same observation, plus the
action history. It is a *byte-identical* option: it changes only how nodes are
looked up, not the tree, the RNG draws or the visits.

## Change set

| File | Change |
|---|---|
| `engine_c/player_view.c` / `.h` | `engine_infostate_hash(state, player, out[2])` — two 64-bit FNV-style streams over exactly the fields `private_view_json` serialises |
| `engine_c/engine_c.def` | export `engine_infostate_hash` |
| `engine_c/bindings/engine_bindings.py` | ctypes signature |
| `engine_c/bindings/c_adapter.py` | `CEngineAdapter.infostate_hash(player_id)` |
| `openspiel_pyrants/state_c.py` | `PyrantsCState.information_state_key(player)` = `(player, hash(history_actions), h0, h1)` |
| `openspiel_pyrants/ismcts_factory.py` | `_InfostateKeyISMCTSBot.get_state_key` uses it (falls back to the stock string for non-Pyrants states) |
| `engine_c/tests/test_infostate_hash.c` (+ `compile.bat`, `justfile`) | C contract tests for both failure modes |
| `openspiel_pyrants/tests/test_infostate_key.py` | equivalence + bot wiring |

`information_state_string` is unchanged and still feeds `info_state_sha256` in
`decisions.jsonl`.

## Measurement (G4) — same DLL, same nodes, A/B on the key alone

A/B by swapping only `get_state_key` (stock string vs hash) on the runner's real
4-player market (`seed 42`, game 0, `random-c`, `uct_c 1.4`, 200 sims/node).
3 reps per side, mid = 150 plies, late = 450 plies.

| Node | stock ms/sim | hash ms/sim | drop | speedup |
|---|---|---|---|---|
| mid | 7.05 | 4.38 | **2.67** | ×1.61 |
| late | 5.38 | 3.29 | **2.09** | ×1.64 |

Done-when (iii) asked for a ≥ 1.2 ms/sim drop; measured 2.1–2.7 ms/sim
(×1.6), above the plan's ×1.30–1.45 estimate. The 2-game acceptance runs
(`sims_per_sec_avg` 237.8 → 288 at 16 sims, 2 workers) corroborate the
direction. The 16-worker / 200-sim games/h half of G4 was measured the next
day as a paired 32-game re-run (below): **38.5 → 65.8 games/h**, in line with
the ~65 this per-sim figure projected.

## Gates

| Gate | Result |
|---|---|
| G0 determinism | 2 games at `--workers 2` and the same game at `--workers 1` have identical decision content (1311 decisions) |
| G1 replays verify | `verify_replays.py --root <candidate run>` → 2/2 OK |
| G2 training profile | `just ismcts-quick` green end-to-end (2 games, verify, `--strict` dataset, leak check 0 mismatches, report) |
| G3 test trees | `ruff check .` — no new findings in changed files; `pytest tests/` → 3 failures = tolerated F-015 ×3; `pytest openspiel_pyrants/tests/` → 11 failures = tolerated F-003 ×10 + F-013 G1 (F-034) |
| G4 measured | per-sim table above; games/h from the paired 32-game re-run below |
| G-I at 200 sims | paired re-run below: all 32 games content-identical |

### Done-when (i) — equivalence classes match

* C: `engine_c/tests/test_infostate_hash.c` pins determinism, clone equality,
  own-hand/own-discard identity splits the owner's key only, hidden deck /
  devour identity does **not** split, board occupancy and public scalars split
  every observer, and spy slot order does not split (the string sorts spies).
* Python: `test_key_equivalence_classes_match_string` groups
  `(player, information_state_string)` and `information_state_key` over a
  trajectory plus determinizations in both directions — no false split, no
  false merge. The player is part of the comparison because the stock key is
  `(current_player, string)`; two players may share a view string and must
  still get different keys.
* Python: `test_every_serialised_field_splits_key` mutates each field
  `private_view_json` serialises (round/phase/resources, market row and
  counts, every per-player summary count and identity list, own hand/discard,
  board troop slots/spies/VP) and asserts the key moves. This is the drift
  guard for the hand-maintained field list in the C hash: a field added to
  `private_view_json` but not to `engine_infostate_hash` fails here.

### Done-when (ii) — G-I byte-identity

2-game `ismcts-quick`-shaped run before (`6db7062f6845`, baseline DLL) and
after (`9e51591bc672`, A1 DLL), same flags (`--num-sims 16 --num-games 2 --seed
42 --workers 2 --num-players 4 --uct-c 1.4 --game python_pyrants_c
--no-steps`):

* `final_decks.json` — SHA-256 equal in both games.
* `decisions.jsonl` (1311 + 1028 lines) and `replay.json` — **full content
  equal** after dropping the two fields the runner stamps per run:
  `run_id` and wall-clock timings (`wall_time_ms` / `wall_time_sec`). Every
  chosen action, policy, visit count, `info_state_sha256` and final score is
  identical; those two fields make a literal byte-for-byte file diff
  impossible for any run, A-option or not. Diff script:
  `%TEMP%/kilo/a1_gi/`.

## Paired 32-game re-run (2026-09-12) — G4 games/h and G-I at 200 sims

**Diagnostic.** Re-play the `teacher_v3_32` baseline run
(`58e54c44a5f5`, engine `3410ef6`, DLL `9f6683eda3d3…`) with the
A1 build (`9d7e5da4a661`, engine `5e1b14b` + working tree, DLL
`a069723114a8…`), flag-for-flag: `--num-sims 200 --num-games 32 --seed 42
--workers 16 --num-players 4 --uct-c 1.4 --game python_pyrants_c --no-steps`. Same box
(8c/16t 7800X3D, 2 % load at launch), same 32 games (shuffle seeds 42–73). Compared with
`scripts/compare_paired_runs.py` (new; exits non-zero on any content difference). Because G0
makes each `game_index` do the same decisions and sims on both sides, the per-game wall ratio
isolates the per-simulation lever, and the run-level wall gives the games/h the plan is
denominated in.

**G-I at the teacher budget.** All 32 games content-identical: every `decisions.jsonl` line
(chosen action, policy, `visit_counts`, `q_values`, `root_value`, `info_state_sha256`) and
every `replay.json` equal after dropping the run-stamped `run_id` / `wall_time_ms`;
`final_decks.json` SHA-256 equal; `moves_total` 36,478 on both sides. The 2026-09-11 G-I was
at 16 sims; this is the first proof at 200.

**G4 games/h.**

| | baseline `58e54c44a5f5` | A1 `9d7e5da4a661` | ratio |
|---|---|---|---|
| run wall (manifest `created_utc` → last write) | 2996 s (49.9 min) | 1750 s (29.2 min) | ×1.71 |
| **games/h (run wall)** | **38.5** | **65.8** | **×1.71** |
| games/h (ideal: Σ game wall ÷ 16 workers) | 45.6 | 76.9 | ×1.69 |
| mean / max game wall | 1,264 / 1,719 s | 749 / 990 s | — |
| move latency p50 / p90 / p99 (run) | 1,237 / 2,015 / 2,920 ms | 681 / 1,317 / 1,972 ms | ×1.82 / ×1.53 / ×1.48 |
| per-game wall ratio, all 32 | | | median ×1.67, mean ×1.69, range ×1.45–2.01 |
| per-game wall ratio, first wave (0–15) | sims/s median 166 | 299 | median ×1.82 |
| per-game wall ratio, second wave (16–31) | sims/s median 201 | 315 | median ×1.61 |

**Reading the split.** The A1 run's sims/s is flat across both waves (299 vs
315); the baseline's first wave was ~17 % slower than its second (166 vs
201 sims/s), i.e. it ran under some external load on 2026-09-11. The
**second-wave ratio ×1.61** is therefore the contention-free per-simulation lever, and it
matches the § *Measurement (G4)* A/B (×1.61–1.64) to within noise. The all-games ×1.67 and
the run-wall ×1.71 carry ~5 % of baseline-side noise in A1's favour. Either way the plan's
projection (×1.30–1.45, ~54 games/h) is exceeded; 1,000 games now cost ~15.2 h instead of 26 h.

Per game:

| game | decisions | wall base (s) | wall A1 (s) | ratio | sims/s base | sims/s A1 | identical |
|---|---|---|---|---|---|---|---|
| 0 | 1308 | 1485 | 802 | 1.85 | 176 | 326 | yes |
| 1 | 1315 | 1643 | 892 | 1.84 | 160 | 295 | yes |
| 2 | 1169 | 1392 | 942 | 1.48 | 168 | 248 | yes |
| 3 | 1093 | 1337 | 762 | 1.76 | 164 | 287 | yes |
| 4 | 1311 | 1549 | 879 | 1.76 | 169 | 298 | yes |
| 5 | 1205 | 1370 | 777 | 1.76 | 176 | 310 | yes |
| 6 | 1049 | 1278 | 701 | 1.82 | 164 | 299 | yes |
| 7 | 1447 | 1719 | 990 | 1.74 | 168 | 292 | yes |
| 8 | 1164 | 1546 | 769 | 2.01 | 150 | 303 | yes |
| 9 | 1099 | 1361 | 846 | 1.61 | 162 | 260 | yes |
| 10 | 1071 | 1086 | 592 | 1.83 | 197 | 362 | yes |
| 11 | 979 | 1064 | 581 | 1.83 | 184 | 337 | yes |
| 12 | 1185 | 1439 | 804 | 1.79 | 165 | 295 | yes |
| 13 | 1179 | 1473 | 810 | 1.82 | 160 | 291 | yes |
| 14 | 875 | 1045 | 564 | 1.85 | 168 | 310 | yes |
| 15 | 1230 | 1515 | 799 | 1.90 | 162 | 308 | yes |
| 16 | 1123 | 1208 | 803 | 1.50 | 186 | 280 | yes |
| 17 | 905 | 917 | 513 | 1.79 | 198 | 353 | yes |
| 18 | 1253 | 1500 | 907 | 1.65 | 167 | 276 | yes |
| 19 | 904 | 904 | 617 | 1.47 | 200 | 293 | yes |
| 20 | 1156 | 1253 | 811 | 1.55 | 184 | 285 | yes |
| 21 | 1276 | 1245 | 820 | 1.52 | 205 | 311 | yes |
| 22 | 853 | 828 | 512 | 1.62 | 206 | 333 | yes |
| 23 | 1320 | 1309 | 799 | 1.64 | 202 | 330 | yes |
| 24 | 1217 | 1350 | 834 | 1.62 | 180 | 292 | yes |
| 25 | 1223 | 1191 | 740 | 1.61 | 205 | 330 | yes |
| 26 | 961 | 909 | 604 | 1.51 | 211 | 318 | yes |
| 27 | 996 | 1030 | 639 | 1.61 | 193 | 312 | yes |
| 28 | 1138 | 1100 | 701 | 1.57 | 207 | 325 | yes |
| 29 | 1168 | 1219 | 843 | 1.45 | 192 | 277 | yes |
| 30 | 1007 | 910 | 554 | 1.64 | 221 | 364 | yes |
| 31 | 1299 | 1275 | 758 | 1.68 | 204 | 343 | yes |

The A1 run (`9d7e5da4a661`) is content-identical to the baseline and can serve as the
baseline for the next byte-identical option's paired re-run.

## Risk

The C hash's field set is the only correctness surface. The failure the plan
names — omitting a serialised field (false merge) or including a hidden one
(false split) — is covered from both ends by the C contract tests and the
Python equivalence test. 128 bits over ≤ a few thousand states per decision
makes accidental collision negligible.
