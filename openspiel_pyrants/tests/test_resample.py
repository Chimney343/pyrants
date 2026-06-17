"""Tests for PyrantsState.resample_from_infostate determinization contract."""

from __future__ import annotations

import numpy as np
import pyspiel
import pytest

from engine.player_view import public_view


def _fresh_state(num_players=2):
    params = {"num_players": str(num_players)} if num_players != 2 else {}
    game = pyspiel.load_game("python_pyrants", params)
    state = game.new_initial_state()
    state.apply_action(42)
    return state


def _card_multiset(card_ids: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for cid in card_ids:
        counts[cid] = counts.get(cid, 0) + 1
    return counts


def _opponent_ids(state, observing_player: int) -> list[str]:
    pids = list(state._game.get_player_ids())
    return [pid for i, pid in enumerate(pids) if i != observing_player]


class TestResampleFromInfostate:
    def test_public_view_preserved(self):
        state = _fresh_state()
        rng = np.random.RandomState(123)

        sampled = state.resample_from_infostate(state.current_player(), rng)

        orig_pub = public_view(state._engine)
        sampled_pub = public_view(sampled._engine)
        assert orig_pub == sampled_pub

    def test_observing_player_hand_exact(self):
        state = _fresh_state()
        rng = np.random.RandomState(123)
        player = state.current_player()
        player_id = state._game.get_player_ids()[player]

        sampled = state.resample_from_infostate(player, rng)

        orig_hand = list(state._engine.players[player_id].hand)
        sampled_hand = list(sampled._engine.players[player_id].hand)
        assert orig_hand == sampled_hand

    def test_observing_player_deck_order_unchanged(self):
        state = _fresh_state()
        rng = np.random.RandomState(123)
        player = state.current_player()
        player_id = state._game.get_player_ids()[player]

        sampled = state.resample_from_infostate(player, rng)

        orig_deck = list(state._engine.players[player_id].deck)
        sampled_deck = list(sampled._engine.players[player_id].deck)
        assert orig_deck == sampled_deck

    def test_observing_player_discard_unchanged(self):
        state = _fresh_state()
        rng = np.random.RandomState(123)
        player = state.current_player()
        player_id = state._game.get_player_ids()[player]

        sampled = state.resample_from_infostate(player, rng)

        orig_discard = list(state._engine.players[player_id].discard_pile)
        sampled_discard = list(sampled._engine.players[player_id].discard_pile)
        assert orig_discard == sampled_discard

    def test_opponents_hidden_multisets_preserved(self):
        state = _fresh_state()
        rng = np.random.RandomState(42)
        player = state.current_player()

        opponent_ids = _opponent_ids(state, player)
        orig_multisets = {}
        for opp_id in opponent_ids:
            p = state._engine.players[opp_id]
            orig_multisets[opp_id] = _card_multiset(
                p.hand + p.deck + p.discard_pile
            )

        sampled = state.resample_from_infostate(player, rng)

        for opp_id in opponent_ids:
            p = sampled._engine.players[opp_id]
            sampled_multiset = _card_multiset(
                p.hand + p.deck + p.discard_pile
            )
            assert orig_multisets[opp_id] == sampled_multiset, \
                f"Multiset mismatch for {opp_id}"

    def test_opponents_zone_sizes_preserved(self):
        state = _fresh_state()
        rng = np.random.RandomState(42)
        player = state.current_player()

        opponent_ids = _opponent_ids(state, player)

        sampled = state.resample_from_infostate(player, rng)

        for opp_id in opponent_ids:
            opp_orig = state._engine.players[opp_id]
            opp_sampled = sampled._engine.players[opp_id]

            assert len(opp_sampled.hand) == len(opp_orig.hand)
            assert len(opp_sampled.deck) == len(opp_orig.deck)
            assert len(opp_sampled.discard_pile) == len(opp_orig.discard_pile)

    def test_determinization_is_random(self):
        state = _fresh_state()
        player = state.current_player()
        opponent_ids = _opponent_ids(state, player)

        rng1 = np.random.RandomState(42)
        rng2 = np.random.RandomState(99)

        s1 = state.resample_from_infostate(player, rng1)
        s2 = state.resample_from_infostate(player, rng2)

        # At least one opponent's deck order should differ between the two RNGs
        any_different = False
        for opp_id in opponent_ids:
            d1 = list(s1._engine.players[opp_id].deck)
            d2 = list(s2._engine.players[opp_id].deck)
            if d1 != d2:
                any_different = True

            total1 = (
                s1._engine.players[opp_id].hand
                + s1._engine.players[opp_id].deck
                + s1._engine.players[opp_id].discard_pile
            )
            total2 = (
                s2._engine.players[opp_id].hand
                + s2._engine.players[opp_id].deck
                + s2._engine.players[opp_id].discard_pile
            )
            assert sorted(total1) == sorted(total2)
        assert any_different, "No opponent deck order changed across different RNGs"

    def test_legal_actions_preserved(self):
        state = _fresh_state()
        rng = np.random.RandomState(123)
        player = state.current_player()

        sampled = state.resample_from_infostate(player, rng)

        orig_actions = state.legal_actions()
        samp_actions = sampled.legal_actions()
        assert orig_actions == samp_actions

    def test_resampled_state_is_playable(self):
        state = _fresh_state()
        rng = np.random.RandomState(123)
        player = state.current_player()

        sampled = state.resample_from_infostate(player, rng)

        for _ in range(10):
            if sampled.is_terminal():
                break
            actions = sampled.legal_actions()
            if not actions:
                break
            sampled.apply_action(actions[0])

        ret = sampled.returns()
        assert len(ret) == 2
        assert abs(sum(ret)) < 1e-9


class TestResampleMultiPlayer:
    @pytest.mark.parametrize("num_players", [3, 4])
    def test_all_opponents_reshuffled(self, num_players):
        state = _fresh_state(num_players=num_players)
        rng = np.random.RandomState(42)
        player = state.current_player()

        opponent_ids = _opponent_ids(state, player)
        orig_multisets = {}
        for opp_id in opponent_ids:
            p = state._engine.players[opp_id]
            orig_multisets[opp_id] = _card_multiset(
                p.hand + p.deck + p.discard_pile
            )

        sampled = state.resample_from_infostate(player, rng)

        for opp_id in opponent_ids:
            p = sampled._engine.players[opp_id]
            sampled_multiset = _card_multiset(
                p.hand + p.deck + p.discard_pile
            )
            assert orig_multisets[opp_id] == sampled_multiset

    @pytest.mark.parametrize("num_players", [3, 4])
    def test_resampled_state_is_playable(self, num_players):
        state = _fresh_state(num_players=num_players)
        rng = np.random.RandomState(123)
        player = state.current_player()

        sampled = state.resample_from_infostate(player, rng)

        for _ in range(10):
            if sampled.is_terminal():
                break
            actions = sampled.legal_actions()
            if not actions:
                break
            sampled.apply_action(actions[0])

        ret = sampled.returns()
        assert len(ret) == num_players
        # For num_players > 2, sum(returns()) is NOT zero
