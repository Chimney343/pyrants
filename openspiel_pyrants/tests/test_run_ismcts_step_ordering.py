"""Tests for the IS-MCTS runner's replay-log step ordering.

The replay log must only record a move *after* ``state.apply_action`` has
succeeded.  If ``apply_action`` raises (the normal failure mode documented in
``docs/ismcts-generic-resolution-bugs.md``), the log must not contain an entry
claiming the move succeeded.

The test drives ``run_one_game()`` through a proxy ``apply_action`` that fails
on the Nth move call and asserts the replay log contains exactly the entries
for moves that actually applied.
"""

from __future__ import annotations

import json

import pytest

import openspiel_pyrants  # noqa: F401
from scripts.run_ismcts import _game_dir, _load_game_or_die, _resolve_policy, run_one_game

_MOVE_FAIL_ON_CALL = 3  # 1 = shuffle chance action, 2 = move 1, 3 = move 2


def _flaky_game(fail_on_call: int = _MOVE_FAIL_ON_CALL):
    """Build a game whose state.apply_action raises on the Nth call.

    ``apply_action`` is called once for the initial shuffle chance node and
    once per move.  Returns ``(game, state, counters)`` where counters is a
    dict with ``apply_calls``, ``move_applies_succeeded`` (chance apply
    excluded), and ``replay_entries_built``.
    """
    game = _load_game_or_die("python_pyrants_c", {"num_players": "2"})
    state = game.new_initial_state()  # chance node pending
    counters = {
        "apply_calls": 0,
        "move_applies_succeeded": 0,
        "replay_entries_built": 0,
    }

    def flaky_apply_action(action) -> None:
        counters["apply_calls"] += 1
        if counters["apply_calls"] == fail_on_call:
            raise RuntimeError("boom")
        state._apply_action(action)
        if counters["apply_calls"] > 1:  # skip the initial chance-node apply
            counters["move_applies_succeeded"] += 1

    state.apply_action = flaky_apply_action

    orig_move_to_payload = state.move_to_payload

    def counting_move_to_payload(move) -> dict:
        counters["replay_entries_built"] += 1
        return orig_move_to_payload(move)

    state.move_to_payload = counting_move_to_payload
    game.new_initial_state = lambda: state
    return game, state, counters


class TestReplayLogOrdering:
    def test_failed_move_not_in_replay_log(self, requires_c_engine, tmp_path):
        """A move whose apply_action raises must not appear in the replay log."""
        game, state, counters = _flaky_game()

        with pytest.raises(RuntimeError, match="boom"):
            run_one_game(
                game=game,
                game_index=0,
                num_sims=2,
                uct_c=1.4,
                max_world_samples=10,
                final_policy_type=_resolve_policy("visited"),
                final_policy_name="visited",
                seed=42,
                shuffle_seed=42,
                out_dir=tmp_path,
                show_progress=False,
                rollout_count=1,
                rollout_max_length=None,
                max_rounds=100,
                setup_data_json="",
                num_players=2,
                deck_a_id="deck_a",
                deck_b_id="deck_b",
                run_id="order_test",
            )

        assert counters["apply_calls"] == _MOVE_FAIL_ON_CALL
        # One move applied successfully before the third apply call raised
        # (the first call is the initial shuffle chance node).
        assert counters["move_applies_succeeded"] == _MOVE_FAIL_ON_CALL - 2
        # The replay log may only contain entries for moves that succeeded:
        # an entry must not be built for a move whose apply_action raises.
        assert counters["replay_entries_built"] == counters["move_applies_succeeded"]


class TestReplayLogRoundAndPhase:
    def test_round_and_phase_reflect_pre_move_state(self, requires_c_engine, tmp_path):
        """replay_log's round_number/phase must describe the state the move
        was chosen in, not the state left behind after applying it.

        decisions.jsonl captures round/phase before apply_action runs (that
        ordering is untouched by the crash-safety fix), so it's the source of
        truth to compare replay_log against. A move that ends a phase or round
        (e.g. end_main_phase, resolve_cleanup) changes state._engine's live
        round_number/phase as a side effect of apply_action; replay_log must
        not pick up that shift.
        """
        game = _load_game_or_die("python_pyrants_c", {"num_players": "2"})

        run_one_game(
            game=game,
            game_index=0,
            num_sims=2,
            uct_c=1.4,
            max_world_samples=10,
            final_policy_type=_resolve_policy("visited"),
            final_policy_name="visited",
            seed=42,
            shuffle_seed=42,
            out_dir=tmp_path,
            show_progress=False,
            rollout_count=1,
            rollout_max_length=None,
            max_rounds=15,
            num_players=2,
        )

        game_out = _game_dir(tmp_path, 0)
        decisions = [
            json.loads(line)
            for line in (game_out / "decisions.jsonl").open(encoding="utf-8")
        ]
        replay_log = json.loads((game_out / "replay.json").read_text(encoding="utf-8"))["replay_log"]

        decisions_by_step = {d["node"]: d for d in decisions}
        checked = 0
        for entry in replay_log:
            if entry["move_type"] == "__terminal__":
                continue
            decision = decisions_by_step[entry["step_index"]]
            assert entry["round_number"] == decision["round"], entry
            assert entry["phase"] == decision["phase"], entry
            checked += 1

        assert checked > 0
