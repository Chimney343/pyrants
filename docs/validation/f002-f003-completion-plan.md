# F-002 + F-003 Completion Plan

**Purpose:** `docs/validation/f002-f003-fix-plan.md` already specifies both parts to full
test-first rigor (Part A: mechanical, fully speced; Part B: a genuine engine architecture change,
design decisions recorded explicitly). That plan is **not superseded here** — this document does
not repeat its content. It states exactly what's done, what's missing, sharpens two things the
original plan left as open investigation with concrete answers found this session, and sequences
the remaining work to closure so both findings can leave the ledger as `CONFIRMED — FIXED`,
reviewed, with `verdict.md` § 5 condition 3 fully struck.

**Status snapshot (updated this session — Step 1 landed, Part B Phase 0/1 landed; `HEAD` at the
time of this update is `8f0e4c3`):**

| | Part A (F-002) | Part B (F-003) |
|---|---|---|
| Phase 0 (red baseline) | ✅ done — `baseline/f002_reroll.{pre,post}.txt` | ✅ done — GB1 baseline (`baseline/f003_chance_nodes.pre.txt`, commit `a6509b1`, re-confirmed fresh this session: 0/128 preceded by `is_chance_node()==True`) **and** T-B3's frozen legacy-path baseline (`baseline/f003_legacy_path.pre.txt`, 39 rows across all 7 effective sites, `harness/f003_legacy_baseline.py`) |
| Phase 1 (RED tests) | ✅ done — `test_determinize_reshuffle_independence.py` | ✅ done — `openspiel_pyrants/tests/test_chance_nodes.py`, 10 tests (T-B1, T-B2, T-B3, and 7 T-B5 per-site probes; T-B4 is the pre-existing `harness/f003_chance_nodes.py` script), confirmed **10/10 FAIL** for the stated reason (`is_chance_node()==False`), zero regressions in the other 78 `openspiel_pyrants/tests/` |
| Phase 2 (GREEN) | ✅ done — `engine_c/state.c::engine_determinize`, commit `e9a2702` | ❌ not started — zero diff to `engine_c/state.c`, `actions.c`, `generic_runtime.c`, `rules.c`, or `openspiel_pyrants/state_c.py`. § 2.3 below now has a concrete proposed design (`PendingChanceState`, `apply_resolve_chance`, per-site step-function shape) for M1 to implement against. |
| Phase 3 (regression guards) | ✅ done (T-A3/T-A4/T-A6 in permanent suite) | ❌ n/a yet |
| Phase 4 (re-run battery) | ✅ done — GA1 0/100 (was 100/100), GA3 3/3 (was 0/3), re-confirmed independently in `reviews/f013-review-01.md` §4b | ❌ n/a yet |
| Phase 5 (review) | ✅ **done** — `reviews/f002-review-01.md`, verdict **ACCEPTED**, recorded in `findings.md`/`verdict.md` | ❌ n/a yet |
| Phase 6 (audit record) | ✅ done — `findings.md` F-002 `Status: CONFIRMED — FIXED`, `verdict.md` § 5 condition 3 already split into 3a (struck, review-backed) / 3b (open) | ❌ n/a — F-003 `Status:` still `CONFIRMED` (not `— FIXED`) |

**Part A is fully closed** (Step 1, this session — see `reviews/f002-review-01.md`). **Part B's
Phase 0/1 are done** (Steps 3-4, this session); **Phase 2 (GREEN) is the next work**, milestone by
milestone per § 5 below, now with § 2.3's continuation-mechanism design to build against. A new,
independent finding (F-015 — Neogi's end-of-turn `force_discard` double-fires) was traced while
mapping cards to sites for this phase; see `findings.md` and § 2.3/2.4 below — it is folded into
M4, not fixed standalone.

---

## 1. Step 1 — Close Part A: a dedicated F-002 review

Part A's code is in production (`e9a2702`), its gates (GA1–GA6) are satisfied by evidence already
captured, and three *other* reviews have each independently re-run some slice of it as
blast-radius collateral without ever finding a problem:

- `f011-review-01.md` §4d — F-002 unchanged (incidental, via `findings.py`)
- `f004-review-01.md` §4d — F-002 unchanged (incidental, via `findings.py`)
- `f013-review-01.md` §4b/d — `f002b.py` unchanged, 3/3+3/3+3/3 (deliberate, in-radius)

None of that substitutes for Phase 5 being run as its **own** primary target, per this repo's own
process constraint (`f002-f003-fix-plan.md` § 0.2: "A Phase 5 review is required for each part, not
a courtesy pass") and per the adversarial-review protocol's own Hard Rule 8 (a fix isn't `ACCEPTED`
until conformance + zero regressions + zero out-of-scope hunks are each independently checked
against that fix's own diff, not inherited from someone else's).

**Action:** run a dedicated adversarial review of F-002 against the diff at `e9a2702`
(parent `2cfd836`), following the same `LOAD → DIFF AUDIT → CONFORMANCE → BLAST RADIUS → RE-RUN →
NEW FINDINGS → VERDICT → INVALIDATION CASCADE → RECORD → HANDOFF` sequence already used for
F-004/F-010/F-011/F-013. Given how much has already been independently re-confirmed, this should
be a short review — most of the RE-RUN table can cite the already-fresh numbers from
`f013-review-01.md` §4b/d rather than re-running them a fourth time, **provided** the review
explicitly states that provenance rather than silently asserting the numbers as its own fresh run
(Hard Rule 5: exact command/N/seeds/SHA — an inherited number needs its source cited, not just its
value).

**Blocking condition:** do not start Part B's implementation work (Step 3 onward) until this
review lands, per the existing plan's § 0 constraint 4 ("Part A and Part B are separate reviewable
units"). This step is cheap and should go first.

---

## 2. Step 2 — Sharpen Part B's design with this session's findings

The original plan flagged one unresolved risk explicitly (§ 20): *"the estimated radius is
optimistic — `engine_legal_moves`'s top-level dispatcher (referenced in D2) was not located during
this investigation... Fixing agent must locate it before M1."* It has now been located, and it's
more involved than the original D2 write-up assumed a single dispatcher point would be.

### 2.1 The dispatcher: `engine_c/rules.c:204`, `int engine_legal_moves(...)`

It branches on `state->phase`, and **only one branch currently checks `pending_generic`**:

| Phase | Line | Current behavior | Needs a `pending_chance` check? |
|---|---|---|---|
| `PHASE_SETUP` | 209-224 | initial-placement enumeration | No — no mid-game chance event fires here |
| `PHASE_DRAW` | 226 | **`return 0` unconditionally** | **Yes** — `draw_cards_state`'s reshuffle (M1, the plan's own first-and-simplest milestone) fires here. Today this phase is a no-decision pass-through; once M1 lands, it can no longer unconditionally short-circuit to 0 moves if a chance event is pending. |
| `PHASE_MAIN` | 228-261 | checks `pending_immediate_count`, then `pending_generic`, then normal play | **Yes** — `reshuffle_discard_into_deck` (M2) and `apply_force_discard` (M3) both fire from card-effect resolution inside this phase. `pending_generic`'s own check (line 233-234) is the closest existing precedent, but a chance event is not a player choice — reusing that exact branch would conflate the two categories D1 already warned against. Add a sibling check, e.g. `if (state->pending_chance) return legal_pending_chance_moves(...)`, ahead of or alongside the `pending_generic` check. |
| `PHASE_END_OF_TURN` | 262-276 | checks `pending_eot_count`, otherwise always returns one `MOVE_RESOLVE_END_OF_TURN` | **Yes** — this is where M4's four `generic_runtime.c` mass-discard variants (Neogi/Mindwitness/Chuul/Nothic) and `rules.c:530-538`'s likely duplicate actually resolve. Confirmed: this branch has **no** `pending_generic` check at all today, meaning these effects currently resolve entirely inline within whatever move handler triggers them — the "resolves silently" bug in the most literal sense. |
| `PHASE_CLEANUP` | 278-285 | always returns one `MOVE_RESOLVE_CLEANUP` | No — no chance event is cited at this phase by any of the ten § 1(b) sites |

**Revision to D2 and the M1–M4 milestone estimates:** this is not "one dispatcher edit" — it is
**three** phase-branch edits (`PHASE_DRAW`, `PHASE_MAIN`, `PHASE_END_OF_TURN`), landing with
whichever milestone first needs each one:
- M1 (`draw_cards_state`) needs the `PHASE_DRAW` branch's unconditional `return 0` replaced with a
  `pending_chance` check first, before returning 0.
- M2/M3 (`reshuffle_discard_into_deck`, `apply_force_discard`) need the `PHASE_MAIN` branch's new
  sibling check.
- M4 (the four `generic_runtime.c` variants + the `rules.c:530-538` duplicate) needs the
  `PHASE_END_OF_TURN` branch's new check — and this is the milestone where "is
  `rules.c:530-538` really a duplicate of a `generic_runtime.c` variant" (§ 1(d) of the original
  plan) should get resolved, since both would otherwise need independent `pending_chance` wiring
  in the same phase branch.

This does not change D1/D3/D4/D5 (the `PendingChanceState` shape, the reshuffle-as-sequential-draws
decomposition, forced-discard-as-single-node, and "all ten sites must convert") — it only replaces
the original plan's one open question ("where does the dispatcher live") with three concrete,
per-milestone edit sites, and revises the milestone sizing: M4 is now confirmed to be the largest
milestone (new phase-branch logic, not just four near-identical call-site conversions), not just
"do these last and together" for stylistic reasons as the original plan framed it.

### 2.3 D6 (new) — the continuation/resume mechanism, and a correction to M1's sizing

Neither the original plan nor § 2.1 above answers a question both need answered before M1 can be
implemented: **how does a site that currently draws its RNG value inline and keeps running in the
same C call pause mid-function, return control to Python with a chance node exposed, and then
resume the *rest* of its own work once `apply(MOVE_RESOLVE_CHANCE)` supplies the outcome?** Two of
the ten sites are not single-draw sites — `draw_cards_state`'s loop may need a reshuffle (itself
`n-1` sequential draws per D3) partway through drawing `count` cards, and each of the four
`generic_runtime.c` mass-discard variants loops "for each opponent," one draw per opponent, inside
one call. C has no coroutines; a plain `return` loses the loop's progress unless something outside
the call stack remembers where to resume.

**The engine already answers this question for player choices, and the answer is not "suspend the
call stack" — read `apply_resolve_generic_choice` → `auto_resolve_pending_generic`
(`generic_runtime.c:726` onward) closely: nothing is ever suspended. Every `apply()` starts a
*fresh* C call from `engine_apply`; all progress is tracked as explicit indices on
`PendingGenericChoiceState` (`next_action_index`, `resolve_depth`, `parent`). "Resuming" means
re-entering the same driving function from the top, where it immediately reads those indices and
skips everything already done.** D1 already says to reuse this *plumbing pattern* — this is what
that means concretely, and it is the reason a `PendingChanceState` needs more than an outcome
count: it needs enough saved progress that each multi-draw site can be rewritten as an **idempotent
step function** — given a `state` that may or may not carry a `pending_chance` continuation, do
exactly one unit of work (one RNG draw's worth), then either bail out with a freshly-populated
`pending_chance` if more units remain, or clear it and fall through to whatever runs after the
whole operation completes.

**Proposed `PendingChanceState` (recommended default, not final — same posture as D1's own
`PendingGenericChoiceState` proposal):**
```c
typedef enum {
    CHANCE_RESHUFFLE_POSITION,   /* D3: one Fisher-Yates position draw */
    CHANCE_FORCED_DISCARD,       /* D4: one uniform hand-index draw */
} ChanceEventKind;

typedef enum {
    CHANCE_SITE_DRAW_CARDS,             /* state.c:29 draw_cards_state (M1) */
    CHANCE_SITE_RESHUFFLE_DISCARD,      /* state.c:219 reshuffle_discard_into_deck (M2) */
    CHANCE_SITE_FORCE_DISCARD,          /* actions.c:404 apply_force_discard (M3) */
    CHANCE_SITE_EOT_MASS_DISCARD,       /* rules.c:530 — F-015: fold the double-fire fix in here (M4) */
    CHANCE_SITE_NEOGI_EOT_DISCARD,      /* generic_runtime.c:519 (M4) */
    CHANCE_SITE_MINDWITNESS_DISCARD,    /* generic_runtime.c:550 (M4) */
    CHANCE_SITE_CHUUL_DISCARD,          /* generic_runtime.c:593 (M4) */
    CHANCE_SITE_NOTHIC_DISCARD,         /* generic_runtime.c:635 (M4) */
} ChanceSite;

typedef struct PendingChanceState {
    ChanceEventKind kind;
    ChanceSite      site;
    Sym             target_player_id;  /* whose zone/hand this event acts on */
    int             outcome_count;     /* current chance_outcomes() length */
    int             chosen_outcome;    /* set by apply_resolve_chance before re-entering the site */

    /* CHANCE_RESHUFFLE_POSITION progress. Addressed by (target_player_id, zone-kind)
     * rather than a raw pointer — GameState is cloned-cow between apply() calls,
     * so a saved pointer into the pre-clone state would dangle. */
    int             reshuffle_position;   /* current Fisher-Yates i; counts down to 0 */

    /* Multi-target loop progress (draw_cards_state's remaining draw count; the
     * four generic_runtime.c "for each opponent" loops' player index). */
    int             loop_index;
    int             loop_remaining;
} PendingChanceState;
```

**Per-site step function shape**, illustrated on `reshuffle_discard_into_deck` (D3's own
decomposition target — the clearest case since it is exactly one Fisher-Yates shuffle, no outer
per-target loop):
```c
/* Old (state.c:219-231): shuffle_deck(...) performs all n-1 Fisher-Yates
 * draws inline, in one call. New: idempotent and re-entrant. */
void reshuffle_discard_into_deck(GameState *state, Sym player_id) {
    PlayerState *player = cow_player(state, player_id);
    if (!player) return;
    int n = player->discard_pile_count;

    if (state->pending_chance && state->pending_chance->site == CHANCE_SITE_RESHUFFLE_DISCARD) {
        /* Resuming: apply the just-declared outcome for the pending position. */
        int j = state->pending_chance->reshuffle_position;
        int chosen = state->pending_chance->chosen_outcome;
        Sym tmp = player->discard_pile[j];
        player->discard_pile[j] = player->discard_pile[chosen];
        player->discard_pile[chosen] = tmp;
        engine_free_pending_chance(state);   /* this position is resolved */
        n = j;   /* continue from the position below the one just resolved */
    } else {
        n = player->discard_pile_count;
    }

    for (int i = n - 1; i > 0; i--) {
        start_pending_chance_reshuffle(state, player_id, CHANCE_SITE_RESHUFFLE_DISCARD, i);
        return;   /* bail — pending_chance now describes position i; engine_apply
                   * returns this state to Python with is_chance_node()==True */
    }

    for (int k = 0; k < player->discard_pile_count && k < MAX_ZONE_SIZE; k++)
        player->deck[k] = player->discard_pile[k];
    player->deck_count = player->discard_pile_count;
    player->discard_pile_count = 0;
}
```
Every one of this function's 3 callers (state.c's own draw loop, `rules.c:629`, `actions.c:175`,
`actions.c:430`) must check `state->pending_chance` immediately after calling it and bail out
themselves if set — the identical "if (state->pending_generic) return state;" propagation
`engine_apply`'s existing `MOVE_RESOLVE_GENERIC` case already performs (`rules.c:730-736`) — so a
pause propagates all the way up to `engine_apply`'s return without any caller trying to keep going
past an incomplete chance sequence.

**`apply_resolve_chance`** mirrors `apply_resolve_generic_choice`'s shape (`generic_runtime.c:726`)
and slots into `engine_apply`'s switch exactly like `MOVE_RESOLVE_GENERIC` does (`rules.c:730-736`):
```c
GameState *apply_resolve_chance(GameState *state, const Move *move) {
    PendingChanceState *pc = state->pending_chance;
    if (!pc) return NULL;
    int outcome = move->data.resolve_chance.outcome_index;
    if (outcome < 0 || outcome >= pc->outcome_count) return NULL;
    pc->chosen_outcome = outcome;
    switch (pc->site) {
        case CHANCE_SITE_RESHUFFLE_DISCARD: reshuffle_discard_into_deck(state, pc->target_player_id); break;
        case CHANCE_SITE_DRAW_CARDS: /* ... re-enter draw_cards_state similarly ... */ break;
        /* ... one case per ChanceSite ... */
    }
    return state;  /* still non-NULL even if pending_chance got re-populated for the next unit —
                    * engine_apply returns this as the new "waiting" state, another chance node */
}
```

**Dispatcher, restated concretely from § 2.1:** all three new `pending_chance` checks
(`PHASE_DRAW`, `PHASE_MAIN`, `PHASE_END_OF_TURN`) reduce to one line each —
`if (state->pending_chance) return legal_pending_chance_moves(state, out, max_moves);` — where
`legal_pending_chance_moves` reads `pc->outcome_count` and fills `out[]` with
`MOVE_RESOLVE_CHANCE{outcome_index = 0..outcome_count-1}`, the same `(Move*, int) -> int` shape
`legal_pending_generic_choice_moves` already uses.

**Correction to the M1/M4 sizing in § 2.1 and the original plan's § 15:** M1 is not "smallest" in
complexity terms, only in lines-of-diff. `PendingChanceState`, `apply_resolve_chance`, all three
dispatcher edits, and the ctypes plumbing (new struct, new `Move` union member, new
`_MOVE_TYPE_MAP`/`MOVE_RESOLVE_CHANCE` entries) all have to be invented from scratch during M1,
since nothing smaller exists to build them against first — M1 carries the *machinery* risk, not
just the smallest call-site count. M2/M3 become close to mechanical once M1's machinery exists
(new `ChanceEventKind`/`ChanceSite` cases against already-proven plumbing). M4 additionally must
resolve F-015 (`docs/validation/findings.md`) as part of converting `CHANCE_SITE_EOT_MASS_DISCARD`/
`CHANCE_SITE_NEOGI_EOT_DISCARD` — tracing confirmed `rules.c:530-538` is not a duplicate
implementation but an unguarded second firing of the same `generic_runtime.c` action, so M4's
natural fix is deleting the `rules.c:530-538` block once `generic_runtime.c`'s interceptor becomes
the sole chance-exposing path for that event, rather than converting both paths independently.

### 2.4 Card → site map, needed before T-B1/T-B3/T-B5 can be written for the 8 card-triggered sites

Two of the ten § 1(b) sites (`draw_cards_state`, `reshuffle_discard_into_deck`) are pure engine
mechanics, reachable for testing via direct struct injection with no card dependency (the
`f002b.py`/`f002_reroll.py` `prep()` pattern: force an empty deck + populated discard pile). The
other 8 each require a specific card scenario. Traced this session (empirically, via
`tests/c_engine/card_test_helpers.py`-style direct construction, not just read from JSON):

| Site | Triggering card(s) | `source_fragment` |
|---|---|---|
| `actions.c:404-413` (`apply_force_discard`, random branch) | `cranium_rats` (`targeted_discard` — matches the function's own code comment, `actions.c:411`: "targeted_discard: no hand_index → pick a random card") | `targeted_discard` |
| `generic_runtime.c:519-548` (`end_of_turn_mass_discard`) | `neogi` | `end_of_turn_mass_discard` |
| `generic_runtime.c:550-591` (`conditional_owner_discard`) | `mindwitness` | `conditional_owner_discard` |
| `generic_runtime.c:593-633` (`local_discard`) | `chuul` | `local_discard` |
| `generic_runtime.c:635-665` (`mass_discard`) | `nothic` (option_2 branch) | `mass_discard` |
| `rules.c:530-538` (end-of-turn duplicate) | `neogi` (same card as the row above — see F-015: this is the double-fire, not a second card) | `end_of_turn_mass_discard` |

`umber_hulk`/`gauth` (`source_fragment: "on_opponent_discard_punish"`) also carry `op:"force_discard"`
but match none of the four `generic_runtime.c` string checks — traced as far as confirming they are
*not* intercepted by any of the four named blocks (so they fall through toward `apply_force_discard`
or a reactive-trigger path via `trigger_opponent_discard_reactive`), but the exact mechanics were
not fully traced this session; not required for the ten-site inventory (neither card is cited in
the original plan's § 1(b) table) but worth a note for whoever builds T-B5's per-site probes in case
`apply_force_discard`'s reachability needs a second confirmed card.

### 2.5 New risk, not in the original plan: interaction with F-013's board-view cache

`CEngineAdapter` (`engine_c/bindings/c_adapter.py`) gained a board-projection cache after this plan
was written (`f013-review-01.md`, commit `16f8712`), invalidated on the one mutation site,
`apply()`. Part B's new `MOVE_RESOLVE_CHANCE` moves, if they go through the same `apply()` cycle
every other move already uses (which D2 already implies — "registered in the `Move` union"), get
this invalidation for free with **zero additional code**. The risk is only if a future
implementation detail routes chance-move resolution through some *other* state-mutation path (a
second, ad hoc reassignment of `self._state` instead of the existing `apply()` cycle) — F-013's own
`test_apply_is_still_the_only_state_reassignment_site` (T5, `test_board_view_cache.py`) is a
structural trip-wire that already fails the moment a fourth `self._state = ` site is added anywhere
in `c_adapter.py`, so this risk is already caught by an existing, permanent test — **provided** Part
B's Python-side plumbing stays inside `CEngineAdapter.apply()` and doesn't bypass it. Add "T5 still
passes" to Part B's own Phase 4 re-run list (§ 17 of the original plan) as an explicit, named check,
not just folded into "the always-on battery."

---

## 3. Step 3 — Execute Part B, Phase 0 remainder

Before any GREEN code: capture the **frozen legacy-path baseline** the original plan's § 13 second
paragraph requires and T-B3 depends on (not yet done — confirmed via `Glob`, no such baseline file
exists). At a fixed `seed`, for each of the ten § 1(b) sites, log the outcome (discarded card /
resulting deck order) the *current* inline-RNG path produces, keyed by
`(site, shuffle_seed, shuffle_counter)`. This is destructive to defer: once Part B's GREEN
implementation deletes the inline-RNG path at a given site, there is nothing left to diff the new
explicit-chance path against for that site.

```
.venv/Scripts/python.exe -u docs/validation/harness/f003_legacy_baseline.py > docs/validation/baseline/f003_legacy_path.pre.txt
```

(new script, one per § 1(b) site, following `common.py`'s existing direct-struct-injection pattern
— `test_observation_completeness.py::_force_discard` is the template already used for this)

Also re-run the existing GB1 probe fresh at the same N (2,020 transitions, per `a6509b1`'s capture)
immediately before Phase 2 begins, per the original plan's § 13 first paragraph — confirms Part A
landing didn't move F-003's number (it shouldn't have; `engine_determinize` doesn't touch
`is_chance_node()`/`chance_outcomes()`).

---

## 4. Step 4 — Execute Part B, Phase 1 (RED tests)

Write T-B1 through T-B5 exactly as specified in `f002-f003-fix-plan.md` §14, confirm each fails for
the stated reason before touching any C code. No changes to that spec — it's already concrete and
matches the ten-site inventory in § 1(b).

---

## 5. Step 5 — Execute Part B, Phase 2 (GREEN), milestone by milestone

Follow the existing plan's M1→M2→M3→M4 order (§15), each with the phase-branch edit identified in
§2.1 above, each ending in its own build+test+battery cycle before the next starts:

1. **M1** — `draw_cards_state` (`state.c:29-40`) + the `PHASE_DRAW` dispatcher branch
   (`rules.c:226`). Smallest, highest-traffic, exercised by every game — do this first so any
   `PendingChanceState`/`MOVE_RESOLVE_CHANCE` plumbing mistake surfaces immediately.
2. **M2** — `reshuffle_discard_into_deck` (`state.c:219-231`) + its three callers, sharing M1's
   `PHASE_MAIN` dispatcher addition.
3. **M3** — `apply_force_discard` random branch (`actions.c:404-413`), same `PHASE_MAIN` branch.
4. **M4** — the four `generic_runtime.c` mass-discard variants + `rules.c:530-538`'s likely
   duplicate, + the new `PHASE_END_OF_TURN` dispatcher branch (`rules.c:262-276`, currently has no
   `pending_generic`/`pending_chance` check at all — confirmed §2.1). Resolve the
   duplicate-vs-distinct question for `rules.c:530-538` here, as the original plan intended.

After each milestone: `just build-c`, re-run that milestone's T-B* tests, INV-1/2/3/6, F-010's
`det_bot.py`, and (new, §2.5) F-013's T5 structural trip-wire — per the original plan's own
guidance that catching a regression at M1 is cheap and catching it after M4 means re-diffing four
milestones at once.

---

## 6. Steps 6–8 — Phases 3 through 6, as originally specified

No changes to `f002-f003-fix-plan.md` §16 (regression guards), §17 (re-run + F-008 measurement —
do not fix F-008, only record its evidence), §18 (Phase 5 review checklist, add the F-013 T5 check
from §2.5 above as an explicit new line item), or §19 (audit record: `verdict.md` § 2/§5 condition
3b, `findings.md` F-003 status flip, F-008's new `Observed:` evidence). Execute them as written.

---

## 7. Definition of done

Both findings leave the ledger only when **all** of the following hold, each independently
verifiable, not asserted:

- [x] `docs/validation/reviews/f002-review-01.md` exists, verdict `ACCEPTED` or
      `ACCEPTED-WITH-DEBT` (Step 1) — **done, ACCEPTED**
- [ ] `openspiel_pyrants/tests/test_chance_nodes.py` exists, T-B1–T-B5 all pass — **file exists,
      10/10 tests confirmed RED** (correctly failing pre-GREEN, per Phase 1); none pass yet, as
      expected before Phase 2
- [ ] GB1 (`f003_chance_nodes.py`) reports 100% of `shuffle_counter` advances preceded by
      `is_chance_node()==True`, N ≥ 2,000 — the exact inverse of the `a6509b1` red baseline
      (0/128)
- [ ] All ten § 1(b) sites individually confirmed converted (GB6/T-B5), including the
      `rules.c:530-538` duplicate resolved one way or the other, not left ambiguous
- [ ] INV-1, INV-4a/4b, INV-5, the always-on battery, F-010's `det_bot.py`, and F-013's T5 all
      re-run and unchanged from their currently-recorded values
- [ ] F-008 has new `Observed:` branching-factor evidence and an updated status (CONFIRMED or
      REFUTED, not left UNTESTABLE)
- [ ] `docs/validation/reviews/f003-review-01.md` exists, verdict `ACCEPTED` or
      `ACCEPTED-WITH-DEBT`
- [ ] `verdict.md` § 5 condition 3 shows both 3a and 3b struck/resolved
- [ ] `findings.md` F-002 and F-003 both show `CONFIRMED — FIXED (<commit sha>)`

---

## 8. Suggested session breakdown

Given Part B's own risk table already flags it as multi-milestone, do not attempt it in one
sitting:

1. **Session 1:** Step 1 (F-002 dedicated review). Cheap, unblocks nothing else but is the correct
   next action per the plan's own sequencing rule.
2. **Session 2:** Step 3 (Phase 0 remainder: legacy-path baseline script + capture) + Step 4
   (Phase 1 RED tests, all five, confirmed failing).
3. **Session 3:** M1 (`draw_cards_state` + `PHASE_DRAW` branch), full build/test/battery cycle.
4. **Session 4:** M2 + M3 (`PHASE_MAIN` branch, shared plumbing already proven by M1).
5. **Session 5:** M4 (`PHASE_END_OF_TURN` branch — the largest milestone per the revised estimate
   in §2.1 — plus the `rules.c:530-538` duplicate resolution).
6. **Session 6:** Phase 4 full re-run, F-008 measurement, Phase 5 review, Phase 6 audit-record
   update (Steps 6–7).
7. **Session 7:** Dedicated F-003 adversarial review (mirrors Step 1's format for F-002).

Each session should end able to answer, concretely, which Definition-of-Done checkboxes moved —
not "milestone M-whatever is mostly done."
