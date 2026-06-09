# Testing and debugging a custom OpenSpiel game

## 1. Random simulation smoke test (run first, run often)

```python
from open_spiel.python.algorithms import random_sim  # if available in your install
# or hand-roll the playthrough loop from core-api.md inside a for-loop:
for _ in range(200):
    play_one_random_game(game)   # assert returns() length == num_players,
                                 # zero-sum games: assert abs(sum(returns)) < 1e-9
```

Assertions worth adding to the loop:
- every `returns()` entry within `[game.min_utility(), game.max_utility()]`
- game length never exceeds `game.max_game_length()` (counting decision nodes)
- `legal_actions()` non-empty and sorted at every decision node
- chance outcome probabilities sum to ~1.0

## 2. The built-in API consistency test

OpenSpiel ships a generic test harness that checks the full State/Game contract:

```python
from open_spiel.python.tests import pyspiel_test  # in-repo
# or, standalone and most useful:
import pyspiel
pyspiel.random_sim_test(game, num_sims=10, serialize=True, verbose=True)
```

`random_sim_test` exercises cloning, serialization round-trips, observer calls, and undo where implemented. Run it after every substantive rules change.

## 3. Playthrough regression files (in-repo development)

If developing inside the open_spiel repo, generate a frozen random playthrough so future changes can't silently alter game behavior:

```
./open_spiel/scripts/generate_new_playthrough.sh python_my_game
```

Integration tests auto-compare stored playthroughs against fresh ones. After an intentional rules change, regenerate with `./scripts/regenerate_playthroughs.sh`.

## 4. Visualizing the tree

For small games, render the full tree with graphviz via `open_spiel/python/examples/treeviz_example.py`. For interactive exploration of larger games there is SpielViz (https://github.com/michalsustr/spielviz). Eyeballing the first two plies catches most action-encoding mistakes.

## 5. Information-set sanity check (imperfect-info games only)

CFR correctness hinges on the info-state string. Enumerate states and verify:

```python
from open_spiel.python.algorithms.get_all_states import get_all_states
states = get_all_states(game, depth_limit=-1, include_terminals=False,
                        include_chance_states=False)
# Group histories by (player, information_state_string). Within one group,
# legal_actions must be identical — if not, your info-state string leaks
# or omits information.
```

Then run a known algorithm and check the number is plausible: tabular CFR on a tiny instance of your game should drive exploitability toward 0.

## 6. Common failure modes → symptoms

| Mistake | Symptom |
|---|---|
| Overrode `legal_actions` instead of `_legal_actions` (or vice versa for `apply_action`) | Infinite recursion, or framework ignores your method entirely |
| `_legal_actions` unsorted | `random_sim_test` failure; subtle algorithm bugs |
| Forgot to flip `_cur_player` in `_apply_action` | One player moves forever; tree visualization makes this obvious |
| `max_game_length` too small | Tree-walking algorithms truncate; exceptions deep in C++ |
| Mutable default / shared object across states | Cloned states corrupt each other; nondeterministic test failures |
| `returns()` only valid at terminal states | Crashes in algorithms that query mid-game; make it total-return-so-far |
| Info-state string missing own past actions | Perfect recall violated; CFR converges to wrong policy with no error |
| Randomness inside `_apply_action` instead of a chance node | Non-reproducible playthroughs; serialization round-trip test fails |
| Observer reassigns `self.tensor` instead of writing through views | Tensors silently stay zero |

## 7. Performance notes

Python games run ~100x slower than C++. Acceptable for: CFR variants (tree extracted once), small/medium tabular analysis, prototyping. Painful for: MCTS at scale, deep RL training loops with millions of steps. The standard path is prototype-in-Python, port-to-C++ once rules stabilize — the C++ port follows the same structure (copy `tic_tac_toe.h/cc` per the developer guide: https://openspiel.readthedocs.io/en/latest/developer_guide.html).
