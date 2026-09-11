"""The single allow-listed reader of hidden card zones for observation encoding.

``public_multisets`` may read ``CState.player_hand/deck/discard`` of a
non-acting seat and ``CState.market_deck()``. Every one of those reads is
returned as a *multiset only*, and the multiset is invariant under
``engine_determinize`` (G9): determinize pools each opponent's hand+deck+discard
and reshuffles them among themselves, and reshuffles the market deck, but never
touches the board, market row, played cards, inner circles, trophy halls or the
observing player's own zones. An opponent's *discard* identities are therefore
never exposed on their own (only as part of the pooled bag), which is what keeps
the leak test in ``tests/nn/test_observation.py`` passing.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class PublicMultisets:
    my_index: int
    hand: Counter
    played: Counter
    discard: Counter
    inner_circle: Counter
    deck: Counter
    bags: tuple[Counter, ...]
    played_by_seat: tuple[Counter, ...]
    inner_circle_by_seat: tuple[Counter, ...]
    market_remaining: Counter
    market_row: tuple[str, ...]


def _counter(items) -> Counter:
    return Counter(item for item in items if item)


def public_multisets(adapter, pid: str) -> PublicMultisets:
    """Return the acting player's view of every hidden-zone *multiset*.

    See the module docstring for the G9 invariance argument.
    """
    state = adapter.state
    my_index = adapter.player_index(pid)
    n = state.player_count

    bags: list[Counter] = []
    played_by_seat: list[Counter] = []
    inner_circle_by_seat: list[Counter] = []
    for i in range(n):
        bag = (
            _counter(state.player_deck(i))
            + _counter(state.player_hand(i))
            + _counter(state.player_discard(i))
        )
        bags.append(bag)
        played_by_seat.append(_counter(state.player_played(i)))
        inner_circle_by_seat.append(_counter(state.player_inner_circle(i)))

    return PublicMultisets(
        my_index=my_index,
        hand=_counter(state.player_hand(my_index)),
        played=_counter(state.player_played(my_index)),
        discard=_counter(state.player_discard(my_index)),
        inner_circle=_counter(state.player_inner_circle(my_index)),
        deck=_counter(state.player_deck(my_index)),
        bags=tuple(bags),
        played_by_seat=tuple(played_by_seat),
        inner_circle_by_seat=tuple(inner_circle_by_seat),
        market_remaining=_counter(state.market_deck()),
        market_row=tuple(c for c in state.market_row() if c),
    )
