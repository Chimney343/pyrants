# ADR-0002: Postpone F-003 (mid-game chance-node exposure) as accepted architectural debt

- **Status:** Active
- **Date:** 2026-09-02
- **Decision owner:** Chimney343
- **Supersedes:** —
- **Superseded by:** —

## Context

`docs/validation/verdict.md` § 5 condition 3 groups two findings under one gate:

- **F-002** (`findings.md`) — `engine_determinize` never rerolled `shuffle_seed`/`shuffle_counter`,
  so every ISMCTS-sampled determinization of one information set shared the same mid-game
  reshuffle/forced-discard outcome. **Fixed** (`e9a2702`) and independently reviewed
  **ACCEPTED**, no debt (`docs/validation/reviews/f002-review-01.md`).
- **F-003** (`findings.md`) — mid-game random events (discard-pile reshuffles, forced random
  discards, four card-effect mass-discard variants) are never exposed as OpenSpiel chance nodes;
  they resolve silently inside whichever `apply_action` triggered them. `docs/ismcts-paper.md`
  § III-C-2 excludes the *initial* deal from the search tree for one stated reason — "since this
  occurs before any player has made a decision" — and does not extend that exemption to chance
  events that happen after decisions have already been made. F-003 is exactly that latter class.
  Confirmed empirically: 134/2,112 `shuffle_counter` advances, 0 preceded by
  `is_chance_node()==True`.

`docs/validation/f002-f003-completion-plan.md` (this session) closed F-002's own review gap and
then scoped F-003's remaining work (its "Phase 2," the actual engine change) in detail before
starting it:

- **Phase 0/1 (baseline + RED tests) are done, committed, and safe** — a frozen legacy-path
  baseline for all 7 effective call sites (`docs/validation/baseline/f003_legacy_path.pre.txt`)
  and 10 RED tests (`openspiel_pyrants/tests/test_chance_nodes.py`), confirmed failing for the
  correct reason, zero regressions elsewhere. Nothing here needs to be undone by this decision.
- **Phase 2 (GREEN) turned out to need machinery that does not exist yet, invented from scratch.**
  Two of the ten sites draw more than one random value across a single C call with no return to
  the caller in between; exposing them as real chance nodes needs a suspend/resume mechanism (C
  has no coroutines) mirroring how `PendingGenericChoiceState` already handles multi-step player
  decisions — a new struct, a new move type, three separate dispatcher edits
  (`engine_legal_moves`'s `PHASE_DRAW`/`PHASE_MAIN`/`PHASE_END_OF_TURN` branches), new ctypes
  plumbing, and ten call-site conversions, each needing its own build+test+battery cycle
  (`f002-f003-completion-plan.md` § 2.1/§ 2.3). This is a genuine multi-session engineering effort,
  sized by investigation, not by guess.
- **A live, unrelated bug (F-015) surfaced as a byproduct** while mapping cards to call sites —
  Neogi's end-of-turn `force_discard` fires twice per play. Tracked independently; not gated on
  this decision.
- **The actual benefit is unmeasured.** F-008 (whether the branching factor at these nodes is
  small enough for the paper's own exploration technique to handle) is explicitly deferred until
  *after* F-003 lands — meaning nobody has evidence today of how much value-estimate distortion
  F-003 actually causes in practice. It is a confirmed *structural* conformance gap against the
  paper, not a demonstrated *magnitude* of harm.
- **`verdict.md`'s own GO conditions already scope what F-003 blocks.** 2-player engine and
  performance work (correctness, throughput, crash-rate, memory) is already cleared to proceed
  without it. F-003 (and F-002, which is now resolved) only gate *strength, policy-quality, or
  agent-training claims* made from ISMCTS search output.

Given a large, certain cost against an unmeasured benefit that does not block the work currently
in front of this project, continuing Phase 2 immediately is not the right call.

## Decision

**Postpone F-003's Phase 2 (GREEN implementation) indefinitely.** F-003 is accepted, tracked
architectural debt — not scheduled work, not abandoned. Phase 0/1's artifacts stay in the tree
as ready-to-resume groundwork: the frozen legacy baseline, the RED test suite, and the proposed
`PendingChanceState`/dispatcher design (`f002-f003-completion-plan.md` § 2.3) mean a future
session does not have to re-derive the card→site mapping or the continuation-mechanism design
from scratch. Phase 2 is not scheduled until there is a concrete, current need to make an ISMCTS
strength/policy-quality/agent-training claim from this engine — the one thing F-003 actually
gates.

### Plain-language summary

**Normal version:** F-003 is a real conformance gap against the paper's treatment of chance
nodes — mid-game random events still get folded invisibly into whatever move triggered them
instead of appearing as their own branch in the search tree, so the search can't cleanly separate
"this move was good" from "this move happened to be followed by a lucky or unlucky random event."
Closing it requires building new engine machinery from scratch (a suspend/resume mechanism, since
C has no coroutines) across ten call sites — a multi-session effort. The resulting benefit has
never been measured (that measurement is F-008, deliberately deferred until after this lands),
and the fix is not required for any of the engine/performance work this project is doing right
now — it only matters before trusting ISMCTS-produced strength or policy-quality numbers. Given
unmeasured benefit and high, certain cost, it stays parked until that specific need exists.

**Caveman version:** Dice roll happen mid-turn. Tree no see dice roll — tree think "move good" or
"move bad" but really just got lucky/unlucky roll after move, tree confused. Paper say: roll
*before* anyone choose anything, tree can ignore; roll *after* choice, tree must see it. We already
fixed worse bug — dice used to give SAME roll to every guess, now guesses get different rolls
(good). Making tree actually see the roll = build brand new engine muscle from zero, touch ten
places, many moons of work. Nobody know yet how much this actually hurts brain-smart-number.
Not stopping anything we do today. Skip for now. Come back when we need to prove brain is smart.

## Consequences

### Positive

- Frees this project's effort for engine/performance work, which was never blocked by F-003 in
  the first place (per `verdict.md`'s own conditions).
- The postponement is explicit and reversible, not a silent drop: the RED tests, frozen baseline,
  and design stay in the tree, so resuming later starts from a scoped Phase 2, not from zero.
- Matches how this ledger already treats comparable residual debt (e.g. F-013's throughput gap) —
  tracked, visible, not blocking, not hidden.

### Negative

- Any ISMCTS strength/policy-quality/agent-training claim made from this engine remains formally
  unverified against the paper's chance-node requirement for as long as this stays postponed.
- F-008 (chance-node branching factor) stays `UNTESTABLE` indefinitely — it has no evidence to
  measure until F-003's chance nodes exist.
- `verdict.md` § 5 condition 3 cannot be marked fully resolved (3a struck, 3b postponed, not
  struck) while this decision stands, so a strict "every condition cleared" GO cannot be declared.

### Neutral

- F-015 (Neogi's end-of-turn `force_discard` double-fire), found while scoping this work, is a
  real, independent correctness bug and is tracked on its own schedule — this decision does not
  postpone it.

## Alternatives Considered

1. **Complete Phase 2 now, as the original fix plan intended.** Rejected for now: the
   investigation confirmed a genuine multi-session cost against an unmeasured benefit, for a gap
   that does not block the work currently in front of this project.
2. **A cheaper partial/approximate mitigation short of full chance-node exposure.** Considered; no
   approximation was identified that would satisfy what the paper actually requires (separate
   tree statistics per branch) — anything short of real chance nodes would add complexity without
   resolving the conformance question, trading one kind of debt for another without measurable
   benefit. Not adopted.
3. **Drop F-003 from the ledger entirely.** Rejected: the underlying conformance gap is real and
   was correctly diagnosed against the paper; removing it would misrepresent this project's own
   validation findings. Tracked as postponed, not deleted.

## Compliance

- `docs/validation/findings.md` F-003's `Status:` line and a new dated Decision entry reference
  this ADR.
- `docs/validation/verdict.md` § 5 condition 3b is annotated **POSTPONED (ADR-0002)** rather than
  left looking like still-in-progress open work.
- `docs/validation/f002-f003-completion-plan.md` is left as-is (not deleted) as the resumption
  reference — its Phase 0/1 completion, § 2.3 design, and § 2.4 card→site map are exactly what a
  future session resuming Phase 2 would need.

## References

- `docs/validation/findings.md` F-002, F-003, F-008, F-015
- `docs/validation/verdict.md` § 5 condition 3
- `docs/validation/f002-f003-fix-plan.md`, `docs/validation/f002-f003-completion-plan.md`
- `docs/ismcts-paper.md` § III-C-1/III-C-2
- `docs/validation/reviews/f002-review-01.md`
- `docs/validation/baseline/f003_legacy_path.pre.txt`,
  `openspiel_pyrants/tests/test_chance_nodes.py`
