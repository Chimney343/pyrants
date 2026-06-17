# Optimize IS-MCTS Performance: Phase 2 — New Bottlenecks

## Why "18× more tree nodes"

The before/after comparison is **not apples-to-apples**. The before run timed out at ~104 moves (incomplete); the after run completed all 134 moves. The `_apply_action` call count went from 48K → 880K because:

1. **Before**: IS-MCTS was bottlenecked on deepcopy, so each simulation was slow (~3.8s/move), and the 5-minute timeout only covered ~104 moves × ~460 tree-node visits each = 48K calls.
2. **After**: With deepcopy eliminated, each simulation is faster (~3.2s/move), so the same 5-minute window covers the full 134 moves. IS-MCTS explores deeper per simulation (more world determinizations, longer rollouts) = 880K calls total.

**Per-action cost** dropped from 2,178µs → 324µs — a **6.7× speedup**. The total wall-clock time is similar because more work got done, not because it got slower.

## New Top Bottlenecks (from cProfile)

| Rank | Function | Self | Cum | % total | Root cause |
|------|----------|------|-----|---------|-------------|
| 1 | `validate_python` | 31.6s | 32.0s | 11% | Pydantic validation in `BoardState()` constructor inside `_cow_clone` |
| 2 | `_cow_clone` | 19.4s | 40.8s | 7%/14% | 2.27M COW clones per game — includes `BoardState()` constructor overhead |
| 3 | `builtins.any` | 17.2s | 27.3s | 6% | Called from `has_presence` and `_can_deploy_to_node` — hot inner loops |
| 4 | `has_presence` | 11.8s | 27.7s | 4%/10% | Called 6.7M times — iterates all board nodes for adjacency |
| 5 | `_legal_main_phase_actions` | 5.3s | 49.8s | 2%/17% | Generator legal moves — calls deploy/assassinate presence checks |
| 6 | `compute_action_map` | 1.0s | 107.6s | 0%/38% | Sort+flatten+encode every legal move, persisted by IS-MCTS |
| 7 | `model_copy` (Pydantic) | 1.1s | 36.2s | 0.4%/13% | Called from `_cow_node`/`_cow_player`/`_cow_market_state`/`_cow_resource_pool` |
| 8 | `sorted` (builtins) | 4.8s | 35.3s | 2%/12% | Sorting legal moves in `compute_action_map` |
| 9 | `_can_deploy_to_node` | 6.8s | 36.2s | 2%/13% | Called 8M times per game — presence + vacancy check per node |
| 10 | `_remaining_special_stack_count` | 5.0s | 11.1s | 2%/4% | Counts cards across all player zones with `.count()` x7 |

## Plan: 6 Optimizations

### 1. Eliminate Pydantic validation in `_cow_clone` and COW accessors

**Problem**: `_cow_clone` line 667 does `BoardState(nodes=dict(value.nodes))` which triggers Pydantic's `__init__` → `validate_python` on every COW clone. That's 2.27M calls × ~14µs validation = 31.6s. Similarly, `_cow_node`/`_cow_player`/`_cow_market_state`/`_cow_resource_pool` call `.model_copy()` which also validates.

**Fix**: Replace `BoardState(nodes=dict(value.nodes))` with `BoardState.clone_fast_shallow()` that skips Pydantic validation.

Add a `clone_fast_shallow()` method to `BoardState` that creates a new instance via `__new__` + `__dict__` assignment, sharing the nodes dict values (COW semantics — individual nodes are lazily copied by `_cow_node`):

```python
class BoardState(BaseModel):
    nodes: dict[str, NodeState] = Field(default_factory=dict)

    def clone_fast_shallow(self) -> BoardState:
        """COW-shallow clone: shares node values by reference (lazy-copied by _cow_node)."""
        m = BoardState.__new__(BoardState)
        d = {"nodes": dict(self.nodes)}  # new dict, shared NodeState values
        object.__setattr__(m, "__dict__", d)
        object.__setattr__(m, "__pydantic_extra__", {})
        object.__setattr__(m, "__pydantic_fields_set__", self.__pydantic_fields_set__.copy())
        object.__setattr__(m, "__pydantic_private__", None)
        return m
```

Then in `_cow_clone`, replace:
```python
d[key] = BoardState(nodes=dict(value.nodes))
```
with:
```python
d[key] = value.clone_fast_shallow()
```

Also replace `.model_copy()` in COW accessors with `.clone_fast()`:
- `_cow_node`: `node.model_copy()` → `node.clone_fast()`
- `_cow_player`: `player.model_copy()` → `player.clone_fast()`
- `_cow_market_state`: `state.market.model_copy()` → `state.market.clone_fast()`
- `_cow_resource_pool`: `state.resource_pool.model_copy()` → `state.resource_pool.clone_fast()`

**Expected savings**: ~31.6s (validate_python) + ~16s (model_copy) = ~47s, roughly 16% of total runtime.

### 2. Cache `has_presence` with an adjacency index

**Problem**: `has_presence` (6.7M calls, 11.8s self) iterates over ALL board nodes checking adjacency for every deploy/assassinate legal-move check. The board has 81 nodes, and each call does O(adjacency_degree) work. With 882K `_legal_actions` calls each checking up to 81 nodes, that's ~7M calls × 4-8 adjacency checks each.

**Fix**: Build a per-player presence set/cache on `GameState` that tracks which node_ids each player occupies. Update it in `_cow_node` when troop_slots or spies change.

Add to `GameState`:
```python
_presence_cache: dict[str, set[str]] | None  # player_id -> set of node_ids with presence
```

Then `has_presence` checks `_presence_cache[player_id]` — O(1) set lookup instead of O(nodes) iteration.

The cache is invalidated when any node's troops or spies change. Since we already use `_cow_node` to lazily copy nodes before mutation, we can detect cache staleness and invalidate. Alternatively, clear the cache on every `_cow_clone` and compute it lazily on first query.

Simpler approach: compute the presence set lazily and cache it on the COW clone:

```python
def has_presence(state: GameState, player_id: str, node_id: str) -> bool:
    cache = state.__dict__.get("_presence_set")
    if cache is None or cache[0] != player_id:
        # Build set of node_ids where player has presence
        present = set()
        for nid, ns in state.board.nodes.items():
            if player_id in ns.spies or any(s == player_id for s in ns.troop_slots):
                present.add(nid)
            else:
                for adj_id in board_index(state.definition.board)[nid].adjacent_to:
                    adj_ns = state.board.nodes[adj_id]
                    if any(s == player_id for s in adj_ns.troop_slots):
                        present.add(nid)
                        break
        cache = (player_id, present)
        state.__dict__["_presence_set"] = cache
    return node_id in cache[1]
```

Actually, this is tricky because `_cow_clone` shares `board.nodes` by shallow reference — mutating a node via `_cow_node` could invalidate the cache. Let me take a different approach.

**Better fix**: Pre-compute a static adjacency lookup table (already exists as `board_index`) and a per-player presence set that's built once per `_cow_clone` and invalidated on `_cow_node` writes:

In `_cow_clone`, add a `_presence_dirty = True` flag. When `_cow_node` writes, set `_presence_dirty = True`. The `has_presence` function checks if presence is dirty and rebuilds.

**Expected savings**: ~11.8s self + ~9s from `any()` calls inside = ~20s, roughly 7% of total.

### 3. Shortcut `_player_has_any_troops_on_board` and cache it

**Problem**: `_player_has_any_troops_on_board` (called inside `_can_deploy_to_node` when `has_troops_on_board` is None) iterates all 81 nodes. Called 8M times but only needs to compute once per COW clone since troops don't change between legal-move checks within the same state.

**Fix**: Add `_has_troops_cache: dict[str, bool] | None` to GameState. Populate lazily in `_player_has_any_troops_on_board`. Reset in `_cow_clone`.

Actually, `_can_deploy_to_node` already has a `has_troops_on_board` parameter and `_legal_main_phase_actions` computes it once and passes it in. But `_can_deploy_to_node` is still called 8M times because it's called per-deploy-node (81 nodes × 882K legal_actions calls), and `has_presence` inside it iterates adjacency each time.

The real fix is to combine with optimization #2 — the presence cache makes `has_presence` O(1), which makes `_can_deploy_to_node` O(1) per node check, which makes `_legal_main_phase_actions` much faster.

**Expected savings**: Combined with #2, roughly 20-25s total.

### 4. Optimize `_remaining_special_stack_count`

**Problem**: Called 1.73M times, 5.0s self, 11.1s cum. It calls `.count()` 7 times (deck, hand, discard, played, inner_circle, trophy_hall × 2 players × 3 stack types).

**Fix**: This is called during legal move generation for recruit moves. Pre-compute card counts once per state and store in a cache keyed on the market row snapshot.

Simpler fix: Replace the 7× `.count()` calls with a single pass:

```python
def _remaining_special_stack_count(state: GameState, card_id: str, stack_total: int) -> int:
    available = state.market.deck.count(card_id) + state.market.row.count(card_id)
    if available > 0:
        return available
    owned_total = 0
    for player in state.players.values():
        owned_total += (
            player.deck.count(card_id)
            + player.hand.count(card_id)
            + player.discard_pile.count(card_id)
            + player.played_cards.count(card_id)
            + player.inner_circle.count(card_id)
            + player.trophy_hall.count(card_id)
        )
    return max(0, stack_total - owned_total)
```

This is already the existing code. The `.count()` on lists is O(n) each. For a typical list of 5-10 card IDs, this is fast but called 1.73M times.

**Better fix**: Cache `has_troops_on_board` per `_cow_clone` and short-circuit `_remaining_special_stack_count` by checking market availability first (fast path already exists). The 5s self-time is mostly `list.count()` overhead.

We could convert player card lists to `Counter`-based tracking, but that's invasive. For now, this is a 4% bottleneck — skip for phase 2.

**Expected savings**: ~2-3s (minor).

### 5. Optimize `compute_action_map` — avoid redundant sort+flatten

**Problem**: `compute_action_map` (107.6s cum, 38% of runtime) is called 880K times. It calls `get_legal_moves()` then `sorted()` with `_move_sort_key` which does `model_dump()` + `_flatten()` + tuple comparison on every call. The `sorted` call alone consumes 35.3s (4.8s self + 30.5s in `move_sort_key` + child calls).

**Fix**: The action map is computed freshly for every `_legal_actions` call in IS-MCTS. For IS-MCTS, the legal move list is used to:
1. Determine which actions are available (list of action IDs)
2. Map action IDs back to moves

The sorting is needed for deterministic action ID assignment. But `_move_sort_key` is expensive: it calls `model_dump()` on every Move, then recursively flattens+sorts the dict into tuples.

**Optimization**: Cache the action map on the `PyrantsState` and invalidate it on `_apply_action`. We already have `_cached_indexed_moves` for this purpose! But it's set to `None` after every `_apply_action`. The issue is that IS-MCTS calls `_legal_actions` and `_apply_action` in alternating patterns, and the cache IS used — it just doesn't help across `_apply_action` calls because the state changes.

The real optimization is to make `_move_sort_key` cheaper. Instead of `model_dump` → flatten → sorted tuples, we could:

a) Pre-compute a sort key at Move construction time (add a `__lt__` method)
b) Use a simpler sort key that doesn't require full model serialization

Approach (b) is simpler. Most Move types have a few key fields:

```python
def _move_sort_key(move: Move) -> tuple:
    return (move.move_type, move.player_id, *_move_sort_payload(move))
```

But this requires per-move-type logic. For now, the 38% cumulative includes child calls that we can't easily eliminate.

**Alternative**: Cache `_legal_actions` results on `PyrantsState` and invalidate only when `_engine` changes. Since `_engine` changes on every `_apply_action`, this gives at most 1 cache hit per `_legal_actions` call... which is exactly what `_cached_indexed_moves` already does. The cache IS working; the cost is inherent to recomputing legal moves for every state.

**Expected savings**: Moderate — the sort+serialize accounts for ~35s but some is irreducible. A simpler sort key could save ~15-20s.

### 6. Optimize `_cow_clone` loop overhead

**Problem**: `_cow_clone` iterates `self.__dict__.items()` with 16+ if/elif branches. Called 2.27M times at 8.5µs per call. The loop + dict iteration + set membership tests add overhead.

**Fix**: Unroll the loop into explicit field assignments:

```python
def _cow_clone(self) -> GameState:
    cls = type(self)
    m = cls.__new__(cls)
    d = {
        "definition": self.definition,
        "board": self.board.clone_fast_shallow(),
        "players": dict(self.players),
        "turn_order": list(self.turn_order) if isinstance(self.turn_order, list) else self.turn_order,
        "current_player_id": self.current_player_id,
        "phase": self.phase,
        "round_number": self.round_number,
        "resource_pool": self.resource_pool,
        "market": self.market,
        "final_scores": dict(self.final_scores) if self.final_scores else {},
        "pending_ability": self.pending_ability,
        "pending_immediate_promotions": list(self.pending_immediate_promotions),
        "pending_end_of_turn_promotions": list(self.pending_end_of_turn_promotions),
        "pending_generic_choice": self.pending_generic_choice.model_copy(deep=True) if self.pending_generic_choice is not None else None,
        "devour_pile": list(self.devour_pile),
        "setup_complete": set(self.setup_complete),
        "shuffle_seed": self.shuffle_seed,
        "shuffle_count": self.shuffle_count,
    }
    object.__setattr__(m, "__dict__", d)
    object.__setattr__(m, "__pydantic_extra__", {} if not self.__pydantic_extra__ else dict(self.__pydantic_extra__))
    object.__setattr__(m, "__pydantic_fields_set__", self.__pydantic_fields_set__.copy())
    object.__setattr__(m, "__pydantic_private__", None)
    object.__setattr__(m, "_cow_dirty", set())
    return m
```

This removes:
- Dict iteration overhead (16 items × 2.27M calls)
- Set membership tests on `_shared`, `_list_copy`, `_dict_copy`, `_set_copy`
- `isinstance` check on `turn_order`
- `if key == "definition"` / `if key == "board"` / etc. string comparisons

**Expected savings**: ~5-8s (the explicit dict construction is faster than the loop).

## Implementation Order

1. **Optimization 1** (BoardState validation bypass) — biggest win (~47s), surgical change
2. **Optimization 6** (unroll _cow_clone loop) — moderate win (~5-8s), simple change
3. **Optimization 2** (presence cache) — moderate win (~20s), requires cache invalidation in COW
4. **Optimization 5** (cheaper action sort key) — moderate win (~15-20s), more invasive
5. **Optimization 4** (special stack count) — minor, skip for now

## Total Expected Impact

Current: 285s CPU for 134 moves (324µs/action)
After opt 1+6: ~230s (285 - 47 - 8 = ~230s) → ~245µs/action
After opt 2+3: ~210s (230 - 20 = ~210s) → ~224µs/action
After opt 5: ~195s → ~208µs/action

Overall: 285s → ~195s = **1.46× faster**, or going from 324µs/action → ~208µs/action = **1.56× faster per action**.