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
| F-013 | ENGINE-OPENSPIEL | MINOR | *(found by the F-011 fix)* routing `build_c_board_view` into `private_view_json` costs ~388 µs/call and regresses search wall-time 9.66×; fixed in two parts — Part A cached the board projection on `CEngineAdapter` (9.66× → ~6.4×), Part B made the projection cheap in pure Python (cheap direct projection + sym memo + static hoisting + per-player string cache + clone/determinize propagation) and closed the residual to ~1.6× vs. the pre-F-011 baseline |
| F-014 | ENGINE | MAJOR | *(found by the F-004 fix's T6 stress probe)* `give_insane_outcast` mints fresh instances without consulting its 30-copy special-stack cap, so `min_utility=-50.0` is a practical, not formally tight, bound |
| F-015 | ENGINE | MODERATE | *(found while mapping F-003 Part B's ten call sites)* `neogi`'s `timing:"end_of_turn"` force_discard fires twice — once inline during pending-generic resolution (which does not filter by `timing`), once again for real at end-of-turn — discarding 2 cards per opponent instead of the rulebook's 1 |

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
- Status: **CONFIRMED — FIXED** (working-tree change; not yet committed)
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
- Resolution: `engine_c/state.c::engine_determinize` now rerolls `clone->shuffle_seed = rng_next(&rng)` and resets `clone->shuffle_counter = 0` after every prior `rng` draw (the same treatment the adjacent market-deck block already gives the market deck), so each determinized world draws an independent mid-game reshuffle/forced-discard stream. See `docs/validation/f002-f003-fix-plan.md` Part A and `verdict.md` § 5 condition 3a. Post-fix evidence (append-only, Hard Rule 7): GA1 0/100 pairs preserve the root stream (was 141/141); GA3 3/3 different first-reshuffle deck orders across determinization seeds (was 0/3); C tests `test_determinize_rerolls_shuffle_stream` / `test_determinize_shuffle_stream_deterministic_per_seed` and Python tests `openspiel_pyrants/tests/test_determinize_reshuffle_independence.py` (3/3) green; always-on battery (INV-1/2/3/6, INV-4a/4b/5) unchanged; F-010 `det_bot.py` B1 unchanged (1 distinct action); full repo suite shows the same 3 pre-existing failures, zero new. Committed as `e9a2702` (parent `b0f3173` — not `2cfd836` as `f002-f003-completion-plan.md` § 1 states; corrected in Review 01 § 0).
- Review 01 [2026-09-01] at `e9a27027bb127e86936ce5b15d7187fca805335b`: **ACCEPTED** [no debt specific to this fix; dedicated Phase 5 review per `f002-f003-fix-plan.md` § 0 constraint 2, unblocking Part B]
- Diff: `engine_c/state.c` (+10, single tail hunk in `engine_determinize`), `engine_c/test_engine.c` (+53, 2 new tests), `openspiel_pyrants/tests/test_determinize_reshuffle_independence.py` (new, 3 tests), `docs/validation/{f002-f003-fix-plan.md, harness/f002_reroll.py, baseline/f002_reroll.{pre,post}.txt, findings.md, verdict.md}` | out-of-scope hunks: 0 | test changes: 2 files (new), cleared against the Hard Rule 4 gaming checklist (strict assertions on the actual fields, plan-prescribed seeds 1111/2222/11/22, no weakened assertions, no reduced N, no seed-pinning, no swallowed exceptions; T-A3's `pytest.skip` terminal-fixture guard confirmed 0-skip in the §4 run)
- Conformance: CONFORMANT — Rulebook § Draw a Card anchors the finding (reshuffles are real events; the fix changes which hidden stream a sampled world consults, not what any site does); whitepaper § III-C-2 determinization premise restored (worlds differ across samples) while GA2 same-seed reproducibility is preserved. Placement (reroll after every other `rng` draw) and byte-identical adjacency of the opponent-zone loop and market-deck block both verified by direct source reading at HEAD, not from the plan's claim
- Test: `docs/validation/harness/f002_reroll.py` N=100 pairs seeds=determinize `RandomState(101)`/`(202)` result=**GA1 0/100** preserve root stream (was 141/141 findings.py, 100/100 pre-baseline); **GA3 3/3** first-reshuffle deck orders differ across determinize seeds (was 0/3); `f002b.py` 3/3+3/3+3/3 unchanged; C tests incl. both new T-A1/T-A2 green via `just build-c`
- Regressions: none — INV-1/2/3/6 (N=100/235/1200/30, 0 violations), INV-4a/4b/5 exact-match (0/300, 618 unique/0 collisions, mean 11.11/12, conservation 0/2400), F-010 `det_bot.py` B1 unchanged (1 distinct action, B2/B3/B4 consistent), F-013 `test_board_view_cache.py` 5/5 within OpenSpiel suite 78/78, full repo suite (150 collected) same 3 pre-existing `engine_c`/catalog failures (Zuggtmoy, Air Elemental, Neogi), zero new
- Invalidated: STALE rows [none newly STALE — INV-7/8/9 already STALE from four prior reviews; this change is a fifth independent trigger (engine `state.c`), no new marking needed] | New findings raised: 0 (completion plan's wrong parent sha and the stale "not yet committed" parenthetical recorded as corrections, not findings; the sha is supplied by this entry)
- Review 02 [2026-09-02] at `74f2be31716712d5fb9385c2a524b8747dba3b9e`: **ACCEPTED** [no debt; second independent pass, zero drift since Review 01 — `git diff e9a2702 HEAD` empty for `state.c`/`test_engine.c`/`test_determinize_reshuffle_independence.py`]
- Diff: none new | out-of-scope hunks: 0 | test changes: 0 new
- Conformance: CONFORMANT vs rulebook § Draw a Card, whitepaper § III-C-2 — unchanged, independently re-derived
- Test: `f002_reroll.py` N=100 result=GA1 0/100 (exact match), GA3 3/3 (exact match); `f002b.py` 3/3+3/3+3/3 unchanged; `just test-c` incl. both F-002 C tests green
- Regressions: none — INV-1/2/3/6/4a/4b/5 all exact-match to Review 01's numbers; `openspiel_pyrants` 78/78 excluding 10 pre-existing postponed F-003 Part B RED failures; repo-root suite same 3 pre-existing failures
- Invalidated: STALE rows [none newly STALE] | New findings raised: 0

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
- Status: **CONFIRMED — POSTPONED (ADR-0002)**
- Command: `.venv/Scripts/python.exe -u docs/validation/harness/findings.py` (section F-003)
- N: 2,112 state transitions. Seeds: shuffle_seeds 1-39, uniform-random policy, up to 300 plies each
- Observed:
  ```
  N transitions=2112  shuffle_counter advanced on 134 of them
  of those advances, preceded by is_chance_node()==True: 0
  ```
- Verdict rationale: Matches "Expected if REAL" exactly - 134 mid-game randomization events (6.3% of all transitions) advanced `shuffle_counter` inside an `apply_action`, and not one of them was preceded by a state reporting `is_chance_node()==True`, so every mid-game random event resolves silently inside a player transition rather than as an OpenSpiel chance node.
- Decision [2026-09-02], `docs/adr/0002-postpone-f003-chance-node-exposure.md`: **POSTPONED**, not
  fixed, not dropped. `docs/validation/f002-f003-completion-plan.md` Phase 0/1 (frozen legacy
  baseline across all 7 effective call sites, 10 RED tests in
  `openspiel_pyrants/tests/test_chance_nodes.py`, all confirmed failing for the correct reason)
  landed safely and stay in the tree; Phase 2 (the actual engine change) was scoped in detail and
  found to require inventing a from-scratch C-level suspend/resume mechanism across ten call
  sites — a genuine multi-session cost, sized by investigation. Deferred because: (1) F-008 (the
  branching-factor measurement that would show F-003's actual impact on search quality) is itself
  gated on F-003 landing, so the benefit of fixing F-003 now is unmeasured; (2) `verdict.md`'s own
  § 5 GO conditions already scope F-003 to block only strength/policy-quality/agent-training
  claims, not the 2-player engine/performance work this project is currently doing. See ADR-0002
  for the full reasoning, alternatives considered, and resumption path. F-015 (found as a
  byproduct of scoping this work) is tracked independently and is not postponed by this decision.

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
- Status: **CONFIRMED — FIXED** (working-tree change; not yet committed)
- Command: `.venv/Scripts/python.exe -u docs/validation/harness/findings.py` (section F-004)
- Resolution: `openspiel_pyrants/game_c.py::_build_c_game_info` now declares the honest contract per player count: `n==2` keeps `utility_sum=0.0` / `min_utility=-200.0` / `max_utility=200.0` (byte-identical to pre-fix, its `returns()` is a genuine zero-sum margin); `n>2` declares `utility_sum=None` (general-sum, the documented OpenSpiel convention — omit for general-sum) with `min_utility=-50.0` (conservative, practical floor derived from the `insane_outcast` 30-copy design intent) and `max_utility=400.0` unchanged. `PyrantsCState.returns()` is untouched — the fix corrects the declared metadata to match existing, rulebook-conformant behaviour, not the reward computation. Tests in `openspiel_pyrants/tests/test_utility_contract.py`; gate probe `docs/validation/harness/f004_utility.py`. See `verdict.md` §2 and `docs/validation/f004-fix-plan.md`.
- N: 8 games played to terminal per player count (2, 3, 4) = 24 terminal states (original ledger capture, append-only). Seeds: shuffle_seeds 1-8, uniform-random policy
- Observed:
  ```
  --- num_players=3  utility_sum=0.0 min_utility=-400.0 max_utility=400.0 type=Utility.GENERAL_SUM
     N=8 terminal returns: sum(returns) values=[18.0, 9.0, 9.0, 23.0, 4.0, 8.0, 10.0, 9.0]
     min(returns) values=[4.0, 1.0, 1.0, 0.0, 1.0, 0.0, 2.0, 0.0]   any negative=False
  --- num_players=4  sum(returns) values=[14.0, 14.0, 9.0, 11.0, 8.0, 12.0, 14.0, 9.0]  any negative=False
  ```
- Verdict rationale: Matches "Expected if REAL" - for both 3- and 4-player games `sum(returns())` was strongly positive in 16/16 terminal states (never the declared `utility_sum=0.0`) and no return was ever negative despite `min_utility=-400.0`. The 2-player case was run as a control and did satisfy its zero-sum declaration (`sum(returns)==0.0` in 8/8), which localises the defect to exactly the `num_players>2` branch the finding names.
- Post-fix gate evidence (Phase 4, `docs/validation/harness/f004_utility.py`): G1 — `n==2` `utility_sum=0.0`/`min=-200.0`/`max=200.0` byte-identical; G2 — `n∈{3,4}` `utility_sum=None`/`min=-50.0`/`max=400.0`/`GENERAL_SUM`; G3 — N=50 terminal random-policy games per player count, 0 out-of-bounds returns (`min(returns)=0.0`, `max(returns)=18.0` across 3p/4p), `n==2` `sum(returns)==0.0` in 50/50; G4 — stress probe (T6) worst random-policy return across N=200 greedy-play games per count is −23.0 (2p, within −200) and 0.0 (3p/4p, within −50); direct-struct-injection upper-bound proxy yields −30 at the 30-copy `insane_outcast` design intent and −80 at the MAX_ZONE_SIZE (80) hard cap — see F-014 for the over-issuance gap this exposes.
- Review 01 [2026-09-01] at `<working tree, not yet committed; base b0f3173>`: **ACCEPTED-WITH-DEBT** [F-014 open]
- Diff: `openspiel_pyrants/game_c.py`, `openspiel_pyrants/tests/test_utility_contract.py` (new), `docs/validation/{findings.md,verdict.md,f004-fix-plan.md}`, `docs/validation/harness/f004_utility.py` (new), `docs/validation/baseline/{f004_utility.pre.txt,f004_utility.post.txt}` | out-of-scope hunks: 0 | test changes: 1 file (new, 8 tests), cleared against the Hard Rule 4 gaming checklist (no weakened assertion, no reduced N, no seed-pinning, no swallowed exceptions, no special-cased input)
- Conformance: CONFORMANT vs rulebook § Final Scoring (VP is additive; this is a metadata-only fix, `returns()` untouched), no whitepaper anchor (same as the finding's own citation-free framing)
- Test: `docs/validation/harness/findings.py` (F-004 section) N=8 seeds=1-8 result=declared contract now numerically consistent with observed returns (was violated: `sum≠0`, `min≥0` vs declared `utility_sum=0.0`/`min_utility=-400.0`); `pytest openspiel_pyrants/tests/test_utility_contract.py` 8/8 PASS; `f004_utility.py` T5/T6 re-run byte-identical to `baseline/f004_utility.post.txt`
- Regressions: none — full repo `pytest -q` shows the same 3 pre-existing failures as `f010-review-01.md`/`f011-review-01.md` (Zuggtmoy, Air Elemental, Neogi, all `engine_c`/catalog issues untouched by this diff, confined to `openspiel_pyrants/game_c.py`); `openspiel_pyrants/tests/` 70/70 pass; always-on battery (INV-1/2/3/6) all PASS, N=100/235/1200/30 unchanged
- Invalidated: STALE rows [none newly STALE — INV-7/8/9 already STALE from prior reviews (a third, independent reason via Hard Rule 4c's "the utilities" trigger), not re-counted] | New findings raised: 0 (F-014 already on record, independently reproduced byte-for-byte against `baseline/f004_utility.post.txt`)
- Review 02 [2026-09-02] at `74f2be31716712d5fb9385c2a524b8747dba3b9e`: **ACCEPTED-WITH-DEBT** [F-014 still open; second independent pass, zero drift since Review 01 — `git diff 3508466 HEAD` empty for `game_c.py`/`test_utility_contract.py`]
- Diff: none new | out-of-scope hunks: 0 | test changes: 0 new
- Conformance: CONFORMANT, unchanged, independently re-derived
- Test: `f004_utility.py` T5 N=50/count result=0/50 out-of-bounds, n==2 sum==0.0 (0/50 violations); T6 worst returns/injection bounds byte-identical to Review 01; `test_utility_contract.py` 8/8; G5 grep re-run fresh, same 3 non-production files
- Regressions: none — INV-1/2/3/6 exact-match; `openspiel_pyrants` 78/78 excluding 10 pre-existing postponed F-003 Part B RED failures; repo-root suite same 3 pre-existing failures
- Invalidated: STALE rows [none newly STALE] | New findings raised: 0

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
- Status: **CONFIRMED — CALIBRATED (default kept at 1.4, 2026-09-02)**
- Command: `grep -rn "uct_c|uct-c|exploration constant" --include=*.md docs/ .kilo/` ; `git log --all -S"uct_c" -- scripts/run_ismcts.py` ; `.venv/Scripts/python.exe -u docs/validation/harness/f006.py` ; `.venv/Scripts/python.exe -u docs/validation/harness/f006_sweep.py "0.7,1.4,2.8" 200 200` ; `... "1.4,2.8,8.0" 200 200` ; `... "1.4,8.0" 200 200`
- N: full repo doc/plan/commit-history search (0 tuning artifacts found); 25 sampled root nodes at `num_sims=200` for the reward-scale measurement. Seeds: shuffle_seeds 1-39. Calibration: 4 seat-swapped pairwise sweeps at N=200 per arm, num_sims=200, seeds 1000-1099 — see `docs/validation/f006-fix-plan.md` and `docs/validation/harness/f006_sweep_results.json`
- Observed:
  ```
  .kilo/plans/openspiel-ismcts-pyrants.md:195:--uct-c FLOAT           # default 1.4   <- only occurrence, a spec line
  (no sweep artifact, no comparison doc, no commit tuning uct_c)
  N=25 root nodes (num_sims=200, uct_c=1.4)
    Q-value spread (max-min child value): mean=9.22  median=8.18  max=24.79
    UCT exploration bonus 1.4*sqrt(ln N/n): mean=1.443  -> exploitation:exploration = 6.4 : 1
  ```
- Verdict rationale: Matches "Expected if REAL" on both clauses - no doc, scenario file, or commit shows `1.4` was ever compared empirically for this game (its single appearance is a plan line restating the argparse default), and the reward magnitudes were never re-derived: the paper calibrated `0.7` against rewards normalised to +/-1, whereas this game backs up raw VP differentials with a mean child-value spread of 9.22, leaving the exploration term outweighed 6.4:1. Severity note: this biases the search but does not disable it - the budget-monotonicity check still shows real strength gains with more simulations.
- Calibration outcome (2026-09-02, `docs/validation/f006-fix-plan.md`): the defect was that `1.4` was *uncalibrated*, so a `uct_c` sweep was run on this game's actual reward scale. **The default stays `1.4`** — the sweep found it already ties or beats its tested neighbours, so per the plan's constraint 4 an honest close keeps the existing default. Evidence (seat-swapped, N=200 per arm, num_sims=200, seeds 1000-1099, `docs/validation/harness/f006_sweep_results.json`):
  ```
  uct_c=0.7 vs uct_c=1.4: N=200 winrate=0.482 (W91/L98/T11) p=0.663 mean_margin=-0.70
  uct_c=1.4 vs uct_c=2.8: N=200 winrate=0.507 (W98/L95/T7)  p=0.886 mean_margin=+0.71
  uct_c=2.8 vs uct_c=8.0: N=200 winrate=0.745 (W144/L46/T10) p=5.9e-13 mean_margin=+10.93
  uct_c=1.4 vs uct_c=8.0: N=200 winrate=0.750 (W149/L49/T2) p=6.3e-13 mean_margin=+11.19
  ```
  Reading: the 6.4:1 exploitation-to-exploration ratio and the ~8-9 "equalising" estimate from the raw root-node probe do NOT translate into a strength preference for a high constant — `1.4` beats `8.0` overwhelmingly (p=6.3e-13) and `2.8` also beats `8.0` (p=5.9e-13). Within the low range {0.7, 1.4, 2.8} there is no significant separation (p=0.66, p=0.89); `1.4`-vs-`2.8` reproduced identically across two independent runs (W98/L95/T7 both), confirming F-010 determinism. The concern that exploration is "outweighed 6.4:1" by raw-VP rewards does not materialise as a strength defect at the budgets tested; the raw-VP scale is evidently compressed by the outcome function in a way the root-node spread does not capture. The `uct_c` value is now calibrated to this game and reachable from all three `just` recipes: trailing recipe parameter on `ismcts`/`ismcts-quick` (default `"1.4"`, forwarded as `--uct-c`; just 1.43 positional override syntax, e.g. `just ismcts-quick 1 2 0.7`), and via the existing `*args` passthrough on `ismcts-perf` (e.g. `just ismcts-perf 2 --uct-c 0.7`, signature otherwise untouched). Live-verified through the `summary.csv` `uct_c` column on `ismcts-quick` and `ismcts` (multi-worker); `ismcts-perf` passthrough dry-run-verified. The sweep harness is committed for any future re-check; omitted-argument defaults remain byte-identical (1.4).

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
- Review 02 [2026-09-02] at `2cfd83634005ae3d56b0e575eef83b236ec55f49`: **ACCEPTED-WITH-DEBT** [F-012 open]
- Diff: `docs/validation/{f010-fix-plan.md,findings.md,verdict.md}` (append-only edits), `docs/validation/grug_findings.md` (deleted), `docs/validation/reviews/f010-review-01.md` (new, the Review 01 record itself) | out-of-scope hunks: 0 | test changes: 0 (no production or test file touched; `git diff 028ff9d HEAD --stat` empty for every F-010 production/test path)
- Conformance: CONFORMANT vs [no rulebook/whitepaper anchor, unchanged from Review 01] — code byte-identical to `028ff9d`, independently re-confirmed
- Test: `docs/validation/harness/inv_a.py` + `det_bot.py` + `inv_b.py` + `f002b.py` + `det_isolate.py` + `det_root.py` + `pytest openspiel_pyrants/tests/test_ismcts_reproducibility.py` + `pytest openspiel_pyrants/tests/` + `pytest -q` (repo root) + `just test-c` N=100 (INV-1), N=10 (det_bot B1), N=2400 (INV-5) seeds=1-100/4242/1-200×12 result=INV-1 PASS 0/100 diverged, det_bot B1 1 distinct chosen action `[8]`, INV-5 mean 11.11/12 (0 singletons) — all exact-match to the current ledger's post-F-011 baseline
- Regressions: none — full battery (INV-1/2/3/6) exact-match; `openspiel_pyrants` suite 78/78 non-F-003 tests pass (10 pre-existing F-003 Part B RED failures, postponed per ADR-0002, unrelated); repo-root suite same 3 pre-existing `engine_c`/catalog failures; `just test-c` exit 0
- Invalidated: STALE rows [none newly STALE — INV-7/8/9 already STALE from Review 01, reaffirmed by `f011`/`f004`/`f013-review-01.md`; this commit changes no engine/binding/observation/search code so it is not itself a trigger] | New findings raised: 0

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
- Review 01 [2026-09-01] at `a7cee832287aa8040a3a70b4b1e0223faec2a8f6`: **ACCEPTED-WITH-DEBT** [F-013 open]
- Diff: `engine_c/bindings/c_adapter.py`, `openspiel_pyrants/tests/test_observation_completeness.py` (new), `docs/validation/{findings.md,verdict.md,f011-fix-plan.md}`, `docs/validation/harness/f011_timing.py` (new), `docs/validation/baseline/{inv_b.post.txt,inv_b2.pre.txt,inv_b2.post.txt,f011_timing.pre.txt,f011_timing.post.txt}` | out-of-scope hunks: 0 | test changes: 1 file (new, 8 tests), cleared against the Hard Rule 4 gaming checklist (no weakened assertion, no seed-pinning, no swallowed exceptions; the one loosened-looking bound — a <100µs cost trip-wire — carries 12.8x headroom over the measured 7.8µs baseline, justified in the test's own docstring)
- Conformance: CONFORMANT vs rulebook § Final Scoring (site/troop VP is the primary scoring substrate), no whitepaper anchor (same as the finding's own citation-free framing)
- Test: `docs/validation/harness/inv_b2.py` N=403 seeds=1-139 result=403/403 `private_view_json` now DIFFERS (was 403/403 IDENTICAL); `inv_b.py` INV-4a 0/300 violations, INV-5 mean 11.11/12 (0 singletons); `det_bot.py` B1 1 distinct chosen action unchanged
- Regressions: none — full repo `pytest -q` shows the same 3 pre-existing failures as `f010-review-01.md` (Zuggtmoy, Air Elemental, Neogi, all `engine_c`/catalog issues untouched by this diff); `openspiel_pyrants/tests/` 63/63 pass; always-on battery (INV-1/2/3/6) all PASS
- Invalidated: STALE rows [none newly STALE — INV-7/8/9 already STALE from F-010 Review 01, not re-counted] | New findings raised: 0 (F-013 already on record, independently reproduced at 9.655x vs claimed 9.66x)
- Review 02 [2026-09-02] at `74f2be31716712d5fb9385c2a524b8747dba3b9e`: **ACCEPTED-WITH-DEBT** [F-013 still open]
- Diff: none new to F-011 itself (`git diff a7cee83 HEAD` for `state_c.py`/`test_observation_completeness.py`/`view.py` empty); `engine_c/bindings/c_adapter.py` drifted (+26/-15) but entirely inside F-013's own already-reviewed `16f8712` cache commit — the six-key board projection dict-literal body is byte-identical, only wrapped in a populate-once cache | out-of-scope hunks: 0 | test changes: 0 new to F-011
- Conformance: CONFORMANT vs rulebook § Final Scoring, unchanged from Review 01, independently re-derived rather than carried over
- Test: `docs/validation/harness/inv_b2.py` N=403 seeds=1-139 result=403/403 differs (exact match to Review 01); `inv_b.py` INV-4a 0/300, INV-5 mean 11.11/12 exact match; `test_observation_completeness.py` 8/8 pass incl. G4 trip-wire; `det_bot.py` B1 1 distinct action unchanged
- Regressions: none — full repo suite same 3 pre-existing failures; `openspiel_pyrants/tests/` 78/78 excluding the 10 pre-existing postponed F-003 Part B RED failures (unrelated); `just test-c` exit 0; F-013's own 5-test cache suite 5/5
- Invalidated: STALE rows [none newly STALE] | New findings raised: 0

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

### F-013 Board projection regresses `private_view_json` cost 9.66×; Part A cache + Part B cheap pure-Python projection close the residual
- Class: ENGINE-OPENSPIEL
- Severity: MINOR (performance — non-blocking for 2-player engine work, blocking for any large-scale ISMCTS throughput claim)
- Origin: **Found by the F-011 fix while re-running the G5 timing gate.**
- Code: `engine_c/bindings/c_adapter.py::_board_nodes_view` (added by F-011) calls `engine_c/bindings/view.py::build_c_board_view`, which invokes `engine_build_view` (`engine_c/view.c`) — a monolithic C projection that `memset`s the full `CGameView` and populates every card zone for every player (4 × 80) plus every board node (128) and three `remaining_special_stack_count` scans, ~388 µs/call — while the board-only wrapper reads back only the `nodes` array.
- Disagreement: `private_view_json` is called once per ISMCTS node expansion for every observing player, so the ~388 µs board cost (vs ~24 µs for the rest of the call) lands on the hot path. Measured end-to-end search wall-time at `num_sims=200` rose 9.66× (0.165 s → 1.589 s).
- Steelman: correctness first — the F-011 observation gap is blocking and had to be fixed regardless of cost; the two-tier snapshot design was preserved (Tier-1 `_build_public_dict` untouched), and the regression is a constant-factor slowdown, not a complexity change.
- Falsification test: `python -u docs/validation/harness/f011_timing.py` before/after, compare mean wall-time.
- Expected if REAL: mean wall-time ratio > 2×.
- Status: **CONFIRMED — FIXED** (Phases 2-4 of `docs/validation/f013-part-b-fix-plan.md`, commits `1564bdd`/`13c3fe4`/`f9157a4`)
- Resolution (Part A, `16f8712`): cache the player-agnostic board projection on `CEngineAdapter` (`_board_cache`), invalidated on `apply()` — the sole state-reassignment site on an existing adapter. Per-adapter repeated `private_view_json` calls now build the board once instead of once per call (G3, `openspiel_pyrants/tests/test_board_view_cache.py::test_repeated_calls_hit_the_cache`).
- Resolution (Part B, this plan): make the projection cheap, not just cached. Measurement showed the C `engine_build_view` call is 3.1 µs of ~400 µs (`docs/validation/f013-part-b-fix-plan.md` § 1), so the residual was Python-side and fixable without touching C. Four pure-Python levers landed: (L3) a private `_project_board_nodes` fast path reading `CGameView` straight into the six output fields, a shared memoised `sym_str` (`engine_bindings.py`, cleared by the new `intern_destroy()` wrapper), and board-static field hoisting into `_board_static`; (L1) a per-player `private_view_json` string cache cleared on `apply()`/`destroy()`; (L2) `_board_cache`/`_board_static` propagation across `determinize()`/`__deepcopy__`, guarded by the determinize-never-touches-the-board invariant (T9 behavioural + T10 structural). The narrower C-level accessor recommended by Part A § 9 is **withdrawn** (§ 9 below): it could save at most 0.8% of the cost it was meant to remove.
- Command: `.venv/Scripts/python.exe -u docs/validation/harness/f013_timing.py` (baselines `docs/validation/baseline/f013b_timing.{pre,post}.txt`)
- Observed (Part B, freshly re-captured because the tree moved since Part A): `f013b_timing.pre.txt` mean 0.7144 s → `f013b_timing.post.txt` mean 0.2643 s = **2.70× faster (−63%)**, i.e. **1.61× vs. the pre-F-011 0.1646 s baseline — under the 2× gate**. Census (`f013b_census.py`): cold `_board_nodes_view` 443.5 µs → 107.3 µs; board projections per search 876 → 676 (gen0 201 → 1); repeat reads served without re-serialization 0 → 1076. The Part A numbers (1.7453 → 1.0500 s, 6.38× residual) are retained below as the historical record.
- Verdict rationale: Part B clears every acceptance gate on the freshly re-captured pre-fix baseline (G1 byte-identity over 302 corpus states incl. 130 spy states, G2 invalidation on mutation/destroy, G3 ≤120 µs, G4 1076/676, G5 −63% ≥ 40%, G6 invariants unchanged, G7 suites same pre-existing failures only). G0 holds: the diff touches only `engine_c/bindings/{c_adapter,view,engine_bindings}.py`, `engine_c/bindings/test_label_enrich.py`, `openspiel_pyrants/tests/{test_board_view_cache.py,test_board_projection.py,_f013b_corpus.py}` and `docs/validation/*`. See Review 03 for the adversarial pass.
- Residual (none — the C-level accessor is withdrawn): the plan's own honest projection was ~3.0-3.9× after Phases 2-4; the measured 1.61× beats it because the freshly re-captured pre-fix baseline (0.7144 s) was already well below Part A's 1.0500 s (the tree moved — F-014 and other work landed since). The residual above 1× is the irreducible cost of F-011's correctness fix: the info-state key legitimately contains the board and own discard, so distinct states per search must each be projected and serialized.
- Review 01 [2026-09-01] at `16f8712f9df2e015c5e88b9be6b82b7763a906c6`: **ACCEPTED-WITH-DEBT** [residual ~6.4× wall-time regression vs. pre-F-011 baseline persists; ledger's "under the 2× gate" phrasing independently corrected, see reviews/f013-review-01.md §1/§6]
- Diff: `engine_c/bindings/c_adapter.py`, `openspiel_pyrants/tests/test_board_view_cache.py` (new), `docs/validation/{findings.md,verdict.md,f013-fix-plan.md}`, `docs/validation/harness/f013_timing.py` (new), `docs/validation/baseline/{f013_timing.pre.txt,f013_timing.post.txt}` | out-of-scope hunks: 0 | test changes: 1 file (new, 5 tests), cleared against the Hard Rule 4 gaming checklist (no weakened assertion, no reduced N, no seed-pinning, no swallowed exceptions, no special-cased input)
- Conformance: CONFORMANT — no rulebook/whitepaper anchor (pure engine-binding performance concern, same posture as F-010); behavioral parity (G1) independently re-verified via T1's control and a standalone live repro
- Test: `docs/validation/harness/f011_timing.py` (the pre-registered script, not the new `f013_timing.py`, per Hard Rule 3) N=10 seeds=fixed-root(42)+bot(131)/search-seeds(1000-1009) result=mean_wall=1.0569s; ratio vs. the pre-F-011 baseline (0.1646s) = **6.42×** — still matches the finding's own "Expected if REAL" (>2×); down from 9.66× but not eliminated, consistent with `MITIGATED` not `FIXED`
- Regressions: none — INV-1/2/3/6 exact-match re-run (N=100/235/1200/30, 0 violations), INV-4a/INV-4b/INV-5 exact-match (0/300, 403/403, mean 11.11/12), F-010 `det_bot.py` B1 unchanged (1 distinct action), F-002 `f002b.py` unchanged (3/3+3/3+3/3), `openspiel_pyrants/tests/` 78/78 pass, full repo suite same 3 pre-existing `engine_c`/catalog failures (Zuggtmoy, Air Elemental, Neogi), zero new
- Invalidated: STALE rows [none newly STALE — INV-7/8/9 already STALE from prior reviews, not re-counted] | New findings raised: 0 (the G4-gate-characterization imprecision is folded into this review's verdict, not filed separately)
- Review 02 [2026-09-02] at `74f2be31716712d5fb9385c2a524b8747dba3b9e`: **ACCEPTED-WITH-DEBT** [residual regression persists, unchanged debt from Review 01; second independent pass, zero drift since Review 01]
- Diff: none new | out-of-scope hunks: 0 | test changes: 0 new
- Conformance: CONFORMANT — unchanged, independently re-derived; G2 re-verified via a fresh, independently-written live repro (not reused from Review 01)
- Test: `f011_timing.py` N=10 result=mean_wall=1.1311s, ratio vs pre-F-011 baseline (0.1646s) = **6.87×** (still matches "Expected if REAL"; run-to-run wall-clock variance vs. Review 01's 6.42×, not a code change)
- Regressions: none — T1-T5 5/5, INV-1/2/3/6/4a/4b/5 exact-match, F-010/F-002 unchanged, `openspiel_pyrants` 78/78 excluding 10 pre-existing postponed F-003 Part B RED failures, repo-root suite same 3 pre-existing failures, `just test-c` exit 0
- Invalidated: STALE rows [none newly STALE] | New findings raised: 0
- Review 03 [2026-09-03] at `f9157a4` (Part B code tip; Phase 7 docs at `HEAD`): **ACCEPTED** — F-013 closed as **CONFIRMED — FIXED**. Adversarial pass over `docs/validation/f013-part-b-fix-plan.md` Phases 1-6 (`docs/validation/reviews/f013-review-03.md`). Zero out-of-scope hunks (G0 file set only). Byte-identity re-verified against the frozen Phase-0 corpus (302 states / 918 player-vectors incl. 130 spy states). INV-1/2/3/6/4a/4b/5 and `det_bot.py`/`f002b.py` reproduce **identical numbers to a pre-change run in the same environment** (INV-5 mean 11.48/12 min 8 — matching the environmental drift from the historical 11.11/7 record, which a temp-worktree pre-change run confirms is not this fix). Wall-time measured 1.61× vs the pre-F-011 baseline, under the 2× gate. The narrower C-level accessor recommendation is withdrawn with measured justification.
- Diff (Part B): `engine_c/bindings/{c_adapter,view,engine_bindings}.py`, `engine_c/bindings/test_label_enrich.py`, `openspiel_pyrants/tests/{test_board_view_cache,test_board_projection}.py`, `openspiel_pyrants/tests/_f013b_corpus.py` (new), `docs/validation/harness/{f013b_census,f013b_gen_vectors}.py` (new), `docs/validation/baseline/f013b_*.{pre,post}.txt` + `f013b_view_vectors.jsonl` (new), `docs/validation/*` | out-of-scope hunks: 0 | test changes: T1-T12 new in `test_board_projection.py`, cache-suite T4 superseded / T2 re-pointed in `test_board_view_cache.py`, cleared against the Hard Rule 4 gaming checklist
- Conformance: CONFORMANT — no rulebook/whitepaper anchor (pure engine-binding performance concern, unchanged posture); behavioral parity (G1) re-verified across the whole corpus
- Test: `harness/f013_timing.py` N=10 pre=0.7144s post=0.2643s → ratio vs pre-F-011 baseline (0.1646s) = **1.61×**, under the 2× gate; census G3 107.3µs (≤120), G4 projections 676 (≤700) + 1076 reads served w/o re-serialization, G5 −63% (≥40%)
- Regressions: none — all F-013B tests green, `openspiel_pyrants/tests/` only the 10 pre-existing postponed F-003 Part B RED failures (chance-node teardown also drops pytest's final counts line in this environment; reproduced identically on a pre-change worktree), repo-root suite same 3 pre-existing failures (Zuggtmoy, Air Elemental, Neogi), `just test-c` exit 0
- Invalidated: STALE rows [none newly STALE] | New findings raised: 0 (the withdrawn C-accessor recommendation is a record correction, not a new finding)

### F-014 `give_insane_outcast` mints fresh instances without its 30-copy special-stack cap
- Class: ENGINE
- Severity: MAJOR (bounds the honestness of the F-004 `min_utility` declaration; no demonstrated effect on ordinary play)
- Origin: **Found by the F-004 fix's T6 stress probe (`docs/validation/harness/f004_utility.py`), not by the static pass.**
- Code: `engine_c/actions.c:698-705` (`give_insane_outcast`) appends `intern("insane_outcast")` directly to a target's `discard_pile` up to `MAX_ZONE_SIZE` (80, `state.h:16`), never calling `remaining_special_stack_count` or consulting the 30-copy `special_stack_config` cap (`engine_c/helpers.c:266`, `market_slot==102` declares `stack_total=30`). The 30-copy figure therefore governs only the shared *market* supply's replenishment display, not what the four `give_insane_outcast_*` effect handlers can mint.
- Rulebook: `docs/tyrants-rulebook.md` § Final Scoring (line 398) — VP is additive; `insane_outcast` is the single negative-`deck_vp` card (`data/cards/insane_outcast.json`: `"deck_vp": -1`, notes confirm "a negative-VP card opponents can force into your deck").
- Whitepaper: [absent]
- Disagreement: `compute_final_scores` (`scoring.c:90-126`) sums `cards_vp(...)` over each player's hand+deck+discard, and `cards_vp` adds `insane_outcast`'s `-1` per copy. With no issuance cap, the *true* worst-case negative `deck_vp` contribution is `-MAX_ZONE_SIZE` (= −80) per player zone, not −30 as the shared-supply design intends. The direct-struct-injection upper-bound probe (T6, part 2) measured this exactly: `final_score` = −30 at the 30-copy design intent, −80 at the 80-copy hard cap. Random greedy play (T6, part 1) never came close — worst observed return across N=200 greedy games per player count was −23.0 (2p) and 0.0 (3p/4p) — so this is a latent, not demonstrated, gap.
- Steelman: the 30-copy cap is a *market-stack* display figure; the six `give_insane_outcast_*` handlers mint "a fresh Insane Outcast" per the cards' own `rules_text` ("Give an Insane Outcast to each opponent"), which arguably should draw from — and be bounded by — the shared supply, but the engine currently treats the special stack as infinite. F-004 accepted this explicitly (§ 1 load-bearing detail) as out-of-scope for the `GameInfo` metadata fix and chose `min_utility=-50.0` as a conservative *practical* bound above the −30 design intent, rather than a formally tight bound.
- Falsification test: force-inject `insane_outcast` copies into one player's discard pile at counts 30/50/80 (direct struct surgery), call `compute_final_scores`/`returns()`, and compare against the declared `min_utility=-50.0`.
- Expected if REAL: a return below −50.0 is reachable (e.g. −80 at the 80-copy hard cap), meaning the declared floor is practical, not tight, and the engine's uncapped issuance is the root cause.
- Expected if FALSE POSITIVE: the 30-copy cap is actually enforced somewhere, and no injection beyond 30 produces a return below −50.0.
- Status: **CONFIRMED — FIXED** (working-tree change; not yet committed) — contingency per `docs/validation/f004-fix-plan.md` § 11; plan: `.kilo/plans/1788349243964-insane-outcast-supply-cap-plan.md`
- Command: `.venv/Scripts/python.exe -u docs/validation/harness/f004_utility.py` (section T6, "direct injection upper bound")
- N: direct-injection at counts {30, 50, 80} for each of `num_players` ∈ {2,3,4} = 9 measurements
- Observed:
  ```
  num_players=2 inject=30 -> final_score[0]=-30 (n==2 diff=-30.0)
  num_players=2 inject=50 -> final_score[0]=-50 (n==2 diff=-50.0)
  num_players=2 inject=80 -> final_score[0]=-80 (n==2 diff=-80.0)
  num_players=3 inject=30 -> final_score[0]=-30 (n>2 raw=-30.0)
  num_players=3 inject=50 -> final_score[0]=-50 (n>2 raw=-50.0)
  num_players=3 inject=80 -> final_score[0]=-80 (n>2 raw=-80.0)
  num_players=4 inject=30 -> final_score[0]=-30 (n>2 raw=-30.0)
  num_players=4 inject=50 -> final_score[0]=-50 (n>2 raw=-50.0)
  num_players=4 inject=80 -> final_score[0]=-80 (n>2 raw=-80.0)
  ```
- Verdict rationale: Matches "Expected if REAL" — the 30-copy cap is not enforced by `give_insane_outcast`; every injected copy above 30 drove the score below the declared −50 floor in direct proportion, confirming the floor is practical (validated at −30 for the design intent) rather than formally tight. Random greedy play never approached it (worst −23.0), so the finding is `OPEN`, not a blocker: F-004's `min_utility=-50.0` stands as a labeled-practical bound, with this finding carrying the residual risk per `docs/validation/f004-fix-plan.md` § 11.
- Resolution [2026-09-02]: `give_insane_outcast` (`engine_c/actions.c`) now enforces the shared supply cap: it looks up the stack total via the new `special_stack_total_for_card` (`engine_c/helpers.c`), no-ops when the stack is undefined (D6), and grants `min(count, remaining)` per copy with `remaining` re-evaluated each mint, so legal play can never mint a 31st `insane_outcast` game-wide. Exhaustion order for `give_insane_outcast_to_each_opponent` now allocates clockwise from the current player (rulebook `docs/tyrants-rulebook.md:355`). The 15/15/30 totals and the slot→card mappings are read from the setup JSON's new `special_stacks` array (`engine_c/state.h`/`loader.c` parse + legacy 15/15/30 fallback when absent, D2); the aberrations gate (`is_aberrations_enabled`) is deleted and slot-102 gating is now "the insane stack is defined" (demons market, D1). Python side: `game_setup/market_setup.py` `compute_special_stacks` returns `(slot, card_id, stack_total)` specs with totals loaded from the `single_card_stack` rosters, demons-gated; `MarketSetup.to_setup_data()` and `data/decks/base_setup.json` emit `special_stacks`. Falsification test = T1 `tests/c_engine/test_insane_outcast_supply.py`; full suite green with only the 3 pre-existing tolerated failures (Zuggtmoy, Air Elemental, Neogi) and the 10 postponed F-003 Part B RED tests. Post-fix the `-30`/`-50`/`-80` direct-injection bounds are no longer reachable by legal play — `min_utility=-50.0` is now a formally safe bound (the D3 follow-up to tighten `min_utility` to `-30.0` is recorded in `verdict.md`).

### F-015 `neogi`'s end-of-turn `force_discard` fires twice: once inline during pending-generic resolution, once again at real end-of-turn
- Class: ENGINE (card execution model)
- Severity: MODERATE (wrong game outcome for one specific card; not a crash, not blocking GO on its own)
- Origin: **Found while investigating `docs/validation/f002-f003-completion-plan.md`'s F-003 Part B M4 milestone** (mapping the ten § 1(b) reshuffle/forced-discard call sites to concrete triggering cards). Promotes the pre-existing `[unverified]` suspicion at § 4 Unanchored (below): "whether these are genuinely mutually exclusive... or can both fire for the same card, causing a double discard, was not traced through the full call graph" — now traced by direct execution (not left in § 4, per Hard Rule 7 the existing § 4 bullet is not edited).
- Code: `engine_c/generic_runtime.c:519-548` (`end_of_turn_mass_discard` interceptor, fires inside `auto_resolve_pending_generic`'s action-advance walk) and `engine_c/rules.c:504-561` / `:597-603` (`apply_end_of_turn_effects`, called from `enter_end_of_turn`/`apply_resolve_end_of_turn` on the real `PHASE_MAIN`→`PHASE_END_OF_TURN` transition) both key off the identical `(op=="force_discard", target_scope=="opponent", source_fragment=="end_of_turn_mass_discard")` triple on the same card action (`data/cards/neogi.json` `action_2`, tagged `"timing": "end_of_turn"`). `generic_runtime.c`'s action-advance loop does not filter by an action's `timing` field at all — it walks every action in a card's `execution_model.actions` sequence in order regardless of tag, so the `timing:"end_of_turn"`-tagged discard still fires immediately, inline, the moment its turn in the sequence comes up during `PHASE_MAIN` pending-generic resolution — then `apply_end_of_turn_effects` fires the *same* action again, correctly, when the turn actually ends.
- Rulebook: Neogi's own `rules_text` (`data/cards/neogi.json`): "Deploy 4 troops. At end of turn, each opponent discards a card" — singular, one discard per opponent per play; `notes` confirms "makes each opponent discard 1 card from hand."
- Whitepaper: [absent] — pure engine/card-execution-model concern, not an ISMCTS/OpenSpiel conformance question.
- Disagreement: playing Neogi discards **two** cards from each opponent's hand, not one (Observed below).
- Steelman: none found — both code paths key off the identical source-fragment string with no guard (e.g. an "already resolved this action" marker) preventing the second fire; the rules text and notes both say "1 card," so this reads as an oversight, not an intentional double-trigger design.
- Falsification test: build a 2-player scenario (`tests/c_engine/card_test_helpers.py`-style direct construction) with `neogi` in `p1`'s hand and 4 cards in `p2`'s hand; play `neogi`, resolve all 4 deploys, then submit `end_main_phase`; track `p2`'s `hand_count` and `shuffle_counter` at each step.
- Expected if REAL: `p2`'s hand count drops by 2 total — once during pending-generic resolution, once again at the end-of-turn transition.
- Expected if FALSE POSITIVE: `p2`'s hand count drops by exactly 1, with only one of the two code paths actually firing for this card.
- Status: **OPEN**
- Command: ad hoc diagnostic (reproduced live via `tests.c_engine.card_test_helpers.make_card_test_session`; not yet promoted to a permanent `docs/validation/harness/*.py` script)
- N: 1 traced scenario (2 players, `neogi` vs. a 4-card opponent hand); deterministic in *that* two discards happen (not in *which* cards are discarded)
- Observed:
  ```
  initial:                                            shuffle_counter=3, p2 hand=4
  after 4th deploy resolves (still PHASE_MAIN,
    pending_generic clears):                          shuffle_counter=4, p2 hand=3
  after end_main_phase (PHASE_MAIN -> PHASE_END_OF_TURN): shuffle_counter=5, p2 hand=2
  ```
- Verdict rationale: Matches "Expected if REAL" exactly — two independent discards, two independent `shuffle_counter` advances, for a card whose rules text specifies one. Folded into `docs/validation/f002-f003-completion-plan.md`'s F-003 Part B M4 milestone rather than fixed standalone, since M4 already has to touch both `generic_runtime.c`'s interceptor and (per the original fix plan's D5) resolve whether `rules.c:530-538` is a duplicate of one of the `generic_runtime.c` variants — the answer, now traced: not a duplicate, an unguarded double-fire of the same action, and M4's chance-node conversion of this site should produce exactly one discard per opponent, not two.

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
