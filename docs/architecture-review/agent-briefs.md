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
| 4 | F1..Fn | mixed | F0, C2 | Build the game handle, per F0's chunk list |
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
- Reserved finding numbers: F-041 (A1, A2). F-042 was reserved for B1, which
  did not need it; it is free. Any other new finding
  takes the next free number; name it in your report.
- Reserved ADR numbers: 0008 (A2), 0009 (D0), 0010 (E0), 0011 (F0), 0012 (G0).
  Any other ADR uses 0013 upward; name it in your report.

**Gates.** Run what the handoff's "Gates for every step" lists, read every pass
count, and add `just verify-replays` after any engine change. Baseline after
brief A1 (`0b9ee96`):

| Gate | Expected |
|---|---|
| `just build-c`, `just test-c` | 10 test executables pass |
| `just test-c-python` | 747 passed, 2 failed (Zuggtmoy, Air Elemental) |
| `just test-all`, `tests/` | 1111 passed, 2 failed, 11 skipped in the main checkout. A new worktree has no `artifacts/`, so 8 more tests skip there: 1103 passed, 2 failed, 19 skipped |
| `just test-all`, `openspiel_pyrants/tests/` | 110 passed, 10 failed (the postponed F-003 Part B tests) |
| `just verify-replays` | all pass (2862/2862 on 2026-11-09; the count grows as runs are added) |
| `just test-c-asan` | clean |
| `just docs-check` | 9 errors, all pre-existing |
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
4. *`engine_git_dirty`.* Every run from the main checkout records
   `engine_git_dirty: true`, because `engine_c/graphify-out/` is untracked. Ask
   the user whether to add it to `.gitignore`; it is the user's graphify output.
5. *Gates* after each commit. For item 1, also run the quick check:
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

## Lane D: finish candidate 4 (and candidate 1's 14th op)

### D0 (design): the rest of the catalog-as-card-spec work

**Owed** (handoff, "Deferred and open"; ADR-0004; ADR-0005):
- the split of `custom_effect`'s 13 effect kinds. That split also gives
  candidate 1 its 14th op.
- the op-selection variants `play`, `promote`, `devour` and `return_unit`.

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
