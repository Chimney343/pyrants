# NN Training Data — Test-Driven Implementation Plan

Implements the **Proposed layout** section of `nn-training-data.md` (layers 0, 1, 2).
Status: plan, not started. Written 2026-09-10 against commit `ea25b68`; every code fact below
was re-verified in the working tree at that commit, not taken from the design doc.

Baseline: `pytest -q` collects 939 tests (`tests/` only; `openspiel_pyrants/tests/` runs
separately via `just openspiel-test`). Tolerated pre-existing failures: the three F-015 card
tests (Zuggtmoy, Air Elemental, Neogi) and the three F-022 artifact-pinned tests when the local
`artifacts/ismcts/game_0000` has drifted.

---

## 0. Process constraints

Same rules as `validation/f011-fix-plan.md` § 0, restated because they bind here too:

1. **Every behavioural change starts as a failing test.** Each phase lists its tests with the
   failure each must show *before* implementation. A phase's implementation does not start
   until its tests are written, run, and observed to fail for the stated reason.
2. **One phase, one commit.** Tests, implementation and doc updates for a phase land together.
   Phases are ordered 0 → 4 and each must leave the whole suite green (modulo the tolerated set).
3. **Register the defect first.** The mixed-run directories (`nn-training-data.md` § Fitness
   audit) become finding F-025 in `validation/findings.md` before the runner is touched, with
   the Phase 1 regression test as its falsification test.
4. **Layer 2 is disposable, layers 0-1 are not.** Anything that changes what the runner writes
   needs a schema bump and a legacy path in the builder. Anything in the encoders only needs an
   `ENCODER_VERSION` / `ACTION_SPACE_VERSION` bump and a dataset rebuild.
5. New tests live under `tests/` so plain `pytest -q` collects them. C-engine tests use the
   existing `requires_c_engine` fixture (`tests/conftest.py`).

---

## 1. Verified ground truth

Facts the plan depends on, checked this session. Where the design doc says something different
the deviation is called out in § 2.

| # | Fact | Where |
|---|---|---|
| G1 | The runner writes `game_XXXX/` straight under `--output-dir`; no run scoping, no manifest. | `scripts/run_ismcts.py:263` (`_game_dir`), `:1169` (`main`) |
| G2 | The experiment scripts already nest `<UTC ts>_<run_id>/` themselves. | `scripts/run_ismcts_uct_sweep.py:58-61` |
| G3 | Success-path write order is `replay.json`, `summary.json`, `final_decks.json`. Crash path: `replay.json` then `summary.json`. Nothing is written atomically. | `scripts/run_ismcts.py:981-993`, `:766-775` |
| G4 | `steps.jsonl` and `decisions.jsonl` are opened with `"w"` before the game loop, so a second run into the same dir silently overwrites file by file. | `scripts/run_ismcts.py:530-531` |
| G5 | `visit_counts` is the stub `{chosen: 1}`. | `scripts/run_ismcts.py:646` |
| G6 | The stock bot returns before touching `_root_node` when exactly one action is legal, so `_root_node` is stale on forced moves. `child.return_sum` accumulates `returns[cur_player]`, i.e. the acting player's `returns()` units (score difference for 2 players, raw score for 3-4). | `open_spiel/python/algorithms/ismcts.py` `run_search` (lines 110-121) and `run_simulation`; `openspiel_pyrants/state_c.py:171` |
| G7 | `read_pending_generic_context(ptr)` returns the 6-key dict or `None`, and must be read before `apply_action`. | `engine_c/bindings/pending_context.py:21` |
| G8 | `compute_c_action_map` drops `unavailable` placeholders and defines the runner's action-id order. The builder must call the same function for parity. | `openspiel_pyrants/action_encoding_c.py:17-36` |
| G9 | `engine_determinize` pools each opponent's hand+deck+discard and reshuffles them, and reshuffles the market deck. It never touches the board, the market row, played cards, inner circles or trophy halls. | `engine_c/state.c:271-318` |
| G10 | `CGameView` exposes public scalars the private view does not: `house_guard_remaining`, `priestess_remaining`, `insane_outcast_remaining`, `devour_pile`, `market_deck_count`, `market_discard_count`. | `engine_c/bindings/engine_bindings.py:420-434` |
| G11 | `setup_data_json` differs per game: a deck pair is drawn per `game_index`. | `scripts/run_ismcts.py:128` |
| G12 | Payload shapes in the 134 stored replays: `play_card{card_id,hand_index}`, `recruit{card_id}`, `promote_card{card_id}`, `skip_promote{source_card_id}`, `initial_placement{target_node_id}`, `deploy{target_node_id,troop_count}`, `assassinate{target_node_id,target_slot_index}`, `return_spy{node_id,spy_owner_id}`, `resolve_generic_choice{action_id,target_id,selection_index}`, and four bare types. `assassinate` carries a slot index, not an owner. | census over `artifacts/ismcts/**/replay.json` |
| G13 | Legacy `decisions.jsonl` lines carry exactly 14 keys and no `generic`/`pending_context`. | census over 44,660 lines |
| G14 | The catalog has 125 card ids across 127 files (`cards_OCR.json` and `manifest.json` are not cards). The board has 81 nodes. | `data/cards/`, `data/boards/tyrants_of_the_underdark.json` |
| G15 | Two tests assume the flat layout after `main()`: `openspiel_pyrants/tests/test_ismcts_reproducibility.py:276-283` and `tests/test_run_ismcts_crash_capture.py:408-435`. | — |
| G16 | The replay viewer tolerates an empty `visit_counts`. | `interface/replay_viewer.py:382` |
| G17 | `ReplayPlayer._apply_entry` matches a logged payload against `to_payload()` of the live legal moves. | `interface/replay_player.py:93-103` |
| G18 | `load_replay` recomposes the setup from deck ids and checks `setup_data_sha256`. | `interface/replay_loader.py:186-199`, `:229-231` |

---

## 2. Design decisions (deviations from the design doc are marked ⚠)

- **D1 Run dir is created by `main()` only.** `DEFAULT_OUTPUT_DIR` becomes
  `artifacts/ismcts/runs`; `main()` creates `<output_dir>/<YYYYMMDDTHHMMSSZ>_<run_id>/` and
  everything that used `args.output_dir` (games, `metrics.json`, `summary.csv/.md`,
  `failures.jsonl`) moves under it. `run_one_game` keeps its signature; the experiment scripts
  (G2) are unaffected. The `ismcts` justfile recipe stops creating its own `run-<ts>-<id>` dir.
- **D2 Collision guard at the source.** `run_one_game` refuses to open a `game_XXXX/` that
  already holds a `replay.json` or `decisions.jsonl` from a different `run_id`. This is the
  F-025 regression test's subject; it protects the experiment scripts and tests too.
- **D3 ⚠ Manifest carries a per-game table.** The doc says "inline `setup_data_json` in the run
  manifest"; G11 shows it varies per game. `manifest.json` therefore has
  `games: [{game_index, shuffle_seed, deck_a_id, deck_b_id, setup_data_sha256, setup_data_json}]`,
  computed up front and written before the first game starts.
- **D4 Engine provenance is three fields**: `engine_git_sha`, `engine_git_dirty`
  (`git status --porcelain -- engine_c`), and `engine_dll_sha256` of `engine_c/engine_c.dll`,
  because the DLL can lag the source. Git being unavailable must never fail a run (fields null).
- **D5 `schema_version: 2`** on `manifest.json`, `replay.json`, `summary.json`. Decision lines
  are not versioned individually; the builder reads the version from `summary.json`.
- **D6 Forced-move lines** carry `visit_counts: {}`, `q_values: {}`, `root_value: null`,
  `total_visits: 0`. Non-forced lines carry `visit_counts` over *every* legal id (zeros
  included, matching `child_info`), `q_values` only where visits > 0.
- **D7 Write order and atomicity.** Success: `replay.json` → `final_decks.json` →
  `summary.json`. Crash: `replay.json` → `summary.json`. All four go through one
  `write_json_atomic` (tmp file + `os.replace`). Completeness is one predicate,
  `is_complete_game(game_dir)`, in `interface/replay_loader.py` (Tk-free, pyspiel-free) so the
  viewer, `verify_replays.py` and the builder agree.
- **D8 ⚠ Action encoder takes a context.** The doc's `move_to_global_action(payload, pending_op)`
  cannot map `assassinate` (G12: slot index, no owner). Signature is
  `move_to_global_action(payload, ctx: ActionContext)` with
  `ActionContext(acting_player_id, seat_order, troop_slots_by_node, pending_op)`.
- **D9 ⚠ No event-driven history tracker in v1.** Every "history-derived" block in the doc's
  observation table (opponent owned bags, own deck remainder, remaining market multiset) is a
  multiset that is invariant under `engine_determinize` (G9) and public knowledge by the doc's
  own argument. v1 reads them through one allow-listed function `public_multisets(adapter, pid)`
  and *proves* the public-knowledge claim in tests (determinize invariance + the
  `final_decks.json` oracle) instead of re-deriving them from move payloads, which G12 shows is
  fragile (e.g. `give_insane_outcast` adds a card to an opponent's bag with no recruit move).
  Signature: `encode_observation(adapter, player_id, pending_ctx) -> np.ndarray[int16]`.
  Opponent discard is **not** encoded separately (G9 would make the leak test fail).
- **D10 Observation values are small non-negative integers** in v1, stored as `int16` and
  widened to float at load time. A build-time assert enforces the range.
- **D11 Shards store raw inputs, loaders compute targets.** `final_scores` per seat,
  `legal_ids`/`visits`/`q` in ragged CSR form; `value_targets` and `policy_target` are pure
  functions in `openspiel_pyrants/nn/targets.py` applied by `load_shard`. Changing the value
  normalisation never requires a rebuild.
- **D12 Legacy mode** (`--allow-legacy-schema`) makes the 120-game experiment usable now:
  visits are recovered as `round(policy × (sims_requested − 1))` with an integrality assert;
  alignment uses the `legal_moves` strings (`str(move)`) instead of payloads; the pending context
  always comes from the engine at replay time (G7), for v2 games too, with the logged
  `pending_context` used only as a cross-check.
- **D13 `--no-steps` flag** on the runner (default on, to keep the viewer working); the manifest
  records `steps_enabled`. A "training profile" default is a later decision.

---

## 3. Phase 0 — Register F-025 and pin the baseline (docs only)

Add to `validation/findings.md`:

- Summary-table row: `F-025 | ENGINE-OPENSPIEL | MODERATE | scripts/run_ismcts.py writes
  game_XXXX/ straight into --output-dir and overwrites file by file, so two runs into one
  directory leave decisions/steps from one run beside replay/summary from another; the top-level
  artifacts/ismcts/game_0000..0003 are in that state today`.
- § 3 entry in the house format (Class, Severity, Origin, Code = G1/G4 citations, Disagreement,
  Steelman, Falsification test = `pytest tests/test_run_ismcts_layer0.py::test_second_run_into_same_dir_is_refused`,
  Expected if REAL = the test fails with `decisions.jsonl run_id == B` while `replay.json run_id == A`,
  Status OPEN). Cross-reference F-018 and F-022.

Done when: the entry exists and the Phase 1 test T1.9 is written and observed failing.

---

## 4. Phase 1 — Layer 0: run dir, manifest, schema version, summary last

New test file `tests/test_run_ismcts_layer0.py`; additions to `tests/test_replay_loader.py`.
Pure helpers land in a new `scripts/_run_layout.py` (no pyspiel import, so tests stay cheap).

### 4.1 Tests (write first; expected failure in brackets)

| ID | Test | Asserts | Fails before because |
|---|---|---|---|
| T1.1 | `test_run_dir_name_is_utc_timestamp_and_run_id` | `run_dir_name("abc123", now=datetime(2026,9,10,12,0,0,tzinfo=UTC)) == "20260910T120000Z_abc123"` | `ImportError` on `scripts._run_layout` |
| T1.2 | `test_main_nests_run_dir_and_writes_manifest` (C engine) | `main()` with `--output-dir tmp --num-games 1 --num-sims 2 --max-rounds 3 --workers 1`; `tmp` has exactly one child dir; it holds `manifest.json`, `game_0000/`, `summary.csv`, `summary.md`, `metrics.json`; manifest has `schema_version == 2`, `run_id`, `engine_git_sha` (40 hex or null), `engine_git_dirty` (bool or null), `engine_dll_sha256` (64 hex), `steps_enabled`, `config` containing every CLI arg, `games[0].setup_data_json` whose `sha256[:16]` equals `game_0000/summary.json["setup_data_sha256"]` | `game_0000` is found directly under `tmp`, no child dir |
| T1.3 | `test_manifest_written_before_first_game` | monkeypatch `run_one_game` to raise; manifest exists anyway | `manifest.json` never written |
| T1.4 | `test_replay_and_summary_carry_schema_version` (C engine) | after `run_one_game`: both files have `schema_version == 2`; crash path (reuse `_flaky_game` from `openspiel_pyrants/tests/test_run_ismcts_step_ordering.py`) writes a partial summary with `schema_version == 2` and `stopped_reason == "error"` | `KeyError: 'schema_version'` |
| T1.5 | `test_summary_is_written_last` (C engine) | wrap `scripts.run_ismcts.write_json_atomic` with a recorder; order of basenames is `["replay.json", "final_decks.json", "summary.json"]`; a second variant raises on the `final_decks.json` write and asserts `summary.json` does not exist while `replay.json` does | `AttributeError: write_json_atomic` |
| T1.6 | `test_write_json_atomic_leaves_no_partial_file` | `write_json_atomic(path, {"x": object()})` raises `TypeError`; `path` does not exist; no `*.tmp` sibling remains | `ImportError` |
| T1.7 | `test_is_complete_game` (pure) | no `summary.json` → False; `stopped_reason` `"error"`/`"round_cap"` → False; `"terminal"` → True; malformed JSON → False | `ImportError` on `is_complete_game` |
| T1.8 | `test_collect_engine_provenance` | injected fake `run` returning sha + porcelain lines → `dirty is True`; empty porcelain → `False`; `FileNotFoundError` from `run` → sha/dirty `None` and no exception; `engine_dll_sha256` equals `hashlib.sha256` of the DLL bytes (tmp fake DLL path) | `ImportError` |
| T1.9 | `test_second_run_into_same_dir_is_refused` (C engine; **F-025 falsification**) | `run_one_game(run_id="A", num_players=2)` then `run_one_game(run_id="B", num_players=4)` into the same `out_dir`; expects `GameDirCollisionError`; afterwards every line of `decisions.jsonl` and `replay.json["run_id"]` still say `"A"` | no exception; `decisions.jsonl` says `B`, `replay.json` says `A` |
| T1.10 | `test_replay_bundle_exposes_schema_version_and_manifest` (pure) | `load_replay` on a synthetic v2 dir with a sibling `manifest.json` → `bundle.schema_version == 2`, `bundle.manifest["run_id"]`, and `bundle.setup_json` is the manifest's inline JSON (not recomposed) when its sha matches; legacy dir → `schema_version is None`, `manifest is None` | `AttributeError` on `ReplayBundle` |
| T1.11 | `test_discover_replays_finds_nested_run_dirs` (pure) | `_write_replay(tmp/"20260910T120000Z_abc"/"game_0000")` is discovered | passes already (rglob); kept as the layout contract |
| T1.12 | Migrate G15 tests | both tests resolve the single run dir with a shared helper `only_run_dir(base)` instead of reading `base/game_0000` | they fail on `FileNotFoundError` once D1 lands |

### 4.2 Implementation

- `scripts/_run_layout.py`: `SCHEMA_VERSION = 2`, `run_dir_name(run_id, now=None)`,
  `collect_engine_provenance(root, run=subprocess.run)`, `write_json_atomic(path, obj)`,
  `build_manifest(*, run_id, args, games, provenance, steps_enabled)`, `GameDirCollisionError`.
- `interface/replay_loader.py`: `is_complete_game(game_dir)`; `ReplayBundle.schema_version`,
  `ReplayBundle.manifest`; `load_replay` prefers the manifest's inline setup when the sha matches
  (fallback unchanged, G18). Update the module docstring's layout block.
- `scripts/run_ismcts.py`: D1 in `main()` (manifest first, then games); `_base_game_summary`
  and `build_replay_payload` (`scripts/_replay_payload.py`) gain `schema_version`; D2 guard
  before line 530; D7 write order through `write_json_atomic`; `--no-steps` (D13).
- `justfile`: `ismcts` recipe passes `--output-dir {{output_dir}}` and lets the runner nest.
- `scripts/verify_replays.py`: print a trailing `INCOMPLETE` status for dirs where
  `is_complete_game` is false (no behaviour change for complete dirs).

### 4.3 Done when

All of T1.1-T1.12 pass; `just test-all` is green; `just verify-replays` still reports 134/134 on the local artifacts;
`just ismcts-quick` produces `artifacts/ismcts/runs/<ts>_<id>/manifest.json`.

---

## 5. Phase 2 — Layer 1: real search telemetry in `decisions.jsonl`

New test file `tests/test_run_ismcts_decision_telemetry.py`. The extraction helper is pure and
duck-typed on `child_info` / `visits` / `return_sum` / `total_visits`, so it lives in a
pyspiel-free module `scripts/_decision_telemetry.py`.

### 5.1 Line schema (v2)

Existing 14 keys unchanged (`policy` stays for the viewer), plus:

```
visit_counts        {action_id: int}     every legal id; {} on forced moves
q_values            {action_id: float}   mean return in the acting player's returns() units; visits > 0 only
root_value          float | null         sum(return_sum) / total_visits; null on forced moves
total_visits        int                  0 on forced moves; equals sims_requested - 1 otherwise
legal_moves_payload [dict]               to_payload() per legal id, same order as legal_action_ids
pending_context     dict                 the 6-key read_pending_generic_context dict; present only when a generic choice is pending
```

`generic` and `chosen_label` stay exactly as they are on `resolve_generic` lines.

### 5.2 Tests

| ID | Test | Asserts | Fails before because |
|---|---|---|---|
| T2.1 | `test_root_stats_forced_move_ignores_stale_root` (pure) | fake bot with a populated `_root_node`; `extract_root_stats(bot, legal_ids=[0])` → `{"visit_counts": {}, "q_values": {}, "root_value": None, "total_visits": 0}` | `ImportError` |
| T2.2 | `test_root_stats_reads_child_info` (pure) | children `(visits, return_sum)` = `(3, 6.0), (0, 0.0), (1, -2.0)`, `total_visits 4` → `visit_counts {0:3, 1:0, 2:1}`, `q_values {0: 2.0, 2: -2.0}`, `root_value 1.0`; every value is a builtin `int`/`float` (json-serialisable, numpy scalars rejected) | `ImportError` |
| T2.3 | `test_root_stats_without_root_attribute` (pure) | a bot object with no `_root_node` (the scripted bots in `tests/test_run_ismcts_generic_context.py`) → forced-move shape, no exception | `ImportError` |
| T2.4 | `test_decision_lines_have_real_visits` (C engine, `num_sims=4`, `max_rounds=3`) | for every line: the six new keys exist; forced lines have the D6 shape; non-forced lines satisfy `set(visit_counts) == set(legal_action_ids)`, `sum(visit_counts.values()) == total_visits == sims_requested - 1`, `set(q_values) == {a for a,v in visit_counts.items() if v > 0}`, `policy[a] ≈ visit_counts[a] / total_visits`, `root_value ≈ Σ visits·q / total_visits` | `KeyError: 'q_values'`; the stub has one key |
| T2.5 | `test_legal_moves_payload_aligns_with_replay` (C engine) | `len(legal_moves_payload) == len(legal_action_ids)` and `legal_moves_payload[legal_action_ids.index(chosen_action_id)] == replay_log[node]["payload"]` on every node | `KeyError: 'legal_moves_payload'` |
| T2.6 | `test_pending_context_present_iff_generic_choice_pending` (C engine, scripted card-playing bot) | lines whose `legal_moves_payload` contains a `resolve_generic_choice` have `pending_context` with the 6 keys and `pending_context["source_card_id"] == generic["source_card_id"]` when `generic` is present; other lines have no `pending_context` | `KeyError: 'pending_context'` |
| T2.7 | `test_stub_is_gone` (C engine) | no non-forced line has `len(visit_counts) == 1` while `len(legal_action_ids) > 1` | the stub always has one key |
| T2.8 | `test_no_steps_flag_skips_steps_jsonl` (C engine) | `run_one_game(..., write_steps=False)` writes no `steps.jsonl`; a crash in that mode still records `failures.jsonl` (reuse `_flaky_game`) | `TypeError: unexpected kwarg` |
| T2.9 | Existing `tests/test_run_ismcts_generic_context.py` and `openspiel_pyrants/tests/test_run_ismcts_runner.py::TestPerSeatBudgets` keep passing | regression guard | — |

### 5.3 Implementation

- `scripts/_decision_telemetry.py`: `extract_root_stats(bot, legal_ids) -> dict`.
- `scripts/run_ismcts.py` around lines 599-660: read `pending_context` once before
  `apply_action` and feed it to `_enrich_resolve_generic` (which today re-reads it) so both
  fields come from one read; build `legal_moves_payload` from
  `state.move_to_payload(state.decode_action(a))` (the action map is cached after
  `legal_actions()`); replace line 646 with the extracted stats; `write_steps` parameter plumbed
  from `--no-steps` through `_run_one_game_standalone` and `main`.
- Measure `decisions.jsonl` growth on one 4-player game and record it in
  `nn-training-data.md` § What the runner writes today (expected +30-50 %).

### 5.4 Done when

T2.1-T2.9 pass; `just test-all` is green; a fresh `just ismcts-quick` game shows `sum(visit_counts) == sims - 1` on its
first non-forced line when inspected by hand.

---

## 6. Phase 3 — Layer 2a: encoders (`openspiel_pyrants/nn/`)

New package, no pyspiel import at module level (only `engine_c.bindings` and numpy), so the
builder can run in worker processes without OpenSpiel.

```
openspiel_pyrants/nn/__init__.py
openspiel_pyrants/nn/index.py        CARD_IDS (125, sorted), UNKNOWN_CARD, CARD_INDEX_SHA, NODE_IDS (81), NODE_INDEX_SHA
openspiel_pyrants/nn/public.py       public_multisets(adapter, pid) -> PublicMultisets (D9)
openspiel_pyrants/nn/observation.py  ENCODER_VERSION, OBS_SIZE, OBS_LAYOUT, encode_observation(adapter, pid, pending_ctx)
openspiel_pyrants/nn/actions.py      ACTION_SPACE_VERSION, NUM_GLOBAL_ACTIONS=2048, ACTION_LAYOUT, ActionContext, move_to_global_action, legal_mask, UnmappedMoveError
openspiel_pyrants/nn/targets.py      value_targets, policy_target, merge_duplicates, sample_weight
```

Tests in `tests/nn/` (`test_index.py`, `test_actions.py`, `test_observation.py`,
`test_targets.py`). Shared fixtures in `tests/nn/conftest.py`: `mid_game_adapter(num_players,
seed, n_moves)` built the way `openspiel_pyrants/tests/test_observation_completeness.py`
builds `_mid_game_state`, and `pending_gauth_session` reusing `make_card_test_session` from
`tests/c_engine/card_test_helpers.py`.

### 6.1 Tests

| ID | Test | Asserts | Fails before because |
|---|---|---|---|
| T3.1 | `test_card_and_node_index_are_stable` | `len(CARD_IDS) == 125`, sorted, `UNKNOWN_CARD` is index 125, `CARD_INDEX_SHA` equals a pinned value; `len(NODE_IDS) == 81`, pinned `NODE_INDEX_SHA` (a catalog change must be a deliberate pin update) | `ImportError` |
| T3.2 | `test_action_layout_partitions_the_space` | block ranges are disjoint, contiguous from 0, total ≤ 2048, and the per-block sizes match the doc's table (126, 126, 127, 81, 82, 405, 324, 5, 640) | `ImportError` |
| T3.3 | `test_move_to_global_action_table` (parametrised over all 13 move types) | hand-built payloads with a fake `ActionContext` land in the expected block and offset: `play_card` by card id; `deploy` with `target_node_id: null` → the null slot; `assassinate` slot 1 at a node whose `troop_slots == ["p2", "p2", "white"]` → (node, owner=opp1); `return_spy` by (node, owner); `resolve_generic_choice` factored by `pending_op` and target kind (option / node / node×owner / card / player / index) | `ImportError` |
| T3.4 | `test_duplicate_equivalent_moves_merge` | two `play_card noble` with different `hand_index` → same id; two assassinate slots with the same owner → same id; different owners → different ids | `ImportError` |
| T3.5 | `test_unmapped_move_raises` | unknown card id, unknown node id, unknown resolve_generic target kind → `UnmappedMoveError` with the payload in the message | `ImportError` |
| T3.6 | `test_every_legal_move_in_stored_replays_maps` (skips without artifacts; full census gated by `PYRANTS_NN_CENSUS=1`, default subset = 3 games) | replay each game through a `CEngineAdapter`; at every step map every move from `compute_c_action_map` (G8); no `UnmappedMoveError`; any two legal moves sharing an id are duplicate-equivalent (same collapsed key); the chosen move maps | `ImportError` |
| T3.7 | `test_observation_shape_dtype_range` | `int16`, shape `(OBS_SIZE,)`, all values in `[0, 32767)`, two calls identical, `OBS_LAYOUT` ranges tile `[0, OBS_SIZE)` exactly | `ImportError` |
| T3.8 | `test_observation_is_perspective_relative` | `encode(p1)`'s `my_hand` block equals `Counter(p1 hand)` and `encode(p2)`'s equals `Counter(p2 hand)`; seat presence mask `[1,1,0,0]` for 2 players, `[1,1,1,1]` for 4; in a 3-player game with p2 acting, opponent slot 1 holds p3 and slot 2 holds p1 | `ImportError` |
| T3.9 | `test_observation_invariant_under_determinize` (**leak test**) | for 20 `(state, seed)` pairs over 2p/4p mid-game states: `encode(adapter, pid, ctx) == encode(adapter.determinize(pid, seed), pid, ctx)` bitwise; control: at least one pair's determinized `CState.player_hand(opp)` differs from the original, otherwise the test is vacuous and fails | `ImportError` |
| T3.10 | `test_public_multisets_match_engine_and_final_decks` | at 50 sampled steps of a stored replay: `opp_bag == Counter(deck+hand+discard)` read from the engine, own `deck_remainder` count equals the view's `deck_size`, `market_remaining` count equals `market_deck_size`; at terminal, `bag + played + inner_circle == Counter(final_decks.json["per_seat"][seat])` for every seat | `ImportError` |
| T3.11 | `test_pending_block_encodes_source_card_and_op` | with the gauth session (option pending): source-card one-hot set, `awaiting_option` set; after choosing an option: the op one-hot set; with no pending choice: the block is all zero | `ImportError` |
| T3.12 | `test_value_targets` | 2 players: `v(a,b)[0] == -v(b,a)[0]`, `tanh((a-b)/40)`; 3-4 players: rotated vector, `clip((s - mean(others))/40, -1, 1)`, mask zeros absent seats | `ImportError` |
| T3.13 | `test_policy_target_and_legal_mask` | mass sums to 1, zero outside the mask, two legal ids mapping to one global id sum their visits and visit-weight their Q; `legal_mask` is True exactly on the mapped ids | `ImportError` |
| T3.14 | `test_sample_weight_monotone_in_sims` | `w(50) < w(100) < w(200) <= w(400)` | `ImportError` |

### 6.2 Implementation notes

- `public_multisets` is the **only** function allowed to read `CState.player_hand/deck/discard`
  of a non-acting seat or `CState.market_deck()`; it returns multisets only. The docstring
  carries the G9 argument.
- `encode_observation` reads: `json.loads(adapter.private_view_json(pid))`, one
  `engine_build_view` call for G10 scalars, `public_multisets`, and `pending_ctx`. Board
  controller/presence/total-control are derived from `troop_slots` and `spies` per node.
- Owner keys are seat-relative: `me, opp1, opp2, opp3, white`, in turn order from the acting
  seat.

### 6.3 Done when

T3.1-T3.14 pass with the default census subset; `PYRANTS_NN_CENSUS=1 pytest tests/nn/test_actions.py`
passes over all 134 stored games; `just test-all` is green.

---

## 7. Phase 4 — Layer 2b: dataset builder

`scripts/build_nn_dataset.py` (CLI) over pure parts in `scripts/_nn_dataset.py`, plus
`openspiel_pyrants/nn/dataset.py` for `write_shards` / `load_shard`. Tests in
`tests/test_build_nn_dataset.py`.

### 7.1 Contracts

```
validate_game_dir(game_dir, *, allow_legacy) -> GameCheck(ok, reasons, schema_version, run_id)
iter_samples(bundle, *, allow_legacy, keep_forced, leak_check_rng=None) -> Iterator[Sample]
write_shards(samples, out_dir, *, dataset_id, shard_size, sources) -> manifest dict
load_shard(path) -> dict with obs float32, legal_mask, policy, value, weight and meta
```

`iter_samples` owns a `CEngineAdapter` (built like `ReplayPlayer` builds its session, via the
bundle's paths and `engine_seed`) and applies moves with `find_matching_move(moves, payload)`,
extracted from `ReplayPlayer._apply_entry` (G17) so both use one matcher. At step `i`, before
applying: acting player = `replay_log[i].player_id`; `indexed = compute_c_action_map(adapter)`;
**alignment assert** (payloads == `decisions[i].legal_moves_payload`, or strings ==
`decisions[i].legal_moves` in legacy mode) raising `AlignmentError(game_dir, node, expected,
actual)`; pending context from the engine (G7); encode; map; visits; rotate scores. After the
last step: adapter must be terminal and `final_scores()` must equal `replay.json`.

Shard `.npz` keys (D10, D11):

```
obs int16 [n, OBS_SIZE]      legal_row_ptr int64 [n+1]   legal_ids int32 [nnz]   legal_visits int32 [nnz]   legal_q float32 [nnz]
chosen_gid int32 [n]         root_value float32 [n]      total_visits int32 [n]  forced bool [n]
final_scores int16 [n, 4]    seat_mask bool [n, 4]       acting_seat int8 [n]    num_players int8 [n]
sims_requested int16 [n]     uct_c float32 [n]           game_idx int32 [n]      node int32 [n]   phase int8 [n]   move_type int8 [n]
```

Dataset `manifest.json`: `dataset_id`, `encoder_version`, `action_space_version`,
`card_index_sha`, `node_index_sha`, `obs_layout`, `action_layout`, `sources` (run dir,
`run_id`, `engine_git_sha`, games accepted/rejected with reasons), `counts` (games, samples,
forced), `shards` (file, rows), `phases`, `move_types`, `leak_check` (nodes, mismatches).

### 7.2 Tests

| ID | Test | Asserts | Fails before because |
|---|---|---|---|
| T4.1 | `test_validate_rejects_bad_dirs` | synthetic dirs: missing summary; `stopped_reason != "terminal"`; **run_id mismatch across replay/decisions/summary (the F-025 fixture)**; `len(decisions) != step_count`; setup sha mismatch; legacy schema without the flag — each yields `ok False` with the matching reason; a fresh v2 game from `run_one_game` is accepted | `ImportError` |
| T4.2 | `test_alignment_assert_fires` (C engine) | swap two entries of one line's `legal_moves_payload` in a fresh v2 game; `iter_samples` raises `AlignmentError` naming that node | `ImportError` |
| T4.3 | `test_tiny_end_to_end` (C engine, `num_sims=4`, `max_rounds=4`, 2p and 4p) | sample count equals the number of non-forced decisions (all decisions with `keep_forced`); per sample: obs shape/dtype, `legal_ids` within `[0, 2048)`, `chosen_gid ∈ legal_ids`, `sum(legal_visits) == total_visits`, `final_scores` rotated so `acting_seat` sits at index 0, `seat_mask` matches `num_players`, meta fields present | `ImportError` |
| T4.4 | `test_legacy_mode_reproduces_v2_targets` (C engine) | run a v2 game, copy the dir, strip `visit_counts/q_values/root_value/total_visits/legal_moves_payload/pending_context/schema_version`; build both; identical `legal_ids`/`legal_visits`/`obs` per sample; legacy without the flag is rejected | `ImportError` |
| T4.5 | `test_shards_round_trip` (pure, synthetic samples) | `np.load` keys/dtypes/shapes as listed; `legal_row_ptr[-1] == len(legal_ids)`; 5 samples with `shard_size 3` → 2 shards; manifest counts and per-shard rows agree; `load_shard` returns `policy` rows summing to 1, `value` from `value_targets`, `weight` from `sample_weight` | `ImportError` |
| T4.6 | `test_desync_is_reported_not_silent` (C engine) | tamper a replay payload: default mode skips the game and writes `rejected.jsonl` with the `ReplayDesyncError` step; `--strict` raises | `ImportError` |
| T4.7 | `test_builder_leak_check` (C engine) | `iter_samples(..., leak_check_rng=rng)` re-encodes 5 random nodes after `determinize` and reports `mismatches == 0` in the manifest | `ImportError` |
| T4.8 | `test_cli_smoke` (C engine, subprocess) | `python -m scripts.build_nn_dataset --runs <run dir> --out <tmp>/ds --shard-size 100` exits 0 and writes `manifest.json` + one shard | `No module named scripts.build_nn_dataset` |

### 7.3 Done when

T4.1-T4.8 pass; `just test-all` is green; `just build-nn-dataset` (new recipe wrapping the CLI) exists and is cited in
`nn-training-data.md`.

---

## 8. Phase 5 — Acceptance gate on the existing 120-game experiment (runbook)

Not tests; a recorded run whose numbers go into `nn-training-data.md` § Fitness audit.

1. `just verify-replays` → expect 134/134 OK.
2. `python -m scripts.build_nn_dataset --runs artifacts/ismcts/experiments/sims_vs_wins/* --allow-legacy-schema --leak-check 200 --out datasets/sims_vs_wins_v1`.
3. `python -m scripts.build_nn_dataset --report datasets/sims_vs_wins_v1` prints: games
   accepted/rejected with reasons (the four top-level mixed dirs must be rejected with
   `run_id mismatch`), alignment holds on every node, `leak_check.mismatches == 0`, value-target
   mean per seat ≈ 0, policy argmax == chosen on ≥ 95 % of nodes with `sims_requested ≥ 200`.
   The report math has its own pure test (`test_report_metrics`) on synthetic shards.
4. Record the numbers, close F-025 in `validation/findings.md`, and update
   `nn-training-data.md` § Concrete next steps to point here.

---

## 9. File map

| Change | Path |
|---|---|
| new | `scripts/_run_layout.py`, `scripts/_decision_telemetry.py`, `scripts/_nn_dataset.py`, `scripts/build_nn_dataset.py` |
| new | `openspiel_pyrants/nn/{__init__,index,public,observation,actions,targets,dataset}.py` |
| new | `tests/test_run_ismcts_layer0.py`, `tests/test_run_ismcts_decision_telemetry.py`, `tests/test_build_nn_dataset.py`, `tests/nn/{conftest,test_index,test_actions,test_observation,test_targets}.py` |
| edit | `scripts/run_ismcts.py` (D1, D2, D6, D7, D13, telemetry), `scripts/_replay_payload.py` (schema_version), `scripts/verify_replays.py` (INCOMPLETE status) |
| edit | `interface/replay_loader.py` (`is_complete_game`, bundle fields, docstring), `interface/replay_player.py` (`find_matching_move` extraction) |
| edit | `openspiel_pyrants/tests/test_ismcts_reproducibility.py`, `tests/test_run_ismcts_crash_capture.py` (run-dir resolution, G15) |
| edit | `justfile` (`ismcts` recipe, new `build-nn-dataset`), `docs/validation/findings.md` (F-025), `docs/nn-training-data.md` (status, numbers, links), `docs/README.md` (pointer) |

---

## 10. Risks and open points

- **`total_visits == sims − 1` assumes the stock bot.** T2.4 pins it; if OpenSpiel is upgraded
  and the root expansion changes, that assertion is the canary, not a bug in the runner.
- **Legal-set stability across determinizations.** T2.4's `set(visit_counts) == set(legal_action_ids)`
  holds only because the root's legal moves do not depend on hidden zones (G9). If a card ever
  makes legality depend on an opponent's hand, this assertion will say so.
- **`resolve_generic` target kinds.** The doc counts 708 distinct `(action_id, target-kind)`
  pairs. T3.6's full census is the only complete check; the default 3-game subset is a smoke
  test. Run the full census before Phase 5.
- **Shard size.** At `OBS_SIZE ≈ 4.8k` int16, 50k samples ≈ 480 MB per shard. Default
  `--shard-size 20000`.
- **Not decided here** (unchanged from the design doc): keeping `steps.jsonl` for training runs,
  card embeddings vs one-hots, a graph layer over the board.
