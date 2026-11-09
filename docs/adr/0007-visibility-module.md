# ADR-0007: One visibility module answers "what does player p know?"

- **Status:** Active (step 1 done as a byte-identical refactor; step 2, the owner's visibility rule, is in progress: A1 fixed the observer's own deck, A2 is next)
- **Date:** 2026-11-06
- **Decision owner:** maintainers
- **Supersedes:** -
- **Superseded by:** -

## Context

Several pieces of code each answered "what does player p know?" on their own:

- `CEngineAdapter.private_view_json` built the observation string in Python from
  the mirrored structs, with F-013 Part B's board-projection caches.
- `engine_infostate_hash` (then in player_view.c, now deleted) re-listed the
  same fields by hand for the IS-MCTS tree key.
- `engine_determinize` (`state.c`) hard-coded which zones it reshuffles.
- `openspiel_pyrants/nn/public.py` read hidden zones under its own contract.
- A test grepped `engine_determinize`'s source text to check it never touches
  the board.

The hash and the JSON could drift apart, and so could the JSON and
determinize. Nothing tied what determinize reshuffles to what the observer
sees. The owner has also settled the visibility rule, which differs from what
the engine does (see the handoff's "Candidate 5 decisions"):

- A player sees their own hand and discard, every opponent's discard pile, the
  market row, the devour pile and everything on the table.
- A player does not see opponents' hands, opponents' decks, their own deck or
  the market deck.

Changing that rule should touch one place.

## Decision

`engine_c/visibility.c` owns the answer. Of three sketched interfaces, the
owner chose a rule table plus one walk. The alternatives were a filled
`PlayerView` record, and a C JSON writer next to a hand-kept hash.

- **One rule table.** `RULES[zone][relation]` gives, for each card zone and for
  the observer's relation to its owner (self or opponent), what the observer
  sees (`VIS_CARDS` or `VIS_COUNT`) and whether determinization resamples the
  zone. Every zone's size is public. The table never resamples a zone it shows.
- **One walk.** A single traversal renders the view. Its shape is data: three
  field lists (the observer's record, the public block and the per-player
  summary) in `json.dumps(sort_keys=True)` key order. A card-list field appears
  only where the table shows those cards to the record's relation. The board
  is always public.
- **Two sinks.** `engine_player_view_json` renders the walk as JSON,
  byte-identical to the Python view it replaced (F-013 G1).
  `engine_infostate_hash` folds the same walk into the 128-bit tree key, so two
  states share a key exactly when they share a view. The hash uses raw
  interned ids. An id interned as the empty string shows as `null` in the JSON
  but stays distinct in the hash: a split, never a merge. Hash values are not
  persisted.
- **Determinization reads the table.** Each player's resampled zones are pooled
  in zone order, sorted by card id, and shuffled together; shared resampled
  zones shuffle alone. With step 1's table this drew the RNG exactly as the old
  `state.c` code did; step 2's A1 (below) adds the observer's own deck to the
  resampled set and sorts every pool.
- **Python asks C.** `private_view_json` is one call to
  `engine_player_view_json`, with the per-player string cache kept. The Python
  board projection and its F-013 Part B caches are deleted.
- **Outside the module, by decision.**
  - The deduced multisets the NN uses (opponent hand+deck bags, own-deck
    remainder, market remaining) stay in `nn/public.py`, and the NN tensor
    stays byte-identical.
  - The GUI's `build_c_game_view` is a seat view for a human, not an
    information set.
  - `_build_public_dict` remains the cheap public snapshot for the per-step
    crash log.

### Step 1: today's rule, byte-identical

The table first encodes the rule the engine already had:

- An opponent's hand, deck and discard are counts and resampled.
- Your own deck is a count but is **not** resampled. This was the known gap:
  search effectively knows its own next draws. Step 2's A1 closes it (see
  "Step 2, part A1" below).
- The devour pile and the market discard are counts whose cards never return
  to play.

Step 1 changes no observable behaviour:

- **Views:** all 918 F-013 G1 vectors, their determinized worlds and 381
  playout views are byte-identical.
- **Determinization:** 2,448 determinized states digest identically, covering
  every zone's order and the rerolled shuffle stream.
- **Search:** see Speed.

### Step 2: the owner's rule

Step 2 is an edit to the table:

- `VZ_DISCARD` for an opponent becomes `VIS_CARDS` with no resampling, so
  opponents' pools become hand+deck and each player summary gains a `discard`
  list.
- `VZ_DEVOUR` becomes `VIS_CARDS`, so the public block gains `devour_pile`.
- `VZ_DECK` for self gets `resample = 1`, so determinization shuffles the
  observer's own deck alone.

The walk already has these fields; nothing else needs to change. Step 2 changes
search and the view bytes, so it gets its own commit, a finding, a G1
re-freeze, the approved changes to
`test_observation_completeness.py:159` and `tests/nn/test_observation.py`'s
leak test, and its own speed run.

#### Step 2, part A1: no player's search knows its own deck order

Done 2026-11-09 (F-041 part (a)). The table's `VZ_DECK`, self, is now
`{VIS_COUNT, 1}`: the observer's own deck is resampled like any other hidden
deck. `engine_determinize` additionally sorts each resampled pool by card id
before the shuffle, so a sampled world depends only on the observer's
knowledge and the seed. The sort draws nothing from the RNG, so the stream
length for a given seed is unchanged.

Why the sort belongs with this change: once the observer's deck is resampled,
the proof test must show that two states differing only in that deck's order
produce the same decision. Without the sort they would still sample different
worlds for one seed, and the test would be statistical rather than exact. It
also hardens the opponents' pools against the same class of leak.

This part changes no view bytes, so no G1 re-freeze and no test flips were
needed. Views, the tree key and the NN observation were already clean: none of
them exposes deck order. Replays replay recorded moves and stayed 2,862/2,862
(baseline records 2,846; the local artifact set has since grown). `VZ_DISCARD`
(opponent) and `VZ_DEVOUR` remain step 2's open part (A2, F-041 part (b)).

Tests added:
- `engine_c/tests/test_visibility.c::test_determinize_shuffles_the_observers_own_deck`
  — across 24 seeds the deck order changes (23 did), while the cards, the count
  and the view do not.
- `engine_c/tests/test_visibility.c::test_determinized_world_depends_only_on_observer_knowledge`
  — two states the observer cannot tell apart (different own-deck order, and a
  different split of an opponent's hidden cards) produce byte-identical
  `engine_serialize_state` output for 12 seeds.
- `openspiel_pyrants/tests/test_no_own_deck_leak.py` — the end-to-end proof:
  the production bot's chosen action and whole policy are identical under two
  own-deck orders (three seeds). It failed on the step-1 engine on every seed.

Speed (script `scripts/bench_determinize.py`, committed; 118 playout states,
6,000 timed calls, 4 players, three runs per build):

- Parent `aa04bb0`: mean 3.96–4.23 µs, median 3.2–3.3 µs per call.
- This change: mean 4.68–5.56 µs, median 3.9–4.1 µs per call.
- About +0.7–1.3 µs per call, roughly +15–30 %, from sorting four small pools.
  At 200 sims per decision that is ~0.15–0.25 ms against a decision of hundreds
  of ms.

Quick check (8 four-player games, 50 sims, seed 42, `--uct-c 1.4`), parent
`aa04bb0` run `20261109T123044Z_59d40db79464` against this build run
`20261109T123258Z_f86a57cd3aaf` (both trees at `aa04bb0`; the candidate tree had
A1 uncommitted, so the runs differ by DLL sha256 `a7ca31cd…` vs `06518253…`):

- games/h 225.8 → 222.4 (run wall); ideal 298.2 → 271.5. Per-game wall ratio
  median 0.954, mean 0.912.
- Decisions differ on every game, as expected: determinization now samples a
  different world. `scripts/compare_paired_runs.py` shows field differences in
  `policy`/`visit_counts`/`q_values` from line 0.

A 32-game paired run was not requested; the quick check answers the games/h
question for this brief.

## Consequences

- **Deletion test.** Deleting the module would scatter the rule back into three
  C functions and the Python view, which is the state this ADR started from.
  The module earns its keep. The deleted Python projection fails the deletion
  test: its complexity vanished rather than moved.
- **Tests.** `engine_c/tests/test_visibility.c` checks the module at its
  interface:
  - the table never resamples a shown zone;
  - hidden cards reach only their owner;
  - the view is JSON with sorted keys and reports its length;
  - determinization keeps the observer's whole view byte-identical (1,440
    worlds);
  - tree-key classes match view classes (720 pairs).
  The last two replace T10, the source-text grep. With the owner's approval,
  T4, T11 and T12 in `test_board_projection.py` were deleted because they
  tested only the removed Python cache. Seven other tests now reach the view
  through the C path with unchanged assertions. The F-013 census harness is
  retired.
- **Gates.** Building this module exposed F-040: `just build-c` reported
  success on a failing C test and left a stale DLL. That is fixed.
- **Still outside, on purpose:** `engine_build_view` (`CGameView`, read by the
  GUI and by `nn/observation.py` for scalars), `build_c_game_view`,
  `_build_public_dict` and `nn/public.py`.

## Speed

The owner chose a quick check over the 45-minute paired 32-game run, and
direct micro-benchmarks of the two functions on the hot path.

The quick check ran 8 four-player games at 50 sims (seed 42, `--uct-c 1.4`)
on the pre-candidate engine `ff42ad6` (run `20261106T223242Z_2a13dd651080`)
and on `f9bec9b` (run `20261106T223244Z_c81a938a83de`).
- `decisions.jsonl` and `final_decks.json` are identical on 8 of 8 games,
  9,368 decisions in total, so step 1 does not change search.
- The only field that differs is `replay_context` in `replay.json`, which
  records absolute data paths; the baseline ran from a separate worktree.

Micro-benchmarks on 118 playout states:

- **Tree-key hash:** 1.45 µs per call, against 1.05 µs for the hand-written
  hash. About 2,500 key calls happen per 200-sim decision, so this is about
  1 ms of an average ~466 ms decision. Dispatching the sinks through inlined
  branches and folding card lists and the board in local variables brought the
  first version's 3.3 µs down to that.
- **Cold view:** about 57 µs, against 107 µs for the Python projection.
