# Implementing a Python game in OpenSpiel

## Contents
1. File anatomy
2. GameType and GameInfo field guide
3. The Game class
4. The State class (perfect-info sequential baseline)
5. Variant delta: chance events
6. Variant delta: imperfect information
7. Variant delta: simultaneous moves
8. The Observer
9. Registration and loading

## 1. File anatomy

A Python game is one module containing, in order: module constants, a `_GAME_TYPE` (`pyspiel.GameType`), a `_GAME_INFO` (`pyspiel.GameInfo`), a `Game` subclass, a `State` subclass, an observer class, helper functions, and a final `pyspiel.register_game(_GAME_TYPE, MyGame)` call. The canonical in-repo examples to crib from:

| Variant | Example in `open_spiel/python/games/` |
|---|---|
| Perfect info, deterministic, sequential | `tic_tac_toe.py` |
| Imperfect info + chance (card deal) | `kuhn_poker.py` |
| Simultaneous moves + per-step rewards | `iterated_prisoners_dilemma.py` |
| Larger board game with parameters | `dynamic_routing.py`, `block_dominoes.py` |

## 2. GameType and GameInfo field guide

```python
_GAME_TYPE = pyspiel.GameType(
    short_name="python_my_game",      # unique id used by load_game; prefix python_ by convention
    long_name="Python My Game",
    dynamics=pyspiel.GameType.Dynamics.SEQUENTIAL,            # or .SIMULTANEOUS
    chance_mode=pyspiel.GameType.ChanceMode.DETERMINISTIC,    # or .EXPLICIT_STOCHASTIC
    information=pyspiel.GameType.Information.PERFECT_INFORMATION,  # or .IMPERFECT_INFORMATION
    utility=pyspiel.GameType.Utility.ZERO_SUM,                # or .GENERAL_SUM, .IDENTICAL
    reward_model=pyspiel.GameType.RewardModel.TERMINAL,       # or .REWARDS for per-step payoffs
    max_num_players=2,
    min_num_players=2,
    provides_information_state_string=True,   # set False for what you don't implement,
    provides_information_state_tensor=False,  # but CFR-family algorithms need info-state
    provides_observation_string=True,         # strings; RL agents need tensors
    provides_observation_tensor=True,
    parameter_specification={})               # e.g. {"board_size": 8} for load_game params
```

```python
_GAME_INFO = pyspiel.GameInfo(
    num_distinct_actions=N,    # size of the global integer action space
    max_chance_outcomes=0,     # max branching at any chance node (0 if deterministic)
    num_players=2,
    min_utility=-1.0,          # tightest known bounds on a player's total return
    max_utility=1.0,
    utility_sum=0.0,           # only for constant-sum games; omit for general-sum
    max_game_length=M)         # max decision nodes on any path; do NOT count chance nodes
```

Why these matter: algorithms trust the declared flags. If `provides_information_state_string=True` but the observer can't produce a perfect-recall string, CFR will silently merge information sets that should be distinct and converge to garbage.

## 3. The Game class

```python
class MyGameGame(pyspiel.Game):
  def __init__(self, params=None):
    super().__init__(_GAME_TYPE, _GAME_INFO, params or dict())
    # Read params via self.get_parameters() if parameter_specification is non-empty

  def new_initial_state(self):
    return MyGameState(self)

  def make_py_observer(self, iig_obs_type=None, params=None):
    if ((iig_obs_type is None) or
        (iig_obs_type.public_info and not iig_obs_type.perfect_recall)):
      return MyGameObserver(params)
    else:
      # Fallback for perfect-info games; imperfect-info games must
      # handle iig_obs_type themselves (see §6)
      from open_spiel.python.observation import IIGObserverForPublicInfoGame
      return IIGObserverForPublicInfoGame(iig_obs_type, params)
```

If `GameInfo` values depend on parameters (e.g. board size), construct the `GameInfo` inside `__init__` from the resolved params instead of using a module constant.

## 4. The State class — perfect-info sequential baseline

Note the naming rule: methods the framework wraps are overridden **with** a leading underscore (`_legal_actions`, `_apply_action`, `_action_to_string`); methods you implement directly have none (`current_player`, `is_terminal`, `returns`). Mixing these up produces a game that imports fine but misbehaves.

```python
class MyGameState(pyspiel.State):
  def __init__(self, game):
    super().__init__(game)
    self._cur_player = 0
    self._is_terminal = False
    # ... your board/score representation; prefer numpy arrays and primitives

  def current_player(self):
    return pyspiel.PlayerId.TERMINAL if self._is_terminal else self._cur_player

  def _legal_actions(self, player):
    # MUST return sorted ascending; only called at decision nodes for `player`
    return sorted(actions)

  def _apply_action(self, action):
    # Mutate self in place. Update terminality and scores here.
    # Advance self._cur_player at the end.
    ...

  def _action_to_string(self, player, action):
    return f"..."   # human-readable, used in playthroughs and debugging

  def is_terminal(self):
    return self._is_terminal

  def returns(self):
    return [score_p0, score_p1]   # total return per player, valid at any point

  def __str__(self):
    return board_as_text   # debug rendering; make it good, you'll stare at it a lot
```

## 5. Variant delta: chance events

Set `chance_mode=EXPLICIT_STOCHASTIC` and `max_chance_outcomes` in GameInfo. Then:

- `current_player()` returns `pyspiel.PlayerId.CHANCE` whenever randomness must resolve next (e.g. before dealing, after a "roll dice" action).
- Implement `chance_outcomes(self)` returning `[(action_id, probability), ...]` — probabilities summing to 1. Only valid at chance nodes.
- `_legal_actions` at a chance node returns the outcome ids (the framework handles this if `chance_outcomes` is implemented, but Kuhn poker also returns sorted outcome ids there for safety).
- `_apply_action` receives the sampled outcome id like any other action; branch on `self.is_chance_node()` inside it.

Design tip for dice games: model "roll" as a chance node *between* player decisions rather than embedding randomness inside `_apply_action`. Implicit randomness breaks tree-based algorithms and reproducibility.

## 6. Variant delta: imperfect information

Set `information=IMPERFECT_INFORMATION`. The heavy lifting moves to the observer:

- The **information state** must satisfy perfect recall: everything the player has seen *and done* so far. The standard construction is private info + full public action sequence (Kuhn: `f"{my_card}{betting_history}"`).
- The **observation** need only capture the current snapshot from the player's point of view.
- `make_py_observer` must branch on `iig_obs_type`: `perfect_recall=True` → information-state observer; otherwise → observation observer. Kuhn poker's observer takes `iig_obs_type` in its constructor and assembles the tensor from configurable pieces — read it before building your own.
- If two histories that differ in opponent-private info produce *different* information-state strings for a player, CFR's information sets fracture and exploitability numbers become meaningless. Test this property explicitly.

## 7. Variant delta: simultaneous moves

Set `dynamics=SIMULTANEOUS`. Then:

- `current_player()` returns `pyspiel.PlayerId.SIMULTANEOUS` at joint-decision nodes.
- Implement `_apply_actions(self, actions)` (plural) taking one action per player; `_legal_actions(player)` is still per-player.
- Per-step payoffs: set `reward_model=REWARDS` and implement `rewards()` (since last transition) alongside `returns()` (cumulative).
- If an algorithm only supports sequential games, wrap with `pyspiel.load_game_as_turn_based("python_my_game")` or the `turn_based_simultaneous_game(game=...)` string transform instead of redesigning the game.

## 8. The Observer

The observer protocol is three members: `self.tensor` (flat float32 numpy array), `self.dict` (named, shaped views onto the same memory), and two methods:

```python
class MyGameObserver:
  def __init__(self, params):
    shape = (planes, rows, cols)
    self.tensor = np.zeros(np.prod(shape), np.float32)
    self.dict = {"observation": np.reshape(self.tensor, shape)}

  def set_from(self, state, player):
    obs = self.dict["observation"]
    obs.fill(0)
    # encode state from `player`'s point of view (one-hot planes work well)

  def string_from(self, state, player):
    return ...  # textual equivalent
```

The dict views and `self.tensor` share memory — write through the shaped view, never reassign `self.tensor`.

## 9. Registration and loading

End the module with `pyspiel.register_game(_GAME_TYPE, MyGameGame)`. After the module is imported once, `pyspiel.load_game("python_my_game")` works everywhere, including from C++-side algorithms. In a standalone project (not the open_spiel repo), just import your module before calling `load_game`, or instantiate `MyGameGame()` directly.
