# Card Complexity Review Framework + Script + Justfile Command

## Goal

Evaluate complexity of the 125 cards in `data/cards/` using their structured `execution_model` / `actions` / `global_conditions` / `state_contract` data plus `rules_text`, produce a ranked complexity review, and expose it as a justfile command.

**Purpose (decided):** composite score, QA-leaning — weighted toward engine/runtime complexity, with rules-text complexity secondary. Per-dimension sub-scores are reported so the ranking also serves design review and test prioritization.

## Context (verified)

- Card files: `data/cards/*.json` (125 cards). `manifest.json` and `cards_OCR.json` are not cards.
- Canonical loading: `game_setup.loaders.load_card_catalog(Path)` validates via Pydantic (`game_setup/types.py`) and auto-excludes non-card files. Use this — no manual JSON walking.
- `ExecutionModel` kinds: `sequence`, `modal_choice`, `repeat_choice` (discriminated union).
- `CardAction` fields: `op`, `target_scope`, `timing`, `optional`, `quantity{kind, value}`, `filters[]`, `source_fragment`, `metadata{}`.
- Observed `quantity.kind` values: `fixed`, `unspecified`, `variable_repeat`.
- Ops seen in `engine_c/generic_runtime.c`: `gain_resource`, `draw_cards`, `deploy_troops`, `place_spy`, `return_spy`, `assassinate_troop`, `supplant_troop`, `move_troop`, `return_unit`, `promote_card`, `recruit_card`, `play_card`, `devour`/`devour_cost`, `force_discard`, `custom_effect`, `grant_vp`.
- `global_conditions.condition_type` values seen: `focus_check`, `conditional_gate`, `timing_trigger`.
- Dynamic text tokens (reuse list from `scripts/catalog_audit.py::_DYNAMIC_TEXT_TOKENS`): "for each", "for every", "if you have", "if another", "if there", "up to", "choose exactly one mode", "choose one", "either".
- Script conventions: snake_case modules run via `python -m scripts.<name>` (e.g. `scripts.build_review_workbook`); artifacts go under `artifacts/`; stdlib + existing deps only (no new dependencies — markdown/CSV/JSON via stdlib).
- Expected reference points for validation: `soldier` = trivial (1 `gain_resource` action, fixed qty); `aboleth` = high (modal + unspecified quantity + conditional_gate); `demogorgon` = high (4 actions incl. `devour_cost` + `custom_effect`); `mummy_lord` = the only `repeat_choice`.

## Complexity Framework: Card Complexity Score (CCS)

Five dimensions. Each yields raw points; weighted sum is scaled to 0–100 against a documented reference maximum, then banded into tiers: 0–19 Low, 20–39 Moderate, 40–59 High, 60–79 Very High, 80+ Extreme.

### D1. Execution structure — weight 0.25
- `execution_model.kind`: `sequence` = 0, `modal_choice` = 2, `repeat_choice` = 3 (no model / empty model = 0, flagged).
- +1 per option beyond the first (modal/repeat models).
- +0.5 per flattened action beyond the first (use the `actions` field — it is the flattened form).

### D2. Operational difficulty — weight 0.25
Op tiers (per action, points = tier):
- Tier 0: `gain_resource`, `draw_cards`, `grant_vp`
- Tier 1: `deploy_troops`, `place_spy`, `return_spy`, `return_unit`, `force_discard`
- Tier 2: `assassinate_troop`, `supplant_troop`, `move_troop`, `recruit_card`, `play_card`
- Tier 3: `promote_card`, `devour`, `devour_cost`, `custom_effect`

Additions:
- +1 per action with `optional: true` (player decision point).
- +1 per action with a targeting scope (any `target_scope` other than `self`).
- +1 per filter entry.
- Unknown ops default to Tier 2 and are listed in the report's "unmapped tokens" section (surfaces catalog drift).

### D3. Dynamism — weight 0.20
- `quantity.kind` per action: `fixed` = 0, `unspecified` = 1.5, `variable_repeat` = 2, unknown = 2 + flagged.
- +1 per action with non-`immediate` timing (e.g. `end_of_turn` deferred/triggered effects).
- +1 per action whose `metadata` contains dynamic keys: `count_from`, `requires_focus`, `targeting` == "anywhere", `ignore_presence_requirement` truthy.

### D4. Conditionality — weight 0.15
- `global_conditions`: `focus_check` = 1.0, `conditional_gate` = 1.5, `timing_trigger` = 1.5, unknown = 1.5 + flagged.

### D5. Textual & state footprint — weight 0.15
- `rules_text`: +1 per sentence beyond the first; +0.5 per dynamic-token occurrence (token list above; case-insensitive), capped at +5 for tokens.
- `state_contract`: +0.25 per read, +0.5 per write.

## Deliverables

### 1. `scripts/card_complexity_review.py` (new)

- Module docstring (matches repo style).
- **Pure, importable scoring API** (for tests): `score_card(card: CardDefinition) -> CardComplexityResult` dataclass holding: total (0–100), tier label, per-dimension sub-scores (D1–D5 raw + weighted), and a `factors: list[str]` breakdown of the concrete contributions, plus `unmapped: list[str]` for unknown ops/condition types/quantity kinds.
- Weights and tier tables as module-level constants (`OP_TIERS`, `DIMENSION_WEIGHTS`, `QUANTITY_POINTS`, `CONDITION_POINTS`, `DYNAMIC_TEXT_TOKENS` — copy the token tuple from `catalog_audit.py`).
- CLI via `argparse`:
  - `--card-path` (default `data/cards`), `--output-dir` (default `artifacts/card_complexity`), `--top N` (console shows top N, default 20), `--card CARD_ID` (score a single card in detail), `--no-artifacts` (console only).
- Flow: `load_card_catalog` → score each card → rank (score desc, then card_id asc for stable ties) → print console table → write artifacts.
- Console table columns: rank, card_id, name, aspect, cost, score, tier, top 2 contributing factors. Plus tier distribution summary and unmapped-token warnings.
- Artifacts (created unless `--no-artifacts`):
  - `artifacts/card_complexity/complexity_review.md` — methodology section (weights, tier tables), full ranked table with sub-scores and factor breakdowns, tier distribution, unmapped tokens.
  - `artifacts/card_complexity/complexity_review.csv` — rank, card_id, name, aspect, cost, score, tier, D1–D5 sub-scores.
  - `artifacts/card_complexity/complexity_review.json` — full structured results.
- Exit code 0 on success; non-zero if catalog load/validation fails.

### 2. `tests/test_card_complexity.py` (new)

- `score_card` unit tests using inline `CardDefinition` fixtures:
  - Single `gain_resource`/fixed-qty card scores in the Low band.
  - Adding `devour_cost` + `custom_effect` actions outscores gain-only card.
  - `modal_choice` outscores equivalent `sequence`; `repeat_choice` outscores `modal_choice`.
  - `variable_repeat`/`unspecified` quantities outscore `fixed`.
  - `end_of_turn` timing adds dynamism points.
  - Unknown op → Tier 2 fallback + appears in `unmapped`.
  - `factors` breakdown strings are non-empty for a non-trivial card.
- Integration test: run `score_card` over the real catalog via `load_card_catalog` — asserts 125 cards scored, `soldier` in Low tier, `aboleth` and `demogorgon` score strictly higher than `soldier`, all scores within 0–100, ranking is deterministic (sorted by (-score, card_id)).
- Report-writing test: invoke the script's `main()` (or writer function) with `tmp_path` output dir; assert the three artifact files exist and CSV parses with expected headers.

### 3. `justfile` (edit)

Add under the existing "Analysis & Tooling" section (next to `review-workbook`):

```just
card-complexity *args:
    & {{python}} -m scripts.card_complexity_review {{args}}
```

Passthrough args allow `just card-complexity --top 40`, `just card-complexity --card aboleth`, etc. (just's `*args` splat; note PowerShell quoting of `--`-prefixed args works since the recipe passes them through verbatim).

## Implementation Notes

- No new dependencies; stdlib only (`argparse`, `csv`, `json`, `dataclasses`, `pathlib`).
- Ruff: line-length 120, py312, rules E,F,I,B,UP,SIM. No comments; docstrings only where they match repo style.
- Keep scoring pure (no I/O) so tests import it directly; file writing isolated in `main()`/writer functions.
- `mummy_lord` is the only `repeat_choice` card — good smoke target.

## Validation

1. `ruff check .`
2. `.venv/Scripts/python.exe -m pytest tests/test_card_complexity.py -q` (and full `just test`)
3. `just card-complexity` — console table renders, artifacts written; spot-check: `soldier` near bottom, `aboleth`/`demogorgon`/`mummy_lord` near top.
4. `just card-complexity --card aboleth` — single-card detail view.

## Out of Scope

- No engine/C changes; no catalog data changes; no OpenSpiel/UI changes.
- No complexity-vs-value (cost/VP) ratio analysis — the CSV includes cost/VP columns so this can be derived later.
- No xlsx workbook (existing `review-workbook` recipe covers that workflow).
