"""A1 proof: a bot's decision must not depend on the order of its own deck.

The owner's visibility rule says no player sees any deck, including their own
(handoff, "Candidate 5 decisions"). IS-MCTS samples worlds through
``engine_determinize``, so before A1 every sampled world carried the acting
player's real next draws and the bot could choose with them.

This test builds two states that differ *only* in the acting player's deck
order, checks that they are indistinguishable through the public view and the
legal-move list, and then runs the production bot from ``ismcts_factory`` on
both with the same seeds. The chosen action and the whole policy must match: a
search that cannot see its own deck must behave identically.

It is the end-to-end companion of the C checks in
``engine_c/tests/test_visibility.c``.
"""

from __future__ import annotations

import os

import numpy as np
import pyspiel
import pytest

import openspiel_pyrants  # noqa: F401


def _load_c_game(num_players: int = 2):
    return pyspiel.load_game("python_pyrants_c", {"num_players": str(num_players)})


def _main_phase_state(game):
    """A fresh game taken to the first main-phase decision.

    Deterministic: chance seed 42, then the first legal move at each setup
    step. The acting player starts their turn with a hand and a refillable
    deck, so the end-of-turn cleanup draw (``engine_c/rules.c``) and every
    draw card in a rollout read the deck.
    """
    state = game.new_initial_state()
    state.apply_action(42)
    for _ in range(50):
        if state._adapter.phase() == "main":
            break
        legal = state.legal_actions()
        if not legal:
            break
        state.apply_action(int(legal[0]))
    assert state._adapter.phase() == "main"
    return state


def _set_deck_order(state, player_index: int, card_ids: list[str]) -> None:
    """Overwrite one player's deck with an explicit ordered card list."""
    from engine_c.bindings.engine_bindings import _lib

    ps = state._adapter._state._s.players[player_index]
    ps.deck_count = len(card_ids)
    for i, card_id in enumerate(card_ids):
        ps.deck[i] = _lib.intern(card_id.encode())
    state._adapter._view_cache.clear()


def _deck_order(state, player_index: int) -> list[str]:
    return list(state._adapter._state.player_deck(player_index))


def _policy_key(policy) -> tuple:
    return tuple(sorted((int(a), round(float(p), 9)) for a, p in policy))


def _make_bot(game, seed: int, num_sims: int):
    from open_spiel.python.algorithms.ismcts import ISMCTSFinalPolicyType

    from openspiel_pyrants.c_rollout_evaluator import CRolloutEvaluator
    from openspiel_pyrants.ismcts_factory import make_ismcts_bot

    return make_ismcts_bot(
        game=game,
        seed=seed,
        num_sims=num_sims,
        uct_c=1.4,
        max_world_samples=-1,
        final_policy_type=ISMCTSFinalPolicyType.NORMALIZED_VISITED_COUNT,
        evaluator=CRolloutEvaluator(
            max_length=0, random_state=np.random.RandomState(seed)
        ),
    )


@pytest.mark.skipif(
    os.environ.get("PYRANTS_SKIP_ISMCTS") == "1",
    reason="PYRANTS_SKIP_ISMCTS=1 set",
)
@pytest.mark.parametrize("seed", [4242, 7, 999])
def test_bot_decision_ignores_own_deck_order(requires_c_engine, seed):
    """Two deck orders the bot cannot see must give the same move and policy."""
    game = _load_c_game(2)
    base = _main_phase_state(game)

    acting = base.current_player()
    assert acting >= 0
    player_index = base._adapter.player_index(game.get_player_ids()[acting])

    order_a = ["noble", "soldier", "noble", "soldier"]
    order_b = ["soldier", "noble", "soldier", "noble"]

    state_a = base.clone()
    state_b = base.clone()
    _set_deck_order(state_a, player_index, order_a)
    _set_deck_order(state_b, player_index, order_b)

    # Only the hidden deck order differs; the acting player's view and legal
    # moves are identical, and the deck really does hold two different orders.
    player_id = game.get_player_ids()[acting]
    assert _deck_order(state_a, player_index) != _deck_order(state_b, player_index)
    assert (
        state_a._adapter.private_view_json(player_id)
        == state_b._adapter.private_view_json(player_id)
    )
    assert state_a.legal_actions() == state_b.legal_actions()

    policy_a, chosen_a = _make_bot(game, seed, 16).step_with_policy(state_a.clone())
    policy_b, chosen_b = _make_bot(game, seed, 16).step_with_policy(state_b.clone())

    assert int(chosen_a) == int(chosen_b)
    assert _policy_key(policy_a) == _policy_key(policy_b)
