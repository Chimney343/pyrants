# Saving IS-MCTS Games for Neural-Network Training

Status: implemented and gated on a fresh v3 corpus. Written 2026-09-09 (commit `ea25b68`); fitness audit last updated 2026-09-11 (`23196b7` + working tree, see § v3 teacher run).
Short version in grug voice: `nn-training-data-grug.md`.

## The answer

Keep `replay.json` + `summary.json` as the canonical record of a game and derive everything else from it. At simulation time log only what the search produces and cannot be recomputed: per-decision visit counts, Q-values and root value, plus the outcome and the full config. Do not write observation tensors from the runner. A separate offline builder replays each game through the C engine, encodes the acting player's observation at every decision node, joins it with the logged search policy and the final scores, and writes sharded numpy files.

The replay layer already exists and verifies clean (134/134 stored games replay to the recorded final scores). The missing pieces are small:

1. Three additions and one removal in `decisions.jsonl` (real visit counts, Q-values, structured legal moves; drop the stub).
2. Run-scoped output directories with a completion marker (the top-level `game_000x` dirs currently mix two runs).
3. A dataset builder plus an observation encoder and a global action encoder, with tests.

## What one training sample is

For an AlphaZero-style policy+value network there is one sample per decision node:

| Field | Meaning | Source |
|---|---|---|
| `obs` | fixed-shape tensor of what the acting player may know | regenerated from replay: engine private view + public history |
| `legal_mask` | which global action ids are legal here | regenerated: engine legal moves through the action encoder |
| `policy_target` | IS-MCTS root visit distribution over legal actions | `decisions.jsonl` (`policy` today, `visit_counts` after the fix) |
| `value_target` | final outcome from the acting player's perspective | `summary.json` final scores per seat |
| `q_root`, `q_actions` | search value estimates, optional auxiliary targets | new `decisions.jsonl` fields |
| metadata | run id, game, node, seat, num_players, phase, move type, sims, uct_c, engine sha, encoder version | `summary.json` + run manifest |

This is an imperfect-information game, so `obs` must be built from the information state only: own hand, own zones, the public board, and the public move history. Opponent hands and every deck order are off limits. Opponent owned-card multisets are fair game because every recruit, promote and devour is a public move.

## What the runner writes today

Since Phase 1 of `nn-training-data-tdd-plan.md`, every run owns a nested
`artifacts/ismcts/runs/<YYYYMMDDTHHMMSSZ>_<run_id>/` directory (no more
`game_XXXX/` straight into `--output-dir`). A run manifest is written before the
first game starts; `schema_version` is 2.

Per run directory:

| File | Content | Verdict for training |
|---|---|---|
| `manifest.json` | `schema_version`, engine git sha + dirty flag + DLL sha256, full CLI config, per-game inline `setup_data_json` | Provenance + setup recovery. |
| `metrics.json`, `summary.csv`, `summary.md`, `failures.jsonl` | run-level aggregates and crash records | Diagnostics. |

Per game directory under the run dir:

| File | Content | Verdict for training |
|---|---|---|
| `replay.json` | chance seed, deck ids, every move payload in order, final scores, `schema_version` | Canonical. Sufficient to regenerate every state and every observation. |
| `summary.json` | config, returns, final scores per player, outcome, setup sha, `schema_version`; written LAST | Needed for value targets and for filtering complete games (`stopped_reason == "terminal"`). |
| `decisions.jsonl` | per decision: legal ids, legal move strings, `policy` (visit fractions), chosen move, sims; since Phase 2 also `visit_counts`, `q_values`, `root_value`, `total_visits`, `legal_moves_payload`, `pending_context` | Usable now as the policy and value target (see the telemetry paragraph below). |
| `steps.jsonl` | post-move public snapshot; board only on mutating moves | Not needed for training; `--no-steps` turns it off. Roughly 60% of the bytes per game. |
| `final_decks.json` | final card multisets per seat | Sanity check only. |

Files are written atomically (`write_json_atomic`) and `summary.json` doubles
as the completion marker: a game counts as complete only when it parses and
`stopped_reason == "terminal"` (`interface/replay_loader.is_complete_game`).

Since Phase 2, every decision line also carries the real search telemetry
(`visit_counts`, `q_values`, `root_value`, `total_visits`, `legal_moves_payload`,
`pending_context`). Measured on one 4-player game (`num_sims=2`,
`max_rounds=10`, 99 decisions): `decisions.jsonl` grows from 60,279 to 108,639
bytes, **+80.2 %** — dominated by the per-node `legal_moves_payload`, so the
plan's +30-50 % estimate was low at this sim budget (the fixed payload cost
matters more when the visit block is small).

Facts verified against code and data:

- `policy` is OpenSpiel's `NORMALIZED_VISITED_COUNT`: child visits divided by root total visits. Over the 120-game experiment it sums to 1 on all 101,230 non-forced decisions, and `policy × (sims_requested − 1)` is an exact integer for every entry. Integer visit counts are therefore recoverable from the files already on disk. The root's first simulation only expands the node, which is why the divisor is sims − 1.
- The acting player's observation is stored nowhere. `decisions.jsonl` keeps a hash of it (`scripts/run_ismcts.py:642`). `steps.jsonl` is written after the move is applied (`scripts/run_ismcts.py:668-674`) and has no hand. The replay is the only path back to the observation.
- Action ids are positional per state (`openspiel_pyrants/action_encoding_c.py:24-36`). Id 3 means "the fourth legal move here" and nothing more. Only the move strings and payloads carry meaning, so any encoder must key on payloads.
- Returns are score differences for 2 players and raw scores for 3 to 4 players (`openspiel_pyrants/state_c.py:171-190`). Value targets need one normalization across player counts.
- The pending card-choice context (which card is resolving, which op) is not part of the private view (`engine_c/bindings/c_adapter.py:245`). IS-MCTS gets it implicitly through the history prefix in the info-state key. A network needs it as explicit input.

## Fitness audit of the artifacts on disk

Checks run 2026-09-09 at commit `ea25b68`:

| Check | Result |
|---|---|
| Replay every stored game through the current engine (`scripts/verify_replays.py`) | 134/134 OK, final scores match |
| `policy` sums to 1 and is integral in (sims − 1) | 101,230 / 101,230 |
| Every game dir has a terminal `summary.json` | 150 dirs: 16 without summary (interrupted run), 1 non-terminal |
| `decisions.jsonl` and `summary.json` come from the same run | 4 of 150 dirs mismatch: top-level `game_0000..0003` hold decisions and steps from a 4-player run and replay and summary from an earlier 2-player run |
| Forced decisions (exactly one legal move) | 44,242 of 145,472 (30%); end_of_turn and cleanup are essentially all forced |
| Non-forced decisions per 4-player game | about 840 (game length 591 to 2069 nodes, mean 1212) |
| Legal actions per non-forced decision | p50 6, p90 10, p99 28, max 658 |
| Policy sharpness by seat budget (mean normalized entropy) | 50 sims 0.50, 100 sims 0.37, 200 sims 0.27, 400 sims 0.19 |
| Schema drift | 2026-09-02 summaries lack `player_ids`, `final_vp_per_seat`, `uct_c_per_seat`; no `schema_version` anywhere |

Consequences:

- The mixed-run directories are a real defect. `interface/replay_loader.py` and any future builder assume decisions line N pairs with replay step N. The symptom matches F-018, and F-022 already records that this directory is locally mutable. The experiment scripts write `<timestamp>_<run_id>/` per run; `scripts/run_ismcts.py` writes straight into the output dir and overwrites file by file. Register this as a finding and fix the runner.
- The 120-game experiment is usable teacher data today: about 101k (obs, policy, outcome) triples after regeneration. It is a mixed-budget experiment (50/100/200/400 sims per seat), so keep `sims_requested` on every sample and weight or filter by it.

### Acceptance run (2026-09-10, `ea25b68` + working tree)

`just verify-replays` → **135/135 OK** (134 stored games + the new v2 run dir).

`python -m scripts.build_nn_dataset --runs artifacts/ismcts --allow-legacy-schema --leak-check 200 --out datasets/sims_vs_wins_v1`:

- **130 games accepted, 5 rejected.** The rejections are exactly the expected set: the four mixed top-level dirs `game_0000..0003` with `["run_id mismatch", "decision count mismatch"]` (F-025) and `performance_testing/game_0000` with `["stopped_reason='round_cap'"]`.
- **107,551 samples, 6 shards.** Alignment held on every node (no `AlignmentError`).
- `leak_check = {nodes: 18299, mismatches: 0}`.
- Value-target mean per seat: **+0.011, −0.034, −0.042, −0.037** (≈0, as intended).
- `policy argmax == chosen`: **0.834** overall, **0.886** for `sims_requested ≥ 200`.

The plan's `≥ 0.95` argmax gate assumed the logged move is the policy argmax, but
`ISMCTSBot.step_with_policy` **samples** from `NORMALIZED_VISITED_COUNT`
(`ismcts.py`), so the match rate equals the policy's top-probability mass. At
200+ sims the audit's own mean normalised entropy is 0.27, consistent with ~0.89.
The gate is recorded as measured rather than met; there is no pipeline defect.

### v2 acceptance run (2026-09-11, `ea25b68` + Phases 0-4 of `nn-training-data-fix-plan.md`)

The fix plan's Phase 5 rebuild, from the 120-game `sims_vs_wins` experiment
(`artifacts/ismcts/experiments/sims_vs_wins/20260902T215139Z_65cdce971bcf`):

```
python -m scripts.build_nn_dataset --runs <experiment> --out datasets/sims_vs_wins_v2 \
  --allow-legacy-schema --leak-check 200 --shard-size 20000
```

- **120 games accepted, 0 rejected. 101,230 samples, 6 shards** (`encoder_version = 2`,
  `action_space_version = 2`).
- `leak_check = {nodes: 16927, mismatches: 0}`.
- Value-target mean per seat: **+0.014, −0.029, −0.037, −0.032** (≈0, as intended).
- `policy argmax == chosen`: **0.830** overall, **0.883** for `sims_requested ≥ 200`
  (51,073 samples). Same sampling explanation as above.
- `pair_move_merge_frac = 0.00213` (0.213 % of non-forced samples); the semantic-collision
  census (`PYRANTS_NN_CENSUS=1 pytest tests/nn/test_actions.py`) over all 137 stored games
  reports **0 rulebook-distinct collisions** (227 destination-only pair merges of 112,339
  non-forced states = 0.202 %). This is the bounded approximation documented in the fix plan § 3.

`just ismcts-quick` → 2/2 replays OK, strict build, leak 0/0 mismatches, report shows both
`pair_move_merge_frac` (0.0024) and `n_legal_raw_mean` (6.9).

### v3 acceptance run (2026-09-11, Fix Plan 02)

`just ismcts-quick` rebuilds `datasets/quick` from a fresh 2-game, 4-player, 16-sim
run under the current engine; the manifest records `encoder_version = 3`,
`action_space_version = 3`.

- **2/2 replays OK**, 2 games accepted, 0 rejected, **1,653 samples, 2 shards**.
- `leak_check = {nodes: 70, mismatches: 0}`.
- Value-target mean per seat: **−0.010, −0.082, −0.032, −0.037** (≈0, as intended).
- `policy argmax == chosen`: **0.558** (`sims_requested = 16` here, so the `≥ 200`
  slice is empty and its metric is `None`).
- `pair_move_merge_frac = 0.00242` (0.242 % of non-forced samples); `n_legal_raw_mean = 6.91`.
- `manifest.json` now also records `op_index_sha` and `effect_index_sha` (m2 of Fix Plan 02).

The 120-game `sims_vs_wins_v2` was **not** rebuilt to v3: `23196b7` also made
`insane_outcast` non-recruitable (`data/decks/base_setup.json` `recruitable: false` +
engine), which changed the setup SHA so the builder rejected all 120 legacy games, and
46 of them desynced at `recruit insane_outcast`. On 2026-09-11 the owner wiped
`artifacts/ismcts/` (every game played under the old rule) and `datasets/sims_vs_wins_v2`
was deleted. The v2 numbers above are history; the corpus below replaces them.

### v3 teacher run (2026-09-11, `23196b7` + working tree)

First corpus played entirely under the current rule set, at the uniform teacher budget
§ How many games asks for:

```
python -m scripts.run_ismcts --num-sims 200 --num-games 32 --seed 42 --workers 16 \
  --num-players 4 --uct-c 1.4 --game python_pyrants_c --no-steps \
  --output-dir artifacts/ismcts/runs            # -> runs/20260911T193759Z_58e54c44a5f5
python scripts/verify_replays.py                # 34/34 OK (32 + the 2-game quick run)
python -m scripts.build_nn_dataset --runs artifacts/ismcts/runs/20260911T193759Z_58e54c44a5f5 \
  --out datasets/teacher_v3_32 --strict --leak-check 200 --shard-size 20000
python -m scripts.build_nn_dataset --report datasets/teacher_v3_32
```

- Run: 32 × 4-player games, engine `3410ef6`, DLL sha recorded, `steps.jsonl` off.
  **50 min wall** on an 8-core / 16-thread Ryzen 7 7800X3D with 16 workers; per game
  828-1,719 s (mean 1,264 s), 183 sims/s per worker. A 4-worker pilot of the same seed
  produced byte-identical move sequences for games 0-3 (search is deterministic per
  seed), so it was discarded rather than double-counted.
- Decks: 12 of the 15 half-deck pairs appeared; **8 of 32 games** carry the demons
  half-deck and therefore the `insane_outcast` special stack.
- Replays: 36,478 moves, 853-1,447 per game (mean 1,140). 72 % non-forced.
- Build (`--strict`, no legacy flag): **32 accepted, 0 rejected, 26,306 samples, 2 shards**
  (`encoder_version = 3`, `action_space_version = 3`, all four index SHAs in the manifest).
  Alignment held on every node.
- `leak_check = {nodes: 4611, mismatches: 0}`.
- Value-target mean per seat: **+0.022, +0.002, −0.008, +0.006** (flatter than the
  mixed-budget v2 run, as a uniform budget should be).
- `policy argmax == chosen`: **0.844** — every sample is at `sims_requested = 200`, so the
  overall and the `≥ 200` figures coincide. Measured, not the plan's 0.95, for the sampling
  reason given under the first acceptance run.
- `pair_move_merge_frac = 0.0016` (0.16 %); `n_legal_raw_mean = 6.74`.
- Census over the new corpus (`PYRANTS_NN_CENSUS=1 pytest tests/nn/test_actions.py`):
  34 dirs, 34 walked, 0 skipped, **0 semantic collisions**. The three `insane_outcast`
  branches are back in the live census (70 / 47 / 14 states, via demon-deck give effects);
  `steal_white_trophy_to_board` (Mummy Lord) dropped out (6 → 0 states) and gained a
  live-engine test. `_EXPECTED_BRANCH_COVERAGE` was re-baked on this corpus.
- Test trees after the run: `tests/` 3 failed (all F-015; the two artifact-bound tests now
  skip); `openspiel_pyrants/tests/` 11 failed (10× F-003 by design, 1× F-013's G1
  byte-identity gate whose frozen reference recruits `insane_outcast` — open, see F-034).

## Proposed layout

Three layers. Layers 0 and 1 are written by the runner. Layer 2 is built offline and is rebuilt whenever the encoder changes.

```
artifacts/ismcts/runs/<YYYYMMDDTHHMMSSZ>_<run_id>/
  manifest.json          # schema_version, engine_git_sha + dirty flag, full config, setup_data_json
  game_0000/
    replay.json          # layer 0: seed, deck ids, moves, final scores
    decisions.jsonl      # layer 1: search telemetry per decision
    steps.jsonl          # optional, off by default for training runs
    summary.json         # layer 0: outcome + config; written LAST, doubles as the completion marker
datasets/<dataset_id>/
  manifest.json          # encoder_version, action_space_version, source runs, counts, feature layout
  shard_0000.npz         # layer 2: obs, legal_mask, policy, visits, value, meta
```

### Layer 0: canonical game record (exists; harden it)

- Add `schema_version` to `replay.json` and `summary.json` (start at 2).
- Add `engine_git_sha` and a dirty flag to the run manifest. A replay is only meaningful under the engine that produced it; `scripts/verify_replays.py` is the gate whenever the engine changes.
- Inline `setup_data_json` (about 2 KB) in the run manifest. `setup_data_sha256` already exists per game and `interface/replay_loader.py:186-199` already rebuilds the setup from the deck ids and checks the sha.
- Write `summary.json` last. A game counts as complete only when `summary.json` exists and `stopped_reason == "terminal"`.

### Layer 1: `decisions.jsonl` (three additions, one removal)

After `bot.step_with_policy` (`scripts/run_ismcts.py:606`) the root node is still on the bot. Read it before the next decision:

```python
# Forced moves never build a root: run_search returns early and _root_node
# still points at the previous decision. Verified live; the guard is required.
root = bot._root_node if len(legal_ids) > 1 else None
visit_counts = {int(a): int(c.visits) for a, c in root.child_info.items()} if root else {}
q_values = {int(a): c.return_sum / c.visits for a, c in root.child_info.items() if c.visits} if root else {}
root_value = (sum(c.return_sum for c in root.child_info.values()) / root.total_visits) if root else None
```

Fields:

- `visit_counts`: real integer visits. Replaces the `{chosen: 1}` stub at `scripts/run_ismcts.py:646`.
- `q_values`: mean return per child, in the acting player's return units. `root_value` and `total_visits` alongside.
- `legal_moves_payload`: the structured `to_payload()` dict for every legal move, in the same order as `legal_action_ids`. Keep the repr strings for humans; encoders parse payloads.
- `pending_context`: already emitted as `generic` on resolve_generic lines. Emit it on every line where a generic choice is pending, since it is the same for all legal moves at that node.

### Layer 2: dataset shards (new builder script)

For each complete game the builder validates first: same `run_id` in replay, decisions and summary; `len(decisions) == step_count`; setup sha matches. Then it replays the game with the `ReplayPlayer` in `interface/replay_player.py`. At step i, before applying the move:

1. Acting player is `replay_log[i].player_id`. `obs` = encode(private view for that player + pending context + history-derived multisets).
2. Legal moves = engine legal moves minus `unavailable` placeholders. Assert their payloads equal `decisions[i].legal_moves_payload` in order. This one assert catches every alignment bug in the family of F-018.
3. `policy_target` = visits mapped onto global action ids, summing mass across duplicate-equivalent moves (two copies of the same card in hand).
4. `value_target` = normalized final-score vector from `summary.json`, rotated so the acting player is seat 0.
5. Skip forced nodes, or keep them with weight 0 if the value head should see them.

Write `.npz` shards of about 50k samples plus a manifest. numpy is installed; torch and pyarrow are not, and npz is enough to start. Store the compact structured form (card ids and counts, not one-hots) and expand at load time, so a switch to learned card embeddings does not touch the shards. *As built*, `write_shards` stores the dense `int16` observation (`OBS_SIZE` per row), not a sparse id/count list; each 126-wide card block is a count vector, so card ids are recoverable from its non-zero entries and an embedding switch reads the same shards — but the stored form is the expanded one, not the compact one this paragraph describes.

## Observation encoding v3

Perspective-relative: seat 0 is always the acting player, followed by the other seats in turn order. Four seat slots with a presence mask, so 2-, 3- and 4-player games share one network. 125 card ids in `data/cards/` plus one "unknown" id. 81 board nodes in `data/boards/tyrants_of_the_underdark.json`.

`ENCODER_VERSION = 3`: the `seat_features` (4 × 8) and `seat_is_current` (4) blocks rotate through the same `order` as every other block, so slot `k` is `order[k]` and slot 0 is the acting player's own stats. v2 indexed both with the *absolute* seat, so for three of four players the own-stats block belonged to another seat (F-030). `seat_is_current` is therefore the constant `[1, 0, 0, 0]` for every training sample (the encoder is always called from the acting player's seat); the block is kept at its size and pinned by a test, and the absolute seat is stored separately as `Sample.acting_seat`. `OBS_LAYOUT` and `OBS_SIZE` are unchanged from v2.

| Block | Features | Size |
|---|---|---|
| Board, per node | my troops, opp1-3 troops, white troops, empty slots, capacity, my spy, opp1-3 spy, controller one-hot (5), total-control flag, my presence flag, control_vp, total_control_vp_per_turn, vp_tokens, is_site | 81 × 24 = 1,944 |
| My cards, counts per card id | hand, played this turn, discard, inner circle, deck remainder (owned minus visible zones; legitimate knowledge) | 5 × 126 = 630 |
| Opponent cards, per seat | owned bag (deck + hand + discard as one multiset; the split is hidden), played this turn, inner circle | 3 × 3 × 126 = 1,134 |
| Market | row slots 6 × 126; remaining market-deck multiset (two half-decks minus everything revealed); special stack counts (priestess, house guard, insane outcast) | 756 + 126 + 3 |
| Pending choice | source card one-hot (126), op one-hot (about 24), awaiting_option, current option index (8), remaining repeats | about 160 |
| Scalars | round, phase one-hot (4), power, influence; per seat: score, vp_tokens, barracks, spies_available, hand/deck/discard/trophy sizes, is_current, present; market deck size and min barracks across seats (both end-game triggers) | about 50 |

Total about 4.8k floats. Board adjacency is static, so an MLP over the flat vector is a valid first network; a graph layer over the 81 nodes is a later refinement that does not change the stored data. Everything above is derivable from the engine private view (`engine_c/bindings/c_adapter.py:245`) plus the replay history. No engine work is needed.

## Action encoding v3 (global, stable)

| Move type | Key | Slots |
|---|---|---|
| play_card | card id, not hand index; duplicates merged | 126 |
| recruit | card id | 126 |
| promote_card, skip_promote | card id, plus one | 127 |
| initial_placement | node | 81 |
| deploy | node, plus one null target (deploy with an empty barracks gains 1 VP; appears in replays as `target_node_id: null`) | 82 |
| assassinate | node × owner (me, opp1-3, white) | 405 |
| return_spy | node × owner | 324 |
| end_main_phase, resolve_end_of_turn, resolve_cleanup, activate/decline ability | fixed | 5 |
| resolve_generic (v3) | option (8) + decline (1) + node (81) + card (126) + player (4) + index (20); troop/spy targets reuse `assassinate` / `return_spy` | 240 |

1,516 of 2,048 slots. `ACTION_SPACE_VERSION = 3`. Slot-index targets (assassinate slot 2 versus slot 1 of the same owner) collapse to the owner key at build time and expand to the first matching slot at play time. `assassinate_troop`, `supplant_troop` and `return_unit`'s `troop:N` route to `assassinate[site × owner]`; `return_unit`'s `spy:<owner>` routes to `return_spy[site × owner]`. Every legal move must map to exactly one slot, and the builder fails loudly on an unmapped move.

v3 keys every structured trophy *placement* on the deployed troop's colour: a target `sp:idx:node:slot` routes to `assassinate[node × owner_slot(colour)]`, colour read from `ctx.trophy_halls`. v2 sent `deploy_from_trophy_hall` and `steal_from_selected_trophy` to `node[destination]`, so 23 of 23 gids on a live Lich state merged two differently-coloured deploys (F-031); the live test now measures 46 gids. A trophy colour that is not a current seat or `white` (e.g. `p3` in a 2-player game) is illegal and raises. The `index` sub-block holds allow-listed positional keys: `select_trophy_hall` is keyed as source seat (4) × trophy colour (5). `steal_white_trophy_to_board` step 1 routes to the `player` sub-block by source player (every offered trophy is white, so no distinct choice folds); its structured step-2 target keys on the trophy colour (always white).

The census semantic key is `(op, effect_kind, destination_node, trophy_colour)`, derived from the live trophy halls rather than the encoder's routing, so it can disagree with the encoder and fail. It reports branch and routing sub-block coverage, and every choice-producing branch the stored games never reach is named in `_UNCOVERED_BY_CENSUS` with the live-engine test that covers it. On the current corpus (`PYRANTS_NN_CENSUS=1 pytest tests/nn/test_actions.py`) it walks 34 stored game dirs (the 32-game 200-sim run plus the 2-game `ismcts-quick` run, all under the `insane_outcast` non-recruitable rule), replays all 34, skips 0, and reports 0 rulebook-distinct collisions; the test prints `CENSUS_CORPUS dirs= walked= skipped=` so the number can be cited from the run rather than from this sentence. Five trophy-related branches the corpus never reaches are named in `_UNCOVERED_BY_CENSUS`, each with a live-engine test in `tests/nn/test_actions_live_custom_effects.py`.

v2 alternative: a per-move scoring head that embeds each legal move's payload and softmaxes over the legal set. It handles the 658-move states without a large sparse head and needs exactly the same stored data. This is why layer 1 stores payloads and per-move visits, never v1's slot ids.

## Value targets

Store raw final scores per seat with every game and compute the target at build time so it can change later:

- 2 players: z = tanh((mine − theirs) / 40), or the sign. Both derivable.
- 3 to 4 players: the value head predicts a 4-vector of normalized final scores per seat, rotated and masked: z_s = clip((score_s − mean of the others) / 40, −1, 1). This matches OpenSpiel's general-sum `returns()` shape and lets the same network serve as an IS-MCTS evaluator later.
- Optional auxiliary: `root_value` and per-action `q_values` from the search, for bootstrapped or mixed targets. Requires the layer-1 additions.

## Network sketch

Included to size the data, not as the final design.

```
obs (about 4.8k) -> Linear 1024 -> 3 x residual MLP block (1024, LayerNorm, GELU, dropout 0.1)
                 -> policy head: Linear 2048, masked log-softmax over legal_mask
                 -> value head:  Linear 256 -> Linear 4, tanh, masked by seat presence
```

Roughly 10 to 15M parameters. Loss = cross-entropy against the visit distribution + MSE on value, optionally + MSE on root value. Per-sample weight is a function of `sims_requested`.

## How many games

About 840 non-forced samples per 4-player game. 1,000 games give about 0.8M samples, enough to prove the pipeline and get a weak policy. Expect 5k to 20k games before a distilled policy is worth plugging back into the search as a prior or evaluator. For teacher runs use a uniform budget of at least 200 sims per seat; the 50-sim seats in the existing experiment produce the noisiest targets. Do not deduplicate on `info_state_sha256`: it includes the history prefix and is unique per node.

Measured cost (2026-09-11, § v3 teacher run): 32 four-player games at 200 sims took 50 min on 8 cores with 16 workers, i.e. **about 40 games per hour**, 822 non-forced samples per game. 1,000 games is roughly a day of compute on that box; 5k-20k games is a week to a month, or a bigger machine.

## Concrete next steps

1. Runner (`scripts/run_ismcts.py`): run-scoped output dir and manifest; real `visit_counts`, `q_values`, `root_value`, `legal_moves_payload`, `pending_context`; `schema_version`; write `summary.json` last. Register the mixed-run directories as a finding next to F-018 and F-022.
2. Encoders (new module, suggested path openspiel_pyrants/nn/encoders.py): `encode_observation(adapter, player_id, pending_ctx)` returning a numpy array, and `move_to_global_action(payload, ctx)` returning an int. Round-trip tests over the 120 replays: every legal move maps, no collisions.
3. Builder (`scripts/build_nn_dataset.py`, wrappers in `openspiel_pyrants/nn/dataset.py` + `scripts/_nn_dataset.py`): validation, replay, encode, shard, manifest. Run it on the current teacher corpus (the 120-game experiment was wiped on 2026-09-11 — it was played under the pre-`recruitable` rule; see § v3 teacher run):
   ```
   just build-nn-dataset artifacts/ismcts/runs/20260911T193759Z_58e54c44a5f5 datasets/teacher_v3_32 --strict --leak-check 200 --shard-size 20000
   just report-nn-dataset datasets/teacher_v3_32
   ```
   (`just` here takes positional arguments; `name=value` is passed through as a literal.)
4. Acceptance gate before any training: all games verify; the alignment assert holds on every node; leak test passes (encoder output identical before and after `CEngineAdapter.determinize`, which reshuffles exactly the hidden zones); label sanity (value target mean about 0 across seats; policy argmax equals the chosen move on at least 95% of nodes with sims ≥ 200).

   Status: **run** (see § Fitness audit → Acceptance run, v2 acceptance run, v3 acceptance run and v3 teacher run above). All gates hold except the argmax threshold (v2 0.883 at sims ≥ 200; v3 teacher run 0.844 at uniform 200 vs 0.95), which is explained there by `step_with_policy` sampling from the visit distribution. F-025 and F-026..F-029 are fixed by `nn-training-data-fix-plan.md`; F-030..F-033 are fixed by `nn-training-data-fix-plan-02.md`; the rule-change stowaway that invalidated the first corpus is F-034. The only training-size v3 dataset is `datasets/teacher_v3_32` (32 games); training has not started.

## Not decided here

- Whether training runs keep `steps.jsonl` at all. `--no-steps` exists and `just ismcts-quick` passes it; the runner's default is still **on** and `just ismcts` leaves it on. Measured 2026-09-11 on a 200-sim game: 5.9 of 8.2 MB (73 %) is `steps.jsonl`. Flip the default or add the flag to `ismcts` before the 1,000-game run.
- Whether opponents' discard contents count as observable. The engine says no, and the owned bag is observable regardless.
- Card embeddings versus one-hots, and a graph layer over the board. Neither changes the stored format.
