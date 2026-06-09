---
name: openspiel-custom-games
description: Implement custom games in OpenSpiel (DeepMind's game-theory/RL framework) as pure-Python pyspiel games. Use this skill whenever the user wants to model a board game, card game, or any turn-based/simultaneous-move game in OpenSpiel, mentions pyspiel, GameType, extensive-form games, or wants to run game-theoretic analysis (CFR, MCTS, exploitability) on their own game. Also use it when porting an existing Python game engine or board game simulator into OpenSpiel, or when debugging a custom pyspiel.Game/pyspiel.State implementation.
---

# OpenSpiel Custom Games

Implement custom games as pure-Python OpenSpiel games (`pyspiel.Game` / `pyspiel.State` subclasses). Python games are slower than C++ but ideal for prototyping and small-to-medium games. C++ algorithms that extract the full game tree (CFR family) run fine on Python games; algorithms that hammer state updates (MCTS) will be slow — warn the user if they plan heavy MCTS on a Python game.

## Prerequisites

OpenSpiel installs via pip: `pip install open_spiel` (Linux/macOS; Windows support is limited — recommend WSL2). Verify with `python -c "import pyspiel; print(len(pyspiel.registered_names()))"`.

## Workflow

**If the user already has a working game engine**, the task is to *wrap* it, not reimplement the rules. Read `references/wrapping-existing-engines.md` first — it covers the adapter pattern, the four properties the engine must have to be wrappable (extractable randomness, cheap cloning, integer action mapping, a pure rules core), the hidden-information caveat, and how to decide between a pure adapter, an engine refactor, and a C++ rewrite. The steps below still apply; the wrapping reference tells you how to satisfy each one by delegating to the engine.

1. **Classify the game first.** Before writing any code, determine four properties — they dictate which methods you implement and which `GameType` flags you set:
   - **Dynamics**: sequential (players alternate) or simultaneous (players act at once)?
   - **Chance**: deterministic, or are there dice/card draws/random events?
   - **Information**: perfect (everyone sees everything) or imperfect (hidden hands, fog of war)?
   - **Utility**: zero-sum, general-sum, or identical (cooperative)?

2. **Design the action encoding.** Every action is a single integer in `[0, num_distinct_actions)`. This is the hardest design decision for complex board games — get it wrong and everything downstream hurts. Flatten composite moves (piece + destination → `piece_id * num_cells + cell`) or split one turn into several sequential decision nodes (often cleaner for "choose unit, then choose order" games). Document the encoding in a comment block.

3. **Implement from the template.** Read `references/game-implementation.md` for the full skeleton and the per-variant deltas (chance nodes, imperfect information, simultaneous moves). Don't guess method names — the override surface is specific (`_legal_actions`, `_apply_action` with underscores on State; `new_initial_state`, `make_py_observer` without on Game).

4. **Verify immediately.** Run a random-playout smoke test plus `pyspiel`'s built-in API consistency test before writing any game logic beyond the minimum. See `references/testing-debugging.md`. A game that passes `random_sim` early saves hours of debugging later.

5. **Iterate on rules, re-test.** Each rule addition can break invariants (legal actions at terminal states, returns summing wrong for zero-sum). Keep the smoke test in the loop.

## Key invariants (violating these causes silent algorithm corruption, not errors)

- `_legal_actions` returns a **sorted, non-empty** list at every non-terminal decision node, and is never called at terminal states.
- `current_player()` returns `pyspiel.PlayerId.TERMINAL` when done, `pyspiel.PlayerId.CHANCE` at chance nodes, `pyspiel.PlayerId.SIMULTANEOUS` at simultaneous nodes, else the player id.
- `returns()` has one entry per player; for zero-sum games they must sum to 0 and stay within `[min_utility, max_utility]` declared in `GameInfo`.
- `chance_outcomes()` probabilities must sum to 1.
- `max_game_length` in `GameInfo` counts **decision nodes**, not chance nodes — underestimating it breaks tree-walking algorithms.
- State is mutated in place by `_apply_action`; never share mutable objects between cloned states (numpy arrays are copied by `clone()` only if your state's attributes deep-copy cleanly — prefer primitives, tuples, and numpy arrays over nested dicts of lists).

## References

- `references/wrapping-existing-engines.md` — wrapping an existing Python rules engine: adapter pattern, the four wrappability requirements, hidden-information handling, validation, and the wrap-vs-rewrite decision. Read this first if the user has an engine already.
- `references/game-implementation.md` — full annotated skeleton, `GameType`/`GameInfo` field guide, observer pattern, variant deltas (chance, imperfect info, simultaneous). Read this before writing the game class.
- `references/core-api.md` — `State` and `Game` method reference for the methods you call (as opposed to override) when testing and using your game.
- `references/testing-debugging.md` — smoke tests, `api_test`, playthrough regression files, tree visualization, common failure modes and their symptoms.

## Quick sanity check (use after every implementation session)

```python
import pyspiel
from open_spiel.python.algorithms.get_all_states import get_all_states

game = pyspiel.load_game("python_my_game")  # or MyGameGame()
state = game.new_initial_state()
print(game.get_type())
# For small games: enumerate the whole tree — crashes here mean broken invariants
all_states = get_all_states(game, depth_limit=20, include_terminals=True, include_chance_states=True)
print(f"{len(all_states)} states reachable")
```
