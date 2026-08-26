"""Tests for the IS-MCTS runner (run_ismcts.py) on the C backend.

Verifies the runner works with python_pyrants_c for 2/3/4 players, using
tiny simulation budgets.
"""

from __future__ import annotations

import pytest

import openspiel_pyrants  # noqa: F401
from scripts.run_ismcts import _load_game_or_die, _resolve_policy, run_one_game


def _build_quick_params(game_name: str, num_players: int) -> dict:
    return {
        "game": _load_game_or_die(game_name, {"num_players": str(num_players)}),
        "game_index": 0,
        "num_sims": 2,
        "uct_c": 1.4,
        "max_world_samples": 10,
        "final_policy_type": _resolve_policy("visited"),
        "final_policy_name": "visited",
        "seed": 42,
        "shuffle_seed": 42,
        "out_dir": __import__("pathlib").Path(
            __import__("tempfile").mkdtemp(prefix="ismcts_test_")
        ),
        "show_progress": False,
        "rollout_count": 1,
        "rollout_max_length": None,
        "max_rounds": 15,
        "num_players": num_players,
    }


class TestRunISMCTSRunner:
    @pytest.mark.parametrize("num_players", [2, 3, 4])
    def test_c_backend(self, requires_c_engine, tmp_path, num_players):
        params = _build_quick_params("python_pyrants_c", num_players)
        params["out_dir"] = tmp_path

        summary = run_one_game(**params)

        assert summary["decision_count"] > 0, "No decisions made"
        ret = summary["returns"]
        assert len(ret) == num_players
        if num_players == 2:
            assert abs(sum(ret)) < 1e-9, f"Returns not zero-sum: {ret}"
        final_scores = summary["final_scores_per_player"]
        assert len(final_scores) == num_players
        assert isinstance(summary["winner"], (int, type(None)))


class TestParseArgsDefaults:
    def test_max_world_samples_defaults_to_unlimited(self, monkeypatch):
        import sys

        from scripts.run_ismcts import _parse_args

        monkeypatch.setattr(sys, "argv", ["run_ismcts"])
        args = _parse_args()
        assert args.max_world_samples == -1


class TestCMoveWrapperNormalization:
    def test_all_moves_normalized(self, requires_c_engine):
        from engine_c.bindings.ce_api import _MOVE_TYPE_MAP, CMoveWrapper  # noqa: I001

        known_python_names = {
            "play_card",
            "end_main_phase",
            "resolve_end_of_turn",
            "resolve_cleanup",
            "assassinate",
            "deploy",
            "recruit",
            "return_spy",
            "activate_card_ability",
            "decline_card_ability",
            "promote_card",
            "skip_promote",
            "resolve_generic_choice",
            "initial_placement",
        }

        for c_name in _MOVE_TYPE_MAP.values():
            normalized = CMoveWrapper._NAME_NORMALIZE.get(c_name, c_name)
            assert normalized in known_python_names, (
                f"C name {c_name!r} normalizes to {normalized!r}, "
                f"not in known Python names"
            )

    def test_to_payload_smoke(self):
        """Verify to_payload() returns move_type + data for a mock move."""
        from engine_c.bindings.ce_api import CMove, CMoveWrapper, MOVE_PLAY_CARD, _lib  # noqa: I001

        _lib.intern_init(4096)
        card_sym = _lib.intern(b"test_card")
        c_move = CMove()
        c_move.type = MOVE_PLAY_CARD
        c_move.data.play_card.card_id = card_sym
        c_move.data.play_card.hand_index = 2

        wrapper = CMoveWrapper(c_move)
        payload = wrapper.to_payload()
        assert payload["move_type"] == "play_card"
        assert payload["card_id"] == "test_card"
        assert payload["hand_index"] == 2

    def test_str_smoke(self):
        from engine_c.bindings.ce_api import CMove, CMoveWrapper, MOVE_PLAY_CARD, _lib  # noqa: I001

        _lib.intern_init(4096)
        card_sym = _lib.intern(b"test_card")
        c_move = CMove()
        c_move.type = MOVE_PLAY_CARD
        c_move.data.play_card.card_id = card_sym
        c_move.data.play_card.hand_index = 2

        wrapper = CMoveWrapper(c_move)
        s = str(wrapper)
        assert "play_card" in s
        assert "test_card" in s

    def test_activate_ability_normalized(self):
        from engine_c.bindings.ce_api import CMove, CMoveWrapper, MOVE_ACTIVATE_ABILITY, _lib  # noqa: I001

        _lib.intern_init(4096)
        card_sym = _lib.intern(b"noble")
        ability_sym = _lib.intern(b"spy")
        c_move = CMove()
        c_move.type = MOVE_ACTIVATE_ABILITY
        c_move.data.activate_ability.card_id = card_sym
        c_move.data.activate_ability.ability_key = ability_sym

        wrapper = CMoveWrapper(c_move)
        payload = wrapper.to_payload()
        assert payload["move_type"] == "activate_card_ability"
        assert payload["card_id"] == "noble"
