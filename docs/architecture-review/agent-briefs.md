# Agent briefs: the rest of the architecture plan

The remaining work of `docs/architecture-review/handoff-2026-11-04.md`, cut into
briefs that separate agents can run one at a time. Written 2026-11-09 on top of
`20c5d0c`.

Each agent gets a short message (at the end of its brief) and reads this file.
It does one brief, then reports to the user. The user brings the report back to
the coordinating session, which merges branches, updates the handoff's Progress
and writes the next briefs.

## Order

Briefs in the **engine lane** change `engine_c/` and run one at a time, on
`develop`. **Side** briefs may run alongside, each in its own worktree. A brief
marked *design* writes no code: it asks the user to choose an interface and
returns the chunk list that becomes the next briefs.

| Wave | Brief | Lane | Depends on | One line |
|---|---|---|---|---|
| 1 | **A1** | engine | - | No player's search may know the order of its own deck. **Top priority.** |
| 1 | B1 | side | - | Check the 2026-11-07 audit's claims; fix the untrue docs and `make clean` |
| 1 | C1 | side | - | Add the first engine purity guard (F-039) |
| 1 | D0 | design | - | Design the rest of candidate 4: `custom_effect`'s effect kinds and the op-selection variants |
| 1 | F0 | design | - | Design candidate 8's game handle |
| 2 | **A2** | engine | A1 | Opponents' discard piles and the devour pile become visible |
| 2 | B2 | engine | B1 | Delete the unreachable per-op branches in `generic_runtime.c` |
| 2 | B3 | side | - | Small cleanups: unused move constructors, duplicate helper, scratch files |
| 2 | E0 | design | - | Design candidate 7's scenario-building fixtures for card tests |
| 3 | A3 | side | A2 | Regenerate the teacher corpus under the new rule (needs the user's go) |
| 3 | C2 | engine | - | One legal-move capacity, and truncation you can see (F-038) |
| 3 | D1..Dn | engine | D0, B2 | Migrate effect kinds, per D0's chunk list |
| 4 | F1 | side | F0 | The game handle, its interface tests and the import guard (**done**) |
| 4 | C4 | engine | - (after C1 if C1 refactors `loader.c`) | The loader fails on input it cannot read or parse (F-043) |
| 4 | F6 | engine | F1 | The decision record as one JSON document from C |
| 4 | F2 | side | F1 | `PyrantsCState` delegates to the handle (F-037, F-042) |
| 4 | F3 | side | F2 | `CSession` delegates to the handle |
| 4 | F5 | side | F3 | Callers stop reaching into `state._adapter`; `c_adapter.py` goes |
| 4 | F4 | side | F5 | One replay and one seed mixer; `run_artifacts/`; the NN stops importing `interface` |
| 4 | E1..En | side | E0 | Move card tests onto the fixtures, per E0's chunk list |
| 5 | G0, G1..Gn | design, then mixed | F done | Candidate 9: pull the self-play step out of `scripts/run_ismcts.py` |
| 5 | E-final | side | F done | Candidate 7 stage 3: the remaining private reach-ins move to handle queries |
| any | C3 | timing | - | Optional: record candidate 3's speed (about 1.5 hours of exclusive machine time) |

A timing run needs the machine to itself. Don't run one while another agent runs
tests, builds or commits (the repowise post-commit hook is CPU-heavy).

## Rules for every agent

**Scope.** Do your brief only. The handoff's "Start here" and "Next" are for the
coordinator; ignore them.

**Read first**, in `docs/architecture-review/handoff-2026-11-04.md`: the
sections "Vocabulary", "Constraints you must not re-litigate", "Gates for every
step" and "Per-candidate loop". Then `GLOSSARY.md` and whatever your brief lists.

**Ask the user before you:**
- design or change an interface (sketch 2-3 options, compare depth, leverage
  and locality, let the user choose);
- change what any test asserts, except the changes your brief lists as approved;
- delete a file you didn't create;
- start a timing run longer than the quick check;
- do anything outside your brief.

**Where to work.**
- Engine-lane briefs commit on `develop` in `C:\Users\mkkom\pyrants`.
- Side and design briefs work in their own git worktree on branch
  `brief/<ID>`, made from `develop`'s tip. If your tool makes the worktree for
  you, give its path and branch in your report.
- Never push. Never merge into `develop` from a worktree; the coordinator merges.

**Commits.**
- Commit freely, never push. Format `[area] description`, using areas already
  in `git log` (`engine-c`, `docs`, `tests`, `build`, ...).
- Never mix engine, UI and data-format changes in one commit.
- Every commit passes the gates.

**Records.**
- Update the ADRs, findings, `GLOSSARY.md` and docs your brief names.
- Don't edit the handoff's Progress or Next; the coordinator does.
- Finding numbers: F-041 belongs to A1 and A2, and F-042 to F0. Any new
  finding takes the next free number, from F-043; name it in your report.
- Reserved ADR numbers: 0008 (A2), 0009 (D0), 0010 (E0), 0011 (F0), 0012 (G0).
  Any other ADR uses 0013 upward; name it in your report.

**Gates.** Run what the handoff's "Gates for every step" lists, read every pass
count, and add `just verify-replays` after any engine change. Baseline after
brief F1 (`f198321`, rechecked by the coordinator in the main checkout):

| Gate | Expected |
|---|---|
| `just build-c`, `just test-c` | 11 test executables pass |
| `just test-c-python` | 796 passed, 2 failed (Zuggtmoy, Air Elemental) |
| `just test-all`, `tests/` | 1160 passed, 2 failed, 11 skipped in the main checkout. A new worktree has no `artifacts/`, so 8 more tests skip there: 1152 passed, 2 failed, 19 skipped |
| `just test-all`, `openspiel_pyrants/tests/` | 110 passed, 10 failed (the postponed F-003 Part B tests) |
| `just verify-replays` | all pass (2886/2886 on 2026-11-11; the count grows as runs are added) |
| `just test-c-asan` | clean |
| `just docs-check` | 9 errors, all pre-existing, in the main checkout. A new worktree has no `artifacts/`, so it reports 24; compare against the same worktree's base |
| `ruff check .` | 634 errors overall; no new error in a file you changed |

Any other failure is new: stop and report it.

**Speed.**
- The **quick check** compares the parent commit with yours:
  1. Build the parent commit in a separate worktree (`git worktree add`, then
     `just build-c` there).
  2. In each tree run `.venv/Scripts/python.exe -m scripts.run_ismcts
     --num-sims 50 --num-games 8 --num-players 4 --workers 8 --seed 42
     --uct-c 1.4 --game python_pyrants_c --output-dir <dir>`.
  3. Compare the two runs with `scripts/compare_paired_runs.py --baseline <run>
     --candidate <run> --md <file>`.
- A change meant to keep behaviour must be content-identical: `decisions.jsonl`
  and `final_decks.json` equal on every game. Only `replay_context` may differ,
  because a worktree build records different absolute paths.
- A change meant to alter search reports games/h for both runs, plus the
  micro-benchmarks its brief names.
- Commit any benchmark script you use. `artifacts/` is gitignored, so also
  write run ids and numbers into the ADR or doc your brief names.
- Ask the user before any 32-game paired run (about 45 minutes per side).

**Environment quirks on this machine.**
- An `rtk` hook rewrites some shell commands and filters their output. If output
  looks cut or odd, rerun as `rtk proxy <command>`.
- The repowise post-commit hook takes 7-27 minutes. Run `git commit` in the
  background, and don't start a timing run until it finishes.
- To see pytest's pass counts, run it from Bash with `-o addopts=""`. PowerShell
  redirection garbles its output.
- `just` recipes take positional arguments only.

**Report back** in this shape, and nothing longer than it needs:

```
Brief: <ID> - done | stopped: <why>
Where: develop | branch brief/<ID> at <worktree path>
Commits: <hash> <subject>, one per line
Gates: build-c ...; test-c ...; test-c-python <n passed, n failed>; tests/ ...;
       openspiel_pyrants/tests/ ...; ruff (changed files) ...; asan ...;
       docs-check <n errors>; verify-replays <n/n>
Speed: <baseline commit, run id> -> <candidate commit, run id>: <numbers>
Tests changed: <file::test - what changed - who approved>
Records: <findings, ADRs, glossary terms touched>
Surprises: <anything that disagrees with this brief>
Questions: <for the user or coordinator>
```

## Lane A: candidate 5 step 2, the owner's visibility rule

The rule, settled by the user (handoff, "Candidate 5 decisions"; restated
2026-11-09):

- Each player sees their own hand, their own discard pile, every opponent's
  discard pile, the devour pile and the market row, plus everything already
  public on the table.
- Nobody sees any deck: not opponents' decks, not the market deck, and **not
  your own deck**. A deck's order is fixed in the real game until it runs out
  and is rebuilt, but it is always hidden from every player, its owner included.
- Every pile's size stays public.

Step 1 (`3d5fbe8`..`f9bec9b`, ADR-0007) built `engine_c/visibility.c` so that
one rule table drives the view, the tree key and determinization. Lane A edits
that table. Read ADR-0007 first.

### A1: no player's search knows its own deck order

**Why.** `engine_determinize` leaves the observer's own deck in its real order
(table row `VZ_DECK`, self: `{VIS_COUNT, 0}`). Every world IS-MCTS samples
therefore holds the real next draws, and the bot chooses with them. F-002
(`e9a2702`) already rerolls the shuffle stream, so the leak ends when the deck
runs out. Opponents' searches already resample this player's deck.

**Goal.** A player's search behaves exactly as if it could not see its own deck.
A test proves it end to end.

**Read first:** ADR-0007; `docs/determinization.md` ("Known gap");
`engine_c/visibility.h`; `engine_c/visibility.c` (table and
`engine_determinize`); `engine_c/tests/test_visibility.c`;
`openspiel_pyrants/ismcts_factory.py`; F-002 in `docs/validation/findings.md`.

**Steps.**
1. *Check every path from the real state into a decision.* For each one, give
   file:line and say whether it can reveal the acting player's own deck order:
   - `engine_determinize`;
   - the resampler wiring at `openspiel_pyrants/ismcts_factory.py:86`. Is every
     bot that plays or makes training data built through it? A bot that
     searches without the resampler sees everything.
   - the C rollout evaluator;
   - the NN observation (`my_deck_remainder` is a multiset; confirm nothing
     ordered);
   - `private_view_json`;
   - the GUI's `build_c_game_view` in `engine_c/bindings/view.py`. Report only:
     UI changes are not in this brief.
2. *Write the tests first and watch them fail.*
   - **The proof test (Python, new file).** Take a state where the acting
     player has at least two different cards in their deck and can draw this
     turn. Make a copy that differs only in that player's deck order, and
     assert the two orders differ. Run the production IS-MCTS bot from
     `ismcts_factory` on both with the same seeds and a small sim count.
     Assert that the chosen action and the policy are identical. It must fail
     on today's engine; if it passes, pick a state where it fails and say how
     you chose it.
   - **C (`test_visibility.c`).** Determinizing for player p shuffles p's own
     deck: across seeds the order changes, but the cards, the count and p's
     view do not.
   - **C (`test_visibility.c`).** A world depends only on what p knows. Take
     two states that p cannot tell apart: one differs in p's deck order and in
     how an opponent's hidden cards are split. Determinize both for p with the
     same seed. The results must be byte-identical; compare
     `engine_serialize_state` output.
3. *Implement.*
   - Set `VZ_DECK`, self, to `{VIS_COUNT, 1}`.
   - In `engine_determinize`, sort each resampled pool by card id before
     shuffling it. The world then depends only on p's information and the
     seed. This is what makes the proof test deterministic rather than
     statistical. Sorting draws nothing from the RNG.
   - Update the `engine_determinize` contract in `visibility.h` to say so.
4. *Tests that pin exact sampled worlds will break by design*, for example
   fingerprints in `openspiel_pyrants/tests/test_ismcts_reproducibility.py` or
   `test_determinize_reshuffle_independence.py`. Don't change them silently. List
   each one, with the assertion and why it changed, and ask the user before
   updating it.
5. *Gates*, all of them, including `just test-c-asan` and `just verify-replays`.
   Replays replay recorded moves, so they must stay 2846/2846. F-013 G1 must
   stay green, because no view changes. A G1 failure means something is wrong.
6. *Speed.*
   - Micro-benchmark `engine_determinize` per call, before and after, on
     playout states. Commit the benchmark script (ADR-0007's numbers had none,
     per the audit).
   - Run the quick check for games/h on both builds. Decisions will differ;
     that is expected.
   - Ask the user whether a 32-game run is wanted.
7. *Records.*
   - **F-041**, "determinization samples worlds the owner's visibility rule
     forbids". Part (a), own deck kept in order: FIXED here. Part (b),
     opponents' discard pooled with hand and deck, and the devour pile shown
     only as a count: OPEN for A2.
   - `docs/determinization.md`: replace "Known gap".
   - ADR-0007: mark step 2 as in progress, with A1's speed numbers.
   - `GLOSSARY.md`: "resampled zone", if the wording needs it.
8. *Commits.* `[engine-c]` with the table, the sorting and the tests; then
   `[docs]`.

**Done when.**
- The proof test passes and failed before the fix.
- All gates are at baseline, apart from changes the user approved in step 4.
- F-041 is logged.

**Message to paste:**

```
You are one of several agents working through the pyrants architecture plan (repo C:\Users\mkkom\pyrants, branch develop). Your task is brief A1 in docs/architecture-review/agent-briefs.md. Read that file's "Rules for every agent" section and brief A1 before anything else; they tell you what else to read. Do brief A1 only. Stop and ask me wherever the rules or the brief say to. End with the report in the format the rules give.

A1 in one line: make sure no player's search ever knows the order of its own deck, and prove it with a test that the bot's move doesn't depend on that order.
```

### A2: opponents' discard piles and the devour pile become visible

**Depends on** A1 being in `develop`.

**Goal.** The table matches the owner's rule:
- `VZ_DISCARD`, opponent, becomes `{VIS_CARDS, 0}`;
- `VZ_DEVOUR` becomes `{VIS_CARDS, 0}` in both columns.

Opponents' resampled pools become hand + deck. Each player summary in the view
gains a `discard` list, and the public block gains `devour_pile`.

**Read first:** ADR-0007 "Step 2"; F-007 and F-011 in
`docs/validation/findings.md`; F-041 (from A1); `ff42ad6` (how G1 was last
re-frozen); `openspiel_pyrants/tests/test_board_projection.py` (the G1 test);
`openspiel_pyrants/nn/public.py`.

**Approved by the user on 2026-11-06, no need to ask again:**
- Flip `openspiel_pyrants/tests/test_observation_completeness.py:159`
  (`test_opponent_discard_pile_still_not_leaked`) to the new rule.
- Flip the T3.9 leak test in `tests/nn/test_observation.py` (from line 157) to
  the new rule.
- Re-freeze the F-013 G1 vectors
  (`docs/validation/baseline/f013b_view_vectors.jsonl`) under the new rule.
- Log the finding, and write an ADR that supersedes F-007's outcome and F-011's
  "own-only discard" gate (G3).

Any other assertion change needs the user.

**Steps.**
1. *Tests first.*
   - In C: an opponent's discard cards appear in p's view, and the devour pile
     appears in every view.
   - Make sure the fixtures behind "determinize keeps observer view" and
     "tree-key classes match view classes" have non-empty opponent discards and
     a non-empty devour pile, so those tests now cover the new fields.
2. *Implement* the two rows. ADR-0007 says the walk already has the fields; if
   it doesn't, stop and report.
3. *Re-freeze G1.* The census harness that made the vectors is retired. Find how
   `ff42ad6` produced them, and write and commit a small regenerator that
   rebuilds the expected bytes from the C view for the same states. Check the
   new vectors by hand on a few states: the added fields hold the right cards.
4. *Make the approved test flips.*
5. *The NN tensor stays byte-identical* (user decision). Only update the
   rationale in `nn/public.py`'s docstring, which cites determinize pooling
   discards. Report whether the NN now ignores information the rule makes
   visible. That is a question for the user, not a change.
6. *Gates*, all of them. A G1 failure after the re-freeze means a bug.
7. *Speed.* Views get longer. Micro-benchmark `engine_player_view_json` and
   `engine_infostate_hash` before and after, and run the quick check for
   games/h. Ask the user whether a 32-game run is wanted.
8. *Records.*
   - **ADR-0008**, "The owner's visibility rule", superseding F-007's outcome
     and F-011 G3. Update those findings' status lines to point at it.
   - F-041 part (b): FIXED; close F-041.
   - ADR-0007: step 2 done.
   - `docs/determinization.md` and `docs/openspiel-architecture.md`, where they
     describe what is hidden.
   - `GLOSSARY.md`.
9. *Commits.* One `[engine-c]` commit with the table, the tests, the approved
   flips and the re-frozen vectors, so the tree is green at every commit. Then
   `[docs]`.

**Don't** regenerate training data; that is A3.

**Message to paste:**

```
You are one of several agents working through the pyrants architecture plan (repo C:\Users\mkkom\pyrants, branch develop). Your task is brief A2 in docs/architecture-review/agent-briefs.md. Read that file's "Rules for every agent" section and brief A2 before anything else; they tell you what else to read. Do brief A2 only. Stop and ask me wherever the rules or the brief say to. End with the report in the format the rules give.

A2 in one line: make every opponent's discard pile and the devour pile visible to all players, as the visibility rule says, with the G1 re-freeze, the approved test flips, ADR-0008 and the finding.
```

### A3: regenerate the teacher corpus under the new rule

**Depends on** A2. **Needs the user's go:** at about 40 games per hour it runs
for hours and keeps the machine busy.

**Why.** `datasets/teacher_v3_32` predates the F-015 fix and the new visibility
rule, so its labels come from search that knew too much.

**Steps.**
1. *Ask the user:*
   - the corpus size and sims (last time: 32 four-player games at 200 sims);
   - the `--uct-c` value (the calibrated default is 5.0);
   - the new dataset's name;
   - whether to delete `datasets/teacher_v3_32` afterwards.
2. *Generate* with `just ismcts` (positional arguments). Then:
   - run `just verify-replays`;
   - build the dataset with `just build-nn-dataset` in strict mode with the
     leak check, as `ismcts-quick` does.
3. *Record* the run id, engine commit, flags, counts and the dataset report in
   `docs/nn-training-data-tdd-plan.md`, or wherever corpus status is kept
   today; say where.

**Don't** train.

**Message to paste:**

```
You are one of several agents working through the pyrants architecture plan (repo C:\Users\mkkom\pyrants, branch develop). Your task is brief A3 in docs/architecture-review/agent-briefs.md. Read that file's "Rules for every agent" section and brief A3 before anything else; they tell you what else to read. Do brief A3 only. Stop and ask me wherever the rules or the brief say to. End with the report in the format the rules give.

A3 in one line: regenerate the IS-MCTS teacher corpus and NN dataset on the engine that hides every deck, after asking me for size, name and whether to delete the old one.
```

## Lane B: the 2026-11-07 audit

`docs/architecture-review/audit-2026-11-07.md` was written by another tool and
is untracked. It is not in a fresh worktree; read it from
`C:\Users\mkkom\pyrants\docs\architecture-review\audit-2026-11-07.md`. Treat
every claim in it as a lead to check, not a fact.

### B1: check the audit, fix what is untrue

**Steps.**
1. *ADR-0004's op-descriptor-cache claim.*
   - ADR-0004's Speed section says runs `20261106T105757Z_b6be8d1087e6` and
     `20261106T112844Z_df41f11c7216` are identical on all 32 games. The audit
     found no artifact comparing those two directly.
   - Find both run directories under `artifacts/` and compare them with
     `scripts/compare_paired_runs.py`.
   - The audit may have mixed up pairs: ADR-0004's "only `replay_context`
     differs" sentence is about the op-migration pair. Check both pairs.
   - If identical: commit the comparison summary and cite it from ADR-0004.
   - If not: correct ADR-0004 to say what is true, log **F-042** ("the op
     descriptor cache may change search"), and stop for the user.
2. *`make clean`.* Make `engine_c/Makefile`'s `clean` recipe take its test
   binaries from `engine_c/tests.txt`. Extend `scripts/check_build_manifest.py`
   if that is the simplest guard.
3. *Speed evidence that survives.*
   - Write `docs/architecture-review/speed-records.md`: every speed claim in the
     ADRs, with baseline and candidate commits, run ids, the dirty flag, DLL
     hashes and numbers.
   - Check the audit's run table against the manifests; don't copy it blindly.
   - Point the ADRs' Speed sections at it.
4. *F-039's wording.* The purity test existed and was deleted in `956f603`, so
   this is a regression, not a gap. Correct the finding's text only.
5. *Verify only*, and report for B2 and B3:
   - Are `engine_c/generic_runtime.c` lines 1030-1153 and 1270-1275
     unreachable?
   - Do 12 `make_*_move` constructors in `engine_c/moves.c` survive with test
     callers only?
6. *Ask the user* whether to commit the audit file itself.
7. *Commits.* `[docs]`, and `[build]` for the Makefile.

**Message to paste:**

```
You are one of several agents working through the pyrants architecture plan (repo C:\Users\mkkom\pyrants, branch develop). Your task is brief B1 in docs/architecture-review/agent-briefs.md. Read that file's "Rules for every agent" section and brief B1 before anything else; they tell you what else to read. Do brief B1 only. Stop and ask me wherever the rules or the brief say to. End with the report in the format the rules give.

B1 in one line: check the claims in the untracked 2026-11-07 audit against the repo and the run artifacts, fix the docs and the Makefile where they are untrue, and make the speed evidence durable.
```

### B2: delete the unreachable per-op branches

**Depends on** B1, which is done. Its verdict, in the correction note at the
top of `docs/architecture-review/audit-2026-11-07.md`:
- `engine_c/generic_runtime.c` lines 1030-1153 are unreachable. They sit
  inside `if (action_requires_selection(...))`, and every op that needs a
  selection returns earlier through the op table (lines 800-1021).
- Lines 1267-1275 stay. 1267-1269 is `custom_effect`'s fall-through for an
  unrecognised `effect_kind`. 1270-1275 is the general fallback for any op that
  needs a selection but is in neither the op table nor `custom_effect`. No
  catalog card reaches it today, but it is not a copy of a migrated op.

Line numbers are as of `b4c4c24`; re-find them before you edit.

**Why.** ADR-0004 says the colon parser survives only for `custom_effect`, but
`engine_c/generic_runtime.c` still has a branch per migrated op after the op
table returns. Two implementations of each op's payload decoding mean the
op-table module is not yet the only path.

**Steps.**
1. *Prove unreachability.* Temporarily make each per-op branch in lines
   1030-1153 abort, then run:
   - `just test-c`, `just test-c-python` and `just test-all`;
   - a quick-check game run.

   Nothing may hit them. Revert the probe.
2. *Delete* lines 1030-1153, so the `if (op)` chain starts at the
   `custom_effect` branch. Leave both fallbacks (1267-1275) as they are.
3. *Gates*, all of them, including asan and verify-replays.
4. *Quick check: content-identical* against the parent commit.
5. *Records.* ADR-0004's sentence about the colon parser is now true; add the
   quick check's run ids and result to ADR-0004.
6. *Commits.* `[engine-c]`, then `[docs]`.

**Message to paste:**

```
You are one of several agents working through the pyrants architecture plan (repo C:\Users\mkkom\pyrants, branch develop). Your task is brief B2 in docs/architecture-review/agent-briefs.md. Read that file's "Rules for every agent" section and brief B2 before anything else; they tell you what else to read. Do brief B2 only. Stop and ask me wherever the rules or the brief say to. End with the report in the format the rules give.

B2 in one line: prove the old per-op branches in generic_runtime.c are unreachable, delete them, and show games are content-identical.
```

### B3: small cleanups

**Steps.** Each is its own commit.
1. *Unused move constructors.*
   - Delete the 12 `make_*_move` constructors from `engine_c/moves.c` and
     `moves.h`, and their exports, if any.
   - Their only callers are C tests: `engine_c/tests/test_describe.c`,
     `engine_c/test_dt_ched.c` and `engine_c/test_engine.c` (the coordinator
     checked; no Python code or export uses them). Change how those tests build
     a move, not what they assert.
2. *Duplicate helper.* `_humanize_action` is defined twice in
   `engine_c/bindings/label_enrich.py` (lines 194 and 201). The second
   definition wins at import, so delete the first; behaviour is unchanged.
3. *Scratch scenario files.*
   - `tests/c_engine/test_engine_c.py` writes scratch scenarios into tracked
     paths (`data/scenarios/test_card_generation/_ae_opt1_test.json`,
     `_we_focus_test.json`). Make it write to `tmp_path`.
   - Ask the user whether to delete the two tracked files.
   - `tests/c_engine/test_bindings_import_guard.py` (F1) writes its probe,
     `_tmp_import_guard_probe.py`, into `engine_c/bindings/` and deletes it in
     `finally`. An interrupted run leaves a file with forbidden imports in the
     package. `find_forbidden_imports` takes any path, so write the probe to
     `tmp_path`; the assertions stay as they are.
4. *`engine_git_dirty`.* Every run from the main checkout records
   `engine_git_dirty: true`, because `engine_c/graphify-out/` is untracked. Ask
   the user whether to add it to `.gitignore`; it is the user's graphify output.
5. *C2 leftovers* (the coordinator found these reviewing C2):
   - `engine_c/ops/op.h` declares `extern int g_enum_probe;` under a second
     copy of the probe comment. Nothing defines or uses it; the live flag is
     `g_op_enum_probe`, defined in `engine_c/selection.c`. Delete the
     declaration and its comment.
   - `tests/c_engine/test_move_capacity_binding.py::test_python_buffers_are_sized_from_the_engine_capacity`
     can't fail. Its fake library reports 1024, which is the real capacity,
     and `ce_api.move_capacity()` caches the first value it reads in
     `ce_api._MOVE_CAPACITY`. A hard-coded `CMove * 1024` would pass. Make the
     fake report another capacity (for example 7), monkeypatch
     `ce_api._MOVE_CAPACITY` to `None`, and assert that both buffers follow the
     fake. Watch it fail against a temporary hard-coded 1024. **Approved:**
     this changes what the test asserts so that it tests what its docstring
     says. C2 wrote it, and no behaviour assertion changes.
   - The `engine_move_capacity()` comment in `engine_c/engine.h` and the
     `move_capacity()` docstring in `engine_c/bindings/ce_api.py` say
     `NUM_DISTINCT_ACTIONS` "derives from" the export. It doesn't: `game_c.py`
     declares it and checks it against the export at import. Fix the wording.
6. *Gates* after each commit. For item 1, also run the quick check:
   content-identical.

**Message to paste:**

```
You are one of several agents working through the pyrants architecture plan (repo C:\Users\mkkom\pyrants, branch develop). Your task is brief B3 in docs/architecture-review/agent-briefs.md. Read that file's "Rules for every agent" section and brief B3 before anything else; they tell you what else to read. Do brief B3 only. Stop and ask me wherever the rules or the brief say to. End with the report in the format the rules give.

B3 in one line: delete the unused move constructors and the duplicate _humanize_action, stop tests writing scratch files into tracked paths, and ask me about ignoring engine_c/graphify-out/.
```

## Lane C: open findings

### C1: add an engine purity guard (F-039)

**Why.** AGENTS.md and ADR-0001 say engine library sources do no I/O, but
nothing checks it. B1 found that the purity test deleted in `956f603` only ever
scanned the legacy Python `engine/*.py`, so `engine_c/` has never had a guard.
`engine_c/loader.c` calls `fopen`.

**Steps.**
1. *Ask the user:* allowlist `loader.c`, or refactor it so the caller passes the
   bytes in? A refactor makes this an engine-lane brief.
2. *Write the guard.* A pytest that reads `engine_c/sources.txt` and fails on
   real I/O and hidden nondeterminism in library sources:
   - `fopen`, `fread`, `fwrite`, `fprintf`, `printf`, `puts`, `getenv`,
     `time(`, `rand(`, `system(`;
   - `snprintf` is fine;
   - except vendored `cJSON.c` and whatever the user allowlists.

   Watch it fail on a temporary violation.
3. *Records.*
   - Point AGENTS.md's "Engine purity" bullet and ADR-0001's Compliance
     section at the new test.
   - Set F-039 to FIXED. B1 already corrected its text: a gap that was never
     filled, not a regression.

**Message to paste:**

```
You are one of several agents working through the pyrants architecture plan (repo C:\Users\mkkom\pyrants, branch develop). Your task is brief C1 in docs/architecture-review/agent-briefs.md. Read that file's "Rules for every agent" section and brief C1 before anything else; they tell you what else to read. Do brief C1 only. Stop and ask me wherever the rules or the brief say to. End with the report in the format the rules give.

C1 in one line: add the first automated check that engine_c library sources do no I/O (F-039), after asking me how to treat loader.c's fopen.
```

### C2: one legal-move capacity, visible truncation (F-038)

**Why.**
- The capacity 1024 is hard-coded in `engine_c/bindings/ce_api.py`, for both
  the legal and display queries.
- It is hard-coded again as `NUM_DISTINCT_ACTIONS` in
  `openspiel_pyrants/game_c.py:14`.
- C stops at the cap without saying so.

**Steps.**
1. *Ask the user* to choose between at least these:
   - **(a)** C exports the capacity; the bindings read it and assert it equals
     `NUM_DISTINCT_ACTIONS` at import.
   - **(b)** The move queries return how many moves exist, as
     `engine_player_view_json` does, and Python raises on overflow.
   - **(c)** Both.

   `NUM_DISTINCT_ACTIONS` is part of the NN action space, a frozen wire format:
   keep 1024.
2. *Tests first*, at the chosen interface. Include one that makes truncation
   visible.
3. *Implement*, run the gates, and run the quick check: content-identical.
4. *Records.* F-038 to FIXED; ADR-0003 if the query contract changes.

**Message to paste:**

```
You are one of several agents working through the pyrants architecture plan (repo C:\Users\mkkom\pyrants, branch develop). Your task is brief C2 in docs/architecture-review/agent-briefs.md. Read that file's "Rules for every agent" section and brief C2 before anything else; they tell you what else to read. Do brief C2 only. Stop and ask me wherever the rules or the brief say to. End with the report in the format the rules give.

C2 in one line: give the legal-move capacity one source and make truncation visible (F-038), after I choose the interface.
```

### C3 (optional): candidate 3's speed record

Candidate 3 (`d815205`, `a985208`) has no speed record (handoff, "Deferred and
open").

**Steps.**
1. *Ask the user* whether it is worth about 1.5 hours of exclusive machine time.
2. *If yes:* a same-session 32-game paired run, `0a7a894` → `a985208`, using
   ADR-0004's method.
3. *Record it* in ADR-0003 and `docs/architecture-review/speed-records.md`.

Games are expected to differ, because candidate 3 changed which moves search
sees.

**Message to paste:**

```
You are one of several agents working through the pyrants architecture plan (repo C:\Users\mkkom\pyrants, branch develop). Your task is brief C3 in docs/architecture-review/agent-briefs.md. Read that file's "Rules for every agent" section and brief C3 before anything else; they tell you what else to read. Do brief C3 only. Stop and ask me wherever the rules or the brief say to. End with the report in the format the rules give.

C3 in one line: if I agree to the machine time, measure candidate 3's speed with a same-session paired run and record it.
```

### C4: the loader fails on input it cannot read or parse (F-043)

**Engine lane**, on `develop`, one at a time with F6 and D1..Dn. If C1 chose to
refactor `loader.c` so callers pass the bytes in, run C4 after C1 and fix the
new shape.

**Why.** F-043, as widened by the coordinator after F1:
- `engine_apply_setup_json` (`engine_c/loader.c:591-595`) returns 0 for setup
  JSON that cJSON cannot parse.
- `engine_load_definition_json` (`:572-582`) skips a board or setup file that
  `read_file` cannot read.
- `parse_board` and `parse_setup` return a zeroed struct when `cJSON_Parse`
  fails.

Each of these starts a game with a 0-card deck, or with no board and so no
legal moves, and raises nothing. F1's handle catches only the first, in Python
(`Definition.load` parses the text before C sees it).

**Steps.**
1. *Tests first.* Each of these must fail to load:
   - unparsable `setup_data_json`;
   - a missing board file, and one that does not parse;
   - a missing setup file, and one that does not parse.

   Test each in C where `engine_c/tests/` can reach it, and through the handle
   as `EngineSetupFailed` (new tests in `tests/c_engine/test_game_handle.py`).
   Watch them fail before the fix.
2. *Fix in C.* `engine_apply_setup_json` returns non-zero and leaves
   `def->setup` as it was. `engine_load_definition_json` returns NULL when the
   board or setup file is missing or does not parse. A file that parses must
   load exactly as it does today.
3. *Ask the user* before treating `{}` as an error. It parses but has no
   starter deck, and F-043 records it as a separate case.
4. *Remove `Definition.load`'s Python pre-parse* once C reports the failure,
   so the rule lives in one place.
   `test_from_files_rejects_unparsable_setup_data_json` must stay green
   unchanged.
5. *Search tests and scripts for a board or setup path that does not exist.*
   If a test relied on the silent path, ask the user before changing what it
   asserts.

**Gates.** All, plus asan and verify-replays. No quick check is needed: the
definition loads once per process, off the search path, and a valid file
loads as before. If you change a `parse_*` helper in a way that could alter
what a valid file produces, run the quick check (content-identical).

**Records.** F-043 FIXED; ADR-0011 (the handle no longer pre-parses);
`docs/validation/findings.md`.

**Message to paste:**

```
You are one of several agents working through the pyrants architecture plan (repo C:\Users\mkkom\pyrants, branch develop). Your task is brief C4 in docs/architecture-review/agent-briefs.md. Read that file's "Rules for every agent" section and brief C4 before anything else; they tell you what else to read. Do brief C4 only. Stop and ask me wherever the rules or the brief say to. End with the report in the format the rules give.

C4 in one line: make the C loader fail on setup JSON, board files and setup files it cannot read or parse (F-043), then drop the handle's Python pre-parse.
```

## Lane D: finish candidate 4 (and candidate 1's 14th op)

### D0 (design): the rest of the catalog-as-card-spec work

**Owed** (handoff, "Deferred and open"; ADR-0004; ADR-0005):
- the split of `custom_effect`'s 13 effect kinds. That split also gives
  candidate 1 its 14th op.
- the op-selection variants `play`, `promote`, `devour` and `return_unit`.

**Since C2**, every target enumerator has two modes. Public move queries count
every target. Under `legal_generic_target_selection_probe()`, the global
`g_op_enum_probe` is set, and an enumerator returns as soon as its buffer is
full (`engine_c/ops/op.h`, ADR-0003's amendment). A new op that ignores the
flag is still correct, so no test fails, but the engine's internal "any
target?" checks then walk its whole target space. C2 measured that cost at
about 10% games/h. Each design must say how a new op gets this right: keep the
flag and add a probe check to the op-completeness test, or make probing an
explicit argument of the enumerate function.

**Steps.**
1. *Inventory every effect kind and selection variant*: the cards that use it,
   how it is targeted, applied and described, the tests covering it, and its
   catalog spelling. Start from the `custom_effect` branch of
   `engine_c/generic_runtime.c` and from `engine_c/ops/`.
2. *Sketch 2-3 interfaces* and compare them on depth, leverage, locality and
   wire-format impact. Move payloads and NN action ids are frozen, and the
   per-card catalog files in `data/cards/` change more often than anything else
   in the repo. Some shapes to consider:
   - each effect kind becomes a leaf op;
   - `custom_effect` stays a dispatcher with a loader-validated effect-kind
     table;
   - the catalog decomposes effects into existing ops, which is a data-format
     change.

   Let the user choose.
3. *Write ADR-0009 as Proposed* with the choice. Return the chunk list in your
   report: about 2-4 effect kinds per chunk, leaf kinds first, each one commit
   that keeps all 118 card tests green and is content-identical in the quick
   check. The coordinator turns it into briefs D1..Dn.

No code.

**Message to paste:**

```
You are one of several agents working through the pyrants architecture plan (repo C:\Users\mkkom\pyrants, branch develop). Your task is brief D0 in docs/architecture-review/agent-briefs.md. Read that file's "Rules for every agent" section and brief D0 before anything else; they tell you what else to read. Do brief D0 only. Stop and ask me wherever the rules or the brief say to. End with the report in the format the rules give.

D0 in one line: inventory custom_effect's effect kinds and the op-selection variants, sketch 2-3 designs for me to choose from, write ADR-0009 and return a chunk list. No code.
```

## Lane E: candidate 7, stages 2 and 3

### E0 (design): scenario-building fixtures for card tests

**Evidence to re-verify:** 105 of 137 `tests/c_engine` files read `.contents`,
and 50 write state memory (handoff, "2.1").

**Steps.**
1. *Re-count* the reads and writes, and group them by what the tests actually
   set up and inspect.
2. *Sketch 2-3 fixture interfaces*, for example:
   - building scenarios through the schema-v2 loader;
   - a Python builder over C setters;
   - declarative fixtures.

   Prefer reads through queries. Let the user choose.
3. *Write ADR-0010 as Proposed*, and return migration batches of about 15-20
   test files each. Tests change how they reach the engine, never what they
   assert, and keep every "fixture still covers this case" check. Stage 3
   (E-final) waits for candidate 8's handle.

No code.

**Message to paste:**

```
You are one of several agents working through the pyrants architecture plan (repo C:\Users\mkkom\pyrants, branch develop). Your task is brief E0 in docs/architecture-review/agent-briefs.md. Read that file's "Rules for every agent" section and brief E0 before anything else; they tell you what else to read. Do brief E0 only. Stop and ask me wherever the rules or the brief say to. End with the report in the format the rules give.

E0 in one line: design how card tests build and inspect scenarios without reaching into engine memory, let me choose, write ADR-0010 and return migration batches. No code.
```

## Lane F: candidate 8, one game handle

### F0 (design): the game handle

**Done** 2026-11-11 (`b52de63`): ADR-0011, F-042. The chunk briefs F1-F6 follow
this one.

**Evidence to re-verify** (handoff, "2.2"):
- `CSession` returns `None` on failure; `CEngineAdapter` raises.
- Replay is implemented three times (`state_c`, `_nn_dataset`,
  `replay_player`).
- The seed mixer is copied.
- The NN pipeline imports the GUI package.
- Four calls bypass the seam.
- `pending_context.py` reads raw memory.
- F-037: `_init_attrs` drops `setup_data_json`.
- ADR-0006 deferred moving `pending_ability`/`pending_generic` storage out of
  `GameState` to here.
- Since C2 (F-038), both move queries return how many moves exist, and
  `ce_api` raises `MoveCapacityError` when that is more than the capacity
  (1024, also the NN action space). The handle's failure semantics must cover
  this error as well as `None`-versus-raise.

**Steps.**
1. *Re-verify* each item with file:line.
2. *Sketch 2-3 pyspiel-free handle interfaces.* Each must cover:
   - setup from a seed, apply, clone and determinize;
   - legal and display moves;
   - the decision record and views;
   - replay from a log.

   Ask the user to settle the failure semantics, whether the decision record
   reaches Python here, and whether the pending storage moves.
3. *Write ADR-0011 as Proposed*, and return a chunk list. A likely shape, to
   confirm or change:
   - F1: the handle and tests at its interface.
   - F2: `PyrantsCState` becomes an adapter.
   - F3: `CSession` becomes an adapter.
   - F4: one replay and one seed mixer; the NN stops importing `interface`.
   - F5: evaluators stop touching `state._adapter`.
   - F6: the decision record replaces `pending_context.py`'s reads.
   - F7: the pending storage moves out, if chosen; F-037 is fixed along the way.

   Candidate 8 is speed-gated: chunks that touch clone or determinize need a
   content-identical quick check.

No code.

**Message to paste:**

```
You are one of several agents working through the pyrants architecture plan (repo C:\Users\mkkom\pyrants, branch develop). Your task is brief F0 in docs/architecture-review/agent-briefs.md. Read that file's "Rules for every agent" section and brief F0 before anything else; they tell you what else to read. Do brief F0 only. Stop and ask me wherever the rules or the brief say to. End with the report in the format the rules give.

F0 in one line: re-verify candidate 8's evidence, sketch 2-3 designs for one pyspiel-free game handle for me to choose from, write ADR-0011 and return a chunk list. No code.
```

### Rules for every F chunk (F1-F6)

- **Read `docs/adr/0011-game-handle.md` in full first**, including its
  "Coordinator's amendments". It is the design; this brief only cuts it up.
- **The interface is settled** (owner, 2026-11-11). Ask the user before you
  change a name or signature that ADR-0011 gives, and record any change there.
- **Frozen**: move payloads, `decisions.jsonl`, NN action ids. No RNG may be
  drawn differently; `just verify-replays` stays green in every chunk that
  touches clone, determinize, apply or replay.
- **"Within noise"**: the quick check's games/h within 3% of the parent's, in
  the same session. If it is further off, run C2's alternating method before
  you report: 6 games and 6 workers, baseline and candidate alternating, three
  pairs (`speed-records.md`, section "ADR-0003 amendment, C2"). A regression
  beyond noise needs the user's sign-off.
- **Tests** may change how they reach the engine (imports, attribute paths)
  only where a chunk lists it as approved; what they assert changes only with
  the user's approval.
- **Where**: F6 is engine lane, on `develop`, one at a time with D1..Dn. The
  others are side chunks in worktree `brief/F<n>`. Each starts from `develop`'s
  tip after the coordinator has merged the chunk it depends on.

### F1: the game handle and its interface tests

**Done** 2026-11-12, merged fast-forward as `7665bb2`..`f198321`: `handle.py`
(`GameHandle`, `Definition`), `errors.py`, `import_guard.py` and 43 tests in
three new files; `handle.Move is CMoveWrapper`. Logged F-043, which brief C4
fixes. What later chunks inherit:
- The handle has no `__del__`. Its `CState` frees the C state when collected,
  so `destroy()`/`with` only make the free deterministic.
- `GameHandle.new(..., definition=)` lets one `Definition` start many games, so
  `game_c.py` (F2) and `session.py` (F3) can share one load instead of building
  a `CEngine` per game.
- `test_game_handle_parity.py` drives a handle and a `CEngineAdapter` side by
  side. It is F2's guard: keep it green, and keep it until F5 deletes
  `CEngineAdapter`.

**Depends on** F0. Side, worktree `brief/F1`.

**Build** (ADR-0011, "The interface" and "Failure semantics"):
- `engine_c/bindings/handle.py` with `GameHandle`: setup (`new`, and
  `from_files` with `setup_data_json`), apply, clone, determinize, legal and
  display moves, views, `infostate_key`, the phase/round/player/terminal/score
  queries, rollout, scenario load and save, and the context manager. Leave out
  `decision_record` (F6) and the replay operations (F4).
- The failure family in its own leaf module; `ce_api` imports
  `MoveCapacityError` from it (ADR-0011, "Failure semantics").
- The `Move` value. `legal_moves` is on the search's hot path, so don't create
  a second Python object per move: today's `CMoveWrapper` already has public
  `move_type`, `data` and `to_payload`. The ctypes struct
  `engine_bindings.Move` already uses the name `Move`; decide how to resolve
  that and record it in ADR-0011.
- Nothing delegates to the handle yet, and no caller changes.

**Tests first**, at the handle's interface:
- Every operation, and every failure: a rejected apply; a clone that fails
  (monkeypatch `engine_clone` to return NULL) raises `EngineCloneFailed`; a
  failed determinize; `MoveCapacityError` through a fake library, as
  `tests/c_engine/test_move_capacity_binding.py` does. Every class is a
  `RuntimeError`, and `ce_api.MoveCapacityError` is the same object.
- Clone independence: advancing a clone leaves the original's legal moves,
  view and infostate key unchanged.
- Lifetime: leaving the `with` block destroys the state; destroying twice is
  safe.
- **A parity test, which guards F2.** For several seeds, drive a handle and a
  `CEngineAdapter` through the same random move sequence. At every step compare
  the legal and display moves (as payloads), the phase, round and current
  player, every player's view and infostate key, the scores, and a rollout from
  the same seed.
- The import guard: an AST scan, function-level imports included, that no
  module under `engine_c/bindings/` imports `interface`, `openspiel_pyrants`,
  `pyspiel`, `scripts` or `run_artifacts`. Watch it fail on a temporary
  violation.

**Gates.** All, except asan and verify-replays (no C change). No speed run: no
caller moved.

**Records.** ADR-0011 (F1 done, and the `Move` naming decision).

**Overlap.** B3 also edits `ce_api.py` (the `move_capacity()` docstring) and
`test_move_capacity_binding.py`. If both are open, the coordinator merges B3
first.

**Message to paste:**

```
You are one of several agents working through the pyrants architecture plan (repo C:\Users\mkkom\pyrants, branch develop). Your task is brief F1 in docs/architecture-review/agent-briefs.md. Read that file's "Rules for every agent" section, its "Rules for every F chunk" and brief F1 before anything else; they tell you what else to read. Do brief F1 only. Stop and ask me wherever the rules or the brief say to. End with the report in the format the rules give.

F1 in one line: build the game handle from ADR-0011 with tests at its interface, a parity test against CEngineAdapter and the bindings import guard; nothing delegates to it yet.
```

### F6: the decision record as one JSON document from C

**Depends on** F1 merged. Engine lane, on `develop`, one at a time with
D1..Dn. Don't touch `engine_c/generic_runtime.c`; lane D is rewriting it.

**Build** (ADR-0011, "The decision record"):
- C: `engine_pending_decision_json(state, buf, cap)`. Copy the size-query
  contract of `engine_player_view_json` (`engine_c/visibility.h`) exactly,
  including what a too-small buffer gets. Cover every `PendingKind`. Export it
  and bind it in `engine_bindings.py`.
- `pending_context.py`: `read_pending_generic_context` and
  `read_pending_generic_context_full` become projections of the record, with
  **unchanged signatures**. Their callers (`view.py:224`,
  `run_ismcts.py:395,777`, `_nn_dataset.py:289`) stay as they are; F5 moves
  them.
- `view.py:236-271` reads the promotion head from the record.
- `GameHandle.decision_record()`.

**Tests first.**
- A C test of the size contract, and of 0 when nothing is pending.
- An oracle test. Copy today's raw-memory readers (`pending_context.py`'s two,
  and `view.py`'s promotion head) into the test as the oracle. Compare them
  with the new readers at every decision of seeded random games, plus scenarios
  from `data/scenarios/` for any pending kind that random play does not reach.
  Assert that every kind was seen. This is the NN-encoder half of ADR-0011's
  byte-identity test. The quick check covers the decision-log half, because
  `decisions.jsonl` carries `pending_context`.

**Gates.** All, plus asan and verify-replays; every
`tests/c_engine/test_pending_context*.py`; quick check content-identical.

**Records.** ADR-0011; ADR-0006 (the decision record now reaches Python);
`GLOSSARY.md`; `speed-records.md`.

**Message to paste:**

```
You are one of several agents working through the pyrants architecture plan (repo C:\Users\mkkom\pyrants, branch develop). Your task is brief F6 in docs/architecture-review/agent-briefs.md. Read that file's "Rules for every agent" section, its "Rules for every F chunk" and brief F6 before anything else; they tell you what else to read. Do brief F6 only. Stop and ask me wherever the rules or the brief say to. End with the report in the format the rules give.

F6 in one line: C renders the pending decision as one JSON document; pending_context.py and view.py's promotion head read it instead of raw memory, proven identical against an oracle of today's readers.
```

### F2: `PyrantsCState` delegates to the handle (F-037, F-042)

**Depends on** F1 merged (not F6). Side, worktree `brief/F2`.

**Build** (ADR-0011, chunk F2 and the coordinator's amendments):
- `PyrantsCState` holds a `GameHandle`, which `game_c.py` gives it. `clone()`
  goes through `handle.clone()`.
- `_adapter` stays as a private compatibility property that still answers
  every read F5 lists.
- Every other observable behaviour stays the same. That includes
  `__deepcopy__` rebuilding by replay (F4 owns replay) and `_engine`'s
  `_EngineShim` (G4 deletes it).
- **One intended change:** when `engine_clone` fails, `clone()` raises
  `EngineCloneFailed` instead of falling back to a replay. That happens only
  when an arena allocation fails. Record it in ADR-0011.
- **F-042:** `CEngineAdapter.__deepcopy__` raises `EngineCloneFailed` instead of
  returning `self`. The falsification test in `findings.md` goes red before your
  change and green after.
- **F-037:** `_init_attrs` passes `setup_data_json`. Test first: build a game
  with a non-empty `setup_data_json` once through `cls.__new__` plus
  `_init_attrs` and once through `__init__`; the two set up the same.

**Speed** (ADR-0011, condition 2).
- No extra ctypes crossing on clone, apply or `legal_moves`. Prove it with a
  test that wraps `_lib` in a call-counting proxy and checks the counts per
  operation against today's.
- Then the quick check: content-identical, and games/h within noise.

**Gates.** All, plus verify-replays and the quick check; asan only if you
change C.

**Records.** F-037 and F-042 FIXED; ADR-0011; `speed-records.md`.

**Message to paste:**

```
You are one of several agents working through the pyrants architecture plan (repo C:\Users\mkkom\pyrants, branch develop). Your task is brief F2 in docs/architecture-review/agent-briefs.md. Read that file's "Rules for every agent" section, its "Rules for every F chunk" and brief F2 before anything else; they tell you what else to read. Do brief F2 only. Stop and ask me wherever the rules or the brief say to. End with the report in the format the rules give.

F2 in one line: PyrantsCState delegates to the game handle with no extra ctypes crossing and no speed loss, keeping _adapter as a compatibility property; fix F-037 and F-042 on the way.
```

### F3: `CSession` delegates to the handle

**Depends on** F2 merged. Side, worktree `brief/F3`.

**Build.**
- `CSession` holds a `GameHandle`. Its public surface stays the same: `state`,
  `move_count`, `legal_moves`, `display_moves`, `submit_move`, `snapshot`,
  `save`/`load` and `from_files`. `state` still returns a `CState`, because the
  GUI reads it (`game_viewer.py:1179`, `:2109`; `replay_viewer.py:417`).
- `submit_move` returns `None` only for `EngineApplyRejected`; any other
  `EngineError` propagates.
- The three `CEngine` setup sites in `session.py` (`:60`, `:196`, `:229`) go
  through the handle's setup. `_session_protocol.SessionLike` does not change.

**Tests first.** The existing tests for a rejected move returning `None` stay.
Add one: a capacity error from a fake library propagates out of `submit_move`.

**Gates.** All, including the GUI tests and `tests/c_engine`; verify-replays
(`ReplayPlayer` runs on `CSession`); quick check content-identical.

**Records.** ADR-0011.

**Message to paste:**

```
You are one of several agents working through the pyrants architecture plan (repo C:\Users\mkkom\pyrants, branch develop). Your task is brief F3 in docs/architecture-review/agent-briefs.md. Read that file's "Rules for every agent" section, its "Rules for every F chunk" and brief F3 before anything else; they tell you what else to read. Do brief F3 only. Stop and ask me wherever the rules or the brief say to. End with the report in the format the rules give.

F3 in one line: CSession delegates to the game handle, keeping its public surface, and returns None only for a rejected apply.
```

### F5: callers stop reaching into `state._adapter`

**Depends on** F3 merged. Side, worktree `brief/F5`.

**Build.**
- Move every reader of `state._adapter`, and every module that names
  `CEngineAdapter`, onto the handle's public surface:
  - production: `c_rollout_evaluator.py:30`;
    `run_ismcts.py:395,428,567,777,781,798,800`; `_replay_payload.py:20-34`;
    `_state_snapshot.py`; `nn/actions.py`; `_nn_dataset.py`;
  - the bench scripts `bench_determinize.py` and `bench_view_hash.py`;
  - `docs/validation/harness/`. No gate runs these investigation scripts. Port
    the ones whose change is mechanical, list the rest in your report, and
    delete none.
- If F6 has landed, the `pending_context` callers read the handle's
  `decision_record()`. Otherwise they keep the pointer form.
- Callers and tests read `move_type`, not the `_move_type` shim.
- Then delete `_adapter`, and `engine_c/bindings/c_adapter.py` once nothing
  imports it. Deleting the file needs the user's approval: ask, unless this
  line says Approved.
- `_EngineShim` stays, fed from the handle; G4 deletes it.

**Approved test changes.** The 15 test files that read `._adapter`, the 12 that
name `CEngineAdapter`, and the ~50 that read `._move_type` change how they reach
the engine. What they assert does not change.

**Speed.** Quick check content-identical, games/h within noise; `just
ismcts-perf` before and after, because the rollout evaluator is on the hot
path.

**Gates.** All, plus verify-replays.

**Records.** ADR-0011; `speed-records.md`.

**Message to paste:**

```
You are one of several agents working through the pyrants architecture plan (repo C:\Users\mkkom\pyrants, branch develop). Your task is brief F5 in docs/architecture-review/agent-briefs.md. Read that file's "Rules for every agent" section, its "Rules for every F chunk" and brief F5 before anything else; they tell you what else to read. Do brief F5 only. Stop and ask me wherever the rules or the brief say to. End with the report in the format the rules give.

F5 in one line: move every reader of state._adapter and CEngineAdapter onto the game handle's public surface, then delete _adapter and c_adapter.py.
```

### F4: one replay, one seed mixer, `run_artifacts/`

**Depends on** F5 merged. Side, worktree `brief/F4`.

**Build** (ADR-0011, "Where the code lives, and the import rules"):
- The handle gains `from_log`, `advance`, `seek`, `engine_seed`,
  `find_matching_move` and `ReplayDesyncError`. Replay takes an in-memory log,
  never a path.
- The three replay loops become that one: `PyrantsCState.__deepcopy__`,
  `_nn_dataset.py:243-350` and `ReplayPlayer`.
- A new top-level package, `run_artifacts/`, holds `load_replay`,
  `discover_replays`, `ReplayBundle`/`ReplayMeta`, `is_complete_game`, and the
  manifest, summary and decision-log parsing. It must not import `interface`.
- `interface/replay_loader.py` and `interface/replay_player.py` leave
  `interface/`. **Approved** (the owner's answer to F0's question 6): only
  `replay_viewer.py` stays. Their callers move with them: `_nn_dataset.py`,
  `card_playstats/extract.py`, `card_playstats/discovery.py`,
  `verify_replays.py`, `replay_viewer.py` and the tests.
- The seed-mixer copy in `state_c.py` goes.
- The import guards: `engine_c/bindings/` must not import `run_artifacts`
  (already in F1's list), and `run_artifacts/` must not import `interface`.
  Watch both fail on a temporary violation.

**Tests.**
- `tests/test_replay_loader.py` and `tests/test_replay_player.py` change their
  imports only. **Approved.**
- `test_replay_loader.py::test_engine_seed_matches_openspiel` compares the two
  mixer copies, so with one copy left its assertion must change. That needs the
  user's approval: ask, unless this line says Approved.

**Proof.**
- Quick check content-identical.
- verify-replays, which is the main proof here.
- NN dataset parity: build a small dataset from 4 stored games with the parent
  and with your commit, and compare the tensors byte for byte. Commit the script
  you use.

**Gates.** All.

**Records.** ADR-0011 (all chunks done; the coordinator sets it Accepted);
`GLOSSARY.md` ("run artifact").

**Message to paste:**

```
You are one of several agents working through the pyrants architecture plan (repo C:\Users\mkkom\pyrants, branch develop). Your task is brief F4 in docs/architecture-review/agent-briefs.md. Read that file's "Rules for every agent" section, its "Rules for every F chunk" and brief F4 before anything else; they tell you what else to read. Do brief F4 only. Stop and ask me wherever the rules or the brief say to. End with the report in the format the rules give.

F4 in one line: one replay-from-log in the game handle, the run-artifact reader in a new run_artifacts/ package, and the NN pipeline stops importing interface.
```

## Lane G: candidate 9, the self-play step

### G0 (design), after lane F

**Evidence to re-verify** (handoff, "2.3"):
- `scripts/run_ismcts.py` is about 1,500 lines, and `run_one_game` has about 14
  responsibilities.
- 10 test files and 2 sweep scripts import its private helpers.
- `_EngineShim` has 11 uses.
- Bot setup is duplicated in `docs/validation/harness/common.py`.

**Steps.**
1. *Sketch the self-play module* (decide → record → apply) with a recorder
   seam:
   - production writes `decisions.jsonl`, the replay, snapshots and the crash
     log;
   - tests record in memory.

   Let the user choose.
2. *Write ADR-0012* and return a chunk list. Likely:
   - G1: extract the step, with an in-memory recorder and tests.
   - G2: production recorders, content-identical in the quick check.
   - G3: move the tests and sweep scripts off the private helpers, and dedupe
     bot setup.
   - G4: delete `_EngineShim`.

No code.

**Message to paste:**

```
You are one of several agents working through the pyrants architecture plan (repo C:\Users\mkkom\pyrants, branch develop). Your task is brief G0 in docs/architecture-review/agent-briefs.md. Read that file's "Rules for every agent" section and brief G0 before anything else; they tell you what else to read. Do brief G0 only. Stop and ask me wherever the rules or the brief say to. End with the report in the format the rules give.

G0 in one line: design a self-play module with a recorder seam to replace run_one_game in scripts/run_ismcts.py, let me choose, write ADR-0012 and return a chunk list. No code.
```
