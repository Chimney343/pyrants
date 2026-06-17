# Comparison: `engine/` (Python) vs `engine_c/` (C)

Repo: pyrants. The Python `engine/` package is the deprecated reference engine; the C
implementation in `engine_c/` is the active, perf-oriented rewrite used by IS-MCTS.

This plan is a **read-only analysis**. It maps each module, flags semantic differences,
and lists the areas that most warrant scrutiny.

---

## 1. Top-level shape

| Concern            | `engine/` (Python)                            | `engine_c/` (C)                                                 |
|--------------------|-----------------------------------------------|------------------------------------------------------------------|
| Language           | Python 3.12+, Pydantic v2                     | C99, compiled to `engine_c.dll`; ctypes bindings in `bindings/`  |
| Module count       | 9 .py + 6 in `generic_runtime/`               | 20 .c/.h + 5 binding .py + 4 test .c                             |
| Source size (SLOC) | ~199 KB (state.py alone ~36 KB)               | C core ~190 KB + cJSON ~80 KB + Python bindings ~54 KB           |
| State model        | Pydantic `BaseModel`, mutable + COW clone     | Plain `struct`s, COW via `cow_*` helpers, `Arena` allocator       |
| Strings            | Native Python `str`                           | Interned `Sym` (uint32) — global `intern` table                  |
| RNG                | `random.Random((seed << 16) ^ counter)`       | xoshiro-style 4×64-bit `RNG` (`rng.h`)                            |
| Move union         | Pydantic discriminated union (`moves.py`)     | Tagged union (`Move` struct in `state.h`); constructors in `moves.c` |
| External API       | Pure functions: `legal_moves`, `apply`, …     | `engine_create_game`, `engine_apply`, … (DLL exports `engine_c.def`) |
| Python surface     | Direct function calls                         | `ce_api.py` / `engine_bindings.py` ctypes wrappers, swap via `PYRANTS_ENGINE=c` |
| Persistence        | None (Pydantic JSON via callers)              | `saveload.c` — JSON snapshot round-trip                           |
| I/O                | None — `tests/test_engine_purity.py` enforced | None — engine is pure; JSON load via cJSON (`loader.c`)           |

Both engines are pure (no I/O); the C engine keeps that property by routing all file
reads through `loader.c`/`saveload.c` at the C boundary, while the Python engine
relies on test-enforced purity.

---

## 2. Module-by-module mapping

| Python module                          | C counterpart                                                            | Notes |
|----------------------------------------|---------------------------------------------------------------------------|-------|
| `engine/state.py`                      | `state.h`, `state.c`                                                      | Types differ (Pydantic vs struct). Both expose COW accessors (`_cow_*` vs `cow_*`). |
| `engine/moves.py`                      | `moves.h`, `moves.c`                                                      | Python: discriminated `BaseModel` union. C: tagged union + factory functions. |
| `engine/phases.py`                     | `phases.h`, `phases.c`                                                    | Same phase order (SETUP→DRAW→MAIN→END_OF_TURN→CLEANUP→GAME_OVER). |
| `engine/scoring.py`                    | `scoring.h`, `scoring.c`                                                  | Same formula: site control + trophy + tokens + deck_vp + inner_circle_vp. |
| `engine/rules.py`                      | `rules.h`, `rules.c`                                                      | `legal_moves`/`apply`/`is_terminal`/`winner`. C inlines wrappers in `apply_effect_with_wrappers`. |
| `engine/helpers.py`                    | `helpers.h`, `helpers.c`                                                  | Effect registry (`_EFFECT_REGISTRY` vs `effect_registry[EFFECT_COUNT=16]`), placement, deploy, recruit, promote helpers. |
| `engine/generic_runtime/` (6 files)    | `generic_runtime.h`, `generic_runtime.c`                                  | Card-effect interpreter for sequence/modal_choice/repeat_choice. C has a single ~366-LOC file. |
| `engine/player_view.py`                | `player_view.h`, `player_view.c`                                          | PublicView + PrivateView projection. C view drops some Python-only fields. |
| `engine/errors.py`                     | None — C uses sentinel returns / `assert`                                  | `IllegalMoveError`, `RuleViolationError`, `MissingRuleImplementationError`, `UnknownCardEffectError` not represented in C. |
| `engine/__init__.py`                   | `engine_c.dll` exports (`engine_c.def`)                                   | Re-exports `apply/is_terminal/legal_moves/winner`. |
| (none)                                 | `arena.c`/`arena.h`, `intern.c`/`intern.h`, `rng.c`/`rng.h`, `cJSON.c`/`cJSON.h` | New C-only subsystems. |
| (none)                                 | `saveload.c`/`saveload.h`, `loader.c`/`loader.h`, `describe.c`, `view.c`  | New C-only utilities. |
| (none)                                 | `bindings/*.py` (5 files)                                                | ctypes wrapper layer for Python callers. |
| (none)                                 | `tests/test_*.c` (4 files) + `test_engine.c`, `test_game.c`, `test_generic.c`, `test_intern_c.c` | C-side unit tests. |
| (none)                                 | `profile_runner.c`, `build_profile/`                                      | Profiling binary. |

---

## 3. State representation — biggest semantic gap

**Python** — `GameState` is a Pydantic `BaseModel` with mutable containers
(`board.nodes: dict`, `players: dict`, `setup_complete: set`). Mutation goes
through `_cow_clone()` → `_cow_node/_cow_player/_cow_market_state/_cow_resource_pool`
which mark entries in a `_cow_dirty: set` so only touched nodes/players get deep
copied. Pydantic `model_config` is mutable; a fast `__deepcopy__` builds via
`__new__ + object.__setattr__` to skip pydantic overhead. Hot-path fields include
private caches (`_presence_cache`, `_special_stack_cache`, `_cached_legal_moves`,
`_cached_indexed_moves`).

**C** — `GameState` is a single struct holding **fixed-size arrays** of nodes
(`NodeState nodes[MAX_NODES=128]`), players (`PlayerState players[MAX_PLAYERS=4]`),
and a `MarketState` with `Sym deck[MAX_ZONE_SIZE=80]`. Mutation uses `cow_node` /
`cow_player` / `cow_market` / `cow_resource_pool` returning mutable pointers; the
`cow_dirty` flag is per-element (`NodeState.cow_dirty`, `PlayerState.cow_dirty`,
`MarketState.cow_dirty`) rather than a central set. There is no Python-style cache
layer on the C struct — legal-moves caching is presumably done in Python bindings
or omitted.

**Strings → Sym.** Every `str` in Python (card id, player id, node id, ability key,
kind, timing, …) becomes a `Sym` (uint32) in C, interned through `intern()`. This
means a global `intern` table is created once and shared across all states; **all
catalogs/boards/setups loaded into the same process must agree on id strings**,
or collisions/incorrect lookups can occur across catalog loads. The Python engine
has no such shared state — strings are dict keys.

**Resource pool.** Python resets via `ResourcePool()` (fresh Pydantic object); C
uses `memset(&state->resource_pool, 0, sizeof(ResourcePool))`. Semantically
identical.

**Pending state.** Python has three Pydantic models (`PendingAbilityState`,
`PendingPromotionState`, `PendingGenericChoiceState`) attached as fields on
`GameState`. C inlines them as structs (`PendingAbilityState *pending_ability`,
`PendingPromotionState pending_immediate[MAX_PENDING_PROMO=16]` / `pending_eot`,
`PendingGenericChoiceState *pending_generic`). Field names diverge:

| Python field                            | C field                       |
|-----------------------------------------|-------------------------------|
| `pending_generic_choice.execution_kind` | `pending_generic->exec_kind`  |
| `pending_generic_choice.last_selection` | `last_selection_keys[8]` + `last_selection_values[8]` (parallel arrays) |
| `pending_generic_choice.action_counters` | `counter_keys[8]` + `counter_values[8]` |
| `pending_generic_choice.action_repeat_limits` | `limit_keys[8]` + `limit_values[8]` |
| (no equivalent)                          | `last_selection_count`, `counter_count`, `limit_count`, `resolve_depth` |
| `pending_generic_choice.next_action_index` | `next_action_index` (same)  |

**Pending ability.** Python has no `resolved` field on `PendingAbilityState`;
C has `bool resolved` and surfaces it in the public view.

**`devour_pile` and `setup_complete`** are `set[str]` / `list[str]` in Python
(`Sym devour_pile[MAX_ZONE_SIZE]` + `setup_complete[MAX_PLAYERS]` parallel arrays
in C). Behavior should match but ordering of `setup_complete` is array order in C
vs set-unordered in Python — only matters if exposed in views; it is not.

**No `final_scores` dict.** Python stores `final_scores: dict[str, int]`; C uses
parallel arrays (`final_score_keys[MAX_PLAYERS]` + `final_score_values[MAX_PLAYERS]`
+ count). C scoring also exposes `find_winner` returning the winning player id;
Python uses `winner` in `rules.py`.

---

## 4. Move representation

**Python** — discriminated `BaseModel` union keyed on `move_type: Literal[...]`
(`PlayCardMove`, `DeployMove` with `troop_count: int`, `RecruitMove` with
`market_slot: int`, `ActivateCardAbilityMove` with `card_id + ability_key +
discard_hand_indices`, etc.). `extra="forbid"` and `Field(discriminator=...)`.

**C** — `Move` is a struct with `type` (`MoveType` enum) and a tagged union of
`{ … } data;`. Notable differences:

| Concept                  | Python                                       | C                                            |
|--------------------------|----------------------------------------------|----------------------------------------------|
| `play_card` payload      | `card_id, hand_index`                        | `card_id, hand_index` (same)                 |
| `deploy` payload         | `target_node_id, troop_count=1`              | `node_id, slot_index=0` (single-troop, fixed slot) |
| `assassinate` payload    | `target_node_id, target_slot_index`          | `target_node_id, troop_owner_id, slot_index` (extra owner field) |
| `recruit` payload        | `market_slot`                                | `card_id` (no market_slot; resolved at apply) |
| `activate_ability`       | `card_id + ability_key + discard_hand_indices` | `ability_key` only                        |
| `resolve_generic`        | `source_card_id, option_id?, selection: dict` | `action_id, target_id, selection_index`      |
| `initial_placement`      | `target_node_id`                              | `node_id`                                   |
| `Move` construction      | Pydantic constructors                         | `make_*` factory functions in `moves.c`       |

`MOVE_RESOLVE_CLEANUP` exists in the C `MoveType` enum but no `make_*` factory
exists in `moves.c` — it is accepted as a move type but never constructed by
bindings, suggesting cleanup is implicit on phase advance.

`engine_c/bindings/engine_bindings.py` translates between C `Sym`/struct moves
and Python dicts; the move name map is in `ce_api.py:_MOVE_TYPE_MAP`.

---

## 5. Phase machine

Identical phase order and reset behavior:

- **SETUP** — advance player until all in `setup_complete` (Python `set` /
  C `Sym[]`); on completion → DRAW, current_player = turn_order[0].
- **DRAW** — every player draws 5 (`draw_cards_state` vs `draw_cards`). C iterates
  `state->player_id_count` and uses one `RNG rng;` value-initialized for each draw.
  Python seeds per-call via `Random((seed << 16) ^ counter)` and bumps `shuffle_count`
  on reshuffles.
- **MAIN → END_OF_TURN → CLEANUP → MAIN** — clean transition with `round_number++`
  when the next player is the first in order.

Both reset `resource_pool` to zero on every transition; both use a single
`advance_phase` function. Phase strings differ subtly: Python uses `TurnPhase(str,Enum)`
so it serializes as `"setup"`, `"draw"`, `"main"`, `"end_of_turn"`, `"cleanup"`,
`"game_over"`; C uses an int enum and a `_PHASE_MAP` in `ce_api.py` translates to
the same strings.

**Discrepancy worth verifying:** C `phases.c:27-31` declares `RNG rng;` once
without seeding, then passes `&rng` into `draw_cards_state` for every player.
The RNG is uninitialized at that point — its `s[]` is whatever was on the stack.
Python seeds deterministically via `(shuffle_seed << 16) ^ shuffle_counter`.
**Likely the C RNG relies on the seed already inside `draw_cards_state`'s
implementation (look at `state.c::draw_cards_state` / `shuffle_deck`)** — needs
a follow-up read to confirm. If uninitialized, IS-MCTS determinism may differ
between engines.

---

## 6. Scoring

Formula is identical:

- `award_end_of_turn_site_vp(state, player_id)` — sum of
  `node_definition.total_control_vp_per_turn` over sites where
  `is_total_control(player)` (all troop slots + no enemy spies).
- `compute_final_scores` = `score + sum(site.control_vp if controlled) + len(trophy) +
  vp_tokens + sum(card.deck_vp for deck/hand/discard) + sum(card.inner_circle_vp
  for inner_circle)`.

`_site_control_owner` is the same algorithm: count occupants, pick the player
with strictly most troops, exclude `"white"`, return `None` on tie. C uses
parallel `owners[MAX_PLAYERS+1] / counts[]` arrays; Python uses a dict.
C returns `-1` and the caller casts to `Sym` for the winner; Python returns `None`.
C includes a `find_winner` function; Python exposes `winner` from `rules.py`.

---

## 7. Rules / legal-moves generation

Both `engine/rules.py:legal_moves` and `engine_c/rules.c:engine_legal_moves`
share the same outline:

1. `phase == GAME_OVER` → empty.
2. `phase == SETUP` → `InitialPlacementMove` per legal node, unless player already
   in `setup_complete`.
3. `phase == DRAW` → empty.
4. `phase == MAIN`:
   - If `pending_immediate_promotions[0]` → `PromoteCardMove` / `SkipPromoteMove`.
   - Else if `pending_generic_choice` → `_legal_pending_generic_choice_moves`.
   - Else `legal_pending_ability_moves` (`ActivateAbilityMove` /
     `DeclineAbilityMove`) when pending, `PlayCardMove` for each hand card,
     `legal_main_phase_actions` (deploy/assassinate/return_spy/recruit + special
     stacks), and `EndMainPhaseMove`.
5. `phase == END_OF_TURN`:
   - If `pending_end_of_turn_promotions[0]` is `deferred_choice` → deferred
     target list; else if `optional` → optional promo pair; else
     `ResolveEndOfTurnMove`.
6. `phase == CLEANUP` — Python returns `[ResolveCleanupMove]`; C returns 0 (no
   explicit cleanup move — cleanup is auto-advanced by `phases.c`).

**Differences:**

- C `legal_main_phase_actions` hard-codes `state->resource_pool.power >= 1` for
  deploy and `>= 3` for assassinate/return_spy. Python has the same gating (see
  `engine/rules.py` + `helpers.py`); confirm the thresholds are aligned.
- C hard-codes `special_slots[] = {100, 101, 102}` and uses `special_stack_config`
  + `remaining_special_stack_count` to populate `RecruitMove`. Python uses the same
  three slot ids from `engine/moves.py:HOUSE_GUARD_RECRUIT_SLOT=100`, etc., and
  `_remaining_special_stack_count` from `helpers.py`.
- C guards `slot == 102` (Insane Outcast) behind `is_aberrations_enabled(state)`.
  Verify Python has the same guard.
- C always writes `player_index = 0` for promotion / ability / generic / placement
  moves, even though `Move.player_index` exists. This is probably fine because the
  rules engine validates from `state->current_player_id`, but the Python engine
  carries `player_id: str` on every move.

---

## 8. Generic card interpreter

Python's interpreter is **six files** under `engine/generic_runtime/`
(`__init__.py`, `_resolve.py`, `_actions.py`, `_selection.py`,
`_custom_effects.py`, `_promotion_helpers.py`, `_utils.py`), totaling ~104 KB
and ~2700 SLOC. The C interpreter is a **single file** of ~15 KB / 366 SLOC
(`generic_runtime.c`) plus a ~2 KB header.

Logic to compare:

- `action_requires_selection` — both enumerate a list of selection-requiring ops
  (`deploy_troops`, `assassinate_troop`, `supplant_troop`, `place_spy`,
  `return_spy`, `return_unit`, `move_troop`, `force_discard`, `recruit_card`,
  `devour`, `devour_cost`, `play_card`). Python version lives in
  `_actions.py` / `_selection.py`.
- `resolve_runtime_action_count` — both support `count_from=controlled_sites` and
  `count_from=spies_on_board` metadata. Python uses the same in
  `generic_runtime/_resolve.py` / `_utils.py`.
- `pending_action_counter_key` — `"op:action_id"` string format (matches Python's
  `"op:action_id"` key in `action_counters`).
- `pending_generic_active_action` — returns
  `current_actions[next_action_index]` if in range.
- `action_focus_requirement_met` — checks `requires_focus=true` + `focus_aspect`
  metadata, defers to `focus_requirement_met` in `helpers.c`.

**C-only fields** in `PendingGenericChoiceState` that Python does not have:
- `last_selection_count`, `counter_count`, `limit_count` — bookkeeping
  parallel to `len(...)` in Python.
- `resolve_depth` — recursion depth counter; Python version tracks this in
  `_resolve.py` (verify the limit matches).
- `awaiting_option` — present in both.

**Selection storage.** Python uses `last_selection: dict[str, Any]`. C uses two
parallel `Sym` arrays of length 8 (`last_selection_keys[8]`, `last_selection_values[8]`)
plus a count. Means **C can store at most 8 selection keys per pending generic**;
the Python dict is unbounded. If any card exceeds 8 selection keys this is a bug.

---

## 9. Effect registry

**Python** — `engine/helpers.py` keeps `_EFFECT_REGISTRY: dict[str, EffectFn]` and
`SPECIAL_RECRUIT_STACKS`. Each card effect registers at import time.

**C** — `engine_c/helpers.c` keeps `EffectFn effect_registry[EFFECT_COUNT=16]` with
matching `effect_keys[EFFECT_COUNT]`. The hard cap is **16 effect keys total**; if
the catalog ever has more, registration silently truncates (`if (effect_count <
EFFECT_COUNT)`). Python has no cap.

---

## 10. Determinization / cloning

**Python** — `_cow_clone()` performs a shallow state copy + lazy node/player deep
copy via `_cow_node/_cow_player/_cow_market_state/_cow_resource_pool`. Cache
attributes (`_presence_cache`, `_cached_legal_moves`, `_cached_indexed_moves`,
`_cached_legal_moves_version`, `_cached_indexed_moves_version`) are explicitly
copied. `pending_generic_choice` is **eager**-cloned because the resolver mutates
in place.

**C** — `engine_clone_cow(const GameState *src)` and `engine_determinize(...)` in
`state.c`. `NodeState`, `PlayerState`, `MarketState`, `ResourcePool` each have a
`bool cow_dirty` flag; `cow_*` functions check it and deep-copy on first write.
`Arena` allocation (`arena.c`) backs dynamic structures (`pending_ability`,
`pending_generic`, deep-cloned card arrays). The C `state` struct has no cache
fields, so cloning is plain deep copy.

The Python `PlayerState` has an explicit `clone_fast()`; C clones by `memcpy`/
struct assignment in `engine_clone_cow`.

**Implication for IS-MCTS:** Python and C take different code paths for tree
expansion. Python's `clone_fast` keeps cached legal moves so siblings of an
expansion can reuse computation; C must recompute. This is likely the dominant
performance delta in IS-MCTS.

---

## 11. Public / private view

**Python** — `engine/player_view.py` defines `PublicNodeView` (Pydantic frozen),
`PublicPendingAbilityView`, `PublicPendingPromotionView`, `PublicPendingGenericChoiceView`,
plus `PublicView` (round, phase, current player, market, pending effect ids) and
`PrivateView` (PublicView + observer's player state). Includes `kind`, `controller`,
`troop_counts: dict`, `spy_owners: list`, `vp_tokens`.

**C** — `state.h` defines `PublicNodeView` (parallel arrays: `troop_counts[MAX_PLAYERS]`
+ `troop_owners[MAX_PLAYERS]` + counts, `spy_owners[MAX_SPY_SLOTS]` + count,
`white_troops`, `vp_tokens`, `controlled`, `controller_id`). Includes
`white_troops` as a separate counter — Python view doesn't surface it
explicitly (it's folded into `troop_counts["white"]`).

`PublicPendingAbilityView` in C has `bool resolved` — Python does not.

`PublicPendingPromotionView` in C carries `player_index`. Python has
`source_card_id`, `requires_another_played_card`, `required_aspect`,
`required_secondary_aspect`, `repeat_while_targets`, `timing`. C's view has only
`card_id` and `is_optional`. **C public view of promotions loses most of the
metadata.**

`PublicPendingGenericChoiceView` in C: `source_card_id`, `player_index`,
`is_pending` — much smaller than Python's view (which carries all the
selection/counter/limit state). This is probably intentional for serialization
size but means C observers cannot reconstruct the choice tree from the public
view alone.

---

## 12. Bindings (Python↔C)

`engine_c/bindings/` provides:

- `engine_bindings.py` — ctypes: loads `engine_c.dll`, declares structures,
  constants, function prototypes.
- `c_adapter.py` — likely translates between ctypes structs and Python dicts.
- `ce_api.py` — `CEngine` class with `create_game / legal_moves / apply /
  is_terminal / winner / public_view / private_view`. Swap-in via
  `PYRANTS_ENGINE=c` env var (per module docstring).
- `session.py` — session controller around C engine.
- `view.py` — wraps C view structs as Python objects.

The bindings are the **public Python API surface** for the C engine. Consumers
(`game_session.py`, `game_simulation.py`, `scripts/run_ismcts.py`) can run
either engine behind the same call sites.

---

## 13. Things that *might* differ in behavior (verify in plan execution)

These are the spots where an automated test comparing both engines could
realistically trip:

1. **C `phases.c` RNG init for DRAW** — does `draw_cards_state` actually seed the
   `RNG` before use? If not, the first card of each player's hand in turn 1 is
   non-deterministic per process.
2. **Move translation** — `RecruitMove` (Python `market_slot` vs C `card_id`),
   `DeployMove` (Python `troop_count` vs C `slot_index`), `AssassinateMove`
   (Python no `troop_owner_id` vs C has it), `ActivateAbilityMove` (Python carries
   `discard_hand_indices` vs C doesn't), `ResolveGenericChoiceMove` (Python
   `source_card_id + option_id + selection: dict` vs C `action_id + target_id +
   selection_index`). The binding layer must bridge these correctly.
3. **Selection key cap** — C `last_selection_keys[8]`/`counter_keys[8]`/`limit_keys[8]`
   cap selection state at 8 keys. Python is unbounded.
4. **Effect registry cap** — C caps at 16 effects.
5. **`PromoteCardMove.card_id` semantics** — In C's optional promo pair, the move
   sets `data.promote_card.card_id = pending->card_id` (the *promo target*).
   Python: same — `PromoteCardMove(card_id=pending.card_id)`. Verify against
   deferred end-of-turn promotion, where Python takes `targets[i]` (the
   *card-being-promoted*, not the source card).
6. **Public view of promotions** — C drops metadata. If IS-MCTS relies on this
   metadata to key its determinization, the two engines will diverge in cached
   information state strings.
7. **CLEANUP move** — Python `legal_moves` returns `[ResolveCleanupMove]` in
   CLEANUP phase; C returns 0. If callers expect to advance via a move, the C
   engine must either auto-advance or accept the move type without listing it
   (verify `MOVE_RESOLVE_CLEANUP` is handled in `engine_apply`).
8. **`setup_complete` ordering** — C stores a `Sym[]` (insertion order via
   push); Python uses a `set` (unordered). `legal_moves` only checks membership,
   so behavior matches, but iteration order would differ.
9. **Card id collisions across catalog reloads** — C's global `intern` table
   persists across `engine_create_game` calls. If two games load different
   catalogs that share an id but with different rules, the second load will reuse
   the first's `Sym`. **Likely safe if all game definitions use a single shared
   catalog**, but `tests/test_generic.c`, `test_game.c`, etc. that load multiple
   scenarios sequentially may exhibit this.
10. **`white` troops counted differently in C scoring vs C view** — Python
    `_is_total_control` requires all troop slots be `player_id` (white still
    counts as occupant); C `is_total_control` requires every troop slot be
    `player_id` (so a node with a white troop on it is *not* totally controlled
    by anyone — but also not by white). Behavior matches, but the
    `site_control_owner` "white loses ties" rule applies in both.
11. **Arena clone** — `engine_clone_cow` deep-clones the arena; Python doesn't
    need arenas. Memory cost: each clone ≈ `arena.total_allocated` bytes.

---

## 14. Recommended next steps (NOT executed in plan mode)

These are read-only investigations the user could authorize later:

1. **Read `engine_c/state.c::draw_cards_state` and `shuffle_deck`** to confirm
   RNG seeding behavior matches Python's `Random((seed<<16)^counter)`.
2. **Read `engine_c/rules.c::engine_apply` for `MOVE_RESOLVE_CLEANUP`** to
   confirm cleanup is handled without an explicit move.
3. **Read `engine_c/bindings/ce_api.py` and `c_adapter.py`** to confirm the move
   translations (especially `RecruitMove` market_slot↔card_id and
   `AssassinateMove` adding `troop_owner_id`) are lossless for IS-MCTS callers.
4. **Diff card-effects registered in Python vs C** to confirm the
   `EFFECT_COUNT=16` cap is not silently truncated.
5. **Inspect `engine_c/intern.c`** to see if `intern_destroy` is called between
   `engine_create_game` calls (and whether collisions across games are possible).
6. **Compare public-view JSON for a fixed state** (use the same seed via both
   engines, snapshot the JSON, diff) — would surface every metadata gap above.

---

## 15. Files inspected (read-only)

- `engine/__init__.py`, `engine/state.py` (1–928), `engine/moves.py`,
  `engine/phases.py`, `engine/scoring.py`, `engine/player_view.py` (1–80),
  `engine/rules.py` (1–120).
- `engine_c/engine.h`, `engine_c/state.h`, `engine_c/rules.h`, `engine_c/rules.c`
  (1–200), `engine_c/moves.c`, `engine_c/phases.c`, `engine_c/scoring.c`,
  `engine_c/player_view.c`, `engine_c/helpers.h`, `engine_c/helpers.c` (1–120),
  `engine_c/generic_runtime.c` (1–120), `engine_c/loader.c` (1–80),
  `engine_c/arena.c`, `engine_c/intern.h`, `engine_c/rng.h`, `engine_c/saveload.h`,
  `engine_c/bindings/ce_api.py` (1–60), `engine_c/bindings/engine_bindings.py` (1–60).