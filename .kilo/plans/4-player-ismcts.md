# Plan: 4-Player IS-MCTS Support

## Goal

Enable 4-player games in the IS-MCTS runner (`scripts/run_ismcts.py`) against
the `python_pyrants` OpenSpiel wrapper. Today the wrapper is hard-wired to
exactly 2 players; the engine itself already supports arbitrary `N` players
via `turn_order: list[str]` and `next_player_id()` rotation. Most of the work
is in the OpenSpiel adapter layer (`openspiel_pyrants/`).

This is a *de jure* generalization, not new rule work: 2- and 3-player
configurations must keep working bit-for-bit (same bot behaviour, same RNG
streams, same artifacts).

## Scope

| In scope | Out of scope |
|----------|-------------|
| `openspiel_pyrants/game.py` — generalize player count | Card balance / new effects |
| `openspiel_pyrants/state.py` — N-player returns, multi-opponent determinization, generalise `current_player` range | `engine/rules.py` rules work (already N-agnostic) |
| `openspiel_pyrants/determinization.py` — multi-opponent resampling | UI viewer changes (already supports 2–4) |
| `openspiel_pyrants/observer.py` — no real change (already per-player) | New UI/CLI affordances |
| `scripts/run_ismcts.py` — N bots, multi-opponent summary, multi-deck market distribution | Scenario regeneration for 4-player |
| `openspiel_pyrants/tests/test_resample.py` + new tests | Replay viewer changes |
| GameInfo utility range / `max_game_length` | C++ rewrite |

## Findings From Recon

- `engine/state.py:895-922` (`build_initial_game_state`) iterates `turn_order`
  for any iterable; `next_player_id` (phases.py:9) cycles `(i+1) % N`. The
  engine is already N-player safe.
- `engine/rules.py:190-199` `is_terminal()` uses `any(player.barracks == 0)`
  over `state.players.values()` — N-agnostic.
- The OpenSpiel wrapper hardcodes:
  - `game.py:39-40` `min/max_num_players = 2`
  - `game.py:58` `num_players = 2`
  - `state.py:104-109` `returns()` only sums `p0` vs `p1`; `ZERO_SUM` declared
  - `state.py:117-118` `__str__` only shows p0/p1
  - `determinization.py:72-79` resamples "the opponent" by taking the first
    non-observing id (wrong for N>2 — all opponents must be sampled)
  - `scripts/run_ismcts.py:207-226` `bots = [...]` list literal of length 2;
    `state.py:255` guard `if cp < 0 or cp >= 2: break` truncates the game
- The IS-MCTS bot is identical for every player; we just need N copies of it
  with disjoint RNG streams.
- The market only needs *two* deck halves (the canonical Tyrants 4-player rule
  is to share the same combined market between all players); this is already
  what `combine_two_deck_market_setup` produces. No market setup change.
- `game_viewer.py:282,456,738` already supports `player_count` ∈ {2, 3, 4}
  via `player_ids = [f"p{index}" for index in range(1, player_count + 1)]`.
  We will reuse that same naming for OpenSpiel.
- `data/decks/base_setup.json` has `market_row_size: 6`. The 4-player rule
  in the official game uses the same market row; no data change.

## Design Decisions

### 1. Player count: 2–4, controlled by a single param

Add `num_players` (int) to the `PyrantsGame` params. Default 2 (preserve all
existing call sites and tests). The `player_ids` colon-string param is
deprecated in favour of `num_players`; the constructor derives
`p1, p2, …, pN` internally. This matches `game_viewer.py`'s convention and
removes a footgun (mismatched lengths between the two params).

### 2. Game type flags: `ZERO_SUM` → `GENERAL_SUM`

Tyrants with 3+ players is **not** zero-sum: the score difference between
any two players is not the negation of another's. Set
`utility=pyspiel.GameType.Utility.GENERAL_SUM` and `utility_sum=0.0` for
`num_players=2` (existing behaviour: `p0 - p1` and `p1 - p0` still sum to 0),
or **leave it as zero-sum when `num_players==2`** for the most conservative
backward-compat path.

**Decision (ask user — see Open Questions):** keep `ZERO_SUM` for N=2 and
switch to `GENERAL_SUM` for N>2, OR always use `GENERAL_SUM` with
`utility_sum` reflecting true totals.

Recommended: **always `GENERAL_SUM`, but `utility_sum=0.0` only when N==2**
(matches today's invariant). For N>2, leave `utility_sum=0.0` (the field
documents the "best-case" sum; for general-sum games OpenSpiel doesn't
enforce it). This keeps `sum(returns()) == 0` for 2-player games (test
`test_ismcts_smoke.py:88` still passes) while being honest about N>2.

### 3. `returns()`: N entries, sum-zero only when N==2

```python
def returns(self):
    if self._engine is None:
        return [0.0] * self.num_players
    pids = self._game.get_player_ids()
    scores = compute_final_scores(self._engine) if is_terminal else current_scores
    base = scores[pids[0]] - sum(scores[pid] for pid in pids[1:])  # if N==2
    # For N>2: report each player's score as the return, so
    # sum(returns()) is the total VP at the table; OpenSpiel doesn't
    # require zero sum for general-sum games.
```

Document this in a docstring; add a test for both cases.

### 4. Determinization: resample *all* opponents independently

In `determinization.py`, replace the single-opponent loop with a loop over
`[pid for pid in turn_order if pid != observing_pid]`, Fisher-Yates shuffling
each opponent's combined hidden multiset independently with the same RNG.
The IS-MCTS bot already passes one RNG per call; calling `rng.shuffle()`
multiple times advances the stream deterministically, so the bot's randomness
contract is preserved. The current test
(`test_resample.py:97,111` `opponent_id = state._game.get_player_ids()[1 - player]`)
will need a rewrite — see Test Plan.

### 5. IS-MCTS runner: N bots with disjoint RNGs

In `scripts/run_ismcts.py`:

- Replace the `[ISMCTSBot(...), ISMCTSBot(...)]` list with a comprehension
  over `range(num_players)`; seed each with
  `np.random.RandomState(seed + gi*2 + pid)`.
- Replace `if cp < 0 or cp >= 2: break` with
  `if cp not in range(num_players): break` — covers TERMINAL, CHANCE, and
  SIMULTANEOUS.
- `winner` resolution: `ret = state.returns()`. For N==2 keep the diff
  framing; for N>2 report `argmax(ret)` and the high score.
- The `outcome` field in the summary needs an N-way split
  (`p0_win | p1_win | … | pN_minus_1_win | tie`).
- `_summary_md_path` table: append extra `outcome` columns or collapse
  to a generic "winner=pK" string. Recommend a single column.

### 6. No data/setup changes

`base_setup.json`, all `data/decks/*.json`, board JSONs, the card catalog —
none need edits. The 4-player variant shares the same 80-card combined
market the 2-player game already uses (per official rules). The wrapper
just hands N copies of the starter deck to N players.

## Implementation Steps

1. **Add `num_players` param to `PyrantsGame`**
   - `game.py`: default `_DEFAULT_PARAMS["num_players"] = "2"`; cast to int;
     validate `2 <= n <= 4`; derive `_player_ids` from
     `[f"p{i}" for i in range(1, n+1)]`.
   - Update `parameter_specification` and `min/max_num_players`.
   - Drop or deprecate the `player_ids` colon-string param (keep for
     backward compat: if explicitly passed, use it; else derive from
     `num_players`).
   - Update `_GAME_INFO` and `_GAME_TYPE` `num_players` field dynamically
     from resolved params. (Currently both are module-level constants —
     lift them to per-instance `__init__` values, which is allowed for
     `pyspiel.Game`. Verify with the C++ binding docs.)

2. **Generalize `PyrantsState.returns()` and `__str__`**
   - Replace hardcoded `player_ids[0]/[1]` with iteration over
     `self._game.get_player_ids()`.
   - For N==2 preserve `returns = [s0 - s1, s1 - s0]` (sum=0 invariant).
   - For N>2 return raw scores per player (`returns[i] = score_i`).
   - Update `__str__` to format N player lines.

3. **Generalize `determinization.py`**
   - Loop over all non-observing players, reshuffle each one's hidden multiset
     with the same RNG.
   - Update docstring.

4. **Update `scripts/run_ismcts.py`**
   - Load `num_players` from `params["num_players"]` (parse from
     `load_params`).
   - N-bots construction with disjoint RNGs.
   - Generalize winner/outcome, summary stats, and the markdown table.
   - Add `--num-players` CLI flag (default 2).

5. **Update tests**
   - `test_pyrants_register.py`: parametrize on `num_players ∈ {2, 3, 4}`.
   - `test_resample.py`: replace the single-`opponent_id` assertion with
     a loop that verifies *every* non-observing player's hidden multiset
     is reshuffled and the observing player's is preserved.
   - New `test_state_n_player.py`: assert `len(returns()) == n` and
     `sum == 0` for n==2 only.
   - `test_ismcts_smoke.py`: parametrize on `num_players ∈ {2, 3, 4}`.
     **All parametrizations run in CI** (per user direction). Keep
     `--num-sims 5 --num-games 1` budget so each run stays under
     ~2 minutes. Remove or repurpose the `PYRANTS_SKIP_ISMCTS` skip
     guard so the 2-player default still skips if the env var is set
     (preserves developer escape hatch), but parametrized 3/4-player
     cases run unconditionally.

6. **Engine-purity + lint**
   - Run `pytest -q` (all tests).
   - Run `ruff check .`.

7. **Manual smoke (local, not in plan)**
   - `python -m scripts.run_ismcts --num-players 4 --num-sims 10 --num-games 1 --seed 7 --output-dir artifacts/ismcts_4p`
   - Confirm `summary.csv`, `summary.md`, and per-game `replay.json` exist;
     check `replay_context.player_ids == ["p1", "p2", "p3", "p4"]`.

## Files To Edit (Exact)

| File | Change |
|------|--------|
| `openspiel_pyrants/game.py` | Add `num_players` param, derive player ids, dynamic GameInfo |
| `openspiel_pyrants/state.py` | N-player returns, N-player `__str__` |
| `openspiel_pyrants/determinization.py` | Multi-opponent resampling |
| `scripts/run_ismcts.py` | N bots, N-aware winner/outcome, `--num-players` flag |
| `openspiel_pyrants/tests/test_pyrants_register.py` | Parametrize on N |
| `openspiel_pyrants/tests/test_resample.py` | Loop over opponents |
| `openspiel_pyrants/tests/test_ismcts_smoke.py` | Parametrize on N (most skipped) |
| **new** `openspiel_pyrants/tests/test_state_n_player.py` | N-player returns shape |
| `docs/openspiel_integration.md` | Update 4-player-support section (now implemented) |
| `docs/openspiel-architecture.md` | Note the dynamic GameInfo |

## Confirmed Choices

1. **Utility model**: hybrid — `ZERO_SUM` when `num_players==2`,
   `GENERAL_SUM` when `num_players > 2`. `utility_sum=0.0` always.
2. **CLI default**: `--num-players` defaults to **2**.
3. **Determinization**: resample **all** non-observing players' hidden
   zones with the same RNG stream.
4. **CI scope**: the parametrized 2/3/4-player smoke tests **all run in CI**
   (no `PYRANTS_SKIP_ISMCTS` guard for the parametrized cases). Update
   `test_ismcts_smoke.py` so each parametrization runs end-to-end against
   a 2-game, 5-sims budget.

## Verification Checklist

- [ ] `pytest -q` passes (existing 32 test files untouched; new test passes)
- [ ] `ruff check .` passes
- [ ] `python -m scripts.run_ismcts --num-sims 10 --num-games 1` (2-player)
      produces a valid summary (regression)
- [ ] `python -m scripts.run_ismcts --num-players 4 --num-sims 10
      --num-games 1` produces a valid 4-player summary
- [ ] `state.returns()` length matches `num_players` for 2, 3, 4
- [ ] For 2-player, `sum(returns()) == 0.0` (preserves smoke test)
- [ ] Determinization test passes for 2, 3, 4 players
- [ ] `engine/purity` test still passes (no I/O leaked into `engine/`)
