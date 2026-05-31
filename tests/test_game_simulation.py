"""Tests for headless simulation and replay logging."""

from __future__ import annotations

import json
from pathlib import Path

from game_simulation import (
    choose_first_legal_move,
    make_random_legal_move_chooser,
    replay_views_from_payload,
    run_simulation_from_files,
    write_replay_log,
)

BASE_DIR = Path(__file__).resolve().parents[1]
BOARD_PATH = BASE_DIR / "data" / "boards" / "base_game.json"
CARD_PATH = BASE_DIR / "data" / "cards" / "catalog.json"
SETUP_PATH = BASE_DIR / "data" / "decks" / "base_setup.json"


def test_run_simulation_with_first_policy_produces_replay_steps() -> None:
    result = run_simulation_from_files(
        board_path=BOARD_PATH,
        card_path=CARD_PATH,
        setup_path=SETUP_PATH,
        player_ids=["p1", "p2"],
        seed=3,
        chooser=choose_first_legal_move,
        max_steps=20,
    )

    assert result.step_count > 0
    assert result.stopped_reason in {"terminal", "max_steps", "no_legal_moves"}
    assert len(result.replay_log) == result.step_count


def test_run_simulation_with_seeded_random_policy_is_deterministic() -> None:
    chooser_a = make_random_legal_move_chooser(17)
    chooser_b = make_random_legal_move_chooser(17)

    result_a = run_simulation_from_files(
        board_path=BOARD_PATH,
        card_path=CARD_PATH,
        setup_path=SETUP_PATH,
        player_ids=["p1", "p2"],
        seed=11,
        chooser=chooser_a,
        max_steps=15,
    )
    result_b = run_simulation_from_files(
        board_path=BOARD_PATH,
        card_path=CARD_PATH,
        setup_path=SETUP_PATH,
        player_ids=["p1", "p2"],
        seed=11,
        chooser=chooser_b,
        max_steps=15,
    )

    moves_a = [step.payload["move_type"] for step in result_a.replay_log]
    moves_b = [step.payload["move_type"] for step in result_b.replay_log]

    assert moves_a == moves_b


def test_write_replay_log_serializes_result(tmp_path: Path) -> None:
    result = run_simulation_from_files(
        board_path=BOARD_PATH,
        card_path=CARD_PATH,
        setup_path=SETUP_PATH,
        player_ids=["p1", "p2"],
        seed=2,
        max_steps=5,
    )
    output_path = tmp_path / "replay.json"

    write_replay_log(output_path, result)

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["step_count"] == result.step_count
    assert payload["replay_log"]
    assert payload["replay_log"][0]["payload"]["move_type"]
    assert payload["replay_context"]["board_path"] == str(BOARD_PATH)
    assert payload["replay_context"]["card_path"] == str(CARD_PATH)
    assert payload["replay_context"]["setup_path"] == str(SETUP_PATH)


def test_replay_views_from_payload_reconstructs_step_sequence(tmp_path: Path) -> None:
    result = run_simulation_from_files(
        board_path=BOARD_PATH,
        card_path=CARD_PATH,
        setup_path=SETUP_PATH,
        player_ids=["p1", "p2"],
        seed=5,
        max_steps=8,
    )
    replay_path = tmp_path / "replay.json"
    write_replay_log(replay_path, result)
    payload = json.loads(replay_path.read_text(encoding="utf-8"))

    views = replay_views_from_payload(payload)

    assert len(views) == result.step_count + 1
    assert views[0].round_number >= 1
    assert views[-1].phase in {"main", "end_of_turn", "cleanup", "game_over"}
