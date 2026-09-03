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

## Keeping This Folder Honest

`README.md`, `AGENTS.md`, this file, `engine-status.md`, `board-creator-status.md`, `openspiel-architecture.md`, `openspiel-integration.md`, `repo-structure.md`, and everything in `adr/` are the "living" tier — they're expected to stay accurate, unlike the dated snapshots in `archive/` and `validation/`. Run `just docs-check` to mechanically check every `docs/**/*.md` citation (file paths, `path:line` ranges, `just <task>` references, and this file's own subfolder index) against the actual tree; it fails on broken living-tier citations and reports everything else as informational. It cannot check that a citation's *content* still matches its claim — only that the path/line still exists — so a human pass is still needed for that.