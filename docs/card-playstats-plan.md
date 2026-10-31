# Card Play Post-Mortem Notebook — Plan

Scope: a script that scaffolds an interactive Jupyter notebook analyzing per-card play
behavior (recruited / appeared in hand / played / modal choices) across one or more
IS-MCTS simulation folders under `artifacts/`, plus collection-level run metadata. Status:
**implemented**. Written for handoff — the implementing agent should not need to
re-derive the schemas below from scratch, but should verify them against current `HEAD`
before building (index/plan may drift). See "Implementation notes / deviations" at the
end for what differed from this plan.

---

## 0. Grounding facts (verified against a live artifact at plan time)

Artifact layout: `artifacts/ismcts/<bucket>/<run_id>/` (bucket examples seen:
`quick`, `runs`, `experiments/uct_sweep`) contains a run-level `manifest.json` and
`metrics.json`, and one `game_NNNN/` subfolder per game with:

- `replay.json` — always present. Top-level `replay_log`: an ordered list of step dicts
  with `move_type`, `player_id`, `round_number`, `phase`, `payload`. Relevant
  `move_type` values: `play_card` (`payload.card_id`, `payload.hand_index`), `recruit`
  (`payload.card_id`), `resolve_generic` (`payload.move_type == "resolve_generic_choice"`,
  `payload.action_id`, `payload.target_id`, `payload.selection_index`).
- `summary.json` — usually present (missing/non-terminal = incomplete game). Per-game
  aggregates: `winner`, `outcome`, `final_scores_per_player`, `decision_count`,
  `wall_time_sec`, `move_type_counts`, `final_deck_metrics` (shannon entropy, simpson,
  per seat, full vs. recruited-only), `player_ids`.
- `final_decks.json` — `per_seat`: final bag of card_ids per seat. Useful as a
  cross-check, not the primary recruited-count source (event log is time-ordered and
  instance-level; this is a terminal snapshot).
- `decisions.jsonl` — **optional**, not present in all runs (absent in older `quick`/`runs`
  folders, present in newer `experiments/*` folders). One JSON line per decision,
  index-aligned with `replay_log`. When present, `resolve_generic` lines carry
  `pending_context.source_card_id`, `pending_context.awaiting_option` (true exactly on the
  line that *is* the modal pick), and `generic.move_action_id` (the option id chosen).

`manifest.json` — run-level: `config` (sims, `uct_c`, `evaluator`, `seed`, `workers`,
`num_games`, ...), `engine_git_sha`/`engine_git_dirty`, and `games[]` with
`setup_data_json` (market deck composition per game — needed to know which cards were
even eligible to be recruited in a given game).

Reuse, don't reimplement, folder/game discovery and replay stepping:

- `interface/replay_loader.py` — `discover_replays(root)` walks a root for `replay.json`
  files; `load_replay(game_dir)` returns a fully-resolved `ReplayBundle`
  (replay + summary + decisions + manifest + resolved catalog/board/setup paths);
  `is_complete_game(game_dir)` is the shared completeness predicate.
- `interface/replay_player.py` — `ReplayPlayer(bundle)` re-simulates a game through the
  real C engine, `step_forward()`/`seek(i)`, exposes `.session` (a `CSession`). Already
  used by `scripts/verify_replays.py` at ~80ms/game for a full game.
- `engine_c/bindings/ce_api.py::CState.player_hand(seat_index)` — direct field read
  (no view construction) returning the list of card_id strings currently in that seat's
  hand. This is the hook hand-tracking depends on.

Card catalog: `data/cards/<card_id>.json`, 125 files (excl. `manifest.json`,
`cards_OCR.json`). Modal cards carry `execution_model.kind == "modal_choice"` with
`execution_model.options[].option_id` (verified: 35 of 125 cards are modal; most use
`option_1`/`option_2`, a few use named ids, e.g. `advocate` uses `gain_influence` /
`promote_end_of_turn`).

---

## 1. New dependencies

None of these are in `pyproject.toml` today. Add as an optional group so the core
engine/RL install stays lean:

```toml
[project.optional-dependencies]
analysis = ["pandas>=2.2", "plotly>=5.24", "ipywidgets>=8.1", "jupyter>=1.0", "nbformat>=5.10"]
```

Caching uses `pandas.DataFrame.to_pickle` — no `pyarrow`/Parquet dependency needed.

---

## 2. Per-card metrics — definitions and source

| Metric | Definition | Source |
|---|---|---|
| Recruited | count of `recruit` events, grouped by `payload.card_id` | `replay_log`, cheap |
| Played | count of `play_card` events, grouped by `payload.card_id` | `replay_log`, cheap |
| Appeared in hand | count of distinct card-copy *draws* — a card_id newly present in a seat's hand relative to the previous sampled snapshot | engine replay, expensive (§3) |
| Modal choice | for each modal card, the distribution of which `option_id` was picked each time it was played | `decisions.jsonl` when present, else heuristic (§4) |

"Recruited but rarely/never played" and "recruited but never even drawn" both fall out
of this table directly (join recruited/played/hand-appeared per card_id) — no separate
metric needed.

## 3. Hand-tracking (the expensive, load-bearing part)

Confirmed in scope for v1 — this is the metric the whole analysis exists to answer
("does the computer recruit cards and then not use them"), so it is not optional.

For each game: drive `ReplayPlayer` step by step. After every applied step, for every
seat, read `state.player_hand(seat_index)` and multiset-diff (`collections.Counter`)
against that seat's previous snapshot. Any card_id whose count went up contributes that
many "hand appearances" for that card_id. This gives an authoritative per-copy draw
count, at the same granularity as recruited/played, without needing an explicit "draw"
event (none exists in the log).

This is the one part of the pipeline meaningfully more expensive than log parsing
(engine replay is ~80ms/game baseline per `verify_replays.py`; the hand-sampling adds a
cheap direct-field read per seat per step on top, not a second engine call). Mitigate
with the per-game-directory cache in §5 — the cost is paid once, not on every notebook
open or every folder recombination.

## 4. Modal choice resolution

Preferred path (`decisions.jsonl` present): the line where
`pending_context.awaiting_option == True` is the modal pick; `pending_context.source_card_id`
identifies the card, `generic.move_action_id` (or the line's own `chosen_move`/`action_id`
equivalent) is the option id chosen.

Fallback path (`decisions.jsonl` absent — true for older `quick`/`runs` folders): for each
modal card's `play_card` event, find the next `resolve_generic` event from the *same
player* whose `payload.action_id` is one of that card's declared `option_id`s (from the
catalog lookup in §0), before that player's next `play_card`/`recruit`. Not all
`resolve_generic` steps are modal picks — some (e.g. `action_id` values that aren't a
declared option id, like site ids or a repeated card_id for a forced sub-choice) are
downstream mandatory resolution steps, not the modal decision itself, and must be
excluded by the "action_id is a declared option_id" filter.

Per-game sanity check: count of modal cards played should equal count of modal choices
resolved. Log mismatches as a warning row in the output rather than silently dropping
data.

## 5. Module layout

```
scripts/card_playstats/
  discovery.py   find_run_folders(root) -> folders containing manifest.json + game_* dirs
                 (built on interface.replay_loader.discover_replays / is_complete_game)
  catalog.py     load data/cards/*.json once; card_id -> {is_modal, option_id -> label}
  extract.py     per-game extraction (cheap log pass + expensive engine-replay pass),
                 disk-cached per game_dir keyed on (game_dir path, replay.json mtime)
  metadata.py    per-run collection metadata (config, completion, win rate by seat,
                 matchup coverage, score/length distributions, move-type mix,
                 deck-diversity rollups) — kept per-run, not blended, when multiple
                 folders are selected with differing configs
scripts/build_card_playstats_notebook.py
                 one-time nbformat scaffold of card_playstats.ipynb (imports + picker
                 widget wiring + chart cells); does not bake in a fixed folder
```

`extract.py`'s cache means analyzing an overlapping multi-folder selection only pays
engine-replay cost for the *new* games, not the previously-seen ones.

## 6. The notebook

1. Imports + `discovery.find_run_folders(ARTIFACTS_ROOT)`.
2. `ipywidgets` multi-select (checkboxes) of discovered run folders, a free-text box for
   a path outside the default root, and an "Analyze" button. The handler calls
   `extract`/`metadata` for the selected folder(s) (cache-backed) and re-renders
   everything below into an `Output` widget — so folder choice happens at notebook-open
   time, not at generation time.
3. Collection overview: per-run config table (surfaced separately per run, not merged),
   completion rate, win rate by seat, deck matchup counts, game length/score
   distributions — Plotly.
4. Per-card table: recruited / appeared-in-hand / played counts, play-rate-given-
   recruited, sorted "recruited but rarely/never played" list.
5. Modal cards: one grouped/stacked bar per modal card, option-choice frequency.

## 7. Sanity checks (build these in, don't bolt on later)

- Per game: sum of per-card `recruit` counts == `summary.json.move_type_counts.recruit`
  (same check for `play_card`). Mismatch = parsing bug, fail loud.
- Per game: modal cards played count == modal choices resolved count (§4). Mismatch =
  surfaced warning row, not a silent drop.

## 8. Acceptance criteria

- Given a folder path (or several), the notebook lists discoverable run folders, lets the
  user pick a subset, and renders all sections in §6 for the union of games in the
  selection.
- Re-selecting an overlapping set of folders does not re-run the engine replay for games
  already cached.
- Per-card table numbers pass both sanity checks in §7 on at least one real multi-game
  folder (recommend `artifacts/ismcts/runs/20260911T193759Z_58e54c44a5f5`, 31 games, no
  `decisions.jsonl` — exercises the fallback modal-resolution path — plus one folder
  under `artifacts/ismcts/experiments/uct_sweep` that does have `decisions.jsonl`, to
  exercise both modal-resolution paths).
- Modal breakdown covers every modal card that actually appears in the selected games'
  market decks (not a hardcoded list — read at run time, since the catalog can change).
  Note: the catalog has **36** such cards, not 35 — `mummy_lord` is `repeat_choice`, which
  the engine treats as modal (`engine_c/generic_runtime.c`), so it is included.

## 9. Explicit non-goals for v1

- No cross-run statistical comparison UI (e.g. A/B strength testing between configs) —
  that's a different tool.
- No live/streaming analysis of an in-progress run — folders are read as static,
  completed (or partially-completed) artifacts.

## 10. Implementation notes / deviations

- **Every current artifact has `decisions.jsonl`.** The recommended
  `runs/20260911T193759Z_58e54c44a5f5` and *all* `quick/` and `uct_sweep/` runs carry
  decision telemetry, so the §4 fallback path is exercised by synthetic unit tests and
  cross-validated against the decisions path on real logs (31/32 games agree; the
  disagreement is a modal card invoked by another card's effect, so no top-level
  `play_card` event exists for it).
- **Sweep runs use `experiment_config.json`, not `manifest.json`.**
  `experiments/uct_sweep/<run>/` has no manifest; discovery accepts either marker.
- **Cache is JSON, not a pickled DataFrame.** Keyed on game-dir path + `replay.json`
  mtime + format version, so extraction stays pandas-free (the `analysis` extra is only
  needed for `report.py`/the notebook).
- **`report.py` added** beyond the §5 layout for pandas aggregation, keeping the
  notebook thin. Market composition is captured per game from `setup_json`
  (`extract.market_card_ids_from_setup`), so modal-market coverage also works for
  manifest-less sweep runs.
- **`repeat_choice` is modal.** The catalog has 35 `modal_choice` cards plus one
  `repeat_choice` card (`mummy_lord`); `catalog.load` treats both as modal, matching the
  engine, so modal coverage is 36 when `mummy_lord` is in a selected market.
- **`pyproject.toml`**: added the `analysis` extra per §1, plus `nbformat`, `openpyxl` and
  `ruff` to the dev group because existing tests/tooling already require them.
