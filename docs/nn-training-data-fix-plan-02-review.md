# NN Training Data — Review of Fix Plan 02's implementation (`23196b7`)

Scope: does the committed tree do what `nn-training-data-fix-plan-02.md` says it does, and
what did the commit change that the plan did not ask for? Base: HEAD `23196b7`, clean working
tree, 2026-09-11. Reviewer did not write the fix. Every claim below was re-measured on this
tree, not read off the plan's status line.

Short version: **the four findings and six cleanups are implemented as specified, every named
test exists and asserts what the plan asked, and both encoders are at v3.** Phase 5 is not
finished, and the commit bundled an unrelated engine change that broke the plan's central
premise ("no run needs repeating — `replay.json` is canonical"). Verdict:
**ACCEPTED-WITH-DEBT** — the debt is § 3.

---

## 0. Gates, re-run

| gate | plan's Phase-0 baseline | measured now | delta |
|---|---|---|---|
| `pytest tests/nn tests/test_build_nn_dataset.py tests/c_engine/test_pending_context_full.py tests/test_run_ismcts_layer0.py tests/test_run_ismcts_decision_telemetry.py` | 97 passed | **115 passed**, 0 failed | +18 new tests |
| `pytest tests/ -q` | 4 failed (3× F-015, 1× F-022) | **5 failed** | **+1** `tests/test_replay_loader.py::test_load_replay_real_artifact_setup_sha_matches` |
| `pytest openspiel_pyrants/tests/ -q` | 10 failed (all F-003) | **11 failed** | **+1** `test_board_projection.py::TestProjectionDifferential::test_private_view_json_byte_identical_to_reference` (F-013's G1 gate) |
| `PYRANTS_NN_CENSUS=1 pytest tests/nn/test_actions.py` | green over 139 dirs | green: **141 dirs, 95 walked, 46 skipped as desync**; 0 collisions | population −33 % |
| `ruff check` on every changed module | clean | clean | — |
| `just test-all` shape (T1.1) | recipe aborted on line 1 | probe justfile: both trees run in all three cases, exit 1 if either fails | fixed |
| `datasets/quick` | v2 | v3, 2 games, 1,653 samples, leak 0/70 | rebuilt |
| `datasets/sims_vs_wins_v2` | v2, 120 games, 101,230 samples | **still v2** | **not rebuilt** |

The two new test failures share one root cause (§ 3, N-1) and are recorded nowhere.

---

## 1. Finding by finding

### R-1 seat blocks rotate — DONE

`observation.py:343` indexes `seat_features` with `summaries.get(order[i], {})`;
`observation.py:332` computes `seat_is_current` as `order[i] == current_id`;
`observation.py:37` pins `ENCODER_VERSION = 3`. `OBS_LAYOUT` and `OBS_SIZE` are untouched, as
the plan required.

Tests T2.1–T2.5 all exist and assert the contract. T2.1
(`tests/nn/test_observation.py::test_seat_features_are_perspective_relative`) checks slot `k`
equals `summaries[order[k]]` for every seat in 3- and 4-player states and zero-fills the
absent seats. T2.2 pins `[1, 0, 0, 0]` for 2/3/4 players. T2.5 confirms slot 0's `score` and
`final_scores[0]` belong to the same player through `iter_samples`.

One soft spot: T2.1's "block differs between perspectives" is guarded by
`if len(set(summary_sets.values())) > 1` (`test_observation.py:142`). If the fixture ever
produced identical summaries across seats, the whole test would pass under the v2 bug too.
The plan asked for a fixture "with distinct `discard_size`"; the test should assert that
precondition rather than skip on it (§ 3, N-4).

### R-2 structured placement keys on trophy colour — DONE

`actions.py:355-399` (`_structured_placement_offset`) parses `<sp>:<idx>:<node>:<slot>`,
resolves the colour through `ctx.trophy_halls[sp][idx]`, and routes to
`assassinate[node × owner_slot(colour)]`. The `steal_white_trophy_to_board` special case is
gone; all three structured kinds go through one rule. Malformed / out-of-range / non-seat
colours raise `UnmappedMoveError` naming op and shape. `ACTION_SPACE_VERSION = 3`
(`actions.py:44`), sizes unchanged.

T3.1 and T3.2 (pure) match the plan row for row. T3.3
(`tests/nn/test_actions_live_custom_effects.py::test_lich_deploy_from_trophy_hall_maps_each_trophy`)
asserts no gid merges two colours and the count doubles 23 → 46 on a live Lich state. T3.9's
table rows expect the colour-keyed slot.

Sensible deviation: T3.3 uses hall `["white", "p1"]` in a 2-player game, not the plan's
`["white", "p3"]`. The encoder (correctly) refuses a `p3` colour in a 2-player game, and T3.2
pins that refusal.

### R-2b census reports its coverage — DONE mechanically, went backwards in substance

`tests/nn/test_actions.py:636-718` — `_semantic_key` for a structured target is
`("troop", node, colour)` with the colour read from `ctx.trophy_halls`, not from the
encoder. `_CHOICE_BRANCHES` (`:728`) lists eight branches (the plan's table said "six" but
listed eight; the implementer caught it and included the two `give_insane_outcast_*` kinds).
`_UNCOVERED_BY_CENSUS` (`:741`) names a live test per uncovered branch and the full walk asserts
`covered | listed == _CHOICE_BRANCHES` and `covered & listed == ∅`. Branch and sub-block
counts are checked against `_EXPECTED_BRANCH_COVERAGE` / `_EXPECTED_SUB_BLOCK_COVERAGE`.
Seven live tests exist (`test_actions_live_custom_effects.py`), one per uncovered branch.
T3.4's Orcus setup was probed: p1's hall is `(white, white, white, p2)`, so both the
same-colour merge and the different-colour split are exercised.

But compare the plan's R-2b table with the checked-in expected table:

| effect_kind | plan's census (139 games) | `_EXPECTED_BRANCH_COVERAGE` now |
|---|---|---|
| `self_purge_to_supply` | 5,122 states | **0 — moved to `_UNCOVERED_BY_CENSUS`** |
| `give_insane_outcast_to_selected_player` | 89 | **0 — `_UNCOVERED_BY_CENSUS`** |
| `give_insane_outcast_to_player_with_presence…` | 32 | **0 — `_UNCOVERED_BY_CENSUS`** |
| `steal_white_trophy_to_board` | 6 | 6 |
| the four the plan flagged as uncovered | 0 | 0 (live tests added) |

The plan's complaint was "4 of 8 branches have no live-engine census coverage". The tree now
has **7 of 8** in `_UNCOVERED_BY_CENSUS`. The census reaches exactly one `custom_effect`
branch, six times. The mechanism is § 3, N-1; the accounting is honest (the test prints
`CENSUS_SKIPPED_DESYNC 46` and the docs say so), but a gate that lists seven of eight branches
as "covered elsewhere" is a thinner gate than the one the plan set out to build.

### R-3 extended-read failure degrades to base — DONE

`pending_context.py:105` — `return base`. T1.2 monkeypatches `sym_str` to raise on option
ids; asserts the result is not `None`, has exactly the six base keys, and equals the base
reader's dict.

### R-4 `just test-all` runs both trees — DONE

`justfile:31` is the plan's one-line recipe. Probed with a mirror justfile whose two pytest
calls are `exit 0`/`exit 1` stand-ins: fail-first → both run, exit 1; fail-second → both run,
exit 1; both-ok → exit 0.

### R-5 cleanups — all six DONE

| # | verified |
|---|---|
| m1 | `actions.py` comments read 240 / 1,516 |
| m2 | `dataset.py:194-195` writes `op_index_sha`, `effect_index_sha`; T4.2 asserts them; `datasets/quick/manifest.json` carries them |
| m3 | both clamps replaced by `UnmappedMoveError` (`actions.py::_option_offset`, `observation.py` pending block); T4.3 in both test files |
| m4 | `_nn_dataset.py:72-80` returns `None` on empty denominators; T4.4 |
| m5 | `_has_pair_merge(gids, …)` takes the already-mapped gids; one `move_to_global_action` per payload |
| m6 | F-026 Resolution now says step 1 routes to `player` by source; counts reconciled to 139 — **and already drifted to 141** (§ 3, N-3) |

---

## 2. Engine facts this review depends on (verified)

| fact | where | how |
|---|---|---|
| `insane_outcast` became non-recruitable in the same commit | `data/decks/base_setup.json:43` (`"recruitable": false`), `engine_c/rules.c:188`, `engine_c/helpers.c:269-272, 516`, `engine_c/loader.c:434-442, 460-461` | `git show HEAD` |
| a `special_stacks` entry with no `recruitable` key defaults to recruitable | `loader.c:461` `json_bool(js, "recruitable", true)` | read |
| the `sims_vs_wins` run has no `manifest.json` | `artifacts/ismcts/experiments/sims_vs_wins/20260902T215139Z_65cdce971bcf/` | `FileNotFoundError` on probe |
| with no manifest, the replay loader recomposes the setup from the **current** `base_setup.json` | `interface/replay_loader.py:127-155` (`_manifest_setup` → `return recomposed`), `:255` (`_build_setup_json`) | read + probe: `bundle.setup_json` carries `"recruitable": false`, `setup_sha_matches=False` |
| all 46 census skips are `('recruit', 'insane_outcast')` | `CENSUS_SKIPPED_DESYNC` output | full walk |
| the builder rejects a game on `setup sha mismatch` before it can desync | `scripts/_nn_dataset.py:169` | read; `nn-training-data.md:152` confirms "rejects all 120" |
| F-013's G1 reference has `"discard": ["insane_outcast", …]` at `playout_s11_d6` | `openspiel_pyrants/tests/test_board_projection.py:130` | ran the test alone |

---

## 3. What the implementation got wrong or left blind

Severities are proposals; the ledger owner assigns.

### N-1 An unrelated rule change rode in the same commit and invalidated the plan's premise — MAJOR (process)

The commit message admits it: "concurrent working-tree work: insane_outcast not directly
recruitable (setup+engine)". Fix Plan 02 § 0 said: *"Nothing here changes what the runner
writes, so `schema_version` stays 2 and no run needs repeating."* That was true of the plan
and false of the commit. Three consequences:

1. **The census lost a third of its corpus.** 46 of 141 games desync at `recruit
   insane_outcast` and are skipped whole — including every state before the desync. All
   5,122 `self_purge_to_supply` states and all 121 `give_insane_outcast_*` states left the
   live census (§ 1, R-2b table).
2. **The 120-game dataset cannot be rebuilt to v3.** The `recruitable` key changed the setup
   SHA; the builder rejects all 120 legacy games. The only v3 dataset on disk is
   `datasets/quick` — 2 games, 1,653 samples. `nn-training-data.md:152-157` records this
   honestly and says "rebuild it only from a fresh run". Phase 5 step 4 is therefore half
   done and no v3 dataset of training size exists.
3. **One new test failure per tree, neither recorded.** `test_load_replay_real_artifact_setup_sha_matches`
   (the stored `game_0000` artifact's sha no longer matches the recomposed setup) and F-013's
   G1 byte-identity gate (`test_private_view_json_byte_identical_to_reference` — the frozen
   corpus playout recruited `insane_outcast`). F-013's test docstring says "This must stay
   true through all phases." Neither failure is in `findings.md`, and the Fix Plan 02 closure
   note there says only that "the targeted suite was re-run as two trees" — Phase 5 step 2
   (`just test-all`, no new failures vs. baseline) was never recorded because it would have
   shown +1/+1.

**The corpus is recoverable.** The desync is not the engine refusing to replay old games; it is
the loader handing the engine today's setup. `loader.c:461` already defaults a missing
`recruitable` to `true`, so a run recorded before the key existed is *meant* to replay as
recruitable. `_build_setup_json` (`replay_loader.py:255`) recomposes from the current file and
so injects `"recruitable": false` into a 2026-09-02 game. Teaching the recomposer to omit (or
set true) `recruitable` for runs older than the key — a manifest-less run is by construction
such a run — would return the 46 games to the census and let all 120 build at v3, modulo the
setup-SHA strictness gate, which exists to catch exactly this and would need a documented
`--allow-setup-drift`-style escape. Whether to do that or to spend a day of compute on a fresh
120-game run under the new rule is a decision the ledger owner should make and record; today it
is made by default and the default is "no dataset".

### N-2 Phase 5 is not finished — MODERATE

| step | status |
|---|---|
| 1. census 0 collisions, coverage asserted, pair merges ≤ 0.25 % | done |
| 2. `just test-all`, no new failures vs. Phase-0 baseline | **not recorded; fails (+1/+1)** |
| 3. `just ismcts-quick` 2/2, strict, leak 0, non-null metrics | done (`nn-training-data.md:138-150`) |
| 4. rebuild `datasets/quick` and `datasets/sims_vs_wins_v2` | **half** — quick only |
| 5. close F-030..F-033; delete v2 once v3 accepted | closed; v2 correctly kept (v3 not accepted for it) |

The plan's own status line reads "**implemented**". "Implemented, Phase 5 open" would be accurate.

### N-3 The coverage table cannot say what corpus it was baked on — MINOR

`_EXPECTED_BRANCH_COVERAGE` is asserted equal to the walk, so it *must* reflect 141 dirs / 95
walked — yet `findings.md:69,794`, `nn-training-data.md:250` and the plan all say 139 / 93.
m6 asked to reconcile the count "to one number with the command that produces it"; the command
is there, the number has already moved (the `just ismcts-quick` run in Phase 5 step 3 added two
dirs), and the census prints `CENSUS_SKIPPED_DESYNC` but not walked/total. Print all three and
cite the printout, not a number.

### N-4 Two assertions that cannot fail — MINOR

- `test_observation.py:142` — T2.1's cross-perspective "differs" check is conditional on the
  data. Assert the precondition (`assert len(set(summary_sets.values())) > 1`) so a
  degenerate fixture fails loudly.
- `test_actions_live_custom_effects.py:389` — T3.5's "slots at one node merge" is
  `assert all(len(slots) >= 1 …)`, a tautology on a dict of non-empty sets. The routing
  assertion two lines above is real; either assert `any(len(slots) > 1 …)` or delete the line
  and the docstring claim.

---

## 4. What to do, in order

1. **Ledger.** Add N-1 to `findings.md` (proposed class VALIDATION-PROCESS, MAJOR). Add the
   two new failures to the tolerated set *with the finding ID*, or fix them (3 below). Change
   Fix Plan 02's status line to "implemented; Phase 5 steps 2 and 4 open".
2. **Decide the corpus.** (a) recompose pre-`recruitable` runs as recruitable in
   `replay_loader.py` and add a documented escape for the setup-SHA gate, then rebuild
   `sims_vs_wins_v2` at v3 and re-bake the coverage table with all 141 dirs walking; or
   (b) run a fresh 120-game `sims_vs_wins` under the current rule and rebuild from that.
   (a) is an hour and restores the plan's premise; (b) is a day of compute and gives a corpus
   that matches the rule the network will play under. Both are defensible. Not deciding is
   not: 1,653 samples is not a dataset.
3. **F-013 G1.** Re-capture the reference vectors under the new rule (its own harness,
   `docs/validation/harness/f013b_gen_vectors.py`) or pin the old rule for that corpus.
   Record which.
4. **Small fixes.** Census prints walked/total/skipped; T2.1 asserts its precondition; T3.5's
   tautology goes; docs cite the printout.

---

## 5. Risks carried forward

- **The census is now mostly a routing unit-test with a live-engine veneer.** Seven of eight
  `custom_effect` branches are covered only by hand-driven states. The live tests are good
  tests, but they exercise one state each; the census exercised thousands. Until step 2 above
  lands, treat "0 semantic collisions" as a statement about 95 games and one effect kind.
- **Two rule regimes in one artifact tree.** 46 stored games were played under "insane_outcast
  recruitable"; everything after `23196b7` will not be. Whatever step 2 decides, the run
  manifest should record the rule set (or the setup SHA it was played under) so the builder
  can refuse to mix them on purpose rather than by accident.
- **Every "done when" that says `just test-all` now needs a written baseline of 5 / 11**, or
  the next reviewer inherits the same unrecorded delta.

---

## 7. Follow-up (2026-09-11, same day)

The owner took option (b) from § 4 step 2 and went further: `artifacts/ismcts/` was wiped
(every stored game had been played under the old rule), `datasets/sims_vs_wins_v2` deleted,
and a fresh 32-game corpus played at a uniform 200 sims. Outcome, all measured:

| item | before (this review) | after |
|---|---|---|
| census corpus | 141 dirs, 95 walked, 46 skipped | 34 dirs, 34 walked, 0 skipped (`CENSUS_CORPUS` now printed — N-3) |
| `custom_effect` branches in `_UNCOVERED_BY_CENSUS` | 7 of 8 | 5 of 8 — the three `insane_outcast` kinds are live again (70 / 47 / 14 states); `steal_white_trophy_to_board` dropped to 0 and got its live test |
| training-size v3 dataset | none (`quick`, 2 games) | `datasets/teacher_v3_32`: 32 games, 26,306 samples, leak 0/4611, argmax 0.844 |
| `tests/` | 5 failed | 3 failed (F-015 only; the two artifact-bound tests skip) |
| `openspiel_pyrants/tests/` | 11 failed | 11 failed — F-013's G1 gate is the one that remains **open** |
| ledger | N-1 unrecorded | F-034 (MITIGATED, G1 re-capture open) |

N-4's two weak assertions are still as described; they are cosmetic and were left for the
next pass over `tests/nn/`. Numbers and commands: `nn-training-data.md` § v3 teacher run.
