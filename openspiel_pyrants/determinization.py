"""Determinization helper for IS-MCTS ``resample_from_infostate``.

Given an engine state and an observing player, produces a new engine state
where:
  - The public view is unchanged.
  - The observing player's private zones (hand, deck order, discard, etc.)
    are preserved exactly.
  - The opponent's hidden zones (hand, deck, discard) are reshuffled from
    the same multiset of cards — the observing player knows the counts but
    not the identities/order of the opponent's hidden cards.

Devour pile and played-cards / inner-circle / trophy-hall zones are public
knowledge and left unchanged.

Design note: this implements "perfect determinization" (we know all card
identities because we have the omniscient engine state).  A follow-up could
implement partial determinization that resamples only the top of the
opponent's deck while keeping hand/discard exactly as-is, which is a
well-known IS-MCTS speed/accuracy tradeoff.  See the handover notes.

The RNG parameter may be ``numpy.random.RandomState`` (with ``.shuffle``) or
``pyspiel.UniformProbabilitySampler`` (with only ``.uniform()``).  We adapt
to either.
"""

from __future__ import annotations

from engine.state import GameState


def _shuffle(items: list, rng) -> None:
    """Fisher-Yates shuffle using *rng*.

    *rng* may be ``numpy.random.RandomState`` (``.shuffle``) or
    ``pyspiel.UniformProbabilitySampler`` (callable, returns float in [0,1)).
    """
    if hasattr(rng, "shuffle"):
        rng.shuffle(items)
        return
    n = len(items)
    for i in range(n - 1, 0, -1):
        j = int(rng() * (i + 1))
        if j != i:
            items[i], items[j] = items[j], items[i]


def determinize_opponent_hidden_zones(
    engine: GameState,
    observing_player_id: str,
    rng,
) -> GameState:
    """Return a copy of *engine* with the opponent's hidden zones reshuffled.

    The *observing_player_id* is the player who is about to make a decision.
    Their private state is preserved.  The other player's hand, deck, and
    discard are reshuffled using *rng* (which must expose ``.uniform()``).

    Args:
        engine: The current omniscient engine state.
        observing_player_id: Player whose perspective the determinization
            respects.
        rng: RNG that is either callable (returning a float in [0,1)) or
            has ``.shuffle(list)`` — typically either
            ``numpy.random.RandomState`` or
            ``pyspiel.UniformProbabilitySampler`` as passed by the IS-MCTS bot.

    Returns:
        A new ``GameState`` with opponent hidden zones reshuffled.
    """
    result = engine.model_copy(deep=True)

    opponent_id: str | None = None
    for pid in engine.turn_order:
        if pid != observing_player_id:
            opponent_id = pid
            break

    if opponent_id is None:
        return result

    opponent = result.players[opponent_id]
    hidden: list[str] = list(opponent.hand) + list(opponent.deck) + list(opponent.discard_pile)
    hand_size = len(opponent.hand)
    deck_size = len(opponent.deck)
    discard_size = len(opponent.discard_pile)

    _shuffle(hidden, rng)

    opponent.hand = hidden[:hand_size]
    opponent.deck = hidden[hand_size : hand_size + deck_size]
    opponent.discard_pile = hidden[hand_size + deck_size : hand_size + deck_size + discard_size]

    return result

