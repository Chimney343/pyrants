"""Crash-safety tests for the IS-MCTS runner (scripts/run_ismcts.py).

Phase 1 of the IS-MCTS observability work: the per-game ``steps.jsonl`` and
``decisions.jsonl`` files must be written *streaming* (line-by-line, flushed
immediately) rather than batch-dumped when the game loop exits, and a
mid-loop exception must degrade gracefully into ``GameRunFailedError``
carrying a partial ``game_summary`` instead of losing every artifact or
taking the whole process down.

The games here run with ``num_sims=2`` (a few seconds each) and are driven
directly against ``run_one_game()`` / the single-worker ``main()`` branch.
"""

from __future__ import annotations

import json
import pickle
from concurrent.futures import ProcessPoolExecutor

import pytest

import openspiel_pyrants  # noqa: F401
from scripts._obs import new_run_id
from scripts.run_ismcts import (
    GameRunFailedError,
    _game_dir,
    _load_game_or_die,
    _resolve_policy,
    _run_one_game_standalone,
    main,
    run_one_game,
)

# How many total apply_action calls happen before the first player move:
# 1 (initial shuffle chance node) + 1 (first move) = 2.
_CHANCE_AND_FIRST_MOVE_CALLS = 2


def _raise_game_run_failed_from_worker() -> None:
    """Module-level so a spawned ProcessPoolExecutor worker can import it by
    reference (functions are pickled by name, not by value)."""
    raise GameRunFailedError(
        {"decision_count": 1, "stopped_reason": "error"},
        {"exception_type": "RuntimeError", "exception_message": "simulated demon bite"},
    )


class TestGameRunFailedErrorIsPicklable:
    """GameRunFailedError crosses process boundaries: _run_one_game_standalone
    re-raises it inside a worker process, and ProcessPoolExecutor (the
    --workers > 1 path, the default for `just ismcts`) pickles exceptions to
    hand them back to the parent via future.result(). __init__ previously
    forwarded only game_summary to Exception.__init__, so self.args was
    missing crash_record and the default unpickle — which reconstructs via
    ``cls(*self.args)`` — raised TypeError. That TypeError killed the worker
    process, which poisoned the whole pool: every other in-flight/pending
    future failed with BrokenProcessPool, even games that never crashed.
    """

    def test_pickle_round_trip_preserves_game_summary_and_crash_record(self):
        exc = GameRunFailedError(
            {"decision_count": 3, "stopped_reason": "error"},
            {"exception_type": "RuntimeError", "exception_message": "boom"},
        )
        restored = pickle.loads(pickle.dumps(exc))
        assert restored.game_summary == exc.game_summary
        assert restored.crash_record == exc.crash_record

    def test_survives_process_pool_executor_boundary(self):
        with ProcessPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_raise_game_run_failed_from_worker)
            with pytest.raises(GameRunFailedError) as excinfo:
                future.result()

        assert excinfo.value.crash_record["exception_type"] == "RuntimeError"
        assert excinfo.value.crash_record["exception_message"] == "simulated demon bite"
        assert excinfo.value.game_summary["decision_count"] == 1


def _quick_params(tmp_path, game_index=0, num_players=2, **overrides) -> dict:
    params = {
        "game": _load_game_or_die("python_pyrants_c", {"num_players": str(num_players)}),
        "game_index": game_index,
        "num_sims": 2,
        "uct_c": 1.4,
        "max_world_samples": 10,
        "final_policy_type": _resolve_policy("visited"),
        "final_policy_name": "visited",
        "seed": 42,
        "shuffle_seed": 42 + game_index,
        "out_dir": tmp_path,
        "deck_a_id": "deck_a",
        "deck_b_id": "deck_b",
        "show_progress": False,
        "run_id": new_run_id(),
        "rollout_count": 1,
        "rollout_max_length": None,
        "max_rounds": 15,
        "setup_data_json": "",
        "num_players": num_players,
    }
    params.update(overrides)
    return params


def _flaky_game(game, state, counters, fail_on_call):
    """Install an apply_action wrapper that raises on the Nth total call.

    apply_action is called once for the initial shuffle chance node and once
    per move.  ``counters`` is a shared dict mutated by the wrapper.
    """
    def flaky_apply_action(action) -> None:
        counters["apply_calls"] += 1
        if counters["apply_calls"] == fail_on_call:
            raise RuntimeError("simulated demon bite")
        state._apply_action(action)
        if counters["apply_calls"] > 1:  # skip the initial chance-node apply
            counters["move_applies_succeeded"] += 1

    state.apply_action = flaky_apply_action
    game.new_initial_state = lambda: state
    return state


def _load_flaky_game(fail_on_call, counters):
    game = _load_game_or_die("python_pyrants_c", {"num_players": "2"})
    state = game.new_initial_state()
    counters["apply_calls"] = 0
    counters["move_applies_succeeded"] = 0
    _flaky_game(game, state, counters, fail_on_call)
    return game


def _steps_lines(game_out) -> list[dict]:
    steps_path = game_out / "steps.jsonl"
    if not steps_path.exists():
        return []
    return [json.loads(line) for line in steps_path.open(encoding="utf-8")]


def _decisions_lines(game_out) -> list[dict]:
    decisions_path = game_out / "decisions.jsonl"
    if not decisions_path.exists():
        return []
    return [json.loads(line) for line in decisions_path.open(encoding="utf-8")]


def _read_failures(out_dir) -> list[dict]:
    failures_path = out_dir / "failures.jsonl"
    if not failures_path.exists():
        return []
    return [json.loads(line) for line in failures_path.open(encoding="utf-8")]


# Every field the phase-3 structured crash record must surface in the
# failures.jsonl line, merged additively into the base shape
# {run_id, game_index, worker_pid, error}.  Both the single-worker (main()
# workers==1) and multi-worker (_run_one_game_standalone) paths must produce
# the identical key set.
_FAILURE_KEYS = {
    "run_id", "game_index", "worker_pid", "error",
    "exception_type", "exception_message", "traceback",
    "step_index", "attempted_move_type", "attempted_move_label", "attempted_payload",
    "pending_card_id", "phase_at_failure", "round_number_at_failure",
    "current_player_at_failure", "is_terminal_at_failure",
    "legal_moves_count_at_failure", "legal_moves_at_failure",
}


def _assert_failure_keys(line: dict) -> None:
    for key in _FAILURE_KEYS:
        assert key in line, f"missing failures.jsonl key {key!r} in {sorted(line)}"


class TestStreamingStepsJsonl:
    def test_steps_written_during_run_not_batch_dumped(self, requires_c_engine, tmp_path):
        """steps.jsonl must be written line-by-line while the game runs.

        The proxy apply_action checks the file on the second move's apply; by
        then the first move's ``"step"`` line must already be on disk (flushed)
        even though the game is far from over.
        """
        game_out = _game_dir(tmp_path, 0)
        game = _load_game_or_die("python_pyrants_c", {"num_players": "2"})
        state = game.new_initial_state()
        counters = {"apply_calls": 0}
        seen_steps = []

        orig_apply = state._apply_action

        def probing_apply_action(action) -> None:
            counters["apply_calls"] += 1
            orig_apply(action)
            # On the second move's apply the first move's step line must
            # already be flushed to disk.
            if counters["apply_calls"] == _CHANCE_AND_FIRST_MOVE_CALLS + 1:
                steps_path = game_out / "steps.jsonl"
                if steps_path.exists():
                    seen_steps.extend(
                        json.loads(line)
                        for line in steps_path.open(encoding="utf-8")
                    )

        state.apply_action = probing_apply_action
        game.new_initial_state = lambda: state

        params = _quick_params(tmp_path, max_rounds=15)
        params["game"] = game
        summary = run_one_game(**params)
        assert summary["decision_count"] > 0

        steps = _steps_lines(game_out)
        assert len(seen_steps) == 1
        assert seen_steps[0]["event"] == "step"
        assert steps[-1]["event"] == "game_end"
        assert len([s for s in steps if s["event"] == "step"]) == summary["decision_count"]

    def test_steps_are_flushed_line_by_line(self, requires_c_engine, tmp_path):
        """Each step line must be a complete, valid JSON object on its own."""
        params = _quick_params(tmp_path, max_rounds=15)
        run_one_game(**params)

        game_out = _game_dir(tmp_path, 0)
        steps = _steps_lines(game_out)
        assert len(steps) > 1
        for line in steps:
            assert isinstance(line, dict)
            assert "event" in line
            assert isinstance(line["event"], str)

        decisions = _decisions_lines(game_out)
        assert len(decisions) == len([s for s in steps if s["event"] == "step"])


class TestGameRunFailedError:
    def test_exception_raises_game_run_failed_with_partial_artifacts(
        self, requires_c_engine, tmp_path
    ):
        """A mid-loop exception must raise GameRunFailedError, keep the prior
        steps on disk, record the failed decision, and write a partial summary.
        """
        fail_on_call = _CHANCE_AND_FIRST_MOVE_CALLS + 1  # first move ok, 2nd raises
        counters = {}
        game = _load_flaky_game(fail_on_call, counters)

        params = _quick_params(tmp_path, max_rounds=100)
        params["game"] = game

        with pytest.raises(GameRunFailedError) as excinfo:
            run_one_game(**params)

        exc = excinfo.value
        assert isinstance(exc.crash_record, dict)
        assert exc.crash_record["exception_type"] == "RuntimeError"
        assert exc.crash_record["exception_message"] == "simulated demon bite"

        summary = exc.game_summary
        assert isinstance(summary, dict)
        assert summary["stopped_reason"] == "error"
        assert summary["decision_count"] == 1  # one move applied before the crash

        game_out = _game_dir(tmp_path, 0)
        steps = _steps_lines(game_out)
        step_events = [s["event"] for s in steps]
        assert step_events == ["step", "game_crashed"]

        decisions = _decisions_lines(game_out)
        assert len(decisions) == 2  # 2 decisions made; applying the 2nd failed

    def test_original_exception_is_chained(self, requires_c_engine, tmp_path):
        fail_on_call = _CHANCE_AND_FIRST_MOVE_CALLS  # first move apply raises
        counters = {}
        game = _load_flaky_game(fail_on_call, counters)

        params = _quick_params(tmp_path, max_rounds=100)
        params["game"] = game

        with pytest.raises(GameRunFailedError) as excinfo:
            run_one_game(**params)

        assert isinstance(excinfo.value.__cause__, RuntimeError)
        assert str(excinfo.value.__cause__) == "simulated demon bite"

    def test_partial_summary_has_base_fields(self, requires_c_engine, tmp_path):
        fail_on_call = _CHANCE_AND_FIRST_MOVE_CALLS  # first move apply raises
        counters = {}
        game = _load_flaky_game(fail_on_call, counters)

        params = _quick_params(tmp_path, max_rounds=100, run_id="crash_run")
        params["game"] = game

        with pytest.raises(GameRunFailedError) as excinfo:
            run_one_game(**params)

        summary = excinfo.value.game_summary
        for key in (
            "run_id", "game_index", "shuffle_seed", "deck_a_id", "deck_b_id",
            "num_players", "num_sims_per_move", "uct_c", "rollout_count",
            "rollout_max_length", "policy_type", "decision_count", "wall_time_sec",
        ):
            assert key in summary, f"missing base key {key} in partial summary"

        assert summary["run_id"] == "crash_run"
        assert summary["decision_count"] == 0

    def test_partial_summary_omits_uncomputable_fields(self, requires_c_engine, tmp_path):
        """Fields that need a terminal state must not be fabricated."""
        fail_on_call = _CHANCE_AND_FIRST_MOVE_CALLS  # first move apply raises
        counters = {}
        game = _load_flaky_game(fail_on_call, counters)

        params = _quick_params(tmp_path, max_rounds=100)
        params["game"] = game

        with pytest.raises(GameRunFailedError) as excinfo:
            run_one_game(**params)

        summary = excinfo.value.game_summary
        for key in (
            "returns", "winner", "outcome", "final_scores_per_player",
            "policy_entropy_mean", "policy_entropy_max",
            "chosen_action_prob_mean", "chosen_action_prob_p50",
            "chosen_action_prob_p90", "move_latency_ms",
        ):
            assert key not in summary, f"uncomputable key {key} present in partial summary"


class TestSingleWorkerContinue:
    def test_main_workers1_survives_crash_and_continues(self, requires_c_engine, tmp_path, monkeypatch):
        """main()'s workers==1 branch must catch GameRunFailedError per game,
        record the failure in metrics, and continue to the next game."""
        import sys

        crash_at_game = 1
        counters = {"game_index": 0}

        # Patch _load_game_or_die to return a state that crashes on the Nth
        # apply_action call for game 1 only.
        original_load = _load_game_or_die

        def patched_load(name, params):
            game = original_load(name, params)
            gi = counters["game_index"]
            if gi == crash_at_game:
                state = game.new_initial_state()
                fail_on_call = _CHANCE_AND_FIRST_MOVE_CALLS  # first move apply raises
                ctr = {"apply_calls": 0, "move_applies_succeeded": 0}

                def flaky_apply(action) -> None:
                    ctr["apply_calls"] += 1
                    if ctr["apply_calls"] == fail_on_call:
                        raise RuntimeError("simulated demon bite")
                    state._apply_action(action)

                state.apply_action = flaky_apply
                game.new_initial_state = lambda: state
            return game

        monkeypatch.setattr("scripts.run_ismcts._load_game_or_die", patched_load)

        monkeypatch.setattr(
            "scripts.run_ismcts.new_run_id", lambda: "single_worker_crash_test"
        )

        args = {
            "--num-sims": 2,
            "--uct-c": 1.4,
            "--max-world-samples": 10,
            "--final-policy": "visited",
            "--num-games": 3,
            "--seed": 42,
            "--num-players": 2,
            "--game": "python_pyrants_c",
            "--output-dir": str(tmp_path),
            "--shuffle-seed": 0,
            "--workers": 1,
            "--log-level": "WARNING",
            "--json-logs": False,
            "--worker-log-level": "WARNING",
            "--rollout-count": 1,
            "--rollout-max-length": 0,
            "--max-rounds": 15,
        }

        argv = ["run_ismcts", "--no-plots"]
        for k, v in args.items():
            if isinstance(v, bool):
                argv.append(k)  # store_true flags take no value
            else:
                argv.append(f"{k}={v}")

        monkeypatch.setattr(sys, "argv", argv)

        # Override the per-game counters so the crash lands on game 1.
        import scripts.run_ismcts as runner

        orig_build = runner._build_ismcts_setup_json
        call_count = {"n": 0}

        def counting_build(*a, **kw):
            result = orig_build(*a, **kw)
            counters["game_index"] = call_count["n"]
            call_count["n"] += 1
            return result

        monkeypatch.setattr(runner, "_build_ismcts_setup_json", counting_build)

        main()

        summaries = _read_summaries(tmp_path)
        assert len(summaries) == 3
        by_index = {s["game_index"]: s for s in summaries}
        assert by_index[1]["stopped_reason"] == "error"
        assert by_index[0]["stopped_reason"] in ("terminal", "round_cap")
        assert by_index[2]["stopped_reason"] in ("terminal", "round_cap")

        metrics = json.loads((tmp_path / "metrics.json").read_text(encoding="utf-8"))
        assert metrics["counters"]["games_failed"] == 1
        assert metrics["counters"]["games_completed"] == 2

        assert (tmp_path / "summary.csv").exists()
        assert (tmp_path / "summary.md").exists()

        # The crashed game's steps.jsonl must show step + game_crashed.
        crashed_steps = _steps_lines(_game_dir(tmp_path, 1))
        assert crashed_steps[-1]["event"] == "game_crashed"

        # The single-worker path must write the same structured failures.jsonl
        # line the multi-worker path writes (phase 3).
        failures = _read_failures(tmp_path)
        assert len(failures) == 1
        failure = failures[0]
        assert failure["game_index"] == crash_at_game
        assert failure["worker_pid"] is None
        assert failure["run_id"] == "single_worker_crash_test"
        _assert_failure_keys(failure)


class TestFailuresJsonlStructuredFields:
    def test_standalone_worker_writes_structured_failures_jsonl(
        self, requires_c_engine, tmp_path, monkeypatch
    ):
        """The multi-worker path (_run_one_game_standalone) must write the
        structured failures.jsonl line via record_game_failure, carrying the
        same keys as the single-worker path (phase 3)."""
        counters = {}
        game = _load_flaky_game(_CHANCE_AND_FIRST_MOVE_CALLS, counters)
        monkeypatch.setattr(
            "scripts.run_ismcts._load_game_or_die", lambda name, params: game
        )

        with pytest.raises(GameRunFailedError):
            _run_one_game_standalone(
                game_index=3,
                num_sims=2,
                uct_c=1.4,
                max_world_samples=10,
                final_policy_name="visited",
                seed=42,
                shuffle_seed=45,
                output_dir=str(tmp_path),
                run_id="standalone_crash",
                num_players=2,
                max_rounds=15,
            )

        failures = _read_failures(tmp_path)
        assert len(failures) == 1
        line = failures[0]
        assert line["run_id"] == "standalone_crash"
        assert line["game_index"] == 3
        assert line["worker_pid"] is not None
        assert line["exception_type"] == "RuntimeError"
        assert line["exception_message"] == "simulated demon bite"
        _assert_failure_keys(line)


def _read_summaries(out_dir) -> list[dict]:
    import csv as _csv

    csv_path = out_dir / "summary.csv"
    if not csv_path.exists():
        return []
    rows = []
    with csv_path.open(encoding="utf-8", newline="") as f:
        for row in _csv.DictReader(f):
            row["game_index"] = int(row["game_index"])
            rows.append(row)
    return rows
