"""Tests for write_summaries() in scripts/run_ismcts.py.

Phase 1 will produce partial/crashed-game summaries that may omit fields
present in the CSV fieldnames list. The writer must tolerate missing fields
by writing blank cells rather than raising KeyError.
"""

from __future__ import annotations

import csv

from scripts.run_ismcts import write_summaries


class TestWriteSummariesMissingFields:
    def test_missing_field_does_not_raise(self, tmp_path):
        summaries = [
            {
                "run_id": "run123",
                "game_index": 0,
                "shuffle_seed": 42,
                "deck_a_id": "a",
                "deck_b_id": "b",
                "num_sims_per_move": 2,
                "uct_c": 1.4,
                "rollout_count": 1,
                "rollout_max_length": None,
                "decision_count": 10,
                "wall_time_sec": 5.0,
                "sims_per_sec_avg": 4.0,
                "moves_per_sec_avg": 2.0,
                "winner": 0,
                "outcome": "p0_win",
                "stopped_reason": "terminal",
                "max_rounds": 0,
                "unique_info_states": 8,
                "info_state_repeat_rate": 0.2,
                "final_round": 12,
                "final_phase": "game_over",
                "setup_data_sha256": "abc",
                "initial_state_sha256": "def",
                # "policy_entropy_mean" and "chosen_action_prob_mean" omitted
                # to simulate a phase-1 partial/crashed-game summary.
            }
        ]
        write_summaries(tmp_path, summaries, "run123")
        rows = list(csv.DictReader((tmp_path / "summary.csv").open(encoding="utf-8")))
        assert len(rows) == 1
        assert rows[0]["policy_entropy_mean"] == ""
        assert rows[0]["chosen_action_prob_mean"] == ""
        assert rows[0]["decision_count"] == "10"


class TestWriteSummariesPerSeatColumn:
    def test_num_sims_per_seat_written_as_comma_joined(self, tmp_path):
        summaries = [
            {
                "run_id": "run123",
                "game_index": 0,
                "shuffle_seed": 42,
                "deck_a_id": "a",
                "deck_b_id": "b",
                "num_sims_per_move": 2.75,
                "num_sims_per_seat": [2, 2, 3, 4],
                "uct_c": 1.4,
                "rollout_count": 1,
                "rollout_max_length": None,
                "decision_count": 10,
                "wall_time_sec": 5.0,
                "sims_per_sec_avg": 4.0,
                "moves_per_sec_avg": 2.0,
                "winner": 0,
                "outcome": "p0_win",
                "stopped_reason": "terminal",
                "max_rounds": 0,
                "unique_info_states": 8,
                "info_state_repeat_rate": 0.2,
                "final_round": 12,
                "final_phase": "game_over",
                "setup_data_sha256": "abc",
                "initial_state_sha256": "def",
            }
        ]
        write_summaries(tmp_path, summaries, "run123")
        rows = list(csv.DictReader((tmp_path / "summary.csv").open(encoding="utf-8")))
        assert rows[0]["num_sims_per_seat"] == "2,2,3,4"
