"""Tests for C engine determinization used by IS-MCTS resample_from_infostate."""

from __future__ import annotations

import os
import numpy as np
import pyspiel
import pytest

import openspiel_pyrants  # noqa: F401


def _load_c_game(num_players: int = 2):
    return pyspiel.load_game("python_pyrants_c", {"num_players": str(num_players)})


def _hetero_market_setup_json() -> str:
    """A market deck with multiple distinct card IDs so shuffled order is observable."""
    import json

    return json.dumps(
        {
            "setup_id": "test_hetero_market",
            "starter_deck": {
                "deck_id": "starter_deck",
                "entries": [
                    {"card_id": "noble", "count": 7},
                    {"card_id": "soldier", "count": 3},
                ],
            },
            "market_deck": {
                "deck_id": "test_market",
                "entries": [
                    {"card_id": "noble", "count": 5},
                    {"card_id": "soldier", "count": 5},
                    {"card_id": "advance_scout", "count": 5},
                ],
            },
            "market_row_size": 6,
        }
    )


def _load_c_game_with_hetero_market(num_players: int = 2):
    return pyspiel.load_game(
        "python_pyrants_c",
        {"num_players": str(num_players), "setup_data_json": _hetero_market_setup_json()},
    )


@pytest.mark.skipif(
    os.environ.get("PYRANTS_SKIP_ISMCTS") == "1",
    reason="PYRANTS_SKIP_ISMCTS=1 set",
)
class TestDeterminizeC:
    def test_determinize_preserves_observing_player(self, requires_c_engine):
        """Observing player's hand/deck/discard unchanged after determinization."""
        game = _load_c_game(2)
        state = game.new_initial_state()
        state.apply_action(42)

        player_id = game.get_player_ids()[0]
        obs_view_before = state._adapter.private_view_json(player_id)

        det = state._adapter.determinize(player_id, seed=12345)
        assert det is not None
        obs_view_after = det.private_view_json(player_id)

        assert obs_view_before == obs_view_after

    def test_determinize_changes_opponent_hidden(self, requires_c_engine):
        """Opponent hidden zones differ across determinization seeds."""
        game = _load_c_game(2)
        state = game.new_initial_state()
        state.apply_action(42)

        det1 = state._adapter.determinize(game.get_player_ids()[0], seed=100)
        det2 = state._adapter.determinize(game.get_player_ids()[0], seed=999999)
        assert det1 is not None
        assert det2 is not None

        opp_idx = 1
        s1 = det1._state._s
        s2 = det2._state._s
        deck1 = [s1.players[opp_idx].deck[i] for i in range(s1.players[opp_idx].deck_count)]
        deck2 = [s2.players[opp_idx].deck[i] for i in range(s2.players[opp_idx].deck_count)]
        assert deck1 != deck2

    def test_determinize_reshuffles_market_deck(self, requires_c_engine):
        """Market deck order differs across seeds but preserves the multiset."""
        game = _load_c_game_with_hetero_market(2)
        state = game.new_initial_state()
        state.apply_action(42)

        adapter = state._adapter
        original_deck = adapter.state.market_deck()
        assert len(original_deck) > 1

        det1 = adapter.determinize(game.get_player_ids()[0], seed=100)
        det2 = adapter.determinize(game.get_player_ids()[0], seed=999999)
        assert det1 is not None
        assert det2 is not None

        deck1 = det1.state.market_deck()
        deck2 = det2.state.market_deck()

        assert sorted(deck1) == sorted(original_deck)
        assert sorted(deck2) == sorted(original_deck)
        assert deck1 != deck2

    def test_determinize_preserves_market_row(self, requires_c_engine):
        """Face-up market row is public: identical order across determinizations."""
        game = _load_c_game_with_hetero_market(2)
        state = game.new_initial_state()
        state.apply_action(42)

        adapter = state._adapter
        row_before = adapter.state.market_row()
        assert len(row_before) > 0

        for seed in (100, 999999):
            det = adapter.determinize(game.get_player_ids()[0], seed=seed)
            assert det is not None
            assert det.state.market_row() == row_before

    def test_resample_market_keeps_infostate_key(self, requires_c_engine):
        """Market-deck reshuffle must not leak into the information-state key."""
        game = _load_c_game_with_hetero_market(2)
        state = game.new_initial_state()
        state.apply_action(42)
        for _ in range(5):
            legal = state.legal_actions()
            if not legal:
                break
            state.apply_action(legal[0])

        cp = state.current_player()
        if cp < 0:
            pytest.skip("game ended early")

        rng = np.random.RandomState(99)
        deck_before = state._adapter.state.market_deck()
        resampled = state.resample_from_infostate(cp, rng)
        deck_after = resampled._adapter.state.market_deck()

        assert sorted(deck_before) == sorted(deck_after)
        if len(deck_before) > 1:
            assert deck_before != deck_after

        key_orig = state.information_state_string(cp)
        key_resampled = resampled.information_state_string(cp)
        assert key_orig == key_resampled

    def test_resample_from_infostate_matches_key(self, requires_c_engine):
        """ISMCTS assertion: resampled state has same infostate key as root."""
        game = _load_c_game(2)
        state = game.new_initial_state()
        state.apply_action(42)
        for _ in range(5):
            legal = state.legal_actions()
            if not legal:
                break
            state.apply_action(legal[0])

        rng = np.random.RandomState(99)
        resampled = state.resample_from_infostate(state.current_player(), rng)

        key_orig = state.information_state_string(state.current_player())
        key_resampled = resampled.information_state_string(state.current_player())
        assert key_orig == key_resampled

    def test_ismcts_smoke_with_determinization(self, requires_c_engine):
        """Existing smoke test pattern should still pass — regression check."""
        from open_spiel.python.algorithms.ismcts import ISMCTSFinalPolicyType
        from open_spiel.python.algorithms.mcts import RandomRolloutEvaluator

        from openspiel_pyrants.ismcts_factory import make_ismcts_bot

        game = _load_c_game(2)

        bot = make_ismcts_bot(
            game=game,
            seed=42,
            num_sims=5,
            uct_c=1.4,
            max_world_samples=100,
            final_policy_type=ISMCTSFinalPolicyType.NORMALIZED_VISITED_COUNT,
            evaluator=RandomRolloutEvaluator(
                n_rollouts=1, random_state=np.random.RandomState(42)
            ),
        )

        state = game.new_initial_state()
        state.apply_action(42)

        decisions = 0
        while not state.is_terminal():
            cp = state.current_player()
            if cp < 0 or cp >= 2:
                break
            legal_ids = state.legal_actions()
            _, chosen = bot.step_with_policy(state)
            assert chosen in legal_ids
            state.apply_action(chosen)
            decisions += 1

        assert decisions > 0
        ret = state.returns()
        assert len(ret) == 2
        assert abs(sum(ret)) < 1e-9
