# Move-Label Clarity Improvements (C engine + Python enrich layer)

## Goal
Improve player-facing clarity of legal-move labels in the GUI. Labels flow from the C engine's `engine_describe_move` (`engine_c/describe.c`) and are post-processed by Python `enrich_label` (`engine_c/bindings/label_enrich.py`), which the GUI always invokes (`engine_c/bindings/view.py:213`). `enrich_label` bails (returns the raw C label) for the targeting ops `assassinate_troop`, `supplant_troop`, `move_troop`, `return_unit`, and steal-custom-effects — so those reach the player as the C string.

Scope is "clarity first": wording and consistency only. The overloaded `target_id` string-encoding channel is left in place (hardening is explicitly out of scope).

## Key facts established
- GUI always passes `node_names` from the layout (`interface/game_viewer.py:606,1235`); layout labels are already curated (`data/layouts/tyrants_of_the_underdark_layout.json` — e.g. `"Gauntlgrym"`, `"Halls of the Scoured Legion"`). So the C `_humanize_id` site-prefix/title-case bug is **dead in the GUI**; do not "fix" it.
- Player ids are `p1`–`p4` (verified in scenarios/state JSON). They reach troop/spy labels **un-humanized** via `intern_str` in `troop_owner_label` and the `return_spy` spy_owner path.
- `_sym_str(SYM_NULL)` returns `None` (`engine_c/bindings/ce_api.py:74`), so a null `action_id` move triggers the Python `if not action_id:` skip branch (`label_enrich.py:244`) — the C `"Skip (resign)"` is dead in the GUI.
- `_humanize_id` (`describe.c:20`) title-cases only the first char → `p2` → `P2`, inconsistent with the planned `Player 2`.
- Trophy occupants for captured units are player ids (`trophy_hall: ["p4","white"]` in scenario data); `_humanize_id` renders them `P4`, inconsistent with troop labels.
- The `"troop"` trophy-type defaults (`describe.c:255,278`) and the `Return unit` fallback (`describe.c:200-205`) are dead defensive code (selectors guarantee valid occupants/payloads); left unchanged.

## Changes

### Change 1 — Align Python op description for supplant (Python-only)
`label_enrich.py:25`: `"supplant_troop": "Replace troop"` → `"supplant_troop": "Supplant troop"`.
Rulebook jargon is retained; the C targeting move already says "Supplant". No test asserts the "Replace" string (`test_label_enrich.py:117` only checks the card name).

### Change 2 — Assassinate targeting → "Assassinate ... at" (C + C test)
- `describe.c:109` (`MOVE_ASSASSINATE`): `"Remove %s troop from %s"` → `"Assassinate %s troop at %s"`
- `describe.c:168` (`MOVE_RESOLVE_GENERIC`/`assassinate_troop`): same old → new
- `engine_c/tests/test_describe.c:127`: `assert(strstr(buf, "Remove") != NULL)` → `assert(strstr(buf, "Assassinate") != NULL)`
Matches the rulebook verb and the Python `_OP_DESCRIPTIONS["assassinate_troop"] = "Assassinate troop"`. Aligns preposition with the Supplant move (`at`). The `return_unit`/steal "Remove" labels (asserted at `test_label_enrich.py:24`) stay unchanged.

### Change 3 — Disambiguate "Skip" (Python + C)
Optional-action decline vs degenerate skip are distinct; `CardAction.optional` is exposed (`engine_bindings.py:86`) and `current_action` is already fetched at `view.py:194`.
- `view.py:213` (the `enrich_label` call): pass a new kwarg `is_optional_action` (bool), read from `current_action.optional` when `current_action` is available and `action_id` is null.
- `label_enrich.py:207`: add kwarg `is_optional_action: bool = False`. In the `if not action_id:` branch (lines 244-250): when `is_optional_action` is True and a `card_action` desc exists, return `f"Decline {desc} for {card_name}"`; otherwise keep `Skip <desc> for <card>` / `Skip for <card>`. `Decline` matches `MOVE_DECLINE_ABILITY`'s verb.
- `describe.c:145`: `"Skip (resign)"` → `"Skip"` (belt-and-suspenders cleanup for headless/tests; dead in GUI).

### Change 5 — Align C gain_resource capitalization to lowercase (C-only)
`resource` stays singular (no pluralization). `label_enrich.py:111` already lowercases the resource string (`Gain 2 power`).
- `describe.c:348-351`: remove the title-case line `rbuf[0] = toupper(...)`; emit the raw lowercased `res`. Result: C produces `Gain 2 power` / `Gain 2 resource`, matching Python.

### Change 6 — Humanize player ids via `_player_label` (C-only, introduces helper)
Add a static helper after `_humanize_id` in `describe.c`:
```c
static const char *_player_label(const char *id_str) {
    if (id_str && (id_str[0]=='p'||id_str[0]=='P') && id_str[1]>='0' && id_str[1]<='9') {
        static char buf[32];
        snprintf(buf, sizeof(buf), "Player %s", id_str+1);
        return buf;
    }
    return id_str ? id_str : "unknown";
}
```
Rule: `p<N>` (case-insensitive) → `Player <N>`; otherwise passthrough (so `white`, `empty`, `unknown` are preserved). Apply at:
- `describe.c:62`: `return intern_str(owner);` → `return _player_label(intern_str(owner));`
- `describe.c:118`: spy_owner → `_player_label(intern_str(move->data.return_spy.spy_owner_id))`
The `move_troop` and `return_unit` owner strings all flow through `troop_owner_label`, so they inherit the fix.
Note: `_player_label` uses a static buffer like `_humanize_id`; acceptable since these labels are produced one at a time into a 256-byte output buffer (existing pattern).

### Change 7 — Trophy-occupant labels use `_player_label` (C-only, reuses helper)
Replaces `_humanize_id` with `_player_label` at three sites so captured player units render as `Player N` consistent with troop labels:
- `describe.c:254` (trophy-hall owner `sp_label_buf`): `_humanize_id(intern_str(aid))` → `_player_label(intern_str(aid))`
- `describe.c:264` (`select_trophy_hall` occupant): `_humanize_id(oc)` → `_player_label(oc)`
- `describe.c:305` (`steal_from_selected_trophy` occupant): `_humanize_id(oc)` → `_player_label(oc)`
The `white` occupant branches (lines 261, 302) set the literal `"white"` and are untouched; `_player_label` passes `"white"` through unchanged.

### Change 8 — Reword live `Resolve` fallback → `Choose for <name>` (Python-only)
The GUI always has `source_card_id` populated (`view.py:189`), so Levels 4/5 (`label_enrich.py:312,315`) are dead in the GUI; only Level 2/3 (`:301,:307`) is the live floor.
- `label_enrich.py:301`: `f"Resolve {name} choice"` → `f"Choose for {name}"`
- `label_enrich.py:307`: same
Dead Level 4/5 strings left as-is (out of scope).

## Order of implementation
1. Change 6 first (introduces `_player_label` helper).
2. Change 7 next (reuses the helper).
3. Changes 2, 5 (other C edits).
4. Rebuild C: `just build-c`.
5. Run C tests: `just test-c`; fix the `test_describe.c:127` assertion per Change 2 and any trophy/owner assertions that now expect `Player N` instead of `P`/raw ids.
6. Python-only changes 1, 3, 8.
7. `just test-c-python`, `ruff check .`.

## Validation
- `just build-c` (required after any C edit)
- `just test-c` — C suite; specifically `test_describe_assassinate` and `test_describe_assassinate_no_slot_index` (`test_describe.c:93,137`)
- `just test-c-python` — runs `tests/test_engine_c.py` exercising `enrich_label`
- `ruff check .`
- Update assertions in `engine_c/bindings/test_label_enrich.py` and `engine_c/tests/test_describe.c` where expected strings change (Changes 1, 2, 6, 7). Change 3 and 8 should get new assertions for the `Decline`/`Choose for` paths.

## Risks / notes
- `_player_label` static buffer is shared — safe under the existing single-label-at-a-time formatting contract but not thread-safe (matches existing `_humanize_id` precedent).
- Change 3 adds a kwarg to `enrich_label`; all existing callers pass it via default — only `view.py` is updated to supply it. The non-GUI callers in `test_label_enrich.py` keep working with the default `False`.
- No data-format or move-encoding changes; `target_id` payload parsing is untouched.
- Out of scope: robustness hardening of `target_id` parsing, pluralization of `resource`, the dead `Return unit` and `troop`-default fallbacks, the `_humanize_id` node-label path (dead in GUI).
