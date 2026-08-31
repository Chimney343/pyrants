# Spy Relocation When All Spies Are Already Placed

## Problem

Rulebook line 337-338 (Actions → Place a spy):

> To place a spy, put it on any site that doesn't already contain one of your spies…
> You don't need to have Presence at a site to place a spy there.
> **If you take this action while all your spies are already placed, you may either do
> nothing or first return one of your spies and then place it.**

The engine implements only the first half. `sel_place_spy`
([`selection.c:390-419`](engine_c/selection.c#L390-L419)) computes
`has_spies = spies_available > 0` (line 400) and, when false, walks the whole node
list writing **nothing** (the emit at line 411-416 is guarded by `has_spies`). The
action reports zero targets.

Consequences:

1. **A rules capability is missing entirely** — relocating a placed spy is a legal
   move in Tyrants and cannot be expressed in this engine today.
2. **It manufactures soft-locks.** Zero targets makes the enclosing modal option
   non-viable ([`generic_runtime.c:1155-1166`](engine_c/generic_runtime.c#L1155-L1166)),
   emitted as an `unavailable` placeholder
   ([`generic_runtime.c:1219`](engine_c/generic_runtime.c#L1219)) that `engine_apply`
   then refuses ([`generic_runtime.c:736-741`](engine_c/generic_runtime.c#L736-L741)).
   **Air Elemental** option_1 (`place_spy`) dead-ends this way — observed at
   `spies_available = 0` with 5 own spies on the board.

## The apply side is already done

`apply_place_spy` ([`actions.c:263-293`](engine_c/actions.c#L263-L293)) **already
implements relocation**:

```c
if (ps->spies_available > 0) {
    ps->spies_available--;
} else {
    Sym src_node = find_sel(sk, sv, sc, "source_node_id");
    if (src_node == SYM_NULL || src_node == target) return state;
    /* …remove this player's spy from src_node… */
}
```

It expects a `source_node_id` selection key that **nothing ever supplies**. So this
plan is not new mechanics — it is wiring up move generation to feed an apply path that
already exists. That keeps the change small and low-risk.

## Mechanism Design

### Move encoding — one composite move

A relocation is a (source site, destination site) pair. `MOVE_RESOLVE_GENERIC` has two
free Sym fields, and for `place_spy` only `action_id` is currently consumed
([`generic_runtime.c:819-820`](engine_c/generic_runtime.c#L819-L820) maps
`action_id → target_node_id`; `target_id` is unused). So encode:

| Field | Meaning |
|---|---|
| `action_id` | destination site (as today) |
| `target_id` | source site holding the spy to pick up (`SYM_NULL` when placing from supply) |

This keeps relocation a **single atomic move** — no new pending-selection step, no
partially-applied state, and it stays a one-index action for OpenSpiel.

### Move count

28 sites on the board, 5 spies per player
([`loader.c:456`](engine_c/loader.c#L456) `default_player_spies = 5`). Worst case
5 × 27 = **135** moves — within the 1024-move buffer
([`ce_api.py:401-402`](engine_c/bindings/ce_api.py#L401-L402)) and the
`NUM_DISTINCT_ACTIONS = 1024` ceiling. No buffer change needed, but this is the
largest single action-space contributor added by any of the three plans.

## Implementation Tasks

### 1. `engine_c/selection.c` — `sel_place_spy`

When `spies_available == 0`, emit one move per (source, destination) pair. Preserve
the existing constraints: destination must be a `site`
([line 406](engine_c/selection.c#L406)) that does not already contain one of this
player's spies ([lines 407-410](engine_c/selection.c#L407-L410)), and Presence is
**not** required (rulebook 337 — the current handler is already correct here).

```c
if (has_spies) {
    /* …existing single-move emit, target_id stays SYM_NULL… */
} else {
    /* Rulebook 338: all spies placed → may return one of your spies and
     * place it. Emit (source, destination) pairs; apply_place_spy already
     * consumes source_node_id. */
    for (int s = 0; s < state->node_count && w < max_out; s++) {
        if (state->nodes[s].node_id == nid) continue;      /* no self-move */
        if (!node_has_own_spy(state, player_id, s)) continue;
        out[w].type = MOVE_RESOLVE_GENERIC;
        out[w].data.resolve_generic.action_id = nid;                    /* destination */
        out[w].data.resolve_generic.target_id = state->nodes[s].node_id; /* source */
        out[w].player_index = 0;
        w++;
    }
}
```

Emit the **decline** once, before the per-destination node loop (not inside it), so it
appears exactly once regardless of how many sites qualify:

```c
if (!has_spies && w < max_out) {
    out[w].type = MOVE_RESOLVE_GENERIC;
    out[w].data.resolve_generic.action_id = SYM_NULL;   /* decline */
    out[w].data.resolve_generic.target_id = SYM_NULL;
    out[w].player_index = 0;
    w++;
}
```

Factor the "does this node hold one of my spies" scan (already inline at lines
407-410) into a small static helper and reuse it for both the destination exclusion
and the source scan.

### 2. `engine_c/generic_runtime.c` — selection-key mapping

At [line 819-820](engine_c/generic_runtime.c#L819-L820), the `place_spy` branch must
also forward `target_id`:

```c
if (strcmp(op, "deploy_troops") == 0 || strcmp(op, "place_spy") == 0) {
    if (aid != SYM_NULL) { sk[sc] = intern("target_node_id"); sv[sc] = aid; sc++; }
    if (strcmp(op, "place_spy") == 0 && tid != SYM_NULL) {
        sk[sc] = intern("source_node_id"); sv[sc] = tid; sc++;
    }
}
```

Guard the `sk[8]`/`sv[8]` bound (line 812-813) — two keys is well within it.

### 3. `engine_c/describe.c` — label

`place_spy` resolve moves are labelled around
[`describe.c:473`](engine_c/describe.c#L473). Add a relocation form so the GUI and
`move_to_str` distinguish the two cases:

- placing from supply: `Place a spy at {site}` (unchanged)
- relocating: `Move your spy from {source} to {destination}`

### 4. Tests

- **C** (`engine_c/tests/test_generic_actions.c`): `sel_place_spy` with
  `spies_available = 0` and spies at two sites emits pairs excluding self-moves and
  excluding destinations already holding this player's spy; with
  `spies_available > 0` the output is unchanged (regression guard).
- **Python** (new `tests/c_engine/test_spy_relocation.py`, via
  `card_test_helpers.make_card_test_session`):
  1. `spies_available = 0`, own spies at two sites → `place_spy` offers relocation
     moves; none is tagged `unavailable`.
  2. Applying one removes the spy from the source site and adds it to the
     destination; `spies_available` stays 0; total spy count on board is unchanged.
  3. Destination already holding this player's spy is never offered.
  4. `spies_available > 0` → placement from supply, `spies_available` decrements,
     board spy count increases (regression guard).
  5. **Air Elemental option_1** with `spies_available = 0` and spies on board is
     selectable end to end (this is the soft-lock regression test).
  6. `spies_available = 0` **and no own spies on board at all** → exactly one move
     (the decline) is offered; it applies cleanly and leaves state unchanged. No
     `unavailable` placeholder, no dead end.
  7. Decline is present in every `spies_available = 0` state, alongside relocations.

### 5. Validation

```
just build-c && just test-c && just test-c-python && just test && just openspiel-test
ruff check .
```

Then confirm the Air Elemental dead end is gone under IS-MCTS rollouts (it surfaced at
seed 1 / 4p and seed 21 / 4p).

## Risks

- **Action-space growth** (up to +135 moves in all-spies-placed states). Bounded and
  under the buffer, but it will slow IS-MCTS branching in late-game states where spies
  are exhausted. Measure with `just ismcts-perf` before and after.
- **`apply_place_spy` is reached from other cards too** (any card with a `place_spy`
  action). Feeding `source_node_id` changes behavior for **every** such card once
  spies run out — that is the intent, but the blast radius is the whole `place_spy`
  op, not just Air Elemental. Enumerate the affected cards with
  `grep -l '"place_spy"' data/cards/*.json` and spot-check each.
- **Self-move guard**: `apply_place_spy` already rejects `src_node == target`
  ([`actions.c:279`](engine_c/actions.c#L279)); the generator must not emit those
  either, or they would appear as legal-but-inert moves.

## Resolved Decision — offer an explicit decline

Rulebook 338 says you may *either* do nothing *or* relocate, so `sel_place_spy` emits
**both** when `spies_available == 0`:

- one **decline** move ("Do not place a spy"), and
- the (source, destination) relocation pairs.

This matters for more than fidelity: the decline is what covers the residual edge case
where the player has **no** spies on the board *and* none in supply (reachable if
their spies were returned to supply by an opponent). Without it, `sel_place_spy` would
emit zero moves there and the original soft-lock would return.

Encode the decline as a `MOVE_RESOLVE_GENERIC` with `action_id = SYM_NULL` and
`target_id = SYM_NULL` — distinguishable from a relocation (which always carries both)
and from a supply placement (which carries `action_id` only). `apply_place_spy` already
returns `state` unchanged when `target` is `SYM_NULL`
([`actions.c:267-268`](engine_c/actions.c#L267-L268)), so the decline is a no-op on the
apply side with **no change required there**.

Note the contrast with the empty-barracks deploy, which is *mandatory* — the rulebook
grants a decline for spies (line 338) but not for deploys (line 319).

## Out of Scope

- The paid/standard "place a spy" action — there is no `MOVE_PLACE_SPY`; spy placement
  is card-driven only in this engine, and adding a Power-purchased variant is a
  separate question.
- `sel_return_spy` ([`selection.c:433-471`](engine_c/selection.c#L433-L471)) and the
  standalone `return_spy` op, which are unaffected.
- Enemy-spy relocation — rulebook 338 covers only *your own* spies.
