"""Tests for the IS-MCTS runner (run_ismcts.py) on the C backend.

Verifies the runner works with python_pyrants_c for 2/3/4 players, using
tiny simulation budgets.
"""

from __future__ import annotations

import json

import pytest

import openspiel_pyrants  # noqa: F401
from scripts.run_ismcts import _game_dir, _load_game_or_die, _resolve_policy, run_one_game


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

        # A successful run must have produced a streaming steps.jsonl with one
        # "step" line per decision and a trailing "game_end" line.
        game_out = _game_dir(tmp_path, 0)
        steps_path = game_out / "steps.jsonl"
        assert steps_path.exists(), "steps.jsonl missing after a successful run"
        steps = [json.loads(line) for line in steps_path.open(encoding="utf-8")]
        step_events = [s["event"] for s in steps]
        assert step_events[-1] == "game_end"
        assert len([e for e in step_events if e == "step"]) == summary["decision_count"]


class TestParseArgsDefaults:
    def test_max_world_samples_defaults_to_unlimited(self, monkeypatch):
        import sys

        from scripts.run_ismcts import _parse_args

        monkeypatch.setattr(sys, "argv", ["run_ismcts"])
        args = _parse_args()
        assert args.max_world_samples == -1

    def test_num_sims_per_seat_default_absent(self, monkeypatch):
        import sys

        from scripts.run_ismcts import _parse_args

        monkeypatch.setattr(sys, "argv", ["run_ismcts"])
        args = _parse_args()
        assert args.num_sims_per_seat is None
        assert args.num_sims == 200

    def test_num_sims_per_seat_parses(self, monkeypatch):
        import sys

        from scripts.run_ismcts import _parse_args

        monkeypatch.setattr(
            sys, "argv", ["run_ismcts", "--num-sims-per-seat", "50,100,200,400",
                          "--num-players", "4"]
        )
        args = _parse_args()
        assert args.num_sims_per_seat == [50, 100, 200, 400]

    def test_num_sims_per_seat_length_mismatch(self, monkeypatch):
        import sys

        from scripts.run_ismcts import _parse_args

        monkeypatch.setattr(
            sys, "argv", ["run_ismcts", "--num-sims-per-seat", "50,100,200",
                          "--num-players", "4"]
        )
        with pytest.raises(SystemExit):
            _parse_args()

    def test_num_sims_per_seat_mutually_exclusive_with_num_sims(self, monkeypatch):
        import sys

        from scripts.run_ismcts import _parse_args

        monkeypatch.setattr(
            sys, "argv", ["run_ismcts", "--num-sims-per-seat", "50,100,200,400",
                          "--num-sims", "200", "--num-players", "4"]
        )
        with pytest.raises(SystemExit):
            _parse_args()

    def test_num_sims_per_seat_non_integer(self, monkeypatch):
        import sys

        from scripts.run_ismcts import _parse_args

        monkeypatch.setattr(
            sys, "argv", ["run_ismcts", "--num-sims-per-seat", "50,abc,200,400",
                          "--num-players", "4"]
        )
        with pytest.raises(SystemExit):
            _parse_args()


class TestPerSeatBudgets:
    def test_run_one_game_per_seat_budgets(self, requires_c_engine, tmp_path):
        # Note: budgets are >= 2 because the stock ISMCTSBot leaves
        # total_visits == 0 after a single simulation, which trips its
        # NORMALIZED_VISITED_COUNT assertion (num_sims=1 is unsupported).
        params = _build_quick_params("python_pyrants_c", 4)
        params["num_sims"] = [2, 2, 3, 4]
        params["out_dir"] = tmp_path
        params["max_rounds"] = 5

        summary = run_one_game(**params)

        assert summary["num_sims_per_seat"] == [2, 2, 3, 4]
        assert summary["num_sims_per_move"] == 2.75
        assert summary["decision_count"] > 0
        assert len(summary["returns"]) == 4

        # decisions.jsonl must record the acting seat's budget, not a global value.
        game_out = _game_dir(tmp_path, 0)
        decisions = [
            json.loads(line)
            for line in (game_out / "decisions.jsonl").open(encoding="utf-8")
        ]
        requested = {d["sims_requested"] for d in decisions}
        assert requested <= {2, 3, 4}

    def test_run_one_game_scalar_backward_compat(self, requires_c_engine, tmp_path):
        params = _build_quick_params("python_pyrants_c", 4)
        params["out_dir"] = tmp_path
        params["max_rounds"] = 5

        summary = run_one_game(**params)

        assert summary["num_sims_per_seat"] == [2, 2, 2, 2]
        assert summary["num_sims_per_move"] == 2

    def test_run_one_game_invalid_length_raises(self, requires_c_engine, tmp_path):
        params = _build_quick_params("python_pyrants_c", 4)
        params["num_sims"] = [1, 2, 2]
        with pytest.raises(ValueError):
            run_one_game(**params)


class TestPerSeatUct:
    def test_run_one_game_per_seat_uct(self, requires_c_engine, tmp_path):
        params = _build_quick_params("python_pyrants_c", 4)
        params["uct_c"] = [0.3, 0.8, 1.4, 2.5]
        params["out_dir"] = tmp_path
        params["max_rounds"] = 5

        summary = run_one_game(**params)

        assert summary["uct_c_per_seat"] == [0.3, 0.8, 1.4, 2.5]
        assert summary["uct_c"] == pytest.approx(1.25)
        assert summary["decision_count"] > 0

        # Final-deck capture: final_decks.json written, final_vp_per_seat
        # seat-ordered, final_deck_metrics present.
        game_out = _game_dir(tmp_path, 0)
        decks_path = game_out / "final_decks.json"
        assert decks_path.exists(), "final_decks.json missing after a successful run"
        final_decks = json.loads(decks_path.read_text(encoding="utf-8"))
        assert len(final_decks["player_ids"]) == 4
        assert len(final_decks["per_seat"]) == 4

        # The captured deck is card zones only: trophy-hall entries store
        # troop-owner tokens ("white" / player ids), never card ids, so they
        # must not appear in the per-seat card-id lists.
        token_ids = set(final_decks["player_ids"]) | {"white"}
        for seat in final_decks["per_seat"]:
            assert seat, "per-seat deck must not be empty"
            for card_id in seat:
                assert isinstance(card_id, str)
                assert card_id not in token_ids, (
                    f"non-card trophy token {card_id!r} leaked into the deck capture"
                )

        assert len(summary["player_ids"]) == 4
        assert len(summary["final_vp_per_seat"]) == 4
        assert all(isinstance(v, int) for v in summary["final_vp_per_seat"])
        assert len(summary["final_deck_metrics"]) == 4
        for dm in summary["final_deck_metrics"]:
            assert "full" in dm
            assert "recruited" in dm
            assert "recruited_degraded" in dm
            for metric_key in ("unique_count", "deck_size", "unique_ratio",
                               "shannon_entropy", "normalized_entropy", "simpson"):
                assert metric_key in dm["full"]
                assert metric_key in dm["recruited"]

    def test_run_one_game_scalar_uct_backward_compat(self, requires_c_engine, tmp_path):
        params = _build_quick_params("python_pyrants_c", 4)
        params["out_dir"] = tmp_path
        params["max_rounds"] = 5

        summary = run_one_game(**params)

        assert summary["uct_c_per_seat"] == [1.4, 1.4, 1.4, 1.4]
        assert summary["uct_c"] == pytest.approx(1.4)

    def test_run_one_game_uct_wrong_length_raises(self, requires_c_engine, tmp_path):
        params = _build_quick_params("python_pyrants_c", 4)
        params["uct_c"] = [0.3, 0.8, 1.4]
        with pytest.raises(ValueError):
            run_one_game(**params)

    def test_run_one_game_uct_nonpositive_raises(self, requires_c_engine, tmp_path):
        params = _build_quick_params("python_pyrants_c", 4)
        params["uct_c"] = [0.3, 0.0, 1.4, 2.5]
        with pytest.raises(ValueError):
            run_one_game(**params)


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

        # NOTE: do NOT call _lib.intern_init here — the intern table is global
        # C state; re-initializing it wipes Syms referenced by any loaded game
        # definition and corrupts subsequent tests in the session. intern()
        # self-initializes when the table is empty.
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
