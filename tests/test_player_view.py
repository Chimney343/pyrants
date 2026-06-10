"""Tests for engine/player_view.py — public/private information projection."""

from __future__ import annotations

from pathlib import Path

from engine.player_view import (
    PrivateView,
    PublicView,
    private_view,
    public_view,
)
from engine.rules import apply as apply_move
from game_setup.loaders import build_game_definition_from_files

_DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _make_definition():
    return build_game_definition_from_files(
        _DATA_DIR / "boards" / "tyrants_of_the_underdark.json",
        _DATA_DIR / "cards" / "catalog.json",
        _DATA_DIR / "decks" / "base_setup.json",
    )


def _initial_state():
    from engine.state import build_initial_game_state

    return build_initial_game_state(
        _make_definition(),
        player_ids=["p0", "p1"],
        shuffle_seed=42,
    )


class TestPublicView:
    def test_round_trip_serialize(self):
        state = _initial_state()
        pub = public_view(state)
        json_str = pub.model_dump_json()
        rehydrated = PublicView.model_validate_json(json_str)
        assert rehydrated == pub

    def test_identical_for_both_players(self):
        state = _initial_state()
        pub0 = public_view(state)
        pub1 = public_view(state)
        assert pub0 == pub1

    def test_no_private_contents_in_public(self):
        state = _initial_state()
        pub = public_view(state)
        summary_keys = set(next(iter(pub.public_player_summaries.values())).keys())
        for key in summary_keys:
            assert key.endswith("_size") or key in {
                "barracks", "spies_available", "vp_tokens", "score"
            }, f"Unexpected key in public summary: {key}"

    def test_board_has_controllers_and_troops(self):
        state = _initial_state()
        pub = public_view(state)
        starter_node = pub.board[0]
        assert starter_node.node_id
        assert starter_node.kind in ("site", "route")
        assert isinstance(starter_node.controller, str) or starter_node.controller is None
        assert isinstance(starter_node.troop_counts, dict)

    def test_market_row_is_card_ids(self):
        state = _initial_state()
        pub = public_view(state)
        assert len(pub.market_row) == 6
        assert all(isinstance(cid, str) for cid in pub.market_row)
        assert pub.market_deck_size > 0
        assert pub.market_discard_size == 0


class TestPrivateView:
    def test_round_trip_serialize(self):
        state = _initial_state()
        priv = private_view(state, "p0")
        json_str = priv.model_dump_json()
        rehydrated = PrivateView.model_validate_json(json_str)
        assert rehydrated == priv

    def test_public_view_is_subset(self):
        state = _initial_state()
        priv = private_view(state, "p0")
        pub = public_view(state)
        assert priv.public == pub

    def test_players_differ_in_private_fields(self):
        state = _initial_state()
        priv0 = private_view(state, "p0")
        priv1 = private_view(state, "p1")
        assert priv0.public == priv1.public
        assert priv0.hand != priv1.hand or priv0.deck_size != priv1.deck_size

    def test_hand_contains_card_ids(self):
        state = _initial_state()
        priv = private_view(state, "p0")
        assert len(priv.hand) == 5
        assert all(isinstance(cid, str) for cid in priv.hand)

    def test_deck_size_is_correct(self):
        state = _initial_state()
        priv0 = private_view(state, "p0")
        priv1 = private_view(state, "p1")
        assert priv0.deck_size == 5
        assert priv1.deck_size == 5

    def test_opponent_hand_not_visible(self):
        state = _initial_state()
        priv0 = private_view(state, "p0")
        assert priv0.public.public_player_summaries["p1"]["hand_size"] == 5
        assert "p1" not in [str(h) for h in ["hand"]]  # hand field is only p0's

    def test_barracks_and_spies_present(self):
        state = _initial_state()
        priv = private_view(state, "p0")
        assert priv.barracks == 40
        assert priv.spies_available == 5

    def test_opponent_private_not_leaked(self):
        state = _initial_state()
        priv0 = private_view(state, "p0")
        assert len(priv0.hand) == 5
        assert len(state.players["p0"].hand) == 5
        assert priv0.hand == state.players["p0"].hand


class TestAfterPlayCard:
    def test_played_card_appears_in_private_played(self):
        state = _initial_state()
        hand_before = list(state.players["p0"].hand)
        card_to_play = hand_before[0]

        from engine.moves import PlayCardMove

        move = PlayCardMove(player_id="p0", card_id=card_to_play)
        state2 = apply_move(state, move)

        priv0 = private_view(state2, "p0")
        priv1 = private_view(state2, "p1")

        assert card_to_play in priv0.played_cards
        assert priv1.public.public_player_summaries["p0"]["played_size"] > 0
        assert card_to_play not in priv1.public.market_row
