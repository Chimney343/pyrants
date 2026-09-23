# Determinization

A determinization is one concrete, fully-visible world consistent with what an
observing player is allowed to know. Pyrants hides opponents' hands, deck orders,
and the market-deck order, so IS-MCTS cannot simulate a future until those zones
are filled in. `engine_determinize` does that filling in: it clones the state and
reshuffles only the hidden zones. The normal rules engine then evolves the world
during search.

This doc maps the contract to the code. For the surrounding wrapper, see
[openspiel-architecture.md](openspiel-architecture.md) and
[openspiel-integration.md](openspiel-integration.md).

## Code map

| Step | Location |
|------|----------|
| Resample hidden zones (the real work) | `engine_c/state.c:271-319` (`engine_determinize`) |
| Python ctypes call | `engine_c/bindings/ce_api.py:451-457` (`CEngine.determinize`) |
| Adapter wrapper (returns a new adapter) | `engine_c/bindings/c_adapter.py:105-118` (`CEngineAdapter.determinize`) |
| OpenSpiel entry point | `openspiel_pyrants/state_c.py:310-341` (`PyrantsCState.resample_from_infostate`) |
| Seeded resampler hook | `openspiel_pyrants/ismcts_factory.py:69` (`make_ismcts_bot`) |
| Leaf rollout, separate RNG | `openspiel_pyrants/c_rollout_evaluator.py:29-39` |
| Random rollout loop | `engine_c/rollout.c:25-78` |

## What `engine_determinize` does

Given the current state and the observing player's id:

1. Clone the state (`engine_clone`, `engine_c/state.c:273`). The caller's state is
   never mutated.
2. For each opponent (`engine_c/state.c:279-298`):
   - pool their `hand + deck + discard` into one array;
   - Fisher-Yates shuffle the pooled cards;
   - deal them back into the same three zones, keeping the original per-zone counts.
3. Reshuffle the market deck order if it holds more than one card
   (`engine_c/state.c:304-306`). The face-up market row and the unused market
   discard are left alone.
4. Reroll the world's shuffle stream: `shuffle_seed = rng_next(&rng)` and
   `shuffle_counter = 0` (`engine_c/state.c:315-316`).

The observing player is skipped (`engine_c/state.c:281`); their cards keep their
exact identities and positions.

## What it does not do

- It does not draw, discard, or add cards. Every hidden zone keeps the same
  multiset and the same count; only the arrangement changes.
- It does not touch the board, scores, resources, trophies, or other public state.
- It does not simulate how decks evolve. That happens later, when search applies
  moves and the rules engine draws cards and reshuffles discard piles.

## Why reshuffle the whole hand + deck + discard

A player's information state gives them the *sizes* of an opponent's hidden zones
and the public card pool, but not which cards sit in which zone or in what order.
Any arrangement that keeps those sizes and the known multiset is a possible world.
The resampler samples one of them at random, so the search does not assume a single
clairvoyant ordering.

## Why reroll `shuffle_seed`

Every deck shuffle in the engine reseeds from the state's
`(shuffle_seed, shuffle_counter)` pair — see `shuffle_deck`
(`engine_c/state.c:19-26`) and `reshuffle_discard_into_deck`
(`engine_c/state.c:219-231`). If determinization reused the parent's seed, every
sampled world would produce the *same* future reshuffle order, and IS-MCTS could
exploit one fixed draw order. Rerolling the seed and zeroing the counter gives each
sampled world an independent stream of future draws. The reroll sits after every
other RNG draw so the new seed is a deterministic function of the input `seed`
(`engine_c/state.c:308-316`; see `docs/validation/f002-f003-fix-plan.md`).

## Lifecycle in IS-MCTS

1. At a decision node the bot calls `resample_from_infostate(player, rng)`
   (`openspiel_pyrants/state_c.py:310-341`). A seeded numpy RNG supplies a 62-bit
   seed (`state_c.py:316-319`); a bare callable is rejected (`state_c.py:320-326`).
2. `determinize` returns a new adapter, and `resample_from_infostate` wraps it in a
   new `PyrantsCState` with the same history. Cached action ids are cleared
   (`state_c.py:336`).
3. The stock `ISMCTSBot` searches that concrete world. Normal move application
   evolves the decks: `draw_cards_state` (`engine_c/state.c:29-41`),
   `reshuffle_discard_into_deck` (`engine_c/state.c:219-231`), and the end-of-turn
   draw-up-to-five (`engine_c/phases.c:31`).
4. Leaf values come from `CRolloutEvaluator`, which runs the whole random rollout
   in C via `engine_random_rollout` (`engine_c/rollout.c:25-78`) using its own
   rollout seed, separate from the world's shuffle stream.

## Invariants (locked by tests)

| Invariant | Test |
|-----------|------|
| Observing player's hand/deck/discard unchanged | `openspiel_pyrants/tests/test_determinize_c.py:56` |
| Opponent hidden zones differ across seeds | `openspiel_pyrants/tests/test_determinize_c.py:71` |
| Market deck order changes but multiset is preserved | `openspiel_pyrants/tests/test_determinize_c.py:89` |
| Public market row identical across determinizations | `openspiel_pyrants/tests/test_determinize_c.py:111` |
| Resampled state keeps the same information-state key | `openspiel_pyrants/tests/test_determinize_c.py:154` |
| Different seeds decouple the reshuffle stream; same seed reproduces | `openspiel_pyrants/tests/test_determinize_reshuffle_independence.py:69` |
| Determinization does not change the observation | `openspiel_pyrants/tests/test_observation_completeness.py:147` |
| Worlds stay diverse while a run is reproducible from `--seed` | `openspiel_pyrants/tests/test_ismcts_reproducibility.py:210` |

## Notes

- If the C call fails, `resample_from_infostate` falls back to an ordinary clone
  (`openspiel_pyrants/state_c.py:329-330`).
- Determinization never changes public state, so the parent's board projection is
  shared by reference with the child (`engine_c/bindings/c_adapter.py:69-87`).
- Every opponent is reshuffled from the same RNG stream, so in 3-4 player games the
  draw order is still deterministic for a given `seed`.
