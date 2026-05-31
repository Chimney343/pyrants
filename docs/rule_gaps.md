# Rule Gaps Register

Date: 2026-04-27
Status: Open

This register tracks rule ambiguities and missing details that block complete implementation.
Each item includes a required clarification question.

## Action Rules

1. Assassinate resolution is unspecified [gap]
- Source: [docs/tyrants_of_the_underdark_logic.md](docs/tyrants_of_the_underdReark_logic.md#L38)
- Needed: What is the exact cost, legal targets, range or presence constraints, and post-effect state changes?

2. Deploy resolution is only partially specified [gap]
- Source: [docs/tyrants_of_the_underdark_logic.md](docs/tyrants_of_the_underdark_logic.md#L32), [docs/tyrants_of_the_underdark_logic.md](docs/tyrants_of_the_underdark_logic.md#L38)
- Known: barracks-empty fallback gives 1 VP [from rules: §3]
- Needed: Full deploy legality, placement limits, adjacency or presence requirements, and interaction with occupied spaces.

3. Recruit action is unspecified [gap]
- Source: [docs/tyrants_of_the_underdark_logic.md](docs/tyrants_of_the_underdark_logic.md#L38)
- Needed: Influence cost timing, market row refill timing, where recruited cards go, and any faction or aspect constraints.

4. Return Spy action is unspecified [gap]
- Source: [docs/tyrants_of_the_underdark_logic.md](docs/tyrants_of_the_underdark_logic.md#L38)
- Needed: Eligibility conditions, source and destination locations, rewards, and whether this consumes action economy.

5. Supplant mechanic [resolved 2026-04-30]
- Source: user card review clarifications for Green Dragon [from rules: user clarification 2026-04-30]
- Resolution: Supplant removes another player's troop, moves it to your trophy hall, and places your own troop into that exact slot. If no site is named, supplant is legal anywhere you have presence. Card text may further restrict the site, such as `there` on Green Dragon.

## Card Ability Semantics

5. Focus timing and eligibility window [resolved 2026-04-28]
- Source: [docs/tyrants_of_the_underdark_logic.md](docs/tyrants_of_the_underdark_logic.md#L23)
- Resolution: The played card cannot satisfy Focus by itself. A different card in hand or in played cards must provide the matching aspect.

6. Paid ability resolution order and optionality [resolved 2026-04-28]
- Source: [docs/tyrants_of_the_underdark_logic.md](docs/tyrants_of_the_underdark_logic.md#L24)
- Resolution: Choosing not to pay leaves the card played with no paid-ability effect. Payment is legal only if the player can pay the full cost and fulfill every required paid action. Paid abilities must be resolved or declined before another card is played.

7. Promote timing and edge cases [resolved 2026-04-28]
- Source: [docs/tyrants_of_the_underdark_logic.md](docs/tyrants_of_the_underdark_logic.md#L25), [docs/tyrants_of_the_underdark_logic.md](docs/tyrants_of_the_underdark_logic.md#L41)
- Resolution: Promote follows the card instruction. It may be immediate or end-of-turn, optional or mandatory. Once promoted, a card is out of play, cannot be referenced by later effects, and cannot satisfy Focus.

## Turn, Endgame, and Scoring

8. Tie-break policy is missing [gap]
- Source: no tie policy in current rules document
- Needed: How to break ties at game end.

9. No-legal-move behavior is missing [gap]
- Source: no explicit handling in current rules document
- Needed: Does player pass, skip phase, or incur penalty when no legal moves exist in main phase?

10. Site control source-of-truth is ambiguous between markers and recomputed majority [gap]
- Source: [docs/tyrants_of_the_underdark_logic.md](docs/tyrants_of_the_underdark_logic.md#L8), [docs/tyrants_of_the_underdark_logic.md](docs/tyrants_of_the_underdark_logic.md#L42), [docs/tyrants_of_the_underdark_logic.md](docs/tyrants_of_the_underdark_logic.md#L48)
- Needed: Should control marker always be authoritative, or may control be recomputed from troop state during scoring?

11. Endgame trigger interpretation needs clarification [gap]
- Source: [docs/tyrants_of_the_underdark_logic.md](docs/tyrants_of_the_underdark_logic.md#L47)
- Needed: Does market-deck empty trigger immediate game end, or after current turn or round completion?

## Information and Ordering

12. Simultaneous and replacement-effect ordering not defined [gap]
- Source: not defined in current rules document
- Needed: Priority and ordering policy for simultaneous outcomes.

13. Visibility rules are not defined [gap]
- Source: not defined in current rules document
- Needed: Public vs hidden zones for hands, deck order knowledge, and market visibility assumptions.

## Data Completeness Gaps

14. Canonical board topology is incomplete [gap]
- Source: current board file is minimal scaffold only
- Needed: Full production board node set, adjacency graph, capacities, VP values, and initial token placement.

15. Canonical card catalog and decklists are incomplete [gap]
- Source: current catalog and setup are placeholder bootstrap data
- Needed: Complete card metadata, effect keys, starter compositions, market deck composition, and balancing counts.

## Current Engine Handling

- Unsupported actions and unresolved card effects are intentionally blocked via typed exceptions [inferred].
- This protects correctness until source rules are clarified [inferred].
