"""Phase 4 tests — the NN dataset builder."""

from __future__ import annotations

import json
import random
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

import openspiel_pyrants  # noqa: F401
from interface.replay_loader import load_replay
from interface.replay_player import ReplayDesyncError
from openspiel_pyrants.nn.actions import NUM_GLOBAL_ACTIONS
from openspiel_pyrants.nn.dataset import Sample, load_shard, write_shards
from openspiel_pyrants.nn.observation import OBS_SIZE
from openspiel_pyrants.nn.targets import value_targets
from scripts._nn_dataset import (
    AlignmentError,
    iter_samples,
    report_metrics,
    validate_game_dir,
)
from scripts._obs import new_run_id
from scripts.run_ismcts import _game_dir, _load_game_or_die, _resolve_policy, run_one_game

ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "data" / "boards" / "tyrants_of_the_underdark.json"
CARDS = ROOT / "data" / "cards"
SETUP = ROOT / "data" / "decks" / "base_setup.json"


def _quick_params(tmp_path, num_players=2, num_sims=4, max_rounds=4, **overrides) -> dict:
    params = {
        "game": _load_game_or_die("python_pyrants_c", {"num_players": str(num_players)}),
        "game_index": 0,
        "num_sims": num_sims,
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
        "max_rounds": max_rounds,
        "setup_data_json": "",
        "num_players": num_players,
    }
    params.update(overrides)
    return params


def _make_game(tmp_path, **kwargs) -> Path:
    run_one_game(**_quick_params(tmp_path, **kwargs))
    return _game_dir(tmp_path, 0)


def _write_synthetic_game(
    game_dir: Path,
    *,
    run_id: str = "r1",
    schema_version: int | None = 2,
    stopped_reason: str = "terminal",
    step_count: int = 1,
    decision_count: int = 1,
    setup_sha: str = "",
    summary: bool = True,
) -> None:
    game_dir.mkdir(parents=True, exist_ok=True)
    replay = {
        "run_id": run_id,
        "stopped_reason": stopped_reason,
        "step_count": step_count,
        "is_terminal": stopped_reason == "terminal",
        "winner_id": None,
        "final_scores": {},
        "replay_log": [],
        "replay_context": {
            "board_path": str(BOARD),
            "card_path": str(CARDS),
            "setup_path": str(SETUP),
            "player_ids": ["p1", "p2"],
            "seed": 42,
            "deck_a_id": "drow",
            "deck_b_id": "dragon",
        },
    }
    if schema_version is not None:
        replay["schema_version"] = schema_version
    (game_dir / "replay.json").write_text(json.dumps(replay), encoding="utf-8")
    (game_dir / "decisions.jsonl").write_text(
        "".join(json.dumps({"run_id": run_id, "node": i}) + "\n" for i in range(decision_count)),
        encoding="utf-8",
    )
    if summary:
        (game_dir / "summary.json").write_text(
            json.dumps({
                "run_id": run_id,
                "stopped_reason": stopped_reason,
                "setup_data_sha256": setup_sha,
            }),
            encoding="utf-8",
        )


# ── T4.1 validation ────────────────────────────────────────────────────────


def test_validate_rejects_bad_dirs(tmp_path) -> None:
    missing = tmp_path / "missing"
    _write_synthetic_game(missing, summary=False)
    check = validate_game_dir(missing, allow_legacy=True)
    assert not check.ok
    assert "missing summary" in check.reasons

    nonterminal = tmp_path / "nonterminal"
    _write_synthetic_game(nonterminal, stopped_reason="round_cap")
    check = validate_game_dir(nonterminal, allow_legacy=True)
    assert not check.ok
    assert any("round_cap" in r for r in check.reasons)

    mismatch = tmp_path / "mismatch"
    _write_synthetic_game(mismatch, run_id="A")
    (mismatch / "decisions.jsonl").write_text(
        json.dumps({"run_id": "B", "node": 0}) + "\n", encoding="utf-8"
    )
    (mismatch / "summary.json").write_text(
        json.dumps({"run_id": "B", "stopped_reason": "terminal", "setup_data_sha256": ""}),
        encoding="utf-8",
    )
    check = validate_game_dir(mismatch, allow_legacy=True)
    assert not check.ok
    assert "run_id mismatch" in check.reasons

    count = tmp_path / "count"
    _write_synthetic_game(count, step_count=5, decision_count=1)
    check = validate_game_dir(count, allow_legacy=True)
    assert not check.ok
    assert "decision count mismatch" in check.reasons

    sha = tmp_path / "sha"
    _write_synthetic_game(sha, setup_sha="deadbeefdeadbeef")
    check = validate_game_dir(sha, allow_legacy=True)
    assert not check.ok
    assert "setup sha mismatch" in check.reasons

    legacy = tmp_path / "legacy"
    _write_synthetic_game(legacy, schema_version=None)
    check = validate_game_dir(legacy, allow_legacy=False)
    assert not check.ok
    assert "legacy schema" in check.reasons
    assert validate_game_dir(legacy, allow_legacy=True).ok


def test_validate_accepts_fresh_v2_game(requires_c_engine, tmp_path) -> None:
    game_dir = _make_game(tmp_path, num_players=2, num_sims=2, max_rounds=0)
    check = validate_game_dir(game_dir, allow_legacy=False)
    assert check.ok, check.reasons
    assert check.schema_version == 2
    assert check.run_id


# ── T4.2 alignment assert ──────────────────────────────────────────────────


def test_alignment_assert_fires(requires_c_engine, tmp_path) -> None:
    game_dir = _make_game(tmp_path, num_players=2, num_sims=2, max_rounds=4)
    decisions_path = game_dir / "decisions.jsonl"
    lines = [json.loads(line) for line in decisions_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    target = next((d for d in lines if len(d.get("legal_moves_payload", [])) >= 2), None)
    assert target is not None
    payloads = target["legal_moves_payload"]
    payloads[0], payloads[1] = payloads[1], payloads[0]
    decisions_path.write_text(
        "".join(json.dumps(d) + "\n" for d in lines), encoding="utf-8"
    )

    bundle = load_replay(game_dir)
    with pytest.raises(AlignmentError) as excinfo:
        list(iter_samples(bundle, allow_legacy=False, keep_forced=True))
    assert excinfo.value.node == target["node"]


# ── T4.3 tiny end-to-end ───────────────────────────────────────────────────


@pytest.mark.parametrize("num_players", [2, 4])
def test_tiny_end_to_end(requires_c_engine, tmp_path, num_players) -> None:
    game_dir = _make_game(tmp_path, num_players=num_players, num_sims=4, max_rounds=4)
    assert validate_game_dir(game_dir, allow_legacy=False).ok
    bundle = load_replay(game_dir)

    samples_all = list(iter_samples(bundle, allow_legacy=False, keep_forced=True))
    samples_default = list(iter_samples(bundle, allow_legacy=False, keep_forced=False))
    assert len(samples_default) == sum(1 for s in samples_all if not s.forced)
    assert samples_all

    final_scores = bundle.replay["final_scores"]
    player_ids = list(bundle.meta.player_ids)
    for s in samples_all:
        assert s.obs.dtype == np.int16
        assert s.obs.shape == (OBS_SIZE,)
        assert all(0 <= g < NUM_GLOBAL_ACTIONS for g in s.legal_ids)
        assert s.chosen_gid in s.legal_ids
        assert sum(s.legal_visits) == s.total_visits
        order = player_ids[s.acting_seat:] + player_ids[:s.acting_seat]
        assert s.final_scores[0] == float(final_scores.get(order[0], 0))
        assert sum(s.seat_mask) == num_players
        assert s.phase
        assert s.move_type
        assert s.sims_requested > 0
        assert s.n_legal_raw >= len(s.legal_ids)


# ── T2.5 (R-1) seat_features slot 0 and final_scores[0] are one player ─────


def _acting_player_current_scores(bundle) -> list[int]:
    """Drive a fresh adapter through the replay, returning the acting player's
    public ``score`` at each pre-move state (aligned with ``iter_samples``)."""
    from engine_c.bindings.c_adapter import CEngineAdapter
    from engine_c.bindings.ce_api import CEngine
    from interface.replay_loader import engine_seed

    engine = CEngine()
    engine.initialize(
        catalog_path=str(bundle.card_path),
        board_path=str(bundle.board_path),
        setup_path=str(bundle.setup_path),
        setup_data_json=bundle.setup_json,
    )
    player_ids = list(bundle.meta.player_ids)
    seed = engine_seed(bundle.meta.shuffle_seed)
    adapter = CEngineAdapter(engine.create_game(player_ids, seed), engine, player_ids, seed)
    log = [
        e
        for e in bundle.replay.get("replay_log", ())
        if e.get("payload", {}).get("move_type") != "__terminal__"
    ]
    scores: list[int] = []
    try:
        for entry in log:
            cp = entry.get("player_id") or adapter.state.current_player_id
            view = json.loads(adapter.private_view_json(cp))
            summary = view["public"]["public_player_summaries"].get(cp, {})
            scores.append(int(summary.get("score", 0)))
            match = next(
                (m for m in adapter.legal_moves() if m.to_payload() == entry["payload"]),
                None,
            )
            assert match is not None
            adapter.apply(match)
    finally:
        adapter.destroy()
    return scores


def test_value_target_and_seat_features_agree_on_seat_zero(
    requires_c_engine, tmp_path
) -> None:
    """T2.5 (R-1): ``seat_features`` slot 0's ``score`` and ``final_scores[0]``
    both belong to the acting player, because both rotate through ``seat_order``."""
    from openspiel_pyrants.nn.observation import OBS_LAYOUT

    game_dir = _make_game(tmp_path, num_players=4, num_sims=4, max_rounds=6)
    bundle = load_replay(game_dir)
    samples = list(iter_samples(bundle, allow_legacy=False, keep_forced=True))
    scores = _acting_player_current_scores(bundle)
    assert len(samples) == len(scores)

    final_scores = bundle.replay["final_scores"]
    player_ids = list(bundle.meta.player_ids)
    seat_start = OBS_LAYOUT["seat_features"][0]
    for sample, score in zip(samples, scores, strict=True):
        acting_pid = player_ids[sample.acting_seat]
        assert int(sample.obs[seat_start]) == score
        assert sample.final_scores[0] == float(final_scores.get(acting_pid, 0))


# ── T4.4 legacy mode reproduces v2 targets ─────────────────────────────────

def test_legacy_mode_reproduces_v2_targets(requires_c_engine, tmp_path) -> None:
    v2_dir = _make_game(tmp_path / "v2", num_players=4, num_sims=4, max_rounds=4)
    legacy_dir = tmp_path / "legacy" / "game_0000"
    shutil.copytree(v2_dir, legacy_dir)

    replay_path = legacy_dir / "replay.json"
    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    replay.pop("schema_version", None)
    replay_path.write_text(json.dumps(replay), encoding="utf-8")

    strip_keys = {
        "visit_counts", "q_values", "root_value", "total_visits",
        "legal_moves_payload", "pending_context",
    }
    decisions = []
    for line in (legacy_dir / "decisions.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        for key in strip_keys:
            d.pop(key, None)
        decisions.append(d)
    (legacy_dir / "decisions.jsonl").write_text(
        "".join(json.dumps(d) + "\n" for d in decisions), encoding="utf-8"
    )

    assert "legacy schema" in validate_game_dir(legacy_dir, allow_legacy=False).reasons

    v2_samples = list(iter_samples(load_replay(v2_dir), allow_legacy=False, keep_forced=True))
    legacy_samples = list(iter_samples(load_replay(legacy_dir), allow_legacy=True, keep_forced=True))
    assert len(v2_samples) == len(legacy_samples)
    for a, b in zip(v2_samples, legacy_samples, strict=True):
        assert a.legal_ids == b.legal_ids
        assert a.legal_visits == b.legal_visits
        assert np.array_equal(a.obs, b.obs)


# ── T4.5 shards round trip ─────────────────────────────────────────────────
def _synthetic_samples(n: int = 5) -> list[Sample]:
    samples = []
    for i in range(n):
        samples.append(Sample(
            obs=np.full(OBS_SIZE, i, dtype=np.int16),
            legal_ids=[i, i + 1],
            legal_visits=[3, 2],
            legal_q=[0.5, -0.5],
            chosen_gid=i,
            root_value=0.1 * i,
            total_visits=5,
            forced=False,
            final_scores=[10.0 * i, -10.0 * i, 0.0, 0.0],
            seat_mask=[True, True, False, False],
            acting_seat=0,
            num_players=2,
            sims_requested=200,
            uct_c=1.4,
            game_idx=0,
            node=i,
            phase="main",
            move_type="play_card",
        ))
    return samples


def test_shards_round_trip(tmp_path) -> None:
    samples = _synthetic_samples(5)
    manifest = write_shards(
        samples, tmp_path, dataset_id="ds", shard_size=3, sources={"runs": []}
    )

    assert manifest["counts"]["samples"] == 5
    assert len(manifest["shards"]) == 2
    assert sum(s["rows"] for s in manifest["shards"]) == 5
    assert manifest["encoder_version"] and manifest["action_space_version"]
    assert manifest["card_index_sha"] and manifest["node_index_sha"]
    assert manifest["pair_move_merge_frac"] is None or isinstance(
        manifest["pair_move_merge_frac"], float
    )

    row = 0
    for shard in manifest["shards"]:
        data = load_shard(tmp_path / shard["file"])
        assert data["obs"].dtype == np.float32
        assert data["meta"]["legal_row_ptr"][-1] == len(data["meta"]["legal_ids"])
        assert data["meta"]["n_legal_raw"].shape == (len(data["obs"]),)
        for i in range(data["obs"].shape[0]):
            assert data["policy"][i].sum() == pytest.approx(1.0)
            assert data["value"][i] == pytest.approx(
                value_targets(samples[row].final_scores, 2), abs=1e-6
            )
            assert data["weight"][i] == pytest.approx(1.0)
            row += 1
    assert row == 5


def test_manifest_records_index_shas(tmp_path) -> None:
    """T4.2 (m2): both catalog-derived index SHAs are recorded."""
    from openspiel_pyrants.nn.index import EFFECT_INDEX_SHA, OP_INDEX_SHA

    manifest = write_shards(
        _synthetic_samples(2), tmp_path, dataset_id="ds", shard_size=10, sources={}
    )
    assert manifest["op_index_sha"] == OP_INDEX_SHA
    assert manifest["effect_index_sha"] == EFFECT_INDEX_SHA
    on_disk = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert on_disk["op_index_sha"] == OP_INDEX_SHA
    assert on_disk["effect_index_sha"] == EFFECT_INDEX_SHA


def test_write_shards_records_sources(tmp_path) -> None:
    """T1.2 / F-028: the manifest records its sources as a dict, not key names."""
    sources = {
        "runs": [
            {
                "path": "/runs/abc",
                "run_id": "abc",
                "engine_git_sha": "a" * 40,
                "engine_dll_sha256": "b" * 64,
            }
        ],
        "accepted": [{"game_dir": "/runs/abc/game_0000", "run_id": "abc", "samples": 3}],
        "rejected": [
            {
                "game_dir": "/runs/abc/game_0001",
                "run_id": "abc",
                "reasons": ["stopped_reason='round_cap'"],
            }
        ],
    }
    manifest = write_shards(
        _synthetic_samples(2), tmp_path, dataset_id="ds", shard_size=10, sources=sources
    )
    assert isinstance(manifest["sources"], dict)
    assert manifest["sources"]["runs"][0]["run_id"] == "abc"
    assert manifest["sources"]["accepted"][0]["game_dir"] == "/runs/abc/game_0000"
    assert manifest["sources"]["rejected"][0]["reasons"] == ["stopped_reason='round_cap'"]
    on_disk = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert on_disk["sources"] == sources


# ── T4.6 desync reported, not silent ───────────────────────────────────────


def test_desync_is_reported_not_silent(requires_c_engine, tmp_path, monkeypatch) -> None:
    run_dir = tmp_path / "run"
    game_dir = _make_game(run_dir, num_players=2, num_sims=2, max_rounds=0)
    replay_path = game_dir / "replay.json"
    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    for entry in replay["replay_log"]:
        if entry.get("move_type") != "__terminal__":
            entry["payload"] = {"move_type": "play_card", "card_id": "not_a_card"}
            break
    replay_path.write_text(json.dumps(replay), encoding="utf-8")

    with pytest.raises(ReplayDesyncError):
        list(iter_samples(load_replay(game_dir), allow_legacy=False, keep_forced=True))

    import scripts.build_nn_dataset as cli

    out = tmp_path / "ds"
    monkeypatch.setattr(sys, "argv", [
        "build_nn_dataset",
        "--runs", str(run_dir),
        "--out", str(out),
    ])
    assert cli.main() == 0
    rejected = (out / "rejected.jsonl").read_text(encoding="utf-8")
    assert "ReplayDesyncError" in rejected


# ── T4.7 builder leak check ────────────────────────────────────────────────


def test_builder_leak_check(requires_c_engine, tmp_path) -> None:
    game_dir = _make_game(tmp_path, num_players=2, num_sims=4, max_rounds=6)
    bundle = load_replay(game_dir)
    samples = list(iter_samples(
        bundle,
        allow_legacy=False,
        keep_forced=True,
        leak_check_rng=random.Random(0),
        leak_check_limit=5,
    ))
    checked = [s for s in samples if s.leak_checked]
    assert len(checked) >= 5
    assert all(not s.leak_mismatch for s in checked)

    manifest = write_shards(
        samples, tmp_path / "ds", dataset_id="leak", shard_size=1000, sources={}
    )
    assert manifest["leak_check"]["mismatches"] == 0
    assert manifest["leak_check"]["nodes"] >= 5


# ── T4.8 CLI smoke ─────────────────────────────────────────────────────────


def test_cli_smoke(requires_c_engine, tmp_path) -> None:
    run_dir = tmp_path / "run"
    game_dir = _make_game(run_dir, num_players=2, num_sims=2, max_rounds=0)
    run_id = json.loads((game_dir / "replay.json").read_text(encoding="utf-8"))["run_id"]
    (run_dir / "manifest.json").write_text(
        json.dumps({"run_id": run_id, "engine_git_sha": "a" * 40}), encoding="utf-8"
    )
    out = tmp_path / "ds"
    result = subprocess.run(
        [
            sys.executable, "-m", "scripts.build_nn_dataset",
            "--runs", str(run_dir),
            "--out", str(out),
            "--shard-size", "1000000",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert result.returncode == 0, result.stderr
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["counts"]["samples"] > 0
    assert len(manifest["shards"]) == 1

    sources = manifest["sources"]
    assert isinstance(sources, dict)
    assert sources["accepted"][0]["run_id"] == run_id
    assert len(sources["runs"][0]["engine_git_sha"]) == 40


# ── report metrics (pure) ──────────────────────────────────────────────────


def test_report_metrics(tmp_path) -> None:
    samples = _synthetic_samples(5)
    write_shards(samples, tmp_path, dataset_id="ds", shard_size=5, sources={})
    metrics = report_metrics(tmp_path)
    assert metrics["samples"] == 5
    assert metrics["policy_argmax_match_frac"] == 1.0
    assert len(metrics["value_mean_per_seat"]) == 4
    assert metrics["value_mean_per_seat"][2] == 0.0
    assert "pair_move_merge_frac" in metrics
    assert metrics["n_legal_raw_mean"] >= 0.0


def test_report_metrics_null_when_no_200_sim_samples(tmp_path) -> None:
    """T1.4: an empty metric is None, and the sample counts are reported."""
    low = _synthetic_samples(3)
    for s in low:
        s.sims_requested = 50
    write_shards(low, tmp_path / "low", dataset_id="low", shard_size=10, sources={})
    metrics = report_metrics(tmp_path / "low")
    assert metrics["policy_argmax_match_frac_sims_ge_200"] is None
    assert metrics["argmax_n_sims_ge_200"] == 0
    assert metrics["argmax_n"] == 3

    high = _synthetic_samples(2)
    write_shards(high, tmp_path / "high", dataset_id="high", shard_size=10, sources={})
    metrics = report_metrics(tmp_path / "high")
    assert metrics["policy_argmax_match_frac_sims_ge_200"] == 1.0
    assert metrics["argmax_n_sims_ge_200"] == 2
    assert metrics["argmax_n"] == 2


def test_report_metrics_null_when_no_samples(tmp_path) -> None:
    """T4.4 (m4): empty-denominator metrics are None, not 0.0."""
    empty = tmp_path / "empty"
    empty.mkdir()
    (empty / "manifest.json").write_text(json.dumps({"shards": []}), encoding="utf-8")
    metrics = report_metrics(empty)
    assert metrics["samples"] == 0
    assert metrics["policy_argmax_match_frac"] is None
    assert metrics["n_legal_raw_mean"] is None
