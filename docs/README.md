# Docs Index

This folder is split by purpose.

## Start Here

Use these files for current project status:
- `engine-status.md`
- `board-creator-status.md`

## Subfolders

- `adr/` - architecture decision records (numbered, dated, with Status/Consequences/Compliance sections).
- `archive/` - older plans, reviews, and dated notes kept for history.
- `source/` - live documentation inputs (script inputs and pending-sweep inventories).
- `generated/` - generated reports that are produced from code and source artifacts.
- `validation/` - the OpenSpiel/IS-MCTS empirical validation ledger: dated findings, fix plans, adversarial reviews, and the harness scripts/baselines that produced their numbers.

## How To Read This Folder

- If you want the current state of development, read the two top-level status files.
- If you want to know why an architectural decision was made, read `adr/`.
- If you need detailed card review input, use `source/`.
- If you need generated audits or coverage reports, use `generated/`.
- If you need old planning context, use `archive/`.
- If you want the IS-MCTS/OpenSpiel correctness and performance record, use `validation/` (start with `validation/verdict.md`).
- If you want to know how IS-MCTS games should be saved so a neural network can train on them, read `nn-training-data.md` (short grug-voice version: `nn-training-data-grug.md`).
- If you are implementing that layout, follow `nn-training-data-tdd-plan.md` (tests first, phase by phase).
- If you are fixing what the first verification of that layout found, follow `nn-training-data-fix-plan.md` (each finding reviewed against `tyrants-rulebook.md`).
- If you are fixing what the review of *that* plan's implementation found, follow `nn-training-data-fix-plan-02.md` (seat perspective, trophy-hall action merge, census coverage).
- If you want to know whether Fix Plan 02 actually landed as written, read `nn-training-data-fix-plan-02-review.md` (short grug-voice version: `nn-training-data-fix-plan-02-review-grug.md`).

## Keeping This Folder Honest

`README.md`, `AGENTS.md`, this file, `engine-status.md`, `board-creator-status.md`, `openspiel-architecture.md`, `openspiel-integration.md`, `repo-structure.md`, and everything in `adr/` are the "living" tier — they're expected to stay accurate, unlike the dated snapshots in `archive/` and `validation/`. Run `just docs-check` to mechanically check every `docs/**/*.md` citation (file paths, `path:line` ranges, `just <task>` references, and this file's own subfolder index) against the actual tree; it fails on broken living-tier citations and reports everything else as informational. It cannot check that a citation's *content* still matches its claim — only that the path/line still exists — so a human pass is still needed for that.