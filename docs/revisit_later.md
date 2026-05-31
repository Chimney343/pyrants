# Revisit Later Checklist

Date: 2026-04-27
Purpose: Park pending decisions and implementation tasks so we can resume quickly.

## User Inputs Pending

- [ ] Provide full board topology JSON (all sites, routes, capacities, VP values, adjacency).
- [ ] Provide board layout coordinates for graphical rendering (node x,y and optional edge waypoints).
- [ ] Provide full card catalog data (metadata, effect keys, payload fields).
- [ ] Provide deck variant setup files (starter + market composition per variant).
- [ ] Clarify blocked rules: Assassinate, Deploy, Recruit, Return Spy.
- [ ] Clarify timing rules: Focus, paid abilities, promote triggers/optionality.
- [ ] Clarify tie-break and no-legal-move behavior.
- [ ] Clarify endgame timing on market deck depletion.

## Assistant Backlog

- [ ] Fix cleanup reshuffle to be truly shuffled while remaining deterministic under seed.
- [ ] Unify site-control source-of-truth across end-of-turn and final scoring.
- [ ] Add tests for reshuffle behavior and scoring consistency.
- [ ] Add deck profile registry for easier deck variant selection.
- [ ] Add tests that run against at least two different setup variants.
- [ ] Add graphical board renderer using layout coordinates.
- [ ] Add layout editor to place/move site and route nodes and persist layout JSON.
- [ ] Wire graphical interactions to engine moves without moving rules into interface.

## Confirmed Current Capability

- Different decks are supported by selecting a different setup file at launch.
- Current limitation: one setup profile per game run (no in-session deck switching UI yet).

References:
- [docs/next_steps.md](docs/next_steps.md)
- [docs/rule_gaps.md](docs/rule_gaps.md)
- [docs/phase6_final_review.md](docs/phase6_final_review.md)
