---
name: card-execution-validator
description: Validate that a Tyrants of the Underdraft card's execution model is correctly interpreted end-to-end through the C engine, the JSON catalog, and the terminal GUI. Use whenever the user is reviewing or debugging a specific card's behavior — playing out a card scenario from data/scenarios and checking whether spies, troops, draws, assassinations, promotions, VP, or resource gains happen as the rules_text says. Trigger on "this card is wrong", "card X doesn't work", "validate card", "play the aboleth scenario", "the C engine misinterprets [a named card]", "GUI shows wrong [named card] behavior", "fix card execution model", or when iterating card-by-card through the 125 scenarios. Also use when the user wants tests locking in a card's correct behavior. Works one card at a time, start to finish, even if the user names several cards or asks to "go through the deck" — see the Scope section below. Do NOT use for general engine architecture, OpenSpiel integration, board creation, or deck roster balancing.
---

# Card Execution Validator

This skill drives a **human-in-the-loop, card-by-card** review of the C engine's
card interpretation. The engine is written in C and lives in `/engine_c`; the
Python `engine/` directory is a deprecated port — never extend it. The catalog
of card execution models is `data/cards/*.json`. Each of the 125 cards has
a corresponding saved scenario the human plays through to judge correctness.

## Scope: exactly one card, start to finish

The unit of work is **one card**, not a batch. This matters because the human
review step (step 1 and step 5 below) only produces a reliable verdict when
they're looking at one card's behavior at a time — stack up several cards in a
single pass and the human's feedback stops mapping cleanly to a single fix,
and a regression is much harder to bisect later.

- **Pick one card before doing anything else.** If the human names a single
  card, that's your card. If they name several ("cards 12, 13, and 14 are all
  broken") or ask to sweep the whole deck ("go through all 125", "fix the rest
  of the batch"), say you'll work them one at a time in the order they gave
  (or number order), and start with the first one only. Don't pre-diagnose or
  touch the catalog/engine for the others yet.
- **Don't advance until the current card is actually done.** "Done" means: the
  human has explicitly accepted the behavior in the GUI (step 5) *and* a
  regression test for it exists and passes (step 6). A fix that merely looks
  right to you is not done — see "The human reviews; you don't" below.
- **Shared-code fixes are expected to help other cards — that's fine, just
  don't claim it.** Step 4 asks you to extend a shared applier/handler rather
  than write one-off C, which often means your fix incidentally corrects other
  cards using the same `op`. That's the generic interpreter working as
  intended. But "incidentally correct" isn't "verified": don't write tests for,
  mark as done, or start reviewing those other cards in the same pass. If you
  notice the fix likely affects card Y too, say so in one line and leave it
  for its own turn.
- **One card's test, one commit of understanding.** Finish the current card
  (write its test, confirm it passes) before loading the next scenario. Then
  explicitly ask the human if they're ready to move on — don't auto-advance,
  even if the next card in the numbered sequence seems obvious.

## Mental model: where a card can be wrong

A card's behavior flows through three layers. A "card doesn't work" report is
almost always a defect in exactly one of them, and diagnosing which one is most
of the job:

1. **Catalog (`data/cards/*.json`)** — the `execution_model` is the source
   of truth for what the card *should* do. If it's mis-specified, no engine can
   get it right. Symptoms: the engine faithfully executes something that isn't
   what `rules_text` says.
2. **C engine (`engine_c/generic_runtime.c` + helpers)** — interprets the
   `execution_model`. Symptoms: the catalog is right but the effect doesn't
   happen, targets are missing, the card stalls mid-resolution, or counters are
   mis-counted.
3. **GUI (`interface/game_viewer.py` + `engine_c/view.c`/`describe.c` +
   `game_view.py`)** — renders the C engine state. Symptoms: the engine state is
   correct but the human sees wrong numbers, missing highlights, or no clickable
   targets.

Keep these three layers separate in your head and in your fixes. A wrong layer
guess wastes a rebuild cycle.

## Key locations

| Thing | Path |
|-------|------|
| Per-card scenarios (one per card) | `data/scenarios/batch_card_generation/*_<card_id>.json` (e.g. `001_seed_4_aboleth.json`); also `data/scenarios/random_card_generation/` |
| Card execution models | `data/cards/*.json` (each card's `execution_model` field) |
| Effect family schema | `data/cards/effect_families.json`, `effect_families.schema.json` |
| C engine core | `engine_c/generic_runtime.c` / `.h`, `engine_c/actions.c`, `engine_c/helpers.c`, `engine_c/selection.c` |
| C state / pending choice | `engine_c/state.h` (`PendingGenericChoiceState`, `CardAction`) |
| C view + describe | `engine_c/view.c`, `engine_c/describe.c` |
| Python bindings | `engine_c/bindings/session.py` (`CSession`), `engine_c/bindings/ce_api.py` (`CEngine`), `engine_c/bindings/view.py` (`build_c_game_view`) |
| Terminal GUI (C backend) | `interface/game_viewer.py` — run with `--engine c` |
| Card behavior tests | `tests/test_engine_c.py`, `tests/test_first_ten_cards.py`, `tests/test_rules_cards_a_m.py`, `tests/test_rules_cards_n_z.py`, `tests/test_generate_card_scenarios_c.py` |
| Scenario generation | `scripts/generate_card_scenarios.py`, `engine_c/bindings/scenario_search.py` (`ensure_card_scenario_c`) |

For the full catalog schema and the op→handler dispatch table, read
`references/catalog_and_engine_map.md` when you need to diagnose a specific op.

## The per-card workflow

Run these steps for **the one card** currently in scope (see "Scope" above).
Don't skip ahead — each step feeds the next — and don't start these steps for
a second card until the first has cleared step 6.

### 1. Load the scenario and let the human play it

Find the card's scenario and hand it to the GUI on the **C engine** backend:

```bash
just build-c                       # the DLL must be current before any C run
just game-viewer                   # recipe already passes --engine c (C backend)
```

(To locate the file: `glob data/scenarios/**/*_<card_id>.json`. If no scenario
exists, generate one: `just generate-card-scenario card_id=<card_id>`.)

Tell the human: *"I've rebuilt the C engine and opened the viewer on the C
backend. Load the `<card_id>` scenario and play the card. Tell me what actually
happens vs. what `rules_text` says should happen."* Then **wait**. Do not
speculate about the fix before hearing the observed behavior — a premature guess
anchors you on the wrong layer.

If the human can't easily reach the card (not in hand, wrong phase), the
scenario is bad, not the card. Regenerate it rather than forcing a playthrough.

### 2. Capture the discrepancy precisely

Get a concrete, reproducible report from the human: expected state vs. observed
state, ideally with node ids / player ids / counts. Vague reports ("it's buggy")
are not actionable — ask for the specific effect that didn't fire or the specific
number that's wrong. Re-read the card's `rules_text` and `notes` in the catalog
yourself; the human's reading and the catalog's `rules_text` should agree, and if
they don't, that's itself a finding.

### 3. Diagnose the layer

Decide catalog vs. C engine vs. GUI using the symptom map in
`references/catalog_and_engine_map.md` and the questions below. Verify by
reading the actual source — never assume.

- **Is the `execution_model` in the per-card catalog files a faithful encoding of
  `rules_text`?** Read the card's entry. Check each `op`, `target_scope`,
  `quantity`, `filters`, and `metadata` against `rules_text`. If the encoding is
  wrong, **the fix is the catalog**, not the engine.
- **Does the C engine have a registered applier for every `op` the card uses?**
  `rg '<op_name>' engine_c/generic_runtime.c` and check
  `register_generic_actions`. An op with no applier (or a NULL/disabled branch)
  silently does nothing. **The fix is the C engine.**
- **Does the selection handler emit moves for the `target_scope`/`filters`?**
  If the GUI shows no legal target where one should exist, check
  `register_selection_handlers` and `legal_generic_target_selection_moves`.
  **The fix is the C engine selection handler.**
- **Is the engine state correct but the display wrong?** Inspect the `CState`
  (via `CSession` / `build_c_game_view`) — if the numbers there are right but
  the GUI shows different numbers, **the fix is the GUI/view projection**
  (`game_view.py`, `engine_c/view.c`, or `describe.c`).

### 4. Fix — reuse before you write

Before writing new C, find a sibling card whose `execution_model` already works
and mirror its handling. The workflow:

1. Find cards using the same `op` / `target_scope`:
   `rg '"op": "<op>"' data/cards/*.json`.
2. Find their applier in `engine_c/generic_runtime.c`:
   `rg '<op>' engine_c/generic_runtime.c`.
3. Pick the closest sibling (same scope, same quantity kind, similar filters,
   same `metadata.count_from` if any) and reuse its applier / selection handler
   / helper rather than inventing a new one.

This is important: the engine is a *generic*, data-driven interpreter. New
card-specific C is the last resort, not the first. Most "card doesn't work" bugs
are a missing branch in an existing applier or a wrong `target_scope`/`filter`
combination, fixable by extending an existing handler. Prefer extending a
shared applier over adding a per-card special case — per-card special cases
accumulate and make the next card harder.

Extending a shared applier will often touch code that other cards also rely
on — that's expected and good (see "Scope" above), but keep your testing and
sign-off focused on the one card the human is reviewing right now. Note any
other cards you suspect are now also fixed; don't go verify them yet.

When you do touch C: keep the engine pure (no I/O, no platform calls), match
`-Wall -Wextra -std=c11` / MSVC `/W3 /std:c11`, and **rebuild with
`just build-c`** before any re-test — the Python tools load `engine_c.dll` and
won't see C changes until you rebuild.

### 5. Re-test with the human

After a fix: rebuild, reload the scenario in the viewer, ask the human to replay
the card. Iterate steps 2–5 until the human accepts the behavior. Don't declare
victory on your own — the human is the acceptance gate.

### 6. Lock it in with a test (do this before moving on)

Once the human accepts the card, write a test that would fail if the behavior
regressed. Put it where it fits:

- **C-engine behavior (preferred for engine fixes):** add a case to
  `tests/test_engine_c.py` or a focused `tests/test_card_<card_id>.py` using
  `CSession` + `CEngine`, drive with `PlayCardMove` /
  `ResolveGenericChoiceMove`, assert on the `CState` projection (spies placed,
  troops assassinated, cards drawn, VP, resources). Mirror the style of
  `tests/test_first_ten_cards.py` but against the C bindings.
- **C-level only:** if the fix is purely in C and a Python-binding test would be
  awkward, add a case in `engine_c/tests/` or `engine_c/test_generic.c`, rebuild,
  run `just test-c`.
- **GUI/view fix:** add a test under `tests/test_game_view.py` or
  `tests/test_game_viewer_setup.py` asserting the projected view matches the
  engine state.

Run the new test (and the existing card suites) before declaring the card done:

```bash
.venv/Scripts/python.exe -m pytest tests/test_engine_c.py -q     # binding tests
just test-c                                                      # C tests
ruff check .                                                     # lint
```

This is the point where the current card is actually finished. Only now should
you say so and ask the human whether they want to move on to another card.

## Picking the next card

Only do this once the current card has cleared step 6 — passing test, human
sign-off — and only after the human confirms they're ready to continue. Don't
auto-advance on your own initiative, even between clearly sequential cards.

The scenarios in `data/scenarios/batch_card_generation/` are numbered
(`001_..._aboleth.json` … ~125). When the human is ready for the next card,
suggest the next untested one in number order, or whichever card they name —
but treat it as a fresh instance of this same one-card workflow, starting again
at step 1. Track progress mentally or in a short note the human keeps — this
skill doesn't own a persistent checklist file.

## Things to keep in mind

- **The human reviews; you don't.** You can and should verify your fix
  mechanically (state inspection, tests), but "the card works" is the human's
  call, made from playing the scenario in the GUI.
- **Rebuild before every re-test.** `just build-c`. Forgetting this is the
  single most common wasted cycle — the human will see stale behavior and you'll
  chase a bug that's already fixed.
- **Don't extend the Python `engine/`.** It's deprecated. Fixes go in
  `engine_c/` and (for display) `interface/` / `game_view.py` / the C view.
  Engine purity (`tests/test_engine_purity.py`) must stay green.
- **Generalize the fix, but don't generalize the scope of review.** A fix that
  only makes *this* card work is a liability — extend the shared interpreter so
  the next card with the same pattern works for free. But "the next card" still
  gets its own turn through steps 1–6; a shared fix is not a shortcut past human
  review for the cards it happens to also help.
- **Keep `rules_text` and `execution_model` in agreement.** If you change the
  catalog, re-read `rules_text` to confirm the encoding still matches; if they
  can't agree, surface that to the human rather than silently picking one.
