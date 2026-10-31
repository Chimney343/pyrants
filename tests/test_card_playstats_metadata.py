"""Tests for ``scripts.card_playstats.metadata`` — per-run collection metadata."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.card_playstats.discovery import find_run_folders
from scripts.card_playstats.metadata import RunMetadata, market_card_ids, run_metadata

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_ROOT = ROOT / "artifacts" / "ismcts"
RECOMMENDED_RUN = "20260911T193759Z_58e54c44a5f5"


def _summary(
    *,
    winner: int,
    deck_a: str,
    deck_b: str,
    players: list[str],
    scores: list[int],
    decision_count: int,
    move_type_counts: dict,
    entropy_full: float = 3.0,
    entropy_recruited: float = 2.5,
) -> dict:
    return {
        "winner": winner,
        "outcome": f"{players[winner]}_win",
        "stopped_reason": "terminal",
        "player_ids": players,
        "deck_a_id": deck_a,
        "deck_b_id": deck_b,
        "final_scores_per_player": dict(zip(players, scores, strict=True)),
        "decision_count": decision_count,
        "move_type_counts": move_type_counts,
        "final_deck_metrics": [
            {
                "full": {"shannon_entropy": entropy_full, "deck_size": 20},
                "recruited": {"shannon_entropy": entropy_recruited, "deck_size": 12},
            }
            for _ in players
        ],
    }


def _synthetic_run(tmp_path: Path) -> Path:
    run = tmp_path / "run_meta"
    run.mkdir()
    def _setup(*card_ids: str) -> str:
        return json.dumps(
            {
                "setup_id": "x",
                "market_deck": {"entries": [{"card_id": cid, "count": 1} for cid in card_ids]},
                "special_stacks": [{"card_id": "house_guard", "stack_total": 15, "recruitable": True}],
            }
        )

    (run / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": "meta_run",
                "engine_git_sha": "deadbeef",
                "engine_git_dirty": False,
                "config": {"num_sims": 16, "num_players": 3, "seed": 7},
                "games": [
                    {"game_index": 0, "setup_data_json": _setup("soldier", "advocate")},
                    {"game_index": 1, "setup_data_json": _setup("wight", "advocate")},
                    {"game_index": 2, "setup_data_json": _setup("soldier")},
                ],
            }
        ),
        encoding="utf-8",
    )
    g0 = run / "game_0000"
    g0.mkdir()
    (g0 / "replay.json").write_text(json.dumps({"step_count": 10, "replay_log": []}), encoding="utf-8")
    (g0 / "summary.json").write_text(
        json.dumps(
            _summary(
                winner=0,
                deck_a="undead",
                deck_b="aberrations",
                players=["p1", "p2", "p3"],
                scores=[30, 20, 10],
                decision_count=100,
                move_type_counts={"recruit": 5, "play_card": 9},
            )
        ),
        encoding="utf-8",
    )
    g1 = run / "game_0001"
    g1.mkdir()
    (g1 / "replay.json").write_text(json.dumps({"step_count": 12, "replay_log": []}), encoding="utf-8")
    (g1 / "summary.json").write_text(
        json.dumps(
            _summary(
                winner=2,
                deck_a="undead",
                deck_b="dragons",
                players=["p1", "p2", "p3"],
                scores=[15, 25, 40],
                decision_count=120,
                move_type_counts={"recruit": 7, "play_card": 11},
                entropy_full=4.0,
                entropy_recruited=3.0,
            )
        ),
        encoding="utf-8",
    )
    g2 = run / "game_0002"
    g2.mkdir()
    (g2 / "replay.json").write_text(json.dumps({"step_count": 3, "replay_log": []}), encoding="utf-8")
    (g2 / "summary.json").write_text(json.dumps({"stopped_reason": "round_cap"}), encoding="utf-8")
    return run


def test_run_metadata_rollups(tmp_path: Path) -> None:
    run = _synthetic_run(tmp_path)
    (folder,) = find_run_folders(run)

    meta = run_metadata(folder)

    assert isinstance(meta, RunMetadata)
    assert meta.num_games == 3
    assert meta.complete_games == 2
    assert meta.incomplete_games == 1
    assert meta.config["num_sims"] == 16
    assert meta.engine_git_sha == "deadbeef"
    assert meta.winner_counts_by_seat == {0: 1, 2: 1}
    assert meta.win_rate_by_seat[0] == pytest.approx(0.5)
    assert meta.win_rate_by_seat[1] == pytest.approx(0.0)
    assert meta.win_rate_by_seat[2] == pytest.approx(0.5)
    assert meta.matchup_counts == {"undead vs aberrations": 1, "undead vs dragons": 1}
    assert meta.deck_counts == {"undead": 2, "aberrations": 1, "dragons": 1}
    assert meta.move_type_totals == {"recruit": 12, "play_card": 20}
    assert meta.game_lengths == [100, 120]
    assert meta.mean_score_by_seat["p1"] == pytest.approx(22.5)
    assert meta.mean_score_by_seat["p3"] == pytest.approx(25.0)
    assert meta.mean_deck_entropy["full"] == pytest.approx(3.5)
    assert meta.mean_deck_entropy["recruited"] == pytest.approx(2.75)


def test_market_card_ids_unions_games_and_includes_special_stacks(tmp_path: Path) -> None:
    run = _synthetic_run(tmp_path)
    (folder,) = find_run_folders(run)

    assert market_card_ids(folder) == {"soldier", "advocate", "wight", "house_guard"}


def test_run_metadata_round_trips(tmp_path: Path) -> None:
    run = _synthetic_run(tmp_path)
    (folder,) = find_run_folders(run)

    meta = run_metadata(folder)

    assert RunMetadata.from_dict(meta.to_dict()) == meta


@pytest.mark.skipif(not ARTIFACTS_ROOT.exists(), reason="ISMCTS artifacts not present")
def test_real_recommended_run_metadata() -> None:
    folders = find_run_folders(ARTIFACTS_ROOT)
    folder = next(f for f in folders if f.run_dir.name == RECOMMENDED_RUN)

    meta = run_metadata(folder)

    assert meta.complete_games >= 1
    assert meta.num_games == len(folder.game_dirs)
    assert sum(meta.winner_counts_by_seat.values()) <= meta.complete_games
    assert meta.config
