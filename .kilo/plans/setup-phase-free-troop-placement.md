# Plan: Add SETUP phase with mandatory free troop placement before first hand

## Rule (per user)

Before any hand is dealt and before any player enters MAIN, **each player in turn order** gets exactly one mandatory action: place **one troop for free** on **any site** (routes excluded). Only after every player has placed their free troop does the first player draw 5 cards and enter MAIN. Subsequent players follow the existing draw-up pattern at the start of their first MAIN.

Order with two players, current_player = p1, turn_order = [p1, p2]:

1. SETUP, current=p1 → p1 places 1 free troop on a site.
2. SETUP, current=p2 → p2 places 1 free troop on a site.
3. CLEANUP-ish step (or a new `DRAW` micro-step) for p1: draw 5 cards.
4. MAIN, current=p1 → p1 plays turn normally (resource pool resets, etc.).
5. … existing turn flow for p1 … p2 … repeat.

## Design

### Phases

Reuse the existing `TurnPhase.SETUP` enum (currently dead code in `engine/state.py:25`). Add a new `TurnPhase.DRAW` value to handle the "draw 5 cards" transition that previously happened inside `build_initial_game_state` and inside `_apply_cleanup`. This makes the per-player first-turn draw an explicit, inspectable phase.

Final phase set:
- `SETUP` — only entered for the first turn of each player; legal moves are free `InitialPlacementMove`s targeting sites with empty slots. (Routes are illegal even if they have a free slot — sites only.)
- `DRAW` — draw 5 cards, then auto-advance. Resolves the first-turn draw that `build_initial_game_state` currently pre-applies. This is also where the `_apply_cleanup` post-discard draw can be unified later (out of scope for this change — keep `_apply_cleanup` drawing for now to limit blast radius).
- `MAIN`, `END_OF_TURN`, `CLEANUP`, `GAME_OVER` — unchanged.

`SETUP` is a per-player phase that fires exactly once per player at the very start of the game. The phase does **not** recur in later rounds.

### State changes

`engine/state.py`:

- Extend `TurnPhase` with `DRAW = "draw"`.
- Add a `pending_initial_placement: bool` flag on `GameState` (or, cleaner, a `setup_complete: set[str]` of player ids who have already placed). Using a `set` is the right call: it lets a 2-player and 4-player game both work without changing the loop, and it's stable against future variants (e.g. 5+ player). Default `set()`. (Frozen-by-default? No — `GameState` is mutable, so just `set[str] = Field(default_factory=set)`.)

`engine/phases.py`:

- Extend `advance_phase` to handle:
  - `SETUP` (per player) → advance to SETUP for next player, or if everyone has placed, advance to `DRAW` for the first player.
  - `DRAW` → draw 5 cards for the current player, then advance to `MAIN` (resource pool stays zero per existing main-phase contract).
- `DRAW` from `_apply_cleanup` is **not** in this change's scope (existing behavior preserved).

`engine/state.py` `build_initial_game_state`:

- Do **not** pre-draw 5 cards into the player's hand. Leave `hand=[]`.
- Set `phase=TurnPhase.SETUP`, `current_player_id=turn_order[0]`, `setup_complete=set()`.
- Still shuffle the deck (the same `_shuffle_deck` call) so the eventual draw is deterministic and the shuffle seed/counter contract is preserved. Just don't pop cards into `hand`.

`engine/rules.py`:

- Add a new move type `InitialPlacementMove(MoveBase)` with `move_type: Literal["initial_placement"] = "initial_placement"` and `target_node_id: str`. This is the "place one free troop on a site" action. It costs 0 power, 0 barracks is not consumed (barracks **is** decremented by 1 — the troop is real), 0 cards drawn, no hand limit changes.
- Wire it into the `Move` discriminated union in `engine/moves.py`.
- In `legal_moves`:
  - If `state.phase == TurnPhase.SETUP` and the current player is not in `setup_complete`: return one `InitialPlacementMove` per **site** node with at least one empty troop slot. (Routes and full sites are excluded.)
- In `apply`:
  - Handle `InitialPlacementMove`: validate target is a site, has an empty slot, in SETUP phase, current player not already placed. Place the troop (fill the first empty slot, decrement barracks by 1 — same body as the troop-placement branch of `_apply_deploy` minus the power check and the barracks=0 → score path, which is irrelevant since you must have barracks to place). Add player id to `setup_complete`. Then `advance_phase` to the next setup player, or to DRAW for player 0.
- In `legal_moves` and `apply`, add the `DRAW` branch:
  - `legal_moves` returns `[]` (or just an empty list — DRAW is auto-resolving, no player input).
  - `apply` for `DRAW` is invoked by `advance_phase` itself (the phase handler draws and advances), **not** by the player. No public move type needed for DRAW.

### Files to touch

1. `engine/state.py` — add `DRAW` enum value, add `setup_complete: set[str]` to `GameState`, change `build_initial_game_state` to start in `SETUP` with empty hands and shuffled decks.
2. `engine/moves.py` — add `InitialPlacementMove`, add to `Move` union.
3. `engine/phases.py` — extend `advance_phase` for `SETUP` and `DRAW`.
4. `engine/rules.py` — `legal_moves` SETUP/DRAW branches, `apply` SETUP/DRAW handling, `_apply_initial_placement` helper.
5. `engine/helpers.py` — small helper `_legal_initial_placement_node_ids(state, player_id)` returning sorted site node ids with at least one empty slot. (Keeps the rule for "sites only" in one place; `legal_moves` becomes a one-liner.)
6. `engine/__init__.py` — re-export `InitialPlacementMove` if other modules import from `engine`. (Check; only `engine.moves` re-export exists, so probably no change.)
7. `tests/test_setup.py` — update existing test that asserts `state.phase.value == "main"` and `len(state.players["p1"].hand) == 5`. The new behavior is `phase == "setup"`, `hand == []`, `setup_complete == set()`, and the hand is empty until DRAW resolves.
8. `tests/test_state_machine.py` and `tests/test_game_session.py` — likely the same hard-coded phase/hand assertions. Audit and fix.
9. New test file `tests/test_initial_placement.py`:
   - Initial state is SETUP, hand empty, no troops on map.
   - `legal_moves` returns exactly the SET of site node ids with an empty slot.
   - Routes and fully-occupied sites are excluded.
   - Applying an `InitialPlacementMove` places the troop, decrements barracks, marks the player placed.
   - After p1 places, the active player is p2 (still SETUP).
   - After p2 places, the active player is p1, phase is DRAW.
   - From DRAW, `advance_phase` (via a single internal call) puts p1 into MAIN with 5 cards in hand and resource pool reset.
   - `InitialPlacementMove` is rejected outside SETUP and on full/illegal nodes.
10. `docs/engine-status.md` and `docs/game_manual.md` — add a `2.0 Setup Phase` section to the manual ("each player places one troop on a site, free, before any hand is drawn") and bump the `Done` section of `engine-status.md` to reflect the new flow.

### OpenSpiel wrapper

`openspiel_pyrants/state.py:_legal_actions` calls `compute_action_map(self._engine)`, which already calls `engine.rules.legal_moves`. No code change needed — the SETUP-phase free-placement moves will flow through automatically. **Verify** with the existing openspiel test suite after the change.

### Things to double-check before implementing

- **Replay determinism.** Removing the pre-draw from `build_initial_game_state` will change the shuffle counter consumed by the first player (we used to pop 5 cards in `create_player_state`; now we just shuffle and don't pop). The counter is consumed at shuffle time, not at pop time, so this should be a no-op. Verify by running `tests/test_shuffle_determinism.py`.
- **Scenario fixtures.** `tests/scenario_helpers.py` and the saved scenarios in `data/scenarios/` may have hard-coded `phase == "main"` and a dealt hand. Audit and either regenerate or fix in place. The 125+ saved scenarios in `data/scenarios/` are JSON snapshots; they will need regeneration via the canonical scenarios script.
- **Scenario generation script** `scripts/regenerate_canonical_scenarios.py` (and the scenario-generation flow) goes through `build_initial_game_state`, so saved scenarios will pick up the new initial state automatically. Regenerate them as part of this change.
- **Documentation impact.** The `game_manual.md` currently describes the game starting in MAIN with the first turn being the first player's MAIN phase. Update §2 with a new `2.0 Setup Phase` subsection.

### Out of scope (explicit non-goals)

- Unifying `_apply_cleanup`'s post-discard draw with the new `DRAW` phase. (Noted as future work; the existing `CLEANUP` draw behavior is preserved.)
- Allowing players to skip the free placement. The rules make it mandatory.
- Refactoring `setup_complete` into a per-player counter for multi-troop setup. Single troop per the spec.
- Changing the OpenSpiel action-encoding upper bound (`num_distinct_actions`). The new `InitialPlacementMove` will be one of the `legal_moves` per state, which is already what the encoding supports.
