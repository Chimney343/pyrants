"""Tests for ``interface.replay_loader`` — headless, no Tk, no pyspiel.

The module under test must not import Tkinter or pyspiel; this test file may
import pyspiel to assert seed-mixer parity (guard for trap #1 in the plan).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from interface.game_viewer import DEFAULT_BOARD_PATH, DEFAULT_CARD_PATH, DEFAULT_SETUP_PATH
from interface.replay_loader import discover_replays, engine_seed, load_replay

ROOT = Path(__file__).resolve().parents[1]
GAME0000 = ROOT / "artifacts" / "ismcts" / "game_0000"


@pytest.mark.parametrize("n", [0, 1, 42, 43, 2**16, 2**30])
def test_engine_seed_matches_openspiel(n: int) -> None:
    """The engine seed mixer must mirror openspiel_pyrants.state_c._public_to_seed."""
    from openspiel_pyrants.state_c import _public_to_seed

    assert engine_seed(n) == _public_to_seed(n)


def test_engine_seed_known_value() -> None:
    assert engine_seed(42) == 1964635914


def _write_replay(
    game_dir: Path,
    *,
    seed: int,
    players: list[str],
    deck_a_id: str = "drow",
    deck_b_id: str = "dragon",
) -> None:
    game_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": "test",
        "stopped_reason": "terminal",
        "step_count": 1,
        "is_terminal": True,
        "winner_id": players[-1],
        "final_scores": {p: 7 for p in players},
        "replay_log": [],
        "replay_context": {
            "board_path": str(ROOT / "data" / "boards" / "tyrants_of_the_underdark.json"),
            "card_path": str(ROOT / "data" / "cards"),
            "setup_path": str(ROOT / "data" / "decks" / "base_setup.json"),
            "player_ids": players,
            "seed": seed,
            "deck_a_id": deck_a_id,
            "deck_b_id": deck_b_id,
        },
    }
    (game_dir / "replay.json").write_text(json.dumps(payload), encoding="utf-8")


def test_discover_replays_finds_every_replay_and_no_summary_yields_usable_meta(tmp_path: Path) -> None:
    _write_replay(tmp_path / "game_0000", seed=42, players=["p1", "p2", "p3"])
    _write_replay(tmp_path / "game_0010", seed=10, players=["p1", "p2"])
    no_summary = tmp_path / "game_0003"
    _write_replay(no_summary, seed=45, players=["p1", "p2"])
    (tmp_path / "game_zzz").mkdir()  # red herring: no replay.json at all

    metas = discover_replays(tmp_path)

    assert {meta.game_dir.name for meta in metas} == {"game_0000", "game_0003", "game_0010"}
    by_name = {meta.game_dir.name: meta for meta in metas}

    meta = by_name["game_0003"]  # directory has no summary.json
    assert meta.step_count == 1
    assert meta.player_ids == ("p1", "p2")
    assert meta.deck_a_id == "drow"
    assert meta.deck_b_id == "dragon"
    assert meta.shuffle_seed == 45
    assert meta.winner_id == "p2"


def test_discover_replays_returns_newest_first(tmp_path: Path) -> None:
    p1 = tmp_path / "game_0000"
    p2 = tmp_path / "game_0001"
    p3 = tmp_path / "game_0002"
    _write_replay(p1, seed=1, players=["p1"])
    _write_replay(p2, seed=2, players=["p1"])
    _write_replay(p3, seed=3, players=["p1"])
    for path, mtime in ((p1, 1000), (p2, 3000), (p3, 2000)):
        os.utime(path / "replay.json", (mtime, mtime))

    metas = discover_replays(tmp_path)

    assert [meta.game_dir.name for meta in metas] == ["game_0001", "game_0002", "game_0000"]


def test_load_replay_path_fallback_flags_substitution(tmp_path: Path) -> None:
    game_dir = tmp_path / "game_0000"
    game_dir.mkdir()
    payload = {
        "run_id": "test",
        "step_count": 0,
        "is_terminal": False,
        "winner_id": None,
        "final_scores": {},
        "replay_log": [],
        "replay_context": {
            "board_path": str(tmp_path / "does_not_exist" / "board.json"),
            "card_path": str(tmp_path / "does_not_exist" / "cards"),
            "setup_path": str(tmp_path / "does_not_exist" / "setup.json"),
            "player_ids": ["p1", "p2"],
            "seed": 42,
            "deck_a_id": "drow",
            "deck_b_id": "dragon",
        },
    }
    (game_dir / "replay.json").write_text(json.dumps(payload), encoding="utf-8")

    bundle = load_replay(game_dir)

    assert bundle.board_path == DEFAULT_BOARD_PATH
    assert bundle.card_path == DEFAULT_CARD_PATH
    assert bundle.setup_path == DEFAULT_SETUP_PATH
    assert bundle.substituted_paths == ("board_path", "card_path", "setup_path")


def test_load_replay_decisions_tolerates_malformed_lines(tmp_path: Path) -> None:
    game_dir = tmp_path / "game_0000"
    _write_replay(game_dir, seed=42, players=["p1", "p2"])
    (game_dir / "decisions.jsonl").write_text(
        '{"node": 0}\nNOT-JSON\n{"node": 2}\n',
        encoding="utf-8",
    )

    bundle = load_replay(game_dir)

    assert [d["node"] for d in bundle.decisions] == [0, 2]


def test_load_replay_setup_sha_none_when_summary_has_no_sha(tmp_path: Path) -> None:
    game_dir = tmp_path / "game_0000"
    _write_replay(game_dir, seed=42, players=["p1", "p2"])
    (game_dir / "summary.json").write_text(json.dumps({"run_id": "test"}), encoding="utf-8")

    bundle = load_replay(game_dir)

    assert bundle.setup_sha_matches is None


@pytest.mark.skipif(not GAME0000.exists(), reason="C engine replay artifacts not present")
def test_load_replay_real_artifact_setup_sha_matches() -> None:
    bundle = load_replay(GAME0000)

    assert bundle.setup_sha_matches is True
    assert bundle.meta.step_count == 517
    assert bundle.meta.player_ids == ("p1", "p2")
    assert bundle.meta.deck_a_id == "undead"
    assert bundle.meta.deck_b_id == "aberrations"