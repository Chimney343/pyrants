# Custom IS-MCTS Evaluators — Concepts

## Purpose

Explore the catalog and propose three custom evaluator designs that bias
IS-MCTS rollouts toward playing complicated, interesting cards. Each
evaluator replaces `RandomRolloutEvaluator` in `scripts/run_ismcts.py`
without touching `engine/` or `openspiel_pyrants/`.

## Catalog findings

The 125-card catalog splits into three execution kinds:

| Kind | Count | Behavior |
|------|------:|----------|
| `sequence` | 89 | Linear action chain; agent picks targets for each step. |
| `modal_choice` | 35 | Two options, agent picks one. |
| `repeat_choice` | 1 | One option chosen `repeat_count` times. |

Aspect spread: guile 31, malice 30, conquest 31, ambition 28, obedience 4, - 1.

Modal cards split by dominant mechanic:

- **Spy-chain** (place_spy vs return_spy + payoff): cloaker, conjurer, enchanter_of_thay, mind_flayer, air_elemental, aboleth, marilith, grazzt.
- **Resource vs board action** (gain_resource vs assassinate/devour): blackguard, inquisitor, wight, advocate.
- **Devour combo** (devour_cost prefix + modal payoff): mind_flayer, wight, aboleth.
- **Promote vs recruit** (end-of-turn promote chains): advocate, ambassador (sequence), marlos_urnrayle (sequence).

Inner-circle VP often exceeds deck VP by 2–3× (aboleth 4/7, wight 1/3,
mind_flayer 1/3, cloaker 1/3, beholder 3/6). Random rollouts almost never
realize the inner-circle value because the promote step is buried at the
end of a sequence or a modal option the rollout skips.

## Design constraints

- Plug into `RandomRolloutEvaluator`'s slot in `ISMCTSBot` — must implement
  the `Evaluator.evaluate(state, action=None)` interface and return a list
  of per-player returns.
- Must respect the determinization already in place
  (`openspiel_pyrants/state.py:160` and `determinization.py`).
- Must not mutate the input state; clone via `state.clone()` before
  rolling out.
- Rollout policy has access to the move type and the engine state via
  `state._engine` (Python backend) or `state._adapter` (C backend), as in
  `scripts/run_ismcts.py:_action_to_move`.

## Evaluator 1 — ModalCuriosityEvaluator

**Bias:** prefers rollouts that *encounter* pending modal choices, and
prefers rollouts that take the *stronger* modal option when both are
legal.

**Mechanism:**

1. Run a normal random rollout.
2. Count `modal_hits`: the number of `pending_generic_choice` states
   visited where `awaiting_option=True`.
3. Count `modal_resolved`: how many of those resolved into a *non-trivial*
   option (an option whose action list has ≥ 2 ops or includes a
   `devour_cost`, `supplant_troop`, `return_spy`, or `promote_card` op).
4. Return bonus = `0.05 * modal_resolved` added to the active player's
   return before zero-sum reflection.

**Why interesting:** the catalog's "interesting" cards are the modal ones.
This evaluator makes any rollout that *reaches* and *exercises* a modal
choice look more valuable. States that buy modal cards into hand get
inflated rollout scores, so the tree prefers those buy lines.

**Risk:** the bonus is an additive constant on the return, not the
outcome. Use a small constant (0.05) so the terminal score still
dominates. Log `modal_hits` and `modal_resolved` per rollout for
post-hoc calibration.

## Evaluator 2 — DevourChainEvaluator

**Bias:** when a `resolve_generic_choice` move is legal, the option whose
action chain contains `devour_cost` is weighted 5× higher in the rollout
policy.

**Mechanism:**

1. Build a weighted rollout policy at each step.
2. Inspect each legal action's move type:
   - `play_card` → weight 1.0.
   - `resolve_generic_choice` whose move decodes to
     `option.actions[*].op == "devour_cost"` → weight 5.0.
   - `resolve_generic_choice` without `devour_cost` → weight 1.0.
   - `recruit` → weight 1.5 (sets up future hand).
   - `end_main_phase` → weight 0.2.
   - `deploy` / `assassinate` / `return_spy` → weight 1.0.
3. Sample one legal action proportional to weight.
4. Roll to terminal. Return plain `state.returns()`.

**Why interesting:** `mind_flayer`, `wight`, and `aboleth` all have
`devour_cost` modal options (devour a card from hand, then gain resource /
assassinate / supplant). Random rollouts never chain the devour
discipline — the hand almost never has a discardable card at the right
moment. The 5× weight forces the rollout to keep the devour option
available in hand, exposing the combo's true value to the tree search.

**Risk:** the weight is hard-coded. Could be parameterized
(`--devour-weight`) in `run_ismcts.py` like the existing
`--rollout-count`.

## Evaluator 3 — InnerCircleClimberEvaluator

**Bias:** rollouts prefer the action that promotes a played card, when
such an action is legal. Bias applies to both the sequence-style
`promote_card` action and the modal `promote_end_of_turn` option.

**Mechanism:**

1. At each rollout step, classify every legal action by
   `move.move_type` and the move's decoded payload:
   - `play_card` → weight 1.0.
   - `resolve_generic_choice` whose option's actions include
     `promote_card` (anywhere in the chain) → weight 4.0.
   - `activate_card_ability` whose `ability_key` ends in `_promote` or
     has `promote` in the resolved action op list → weight 3.0.
   - `promote_card` (rare direct move) → weight 4.0.
   - `recruit` → weight 1.2 (future promote fuel).
   - All other actions → weight 1.0.
   - `end_main_phase` → weight 0.3 (don't waste the main phase before
     promoting).
2. Sample weighted. Roll to terminal. Return plain `state.returns()`.

**Why interesting:** the catalog's strongest cards (aboleth 4/7, beholder
3/6, marlos 2/5, mind_flayer 1/3) all pay 2–3× more VP once promoted
to inner circle. Random rollouts undervalue promotion because the
`promote` step is buried at the end of a 2–3-step sequence or hidden
inside a modal option. The 4× weight forces the rollout to attempt the
promote line, surfacing the inner-circle value the tree search would
otherwise miss.

**Risk:** the rollout might starve itself of troops/power by refusing
to deploy. The 1.0 default weight on `deploy` and the 0.3 weight on
`end_main_phase` should keep the rollout playing, but expose
`--promote-weight` as a CLI knob for tuning.

## Cross-cutting notes

- All three evaluators can share a small `_WeightedRolloutPolicy` helper
  that maps `move_type` (and optional decoded payload) → weight, then
  samples with `numpy.random.Generator.choice`. Decoding the move uses
  `openspiel_pyrants.action_encoding.action_to_move` (the helper
  `_action_to_move` in `scripts/run_ismcts.py:185` already handles
  Python and C backends).
- All three can be selected by adding a `--evaluator {random,modal,
  devour,inner_circle}` flag to `run_ismcts.py`, defaulting to `random`
  so existing runs are unchanged.
- Each evaluator logs a per-rollout trace (counts, weights used) into a
  new `evaluator_trace.jsonl` in the game output directory for offline
  analysis.

## Where this lives after implementation

The new evaluator classes belong in `scripts/ismcts_evaluators.py` (a new
module — currently `scripts/` has no such file). `run_ismcts.py` imports
them by name. No changes to `engine/` or `openspiel_pyrants/` are
required because the evaluators consume the public `pyspiel.State`
interface.

## Implementation outline (future work)

1. Create `scripts/ismcts_evaluators.py` with:
   - `_WeightedRolloutPolicy` (shared).
   - `ModalCuriosityEvaluator`, `DevourChainEvaluator`,
     `InnerCircleClimberEvaluator`.
2. Extend `run_ismcts.py` with `--evaluator` and per-evaluator weight
   flags. Wire into both the standalone and root-parallel workers
   (`_ismcts_worker_loop`).
3. Add `evaluator_trace.jsonl` writer to both code paths.
4. Add a smoke test in `openspiel_pyrants/tests/` that runs 1 game per
   evaluator with `--num-sims 5 --num-games 1` and asserts the trace
   file exists with the right schema.
5. Document the evaluators in a new `docs/ismcts-evaluators.md`
   (consumer-facing) — this plan file stays in `.kilo/plans/`.

## Verification

For each evaluator:

- Run `python -m scripts.run_ismcts --evaluator X --num-sims 50
  --num-games 1 --seed 42` and confirm the game completes and writes
  `evaluator_trace.jsonl`.
- Compare the trace's modal-hit / devour-pick / promote-pick counts
  against the `random` baseline. Expect:
  - `modal`: ≥ 2× the baseline modal hits.
  - `devour`: ≥ 3× the baseline devour-option picks.
  - `inner_circle`: ≥ 2× the baseline promote-action picks.
- Replay one game through the existing `just replay-viewer` for each
  evaluator and confirm the trace is consistent with the replay log.

## Out of scope

- Modifying `engine/` or `openspiel_pyrants/`.
- A learned value function or NN evaluator.
- Custom UCB bonuses (a separate Approach 2 from the prior discussion;
  requires subclassing `ISMCTSBot` and changing the tree topology, so
  deferred).
