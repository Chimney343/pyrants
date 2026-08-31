# Plan: Market-deck determinization, unlimited world sampling, dead-code removal, and public-zone visibility

## Context

A validity review of the `python_pyrants_c` OpenSpiel IS-MCTS wrapper (reading
`open_spiel.python.algorithms.ismcts.ISMCTSBot`, `engine_c/state.c`'s
`engine_determinize`, and empirical resampling probes) found the core
mechanics sound — action-index stability across determinizations and
information-state invariance both hold (600/600 empirical checks, full test
suite green) — but surfaced four concrete, still-open gaps. This plan closes
all four. It assumes no memory of that review; each section below is
self-contained with the evidence needed to act.

## Item 1 — Reshuffle the market deck on every determinization

### Review of the market-deck mechanics (confirmed against source)

Your understanding is correct on all three points:

- **1.1** — At game start, [`engine_c/state.c:143-152`](engine_c/state.c#L143-L152)
  builds the combined market deck, shuffles it, deals the row, and stores the
  remainder as `market.deck`. One shuffle, at setup, matches the rulebook
  ("Choose 2 of the market half-decks... shuffle them together to form the
  market deck," rulebook line 131).
- **1.2** — `market_row_size` defaults to 6
  ([`engine_c/loader.c:410`](engine_c/loader.c#L410)); `state.c:143-152` deals
  exactly that many cards face-up into `market.row` from the top of the
  shuffled deck at setup.
- **1.3** — Two, and only two, actions draw from the top of `market.deck` to
  refill a row slot: `apply_recruit`/`apply_recruit_free` ("buy") in
  [`engine_c/helpers.c:495-560`](engine_c/helpers.c#L495-L560) via
  `ms->row[slot] = ms->deck[--ms->deck_count]`, and the "devour" market effect
  ("remove," e.g. an Elemental-deck ability) in
  [`engine_c/actions.c:622-644`](engine_c/actions.c#L622-L644), same refill
  line. Both fall back to shrinking the row (no refill) once `deck_count`
  hits 0 — consistent with the engine's confirmed no-recycle behavior
  (`engine_c/phases.c:55` treats an empty market deck as a game-ending
  condition, not a reshuffle trigger).

**On "shuffled at every single rollout":** this is the right instinct, with
one precision worth stating explicitly so the implementing agent doesn't
over-shuffle. `ISMCTSBot.run_search` (open_spiel `ismcts.py:127-132`) calls
`sample_root_state(state)` once per simulation *iteration*, at the root,
before descending; the resulting determinized state is then played out to
a leaf/terminal with **no further resampling mid-rollout** (deeper tree
nodes reuse whatever hidden state was fixed at their iteration's root
sample). So "shuffle at every rollout" is exactly right if "rollout" means
"one `resample_from_infostate` call, i.e. one simulation iteration" — do
**not** reshuffle again partway through a single simulation's descent, only
at the point `resample_from_infostate` is invoked. That is also exactly
where the fix belongs: inside `engine_determinize`, which is the sole
function backing `resample_from_infostate` for this backend
([`openspiel_pyrants/state_c.py:307-335`](openspiel_pyrants/state_c.py#L307-L335)
→ [`engine_c/bindings/c_adapter.py:63-72`](engine_c/bindings/c_adapter.py#L63-L72)
→ `engine_determinize`).

### The actual gap

[`engine_determinize`](engine_c/state.c#L271-L301) reshuffles each
opponent's hand+deck+discard pool but never touches `market.deck`. This was
scoped once before in
[`.kilo/plans/1784878681754-market-deck-ismcts-determinization.md`](.kilo/plans/1784878681754-market-deck-ismcts-determinization.md)
("Change 1") but never implemented — confirmed by reading the current
function body, which has no market-deck code path. Every simulated rollout
within a search currently sees the game's one true (real) future market
draw order, biasing value estimates for any line of play that depends on
what refills the row.

### Change

In `engine_c/state.c`, append to `engine_determinize`, **after** the existing
opponent-reshuffle loop and before `return clone;` (placement matters: it
keeps the RNG draws consumed by the opponent loop unchanged, so no existing
pinned-value test on opponent hand contents post-determinize breaks):

```c
/* Market deck order is hidden to all players (only its size is public):
 * reshuffle it on every determinization so IS-MCTS cannot exploit a single
 * clairvoyant deck order across simulations. The face-up market row and the
 * (unused, non-recycled) market discard are left untouched. */
if (clone->market.deck_count > 1) {
    rng_shuffle(&rng, (uint32_t *)clone->market.deck, clone->market.deck_count);
}
```

`Sym` is `uint32_t` ([`engine_c/intern.h:6`](engine_c/intern.h#L6)) and
`market.deck` is `Sym[MAX_ZONE_SIZE]`
([`engine_c/state.h:238-239`](engine_c/state.h#L238-L239)), so the cast
matches the pattern already used for the opponent temp buffer three lines
above it. `rng_shuffle(RNG*, uint32_t*, int)` is declared in `engine_c/rng.h:15`.

No Python-side change is needed — `state_c.py`'s `resample_from_infostate`
already calls all the way through to `engine_determinize` for every
resample; the market shuffle is inherited for free once the C function does it.

### Tests to add (`openspiel_pyrants/tests/test_determinize_c.py`)

- `test_determinize_reshuffles_market_deck`: build/reach a state with a
  non-trivial market deck (>1 card) and a known face-up row; call
  `CEngineAdapter.determinize` (or `state.resample_from_infostate`) with two
  different seeds; assert the resulting `market.deck` multiset (via a raw
  `CState` accessor — add one if none exists, mirroring `player_deck`) is a
  permutation of the original (same multiset) and differs in order across
  the two seeds with high probability over several trials.
- `test_determinize_preserves_market_row`: row card IDs and order identical
  before/after, for both seeds (the row is public, never touched).
- `test_resample_market_keeps_infostate_key`: extend the existing
  `test_resample_information_state_string` pattern — pin a state with a
  multi-card market deck and confirm `information_state_string(player)` for
  the observing/current player is byte-identical before/after resampling
  (market deck order is never part of that string, only size — regression
  guard for the "size-only observability" invariant).
- Confirm the whole existing `test_determinize_c.py` / `test_resample_c.py` /
  `test_ismcts_smoke_c.py` suites stay green (opponent-hand tests must not
  shift — that's what the "after the opponent loop" placement protects).

## Item 2 — Default `--max-world-samples` to unlimited

### The gap

`ISMCTSBot.sample_root_state` (`ismcts.py:206-217`) only resamples fresh on
every iteration when `max_world_samples == UNLIMITED_NUM_WORLD_SAMPLES`
(`-1`). With a positive cap, the bot fills a pool of that many
determinizations and then **reuses a random pooled clone** for every later
iteration — no new shuffle, including no new market-deck shuffle once Item 1
lands. [`scripts/run_ismcts.py:105`](scripts/run_ismcts.py#L105) still
defaults `--max-world-samples` to `1000`, not `-1`. Today's default
`--num-sims 200` (`run_ismcts.py:103`, and the `justfile`'s `ismcts`/
`ismcts-quick` targets) never hits that cap, but any run with `--num-sims`
above 1000 (a natural thing to try when scaling up search strength) silently
freezes world diversity partway through.

### Change

In `scripts/run_ismcts.py`:
- Change the `--max-world-samples` argparse default from `1000` to `-1`.
- Update its `help=` text to state the default is unlimited (fresh
  determinization, and thus fresh market-deck shuffle once Item 1 lands,
  every iteration — matching the IS-MCTS whitepaper), and that a positive
  value opts into the capped-pool-reuse behavior instead.
- No other code changes needed — `ISMCTSBot(..., max_world_samples=...)` is
  already wired straight from the parsed arg at
  [`scripts/run_ismcts.py:737` and `:774`](scripts/run_ismcts.py#L737).
- Check the `justfile`'s `ismcts`, `ismcts-quick`, and `ismcts-perf` recipes
  (lines 47-57): none currently pass `--max-world-samples` explicitly, so
  they'll pick up the new default for free. Leave them as-is unless one of
  them needs the capped behavior for a specific reason (unlikely, but check
  before assuming).

### Tests / validation

- No new unit test strictly required (this is an argparse default), but add
  a one-line assertion to whatever test currently exercises
  `_parse_args()`/CLI defaults (grep for existing arg-default tests in
  `openspiel_pyrants/tests/test_run_ismcts_runner.py` and
  `tests/test_run_ismcts_replay_payload.py` first — extend one of those
  rather than adding a new file if a fitting one exists).
- Re-run `just ismcts-quick` and confirm it still completes without error.

## Item 3 — Remove the dead `deterimization_c.py` stub (test-first)

### The gap

[`openspiel_pyrants/deterimization_c.py`](openspiel_pyrants/deterimization_c.py)
is an unimported stub whose docstring claims to be "the determinization
module" for the C backend. It is not: the live path is `state_c.py` →
`CEngineAdapter.determinize` → C `engine_determinize`, which entirely
bypasses this file. Both
[`docs/openspiel-architecture.md:117`](docs/openspiel-architecture.md#L117)
and `docs/repo_structure.md:58` cite it as if it were live, which will
misdirect the next reader.

### Step 1 — write the confirming test first

Add `openspiel_pyrants/tests/test_deterimization_c_unused.py` that proves
the module is dead *before* deleting it, so the removal is a verified no-op
rather than an assumption:

```python
"""Regression guard: deterimization_c.py must stay unreferenced by the live
C-backend path before it can be safely deleted. If this test ever fails,
someone wired the stub back in and the removal plan needs revisiting."""
from __future__ import annotations

import ast
from pathlib import Path

LIVE_C_BACKEND_FILES = [
    "openspiel_pyrants/game_c.py",
    "openspiel_pyrants/state_c.py",
    "openspiel_pyrants/observer_c.py",
    "openspiel_pyrants/action_encoding_c.py",
    "engine_c/bindings/c_adapter.py",
]

ROOT = Path(__file__).resolve().parents[2]


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_deterimization_c_not_imported_by_live_c_backend():
    for rel in LIVE_C_BACKEND_FILES:
        path = ROOT / rel
        imports = _imports(path)
        assert not any("deterimization_c" in name for name in imports), (
            f"{rel} imports deterimization_c — it is no longer dead code, "
            f"do not delete it without re-auditing this plan"
        )
```

Run it and confirm it **passes** (green from the start — this is a
regression guard, not a TDD red/green cycle, since the module is already
unused; the point is to have a mechanical check before deleting, not to
change behavior).

### Step 2 — delete the stub

- Delete `openspiel_pyrants/deterimization_c.py`.
- Fix the two docs that cite it:
  [`docs/openspiel-architecture.md:117-124`](docs/openspiel-architecture.md#L117-L124)
  (the "Information-State Projection" section's closing paragraph, which
  currently attributes the resample contract to this file — repoint it at
  `CEngineAdapter.determinize` / `engine_determinize` instead) and
  `docs/repo_structure.md:58` (drop or repoint the row).
- Keep `test_deterimization_c_not_imported_by_live_c_backend` in the suite
  after deletion — with the file gone, `_imports()` will simply never find
  the substring, so the test remains a valid (trivially-passing) guard
  against it being reintroduced. If you'd rather not keep a test that
  references a deleted file's name, that's a fine call too — but leave a
  one-line comment explaining why the check was removed rather than just
  deleting it silently.

### Validation

- `just test` (or `pytest openspiel_pyrants/tests`) green.
- `ruff check .` clean (no dangling import of the deleted module anywhere —
  grep for `deterimization_c` repo-wide after deleting to be sure).

## Item 4 — Expose face-up zones (inner circle, trophy hall, this-turn plays) for every player

### Why this is safe and worth doing

Per the rulebook, promoted cards go "face up on your inner-circle board"
(rulebook line 345), assassinated troops go to a visible "trophy hall"
(rulebook line 308), and played cards are laid "face up in front of you"
(rulebook line 219) — all physically observable by every player at the
table. The current OpenSpiel-facing view
([`c_adapter.py:124-185`](engine_c/bindings/c_adapter.py#L124-L185)) only
exposes *counts* of these zones for opponents and full identities for the
observing player's own zones — under-informing the model relative to the
real game. Per your note: **this information never affects legal actions**
(confirmed — none of `engine_legal_moves`'s dependencies read another
player's `inner_circle`/`trophy_hall`/`played_cards` contents), so widening
it purely adds informative detail without touching the action-index
stability verified in the review. Safe, additive change.

### 4a — Engine-facing exposure (OpenSpiel public view)

1. Add a `player_trophy_hall(index)` accessor to `CState` in
   [`engine_c/bindings/ce_api.py`](engine_c/bindings/ce_api.py#L248-L256),
   mirroring the existing `player_discard`/`player_inner_circle` pattern
   exactly (the backing C field `trophy_hall[MAX_ZONE_SIZE]` +
   `trophy_hall_count` already exists on `PlayerState`,
   [`engine_c/state.h:222-223](engine_c/state.h#L222-L223) — this is a pure
   Python-binding addition, no C engine change needed):

   ```python
   def player_trophy_hall(self, index: int) -> list:
       """Return list of card ID strings in the player's trophy hall."""
       p = self._s.players[index]
       return [_sym_str(p.trophy_hall[i]) for i in range(p.trophy_hall_count)]
   ```

2. In [`CEngineAdapter._build_public_dict`](engine_c/bindings/c_adapter.py#L124-L161),
   inside the per-player `summaries[pid] = {...}` block, add three new keys
   alongside the existing `*_size` fields — the actual identity lists, for
   **every** player, not just the observer:

   ```python
   "inner_circle": [_sym_str(p.inner_circle[i]) for i in range(p.inner_circle_count)],
   "trophy_hall": [_sym_str(p.trophy_hall[i]) for i in range(p.trophy_hall_count)],
   "played_cards": [_sym_str(p.played_cards[i]) for i in range(p.played_cards_count)],
   ```

   (Keep the existing `*_size` fields too — cheap redundancy, avoids
   breaking anything that already reads them.)

3. `private_view_json` (same file, `c_adapter.py:163-185`) already includes
   these three lists for the observing player only, via the top-level
   `hand`/`played_cards`/`inner_circle`/`trophy_hall` keys built from `p =
   self._state._s.players[idx]`. Leave that as-is — it becomes redundant
   with the new public fields for the observer's own player, which is
   harmless.

4. `information_state_string()` / `observation_string()` in `state_c.py`
   don't need any change — they already serialize whatever
   `private_view_json` returns, which now transitively includes the wider
   public dict.

### 4b — GUI dropdowns (`interface/game_viewer.py`)

The GUI already has exactly this pattern implemented for discard piles —
replicate it twice, not from scratch.

1. Reference implementation to copy:
   `_sync_other_player_discard_boxes_c`
   ([`interface/game_viewer.py:1234-1289`](interface/game_viewer.py#L1234-L1289)),
   wired from `_sync_other_player_discard_boxes_c(cstate, cards_by_id)` at
   [`game_viewer.py:1187`](interface/game_viewer.py#L1187), backed by a
   sidebar section built at
   [`game_viewer.py:929-933`](interface/game_viewer.py#L929-L933)
   (`self.other_discards_frame`, one `ttk.Combobox` row per opponent,
   created/destroyed as `turn_order` changes).

2. Add two more sidebar sections, each with its own frame/placeholder
   (mirroring lines 929-933) and its own sync method (mirroring lines
   1234-1289):
   - **"Other Player Inner Circles"** → `_sync_other_player_inner_circle_boxes_c`,
     sourced from `state.player_inner_circle(state.player_index(player_id))`
     (already exists on `CState`), formatted with the existing
     `format_ordered_card_options` helper (already used for the current
     player's own inner circle at `game_viewer.py:1193`).
   - **"Other Player Trophy Halls"** → `_sync_other_player_trophy_hall_boxes_c`,
     sourced from the new `state.player_trophy_hall(index)` from step 4a.1,
     formatted with the existing `format_trophy_hall_options` helper
     (already used at `game_viewer.py:1203`).
3. Call both new sync methods alongside the existing
   `self._sync_other_player_discard_boxes_c(cstate, cards_by_id)` call at
   `game_viewer.py:1187`.
4. **Do not** add a dropdown for "cards played this turn" — per your
   instruction, turns are strictly sequential in this game (no simultaneous
   play), so an opponent's in-progress turn is already visible live as it
   happens; a persistent dropdown for it would be redundant UI. The
   engine-level exposure from 4a (item 3 in the list above, `played_cards`
   in `_build_public_dict`) stays — that's for the OpenSpiel/IS-MCTS
   consumer, which has no "watch it happen live" equivalent and does
   benefit from the data being in the information state.
5. Register/unregister the new frames the same way discards do when players
   are added/removed (the loop at `game_viewer.py:1279-1283` that destroys
   stale rows) — copy that teardown logic into both new sync methods too, or
   factor a small shared helper if the duplication feels excessive (three
   near-identical sync methods is a reasonable point to extract one
   parameterized helper — use your judgment, but don't over-engineer a
   fourth zone type that doesn't exist yet).

### Tests to add

- `engine_c/bindings/test_label_enrich.py` or a new
  `engine_c/bindings/tests/test_ce_api_player_trophy_hall.py` (match
  whatever the existing test-file convention is for `ce_api.py` accessors —
  check for one first): assert `player_trophy_hall(index)` returns the
  correct card IDs after an assassinate move, for a non-current-player
  index.
- Extend `openspiel_pyrants/tests/test_resample_c.py` or add a new small
  test asserting `information_state_string(cp)` from a state with a
  non-empty opponent inner_circle/trophy_hall/played_cards includes those
  opponent card identities (a simple substring/JSON-key check), i.e. that
  the widened `_build_public_dict` is actually reaching the information
  state string end-to-end.
- No GUI automated test infrastructure was found for `game_viewer.py`
  (Tkinter, manually driven) — validate the new dropdowns by running the
  viewer against a scenario with non-empty opponent inner circle/trophy
  hall (several exist under `data/scenarios/`) and confirming the new
  sidebar sections populate and clear correctly as players rotate.

## Validation (all items)

1. `just build-c` (rebuilds `engine_c.dll` + C tests — required for Item 1).
2. `just test-c` (C unit suite).
3. `just test-c-python` / `pytest openspiel_pyrants/tests` (or `rtk proxy
   "python -m pytest openspiel_pyrants/tests -v"` if bare `pytest` reports
   "No tests collected" — that's a known local hook/rootdir quirk, not a
   real collection failure; `rtk proxy` bypasses it).
4. `just test` (full Python suite) and `ruff check .`.
5. `just ismcts-quick` completes without error (sanity check across all four
   items at once, small budget).
6. Manually launch the game viewer on a mid-game scenario with non-trivial
   opponent inner circle/trophy hall contents and confirm the new dropdowns
   show correct data (Item 4b has no automated coverage).

## Risks

- **Item 1 placement**: shuffling market deck *before* the opponent loop
  instead of after would shift the RNG stream consumed by opponent
  reshuffling and could change any test that pins exact opponent-hand
  contents post-determinize. Keep it after, as specified.
- **Item 1 scope creep**: do not also shuffle `market.discard_pile` — the
  engine never recycles it (confirmed: no runtime
  `market.discard_pile_count++` outside JSON load, and `phases.c:55` treats
  an empty deck as terminal, not a recycle trigger). Pooling it in would be
  wrong per the current rules implementation. If a future change
  reintroduces market-discard recycling, this scope must be revisited.
- **Item 1 performance**: one extra Fisher-Yates over up to ~74 cards per
  determinization is negligible next to the existing per-opponent reshuffle
  work, but note it scales with `num_sims × decision_count` like everything
  else in IS-MCTS.
- **Item 2**: no correctness risk; purely changes a default. The only
  observable effect is slower-but-more-correct behavior for anyone who was
  relying on the old capped default without realizing it, which is the
  intended fix.
- **Item 3**: verify the confirming test (step 1) actually passes *before*
  deleting — if it somehow fails, something currently depends on the stub
  and the deletion must be reconsidered, not forced through.
- **Item 4**: purely additive to public data — the review already confirmed
  legal-action generation doesn't read these fields for other players, so
  this shouldn't be able to regress action-index stability. Still, re-run
  the action-stability-style checks (or at minimum the full test suite) after
  landing it, since "shouldn't" is not "can't."

## Out of scope

- Any change to the C engine's native `engine_public_view`/`engine_private_view`
  (`engine_c/player_view.c`) — those are currently bypassed by
  `c_adapter.py` due to a documented ctypes struct-layout mismatch and are
  not the live path for either the OpenSpiel wrapper or the GUI. Fixing that
  mismatch is a separate, larger effort and not needed for any of the four
  items here.
- Discard-pile visibility semantics (whether opponents' discard piles should
  be treated as public vs. hidden in determinization) — flagged in the
  original review as an open rules question, not addressed by this plan.
  `engine_determinize` currently pools discard into the same hidden
  reshuffle as hand+deck; that is unchanged here.
- Board-occupancy fields (troop/spy positions per node) in
  `_build_public_dict` — currently implicitly carried through
  `information_state_string`'s history-string component rather than
  explicitly serialized; out of scope for this plan.
