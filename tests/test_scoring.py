"""Final-scoring aggregation tests."""

from __future__ import annotations

from pathlib import Path

from engine.scoring import award_end_of_turn_site_vp, compute_final_scores
from game_setup.loaders import create_game_state_from_files

BASE_DIR = Path(__file__).resolve().parents[1]
BOARD_PATH = BASE_DIR / "data" / "boards" / "tyrants_of_the_underdark.json"
CARD_PATH = BASE_DIR / "data" / "cards" / "catalog.json"
SETUP_PATH = BASE_DIR / "data" / "decks" / "base_setup.json"


def test_compute_final_scores_aggregates_all_known_sources() -> None:
    state = create_game_state_from_files(
        BOARD_PATH,
        CARD_PATH,
        SETUP_PATH,
        player_ids=["p1", "p2"],
        seed=31,
    )
    updated = state.model_copy(deep=True)

    updated.board.nodes["site_menzoberranzan"].troop_slots = ["p1", "p1", "p1", "p1", "p1", "p1"]
    updated.board.nodes["site_menzoberranzan"].spies = set()

    updated.players["p1"].trophy_hall = ["enemy_troop"]
    updated.players["p1"].vp_tokens = 3
    updated.players["p1"].inner_circle = ["noble"]
    updated.players["p1"].score = 4

    totals = compute_final_scores(updated)

    assert "p1" in totals
    assert totals["p1"] > totals["p2"]
    assert totals["p1"] >= 4


def test_end_of_turn_site_vp_awards_for_total_control() -> None:
    state = create_game_state_from_files(
        BOARD_PATH,
        CARD_PATH,
        SETUP_PATH,
        player_ids=["p1", "p2"],
        seed=37,
    )
    updated = state.model_copy(deep=True)
    updated.board.nodes["site_menzoberranzan"].troop_slots = ["p1", "p1", "p1", "p1", "p1", "p1"]
    updated.board.nodes["site_menzoberranzan"].spies = set()
    score_before = updated.players["p1"].score

    scored = award_end_of_turn_site_vp(updated, "p1")

    assert scored.players["p1"].score == score_before + 1


def test_end_of_turn_site_vp_no_award_without_total_control() -> None:
    state = create_game_state_from_files(
        BOARD_PATH,
        CARD_PATH,
        SETUP_PATH,
        player_ids=["p1", "p2"],
        seed=41,
    )
    updated = state.model_copy(deep=True)
    updated.board.nodes["site_menzoberranzan"].troop_slots = ["p1", "p2", None, None, None, None]
    score_before = updated.players["p1"].score

    scored = award_end_of_turn_site_vp(updated, "p1")

    assert scored.players["p1"].score == score_before
