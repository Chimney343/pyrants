# Validation Findings — Engine / OpenSpiel / ISMCTS / Rulebook / Whitepaper

Static, read-only audit. No files outside `docs/validation/` were modified. No simulations or builds were run.

## 1. Path Map (Phase 0)

Read `justfile` in full (140 lines) and its recipe bodies; `just --list` was not additionally run since every recipe body was already read verbatim.

| Component | Actual path(s) | Notes |
|---|---|---|
| Engine core | `engine_c/state.c`, `state.h`, `phases.c`, `actions.c`, `rules.c`, `rng.c`/`rng.h`, `scoring.c`, `generic_runtime.c`, `rollout.c`, `arena.c`, `selection.c`, `moves.c` | C, built via `engine_c/compile.bat` (`just build-c`) |
| Python↔C bindings | `engine_c/bindings/engine_bindings.py` (ctypes), `ce_api.py` (`CEngine`/`CState`), `c_adapter.py` (`CEngineAdapter`), `view.py`, `session.py` | |
| OpenSpiel binding layer | `openspiel_pyrants/game_c.py` (`PyrantsCGame`), `state_c.py` (`PyrantsCState`), `action_encoding_c.py`, `observer_c.py`, `c_rollout_evaluator.py`, `__init__.py` (registers `python_pyrants_c`) | |
| ISMCTS implementation | **Not in this repo.** Stock `open_spiel.python.algorithms.ismcts.ISMCTSBot` at `.venv/Lib/site-packages/open_spiel/python/algorithms/ismcts.py`, driven unmodified by `scripts/run_ismcts.py` | No custom ISMCTS search code exists in-repo; `openspiel_pyrants/c_rollout_evaluator.py` supplies only the leaf-evaluation rollout, not the tree search |
| Card / rules data | `data/cards/*.json` (catalog), `data/boards/tyrants_of_the_underdark.json`, `data/decks/base_setup.json`, `data/layouts/*.json` | |
| Tests / fixtures | `tests/c_engine/*.py` (per-card behavior tests), `tests/test_run_ismcts_*.py`, `openspiel_pyrants/tests/*`, `engine_c/test_*.exe` (C-level tests via `just test-c`), `data/scenarios/{batch_card_generation,test_card_generation,random_card_generation,cards}` | |
| Simulation entry point | `scripts/run_ismcts.py` (invoked by `just ismcts` / `just ismcts-quick`), output to `artifacts/ismcts/<run>/{steps,decisions}.jsonl` | Default `just ismcts` recipe runs **4 players** (`justfile:63`) |
| Rulebook | `docs/tyrants-rulebook.md` (581 lines) | |
| Whitepaper | `docs/ismcts-paper.md` — Cowling, Powley & Whitehouse, "Information Set Monte Carlo Tree Search" | Full text incl. Appendix pseudocode |

All six required components exist; none had to be substituted.

## 2. Summary Table

| ID | Class | Severity | One-line claim |
|---|---|---|---|
| F-001 | OPENSPIEL-ISMCTS | CRITICAL | Legal-action integer IDs are not stable across states in the same information set, but `ISMCTSBot` keys all tree statistics by raw action ID |
| F-002 | OPENSPIEL-ISMCTS | CRITICAL | `engine_determinize` reshuffles hidden zones with a fresh per-simulation seed but never rerolls `shuffle_seed`/`shuffle_counter`, so every later in-rollout reshuffle/random-discard collapses onto one shared outcome across all sampled worlds |
| F-003 | ENGINE-OPENSPIEL | CRITICAL | Mid-game random events (discard-into-deck reshuffle, forced random discard, card-effect mass-discards) are never exposed as OpenSpiel chance nodes |
| F-004 | ENGINE-OPENSPIEL | CRITICAL | `Returns()`/`UtilitySum`/`MinUtility`/`MaxUtility` contract is violated for the 3–4 player game (the project's own default configuration) |
| F-005 | RULE-ENGINE | MAJOR | Rulebook requires random first-player selection; engine always seats `player_ids[0]` |
| F-006 | PAPER-CODE | MAJOR | Default `uct_c=1.4` (generic √2 UCT) is used instead of the paper's calibrated `0.7` |
| F-007 | SPEC-GAP | MINOR | Discard-pile contents are treated as hidden (pooled into the shuffled/indistinguishable set) with no rulebook passage confirming or denying discard-pile visibility |
| F-008 | PAPER-RULE | MINOR | The paper's chance-node exploration technique is designed for ≤4-outcome chance nodes; this game's (currently unexposed, see F-003) analogous events have much larger branching |
| F-009 | ENGINE-OPENSPIEL | MINOR | `max_chance_outcomes` is hardcoded to 1000 independent of the configurable `shuffle_seed_count` game parameter |
| F-010 | OPENSPIEL-ISMCTS | CRITICAL | *(found empirically, not in the static pass)* ISMCTS determinization seeds come from an **unseeded** `pyspiel.UniformProbabilitySampler`, so `--seed` does not reproduce a run |
| F-011 | ENGINE-OPENSPIEL | CRITICAL | *(found empirically, not in the static pass)* The entire board — sites, troops, spies, control — is absent from `information_state_string`/`observation_string` |
| F-012 | OPENSPIEL-ISMCTS | MINOR | *(found by Review 01 of F-010, not in the static pass)* `resample_from_infostate`'s accept-branch and its own error message both claim `numpy.random.Generator` works, but the branch body calls `.randint()`, which `Generator` does not have |
| F-013 | ENGINE-OPENSPIEL | MINOR | *(found by the F-011 fix)* routing `build_c_board_view` into `private_view_json` costs ~388 µs/call and regresses search wall-time 9.66×; needs a narrower C-level board-only accessor |

## 3. Findings

### F-001 Action-ID space is not information-set-stable, but ISMCTSBot keys tree statistics by raw action ID
- Class: OPENSPIEL-ISMCTS
- Severity: CRITICAL (invalidates results)
- Code: `openspiel_pyrants/action_encoding_c.py:24-36` behaviour: `compute_c_action_map` assigns action IDs via `enumerate()` over that state's own `legal_moves()` order; docstring: "Indices are recomputed per state and never persist across determinizations"
- Rulebook: [absent] — not a rulebook-governed concern
- Whitepaper: `docs/ismcts-paper.md` § IV-B Subset-Armed Bandits: "a branch for every action that is legal in some state" [implies one stable action identity shared across an information set's states]
- Disagreement: `.venv/Lib/site-packages/open_spiel/python/algorithms/ismcts.py` stores per-action statistics in `node.child_info[action]` keyed by the raw integer (`expand_if_necessary`, lines 278-284; `run_simulation`, lines 355-384). Since `scripts/run_ismcts.py:390-399` never passes `allow_inconsistent_action_sets=True`, `select_action_tree_policy` (ismcts.py:286-297) takes the `else` branch and calls `select_action(node)` directly on the **unfiltered** `node.child_info`, with no check that the chosen action ID is even legal in the currently-sampled determinized state. `check_expand` (ismcts.py:336-345) only compares `len(node.child_info) == len(legal_actions)` — a count, not an identity check. The chosen integer is then applied via `state.apply_action(chosen_action)` (ismcts.py:381) to whatever world this simulation sampled, where that integer may denote a completely unrelated move.
- Steelman: If the C engine's internal move-enumeration order happens to be stable in practice across the hidden-card permutations that actually occur (e.g., iteration always proceeds site-by-site / catalog-order first, hand-dependent options second), drift might be rare enough not to matter for early, low-branching decisions.
- Falsification test: From one information-state root, call `resample_from_infostate` twice with two different seeds; diff `compute_c_action_map(adapter)`'s `(index, move_type, target)` tuples at the same index across the two resulting adapters, for several indices and several depths into the game.
- Expected if REAL: A meaningful fraction of indices map to different move types/targets between the two determinizations of the same information set (e.g. index 3 = "recruit noble" in one world, "assassinate troop" in another).
- Expected if FALSE POSITIVE: The move at each tested index is consistently the same move type/target across all sampled determinizations of a given information set.
- Status: **REFUTED**
- Command: `.venv/Scripts/python.exe -u docs/validation/harness/findings.py` (section F-001)
- N: 251 information sets / 993 index-to-index comparisons. Seeds: shuffle_seeds 1-59, probed every 11th ply; the two determinizations drawn with `RandomState(11)` vs `RandomState(77)`
- Observed:
  ```
  N infosets=251  indices compared=993
  indices whose move CHANGED between two determinizations: 0 (0.00%)
  infosets where legal-action COUNT differed: 0/251
  ```
- Verdict rationale: This is the pre-registered "Expected if FALSE POSITIVE" verbatim - the move at every tested index was the same move type and target across both determinizations in all 993 comparisons, and the legal-action count never differed, so the steelman (stable C move-enumeration order) holds and `ISMCTSBot`'s raw-integer keying is not corrupted by determinization.

### F-002 `engine_determinize` never rerolls `shuffle_seed`/`shuffle_counter`, so post-determinization chance events collapse across worlds
- Class: OPENSPIEL-ISMCTS
- Severity: CRITICAL (invalidates results)
- Code: `engine_c/state.c:271-309` (`engine_determinize`) behaviour: clones `src` via `engine_clone` (which `memcpy`s `shuffle_seed`/`shuffle_counter` unchanged), reshuffles opponents' hidden zones and the market deck with a **local** `RNG` seeded from the caller's `seed` param, but writes nothing back into `clone->shuffle_seed`/`clone->shuffle_counter`
- Rulebook: `docs/tyrants-rulebook.md` § Draw a Card (line 328): "Whenever you need to draw a card but there are none left, shuffle your discard pile to re-form your deck."
- Whitepaper: `docs/ismcts-paper.md` § III-C-2 Chance Nodes (line 297): "chance nodes do occur under certain circumstances ... they cannot be ignored completely"
- Disagreement: `reshuffle_discard_into_deck` (`state.c:219-231`) and `apply_force_discard` (`actions.c:404-412`, confirmed: `rng_seed(&rng, state->shuffle_seed)` then fast-forward `state->shuffle_counter` steps) both reseed from the **state-level, never-rerolled** `shuffle_seed`/`shuffle_counter` fields — the same fields every ISMCTS-sampled determinization inherits verbatim from the real root state. Two simulations that sampled different hidden worlds (different `seed` passed to `determinize`) but reach the same `shuffle_counter` value at their first in-rollout reshuffle will apply the **identical RNG permutation stream**, even though `engine_determinize` itself carries a comment (`state.c:300-303`) showing the author explicitly understood and fixed this exact failure mode for one channel only: "reshuffle it [the market deck] on every determinization so IS-MCTS cannot exploit a single clairvoyant deck order across simulations." Player-deck reshuffles and forced-discard picks receive no equivalent fix.
- Steelman: The market-deck comment shows this was a deliberate, scoped decision — player-deck reshuffles and force-discards may have been judged rare enough within the typical simulation horizon (`num_sims=200`, bounded rollout depth) to not measurably bias search, a conscious simplification rather than an oversight.
- Falsification test: From one information-state root, produce two adapters via `CEngineAdapter.determinize(player_id, seed1)` and `determinize(player_id, seed2)`, seed1≠seed2. Confirm both report identical `shuffle_seed`/`shuffle_counter` (they must, since `engine_determinize` never writes them). Drive each to the same `shuffle_counter` value via a reshuffle-triggering draw and record the **relative permutation** `rng_shuffle` applies (index mapping), not the resulting card identities (which differ anyway because the pre-shuffle contents differ per world).
- Expected if REAL: The permutation indices are bit-for-bit identical between the two worlds at matching `shuffle_counter` values.
- Expected if FALSE POSITIVE: The permutation indices differ, meaning `shuffle_seed`/`shuffle_counter` are perturbed by determinization somewhere not found in this reading.
- Status: **CONFIRMED**
- Command: `.venv/Scripts/python.exe -u docs/validation/harness/findings.py` (section F-002) and `.venv/Scripts/python.exe -u docs/validation/harness/f002b.py`
- N: 141 determinization pairs (field-invariance half); 3 controlled reshuffles (permutation half). Seeds: shuffle_seeds 1-39 probed every 13th ply, determinizations `RandomState(101)` vs `RandomState(202)`; reshuffle probes at shuffle_seeds {3, 31, 37}
- Observed:
  ```
  N=141  determinizations preserving root (shuffle_seed,shuffle_counter) EXACTLY: 141/141
   root=(506952113,3)  det1=(506952113,3)  det2=(506952113,3)
  same (seed,counter,contents) -> identical permutation: 3/3
  shuffle_counter+1 -> permutation CHANGED: 3/3
  shuffle_seed^const -> permutation CHANGED: 3/3
  ```
- Verdict rationale: Matches "Expected if REAL". `engine_determinize` left `shuffle_seed`/`shuffle_counter` bit-identical to the root in 141/141 cases, and the reshuffle permutation was shown to be a pure function of exactly those two fields (identical when both held fixed, changed when either was perturbed), so every sampled world shares one reshuffle stream. Caveat: the permutation half rests on only N=3 controlled reshuffles, because forcing a reshuffle requires direct struct surgery; the field-invariance half, which is the load-bearing premise, is measured at N=141.
- Note (post F-010 fix): the F-010 repair **unmasks** this defect rather than cancelling it. With determinization now reproducibly seeded, hidden-zone draws vary per simulation as intended, which makes the shared `shuffle_seed`/`shuffle_counter` stream the next binding correctness limit on world sampling — this is the one permitted cross-finding note in `docs/validation/f010-fix-plan.md` § 11.

### F-003 Mid-game random events are never surfaced as OpenSpiel chance nodes
- Class: ENGINE-OPENSPIEL
- Severity: CRITICAL (invalidates results)
- Code: `openspiel_pyrants/state_c.py:202-210` behaviour: `chance_outcomes()` and `is_chance_node()` are gated solely on `self._pending_initial_chance`, true exactly once, before any player acts
- Rulebook: `docs/tyrants-rulebook.md` § Draw a Card (line 328): "Whenever you need to draw a card but there are none left, shuffle your discard pile to re-form your deck."
- Whitepaper: `docs/ismcts-paper.md` § III-C-2 (line 297): "since this occurs before any player has made a decision it never occurs as a chance node in our search tree" [stated only about the initial deal]
- Disagreement: The paper's justification for excluding a shuffle from the search tree hinges specifically on it happening "before any player has made a decision." Tyrants' discard-pile reshuffles (`state.c:219-231`), forced random discards (`actions.c:404-412`), and card-effect mass-discards (`generic_runtime.c`, tags `end_of_turn_mass_discard`/`conditional_owner_discard`/`local_discard`/`mass_discard`, ~lines 531-660) all occur mid-game, after many decisions — precisely the class of event the paper says must be an explicit chance node — yet `PyrantsCState` never exposes any of them; they resolve silently inside whichever `apply_action` triggered them.
- Steelman: Once a determinization has fixed the hidden-zone contents, these events have a small, deterministic outcome space; folding them into the transition (rather than a separate tree node) is a legitimate design choice provided the outcome still varies correctly per Monte Carlo sample — which F-002 shows it currently does not, but the two defects are logically separable (fixing F-002 would not by itself give these events dedicated tree statistics).
- Falsification test: Instrument a `just ismcts-quick` run to log `state->shuffle_counter` deltas per `apply_action` call alongside `state.is_chance_node()`'s value immediately before that call.
- Expected if REAL: `shuffle_counter` advances during a transition where `is_chance_node()` was False.
- Expected if FALSE POSITIVE: Every `shuffle_counter` advance is immediately preceded by an `is_chance_node()==True` state.
- Status: **CONFIRMED**
- Command: `.venv/Scripts/python.exe -u docs/validation/harness/findings.py` (section F-003)
- N: 2,112 state transitions. Seeds: shuffle_seeds 1-39, uniform-random policy, up to 300 plies each
- Observed:
  ```
  N transitions=2112  shuffle_counter advanced on 134 of them
  of those advances, preceded by is_chance_node()==True: 0
  ```
- Verdict rationale: Matches "Expected if REAL" exactly - 134 mid-game randomization events (6.3% of all transitions) advanced `shuffle_counter` inside an `apply_action`, and not one of them was preceded by a state reporting `is_chance_node()==True`, so every mid-game random event resolves silently inside a player transition rather than as an OpenSpiel chance node.

### F-004 `Returns()`/`UtilitySum`/`MinUtility`/`MaxUtility` contract violated for 3–4 player games
- Class: ENGINE-OPENSPIEL
- Severity: CRITICAL (invalidates results)
- Code: `openspiel_pyrants/game_c.py:65-75` behaviour: `min_utility=-max_utility` (e.g. -400.0) and `utility_sum=0.0` declared unconditionally for every `num_players`
- Rulebook: `docs/tyrants-rulebook.md` § Final Scoring (line 398): "The player with the most VP at the end of the game wins" [all listed VP sources — site VP, trophy-hall count, deck VP, inner-circle VP, VP tokens — are additive; no rule subtracts VP]
- Whitepaper: [absent] — GameInfo bounds are an engine/API contract, not a paper concern
- Disagreement: `PyrantsCState.returns()` (`state_c.py:171-187`) only zero-sums the `n==2` case (`[s0-s1, s1-s0]`); for `n>2` it returns raw non-negative VP totals (line 187: `[float(scores.get(pid,0)) for pid in player_ids]`), whose sum is the total VP awarded (generically hundreds, never 0) and whose individual values are never negative — directly contradicting `utility_sum=0.0` and `min_utility=-max_utility` declared for exactly the `GENERAL_SUM`/`num_players>2` case `game_c.py:34-38` itself selects. The project's own default `just ismcts` recipe runs `num_players="4"` (`justfile:63`), so this is the primary configuration, not an edge case.
- Steelman: Vanilla `ISMCTSBot`'s backup step uses raw `returns()[cur_player]` with no normalization by `min_utility`/`max_utility`/`utility_sum` (confirmed at `ismcts.py:383`), so this may be inert metadata that only matters to other pyspiel consumers (exploitability tools, generic normalized bots), not to the searches this repo currently runs.
- Falsification test: `pyspiel.load_game("python_pyrants_c", {"num_players": "4"}).new_initial_state()`, play to terminal, call `.returns()`, and check `sum(returns) == 0` and `all(r >= -400 for r in returns)` against the declared contract.
- Expected if REAL: `sum(returns())` is strongly positive and no return is ever negative.
- Expected if FALSE POSITIVE: Observed returns are numerically consistent with the declared zero-sum, symmetric-bound contract.
- Status: **CONFIRMED**
- Command: `.venv/Scripts/python.exe -u docs/validation/harness/findings.py` (section F-004)
- N: 8 games played to terminal per player count (2, 3, 4) = 24 terminal states. Seeds: shuffle_seeds 1-8, uniform-random policy
- Observed:
  ```
  --- num_players=3  utility_sum=0.0 min_utility=-400.0 max_utility=400.0 type=Utility.GENERAL_SUM
     N=8 terminal returns: sum(returns) values=[18.0, 9.0, 9.0, 23.0, 4.0, 8.0, 10.0, 9.0]
     min(returns) values=[4.0, 1.0, 1.0, 0.0, 1.0, 0.0, 2.0, 0.0]   any negative=False
  --- num_players=4  sum(returns) values=[14.0, 14.0, 9.0, 11.0, 8.0, 12.0, 14.0, 9.0]  any negative=False
  ```
- Verdict rationale: Matches "Expected if REAL" - for both 3- and 4-player games `sum(returns())` was strongly positive in 16/16 terminal states (never the declared `utility_sum=0.0`) and no return was ever negative despite `min_utility=-400.0`. The 2-player case was run as a control and did satisfy its zero-sum declaration (`sum(returns)==0.0` in 8/8), which localises the defect to exactly the `num_players>2` branch the finding names.

### F-005 Rulebook mandates random first-player selection; engine always seats `player_ids[0]`
- Class: RULE-ENGINE
- Severity: MAJOR (biases results)
- Code: `engine_c/state.c:99` (also `:68`, and `phases.c:19`) behaviour: `if (player_count > 0) gs->current_player_id = gs->player_ids[0];` — no RNG call anywhere near first-player assignment; confirmed repo-wide (no counterexample found across `engine_c/*.c`)
- Rulebook: `docs/tyrants-rulebook.md` § Setup (line 113): "Randomly choose who will take the first turn and give that player the first-player marker."
- Whitepaper: [absent]
- Disagreement: The rulebook requires the first player to be chosen uniformly at random each game; the engine deterministically seats whichever ID is first in the caller-supplied `player_ids` list on every game, with no randomization anywhere in the C engine.
- Steelman: `player_ids` order could in principle be permuted by the calling harness before `create_game`, pushing randomization up a layer rather than omitting it; for symmetric self-play training over many games, "who goes first" may have been treated as a harness-level concern.
- Falsification test: Call `game.new_initial_state()`, `apply_action(shuffle_seed)` for several different `shuffle_seed` values with a fixed `player_ids` order, and inspect `state._adapter.current_player_id()` immediately after setup.
- Expected if REAL: `current_player_id` is always `player_ids[0]` regardless of `shuffle_seed`.
- Expected if FALSE POSITIVE: `current_player_id` varies with `shuffle_seed`.
- Status: **CONFIRMED**
- Command: `.venv/Scripts/python.exe -u docs/validation/harness/findings.py` (section F-005)
- N: 10 distinct initial chance outcomes. Seeds: shuffle_seeds {0, 1, 2, 7, 42, 99, 123, 500, 777, 999}
- Observed:
  ```
  N=10 shuffle_seeds [0,1,2,7,42,99,123,500,777,999] -> current_player_id counts: {'p1': 10}
  ```
- Verdict rationale: Matches "Expected if REAL" - `current_player_id` was `player_ids[0]` (`p1`) for all 10 shuffle seeds, so the initial chance node randomizes deck order but never the seat that acts first, against the rulebook's "Randomly choose who will take the first turn." Note this is a seat-order bias, not a strength bias: the self-play calibration check (N=48, seat-swapped) found no significant first-seat advantage.

### F-006 Default `uct_c=1.4` diverges from the paper's calibrated `0.7`
- Class: PAPER-CODE
- Severity: MAJOR (biases results)
- Code: `scripts/run_ismcts.py:151,393` behaviour: `parser.add_argument("--uct-c", type=float, default=1.4)`, passed unmodified into `ISMCTSBot(..., uct_c=uct_c, ...)`
- Rulebook: [absent]
- Whitepaper: `docs/ismcts-paper.md` § IV-A Choice of UCB1 Exploration Constant: "The value of 0.7 was thus used for all algorithms in all experiments in this paper."
- Disagreement: The paper calibrated and used `c=0.7` for every SO-ISMCTS/MO-ISMCTS/determinized-UCT experiment it reports, after observing performance "decrease[s] outside" a tested neighborhood of that value; this repo's default (`just ismcts`, `just ismcts-quick`) instead runs the untuned classic-UCT constant `1.4` (≈√2), a value the paper neither uses nor endorses for this algorithm family.
- Steelman: `0.7` was tuned for the paper's three specific domains with small/normalized rewards; Tyrants' branching factor and reward scale (raw VP totals in the hundreds, not normalized to ±1) differ enough that an independent re-calibration to a different constant — including 1.4 — could be legitimate rather than an oversight.
- Falsification test: Search the repo (`docs/`, commit history, `.kilo/plans/`) for evidence that `1.4` was chosen via an empirical sweep for this game, versus being the untouched argparse factory default.
- Expected if REAL: No tuning evidence exists for `1.4`; it is simply `argparse`'s default, and reward magnitudes were never re-derived against the paper's guidance.
- Expected if FALSE POSITIVE: A doc, scenario file, or commit shows `1.4` was deliberately chosen after empirical comparison for this specific game.
- Status: **CONFIRMED**
- Command: `grep -rn "uct_c|uct-c|exploration constant" --include=*.md docs/ .kilo/` ; `git log --all -S"uct_c" -- scripts/run_ismcts.py` ; `.venv/Scripts/python.exe -u docs/validation/harness/f006.py`
- N: full repo doc/plan/commit-history search (0 tuning artifacts found); 25 sampled root nodes at `num_sims=200` for the reward-scale measurement. Seeds: shuffle_seeds 1-39
- Observed:
  ```
  .kilo/plans/openspiel-ismcts-pyrants.md:195:--uct-c FLOAT           # default 1.4   <- only occurrence, a spec line
  (no sweep artifact, no comparison doc, no commit tuning uct_c)
  N=25 root nodes (num_sims=200, uct_c=1.4)
    Q-value spread (max-min child value): mean=9.22  median=8.18  max=24.79
    UCT exploration bonus 1.4*sqrt(ln N/n): mean=1.443  -> exploitation:exploration = 6.4 : 1
  ```
- Verdict rationale: Matches "Expected if REAL" on both clauses - no doc, scenario file, or commit shows `1.4` was ever compared empirically for this game (its single appearance is a plan line restating the argparse default), and the reward magnitudes were never re-derived: the paper calibrated `0.7` against rewards normalised to +/-1, whereas this game backs up raw VP differentials with a mean child-value spread of 9.22, leaving the exploration term outweighed 6.4:1. Severity note: this biases the search but does not disable it - the budget-monotonicity check still shows real strength gains with more simulations.

### F-007 Discard-pile visibility is a rulebook silence the code has resolved by treating discards as hidden
- Class: SPEC-GAP
- Severity: MINOR (cosmetic / conditionally biases opponent modeling)
- Code: `engine_c/state.c:279-298` (`engine_determinize` pools `hand`+`deck`+`discard_pile` into one shuffled, indistinguishable block per opponent) and `engine_c/bindings/c_adapter.py:200-222` (`private_view_json` exposes only `discard_size`, a count, never discard-pile card identities, for any player's view of any other player)
- Rulebook: `docs/tyrants-rulebook.md` — no section states whether an opponent's discard pile is publicly inspectable while sitting as a pile (the only discard-pile text found, line 328, describes reshuffling it into the deck, not its visibility). [absent — genuine silence]
- Whitepaper: [absent]
- Disagreement: The code has firmly chosen "discard-pile contents are as hidden as an undrawn deck," with no rulebook passage granting or denying this. The rulebook's phrasing distinguishes decks explicitly ("Shuffle your deck and place it face down," line 116; "Put it face down," line 131) but never gives discard piles an orientation, which in many deckbuilders defaults to face-up/public by table convention.
- Steelman: If discards are conventionally face-up, hiding them denies the ISMCTS opponent model information a human opponent would legitimately have — the "leaking too little" failure mode Sweep B calls out — but no rulebook line confirms or denies this, so the claim cannot be elevated past a suspicion.
- Falsification test: Check `data/cards/*.json` for any card text that references looking at or revealing an opponent's discard pile (which would only make sense if discard piles are otherwise private), or consult the published physical rulebook / BGG rules FAQ for an explicit visibility statement.
- Expected if REAL (discards should be public): A rule or card confirms public discard-pile visibility, meaning `information_state_string` should include opponents' discard-pile identities but currently only sends a count.
- Expected if FALSE POSITIVE: Rules confirm discard piles are effectively private/reshuffled-away by design, or no rule ever depends on an opponent knowing discard contents mid-game.
- Status: **REFUTED**
- Command: `grep -rio "discard pile" data/cards/ | sort -u` ; `grep -ril "opponent.*discard|discard.*opponent" data/cards/`
- N: all 12 cards in `data/cards/` whose text mentions a discard pile (full-corpus scan)
- Observed:
  ```
  cards referencing an OPPONENT's discard: (none)
  Every hit is either "your discard pile" (promote/deploy from own discard) or
  "That player adds an Insane Outcast ... to their discard pile" (a write, not a read).
  ```
- Verdict rationale: Matches the second clause of "Expected if FALSE POSITIVE" - no card and no rule anywhere depends on a player reading an opponent's discard-pile contents; every reference is either to the player's own discard or is an insertion into someone else's, which requires no visibility. The rulebook silence therefore has no mechanical consequence and cannot be elevated to a defect. A distinct and real observation gap did surface from this scan and is filed separately as F-011: a player cannot see their **own** discard-pile contents either, yet those same 12 cards require selecting a card from it.

### F-008 Paper's chance-node exploration technique targets small outcome counts; this domain's (currently hidden, F-003) chance events are larger
- Class: PAPER-RULE
- Severity: MINOR (conditional on F-003)
- Code: `engine_c/state.c:219-231` (`reshuffle_discard_into_deck`, outcome space = permutations of an opponent's full discard pile, which can hold well over 4 cards) — behaviour: not currently a chance node at all (see F-003), but would become the relevant comparison if F-003 were fixed
- Rulebook: `docs/tyrants-rulebook.md` § Draw a Card (line 328) — same citation as F-002/F-003
- Whitepaper: `docs/ismcts-paper.md` § III-C-2 (line 297): "our chance nodes have a small number of possible outcomes (at most four but rarely more than two)"
- Disagreement: The paper's round-robin/permutation exploration mechanism for chance nodes ("the first visits select all outcomes in a random permutation...") is explicitly justified for branching factors of "at most four but rarely more than two." A discard-pile reshuffle or a mass-discard among a 5-card hand already exceeds that design range, and a full discard-pile reshuffle (potentially dozens of cards) is combinatorially far beyond it — the paper's technique for guaranteeing even exploration of chance branches would not straightforwardly scale to these events even if they were exposed as chance nodes.
- Steelman: What actually matters strategically from a reshuffle is usually just "which card ends up on top of the deck next," not the full permutation — if only the next-draw identity is treated as the outcome, the effective branching collapses to deck size, which is still often >4 but far more tractable than full-permutation branching.
- Falsification test: If F-003 is fixed to expose these as chance nodes, measure the actual `len(chance_outcomes())` at each such node during a representative game and compare to the paper's assumed range.
- Expected if REAL: Chance-node branching factors observed are consistently well above the paper's stated 2–4 range.
- Expected if FALSE POSITIVE: Effective branching (e.g., because only the next 1–2 draws matter) stays within a range the paper's technique was shown to handle.
- Status: **UNTESTABLE** [the pre-registered test is explicitly conditional on F-003 being fixed first - "If F-003 is fixed to expose these as chance nodes, measure the actual `len(chance_outcomes())`" - and F-003 is CONFIRMED unfixed, so no mid-game chance node exists to measure]
- Command: `.venv/Scripts/python.exe -u docs/validation/harness/findings2.py` (section F-008); `.venv/Scripts/python.exe -u docs/validation/harness/findings.py` (section F-003, for the event count)
- N: 1 chance-node type reachable in the current build; 134 mid-game randomization events observed over 2,112 transitions (seeds 1-39)
- Observed:
  ```
  the ONE exposed chance node: len(chance_outcomes())=1000 (paper assumes <=4)
  mid-game randomization events that would become chance nodes if F-003 were fixed: 134
  ```
- Verdict rationale: Neither pre-registered expectation can be evaluated, because the events this finding is about are not chance nodes today. Supporting but non-dispositive evidence points toward REAL: the single chance node that *is* exposed already carries 1,000 outcomes, 250x the paper's stated "at most four but rarely more than two" design range, so the paper's round-robin chance exploration technique is already outside its calibrated regime in this domain.

### F-009 `max_chance_outcomes` is hardcoded independent of the configurable `shuffle_seed_count` parameter
- Class: ENGINE-OPENSPIEL
- Severity: MINOR (dormant under current default configuration)
- Code: `openspiel_pyrants/game_c.py:65-69` behaviour: `_build_c_game_info(num_players)` hardcodes `max_chance_outcomes=1000`; `game_c.py:97-112` (`PyrantsCGame.__init__`) calls `_build_c_game_info(num_players)` without passing the resolved `shuffle_seed_count` param, then separately sets `self._shuffle_seed_count = int(resolved["shuffle_seed_count"])` (line 112), which is what actually drives `chance_outcomes()`'s length via `state_c.py:205` (`n = self._game.get_shuffle_seed_count()`)
- Rulebook: [absent]
- Whitepaper: [absent]
- Disagreement: `shuffle_seed_count` is a documented, caller-configurable game parameter (`_DEFAULT_PARAMS`/`parameter_specification`, default 1000) but `max_chance_outcomes` never reads it — it is a bare literal. If a caller instantiates the game with `shuffle_seed_count` set to anything other than 1000, `chance_outcomes()` will return a different number of outcomes than `game.get_type()`'s declared `max_chance_outcomes`, violating the Sweep B requirement that `MaxChanceOutcomes` be reachable-consistent.
- Steelman: No script in this repo (`run_ismcts.py`, `justfile`) ever overrides `shuffle_seed_count` away from its default of 1000, so under every code path actually exercised today the two numbers coincide and the bug is dormant.
- Falsification test: `pyspiel.load_game("python_pyrants_c", {"shuffle_seed_count": "5000"})`, call `new_initial_state().chance_outcomes()`, and compare `len(...)` to `game.get_type()`'s (or `game_info`'s) `max_chance_outcomes`.
- Expected if REAL: `len(chance_outcomes()) == 5000` while `max_chance_outcomes == 1000`.
- Expected if FALSE POSITIVE: Both report 5000, meaning `max_chance_outcomes` is threaded through somewhere not found in this reading.
- Status: **CONFIRMED**
- Command: `.venv/Scripts/python.exe -u docs/validation/harness/f009.py`
- N: 3 game configurations (`shuffle_seed_count` = 1000, 5000, 250), 2 players each
- Observed:
  ```
  shuffle_seed_count= 1000 -> len(chance_outcomes())= 1000  max_chance_outcomes()= 1000  CONSISTENT=True
  shuffle_seed_count= 5000 -> len(chance_outcomes())= 5000  max_chance_outcomes()= 1000  CONSISTENT=False
     applying outcome id 4999 (>= max_chance_outcomes) SUCCEEDED
  shuffle_seed_count=  250 -> len(chance_outcomes())=  250  max_chance_outcomes()= 1000  CONSISTENT=False
  ```
- Verdict rationale: Matches "Expected if REAL" exactly - at `shuffle_seed_count=5000` the state offers 5,000 chance outcomes while the game declares `max_chance_outcomes()==1000`, and outcome id 4999 (far outside the declared range) applies without error. The bug is bidirectional: at 250 the declaration over-states the true count. It remains dormant only because no in-repo caller overrides the default.

### F-010 ISMCTS determinization seeds come from an unseeded RNG, so runs are not reproducible
- Class: OPENSPIEL-ISMCTS
- Severity: CRITICAL (invalidates reproducibility of every reported result)
- Origin: **Found empirically by the invariant battery (replay determinism), not by the static pass.**
- Code: `.venv/Lib/site-packages/open_spiel/python/algorithms/ismcts.py:222-225` — `resample_from_infostate` calls `state.resample_from_infostate(state.current_player(), pyspiel.UniformProbabilitySampler(0., 1.))`, passing a **freshly constructed, unseeded C++ sampler** rather than the bot's own `self._random_state`. `openspiel_pyrants/state_c.py:313-321` then branches: a `numpy.RandomState` (has `.shuffle`) yields a seed derived reproducibly, but any other callable falls to `seed = int(rng() * 2**63)`. `UniformProbabilitySampler` is callable and has no `.shuffle`, so every determinization seed in every search is drawn from an unseeded global RNG.
- Disagreement: `scripts/run_ismcts.py` exposes `--seed` and records `shuffle_seed` in `summary.csv`, presenting runs as reproducible. They are not: the shuffle seed fixes only the initial deal, while every subsequent determinization — the sampling that drives the entire search — is unseeded.
- Falsification test: run the same seed, same policy, twice, and compare action sequences and terminal returns; then re-run a single search from one fixed, unmutated root with an identically seeded fresh bot.
- Expected if REAL: identical seeds produce different action sequences and different returns; a fixed root yields different chosen actions across identically seeded searches.
- Expected if FALSE POSITIVE: identical seeds reproduce the game exactly.
- Status: **CONFIRMED — FIXED** (working-tree change; not yet committed)
- Command: `.venv/Scripts/python.exe -u docs/validation/harness/inv_a.py` ; `.venv/Scripts/python.exe -u docs/validation/harness/det_isolate.py` ; `.venv/Scripts/python.exe -u docs/validation/harness/det_bot.py` ; `.venv/Scripts/python.exe -u docs/validation/harness/det_root.py`
- Resolution: `openspiel_pyrants/ismcts_factory.py` (`make_ismcts_bot`) always installs a seeded numpy resampler via the stock `ISMCTSBot.set_resampler` hook, with a dedicated `RandomState(seed ^ 0x5F10)` stream decoupled from the bot's `random_state`. `scripts/run_ismcts.py` now builds every seat through this factory, preserving the per-seat seed derivation `seed + game_index * num_players + i`. `openspiel_pyrants/state_c.py::resample_from_infostate` now raises `TypeError` on a bare callable (the old unseeded path) instead of silently deriving an irreproducible seed. Post-fix INV-1 passes at N=100 seed-paired games (0 divergent), `det_bot.py` B1 returns exactly 1 distinct chosen action across 10 identically-seeded searches, and INV-5 world diversity is unchanged (mean 10.26/12 distinct worlds, 0 singletons) — see `verdict.md` §2.
- N: 10 seed-paired full games (replay); 10 identically-seeded searches from one fixed root; 6 freshly constructed samplers. Seeds: shuffle_seeds 1-10, bot `RandomState` seeds 1000+s / 2000+s, fixed-root probe at seed 4242
- Observed:
  ```
  INV1 replay determinism: FAIL [(1, 42 vs 41 moves, returns [18,-18] vs [8,-8]), (2, 47 vs 30, [-2,2] vs [17,-17])]  10/10 seeds diverged
  L1 engine replay (fixed action sequence):        PASS N=10
  L2 RandomBot self-play replay:                   PASS N=10
  L3 ISMCTS replay (random-py evaluator):          FAIL 5/5
  L4 adapter.random_rollout(seed) x8:              1 distinct result  (deterministic)
  B1 one fixed root, 10 identically-seeded bots:   num_sims=20 -> 3 distinct chosen actions; num_sims=200 -> 2
  B2 root state fingerprint before/after search:   intact (search does not mutate the root)
  S1 fresh UniformProbabilitySampler first draws:  0.3234.., 0.2018.., 0.6688.., 0.5374.. (all different)
  S5 control, resample with RandomState(555) x6:   1 distinct world  (deterministic)
  ```
- Verdict rationale: Matches "Expected if REAL" on both clauses, and the layer isolation is decisive — the C engine (L1), the full game loop under a pure-Python policy (L2), the C rollout (L4) and the evaluator are each deterministic, and the root is not mutated (B2), so the only remaining source is the search's world sampling; S1 shows the sampler it uses is unseeded and S5 shows the same code path is fully deterministic when a seeded `RandomState` is passed instead. Note this defect masks F-002 in practice rather than cancelling it: the *hidden-zone* draw varies per simulation, but the `shuffle_seed`/`shuffle_counter` stream F-002 identifies stays shared across all of them.
- Review 01 [2026-08-31] at `028ff9d1d27841e63f0945b5ddd69b4afe838d85`: **REJECTED-SCOPE**
- Diff: `openspiel_pyrants/__init__.py`, `openspiel_pyrants/ismcts_factory.py` (new), `openspiel_pyrants/state_c.py`, `scripts/run_ismcts.py`, 3 test-file conversions, `openspiel_pyrants/tests/test_ismcts_reproducibility.py` (new), 6 deleted debug scripts, `docs/validation/{findings.md,verdict.md,f010-fix-plan.md,grug_findings.md}` (new), `docs/validation/harness/*.py` (new), `docs/validation/baseline/*.txt` (new) | out-of-scope hunks: 4 (deletion of `scripts/check_clone_attrs.py`, `scripts/check_ismcts_chain.py`, `scripts/trace_clone.py` — not on the fix plan's authorized 7-site table; addition of `docs/validation/grug_findings.md` — not mentioned anywhere in the fix plan) | test changes: 4 files, all cleared against the Hard Rule 4 gaming checklist (no weakened assertion, no reduced N, no seed-pinning, no swallowed exceptions — bot-construction calls only)
- Conformance: CONFORMANT vs [no rulebook/whitepaper anchor — pure engine/API reproducibility contract, same as the finding's own citation-free framing]
- Test: `docs/validation/harness/inv_a.py` + `det_bot.py` + `inv_b.py` + `f002b.py` + `pytest openspiel_pyrants/tests/` + `pytest -q` (repo root) N=100 seed-paired games (INV-1), N=10 fixed-root searches (det_bot B1), N=2400 determinizations (INV-5) seeds=1-100/1-200×12/4242 result=INV-1 PASS 0/100 diverged (was FAIL 10/10); det_bot B1 1 distinct chosen action (was 4); INV-5 mean 10.26/12 unchanged (G2 holds, no world-sampling collapse)
- Regressions: none attributable to this diff — 3 pre-existing failures in the full repo suite (`test_card_zuggtmoy`, `test_engine_c::test_air_elemental_option_1_focus_draw`, `test_card_neogi`) exercise `engine_c`/`data/cards/catalog.json`, files this diff does not touch at all
- Invalidated: STALE rows [verdict.md §1 INV-7, INV-8, INV-9 — STRENGTH rows measured under the unseeded resampler, already flagged by the fixing agent, independently confirmed here] | New findings raised: 1 (F-012)

### F-011 Board state is absent from the information state and the observation
- Class: ENGINE-OPENSPIEL
- Severity: CRITICAL (invalidates results; the observation omits the game's primary scoring substrate)
- Origin: **Found empirically by the invariant battery (information-set leakage, distinguishability direction), not by the static pass.**
- Code: `engine_c/bindings/c_adapter.py:158-198` — `_build_public_dict` returns only round/phase/current player/turn order/market row/market counts/resource pool/per-player summaries. It never iterates `s.nodes` (the board). `private_view_json` (`:200-222`) wraps that dict with the player's own hand and a set of counts. `openspiel_pyrants/state_c.py:212-232` builds `information_state_string` as `history_str() || private_view_json(player)`, and `observation_string` returns `information_state_string` verbatim. A board view *does* exist and is fully public (`engine_c/bindings/view.py::build_c_board_view`, used by `scripts/_state_snapshot.py::_tier2_snapshot`) but is never routed into the observation.
- Rulebook: `docs/tyrants-rulebook.md` § Final Scoring (line 398) — site control VP, total-control VP and troop presence are primary VP sources, and § Sequence of Play makes troop/spy placement the core decision each turn.
- Disagreement: Site control, troop placement, spy placement and control VP are public information every human player can see at all times, and are the dominant source of score. The information state a bot or a trained agent receives contains none of it. Related, from the F-007 scan: a player's *own* discard-pile contents are also absent (only `discard_size`), although 12 cards require choosing a card from that pile.
- Falsification test: construct state pairs that differ only in a public board fact — same move type applied to a different site, so barracks/resource bookkeeping is identical — verify the boards genuinely differ, then compare `private_view_json(p)`.
- Expected if REAL: boards differ while the observation is byte-identical.
- Expected if FALSE POSITIVE: the observation differs whenever the board differs.
- Status: **CONFIRMED — FIXED** (working-tree change; not yet committed)
- Command: `.venv/Scripts/python.exe -u docs/validation/harness/inv_b2.py` ; `.venv/Scripts/python.exe -u docs/validation/harness/obs.py`
- Resolution: `engine_c/bindings/c_adapter.py::private_view_json` now merges `{**pub, "board_nodes": self._board_nodes_view()}` (using the existing, already-public `engine_c/bindings/view.py::build_c_board_view`, reading only the player-agnostic per-node fields — never the current-player-scoped `CBoardViewData` aggregates) and adds `discard = [_sym_str(p.discard_pile[i]) ...]` as a new `discard` key. The cheap Tier-1 path (`_build_public_dict`) is untouched. Post-fix INV-4b passes at N=403 (403/403 pairs now visible), INV-4a unchanged at 0/300, INV-5 mean distinct worlds 11.11/12 (0 singletons — the rise from 10.26 is the omniscient fingerprint now seeing own-discard reshuffles, not leakage). Tests in `openspiel_pyrants/tests/test_observation_completeness.py`. See `verdict.md` §2.
- Cost note: the board projection costs ~388 µs/call and regresses end-to-end search wall-time 9.66× at `num_sims=200` — filed as F-013 (open, performance).
- N: 403 board-differing state pairs (board test); 110 own-discard permutations (discard test). Seeds: shuffle_seeds 1-139 and 1-119 respectively, uniform-random policy
- Observed:
  ```
  same-move-type/different-site pairs with DIFFERENT board: N=403
    private_view_json IDENTICAL (board invisible to observer): 403
    private_view_json differs (board visible):                 0
    e.g. initial_placement(site_blingdenfire) VS initial_placement(site_buiyrandyn)
  board fields present in private_view_json: []
  own-discard permutations, N=110: information state IDENTICAL (content invisible)=110, differs=0
  keys exposing identities: ['hand','inner_circle','played_cards','trophy_hall']
  keys exposing only COUNTS:  ['barracks','deck_size','devour_size','discard_size','score','spies_available','vp_tokens']
  ```
- Post-fix observed (inv_b2.py / inv_b.py):
  ```
  INV4b-DECISIVE: N=403  private_view_json IDENTICAL=0  differs=403
  INV4a leakage: N=300 violations=0
  INV4b board fields present in private_view_json: ['board_nodes']
  ```
- Verdict rationale: Matches "Expected if REAL" in 403/403 pairs - placing a troop at Blingdenfire versus Buiyrandyn yields genuinely different boards and a byte-identical observation, and a scan of the schema confirms zero board fields are exposed. `information_state_string` distinguishes these pairs only because the raw action-index history is prepended, which means the ISMCTS node key encodes *which index was chosen*, not *what the board looks like*; that also explains the measured `info_state_repeat_rate=0.0` (618 unique keys over 618 sampled states), i.e. no information-set statistic sharing across moves at all. The fix closes the board and own-discard gap; the remaining performance regression is F-013.

### F-012 `resample_from_infostate`'s accept branch and its own new error message claim `Generator` support that does not work
- Class: OPENSPIEL-ISMCTS
- Severity: MINOR (dormant — no caller in the repo passes a `Generator`; every call site uses `np.random.RandomState`)
- Origin: **Found by Review 01 of F-010 while auditing the diff, not by a run.**
- Code: `openspiel_pyrants/state_c.py:313-316` (`if hasattr(rng, 'shuffle'): hi = rng.randint(0, 2**31-1); lo = rng.randint(0, 2**31-1)`) vs. the new text this diff adds at `state_c.py:318-323` ("requires a seeded numpy RandomState/Generator") and `openspiel_pyrants/ismcts_factory.py`'s module docstring, which also names `Generator` as acceptable
- Rulebook: [absent] — pure API-contract concern, same category as F-010 itself
- Whitepaper: [absent]
- Disagreement: `numpy.random.Generator` (the modern numpy random API) has `.shuffle()` and so passes the `hasattr(rng, 'shuffle')` gate, but has no `.randint()` method — `Generator` uses `.integers()` instead; `.randint()` exists only on the legacy `numpy.random.RandomState`. A caller who followed the new error message's own advice and passed a `Generator` instead of a `RandomState` would hit an unrelated `AttributeError` deeper inside the accept branch, not the clean, documented behavior the message promises.
- Steelman: fully dormant today — `make_ismcts_bot`, all converted tests, and `docs/validation/harness/common.py::make_bot` construct only `np.random.RandomState`, never `Generator`. The `hasattr`/`randint` branch itself predates this diff and is unchanged by it; the diff's only new contribution is message text asserting `Generator` support that was never actually there.
- Falsification test: call `state.resample_from_infostate(player, np.random.default_rng(1))` (a `Generator`) on any live mid-game state.
- Expected if REAL: raises `AttributeError: 'Generator' object has no attribute 'randint'`.
- Expected if FALSE POSITIVE: succeeds and returns a determinized state.
- Status: **OPEN** (not investigated further, per review protocol — falsification test defined but not executed)

### F-013 Board projection regresses `private_view_json` cost 9.66×; needs a narrower C accessor
- Class: ENGINE-OPENSPIEL
- Severity: MINOR (performance — non-blocking for 2-player engine work, blocking for any large-scale ISMCTS throughput claim)
- Origin: **Found by the F-011 fix while re-running the G5 timing gate.**
- Code: `engine_c/bindings/c_adapter.py::_board_nodes_view` (added by F-011) calls `engine_c/bindings/view.py::build_c_board_view`, which invokes `engine_build_view` (`engine_c/view.c`) — a monolithic C projection that `memset`s the full `CGameView` and populates every card zone for every player (4 × 80) plus every board node (128) and three `remaining_special_stack_count` scans, ~388 µs/call — while the board-only wrapper reads back only the `nodes` array.
- Disagreement: `private_view_json` is called once per ISMCTS node expansion for every observing player, so the ~388 µs board cost (vs ~24 µs for the rest of the call) lands on the hot path. Measured end-to-end search wall-time at `num_sims=200` rose 9.66× (0.165 s → 1.589 s).
- Steelman: correctness first — the F-011 observation gap is blocking and had to be fixed regardless of cost; the two-tier snapshot design was preserved (Tier-1 `_build_public_dict` untouched), and the regression is a constant-factor slowdown, not a complexity change.
- Falsification test: `python -u docs/validation/harness/f011_timing.py` before/after, compare mean wall-time.
- Expected if REAL: mean wall-time ratio > 2×.
- Status: **OPEN**
- Command: `.venv/Scripts/python.exe -u docs/validation/harness/f011_timing.py` (baseline `docs/validation/baseline/f011_timing.pre.txt` vs `.post.txt`)
- Resolution (planned): a narrower `engine_build_board_view`-only C function that populates just `nodes`/`node_count` and skips the card-zone and special-stack work `engine_build_view` always does, then re-point `_board_nodes_view` at it.

## 4. Unanchored (suspicions that could not be fully anchored)

- **[unverified]** `engine_c/rules.c:504-561` (`apply_end_of_turn_effects`, tag `end_of_turn_mass_discard`) and `engine_c/generic_runtime.c` (~lines 531-538, same tag) both implement what looks like the same card effect via two separate code paths — one from the natural end-of-turn phase transition, one from the pending-generic-choice resolver. Whether these are genuinely mutually exclusive (different triggers) or can both fire for the same card, causing a double discard, was not traced through the full call graph and needs dedicated tracing before it can be entered as a ledger finding.
- **[unverified]** `engine_c/state.c` clones the `pending_generic` parent chain with a hardcoded depth cap of 16 (`depth < 16`); whether any real card sequence can nest pending-generic choices deep enough to hit silent truncation was not checked against `data/cards/*.json`.
- **[unverified]** `openspiel_pyrants/action_encoding_c.py:33-35`'s own comment ("an empty `legal_actions()` at a non-terminal state deadlocks OpenSpiel silently") implies the author considered an empty-legal-actions scenario possible; whether this is ever actually reachable in practice (as opposed to a purely defensive comment) was not demonstrated.
- **[unverified]** `max_game_length=4096` (`game_c.py:74`) reachability was not checked against observed game lengths in `artifacts/ismcts/` run logs or `data/scenarios/`.

## 5. Not Checked

- **Exhaustive per-card rulebook conformance.** Only sampled turn structure, action costs, and end-of-game/scoring rules against `engine_c`, per the audit's explicit "sample coverage, do not attempt exhaustive card review" instruction. `data/cards/` holds 100+ card definitions and `tests/c_engine/` has one test file per card; a full per-card cross-check against `docs/tyrants-rulebook.md` and each card's `rules_text` was out of scope for this pass.
- **Full bidirectional `InformationStateString` audit.** Beyond the discard-pile question (F-007), other zones (market discard pile, `pending_generic`/`pending_ability` partial-reveal fields, resource-pool history) were not individually checked in both directions ("everything observed, nothing unobserved") against the rulebook.
- **`History()` replay-from-initial-state reconstruction.** This Sweep B check requires actually executing code (replaying a move sequence and diffing resulting states), which falls outside this session's static-analysis-only gate (HARD RULE 7 / STOP condition). Not performed.
- **`ChanceOutcomes()` probability-sum check.** Confirmed by direct inspection to trivially hold for the one chance node currently exposed (`state_c.py:205-207`: `p = 1.0/n`, `n` uniform outcomes sum to 1); not independently re-verified by execution.
- **Resource/deck/card-count conservation proofs.** No systematic trace was done to confirm no card is ever silently duplicated or destroyed outside of `devour`/`discard` semantics; `scoring.c`/`state.c` were read for the paths relevant to the findings above but not audited end-to-end for conservation.
- **Simultaneous-move / partially-observable-move paper sections (III-C-1, IV-F, IV-G MO-ISMCTS).** Not applicable — confirmed the rulebook's turn structure (§ Sequence of Play) is strictly sequential with no simultaneous decisions, so these paper sections were not cross-checked further.
