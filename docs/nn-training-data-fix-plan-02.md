# NN Training Data — Fix Plan 02 (review of Fix Plan 01's implementation)

Scope: the four findings from the 2026-09-11 review of `nn-training-data-fix-plan.md`'s
implementation, plus six minor cleanups. Base: working tree at `ea25b68` with Phases 0-5 of
Fix Plan 01 applied but uncommitted. Status: **implemented** (2026-09-11).

Fix Plan 01 is confirmed done. Re-verified in this review, not taken on trust:
| gate | result |
|---|---|
| `pytest tests/nn tests/test_build_nn_dataset.py tests/c_engine/test_pending_context_full.py tests/test_run_ismcts_layer0.py tests/test_run_ismcts_decision_telemetry.py` | 97 passed |
| `pytest -q` (`tests/`) | 4 failed — the documented tolerated set (3× F-015, 1× F-022), no regressions |
| `pytest openspiel_pyrants/tests/ -q` | 10 failed, all F-003 by design (was 11; NN-2 closed) |
| `PYRANTS_NN_CENSUS=1 pytest tests/nn/test_actions.py` | **passes over all 139 stored game dirs** |
| `ruff check` on every new/changed module | clean |
| `OP_IDS` / `EFFECT_KINDS` re-derived independently from `data/cards/*.json` | 17 / 13, matches |
| board `adjacent_to` graph | symmetric, 0 dangling, 0 site↔site edges — so the adjacency reading of presence is sound |

The four findings below are things the implementation got wrong or left blind, not things
Fix Plan 01 asked for and skipped.

---

## 0. Process constraints

Unchanged from `nn-training-data-fix-plan.md` § 0, with two changes:

1. **`just test-all` is itself one of the findings** (R-4). Until Phase 1 lands, every
   "done when" below must run the two trees as two separate commands, not through `test-all`.
2. **Both encoders change, so both versions bump.** `ENCODER_VERSION = 3` (R-1 changes the
   *values* in two blocks; `OBS_LAYOUT` and `OBS_SIZE` are untouched) and
   `ACTION_SPACE_VERSION = 3` (R-2 changes `custom_effect` structured routing; `ACTION_LAYOUT`
   and the 1,516 used slots are untouched). Nothing here changes what the runner writes, so
   `schema_version` stays 2 and **no run needs repeating** — but `datasets/quick` and
   `datasets/sims_vs_wins_v2` must be rebuilt (Phase 5).

---

## 1. Findings

Severity is a proposal; the ledger owner assigns the final class and ID (Phase 0).

### R-1 `seat_features` / `seat_is_current` are absolute-seat, not perspective-relative — MODERATE

**Observed.** `observation.py:317-345` indexes both blocks with `player_ids[i]` — the absolute
seat — while every other block in the tensor rotates so that slot 0 is the acting player:
`my_hand`/`my_played`/… use the acting player's own view, `opp_bag_{slot}` resolves through
`player_ids.index(order[slot + 1])` (`:265-270`), the board block keys owners through
`owner_slot(..., order)` (`:222-233`), and the builder's value target rotates with
`seat_order` (`scripts/_nn_dataset.py::_rotate_scores`). The module docstring states the
contract the two blocks break: "Seat 0 is always the acting player, followed by the other
seats in turn order, so 2-, 3- and 4-player games share one network."

Measured on a stored 4-player replay at its last pre-terminal state, engine discard sizes
`{p1: 0, p2: 16, p3: 10, p4: 6}`:

```
p1 order ['p1','p2','p3','p4']  seat_features discard per slot = [0, 16, 10, 6]
p2 order ['p2','p3','p4','p1']  seat_features discard per slot = [0, 16, 10, 6]
p3 order ['p3','p4','p1','p2']  seat_features discard per slot = [0, 16, 10, 6]
p4 order ['p4','p1','p2','p3']  seat_features discard per slot = [0, 16, 10, 6]
```

Identical from every perspective. `seat_is_current` reads `[0, 0, 1, 0]` from all four. So
`value[0]` means "me" while `seat_features[0:8]` means "whoever sits at absolute seat 0" — for
three of four players the own-stats block belongs to somebody else, and the eight features are
`score`, `vp_tokens`, `barracks`, `spies_available`, `hand_size`, `deck_size`, `discard_size`,
`trophy_hall_size`, i.e. most of what a value head would want.

**Rulebook:** not applicable — this is an internal encoding contract, not a rule.

**Why it was not caught.** `test_observation_is_perspective_relative` checks `my_hand` and
`seat_present` only. `seat_present` is a player *count*, identical under any rotation, so it
passes either way; the two blocks that actually carry per-seat values are unasserted.

**Verdict.** Rotate both blocks through `order`. `seat_is_current` then becomes constant
`[1, 0, 0, 0]` for every training sample (the builder always encodes from the current player's
seat) — keep the block at its current size rather than churn the layout, and pin the constant
in a test so the dead slots are deliberate and visible. The absolute seat is not lost: it is
already stored per sample as `Sample.acting_seat`.

### R-2 `custom_effect` structured placement merges rulebook-distinct trophies, and the census key cannot see it — MAJOR when reached, 0 impact on stored data

**Observed.** `actions.py:360-369` routes a `custom_effect` structured target
(`action_id` = destination node, `target_id` = `<source_player>:<trophy_idx>:<node>:<slot>`) to
`resolve_generic.node[destination]`, with one special case sending
`steal_white_trophy_to_board` to `assassinate[node × white]`. The trophy index is dropped.

For `deploy_from_trophy_hall` the trophy index *is* the choice. `engine_c/selection.c:348-397`
enumerates trophy index × site × empty slot, and `engine_c/actions.c:776` deploys a troop of
**the trophy's own colour** (`ns->troop_slots[target_slot] = trophy_owner`). Driven on a live
engine state, reusing the setup from `tests/c_engine/test_card_lich.py:120-160`
(Lich, p2's hall = `["white", "p3"]`):

```
pending op/effect_kind: custom_effect deploy_from_trophy_hall
ctx.trophy_halls:       {'p1': (), 'p2': ('white', 'p3')}
COLLISION gid 1298  trophy idxs ['0','1']  e.g. p2:0:site_jhachalkhyn:0 and p2:1:site_jhachalkhyn:0
COLLISION gid 1299  trophy idxs ['0','1']  e.g. p2:0:site_gracklstugh:2 and p2:1:site_gracklstugh:2
total gids: 23   gids merging different trophies: 23
```

**23 of 23** — the entire action space of that decision is collapsed 2:1, and the two halves
place differently-coloured troops.

The census does not see it because `tests/nn/test_actions.py:566-570` keys a structured target
as `("node", action_id)` — the same key the encoder uses. The test's "own notion of the move's
rulebook identity" is, for exactly the shapes v2 approximates, a restatement of the encoder.
That is the blindness F-026 raised against the v1 census, reintroduced one layer up.

**Rulebook.** Lich (`data/cards/lich.json`): "take 2 troops from that same player's trophy hall
and deploy them anywhere on the board." A trophy hall holds troops of several colours
(`trophy_color_filter: "any"`), and colour decides control (`tyrants-rulebook.md:267`) — white
troops count as a colour but belong to no player (`:271`, `:300`). Deploying a white troop and
deploying an enemy-coloured troop to the same site are different board states and different
choices.

**Current data impact: none.** Walked all 139 stored game dirs: `deploy_from_trophy_hall`
occurs 0 times. The census's "0 semantic collisions" is a true statement about a narrower
population than it reads as — see R-2b.

### R-2b The census's custom_effect coverage is 2 of 6 branches — MODERATE (process)

`engine_c/selection.c` enumerates choices for six `effect_kind`s. Over all 139 stored games the
census met four `effect_kind`s at all:

| effect_kind | enumerates choices | states seen in the 139-game census |
|---|---|---|
| `self_purge_to_supply` | yes | 5,122 |
| `steal_white_trophy_to_board` | yes | 6 |
| `give_insane_outcast_to_selected_player` | yes | 89 |
| `give_insane_outcast_to_player_with_presence_on_last_selected_node` | yes | 32 |
| `deploy_from_trophy_hall` | **yes** | **0** |
| `select_trophy_hall` | **yes** | **0** |
| `steal_from_selected_trophy` | **yes** | **0** |
| `lich_select_target_player` | **yes** | **0** |

So four of the six choice-producing branches — including the whole `index` sub-block, whose
only allow-listed member is `select_trophy_hall`, and the `trophy_halls` plumbing that feeds
it — have **zero live-engine coverage**. They are exercised only by hand-built `ActionContext`
unit rows, which cannot catch a wrong reading of the engine's payload shape.

**Verdict.** The census must report its own coverage, and every unexercised choice-producing
branch needs a live-engine test. A gate that cannot say which branches it visited is not a gate.

### R-3 `read_pending_generic_context_full` turns an extended-read failure into "no pending choice" — MINOR

`engine_c/bindings/pending_context.py:86-101`: `base` is read successfully, then the extended
read runs inside `try: … except Exception: return None`, discarding `base`. The docstring
claims the opposite: "Returns ``None`` exactly when the base reader does."

`None` is not a degraded answer here, it is a wrong one — it means "no generic choice is
pending". Downstream, `action_context` gets `pending_op=None`, so every `resolve_generic` move
routes to `_option_offset` with an empty `option_ids` and raises `UnmappedMoveError`; the
builder then *rejects the game* with a misleading reason, or, in the one case that needs no op
(a decline-only state, `action_id is None and target_id is None`), silently encodes a sample
with an all-zero pending block. `return base` is the correct degradation.

### R-4 `just test-all` stops at the first failing tree — MINOR

`justfile:31-34` is two recipe lines. `just` aborts a recipe on the first non-zero line —
confirmed with a probe justfile (`error: Recipe 'probe' failed on line 4 with exit code 1`,
second line never ran). With today's four tolerated `tests/` failures, `test-all` **never**
reaches `openspiel_pyrants/tests/`. The recipe added to stop an OpenSpiel regression slipping
past cannot, today, run the OpenSpiel tests at all.

### R-5 Minor cleanups (no ledger entries proposed)

| # | where | what |
|---|---|---|
| m1 | `actions.py:14`, `actions.py:43` | comments say "236 slots" / "Total used: 1,512"; actual is 240 / 1,516 (the docs are right) |
| m2 | `dataset.py::write_shards` | manifest records `card_index_sha` / `node_index_sha` but not `op_index_sha` / `effect_index_sha`, both now catalog-derived encoder inputs. Adding an op to an existing card shifts `PENDING_OP_SLOTS` → shifts `OBS_LAYOUT` without moving the card sha |
| m3 | `actions.py:257`, `observation.py:299` | option position is clamped with `min(...)`, the last silent-merge fallback in an encoder that otherwise raises. Harmless today (max options in the catalog is 2) |
| m4 | `scripts/_nn_dataset.py:73,80` | `policy_argmax_match_frac` and `n_legal_raw_mean` still return `0.0` on an empty denominator — the shape NN-7 fixed for the 200-sim metric only |
| m5 | `scripts/_nn_dataset.py:290,305-308` | `_has_pair_merge` maps every payload, then the loop below maps them all again: 2× `move_to_global_action` per decision |
| m6 | `validation/findings.md` F-026 Resolution | says `steal_white_trophy_to_board` step 1 is "keyed by trophy colour in the `index` block"; it routes to the `player` sub-block keyed by source player (harmless — step-1 candidates are all white — but the text is wrong). Game counts also drift: the plan says 134, F-026 says 137, the census walks 139 |

---

## 2. Engine facts the fixes depend on (verified in this review)

| fact | where | verified |
|---|---|---|
| `deploy_from_trophy_hall` enumerates trophy × site × empty slot | `selection.c:348-397` | read |
| the deployed troop takes the **trophy's** colour | `actions.c:776` (`= trophy_owner`) | read; `test_card_lich.py:157` asserts `["p3","white"]` deployed |
| structured target is `<source_player>:<trophy_idx>:<node>:<slot>`, `action_id` is the same destination node | `selection.c:253-265, 381-396`; `generic_runtime.c:989-1051` | read + live probe |
| `public_player_summaries[pid]["trophy_hall"]` is a list of owner-colour strings | `c_adapter.py:220` | live probe: `{'p2': ('white','p3')}` |
| the trophy is still in the hall when the move is enumerated (removal happens on apply) | `actions.c:775-779` | live probe |
| six `effect_kind`s enumerate choices | `selection.c` | grep + 139-game census |
| `just` aborts a recipe on the first non-zero line under the PowerShell shell setting | `justfile:1` | probe justfile |

---

## 3. Design changes

### 3.1 Observation v3 (fixes R-1)

Two blocks change their *meaning*, not their size:

| block | v2 | v3 |
|---|---|---|
| `seat_features` (4 × 8) | `summaries[player_ids[i]]` | `summaries[order[i]]`, zero for `i >= n` |
| `seat_is_current` (4) | `player_ids[i] == current_id` | `order[i] == current_id` — constant `[1,0,0,0]` whenever the encoder is called from the current player's seat, which is every training sample |

`OBS_LAYOUT` and `OBS_SIZE` are unchanged, so nothing downstream needs new columns.
`ENCODER_VERSION = 3`.

Considered and rejected: dropping the now-constant `seat_is_current` block. It would shrink
`OBS_SIZE` and churn every stored `obs_layout` for four slots. Keep it, pin the constant, and
revisit if a future encoder needs the space.

### 3.2 Action space v3: one rule for every structured placement (fixes R-2)

Replace the `structured` branch's special case with a single rule derived from the rulebook
noun: *a troop of colour C placed at node N*.

```
structured target  ->  assassinate[node_index(action_id) * 5 + owner_slot(trophy_colour)]
    where trophy_colour = ctx.trophy_halls[source_player][trophy_idx]
```

parsing `source_player` and `trophy_idx` out of the `<sp>:<idx>:<node>:<slot>` target. The
same rule covers all three structured kinds and **deletes** the `effect_kind` special case:

| effect_kind | v2 routing | v3 routing | changes? |
|---|---|---|---|
| `steal_white_trophy_to_board` step 2 | `assassinate[node × white]` (hard-coded) | `assassinate[node × colour]`, colour always white | no — same slot |
| `steal_from_selected_trophy` | `node[destination]` | `assassinate[node × colour]`, colour fixed by the earlier `select_trophy_hall` step | yes, and more precise |
| `deploy_from_trophy_hall` | `node[destination]` — **merges trophies** | `assassinate[node × colour]` | **fixes R-2** |

Malformed or out-of-range trophy references raise `UnmappedMoveError` (loud), consistent with
the rest of v2. The `node` sub-block keeps its other routes (`deploy_troops`, `return_spy`,
`place_spy`, `move_troop` destination, `custom_effect` with a bare node target). Block sizes,
sub-block sizes and `ACTION_SPACE_USED = 1,516` are all unchanged; only routing moves, so
`ACTION_SPACE_VERSION = 3`.

Reusing the `assassinate` block for a *placement* is safe for the same reason Fix Plan 01's
reuse was: generic and non-generic moves never coexist in one state (measured, and T3.5(e)
keeps measuring), and the pending op + `effect_kind` one-hots in the observation tell the
network which verb the slot means in this state.

### 3.3 The census reports its coverage (fixes R-2b)

Three changes to `test_every_legal_move_in_stored_replays_maps`:

1. `_semantic_key` for a structured target becomes
   `(op, effect_kind, destination_node, trophy_colour)` — derived from `ctx.trophy_halls`, not
   from the encoder's routing, so the key can disagree with the encoder and the test can fail.
2. The test accumulates a coverage dict: states seen per `(op, effect_kind)` and per routing
   sub-block, printed on success and asserted against a checked-in expected-coverage table.
3. A branch that the stored games never reach must be listed in
   `_UNCOVERED_BY_CENSUS` with a pointer to the live-engine test that does cover it. Adding a
   name to that list is a deliberate, reviewable act; a branch in neither place fails the test.

---

## 4. Phases

### Phase 0 — Ledger entries and baseline

Add to `validation/findings.md`:

| proposed | class | severity | one-line claim |
|---|---|---|---|
| F-030 | NN-DATA | MODERATE | `seat_features` / `seat_is_current` are absolute-seat while every other observation block and the value target are perspective-relative, so three of four players get an own-stats block belonging to another seat — R-1 |
| F-031 | NN-DATA | MAJOR | `custom_effect` structured placement drops the trophy index, merging differently-coloured trophy deploys (23 of 23 gids on a live Lich state); the census's semantic key restates the encoder's routing so it cannot see it — R-2, R-2b |
| F-032 | ENGINE-OPENSPIEL | MINOR | `read_pending_generic_context_full` returns `None` — "no generic choice pending" — when only the extended read fails, contradicting its own docstring — R-3 |
| F-033 | VALIDATION-PROCESS | MINOR | `just test-all` aborts on the first failing tree, so with today's four tolerated `tests/` failures it never runs `openspiel_pyrants/tests/` — the very regression it was added to prevent — R-4 |

Baseline to record (measured in this review, at the working tree described above):
`tests/` 4 failed (3× F-015, 1× F-022); `openspiel_pyrants/tests/` 10 failed (all F-003);
`PYRANTS_NN_CENSUS=1 tests/nn/test_actions.py` green over 139 game dirs.

### Phase 1 — R-4 and R-3 first (they gate honest verification of the rest)

| ID | Test (write first) | Asserts | Fails before because |
|---|---|---|---|
| T1.1 | `just test-all` run against a tree with a failing `tests/` test | both trees run; the recipe's exit code is non-zero if *either* tree failed | `just` aborts on line 1 |
| T1.2 | `test_full_reader_degrades_to_base_on_extended_failure` (pure, monkeypatched `sym_str` raising) | the return value is not `None` and equals the 6-key base dict; the four extended keys are absent or `None` | returns `None` |
| T1.3 | existing `test_read_pending_generic_context_full` | unchanged | regression guard |

Recipe shape for T1.1 (one line, so `just` cannot abort early; both exit codes honoured):

```
test-all:
    $a = 0; $b = 0; & {{python}} -m pytest -q; $a = $LASTEXITCODE; & {{python}} -m pytest openspiel_pyrants/tests/ -q; $b = $LASTEXITCODE; if ($a -ne 0 -or $b -ne 0) { exit 1 }
```

Done when: `just test-all` reports both trees and exits 1; `pytest tests/c_engine/test_pending_context_full.py -q` passes.

### Phase 2 — R-1 observation v3

| ID | Test | Asserts | Fails before because |
|---|---|---|---|
| T2.1 | `test_seat_features_are_perspective_relative` (C engine, 3- and 4-player mid-game states with distinct `discard_size`) | for every `pid`, `seat_features[0:8]` equals that pid's own summary, and slot `k` equals `summaries[order[k]]`; the block differs between perspectives | block is identical from every perspective |
| T2.2 | `test_seat_is_current_is_seat_zero` (C engine) | `seat_is_current == [1,0,0,0]` when the encoder is called from the current player's seat, for 2/3/4 players | reads `[0,0,1,0]` |
| T2.3 | `test_observation_is_perspective_relative` (extend) | the existing `my_hand` / `seat_present` rows plus T2.1's assertion, so the contract lives in the named test | seat blocks unasserted |
| T2.4 | existing shape/leak/pending tests, `test_encoder_version_bumped` | pass with `ENCODER_VERSION == 3`; `OBS_SIZE` unchanged | version pin |
| T2.5 | `test_value_target_and_seat_features_agree_on_seat_zero` (C engine, via `iter_samples`) | for each sample, `seat_features` slot 0's `score` belongs to the same player as `final_scores[0]` | slot 0 is absolute seat 0 |

Done when: both trees run (via the Phase 1 recipe) with no new failures; `ENCODER_VERSION == 3`.

### Phase 3 — R-2 action space v3

| ID | Test | Asserts | Fails before because |
|---|---|---|---|
| T3.1 | `test_structured_placement_keys_on_trophy_colour` (pure) | `p2:0:site:0` with hall `("white","p3")` → `assassinate[site × white]`; `p2:1:site:0` → `assassinate[site × opp(p3)]`; the two differ; two slots at one node with one trophy merge | both map to `node[site]` |
| T3.2 | `test_structured_placement_unmapped_raises` (pure) | a trophy index past the hall, a non-player source, a malformed target → `UnmappedMoveError` naming the op and shape | silent `node` fallback |
| T3.3 | `test_lich_deploy_from_trophy_hall_maps_each_trophy` (**C engine**, reusing `test_card_lich.py`'s setup) | at the `deploy_from_trophy_hall` state with hall `["white","p3"]`, no gid group contains two different trophy indices; the gid count doubles from 23 to 46 | 23 of 23 gids merge |
| T3.4 | `test_select_trophy_hall_on_live_engine` (**C engine**) | a live `select_trophy_hall` state maps every move; same-colour hall indices merge, different colours do not; the `index` allow-list is the only block hit | branch has no live coverage (R-2b) |
| T3.5 | `test_steal_from_selected_trophy_on_live_engine` (**C engine**) | every move maps; slots at one node merge; the routing lands in `assassinate[node × colour]` | branch has no live coverage |
| T3.6 | `test_lich_select_target_player_on_live_engine` (**C engine**) | every move maps to a distinct `player` slot per candidate | branch has no live coverage |
| T3.7 | `test_action_layout_partitions_the_space` (update) | sizes and `ACTION_SPACE_USED == 1516` unchanged; `ACTION_SPACE_VERSION == 3` | version pin |
| T3.8 | `test_every_legal_move_in_stored_replays_maps` (extend per § 3.3) | (g) the coverage dict matches the checked-in expected table; (h) every choice-producing `(op, effect_kind)` is either covered by the census or named in `_UNCOVERED_BY_CENSUS` with a live test | no coverage accounting |
| T3.9 | `test_move_to_global_action_table` (update the two structured rows) | `deploy_from_trophy_hall` and `steal_from_selected_trophy` rows expect the colour-keyed slot; the `steal_white_trophy_to_board` row is unchanged | v2 expectations |

Done when: `PYRANTS_NN_CENSUS=1 pytest tests/nn/test_actions.py` passes with 0 semantic
collisions, the coverage table printed and asserted, and pair merges still ≤ 0.25 %.

### Phase 4 — R-5 cleanups

| ID | Test | Asserts |
|---|---|---|
| T4.1 (m1) | — | comments in `actions.py` say 240 / 1,516; `test_action_layout_partitions_the_space` already pins the numbers |
| T4.2 (m2) | `test_manifest_records_index_shas` | `manifest["op_index_sha"] == OP_INDEX_SHA` and `effect_index_sha` likewise |
| T4.3 (m3) | `test_option_beyond_block_raises` | an option at position ≥ 8 raises `UnmappedMoveError` instead of clamping, in both `actions.py` and the observation option one-hot |
| T4.4 (m4) | `test_report_metrics_null_when_no_samples` | `policy_argmax_match_frac` and `n_legal_raw_mean` are `None`, not `0.0`, on an empty dataset |
| T4.5 (m5) | existing `test_tiny_end_to_end` | unchanged; `iter_samples` maps each payload once and reuses the gids for the pair-merge check |
| T4.6 (m6) | — | correct F-026's Resolution text and reconcile the 134 / 137 / 139 game counts to one number with the command that produces it |

### Phase 5 — Rebuild, acceptance, close-out

1. `PYRANTS_NN_CENSUS=1 pytest tests/nn/test_actions.py` — 0 semantic collisions, coverage
   table asserted, pair merges ≤ 0.25 %.
2. `just test-all` — both trees, no new failures against the Phase 0 baseline.
3. `just ismcts-quick` — 2/2 replays OK, strict build, leak 0 mismatches, non-null metrics.
4. Rebuild `datasets/quick` and `datasets/sims_vs_wins_v2` (`--allow-legacy-schema
   --leak-check 200`). **Both carry `encoder_version: 2` / `action_space_version: 2` today and
   are stale the moment Phase 2 lands.** Record games, samples, leak, value means, argmax
   match and pair-merge fraction in `nn-training-data.md` § Fitness audit as a v3 acceptance
   run; keep the v2 numbers beside them for comparison.
5. Close F-030..F-033 with the measured numbers; delete the v2 datasets once v3 is accepted.

---

## 5. File map

| change | path |
|---|---|
| edit | `openspiel_pyrants/nn/observation.py` (seat blocks rotate, `ENCODER_VERSION = 3`) |
| edit | `openspiel_pyrants/nn/actions.py` (structured routing, option clamp → raise, stale comments, `ACTION_SPACE_VERSION = 3`) |
| edit | `openspiel_pyrants/nn/dataset.py` (`op_index_sha`, `effect_index_sha`) |
| edit | `engine_c/bindings/pending_context.py` (`return base` on extended-read failure) |
| edit | `scripts/_nn_dataset.py` (null metrics, reuse the mapped gids) |
| edit | `justfile` (`test-all` one line, both exit codes) |
| edit | `tests/nn/test_observation.py`, `tests/nn/test_actions.py`, `tests/test_build_nn_dataset.py`, `tests/c_engine/test_pending_context_full.py` |
| new | `tests/nn/test_actions_live_custom_effects.py` (T3.3-T3.6, the four uncovered branches) |
| docs | `nn-training-data.md` (v3 layout rows, v3 acceptance run), `validation/findings.md` (F-030..F-033, F-026 text fix), `docs/README.md` (nav line), this file's status line |

---

## 6. Risks

- **R-2's fix reuses the `assassinate` block for a placement.** Same bet as Fix Plan 01's
  reuse, and the same guard keeps it honest: T3.8(e) measures that generic and non-generic
  moves never coexist. If a future card breaks that, the assertion fires before a dataset is
  built.
- **Four branches get their first live test in Phase 3.** Expect the tests to find more than
  R-2: a wrong reading of `select_trophy_hall`'s or `steal_from_selected_trophy`'s payload
  shape would have been invisible until now. Budget for a second round of routing fixes.
- **Encoder v3 invalidates both datasets.** Cheap for `quick` (2 games), ~an hour for
  `sims_vs_wins_v2` (120 games). No run needs repeating — `replay.json` is canonical.
- **`seat_is_current` becomes four constant slots.** Deliberate, pinned by T2.2, and cheaper
  than churning `OBS_SIZE`. Revisit only when something needs the space.
- **The coverage table is a maintenance cost.** It has to be updated whenever a new card
  reaches a new branch. That is the point: the update is where a human notices the new branch.
