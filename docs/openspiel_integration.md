# OpenSpiel Integration

pyrants is registered as `python_pyrants` in OpenSpiel via the
`openspiel_pyrants/` package. Two-player base game with the base board
(`tyrants_of_the_underdark.json`), no scenarios, no hidden-information observer
in this first pass.

## Quick Start

```python
import openspiel_pyrants
import pyspiel

game = pyspiel.load_game("python_pyrants")
state = game.new_initial_state()

# Chance node: pick a shuffle seed
assert state.is_chance_node()
outcomes = state.chance_outcomes()  # 1000 uniform outcomes
state._apply_action(42)  # or sample from outcomes

# Play
print(state.legal_actions())  # 0..N−1, sorted
while not state.is_terminal():
    action = state.legal_actions()[0]
    state._apply_action(action)

print(state.returns())  # [float, float], sums to 0
```

Or via the CLI:

```bash
just openspiel-smoke
just openspiel-test
```

## Game Classification

| Property    | Value                      |
|-------------|----------------------------|
| Dynamics    | SEQUENTIAL                 |
| Chance      | EXPLICIT_STOCHASTIC        |
| Information | IMPERFECT_INFORMATION       |
| Utility     | ZERO_SUM                   |
| Reward      | TERMINAL                   |
| Players     | 2 (min 2, max 2)           |

## Action Encoding

All moves are encoded as integers `[0, num_distinct_actions)` per state.
`num_distinct_actions = 1024` (power of 2, upper bound of ~756 move instances).

The per-state bijection is computed by `openspiel_pyrants.action_encoding`:
1. Call `engine.rules.legal_moves(state)`.
2. Sort moves deterministically (JSON dump, excluding player_id).
3. Assign ids `0..N−1`.

`action_to_move(state, id)` and `move_to_action_id(state, move)` provide the
reverse mapping. Legal actions are always sorted ascending, and the list is
never empty at non-terminal decision nodes.

## Chance Model

One chance node at game start selects a shuffle seed `[0, 999]` with uniform
probability. The seed determines all deck shuffles deterministically via
`(seed << 16) ^ counter`. No random events after the initial seed.

`max_chance_outcomes = 1000`.

## Returns

Zero-sum: `returns() = [score(p0) − score(p1), score(p1) − score(p0)]`.
Bounded by `[−200, 200]`. Mid-game returns use current player scores.
Terminal returns use `compute_final_scores`.

`max_game_length = 4096` (decision nodes only).

## Engine Refactor

`engine/state.py` no longer accepts `rng: Random`. All shuffles are
deterministic from `shuffle_seed` and a counter (`_shuffle_deck` helper,
same pattern as `_reshuffle_discard_into_deck`). `build_initial_game_state`
takes only `shuffle_seed: int`.

## What's Covered

- All 14 move types: PlayCard, EndMainPhase, Assassinate, Deploy, Recruit,
  ReturnSpy, ActivateCardAbility, DeclineCardAbility, PromoteCard, SkipPromote,
  ResolveEndOfTurn, ResolveCleanup, ResolveGenericChoice.
- Full cleanup phase with deterministic reshuffles.
- Terminal detection and scoring.

## What's Not Covered (Deferred)

| Item | Path forward |
|------|-------------|
| 4-player support | Pass `player_ids` as a colon-separated list. Adjust `num_distinct_actions` and `utility_sum`. |
| Scenario injection | Add `scenario_path` parameter; resolve a fixed chance action to "load scenario N". |
| C++ port | Use the Python playthrough as regression oracle. |
| serialize=True in API test | C++ deserialization path on Windows bypasses Python-level `__init__`; the lazy-init guard in `get_player_ids()` handles the attribute access but full round-trip needs `__reduce__`/`__getstate__` override. |
| Information-state tensors | Set `provides_information_state_tensor=False`. The IS-MCTS bot only requires string keys. |
| Observation/perception split for RL | `observation_string` currently mirrors `information_state_string`. Split when RL agents need distinct observation tensors. |

## IS-MCTS Integration

The `scripts/run_ismcts.py` runner drives the stock
`open_spiel.python.algorithms.ismcts.ISMCTSBot` against `python_pyrants`.

### What was added

| Module | Purpose |
|--------|---------|
| `engine/player_view.py` | Pydantic models for `PublicView` (visible to both players) and `PrivateView` (public + observing player's hand, deck size, etc.) |
| `openspiel_pyrants/observer.py` | `PyrantsObserver` — returns `PrivateView` JSON from `string_from` |
| `openspiel_pyrants/determinization.py` | `determinize_opponent_hidden_zones` — reshuffles the opponent's hand/deck/discard for IS-MCTS determinization |
| `openspiel_pyrants/state.py` | Added `information_state_string`, `observation_string`, and `resample_from_infostate` |
| `openspiel_pyrants/game.py` | Flipped `provides_information_state_string` / `provides_observation_string` to `True`; returns `PyrantsObserver` |
| `scripts/run_ismcts.py` | Headless IS-MCTS runner with CLI control, per-game `replay.json` + `decisions.jsonl` + `summary.json`, and cross-run `summary.csv` / `summary.md` |

### How information-state strings work

The `information_state_string` prefixes the game history (from `history_str()`) onto
the observing player's `PrivateView` JSON, separated by `||`. This ensures perfect
recall: two states at different nodes in the game tree produce distinct keys.

**Performance note:** the string is only computed once per actual decision node
(as the search-tree root key). The IS-MCTS simulation loop does *not* call
`information_state_string` — it only uses `legal_actions()` and `apply_action()`.

### Determinization

`resample_from_infostate(player, rng)` clones the current state (preserving
history), then reshuffles the opponent's hand/deck/discard using Fisher-Yates
shuffle driven by the bot's RNG. The observing player's hand and deck order
are preserved exactly. The public view is unchanged.

### Running

```bash
just ismcts num_sims=200 num_games=4 seed=42 output_dir=artifacts/ismcts
just ismcts-quick    # 50 sims, 2 games (fast proof)
```

Output lands in `artifacts/ismcts/` and follows the schema documented in
the plan file `.kilo/plans/openspiel-ismcts-pyrants.md`. The replay JSON is
compatible with `interface/replay_viewer.py`.

## Testing

```bash
just openspiel-test    # pytest openspiel_pyrants/tests/ (9 tests)
just test              # pytest -q (full suite, 33 files including engine regression)
ruff check .           # no new lint regressions
```
