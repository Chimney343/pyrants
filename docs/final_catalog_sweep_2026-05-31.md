# Final Catalog Sweep - 2026-05-31

## Scope

This sweep verifies two things for `data/cards/catalog.json`:

1. `rules_text` consistency against each card's runtime `execution_model`/`actions`.
2. Runtime executability of each card through the current engine.

## Inputs Used

- `data/cards/catalog.json`
- `scripts/catalog_audit.py`
- `scripts/generate_catalog_execution_audit.py`
- `scripts/check_roster_card_stuck_states.py`
- `artifacts/card_stuck_report.json`

## User-Directed Implementation Applied

Applied your requested mismatch direction:

- Noble -> gain influence
- Soldier -> gain power

Source-of-truth updates were made in `docs/first_deck_review.md`, then catalog artifacts were regenerated.

## Verification Run

Commands run:

```powershell
.venv/Scripts/python.exe scripts/generate_first_deck_artifacts.py
.venv/Scripts/python.exe scripts/generate_catalog_execution_audit.py
.venv/Scripts/python.exe -m pytest tests/test_card_model.py -q
.venv/Scripts/python.exe scripts/check_roster_card_stuck_states.py --rosters-path data/decks/first_deck_rosters.json --board-path data/boards/base_game.json --card-path data/cards/catalog.json --setup-path data/decks/base_setup.json --seed 7 --seed-count 1 --max-steps 120 --json-out artifacts/card_stuck_report.json --ci --expected-blocked-cards=
```

## Post-Change Results

From `docs/catalog_execution_audit.md` and `artifacts/card_stuck_report.json`:

- Total cards audited: 125
- Clean cards: 125
- Rules-text mismatches: 0
- Runtime gaps: 0
- Heuristic-only findings: 0
- Probe blocked/stuck/error/max_steps: 0

## Runtime Executability Status

No cards are currently non-executable in the engine.

- blocked: 0
- stuck: 0
- error: 0
- max_steps: 0

## Remaining Inconsistencies

No remaining inconsistencies.

| card_id | current finding summary | remediation track |
|---|---|---|
| none | none | none |

## One-by-One Remediation Plan (Per Your Input)

You asked to go through these one by one and fix as we go. The plan below is staged for iterative approval.

Progress update for point 1 (quantity-driven set):

- Completed: balor, cranium_rats, grimlock, kobold, weaponmaster (normalized fixed deploy quantities in generator overrides).
- Completed: aboleth audit fix for dynamic draw count (`count_from=spies_on_board` + for-each wording) in `scripts/catalog_audit.py`.
- Remaining in this track: none.

Progress update for point 2 (conditional-gain set):

- Completed via audit fix in `scripts/catalog_audit.py`: conditional_bonus amounts now count toward resource expectations for matching resources.
- Cleared cards: banshee, black_earth_cultist, dragonclaw, drow_negotiator, eternal_flame_cultist, green_wyrmling, howling_hatred_cultist, infiltrator.
- Additional card cleared by same fix: imix.
- Remaining in this track: none.

Progress update for point 3 (scaled/custom-effect set):

- Completed via audit fix in `scripts/catalog_audit.py`: scaled `custom_effect` resource gains are recognized for `scaled_resource_from_player_zone` when wording is for-each/for-every.
- Cleared card: beholder.
- Remaining in this track: none.

### Step Loop (repeat per card)

1. Inspect card `rules_text`, `execution_model`, and flattened `actions`.
2. Classify root cause as one of:
   - dynamic quantity actually intended
   - conditional/custom effect represented outside fixed gain/deploy counts
   - true model mismatch
3. Apply smallest fix:
   - if intended dynamic behavior: keep model, improve audit heuristic/rules for that pattern
   - if true mismatch: fix source-of-truth card definition and regenerate
4. Re-run targeted validation:
   - regenerate catalog + execution audit
   - run `tests/test_card_model.py`
   - run probe for changed card (or full probe if needed)
5. Record decision and result in this document.

### Proposed Processing Order

1. No remaining cards in remediation queue.

## Legacy Report Status

The following files are retained for history but marked deprecated:

- `artifacts/catalog_rules_model_consistency_report.md`
- `artifacts/catalog_rules_model_consistency_report.json`

Canonical current sources:

- `docs/catalog_execution_audit.md`
- `docs/final_catalog_sweep_2026-05-31.md`
