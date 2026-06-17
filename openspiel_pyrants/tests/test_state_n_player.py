"""N-player returns shape and invariants for PyrantsState."""

from __future__ import annotations

import pytest


def _fresh_state(num_players=2):
    import pyspiel

    params = {"num_players": str(num_players)} if num_players != 2 else {}
    game = pyspiel.load_game("python_pyrants", params)
    state = game.new_initial_state()
    state.apply_action(42)
    return state


class TestNPlayerReturns:
    @pytest.mark.parametrize("num_players", [2, 3, 4])
    def test_returns_length_matches_num_players(self, num_players):
        state = _fresh_state(num_players=num_players)
        ret = state.returns()
        assert len(ret) == num_players

    def test_returns_zero_sum_for_2_players(self):
        state = _fresh_state(num_players=2)
        ret = state.returns()
        assert abs(sum(ret)) < 1e-9

    @pytest.mark.parametrize("num_players", [3, 4])
    def test_returns_not_necessarily_zero_sum_for_n_gt_2(self, num_players):
        state = _fresh_state(num_players=num_players)
        ret = state.returns()
        assert len(ret) == num_players

    def test_returns_before_engine_initialized(self):
        import pyspiel

        game = pyspiel.load_game("python_pyrants", {"num_players": "3"})
        state = game.new_initial_state()
        ret = state.returns()
        assert ret == [0.0, 0.0, 0.0]

    def test_returns_terminal_scores_2p(self):
        from engine.scoring import compute_final_scores

        import pyspiel

        game = pyspiel.load_game("python_pyrants")
        state = game.new_initial_state()
        state.apply_action(42)

        for _ in range(500):
            if state.is_terminal():
                break
            actions = state.legal_actions()
            if not actions:
                break
            state.apply_action(actions[0])

        if state.is_terminal():
            ret = state.returns()
            assert len(ret) == 2
            assert abs(sum(ret)) < 1e-9

            pids = state._game.get_player_ids()
            scores = compute_final_scores(state._engine)
            s0 = scores.get(pids[0], 0)
            s1 = scores.get(pids[1], 0)
            assert abs(ret[0] - (s0 - s1)) < 1e-6
            assert abs(ret[1] - (s1 - s0)) < 1e-6


class TestNPlayerStr:
    @pytest.mark.parametrize("num_players", [2, 3, 4])
    def test_str_includes_all_players(self, num_players):
        state = _fresh_state(num_players=num_players)
        s = str(state)
        for pid in state._game.get_player_ids():
            assert pid in s

    def test_str_before_engine(self):
        import pyspiel

        game = pyspiel.load_game("python_pyrants", {"num_players": "4"})
        state = game.new_initial_state()
        s = str(state)
        assert "chance node pending" in s
