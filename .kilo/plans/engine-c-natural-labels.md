# Plan: Natural-language labels for C-engine legal moves

## Goal

Replace the mechanical, debug-oriented labels produced by `engine_c/describe.c`
(and the `_describe_c_move` Python wrapper) with player-facing strings that
read like natural game actions. Specifically:

- Use friendly node names instead of raw internal IDs (`site_gauntlgrym` → `Gauntlgrym`).
- Stop exposing internal slot indices in labels.
- Replace raw `ability_key` / `action_id` strings with human-readable equivalents
  anchored on the **card name** that owns the ability/action.
- Provide graceful fallback for any move type that lacks a specialized template.
- Plumb `node_names` from the Python view layer all the way into the label generator
  (currently dead-code path).

The fix is layered: improve the C templates, plumb `node_names` into the Python
wrapper, and add a Python-side ability-key → card-name formatter for the
generic/ability moves that the C side can't resolve cleanly.

---

## Scope

In scope:
- `engine_c/describe.c` — rewrite templates
- `engine_c/describe.h` — no API change, but add a doc comment
- `engine_c/tests/test_describe.c` — update assertions
- `engine_c/bindings/view.py` — plumb `node_names` into `_describe_c_move`
- `engine_c/bindings/view.py` — Python-side enrichment for ability/resolve_generic labels
- One new small helper module for the Python-side enrichment

Out of scope:
- Changes to `engine/` (the deprecated Python engine) — it has no label API.
- Changes to the OpenSpiel wrapper — it consumes the C engine, not the labels.
- Changes to the IS-MCTS / simulation runner — these don't surface labels to users.

---

## File-by-file changes

### 1. `engine_c/describe.c` — rewrite templates

**`node_label()`** is currently dead code in practice (the Python wrapper passes
`NULL` for `node_names`). Tighten it to:
- Return the friendly name when `node_id_str` is found in `node_names`.
- Return a humanized fallback (snake_case → Title Case) when not found, instead
  of leaking the raw ID.
- Keep the existing `strcmp` lookup; add a small `_humanize_id()` helper for the
  fallback path.

**`troop_owner_label()`** — return the owner Sym intern string as before; in the
caller, treat `"white"` / `"black"` / `"red"` / `"purple"` as the actual house
names (these *are* the in-game names, no mapping needed). The `unknown` /
`empty` fallbacks are fine as-is.

**`engine_describe_move()` templates** — rewrite the `snprintf` lines:

| Move type | Current | New |
|---|---|---|
| `MOVE_PLAY_CARD` | `Play {name}` | `Play {Name}` (same — already good) |
| `MOVE_END_MAIN_PHASE` | `End main phase` | `End main phase` (keep — phase terminology is correct) |
| `MOVE_RESOLVE_END_OF_TURN` | `Resolve end of turn` | `Proceed to end of turn` |
| `MOVE_RESOLVE_CLEANUP` | `Resolve cleanup` | `Proceed to cleanup` |
| `MOVE_DEPLOY` | `Deploy to {node}` | `Deploy a troop to {Node}` |
| `MOVE_INITIAL_PLACEMENT` | `Place free troop at {node}` | `Place starting troop at {Node}` |
| `MOVE_ASSASSINATE` | `Assassinate {owner} troop at {node} slot {idx}` | `Remove {owner} troop at {Node}` (drop `slot {idx}`) |
| `MOVE_RECRUIT` | `Recruit {name}` | `Recruit {Name}` (same) |
| `MOVE_RETURN_SPY` | `Return {owner} spy from {node}` | `Return {owner}'s spy from {Node}` |
| `MOVE_ACTIVATE_ABILITY` | `Activate {ability_key}` | `Activate {Name}'s ability` (deferred to Python — see §3) |
| `MOVE_DECLINE_ABILITY` | `Decline {ability_key}` | `Decline {Name}'s ability` (deferred to Python) |
| `MOVE_PROMOTE_CARD` | `Promote {name}` | `Promote {Name}` (same) |
| `MOVE_SKIP_PROMOTE` | `Skip promote` | `Skip promotion` |
| `MOVE_RESOLVE_GENERIC` | `Resolve {action_id}` | `Resolve {CardName} choice` (deferred to Python) |
| default | `Move` | `Unknown move (type N)` — at least the type number is preserved for debugging |

Note: For `MOVE_ACTIVATE_ABILITY`, `MOVE_DECLINE_ABILITY`, and
`MOVE_RESOLVE_GENERIC` the C side will continue to emit a *placeholder* string
(using the raw key), and the Python wrapper will **override** it. The C side
keeps a sensible fallback so that pure-C consumers (tests, the C test runner)
still get a working label.

### 2. `engine_c/describe.h` — doc comment

Add a doc comment explaining the contract:
- `node_names` is a `const char *const *` of known node IDs; the helper will
  look up the friendly name from that array. May be `NULL` (then a
  humanized fallback is used).
- Return value: bytes needed for the full null-terminated string, or 0 on
  failure. Caller may pass `out=NULL, out_cap=0` to query the size.

### 3. `engine_c/tests/test_describe.c` — update assertions

The test asserts `strstr(buf, "Play")`, `strstr(buf, "Deploy")`, etc. — these
all still pass with the new templates, since the new strings still contain the
old leading words. Add **new** explicit assertions for:
- `Assassinate` label no longer contains `slot`
- `Assassinate` label no longer contains the raw `slot_index` number
- `node_names={"site_1"}` → `Deploy` label contains `site_1` (current behavior)
- New test: `node_names=NULL` → `Deploy` label is humanized (e.g. `Site 1`)
- `MOVE_ACTIVATE_ABILITY` placeholder contains the card's name (because the
  Python override is exercised separately — see §5)
- `default` case produces a non-empty string with the type number

### 4. `engine_c/bindings/view.py` — plumb `node_names`

`build_c_game_view(..., node_names=...)` already accepts the dict. The dict
needs to be **forwarded** to `_describe_c_move()` and converted into the
`ctypes` shape that `engine_describe_move` expects.

Change `_build_c_legal_moves(session, state_ptr)` to accept the `node_names`
dict and stash it on the closure for `_describe_c_move`.

Change `_describe_c_move(state_ptr, move_wrapper, node_names_map)` to:
- Convert `node_names_map: dict[str, str]` into a `(c_char_p * N)` array
  of the **values** (friendly names), iterated in insertion order.
- Call `_lib.engine_describe_move(state_ptr, ctypes.byref(c_move),
  (c_char_p * N)(*names), N, buf, 256)`.

Update the call site at `build_c_game_view` line 326:
```python
legal_moves=_build_c_legal_moves(session, state_ptr, node_names=node_names),
```
and propagate `node_names` through `build_c_game_view`'s parameters (it's
already accepted but currently ignored inside `_build_c_legal_moves`).

### 5. `engine_c/bindings/view.py` — Python-side enrichment for ability/resolve_generic

The C side can't easily map `ability_key` → "Bandit Errand" because the
interned string is the key, not the card ID, and the mapping lives in
`catalog.json`. The Python layer already has `_catalog_cache()`.

Add a small helper inside `view.py` (or a new sibling module
`engine_c/bindings/label_enrich.py` if `view.py` gets too big) called
`_enrich_label(move_type, raw_label, move_data)` that:
- For `activate_ability` / `decline_ability`: looks up `card_id` in the
  catalog, formats `"Activate {Card Name}'s ability"` or
  `"Decline {Card Name}'s ability"`. Falls back to `raw_label` if the card
  isn't found.
- For `resolve_generic`: looks up the action's `card_id` (if any) via the
  pending generic choice context — but the C `CMoveWrapper` doesn't currently
  expose that. **Simplification:** format as
  `"Resolve {Card Name} choice"` using the `target_id` (which is the
  card ID for card-targeting actions) when possible, else fall back to
  `raw_label`. If neither is available, emit `"Resolve pending choice"`.
- For all other move types: return `raw_label` unchanged.

`CLegalMoveView.__init__` already takes a `label`; we just need to enrich
before constructing. Modify `_build_c_legal_moves` so the label pipeline is:

```
raw_label = _describe_c_move(state_ptr, mw, node_names_array)
final_label = _enrich_label(mw.move_type, raw_label, mw.data)
CLegalMoveView(mw, mw.move_type, final_label)
```

### 6. New file (optional): `engine_c/bindings/label_enrich.py`

If `view.py` exceeds ~400 lines, extract the enrichment into a sibling
module. Keep the surface small: one public function `_enrich_label(...)`
plus its private helpers. This keeps `view.py` focused on view-model
construction.

---

## Tests

### Update existing tests
- `engine_c/tests/test_describe.c` — add the new assertions listed in §3.

### Add Python-side tests
- `engine_c/bindings/test_label_enrich.py` (new) — pure unit tests:
  - `_enrich_label("play_card", "Play Noble", {"card_id": "noble"})`
    returns `"Play Noble"` (passthrough).
  - `_enrich_label("activate_ability", "Activate ambush",
     {"card_id": "shade_enforcer", "ability_key": "ambush"})`
    returns `"Activate Shade Enforcer's ability"`.
  - `_enrich_label("assassinate", "Remove white troop at Gauntlgrym", {...})`
    returns the input unchanged.
  - `_enrich_label("unknown", "Move", {})` returns `"Move"` (passthrough).
  - `build_c_game_view` with `node_names={"site_gauntlgrym": "Gauntlgrym"}`
    produces a `legal_moves` tuple whose `deploy` move's `label` contains
    `"Gauntlgrym"`, not `"site_gauntlgrym"`.

### Manual smoke test
- `just game-viewer` — load any board, observe the legal-moves listbox. Each
  label should read like a sentence, with site names from the board package
  and card names from the catalog.

---

## Risks

1. **Output buffer size** — the new templates are slightly longer. Current
   buffer is 256 bytes. Estimate: longest new label is
   `"Activate House Do'Urden Representative's ability"` (~55 chars) — well
   within 256. No change needed.
2. **Catalog lookup cost** — Python-side enrichment is O(1) hash lookup; no
   measurable impact. Per-move enumeration still happens once per turn.
3. **Backwards compat for tests/scripts** — any test that greps for the
   exact old strings (e.g. `"Assassinate ... slot"`) will break. The
   `test_describe.c` rewrite covers this. Other consumers:
   - `engine_c/bindings/c_adapter.py` line 97-98 logs
     `legal_moves=legal_strs[:10]` — uses the label, will now show cleaner
     strings. **Improvement, not regression.**
   - `artifacts/` replay logs store move labels. New games will have
     cleaner labels; old logs keep theirs.
4. **OpenSpiel wrapper** — uses `engine_legal_moves` but does not consume
   labels, so unaffected.
5. **Ability name stability** — if the catalog's card-name field changes,
   the enriched labels change too. That's correct (the user should see the
   current name), but worth flagging.

---

## Estimated effort

| File | LoC change |
|---|---|
| `engine_c/describe.c` | ~30 lines (template rewrites + humanize helper) |
| `engine_c/describe.h` | ~5 lines (doc comment) |
| `engine_c/tests/test_describe.c` | ~30 lines (new assertions) |
| `engine_c/bindings/view.py` | ~25 lines (plumb `node_names`, call enricher) |
| `engine_c/bindings/label_enrich.py` (new) | ~60 lines |
| `engine_c/bindings/test_label_enrich.py` (new) | ~80 lines |

Total: ~230 LoC, no engine-state changes, no public API changes
(`engine_describe_move` signature unchanged).
