"""Phase 2 (Layer 1) tests: real root-search telemetry in decisions.jsonl.

Implements ``docs/nn-training-data-tdd-plan.md`` § 5. Pure extraction tests are
cheap; the ``requires_c_engine`` tests drive ``run_one_game`` with
``num_sims=4``.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np
import pytest

import openspiel_pyrants  # noqa: F401
from scripts._decision_telemetry import extract_root_stats
from scripts._obs import new_run_id
from scripts.run_ismcts import (
    GameRunFailedError,
    _game_dir,
    _load_game_or_die,
    _resolve_policy,
    _run_one_game_standalone,
    run_one_game,
)

# ── T2.1-T2.3 pure extraction ──────────────────────────────────────────────


def test_root_stats_forced_move_ignores_stale_root() -> None:
    root = SimpleNamespace(
        child_info={0: SimpleNamespace(visits=5, return_sum=1.0)}, total_visits=5
    )
    bot = SimpleNamespace(_root_node=root)

    stats = extract_root_stats(bot, legal_ids=[0])

    assert stats == {
        "visit_counts": {},
        "q_values": {},
        "root_value": None,
        "total_visits": 0,
    }


def test_root_stats_reads_child_info() -> None:
    root = SimpleNamespace(
        child_info={
            0: SimpleNamespace(visits=np.int64(3), return_sum=np.float64(6.0)),
            1: SimpleNamespace(visits=np.int64(0), return_sum=np.float64(0.0)),
            2: SimpleNamespace(visits=np.int64(1), return_sum=np.float64(-2.0)),
        },
        total_visits=np.int64(4),
    )
    bot = SimpleNamespace(_root_node=root)

    stats = extract_root_stats(bot, legal_ids=[0, 1, 2])

    assert stats["visit_counts"] == {0: 3, 1: 0, 2: 1}
    assert stats["q_values"] == {0: 2.0, 2: -2.0}
    assert stats["root_value"] == 1.0
    assert stats["total_visits"] == 4

    # Everything must be a builtin, not a numpy scalar, to be JSON-safe.
    for value in stats["visit_counts"].values():
        assert type(value) is int
    for value in stats["q_values"].values():
        assert type(value) is float
    assert type(stats["root_value"]) is float
    assert type(stats["total_visits"]) is int


def test_root_stats_without_root_attribute() -> None:
    stats = extract_root_stats(SimpleNamespace(), legal_ids=[0, 1, 2, 3])
    assert stats == {
        "visit_counts": {},
        "q_values": {},
        "root_value": None,
        "total_visits": 0,
    }


# ── helpers ────────────────────────────────────────────────────────────────


def _quick_params(tmp_path, **overrides) -> dict:
    params = {
        "game": _load_game_or_die("python_pyrants_c", {"num_players": "2"}),
        "game_index": 0,
        "num_sims": 4,
        "uct_c": 1.4,
        "max_world_samples": 10,
        "final_policy_type": _resolve_policy("visited"),
        "final_policy_name": "visited",
        "seed": 42,
        "shuffle_seed": 42,
        "out_dir": tmp_path,
        "deck_a_id": "deck_a",
        "deck_b_id": "deck_b",
        "show_progress": False,
        "run_id": new_run_id(),
        "rollout_count": 1,
        "rollout_max_length": None,
        "max_rounds": 3,
        "setup_data_json": "",
        "num_players": 2,
    }
    params.update(overrides)
    return params


def _decision_lines(tmp_path, game_index=0) -> list[dict]:
    path = _game_dir(tmp_path, game_index) / "decisions.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]


def _flaky_game(fail_on_call: int = 3):
    game = _load_game_or_die("python_pyrants_c", {"num_players": "2"})
    state = game.new_initial_state()
    counters = {"apply_calls": 0}

    def flaky_apply_action(action) -> None:
        counters["apply_calls"] += 1
        if counters["apply_calls"] == fail_on_call:
            raise RuntimeError("boom")
        state._apply_action(action)

    state.apply_action = flaky_apply_action
    game.new_initial_state = lambda: state
    return game


class _ScriptedBot:
    """Plays the first legal play_card, otherwise the first legal move."""

    def step_with_policy(self, state):
        legal_ids = state.legal_actions()
        chosen_id = None
        for aid in legal_ids:
            if state.decode_action(aid).move_type == "play_card":
                chosen_id = aid
                break
        if chosen_id is None:
            chosen_id = legal_ids[0]
        return [(aid, 1.0 / len(legal_ids)) for aid in legal_ids], chosen_id


def _install_scripted_bot(monkeypatch) -> None:
    from open_spiel.python.algorithms.ismcts import ISMCTSBot

    monkeypatch.setattr(
        ISMCTSBot,
        "step_with_policy",
        lambda self, state: _ScriptedBot().step_with_policy(state),
    )


# ── T2.4 real visits per decision line ─────────────────────────────────────


def test_decision_lines_have_real_visits(requires_c_engine, tmp_path) -> None:
    run_one_game(**_quick_params(tmp_path, run_id="tele"))

    lines = _decision_lines(tmp_path)
    assert lines
    saw_forced = False
    saw_non_forced = False
    for d in lines:
        assert "visit_counts" in d
        assert "q_values" in d
        assert "root_value" in d
        assert "total_visits" in d
        assert "legal_moves_payload" in d

        legal_ids = d["legal_action_ids"]
        vcounts = {int(k): int(v) for k, v in d["visit_counts"].items()}
        qvals = {int(k): float(v) for k, v in d["q_values"].items()}
        policy = {int(k): float(v) for k, v in d["policy"].items()}

        if len(legal_ids) <= 1:
            saw_forced = True
            assert vcounts == {}
            assert qvals == {}
            assert d["root_value"] is None
            assert d["total_visits"] == 0
            continue

        saw_non_forced = True
        assert set(vcounts) == set(legal_ids)
        assert sum(vcounts.values()) == d["total_visits"] == d["sims_requested"] - 1
        assert set(qvals) == {a for a, v in vcounts.items() if v > 0}
        for aid, visits in vcounts.items():
            assert policy[aid] == pytest.approx(visits / d["total_visits"])
        expected_root = sum(v * qvals.get(a, 0.0) for a, v in vcounts.items()) / d["total_visits"]
        assert d["root_value"] == pytest.approx(expected_root)

    assert saw_forced and saw_non_forced


# ── T2.5 legal payloads align with the replay ──────────────────────────────


def test_legal_moves_payload_aligns_with_replay(requires_c_engine, tmp_path) -> None:
    run_one_game(**_quick_params(tmp_path, run_id="align"))

    game_out = _game_dir(tmp_path, 0)
    replay_log = json.loads((game_out / "replay.json").read_text(encoding="utf-8"))["replay_log"]
    by_node = {entry["step_index"]: entry for entry in replay_log}

    lines = _decision_lines(tmp_path)
    for d in lines:
        payloads = d["legal_moves_payload"]
        assert len(payloads) == len(d["legal_action_ids"])
        index = d["legal_action_ids"].index(d["chosen_action_id"])
        assert payloads[index] == by_node[d["node"]]["payload"]


# ── T2.6 pending_context iff a generic choice is pending ───────────────────


def test_pending_context_present_iff_generic_choice_pending(
    requires_c_engine, tmp_path, monkeypatch
) -> None:
    _install_scripted_bot(monkeypatch)
    run_one_game(**_quick_params(tmp_path, run_id="pending", max_rounds=6))

    lines = _decision_lines(tmp_path)
    assert lines
    for d in lines:
        has_generic = any(
            p.get("move_type") == "resolve_generic" for p in d["legal_moves_payload"]
        )
        if has_generic:
            assert "pending_context" in d, d
            ctx = d["pending_context"]
            assert set(ctx) == {
                "source_card_id",
                "op",
                "card_action_id",
                "current_option_id",
                "awaiting_option",
                "optional",
            }
            if "generic" in d:
                assert ctx["source_card_id"] == d["generic"]["source_card_id"]
        else:
            assert "pending_context" not in d, d


# ── T2.7 the stub is gone ──────────────────────────────────────────────────


def test_stub_is_gone(requires_c_engine, tmp_path) -> None:
    run_one_game(**_quick_params(tmp_path, run_id="nostub"))

    for d in _decision_lines(tmp_path):
        if len(d["legal_action_ids"]) > 1:
            assert len(d["visit_counts"]) != 1


# ── T2.8 --no-steps skips steps.jsonl but keeps failures.jsonl ─────────────


def test_no_steps_flag_skips_steps_jsonl(requires_c_engine, tmp_path) -> None:
    run_one_game(**_quick_params(tmp_path, run_id="nosteps", write_steps=False))

    game_out = _game_dir(tmp_path, 0)
    assert not (game_out / "steps.jsonl").exists()
    assert (game_out / "decisions.jsonl").exists()


def test_no_steps_crash_still_records_failure(requires_c_engine, tmp_path, monkeypatch) -> None:
    game = _flaky_game()
    monkeypatch.setattr(
        "scripts.run_ismcts._load_game_or_die", lambda name, params: game
    )

    with pytest.raises(GameRunFailedError):
        _run_one_game_standalone(
            game_index=0,
            num_sims=4,
            uct_c=1.4,
            max_world_samples=10,
            final_policy_name="visited",
            seed=42,
            shuffle_seed=42,
            output_dir=str(tmp_path),
            run_id="nosteps_crash",
            num_players=2,
            max_rounds=15,
            write_steps=False,
        )

    assert not (_game_dir(tmp_path, 0) / "steps.jsonl").exists()
    assert (tmp_path / "failures.jsonl").exists()
