# ADR-0007: One visibility module answers "what does player p know?"

- **Status:** Active (step 1 done as a byte-identical refactor; step 2, the owner's visibility rule, is next)
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
  in zone order and shuffled together; shared resampled zones shuffle alone.
  With today's table this draws the RNG exactly as the old `state.c` code did.
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
- Your own deck is a count but is **not** resampled. This is the known gap:
  search effectively knows its own next draws.
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
