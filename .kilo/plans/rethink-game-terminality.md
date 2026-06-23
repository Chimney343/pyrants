# Plan: Re-think Game Terminality (End-of-Round Kill Switches)

## Problem

The C engine's `engine_is_terminal()` (`engine_c/rules.c:714-720`) checks
`barracks == 0` and `market.deck_count == 0` **immediately**. When a card
effect (like Red Dragon's `supplant_troop`) reduces barracks to 0 mid-card,
`is_terminal()` flips to true, `session.legal_moves()` short-circuits to `[]`,
and the card's remaining actions (`return_spy`, `grant_vp`) are silently
dropped. The game stalls.

The C engine **already implements** the barracks-fallback deploy rule
(`rules.c:338`: `if (ps->barracks == 0) { ps->score += 1; return state; }`),
which only makes sense if the game **continues** after barracks hits 0. The
current immediate-termination is self-contradictory.

## New Rule (per user spec)

Two **kill switches** exist:
1. The market deck is empty.
2. Any player's barracks reaches 0.

When a kill switch triggers, the game does **not** end immediately. It
continues until the **end of the current round** (the last player in turn
order finishes their cleanup phase), then the game ends.

A round = all players (p1 → p4) each taking a full turn (main → end-of-turn →
cleanup).

## Design: No-Flag Boundary-Check Approach

Both kill-switch conditions are **monotonic** (barracks only decreases, market
deck only shrinks). Once triggered, they stay triggered. So we don't need a
flag — we check the conditions at the **round boundary** in `advance_phase()`.

### Change 1: `engine_is_terminal()` — remove immediate checks

`engine_c/rules.c:714-720`:

```c
// BEFORE
int engine_is_terminal(const GameState *state) {
    if (state->phase == PHASE_GAME_OVER) return 1;
    if (state->market.deck_count == 0) return 1;
    for (int i = 0; i < state->player_count; i++)
        if (state->players[i].barracks == 0) return 1;
    return 0;
}

// AFTER
int engine_is_terminal(const GameState *state) {
    return state->phase == PHASE_GAME_OVER;
}
```

This is the fix for the Red Dragon stall: `is_terminal()` no longer flips true
mid-card, so `session.legal_moves()` returns the actual pending-generic moves.

### Change 2: `advance_phase()` — check kill switch at round boundary

`engine_c/phases.c:51-58` (CLEANUP branch):

```c
// AFTER
if (state->phase == PHASE_CLEANUP) {
    Sym next = next_player_id(state);
    if (next == state->player_ids[0]) {
        // Round boundary — check kill switches
        int kill = 0;
        if (state->market.deck_count == 0) kill = 1;
        for (int i = 0; i < state->player_count && !kill; i++)
            if (state->players[i].barracks == 0) kill = 1;
        if (kill) { set_game_over(state); return 0; }
        state->round_number++;
    }
    state->phase = PHASE_MAIN;
    state->current_player_id = next;
    memset(&state->resource_pool, 0, sizeof(ResourcePool));
    return 0;
}
```

The check fires only when wrapping from the last player back to the first
player (the round boundary). If any kill-switch condition is met, the game
ends instead of starting a new round.

### Change 3: Python engine (deprecated, for parity)

Mirror the same two changes in the deprecated Python engine to keep both
engines consistent (avoids confusing test failures in
`test_terminal_detection` and the OpenSpiel wrapper):

- `engine/rules.py:190-199` — `is_terminal()`: remove barracks/market checks,
  only check `phase == GAME_OVER`.
- `engine/phases.py:58-67` — `advance_phase()` CLEANUP branch: add round
  boundary kill-switch check before `round_number += 1`.

### Change 4: Docs — `docs/game_manual.md`

Update these sections to describe end-of-round termination:
- Line 67 (Barracks row): "When barracks reaches 0, the game ends" → end of round.
- Lines 178-180 (End Conditions): "ends immediately" → "ends at the end of the current round".
- Line 285 (flow diagram): update the GAME OVER condition text.
- Lines 318, 320 (strategy tips): update endgame awareness / barracks fallback.

## TDD Test Plan

All tests use the C engine via Python bindings (`CSession`). Tests go in
`tests/c_engine/test_terminality.py` (new file).

### Test 1 (RED → GREEN): Red Dragon scenario — game continues after barracks→0

```python
def test_red_dragon_supplant_last_troop_does_not_terminate():
    """When Red Dragon's supplant reduces barracks to 0, the game must NOT
    be terminal — remaining card effects (return_spy, grant_vp) must resolve."""
    session = CSession.load("data/scenarios/random_card_generation/red_dragon_seed_666.json")
    # Play Red Dragon
    # Apply supplant (barracks 1 → 0)
    # Assert: not is_terminal()
    # Assert: legal_moves() is non-empty (return_spy targets exist)
```

- **RED**: `is_terminal()` returns true (barracks==0) → assertion fails.
- **GREEN**: Change 1 (remove barracks/market from `engine_is_terminal`).
  Rebuild C engine. Test passes.
- This change alone does NOT break existing tests (no test asserts
  barracks==0 → immediate terminal; `test_terminal_detection` only tests
  `PHASE_GAME_OVER`).

### Test 2 (RED → GREEN): Game ends at round boundary when barracks==0

```python
def test_game_ends_at_round_boundary_when_barracks_zero():
    """After barracks hits 0, the game continues until the round completes,
    then becomes terminal."""
    # Create 2-player game, complete setup
    # Set p1.barracks = 0 (simulate kill switch triggered)
    # Assert: not is_terminal() (mid-round)
    # Play through p1's remaining phases (end_main, eot, cleanup)
    # Play through p2's full turn (end_main, eot, cleanup)
    # At p2's cleanup → round boundary → GAME_OVER
    # Assert: is_terminal() is True
```

- **RED**: After Change 1, `is_terminal()` never returns true for barracks==0
  (no round boundary check yet) → final assertion fails.
- **GREEN**: Change 2 (add round boundary check in `advance_phase`).
  Rebuild. Test passes.

### Test 3 (RED → GREEN): Game ends at round boundary when market deck empty

Same structure as Test 2 but with `market.deck_count = 0`.

### Test 4 (optional): C engine unit test

Add `engine_c/tests/test_terminality.c` with:
- `test_barracks_zero_not_immediately_terminal`
- `test_round_boundary_ends_game_on_barracks_zero`

This locks in the behavior at the C level (source of truth).

## Implementation Steps (TDD order)

1. **Write Test 1** in `tests/c_engine/test_terminality.py`.
2. **Verify RED**: run test, confirm it fails because `is_terminal()` returns true.
3. **GREEN**: edit `engine_c/rules.c:714-720` — remove barracks/market checks.
4. **Rebuild C engine**: `just build-c`.
5. **Verify GREEN**: Test 1 passes. Run `just test-c-python` to check no regressions.
6. **Write Test 2** in the same file.
7. **Verify RED**: run test, confirm it fails (game never becomes terminal).
8. **GREEN**: edit `engine_c/phases.c:51-58` — add round boundary check.
9. **Rebuild C engine**: `just build-c`.
10. **Verify GREEN**: Test 2 passes.
11. **Write Test 3** (market deck empty variant). Verify RED → GREEN (Change 2 already covers this, test should pass immediately — if so, it's a regression guard, not a TDD driver; acceptable).
12. **Update Python engine** (`engine/rules.py`, `engine/phases.py`) for parity.
13. **Update docs** (`docs/game_manual.md`).
14. **Run full suite**: `ruff check .`, `just test`, `just build-c`, `just test-c-python`.

## Edge Cases & Risks

- **Loaded scenarios with barracks already 0**: The no-flag approach lets the
  current round play out, then ends at the next round boundary. This is
  consistent with the new rule (kill switch triggered, game ends at end of
  round). No deserialization changes needed.
- **Setup phase**: Barracks starts at 40; setup uses 1 troop. Kill switch
  during setup is near-impossible and would correctly defer to the first
  round boundary.
- **OpenSpiel wrapper**: Uses the engine's `is_terminal()`. After the update,
  the wrapper will correctly report non-terminal during the round and terminal
  after the round boundary. No wrapper changes needed.
- **Simulation loops** (`game_simulation.py`, `session.py`): Check
  `is_terminal()` first, then `legal_moves()`. With the new behavior, the
  simulation continues through the round and stops at the round boundary.
  No loop changes needed.
- **`engine_legal_moves`** (`rules.c:191`): Already only checks
  `PHASE_GAME_OVER`, not barracks/market. No change needed — it will
  correctly return pending-generic moves during the round.
- **Python engine parity**: The deprecated Python engine is updated for
  consistency but is not the primary target. If the user prefers to skip it,
  the C engine is fully self-sufficient.

## Files Changed

| File | Change |
|------|--------|
| `engine_c/rules.c` | `engine_is_terminal()`: remove barracks/market checks |
| `engine_c/phases.c` | `advance_phase()` CLEANUP: add round-boundary kill-switch check |
| `engine/rules.py` | `is_terminal()`: same removal (deprecated engine parity) |
| `engine/phases.py` | `advance_phase()` CLEANUP: same round-boundary check (parity) |
| `docs/game_manual.md` | Update end-condition descriptions (lines 67, 105, 178-180, 285, 318, 320) |
| `tests/c_engine/test_terminality.py` | New test file (Tests 1-3) |
| `engine_c/tests/test_terminality.c` | (Optional) C-level unit tests |
