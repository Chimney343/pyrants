# Wrapping an existing Python game engine

If the user already has a working rules engine, do **not** rewrite the rules. OpenSpiel only requires that *something* implements the `pyspiel.State` / `pyspiel.Game` interface; what lives behind those methods is unconstrained. The job is to build a thin adapter whose methods delegate to the engine. A full reimplementation is warranted only when the engine's state model is fundamentally hostile to cloning (see §2).

There is no first-class "wrap an external engine" API — the supported path is the same `pyspiel.Game`/`pyspiel.State` subclassing from `game-implementation.md`, with each method translating to an engine call.

## The adapter pattern

Hold the engine on the `State` and translate each method. Keep the translations one or two lines:

```python
class MyGameState(pyspiel.State):
  def __init__(self, game):
    super().__init__(game)
    self._engine = game._engine_factory()      # your existing engine, fresh instance

  def current_player(self):
    if self._engine.is_over():
      return pyspiel.PlayerId.TERMINAL
    if self._engine.awaiting_random_event():
      return pyspiel.PlayerId.CHANCE
    return self._engine.to_move()               # must be 0-indexed

  def _legal_actions(self, player):
    return sorted(self._to_id[m] for m in self._engine.legal_moves(player))

  def _apply_action(self, action):
    if self.is_chance_node():
      self._engine.force_outcome(self._id_to_outcome[action])   # inject, don't sample
    else:
      self._engine.play(self._id_to_move[action])

  def is_terminal(self):
    return self._engine.is_over()

  def returns(self):
    return self._engine.scores_as_list()        # one float per player

  def _action_to_string(self, player, action):
    return str(self._id_to_move[action])
```

Build the `move ↔ id` maps once and hang them off the `Game` so every state shares them — playthroughs and learned policies are indexed by these integers, so the bijection must be stable across runs (see action-encoding guidance in `game-implementation.md`).

## The four wrappability requirements

These are the properties the engine must have. Where it lacks one, that's the refactor work — and it's almost always a partial refactor of the engine, not a rewrite.

### 1. Randomness must be extractable into explicit chance nodes

This is usually the biggest refactor. OpenSpiel's whole formalism is an extensive-form tree with an explicit chance player; an engine that rolls dice or shuffles *inside* a move method breaks tree-based algorithms and reproducibility.

The fix: stop letting the engine sample. At a randomness point, return `pyspiel.PlayerId.CHANCE` from `current_player()`, expose the distribution from `chance_outcomes()`, and **inject** the sampled outcome back into the engine in `_apply_action`:

```python
def chance_outcomes(self):
  assert self.is_chance_node()
  outcomes = self._engine.possible_random_outcomes()   # undealt cards, die faces, ...
  p = 1.0 / len(outcomes)
  return [(self._outcome_to_id[o], p) for o in outcomes]
```

Set `chance_mode=EXPLICIT_STOCHASTIC` and `max_chance_outcomes` (the largest branching at any single chance node) in the GameType/GameInfo. Decompose compound randomness into a *sequence* of chance nodes — deal one card per node, as Kuhn and Leduc poker do — to keep `max_chance_outcomes` small and the tree analyzable.

OpenSpiel's own guidance (`spiel.h`, the `ChanceMode` enum comment): prefer explicit stochastic when in doubt, because it exposes the whole outcome distribution to learning algorithms rather than just a sampled outcome. Reserve `SAMPLED_STOCHASTIC` for cases where enumerating outcomes is genuinely intractable — it forfeits that visibility and creates an RNG-serialization pitfall (a game holding internal RNG state loses it across serialize/deserialize and replays the same "random" sequence; if unavoidable, fold the seed into the game parameters so it round-trips).

### 2. State must be cheaply and correctly deep-copyable

`state.clone()` is called constantly — at essentially every MCTS simulation step — so clone cost is multiplied enormously. The Tic-Tac-Toe source says it outright: Python games are much slower than C++, fine for tree-extraction algorithms like CFR, "likely to be poor if the algorithm relies on processing and updating states as it goes, e.g., MCTS."

Practices:
- **Keep the State's own attributes small and plain** (ints, tuples, small numpy arrays). Clone cost is dominated by what you store on the state; hanging a giant mutable engine object on it makes every clone expensive.
- **Prefer a history/replay representation for heavy engines.** OpenSpiel serialization is already "game string + action list" — `serialize_game_and_state` records the action history and `deserialize` replays it. A wrapper that rebuilds engine state from the action history therefore gets cheap, provably-correct cloning and serialization for free; the trade is recompute time vs. copy time.
- **Never share mutable substructure between a state and its clone** — the classic shallow-copy bug (inner lists/dicts aliased) silently corrupts the search tree with no error.
- **Don't store un-copyable handles** (sockets, file handles, RNG objects with hidden state, C-extension objects without copy support) on the state. If a custom object must live there, give it a correct `__deepcopy__`/`__getstate__`/`__setstate__` that copies only what mutates (copy-on-write for immutable shared parts). Naïve `copy.deepcopy` of a large object graph has been measured at multiple milliseconds per call and a large fraction of MCTS runtime — a real bottleneck, not a micro-optimization.

Note that parallel training (multiprocessing/Ray) relies on the serialize/deserialize pickle path, so the state must serialize losslessly from its history.

### 3. Moves must map to a flat integer action space

Every action is an integer in `[0, num_distinct_actions)`. Build an explicit, stable bijection (precomputed dict + list on the Game). For composite moves, either flatten (`piece * num_cells + dest`) into one decision per ply, or split one logical move into several sequential decision nodes (choose unit, then order) — splitting keeps `num_distinct_actions` small at the cost of tree depth, and is often cleaner for large or variable move spaces. Keep `num_distinct_actions` a fixed upper bound for the whole game and expose only the currently-legal subset via `_legal_actions`. Full detail and the flatten-vs-split tradeoff are in `game-implementation.md`.

### 4. Pure rules core

The engine code reached by move application must be free of printing, input, globals, and UI side effects. If rules and I/O are tangled, separating them is the refactor — one that improves the engine independently of OpenSpiel.

## Hidden information when the engine stores ground truth

If the engine keeps the full truth (all hands, deck order, fog-of-war map) in one object, perfect-information analysis wraps trivially. For imperfect-information algorithms you additionally need the observer to expose **only what each player legitimately knows** — the engine doesn't have to change, but you must be able to query "player p's view" from it.

Implement `make_py_observer` + an observer with `set_from(state, player)` (fill the tensor from `player`'s view, omitting others' private info) and `string_from(state, player)`. The information-state string must satisfy perfect recall (private info + full public action sequence); the observation can be a smaller current snapshot. Use `IIGObserverForPublicInfoGame` for fully-public games. See the imperfect-information delta in `game-implementation.md` for the dispatch-on-`iig_obs_type` pattern. Verify no leak by reading the `InformationStateString`/`ObservationString` lines in a generated playthrough.

## Validation order specific to wrapping

1. **Register and load.** `register_game` at import, then `load_game("python_<name>")`. Note: Python games can't run through the C++ `build/examples/example` binary — use `python/examples/example.py` and `mcts.py`.
2. **Random simulation** driving chance via `chance_outcomes()` and players via `legal_actions()`, asserting the invariants (sorted non-empty legal actions, returns within declared bounds, zero-sum returns summing to 0, length ≤ `max_game_length`). `pyspiel.random_sim_test(game, num_sims=10, serialize=True)` also exercises clone and serialization round-trips — the fastest way to catch aliasing and history-replay bugs.
3. **Enumerate the tree** with `get_all_states` on a small parameterization; it expands via cloning, so it surfaces clone-independence bugs and illegal/mismatched action ids.
4. **Playthrough regression** (`generate_new_playthrough.sh` → commit; integration tests auto-compare). Reading the playthrough by eye is the recommended first mechanics check.

See `testing-debugging.md` for the full harness and the mistake→symptom table.

## The wrap-vs-rewrite decision

- **Pure adapter (≈ a day):** engine already separates a pure rules core from I/O and has injectable randomness.
- **Refactor then wrap:** randomness or side effects are tangled into move application — refactor the engine into a wrappable core first. Partial work, but it improves the engine anyway.
- **Full C++ reimplementation:** the state model is fundamentally hostile to cloning (event-sourced against a DB; copy cost dominates), or you need high-throughput MCTS/AlphaZero self-play. The recommended path is prototype-and-wrap in Python, then port to C++ once rules and action encoding are stable, using the Python playthrough as the regression oracle. CFR-family and exploitability analysis run fine on the Python wrapper; clone-heavy self-play is where C++ becomes necessary.
