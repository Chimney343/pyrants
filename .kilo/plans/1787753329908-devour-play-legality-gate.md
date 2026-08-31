# Play-Legality Gate for Mandatory Devour Costs

## Problem

Cards whose on-play effect contains a **mandatory** devour (`op: "devour_cost"` / `"devour"`, `optional: false`) can currently be played even when the devour source zone is empty:

- `rules.c:230-236` (PHASE_MAIN move generation) emits a `MOVE_PLAY_CARD` for **every** card in hand — no cost-payability check.
- After play, `generic_runtime.c:394-409` (`auto_resolve_pending_generic`) auto-skips **any** selection action whose target enumeration returns 0 — the `nc == 0` branch is not conditioned on `action->optional`. The mandatory cost is silently waived and the payoff fires for free (e.g. Balor's supplant+deploy, Marilith's 5 power, Zuggtmoy's 3 influence).

Affected catalog cards (mandatory devour, empty-able source zone): `balor`, `demogorgon`, `glabrezu`, `marilith`, `mind_flayer` (devour in **both** modal options → unavoidable), `orcus`, `succubus` (hand); `zuggtmoy` (inner_circle); `carrion_crawler` (market). The fix is a **generic mechanism**, not card-specific special cases.

## Mechanism Design

**Rule:** a `MOVE_PLAY_CARD` for hand slot `i` is legal only if every *unavoidable, mandatory* devour cost of that card would have at least one legal target in the post-play state (post-play = hand with slot `i` removed).

**Per-action satisfiability** — a devour action is *payable* iff:

| Source zone (`metadata.source_zone`, else `target_scope`) | Payable when | Notes |
|---|---|---|
| `hand` (default) | `hand_count − 1 ≥ required_qty` (excluding the played slot) | `[balor, balor]` → playable (other copy is a legal target); `insane_outcast` counts as a legal target (sel_devour offers it; apply_devour routes it to supply) |
| `inner_circle` | `inner_circle_count ≥ required_qty` | zuggtmoy |
| `market` | `market.row_count ≥ required_qty` | carrion_crawler |
| `market` + `requires_last_selected_market_slot` | always (dependent selection) | ulitharid — matches the existing `depends_on_prior` convention in option viability (`generic_runtime.c:1094-1105`) |
| `played_self` | always (the played card itself is the target) | wraith, skeletal_horde, flesh_golem, cultist_of_myrkul, minotaur_skeleton |

- `required_qty` = `quantity_kind == QUANT_FIXED ? max(quantity_value, 1) : 1` (all current catalog entries are 1).
- Only `devour` / `devour_cost` ops are gated. Target ops (`assassinate_troop`, `supplant_troop`, `deploy_troops`, …) intentionally keep their documented partial-resolution semantics ("resolving as many as possible") — they are effects, not costs.

**Card-level aggregation** (over `card->execution`, `state.h:78-87`):

- `EXEC_SEQUENCE` (and `EXEC_REPEAT`): card payable iff **every** mandatory devour action in `execution.actions` is payable.
- `EXEC_MODAL` / `EXEC_REPEAT` with options: card payable iff **at least one option** has no unpayable mandatory devour. Options that are individually blocked are already greyed out post-play by the existing option-viability check (`generic_runtime.c:1079-1118`) — e.g. Wight option 2 with empty hand. Mind Flayer (devour in both options) becomes unplayable when the post-play hand is empty.
- Unknown/missing execution kind → payable (never false-block).

**Move semantics: omit, don't label.** The blocked play move is **not emitted** by `engine_legal_moves` (truly illegal), and `apply_play_card` rejects a directly-submitted blocked move. Rationale:

- `openspiel_pyrants/action_encoding_c.py:13` — "every action in `legal_actions()` has to be applicable"; placeholder moves must never reach OpenSpiel.
- `interface/game_viewer.py:1845-1850` — the viewer only submits a hand-card play if a matching `play_card` legal move exists; omission already yields correct unplayable behavior (click is a no-op, card absent from the legal-move list).
- `MoveData.play_card` (engine_bindings.py:280) has no spare field to carry an "unavailable" tag; the existing grey-out channel exists only for `resolve_generic` moves.
- Bots/MCTS/simulations/scenario_search consume `legal_moves()` — a filtered list is correct everywhere with zero adapter changes.

## Implementation Tasks

### 1. `engine_c/selection.c` — devour target counter (pure)

Add and export via `engine_c/selection.h`:

```c
/* Count legal devour targets for `action`'s source zone, excluding hand slot
 * `exclude_hand_index` (pass -1 when not excluding). Pure read; mirrors
 * sel_devour's zone semantics. Returns -1 for dependent-selection devours
 * (requires_last_selected_market_slot) and self-devours (played_self) —
 * always satisfiable. */
int devour_target_count(const GameState *state, Sym player_id,
                        const CardAction *action, int exclude_hand_index);
```

- Resolve zone exactly like `sel_devour` (`selection.c:711-783`): `metadata.source_zone` → fallback `target_scope`; zone strings `market` / `inner_circle` / `played_self` / default `hand`. Do **not** modify `sel_devour`.
- `market` + `requires_last_selected_market_slot` → return -1 (dependent). `played_self` → return -1 (always satisfiable).
- Caller resolves: `count < 0` → payable; else compare against `required_qty`.

### 2. `engine_c/generic_runtime.c` — card-level gate (pure)

Add `#include "selection.h"` and:

```c
/* True iff playing `card` from hand slot `hand_index` leaves every
 * unavoidable mandatory devour cost payable. Pure read. */
int card_play_devour_costs_payable(const GameState *state, Sym player_id,
                                   const CardDefinition *card, int hand_index);
```

- Iterate `card->execution` per the aggregation rules above (sequence: `execution.actions/action_count`; modal: `execution.options[i].actions/action_count`).
- An action is a gated devour iff `op ∈ {devour, devour_cost}` **and** `!optional` **and** `devour_target_count(...) >= 0` **and** count `< required_qty` → unpayable.
- Export in `engine_c/generic_runtime.h` (rules.c already includes it).

### 3. `engine_c/rules.c` — hook the gate in both directions

- **Move generation** (PHASE_MAIN loop, `rules.c:228-237`): before emitting `MOVE_PLAY_CARD` for hand slot `i`, look up `card_by_id_state(state, hand[i])`; skip emission when `!card_play_devour_costs_payable(state, player_id, cd, i)`.
- **Apply defense** (`apply_play_card`, `rules.c:275-314`): immediately after the `played != card_id` check (before mutating the hand), look up the `CardDefinition` and `return NULL` when `!card_play_devour_costs_payable(state, player_id, cd, hand_index)`. This makes replayed/directly-submitted illegal plays fail loudly instead of silently waiving the cost, and guarantees legal-gen and apply can never diverge (same predicate).

No changes needed in bindings, viewer, OpenSpiel wrapper, or Python session layer — they all consume `engine_legal_moves`.

### 4. C tests — `engine_c/tests/test_generic_actions.c` (extend)

Follow the existing struct-level conventions in that file (`intern_init`, memset `CardAction`, assert, `intern_destroy`):

- `devour_target_count`: hand zone with/without `exclude_hand_index` (incl. duplicates and `insane_outcount` counting as a target), inner_circle zone, market zone, `played_self` → -1, `requires_last_selected_market_slot` → -1, zone fallback from `target_scope` when metadata absent.
- `card_play_devour_costs_payable`: sequence card with hand-devour (balor-like: 1-copy hand → 0, extra card → 1), modal all-options-blocked (mind_flayer-like) vs partially blocked (wight-like → still playable), optional devour ignored (cult_fanatic-like), unknown execution kind → playable.
- Add the tests to `main()` in the file; `compile.bat`/`Makefile` pick the file up automatically (no build-script change).

GameState-dependent cases are covered by the Python binding tests below (state construction via ctypes in C is unnecessarily heavy).

### 5. Python binding tests — new `tests/c_engine/test_devour_play_gate.py`

Use `tests/c_engine/card_test_helpers.py::make_card_test_session` (sets `PHASE_MAIN`, bespoke hand/inner_circle) and the access patterns from `tests/c_engine/test_card_cult_fanatic.py`:

1. **Hand devour, singleton hand → ILLEGAL:** for each of `balor`, `demogorgon`, `glabrezu`, `marilith`, `mind_flayer`, `orcus`, `succubus` (parametrized): `hand={"p1": [card]}` → no `play_card` move for that card in `session.legal_moves()`; `end_main_phase` still present (game not stuck).
2. **Hand devour, extra card → LEGAL:** `hand={"p1": ["balor", "noble"]}` → play move exists; submit it → pending generic devour targets are exactly `["noble"]` (devour not skipped: cost actually charged).
3. **Duplicates:** `hand={"p1": ["balor", "balor"]}` → playable.
4. **Inner circle (zuggtmoy):** `hand=["zuggtmoy"]`, `inner_circle=[]` → not playable; `inner_circle=["noble"]` → playable, devour target is `noble`.
5. **Modal partially blocked (wight):** `hand=["wight"]` → still playable; after play, option_2 is tagged unavailable (existing behavior preserved).
6. **Self-devour unaffected (skeletal_horde / wraith):** singleton hand → playable.
7. **Apply-time rejection:** capture the `play_card` CMoveWrapper for `balor` from a 2-card session; in a fresh singleton-hand session, `session.submit_move(that_move)` raises/fails (illegal move rejected at apply).

### 6. Validation

```
just build-c          # rebuilds DLL + runs C tests (incl. new ones)
just test-c
just test-c-python    # new test_devour_play_gate.py + existing card suites
just test             # full pytest suite (scenario replays, bindings)
just openspiel-test   # legal-action mask consistency
ruff check .
```

Rebuild (`just build-c`) before any Python run — bindings load `engine_c.dll`.

## Risks & Compatibility

- **Historical replays/scenarios** containing plays that exploited the waived cost will now fail at apply. Such plays were exercising the bug; this is the intended semantic change. `just test` will surface any test fixtures that need hand adjustments (most card-test fixtures deal 5-card hands, so devour targets exist).
- **Behavioral change for bots/MCTS**: blocked play moves disappear from the action space (never appear as legal). No crash path — the action simply doesn't exist.
- **`scenario_search.py`** (`playable_now` detection) automatically stops considering empty-source devour plays — desired.
- **Purity**: both new functions are pure reads on `GameState`/`CardDefinition`; no I/O, no mutation. Engine purity rule preserved.
- **False-blocking risk** is contained by the conservative defaults: unknown execution kind, `played_self`, and dependent-selection devours are all treated as payable.

## Out of Scope / Follow-ups

- Generalizing the gate to *all* mandatory selection actions (e.g. modal cards whose every option is blocked for non-devour reasons, or market `play_card` actions with no qualifying card) — would change playability of many cards whose partial-resolution semantics are documented as intended. Separate decision, separate plan.
- UI affordance explaining *why* a hand card is unplayable (grey-out rendering in `game_viewer.py`). Current behavior: card click is a no-op and the move is absent from the legal-move list.
- Updating the soft-lock audit script (`scripts/find_devour_softlock_cards.py`, designed earlier) to consume the new gate as the authoritative payability check.
