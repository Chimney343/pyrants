# How the OpenSpiel Wrapper Works

## Architecture

The wrapper translates between two domains: OpenSpiel expects integer actions on a `pyspiel.State`; the pyrants engine produces `Move` objects on a `GameState`. The translation happens in four files.

- `game.py` — loads board, cards, and setup data; declares the `GameType` and `GameInfo`; spawns state objects.
- `state.py` — wraps one moment in the game. Holds an `engine.state.GameState` internally, delegates all rule questions to it, and translates integer actions back into engine moves.
- `action_encoding.py` — builds the per-state mapping between engine moves and integer action ids.
- `__init__.py` — registers the game with `pyspiel` so `load_game("python_pyrants")` works.

## Game Object

`PyrantsGame` constructs itself from three JSON files in `data/`: a board definition, a card catalog, and a deck setup. It caches the parsed definition, the player id list (derived from `num_players`, default ``p1, p2`` for 2 players), and the shuffle seed count (1000).

The `GameType` and `GameInfo` are built per-instance from the resolved `num_players` parameter (2–4). For 2 players the game is declared `ZERO_SUM`; for 3+ players it is `GENERAL_SUM`. The `GameInfo` sets a ceiling of 1024 distinct actions, 1000 chance outcomes, utility range `[-200, 200]` (2p) or `[-400, 400]` (3–4p), and a game length of 4096 decision nodes.

`new_initial_state()` returns a fresh `PyrantsState` with no engine. The engine materializes only after the chance node resolves.

## State Lifecycle

A `PyrantsState` has two modes, governed by `_pending_initial_chance`.

### Chance Mode

Before the engine exists, the state reports `PlayerId.CHANCE` as the current player. Its legal actions are the integers 0 through 999, one per possible shuffle seed. Each outcome carries uniform probability.

When the framework applies a chance action, the state hashes the public outcome id into an internal seed and calls `build_initial_game_state(definition, [p0, p1], seed=internal)`. The engine is born. The state transitions from baby to adult.

The hash function (`_public_to_seed`) uses a Knuth multiplicative hash: `(id * 2654435761) & 0x7FFFFFFF`. This is a bijection over the 2^31 space, so the mapping preserves the uniform-probability contract of `chance_outcomes`. The public history records the raw outcome id; only the wrapper knows the internal seed. This prevents an observer from recovering both players' shuffle orders by reading the history.

### Decision Mode

Once the engine exists, the state delegates all game queries to it. `current_player()` reads `engine.current_player_id`. `is_terminal()` calls `engine.rules.is_terminal(engine)`. For 2 players `returns()` computes the score difference: `p0_score - p1_score` for player 0, the reverse for player 1. For 3+ players `returns()` reports each player's raw score.

`_legal_actions()` calls `engine.rules.legal_moves(engine)`, sorts the moves deterministically, and assigns each an integer index. It caches the full (index, move) list on `self._cached_indexed_moves` so `_apply_action` and `_action_to_string` can reuse it without re-enumerating. The cache invalidates after each `_apply_action`.

## Action Encoding

OpenSpiel consumes integer actions. The engine produces `Move` objects with typed fields: `PlayCardMove(hand_index=2)`, `DeployMove(node="site_7")`, `AssassinateMove(node="site_3", slot=1)`, and ten other move kinds.

The encoding flattens these into a per-state list:

1. Call `engine.rules.legal_moves(state)` to get the raw move objects.
2. Sort them by their JSON representation, excluding `player_id`, to guarantee deterministic ordering.
3. Assign action ids 0, 1, 2, ... in sorted order.

The sort key is the move's `model_dump_json(exclude={"player_id"})`. Same engine state always produces the same mapping, satisfying OpenSpiel's determinism requirement.

`compute_action_map(state)` returns the full sorted list as `[(original_index, Move), ...]`. The state caches this list once per node visit and uses it for all three operations: enumerating legal actions, decoding an action id into a move, and formatting the action string for history.

The `NUM_DISTINCT_ACTIONS` constant (1024) is a static upper bound, not the per-state count. It covers the worst case across all states: 5 play-card moves, 81 deploy targets, 486 assassinate combos (81 nodes × 6 slots), 162 return-spy targets, 9 recruit slots, 2 ability toggles, 2 promotion choices, 3 resolution moves, and 5 chance outcomes. The total rounds to 1024, a power of two.

## Shuffle Determinism (Engine Side)

The engine uses two functions to shuffle decks. Both need identical seeding logic.

`_shuffle_deck(deck, seed, counter)` in `engine/state.py` generates a `random.Random` instance seeded with `(seed << 16) ^ counter` and shuffles. It handles the initial setup deal.

`_reshuffle_discard_into_deck(state, player_id)` in `engine/helpers.py` runs during cleanup when a player's deck empties and the discard pile recycles. It now delegates directly to `_shuffle_deck` instead of duplicating the seed math inline. The duplicate `from random import Random` import was removed.

## Full Sequence

```
PyrantsGame created
  → new_initial_state() → PyrantsState(_engine=None)

CHANCE NODE:
  current_player() → CHANCE
  _legal_actions() → [0, 1, ..., 999]
  _apply_action(7)
    → _public_to_seed(7) → internal seed
    → build_initial_game_state(definition, players, internal)
    → _engine = GameState with shuffled decks, populated board

DECISION NODES, repeating:
  _legal_actions()
    → compute_action_map(_engine) → cache on state
    → [0, 1, ..., N-1]
  _apply_action(3)
    → cached_map[3][1] → the Move
    → engine.rules.apply(_engine, move) → new _engine
    → cache cleared

TERMINAL:
  is_terminal() → True
  returns() → [p0_diff, p1_diff]
```

## Tests

- `test_random_sim.py` — 100 random playthroughs. Verifies sorted actions, zero-sum returns, no crashes.
- `test_api_test.py` — OpenSpiel's built-in `random_sim_test` with 5 iterations.
- `test_action_encoding.py` — Move to action id roundtrip, plus a seed hashing test that confirms the public id never equals the internal seed (except id 0, which maps to 0 in any multiplicative hash).
- `test_pyrants_register.py` — Verifies the game registers, loads, and reports correct `GameType` flags and `GameInfo` constants.

## Performance

Every state clone deep-copies the engine Pydantic model. MCTS, which clones states thousands of times per second, runs slowly on this wrapper. CFR and other tree-building algorithms that extract the full game tree once run without issue. This tradeoff is inherent to Python game implementations in OpenSpiel.

## Information-State Projection

The `engine/player_view.py` module defines what each player can observe at any
point in the game. Two Pydantic models capture this:

- **`PublicView`** — board occupancy (controller, troop/spy counts per node),
  market row card ids, pending effect identifiers, resource totals, and
  per-player summary counts (hand/deck/discard sizes, scores). No card
  identities from hidden zones.

- **`PrivateView`** — a `PublicView` plus the observing player's hand card ids
  (in hand order), deck/discard/devour sizes, played cards, inner circle,
  trophy hall, barracks, spies, VP tokens, and score. Opponent hidden-zone
  contents are excluded.

Both models are frozen and serialize to stable JSON via `model_dump_json()`.
The serialized `PrivateView` is used as the information-state string in
IS-MCTS (prefixed with the game history for perfect recall).

The determinization module (`openspiel_pyrants/determinization.py`) uses
`PublicView` equality to verify that resampled states are indistinguishable
from the original to a third-party observer. The `resample_from_infostate`
contract:
1. Public view matches the original exactly.
2. The observing player's hand and deck order are preserved.
3. Every opponent's hidden zones preserve the same multiset of cards but
    are reshuffled using the bot's RNG.
