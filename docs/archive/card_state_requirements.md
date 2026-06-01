# Card State Requirements

## Scope

This document summarizes the runtime state required to execute the reviewed first-deck cards after demoting effect families to analysis-only data. The target runtime representation is now a generic per-card model stored directly on each card definition.

## Concrete Runtime State Required

### Board state

Already tracked in the engine:
- `board.nodes[*].troop_slots`
- `board.nodes[*].spies`
- `board.nodes[*].control_marker`
- `board.nodes[*].vp_tokens`
- board topology through `definition.board.nodes[*].adjacent_to`

Needed by reviewed cards but not fully modeled yet:
- richer troop targeting constraints for edge-case supplant and assassinate variants
- explicit board-level effects beyond deterministic first-legal targeting

### Player state

Already tracked in the engine:
- `players[*].hand`
- `players[*].deck`
- `players[*].discard_pile`
- `players[*].played_cards`
- `players[*].inner_circle`
- `players[*].trophy_hall`
- `players[*].barracks`
- `players[*].spies_available`
- `players[*].vp_tokens`
- `players[*].score`

Needed by reviewed cards but not fully modeled yet:
- richer cause tracking for discard, devour, and return effects
- clearer ownership and targeting for negative-card and other-player transfer effects

### Market and shared state

Already tracked in the engine:
- `market.row`
- `market.deck`
- `market.discard_pile`
- `resource_pool.power`
- `resource_pool.influence`
- card metadata through `definition.catalog`

Needed by reviewed cards but not fully modeled yet:
- richer target selection controls for player-driven branching choices
- scalable scoring inputs for effects that award VP from dynamic counts

## What Belongs on Cards Instead of GameState

These requirements should remain card metadata, not mutable game state:
- action sequences and modal choice structure
- source fragments from reviewed card semantics
- target filters and scope restrictions
- conditional gates such as focus checks and thresholds
- static read/write summaries
- timing metadata such as immediate versus end-of-turn resolution

This separation keeps the engine state focused on facts that change during play and keeps printed-card logic on the card definition itself.

## Assessment Of The Generic Card Model

### Clear

Yes. A per-card structured model is clearer than the family registry for this deck because the family abstraction is close to one family per card. The card itself is now the natural source of truth.

### Robust

Mostly. The model is robust for data validation because it captures:
- execution structure
- normalized action primitives
- global conditions
- state contracts

It is now partially robust for gameplay because a generic interpreter exists for core action primitives and supports explicit player-driven option and target selection. Several advanced mechanics still need runtime support.

### Efficient

Yes for this project. The data size is small, and direct card metadata is easier to inspect and debug than indirect family lookup. Validation cost is negligible compared with the clarity gained.

## Current Weak Spots

- Some card families still map to coarse action primitives like `custom_effect` and `conditional_bonus` that are not executable yet.
- Some advanced action variants still need richer selection payloads and validation rules (for example custom conditional branches and complex scaling effects).

## Recommendation

Keep `effect_families.json` as an analysis artifact only. Treat `data/cards/catalog.json` plus the richer `CardDefinition` model as the runtime-facing representation going forward.
