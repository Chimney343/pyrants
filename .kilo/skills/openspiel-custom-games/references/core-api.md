# Core API: methods you call on Game and State

These are the consumer-side methods (Python `snake_case`; C++ is the same in `CamelCase`). `spiel.h` in the OpenSpiel repo is the authoritative documentation. Full per-method docs: https://openspiel.readthedocs.io/en/latest/api_reference.html

## Module-level (pyspiel)

| Call | Purpose |
|---|---|
| `load_game(name)` / `load_game(name, params_dict)` | Construct a registered game, e.g. `load_game("python_my_game")` or `load_game("kuhn_poker", {"players": 3})`. String-embedded params also work: `load_game("kuhn_poker(players=3)")`. |
| `registered_names()` | List all registered short names — use to confirm registration worked. |
| `serialize_game_and_state(game, state)` / `deserialize_game_and_state(s)` | Round-trip a (game, state) pair through a string. |
| `load_game_as_turn_based(name)` | Wrap a simultaneous game as sequential. |

## State: navigation and play

| Call | Purpose |
|---|---|
| `current_player()` | Acting player id, or TERMINAL / CHANCE / SIMULTANEOUS sentinels. |
| `legal_actions()` / `legal_actions(player)` | Legal action ids at this node. |
| `legal_actions_mask()` | Same as 0/1 vector over the global action space — what RL nets consume. |
| `apply_action(a)` / `apply_actions([a0, a1, ...])` | Advance the state in place (plural form for simultaneous nodes). `*_with_legality_check` variants validate first — use them in tests. |
| `child(a)` | Clone-then-apply: new state, original untouched. |
| `clone()` | Deep copy. Essential before speculative exploration. |
| `undo_action(player, a)` | Reverse the last action (only if the game implements it). |
| `is_terminal()` / `is_chance_node()` / `is_simultaneous_node()` / `is_player_node()` / `is_initial_state()` | Node-type predicates. |
| `chance_outcomes()` | `[(action, prob), ...]` at chance nodes. |

## State: payoffs

| Call | Purpose |
|---|---|
| `returns()` | Cumulative return per player from the start. |
| `rewards()` | Reward per player since the last transition (REWARDS model). |
| `player_return(p)` / `player_reward(p)` | Single-player versions. |

## State: information and rendering

| Call | Purpose |
|---|---|
| `information_state_string([player])` | Perfect-recall info-state string — what CFR keys on. |
| `information_state_tensor([player])` | Same as floats. |
| `observation_string([player])` / `observation_tensor([player])` | Current-snapshot view — what RL agents consume. |
| `to_string()` / `__str__` | Debug rendering. |
| `action_to_string(player, a)` / `string_to_action(s)` | Action ↔ readable string. |
| `history()` / `full_history()` / `history_str()` | Actions taken so far (full_history pairs each with its player). |
| `move_number()` | Moves made so far. |
| `serialize()` | State → string; rebuild with `game.deserialize_state(s)`. |
| `resample_from_infostate(player, rng)` | Sample a history consistent with the player's info state (determinization for imperfect-info search). |

## Game

| Call | Purpose |
|---|---|
| `new_initial_state()` | Root state (may itself be a chance node). |
| `num_players()` / `num_distinct_actions()` | Declared sizes. |
| `min_utility()` / `max_utility()` / `utility_sum()` | Declared payoff bounds. |
| `max_game_length()` / `max_chance_outcomes()` | Declared tree bounds. |
| `get_type()` / `get_parameters()` | The GameType flags / resolved parameter dict. |
| `make_observer(iig_obs_type, params)` | Construct an observer (see implementation reference §8). |
| `observation_tensor_shape()` / `information_state_tensor_shape()` (+ `_size`, `_layout`) | Tensor geometry for network input layers. |
| `deserialize_state(s)` | Rebuild a state serialized by `state.serialize()`. |

## Minimal playthrough loop

```python
import numpy as np, pyspiel

game = pyspiel.load_game("python_my_game")
state = game.new_initial_state()
while not state.is_terminal():
  if state.is_chance_node():
    actions, probs = zip(*state.chance_outcomes())
    state.apply_action(np.random.choice(actions, p=probs))
  elif state.is_simultaneous_node():
    state.apply_actions([np.random.choice(state.legal_actions(p))
                         for p in range(game.num_players())])
  else:
    state.apply_action(np.random.choice(state.legal_actions()))
print(state.returns())
```
