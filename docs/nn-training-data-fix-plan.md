# NN Training Data — Fix Plan for the Verification Findings (Review 01)

Scope: the nine findings from the 2026-09-10 verification of `nn-training-data-tdd-plan.md`
(the refined `just ismcts-quick` run `20260910T191204Z_80fae3a64f6e`, dataset `datasets/quick`,
and audits over every 6th of the 134 stored games = 23 games, 26,215 states, 18,265 non-forced).
Base: working tree at `ea25b68` with Phases 0-4 of the TDD plan applied but uncommitted.
Status: **executed** 2026-09-11 — Phases 0-5 applied. Full-census result: 0 semantic
collisions, 227/112,339 = 0.202 % pair merges (`pair_move_merge_frac = 0.00213`);
`datasets/sims_vs_wins_v2` rebuilt (120 games, 101,230 samples, leak 0/16,927). Post-review
correctness fix (same day): trophy-hall choices are keyed by trophy colour rather than physical
hall index, structured placement targets route to the destination node, and the census key was
tightened to expose the former (index sub-block 16→20; total 1,516). See the v2 acceptance run
in `nn-training-data.md` and the F-026..F-029 resolutions in `validation/findings.md`.

Each finding is reviewed against `tyrants-rulebook.md` before its fix is specified, because
most of them are not code slips: they are places where the encoder keyed a decision on
something the rulebook does not consider a choice, or ignored something it does.

---

## 0. Process constraints

Unchanged from `nn-training-data-tdd-plan.md` § 0. In addition:

1. **`just test` is blind to `openspiel_pyrants/tests/`.** Every "done when" below runs both
   `just test` and `just openspiel-test`. Phase 1 adds a `test-all` recipe so this cannot be
   forgotten again.
2. **Encoder changes bump versions.** Phases 2-4 change the observation and action layouts:
   `ENCODER_VERSION = 2`, `ACTION_SPACE_VERSION = 2`. Nothing in this plan changes what the
   runner writes, so `schema_version` stays 2 and no run needs repeating.
3. **The census is the gate.** The full 134-game census (`PYRANTS_NN_CENSUS=1`) must pass with
   the collision assertions of Phase 3 before any dataset is rebuilt.

---

## 1. Findings, each reviewed against the rulebook

Severity is my proposal; the ledger owner assigns the final class and ID (Phase 0).

### NN-1 `resolve_generic` slots merge genuinely different moves — MAJOR

**Observed.** Over the 23-game sample, 597 non-forced states (3.3 %) contain two legal moves
that map to one global action id while differing in something the rules treat as a choice, and
in 535 states (2.9 %) the *chosen* move sits in such a slot, so its visits are summed with a
different move's visits and the policy label is wrong. By pending op:

| op | states with a real collision | chosen move affected | why |
|---|---|---|---|
| `custom_effect` | 372 | 372 | card choices fall into the positional `index` fallback |
| `supplant_troop` | 96 | 96 | not in `_NODE_OWNER_OPS`; all targets fall into `index` |
| `assassinate_troop` | 53 | 16 | target is a slot index string, not `troop:N`; owner never resolved |
| modal option (`op is None`) | 27 | 27 | named option ids (`gain_influence`, `promote_end_of_turn`) both parse to index 0 |
| `return_unit` | 33 | 8 | `troop:N` and `spy:<owner>` at one node collapse to one owner slot |
| `move_troop` | 10 | 10 | positional fallback |
| `place_spy` (pair form) | 6 | 6 | destination ignored |

Code: `openspiel_pyrants/nn/actions.py:189-251` (`_resolve_generic_offset`). The shipped census
test `tests/nn/test_actions.py:234-296` builds a `mapped` dict and never inspects it, so it
cannot see any of this.

**Rulebook.** Every merged pair above is a distinct choice under the rules:

- Assassinate (`tyrants-rulebook.md:308`): "take it from a troop space and place it in the
  trophy hall … You can't assassinate your own troops." Enemy includes white troops (`:300`).
  The choice is *which* troop; two troops of different colours at one site are different
  choices, two of the same colour are not (a trophy is a trophy, `:395`).
- Supplant (`:376`, `:380`): "assassinate that troop and then deploy one of your troops in the
  newly vacated space … only enemy troops." Same keying as assassinate, never own colour.
- Return (`:363`, `:368`, `:573`): a troop *or* a spy, "only forces belonging to a player",
  "White troops cannot be returned." A troop return and a spy return at the same site are
  different actions with different effects (troop space freed vs spy removed), and the owner
  set excludes white.
- Move (`:330`): "from a space where you have Presence … to an empty troop space anywhere on
  the board." Both endpoints are choices.
- Place a spy (`:337-338`): "any site that doesn't already contain one of your spies … If …
  all your spies are already placed, you may either do nothing or first return one of your
  spies and then place it." The destination is the choice; the recalled spy is a second
  choice; "do nothing" is an explicit third option.
- Abilities with costs (`:228`, `:582`): "paying the cost of an ability is optional." Declining
  is a real move and needs its own slot.
- Promote (`:345`), devour (`:322`, `:326`), recruit (`:354`): the choice is a card. Two copies
  of the same card are not different choices.
- Modal cards: "choose one" options are distinct effects, whatever the option id is called.

**Verdict.** The v1 slot keys must be rebuilt on the rulebook's nouns: troop = (site, colour),
spy = (site, owner), card = card id, site = site, option = its position in the card's option
list, plus one "decline" slot. Pair moves (move, spy recall+place) cannot be represented
exactly by a factored head; § 3 keys them by destination and bounds the loss by census.

### NN-2 `test_failed_move_not_in_replay_log` regression — MODERATE (process)

**Observed.** `openspiel_pyrants/tests/test_run_ismcts_step_ordering.py:100` counts calls to
`state.move_to_payload` as replay entries built. `_legal_moves_payloads`
(`scripts/run_ismcts.py:332`) now calls it once per legal move per decision, so the count is
inflated and the assertion fails. Runner behaviour is unchanged (the replay entry is still
built only after `apply_action` succeeds). It was not caught because `just test` runs
`tests/` only. **Rulebook:** not applicable.

### NN-3 Dataset manifest drops its sources — MODERATE

**Observed.** `write_shards` (`openspiel_pyrants/nn/dataset.py:191`) stores
`"sources": list(sources)` where `sources` is a dict, so both datasets built so far record
`["runs", "accepted", "rejected"]` and nothing else: no run dirs, run ids, engine shas, or
rejection reasons. `tests/test_build_nn_dataset.py` passes `sources={}` / `{"runs": []}` and
never reads the field back. **Rulebook:** not applicable.

### NN-4 Pending-op vocabulary is invented — MODERATE (same root cause as NN-1)

**Observed.** `OP_IDS` in `openspiel_pyrants/nn/observation.py:40-66` lists names such as
`gain_influence`, `promote`, `recruit`, `misc`. The engine emits the card catalog's own op
strings (`engine_c/bindings/pending_context.py:21`, `sym_str(action.op)`), of which there are
exactly 17: `assassinate_troop, conditional_bonus, custom_effect, deploy_troops, devour_cost,
draw_cards, force_discard, gain_resource, grant_vp, move_troop, place_spy, play_card,
promote_card, recruit_card, return_spy, return_unit, supplant_troop`. In the sample,
5,357 of 17,311 generic legal moves (30.9 %: all of `move_troop`, `supplant_troop`,
`custom_effect`, `recruit_card`) were encoded under the "unknown" op one-hot.

**Rulebook.** The engine ops are the rulebook's action list, one for one: assassinate
(`:292`), deploy (`:318`), devour (`:321`), move (`:329`), place spy (`:331`), promote
(`:339`), recruit (`:354`), return troop/spy (`:360`), supplant (`:373`), gain Power/Influence
(`:189`), gain VP (`:214`), draw (`:327`). `custom_effect` and `conditional_bonus` are
card-specific text. **Verdict:** derive the vocabulary from the catalog, never type it.

### NN-5 Design-doc table row is stale — MINOR

`nn-training-data.md:50` (the "What the runner writes today" table) still says
"`visit_counts` is a stub. No Q or root value." while the paragraph under it describes the
Phase 2 fields. **Rulebook:** not applicable.

### NN-6 `engine_git_dirty` only watches `engine_c/` — MINOR

The manifest of the verification run says `engine_git_dirty: false` while every file that
produced it (runner, encoders, builder) is uncommitted. **Rulebook:** not applicable.

### NN-7 Report prints `0.0` for an empty metric — MINOR

`report_metrics` (`scripts/_nn_dataset.py:31-77`) returns `0.0` for
`policy_argmax_match_frac_sims_ge_200` when no sample has 200+ sims, which reads as a failed
gate. **Rulebook:** not applicable.

### NN-8 Pending block omits `optional` and repeats — MINOR

`pending_flags` (`observation.py:230-244`) never sets its last slot (`= 0` unconditionally);
`optional` from the pending context and `remaining_repeats` / `allow_repeat` from the C
struct (`engine_bindings.py:305`) are not encoded, though the design doc lists both.

**Rulebook.** `:228` / `:582`: paying an ability cost is optional; `:338`: placing a spy with
none left may be "do nothing". Whether the current choice may be declined is a rule-level fact
of the decision, not decoration. Repeats ("deploy 2 troops", resolved one at a time) are the
engine's `remaining_repeats`.

### NN-9 Board control and presence features contradict the rulebook — MODERATE

**Observed.** `observation.py:163-176`: `controller` flags every colour tied for the most
troops; `total_control` checks only that my troops fill every space; `my_presence` is
`my troops > 0` at the node.

**Rulebook.**

- Control (`:267`): "more troops of your color there than troops of any other single color."
  White counts as a colour (example `:271`: red 2, black 1, white 1 → red controls).
- Ties (`:279`, `:283`): "You lose control … when … tied with or surpassed by another color";
  "If control of the site becomes tied, return that site's control marker." A tie means
  nobody controls.
- Total control (`:281`): "all its troop spaces are filled only with your troops **and no
  enemy spies are present**."
- Presence (`:248-252`): "At any site where you have a spy, a troop, or a troop in a space
  adjacent to that site. At any troop space on a route if that space is adjacent to a site or
  space where you have a troop."

**Verdict.** Three features are wrong as encoded: controller on ties, total control with enemy
spies present, and presence without spies and adjacency. Presence gates deploy, assassinate,
return and supplant (`:308`, `:318`, `:363`, `:376`), so the network is currently shown a
presence map that disagrees with its own legal-move mask.

---

## 2. Engine facts the fixes depend on (verified in `engine_c/generic_runtime.c:852-1000`)

| pending op | `action_id` | `target_id` |
|---|---|---|
| `deploy_troops` | target node | — |
| `place_spy` | target node (destination) | source node of the spy being recalled (pair form only) |
| `assassinate_troop`, `supplant_troop` | node | troop slot index as a decimal string; owner = `troop_slots[node][index]` |
| `return_spy` | node | — |
| `return_unit` | node | `troop:<slot>` or `spy:<owner>` |
| `move_troop` | source node | `<src_slot>:<dst_node>:<dst_slot>` |
| `promote_card` | card id; **or** a hand/discard index when `source_fragment == single_promote_from_multiple_zones` | zone (`played` / `hand` / `discard`) in that form |
| `recruit_card`, `devour`, `devour_cost`, `play_card` | card id | — |
| `force_discard` | player id (`targeted_discard`, `conditional_owner_discard`) or card id | — |
| `custom_effect` | shape depends on `effect_kind` (13 kinds in the catalog): card id + pile index, node, player id + trophy index, or `sp:idx:nid:…` | |
| modal option (`awaiting_option`) | option id: `option_N` (35 cards) or a named id (`gain_influence`, `promote_end_of_turn`) | `unavailable` placeholders are filtered upstream |
| decline (`action->optional`, `generic_runtime.c:1316-1326`) | null | null |

Also verified: generic and non-generic moves never coexist in one state (0 of 26,215), so a
slot may be shared between a main-phase action and the generic action with the same rulebook
meaning without ambiguity. The board has 28 sites, 53 routes, 145 troop spaces. Pair moves are
rare but huge: `move_troop` 10 states / 2,442 moves, `place_spy` pair form 6 states / 690
moves; in 15 of those 16 states two sources share a destination.

---

## 3. Action space v2 (fixes NN-1)

Keep the eight top-level blocks unchanged (1,276 slots). Rebuild `resolve_generic` as 240
slots keyed on the rulebook's nouns, and route troop and spy targets into the existing
`assassinate` (site × {me, opp1-3, white}) and `return_spy` (site × {me, opp1-3}) blocks,
which already carry exactly that meaning. Total 1,516 of 2,048.

| sub-block | size | routes |
|---|---|---|
| `option` | 8 | modal option → its index in the pending card's `option_ids` (never parsed from the name) |
| `decline` | 1 | `action_id is None and target_id is None` |
| `node` | 81 | `deploy_troops`, `return_spy`, `place_spy` destination (single and pair form), `move_troop` destination, `custom_effect` with a node target |
| `card` | 126 | `recruit_card`, `devour`, `devour_cost`, `play_card`, `force_discard` (card), `promote_card` (index form resolved through the acting player's own hand/discard), `custom_effect` with a card target |
| `player` | 4 | `force_discard` (player), `custom_effect` with a player target |
| `index` | 20 | allow-listed `(op, shape)` positional keys: `select_trophy_hall` (source seat 4 × trophy colour 5); anything else raises `UnmappedMoveError` |

`custom_effect` structured placement targets (`deploy_from_trophy_hall`,
`steal_from_selected_trophy`, and `steal_white_trophy_to_board` step 2) route to the
destination node / white owner slot; `steal_white_trophy_to_board` step 1 and
`select_trophy_hall` choose a trophy, keyed by the trophy's colour rather than its physical
hall index (an index above the 4 colours would otherwise be unrepresentable).

Reused blocks: `assassinate_troop`, `supplant_troop`, `return_unit` `troop:N` → `assassinate[site × owner]`;
`return_unit` `spy:<owner>` → `return_spy[site × owner]`.

**Known approximation, bounded.** A factored head cannot express a (source, destination) pair
(81 × 81 for moves, 28 × 28 for spy recalls). v2 keys both by destination and merges sources.
The census counts these merges; the bound is ≤ 0.2 % of non-forced states (measured 16 of
18,265 = 0.09 %). This is the one place the v2 per-move scoring head of the design doc is the
real fix; it is recorded in the dataset manifest as `pair_move_merge_frac`.

Alternative considered: keep `resolve_generic` self-contained (+729 slots for its own troop
and spy targets, 2,241 total, pad to 4,096). Rejected: the rulebook uses one verb for the
main-phase and card-driven forms of each action, so one slot is the truer key.

---

## 4. Phases

### Phase 0 — Ledger entries and baseline

Add to `validation/findings.md` (proposed ids and classes; owner decides):

| proposed | class | severity | one-line claim |
|---|---|---|---|
| F-026 | NN-DATA | MAJOR | v1 `resolve_generic` action slots merge rulebook-distinct moves (2.9 % of chosen moves in a 23-game census) and the op one-hot uses invented names (30.9 % of generic moves encoded as "unknown") — NN-1, NN-4 |
| F-027 | NN-DATA / RULE-ENGINE | MODERATE | board `controller`, `total_control`, `my_presence` features contradict `tyrants-rulebook.md:248-283` — NN-9 |
| F-028 | VALIDATION-PROCESS | MODERATE | dataset manifest records only the key names of its `sources` — NN-3 |
| F-029 | VALIDATION-PROCESS | MINOR | `just test` does not run `openspiel_pyrants/tests/`; the layer-1 change broke a committed ordering test unnoticed — NN-2 |

Baseline to record: `tests/` 1001 passed / 4 failed (3× F-015, 1× F-022 local artifact);
`openspiel_pyrants/tests/` 104 passed / 11 failed (10× F-003 by design, 1× NN-2).

### Phase 1 — Quick fixes (NN-2, NN-3, NN-5, NN-6, NN-7)

| ID | Test (write first) | Asserts | Fails before because |
|---|---|---|---|
| T1.1 | existing `test_failed_move_not_in_replay_log` | passes once `_legal_moves_payloads` calls `state.decode_action(aid).to_payload()` (the same dict, without the wrapper method) | counter inflated |
| T1.2 | `test_write_shards_records_sources` (pure) | `manifest["sources"]["runs"][0]["run_id"] == "abc"`, `accepted` and `rejected` lists round-trip, and `sources` is a dict | it is a list of three strings |
| T1.3 | `test_cli_smoke` (extend) | `sources.accepted[0].run_id` equals the run manifest's `run_id`; `sources.runs[0].engine_git_sha` is 40 hex | `TypeError` on the list |
| T1.4 | `test_report_metrics_null_when_no_200_sim_samples` (pure) | metric is `None`; report also carries `argmax_n` and `argmax_n_sims_ge_200` counts | returns `0.0` |
| T1.5 | `test_collect_engine_provenance_reports_repo_dirty` (pure, injected `run`) | new `repo_git_dirty` from `git status --porcelain` on the whole tree; `engine_git_dirty` unchanged; both in the manifest (extend T1.2 of the TDD plan) | `KeyError` |
| T1.6 | `just test-all` recipe exists and runs both trees | `just --list` shows it; the TDD plan's "done when" lines cite it | recipe absent |

Docs: rewrite the `decisions.jsonl` row at `nn-training-data.md:50`. Run `just docs-check`.

### Phase 2 — Pending context and op vocabulary (NN-4, NN-8; `ENCODER_VERSION = 2`)

The runner's logged `pending_context` stays as it is (6 keys, schema 2). The builder and the
encoder read the engine at replay time (TDD plan D12), so the extra fields come from a new,
additive reader rather than a schema bump.

| ID | Test | Asserts | Fails before because |
|---|---|---|---|
| T2.1 | `test_read_pending_generic_context_full` (C engine, gauth session from `tests/c_engine/card_test_helpers.py`) | `read_pending_generic_context_full(ptr)` returns the 6 existing keys plus `option_ids == ["option_1", "option_2"]`, `remaining_repeats`, `allow_repeat`, `effect_kind` (metadata `effect_kind` when `op == "custom_effect"`, else `None`); the 6-key reader is byte-for-byte unchanged | `ImportError` |
| T2.2 | `test_op_vocabulary_is_the_catalog` (pure) | `index.OP_IDS` equals the sorted set of `op` strings found in `data/cards/*.json` (17 today), `OP_INDEX_SHA` pinned, slots = 17 + `__option__` + `__unknown__`; `op_index("supplant_troop")` is not the unknown slot | `OP_IDS` is hand-typed |
| T2.3 | census extension (T3.5 below) | every pending op met over stored games maps to a non-unknown slot; `awaiting_option` maps to `__option__` | 30.9 % unknown |
| T2.4 | `test_pending_flags_encode_optional_and_repeats` (C engine) | with a card whose action has `optional: true` (Insane Outcast, rulebook `:228`) the `optional` bit is 1 and the decline move is legal; `remaining_repeats` and `allow_repeat` land in their slots; no pending → block all zero | last flag hard-coded 0 |
| T2.5 | `test_effect_kind_one_hot` (pure) | 13 catalog `effect_kind`s + unknown; set only when `op == "custom_effect"` | block absent |
| T2.6 | existing `test_observation_shape_dtype_range`, leak test, perspective test | pass with the new `OBS_LAYOUT`; `ENCODER_VERSION == 2` | layout constants change |

### Phase 3 — Action space v2 (NN-1; `ACTION_SPACE_VERSION = 2`)

`ActionContext` gains `option_ids`, `my_hand`, `my_discard` (from the private view) and
`action_context(adapter, pid, pending_full)` takes the full pending dict instead of the bare op.

| ID | Test | Asserts | Fails before because |
|---|---|---|---|
| T3.1 | `test_action_layout_partitions_the_space` (update) | v2 sizes: `resolve_generic` = 240 with the six sub-blocks of § 3, total used 1,516, `ACTION_SPACE_VERSION == 2` | v1 sizes |
| T3.2 | `test_move_to_global_action_table` (extend, one row per § 2 line) | `assassinate_troop` / `supplant_troop` slot-index target → `assassinate[site × owner]`; `return_unit` `troop:N` → `assassinate` block, `spy:p3` → `return_spy` block; `move_troop` `"0:site_x:1"` → `node[site_x]`; `place_spy` pair → `node[destination]`; `place_spy` single → `node`; decline → `decline`; option by position for both `option_2` and `promote_end_of_turn`; `promote_card` index form → `card` via `my_discard[idx]`; `custom_effect` card + pile index → `card`; player targets → `player`; `force_discard` card → `card` | v1 routing |
| T3.3 | `test_duplicate_equivalent_moves_merge` (extend) | two slot indices with the same owner merge; different owners do not; troop vs spy at one site and owner do not; two instances of one card merge; two sources to one destination merge (documented) | v1 |
| T3.4 | `test_unmapped_move_raises` (extend) | an unknown `custom_effect` target shape off the allow-list raises `UnmappedMoveError`; the message names the op and shape | silent `index` fallback |
| T3.5 | `test_every_legal_move_in_stored_replays_maps` (rewrite; default 3 games, full census under `PYRANTS_NN_CENSUS=1`) | (a) every move maps; (b) two legal moves sharing a gid have equal *semantic keys* — the test's own key: `(op, site, owner)` for troop targets with owner from `troop_slots`, `(op, site, "spy", owner)` for spies, `(op, card_id)` for cards, `(op, option position)` for options, `(op, source, destination)` for pair moves — except pair moves differing only in source, which are counted; (c) counted pair merges ≤ 0.2 % of non-forced states; (d) `index` slots are hit only by allow-listed `(op, shape)` pairs; (e) no state mixes generic and non-generic moves; (f) every pending op is in `OP_IDS` (T2.3) | (b) not asserted today |
| T3.6 | `test_tiny_end_to_end` (extend) | shards carry `n_legal_raw` per sample; manifest carries `pair_move_merge_frac`; report prints both | fields absent |
| T3.7 | `test_legacy_mode_reproduces_v2_targets` (existing) | still identical between legacy and v2 builds under the v2 action space | regression guard |

### Phase 4 — Board features per rulebook (NN-9; same `ENCODER_VERSION = 2` bump)

A pure helper `node_features(troop_slots, spies, capacity, order, adjacency)` in
`observation.py`, unit-tested without the engine; `index.py` gains `NODE_ADJACENT` from the
board JSON's `adjacent_to`.

| ID | Test | Asserts | Fails before because |
|---|---|---|---|
| T4.1 | `test_controller_is_strict_majority` (pure) | counts `[2,1,0,0,1]` → controller me; `[1,1,0,0,0]` → no controller; `[0,0,0,0,2]` → white; `[0,3,0,0,3]` → none (tie with white) — rulebook `:267`, `:271`, `:279`, `:283` | ties flag every leader |
| T4.2 | `test_total_control_requires_no_enemy_spies` (pure) | all spaces mine and `spies == []` → 1; all spaces mine and an opponent spy → 0; one space empty → 0 — rulebook `:281` | spies ignored |
| T4.3 | `test_presence_follows_rulebook` (pure, 3-node hand-built board) | my spy at site → presence; my troop adjacent to site → presence; route space adjacent to my troop → presence; nothing nearby → 0 — rulebook `:248-252` | presence = my troops at the node |
| T4.4 | `test_presence_agrees_with_engine_deploy_targets` (C engine, 3 stored games) | at every main-phase state, every node the engine lists as a `deploy` target has `my_presence == 1` (necessary direction; rulebook `:318`) | disagreement on adjacency-only presence |
| T4.5 | leak test, perspective test (existing) | unchanged (board is public) | regression guard |

### Phase 5 — Rebuild, acceptance, close-out

1. `PYRANTS_NN_CENSUS=1 pytest tests/nn/test_actions.py` over all 134 games: 0 semantic
   collisions, pair merges ≤ 0.2 %, `index` usage only on the allow-list.
2. `just ismcts-quick` (unchanged recipe) → 2/2 replays OK, strict build, leak 0 mismatches,
   report shows `pair_move_merge_frac` and non-null metrics.
3. Rebuild `datasets/sims_vs_wins_v2` from the 120-game experiment with
   `--allow-legacy-schema --leak-check 200`; record accepted/rejected, samples, leak, value
   means, argmax match, pair-merge fraction in `nn-training-data.md` § Fitness audit.
4. Close F-026..F-029 in the ledger with the census numbers; delete `datasets/sims_vs_wins_v1`.

---

## 5. File map

| change | path |
|---|---|
| edit | `scripts/run_ismcts.py` (one line, NN-2), `scripts/_run_layout.py` (`repo_git_dirty`), `scripts/_nn_dataset.py` (report nulls, counts, `n_legal_raw`, pair-merge fraction), `openspiel_pyrants/nn/dataset.py` (`sources`, new columns), `justfile` (`test-all`) |
| edit | `engine_c/bindings/pending_context.py` (`read_pending_generic_context_full`, additive) |
| edit | `openspiel_pyrants/nn/index.py` (`OP_IDS`, `OP_INDEX_SHA`, `EFFECT_KINDS`, `NODE_ADJACENT`), `openspiel_pyrants/nn/actions.py` (v2 layout and routing, `ActionContext` fields), `openspiel_pyrants/nn/observation.py` (v2 pending block, `node_features`) |
| edit | `tests/nn/test_actions.py`, `tests/nn/test_observation.py`, `tests/nn/test_index.py`, `tests/test_build_nn_dataset.py`, `tests/test_run_ismcts_layer0.py` |
| new | `tests/c_engine/test_pending_context_full.py` |
| docs | `nn-training-data.md` (table row, v2 layout, acceptance numbers), `validation/findings.md` (F-026..F-029), this file's status line |

---

## 6. Risks

- **Block reuse assumes generic and main-phase moves never coexist.** Measured true on 26,215
  states; T3.5(e) keeps measuring. If a future card breaks it, the assertion says so before a
  dataset is built.
- **`custom_effect` shapes are open-ended.** The allow-list is the only thing standing between
  a new card and a silent positional label; T3.4 makes the failure loud instead.
- **Pair moves stay approximate in v1.** 0.09 % of states today; the manifest reports the
  fraction so a training run can drop those samples with one filter.
- **Presence via adjacency needs the board graph.** `adjacent_to` is in the board JSON and
  static, so it belongs in `index.py` beside the node table, never read from the engine.
