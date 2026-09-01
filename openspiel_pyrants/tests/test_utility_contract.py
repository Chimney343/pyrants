"""Utility-contract tests for F-004.

``PyrantsCGame`` declared ``utility_sum=0.0`` and ``min_utility=-max_utility``
unconditionally for every ``num_players``, but ``PyrantsCState.returns()`` only
zero-sums the ``n==2`` case; for ``n>2`` it returns raw, non-negative VP totals
(see ``docs/validation/findings.md`` F-004). This suite locks in the fix and
guards the two regression traps:

* accidentally merging the ``n==2`` and ``n>2`` branches back together (T1/T2);
* a future card addition (a second negative-``deck_vp`` card, a new
  ``give_*``-style penalty effect) silently pushing a return below ``-50.0``
  without anyone noticing (T5).

Per the house pattern established in ``f010-fix-plan.md`` / ``f011-fix-plan.md``,
the regression/due-diligence controls (T1, T2) are written before the
completeness assertions (T3, T4) so the guards against breaking what already
works exist in history before the change that could break them. See
``docs/validation/f004-fix-plan.md`` § 4.
"""

from __future__ import annotations

import numpy as np
import pyspiel
import pytest

import openspiel_pyrants  # noqa: F401

N_GAMES = 50


def _load_c_game(num_players: int = 2):
    return pyspiel.load_game("python_pyrants_c", {"num_players": str(num_players)})


def _random_terminal_returns(game, seed: int) -> list[float]:
    """Play one random-policy game to terminal and return its ``returns()``."""
    state = game.new_initial_state()
    state.apply_action(seed)  # initial chance node: shuffle seed
    rng = np.random.RandomState(seed)
    steps = 0
    while not state.is_terminal():
        legal = state.legal_actions()
        if not legal:
            break
        state.apply_action(int(rng.choice(legal)))
        steps += 1
        if steps > 4096:
            break
    return state.returns()


class TestTwoPlayerContractUnchanged:
    def test_two_player_contract_unchanged(self, requires_c_engine):
        """T1 (control, G1): n==2 declaration is byte-identical to pre-fix."""
        game = _load_c_game(2)
        assert game.utility_sum() == 0.0
        assert game.min_utility() == -200.0
        assert game.max_utility() == 200.0
        assert game.get_type().utility == pyspiel.GameType.Utility.ZERO_SUM

    def test_two_player_returns_within_declared_bounds(self, requires_c_engine):
        """T2 (control): n==2 returns stay in [-200, 200] and sum to 0 over N=50.

        Due-diligence check on a magnitude claim the original F-004 finding never
        verified (it only checked the zero-sum *property*)."""
        game = _load_c_game(2)
        for seed in range(1, N_GAMES + 1):
            returns = _random_terminal_returns(game, seed)
            assert len(returns) == 2
            for r in returns:
                assert -200.0 <= r <= 200.0
            assert abs(sum(returns)) < 1e-9


class TestThreeAndFourPlayerContract:
    @pytest.mark.parametrize("num_players", [3, 4])
    def test_three_and_four_player_utility_sum_is_none(self, requires_c_engine, num_players):
        """T3 (RED): n>2 must declare general-sum via ``utility_sum is None``."""
        game = _load_c_game(num_players)
        assert game.utility_sum() is None

    @pytest.mark.parametrize("num_players", [3, 4])
    def test_three_and_four_player_min_utility_is_honest(self, requires_c_engine, num_players):
        """T4 (RED): n>2 declares the honest floor -50.0 and unchanged max/type."""
        game = _load_c_game(num_players)
        assert game.min_utility() == -50.0
        assert game.max_utility() == 400.0
        assert game.get_type().utility == pyspiel.GameType.Utility.GENERAL_SUM

    @pytest.mark.parametrize("num_players", [3, 4])
    def test_three_and_four_player_returns_within_declared_bounds(self, requires_c_engine, num_players):
        """T5 (gate G3): n>2 returns stay in [-50, 400] over N=50 random games."""
        game = _load_c_game(num_players)
        for seed in range(1, N_GAMES + 1):
            returns = _random_terminal_returns(game, seed)
            assert len(returns) == num_players
            for r in returns:
                assert -50.0 <= r <= 400.0
