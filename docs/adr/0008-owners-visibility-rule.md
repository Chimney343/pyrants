# ADR-0008: The owner's visibility rule

- **Status:** Active
- **Date:** 2026-11-09
- **Decision owner:** the project owner (rule settled 2026-11-06; restated 2026-11-09)
- **Supersedes:** F-007's outcome (discards treated as hidden) and F-011's "own-only discard" gate (G3)
- **Superseded by:** -

## Context

ADR-0007 built one visibility module: a rule table in `engine_c/visibility.c`
that drives the player view, the tree-key hash and determinization, so the three
can no longer disagree. Step 1 encoded the rule the engine already had, byte for
byte. Step 2 sets that table to the rule the owner settled:

- Each player sees their own hand, their own discard pile, **every opponent's
  discard pile**, the devour pile and the market row, plus everything already
  public on the table (board troops and spies, played cards, inner circles,
  trophy halls, the resource pool, VP and scores).
- Nobody sees any deck: not opponents' decks, not the market deck, and **not
  their own deck**. A deck's order is fixed in the real game until it runs out
  and is rebuilt, but it is always hidden from every player, its owner
  included. Determinization therefore resamples every deck.
- Every pile's size stays public.

Two older findings had resolved the discard question the other way:

- **F-007** found a rulebook silence on whether an opponent's discard pile is
  inspectable, scanned the cards for any effect that reads one, found none, and
  **refuted** the finding: it judged the engine's "discards are as hidden as an
  undrawn deck" choice to have no mechanical consequence. The owner has since
  decided the question on table-convention grounds (discard piles sit face up),
  not on whether a card currently reads them.
- **F-011** fixed the observation's board and own-discard gap and, in its fix
  plan, set gate **G3 "own-only discard"**: the observing player's own discard
  identities appear in their view; a *different* player's never do. That gate is
  exactly what this rule reverses.

Step 2's first half, **A1**, is already done under ADR-0007: `VZ_DECK`, self, is
`{VIS_COUNT, 1}`, so determinization resamples the observer's own deck and no
player's search knows its own deck order (F-041 part (a)).

## Decision

Edit two rows of the rule table in `engine_c/visibility.c`:

- `VZ_DISCARD`, opponent, becomes `{VIS_CARDS, 0}`: an opponent's discard cards
  are shown, so their resampled pool is **hand + deck** only (the discard is no
  longer pooled in).
- `VZ_DEVOUR` becomes `{VIS_CARDS, 0}` in both columns: the devour pile is shown
  as cards, and it is a shared zone whose cards never return to play, so it is
  never resampled.

The walk already enumerated these fields (the observer's `discard`, the public
block's `devour_pile`, each player summary's `discard`), so the table edit is the
whole code change: a `F_CARDS` field appears only where the rule shows those
cards to the record's relation. No view-shape, hash-shape or determinization
code changed.

## Consequences

- **View bytes change.** Every player summary gains a `discard` list and the
  public block gains `devour_pile`; `discard_size` and `devour_size` stay as the
  public counts. The F-013 G1 reference vectors were re-frozen under the new rule
  (all 918 changed; the only field-level additions are `public.devour_pile` and
  each summary's `discard`, verified across the whole corpus). G1 is green.
- **The tree key changes with the view.** `engine_infostate_hash` folds the same
  walk, so an opponent's discard identity and the devour pile now split every
  observer's key, exactly as the view distinguishes them. New C test:
  `test_devour_and_discard_identity_split_everyone`.
- **Determinization pools only hidden zones.** Per-player resampled zones are now
  hand + deck (the discard is shown); shared resampled zones are the market deck.
  The sort-then-shuffle from ADR-0007 step 2 A1 is unchanged, so a world still
  depends only on the observer's knowledge and the seed.
- **Search changes**, so the paired run is not content-identical (expected). The
  NN tensor stays **byte-identical** by user decision: it encodes opponents as
  deduced hand+deck+discard bags and never reads discard identities, so the rule
  makes information visible that the tensor still does not encode. See "Open
  question" below.
- **F-041 closes.** Part (b) — determinization pooled an opponent's discard with
  their hand and deck, and showed the devour pile only as a count — is fixed
  here. F-007's outcome and F-011's G3 now point at this ADR.
- **Deletion test.** No module is added or removed; this is a two-row table edit
  behind ADR-0007's interface, which is the point of the module.

## Open question (for the owner, not a change)

The rule makes opponents' discard identities and the devour pile visible, but the
NN observation (`openspiel_pyrants/nn/observation.py` via
`openspiel_pyrants/nn/public.py`) still folds an opponent's discard into their
deduced hand+deck+discard bag and does not expose the devour pile's identities.
The tensor is therefore no longer a complete encoding of what a player may know.
That was the user's explicit choice for this brief ("the NN tensor stays
byte-identical"); whether a later candidate should widen the observation is the
owner's call.

## Tests

- **C (`engine_c/tests/test_visibility.c`).**
  - `test_opponent_discard_and_devour_are_visible` — a new test: an opponent's
    discard cards and the devour pile's cards appear in every view, at
    `public.devour_pile` and each summary's `discard`; hand and deck stay counts.
  - `test_hidden_cards_reach_only_their_owner` — flipped to the new rule (the
    opponent's discard is now shown; hand and deck stay hidden).
  - `test_determinize_keeps_the_observer_view` and
    `test_tree_key_classes_match_view_classes` — their fixtures now seed every
    player's discard and the devour pile, so the new fields are covered (the
    determinize fixture also asserts the fixtures are non-empty).
- **C (`engine_c/tests/test_infostate_hash.c`).**
  `test_devour_and_discard_identity_split_everyone` — a same-count change inside
  the devour pile or an opponent's discard splits every observer's key.
- **Python, approved flips.**
  - `openspiel_pyrants/tests/test_observation_completeness.py` — T4 renamed
    `test_opponent_discard_pile_visible` and flipped: the marker now appears, at
    the opponent's summary `discard` and via `discard_size`.
  - `tests/nn/test_observation.py` — the T3.9 determinize-invariance test now
    also asserts the observer's whole view is unchanged by determinization
    (including any opponent discard) and that the opponent-discard component is
    non-vacuous, while the tensor-invariance assertion is unchanged.
  - `docs/validation/baseline/f013b_view_vectors.jsonl` — re-frozen with
    `docs/validation/harness/f013b_gen_vectors.py` (302 states, 918 vectors).
- **Not asserted differently.** `test_infostate_key.py`'s serialised-field
  mutation list already covers the devour *count*; the identity split is pinned
  at the C layer. No other assertion changed.

## Speed

Micro-benchmarks (`scripts/bench_view_hash.py`, committed; 118 playout states,
3,000 timed calls each, 4 players, three runs per build), parent `f68fb88` in a
separate worktree against this change:

- `engine_player_view_json`: parent mean 43.3–45.3 µs, median 38.8–39.0 µs →
  this change mean 42.5–46.2 µs, median 39.6–40.2 µs. The 918-vector corpus adds
  about 2 KB to a view (discard lists + devour pile); per-call cost is within
  run-to-run noise.
- `engine_infostate_hash`: parent mean 1.91–2.26 µs, median 1.9 µs → this change
  mean 2.02–2.16 µs, median 1.9–2.0 µs. The hash folds the extra card lists; its
  median is unchanged and the mean moves inside the parent's own spread.

Quick check (8 four-player games, 50 sims, seed 42, `--uct-c 1.4`), parent
`f68fb88` run `20261109T145355Z_c0d69d87c9c2` against this build run
`20261109T145118Z_524e06781560`:

- games/h 214.1 → 202.9 (run wall); ideal 263.0 → 250.7. Per-game wall ratio
  median 0.933, mean 0.974.
- Content differs on every game, as expected: determinization now leaves the
  visible discards in place and pools only hand+deck, so search samples a
  different world. `scripts/compare_paired_runs.py` reports `info_state_sha256`
  differing from decision line 0.

A 32-game paired run was not requested; the quick check answers the games/h
question for this brief.

Run ids, dirty flags, DLL hashes and per-game numbers for both the benchmarks
and the quick check are transcribed in
`docs/architecture-review/speed-records.md`, which is the durable record
because `artifacts/` is gitignored.
