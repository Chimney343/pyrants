"""Final-scoring aggregation tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.scoring import _cards_vp, _is_total_control, _site_control_owner, award_end_of_turn_site_vp, compute_final_scores
from game_setup.loaders import create_game_state_from_files

BASE_DIR = Path(__file__).resolve().parents[1]
BOARD_PATH = BASE_DIR / "data" / "boards" / "base_game.json"
CARD_PATH = BASE_DIR / "data" / "cards" / "catalog.json"
SETUP_PATH = BASE_DIR / "data" / "decks" / "base_setup.json"


def _fresh_state(seed: int = 31):
    return create_game_state_from_files(
        BOARD_PATH, CARD_PATH, SETUP_PATH, player_ids=["p1", "p2"], seed=seed,
    )


# ---------------------------------------------------------------------------
# _site_control_owner
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "troop_slots,expected_owner",
    [
        ([], None),
        ([None, None, None], None),
        (["white", "white", "white"], None),
        (["p1", "white", "white"], None),
        (["p1", "p1", "white"], "p1"),
        (["p1", "p1", "p2"], "p1"),
        (["p1", "p2"], None),
        (["p1", "p1", None], "p1"),
        (["p1", "white", None], None),
        (["p1", "p2", "white", None, None, None], None),
        (["p1", "p1", "p2", "white", None, None], "p1"),
        (["p1", "p2", "p2", "white", None, None], "p2"),
    ],
    ids=[
        "empty_list",
        "all_none",
        "only_white",
        "white_majority",
        "player_beats_white",
        "p1_majority",
        "player_tie",
        "single_player_sole",
        "player_white_tie",
        "multislot_threeway_tie",
        "multislot_p1_majority",
        "multislot_p2_majority",
    ],
)
def test_site_control_owner(troop_slots: list, expected_owner: str | None) -> None:
    state = _fresh_state(seed=1)
    updated = state.model_copy(deep=True)
    updated.board.nodes["site_a"].troop_slots = troop_slots
    assert _site_control_owner(updated, "site_a") == expected_owner


# ---------------------------------------------------------------------------
# _is_total_control
# ---------------------------------------------------------------------------


def test_is_total_control_all_troops_same_player_no_spies() -> None:
    state = _fresh_state(seed=2)
    updated = state.model_copy(deep=True)
    updated.board.nodes["site_a"].troop_slots = ["p1", "p1", "p1"]
    updated.board.nodes["site_a"].spies = set()
    assert _is_total_control(updated, "site_a", "p1") is True


def test_is_total_control_fails_with_empty_slot() -> None:
    state = _fresh_state(seed=3)
    updated = state.model_copy(deep=True)
    updated.board.nodes["site_a"].troop_slots = ["p1", None, "p1"]
    updated.board.nodes["site_a"].spies = set()
    assert _is_total_control(updated, "site_a", "p1") is False


def test_is_total_control_fails_with_enemy_spy() -> None:
    state = _fresh_state(seed=4)
    updated = state.model_copy(deep=True)
    updated.board.nodes["site_a"].troop_slots = ["p1", "p1", "p1"]
    updated.board.nodes["site_a"].spies = {"p2"}
    assert _is_total_control(updated, "site_a", "p1") is False


def test_is_total_control_succeeds_with_matching_spy() -> None:
    state = _fresh_state(seed=5)
    updated = state.model_copy(deep=True)
    updated.board.nodes["site_a"].troop_slots = ["p1", "p1"]
    updated.board.nodes["site_a"].spies = {"p1"}
    assert _is_total_control(updated, "site_a", "p1") is True


def test_is_total_control_white_can_have_total_control() -> None:
    """White troops filling all slots constitute total control for white."""
    state = _fresh_state(seed=6)
    updated = state.model_copy(deep=True)
    updated.board.nodes["site_a"].troop_slots = ["white", "white", "white"]
    updated.board.nodes["site_a"].spies = set()
    assert _is_total_control(updated, "site_a", "white") is True
    assert _is_total_control(updated, "site_a", "p1") is False


def test_is_total_control_fails_with_mixed_troops() -> None:
    state = _fresh_state(seed=7)
    updated = state.model_copy(deep=True)
    updated.board.nodes["site_a"].troop_slots = ["p1", "p2", "p1"]
    updated.board.nodes["site_a"].spies = set()
    assert _is_total_control(updated, "site_a", "p1") is False


def test_is_total_control_single_slot() -> None:
    state = _fresh_state(seed=8)
    updated = state.model_copy(deep=True)
    updated.board.nodes["site_a"].troop_slots = ["p1"]
    updated.board.nodes["site_a"].spies = set()
    assert _is_total_control(updated, "site_a", "p1") is True


def test_is_total_control_empty_slots() -> None:
    state = _fresh_state(seed=9)
    updated = state.model_copy(deep=True)
    updated.board.nodes["site_a"].troop_slots = []
    updated.board.nodes["site_a"].spies = set()
    assert _is_total_control(updated, "site_a", "p1") is True


# ---------------------------------------------------------------------------
# award_end_of_turn_site_vp
# ---------------------------------------------------------------------------


def test_end_of_turn_vp_sums_configured_total_control_value() -> None:
    """End-of-turn awards total_control_vp_per_turn, not a flat bonus."""
    state = _fresh_state(seed=10)
    updated = state.model_copy(deep=True)
    updated.board.nodes["site_a"].troop_slots = ["p1", "p1", "p1"]
    updated.board.nodes["site_a"].spies = set()
    updated.players["p1"].score = 0

    scored = award_end_of_turn_site_vp(updated, "p1")

    assert scored.players["p1"].score == 0


def test_end_of_turn_vp_does_not_award_for_simple_control() -> None:
    """Simple control (majority) does not grant end-of-turn VP."""
    state = _fresh_state(seed=11)
    updated = state.model_copy(deep=True)
    updated.board.nodes["site_a"].troop_slots = ["p1", None, None]
    updated.board.nodes["site_a"].spies = set()
    updated.players["p1"].score = 0

    scored = award_end_of_turn_site_vp(updated, "p1")

    assert scored.players["p1"].score == 0


def test_end_of_turn_vp_multiple_sites() -> None:
    state = _fresh_state(seed=12)
    updated = state.model_copy(deep=True)
    updated.board.nodes["site_a"].troop_slots = ["p1", "p1", "p1"]
    updated.board.nodes["site_a"].spies = set()
    updated.board.nodes["site_blingdenfire"].troop_slots = ["p1", "p1"]
    updated.board.nodes["site_blingdenfire"].spies = set()
    updated.players["p1"].score = 0

    scored = award_end_of_turn_site_vp(updated, "p1")

    assert scored.players["p1"].score == 0


def test_end_of_turn_vp_spy_blocks_total_control() -> None:
    state = _fresh_state(seed=13)
    updated = state.model_copy(deep=True)
    updated.board.nodes["site_a"].troop_slots = ["p1", "p1", "p1"]
    updated.board.nodes["site_a"].spies = {"p2"}
    updated.players["p1"].score = 0

    scored = award_end_of_turn_site_vp(updated, "p1")

    assert scored.players["p1"].score == 0


def test_end_of_turn_vp_only_awards_correct_player() -> None:
    state = _fresh_state(seed=14)
    updated = state.model_copy(deep=True)
    updated.board.nodes["site_a"].troop_slots = ["p1", "p1", "p1"]
    updated.board.nodes["site_a"].spies = set()
    updated.players["p1"].score = 0
    updated.players["p2"].score = 0

    scored = award_end_of_turn_site_vp(updated, "p1")

    assert scored.players["p1"].score == 0
    assert scored.players["p2"].score == 0


def test_award_end_of_turn_does_not_mutate_state_in_place() -> None:
    state = _fresh_state(seed=15)
    updated = state.model_copy(deep=True)
    updated.board.nodes["site_a"].troop_slots = ["p1", "p1", "p1"]
    updated.board.nodes["site_a"].spies = set()
    original_score = updated.players["p1"].score

    _ = award_end_of_turn_site_vp(updated, "p1")

    assert updated.players["p1"].score == original_score


# ---------------------------------------------------------------------------
# compute_final_scores
# ---------------------------------------------------------------------------


def test_compute_final_scores_aggregates_all_known_sources() -> None:
    state = _fresh_state(seed=31)
    updated = state.model_copy(deep=True)

    updated.board.nodes["site_a"].troop_slots = ["p1", "p1", "p1"]
    updated.board.nodes["site_a"].spies = set()

    updated.players["p1"].trophy_hall = ["enemy_troop"]
    updated.players["p1"].vp_tokens = 3
    updated.players["p1"].inner_circle = ["noble"]
    updated.players["p1"].score = 4

    totals = compute_final_scores(updated)

    assert "p1" in totals
    assert totals["p1"] > totals["p2"]
    assert totals["p1"] >= 4


def test_compute_final_scores_adds_control_vp() -> None:
    state = _fresh_state()
    updated = state.model_copy(deep=True)
    updated.board.nodes["site_a"].troop_slots = ["p1", None, None]
    updated.board.nodes["site_a"].spies = set()
    updated.players["p1"].score = 0
    updated.players["p1"].trophy_hall = []
    updated.players["p1"].vp_tokens = 0
    updated.players["p1"].inner_circle = []
    updated.players["p1"].deck = []
    updated.players["p1"].hand = []
    updated.players["p1"].discard_pile = []

    totals = compute_final_scores(updated)

    assert totals["p1"] == 2


def test_compute_final_scores_no_control_on_tie() -> None:
    state = _fresh_state()
    updated = state.model_copy(deep=True)
    updated.board.nodes["site_a"].troop_slots = ["p1", "p2"]
    updated.board.nodes["site_a"].spies = set()
    updated.players["p1"].score = 0
    updated.players["p1"].trophy_hall = []
    updated.players["p1"].vp_tokens = 0
    updated.players["p1"].inner_circle = []
    updated.players["p1"].deck = []
    updated.players["p1"].hand = []
    updated.players["p1"].discard_pile = []

    totals = compute_final_scores(updated)

    assert totals["p1"] == 0
    assert totals["p2"] == 0


def test_compute_final_scores_white_never_controls() -> None:
    state = _fresh_state()
    updated = state.model_copy(deep=True)
    updated.board.nodes["site_a"].troop_slots = ["white", "white", "white"]
    updated.board.nodes["site_a"].spies = set()
    for pid in ("p1", "p2"):
        p = updated.players[pid]
        p.score = 0
        p.trophy_hall = []
        p.vp_tokens = 0
        p.inner_circle = []
        p.deck = []
        p.hand = []
        p.discard_pile = []

    totals = compute_final_scores(updated)

    assert totals["p1"] == 0
    assert totals["p2"] == 0


def test_compute_final_scores_control_works_despite_enemy_spy() -> None:
    state = _fresh_state()
    updated = state.model_copy(deep=True)
    updated.board.nodes["site_a"].troop_slots = ["p1", "p1", None]
    updated.board.nodes["site_a"].spies = {"p2"}
    for pid in ("p1", "p2"):
        p = updated.players[pid]
        p.score = 0
        p.trophy_hall = []
        p.vp_tokens = 0
        p.inner_circle = []
        p.deck = []
        p.hand = []
        p.discard_pile = []

    totals = compute_final_scores(updated)

    assert totals["p1"] == 2


def test_compute_final_scores_correct_player_receives_vp() -> None:
    state = _fresh_state()
    updated = state.model_copy(deep=True)
    updated.board.nodes["site_a"].troop_slots = ["p1", "p1", "p1"]
    updated.board.nodes["site_a"].spies = set()
    updated.board.nodes["site_blingdenfire"].troop_slots = ["p2", "p2"]
    updated.board.nodes["site_blingdenfire"].spies = set()
    for pid in ("p1", "p2"):
        p = updated.players[pid]
        p.score = 0
        p.trophy_hall = []
        p.vp_tokens = 0
        p.inner_circle = []
        p.deck = []
        p.hand = []
        p.discard_pile = []

    totals = compute_final_scores(updated)

    assert totals["p1"] == 2
    assert totals["p2"] == 2


def test_compute_final_scores_preserves_running_score() -> None:
    state = _fresh_state()
    updated = state.model_copy(deep=True)
    updated.board.nodes["site_a"].troop_slots = []
    updated.board.nodes["site_a"].spies = set()
    for pid in ("p1", "p2"):
        p = updated.players[pid]
        p.score = 10
        p.trophy_hall = []
        p.vp_tokens = 0
        p.inner_circle = []
        p.deck = []
        p.hand = []
        p.discard_pile = []

    totals = compute_final_scores(updated)

    assert totals["p1"] == 10
    assert totals["p2"] == 10


def test_compute_final_scores_does_not_mutate_state() -> None:
    state = _fresh_state()
    updated = state.model_copy(deep=True)
    updated.board.nodes["site_a"].troop_slots = ["p1", "p1", "p1"]
    updated.board.nodes["site_a"].spies = set()
    original_p1_score = updated.players["p1"].score

    _ = compute_final_scores(updated)

    assert updated.players["p1"].score == original_p1_score


def test_compute_final_scores_empty_board() -> None:
    state = _fresh_state()
    updated = state.model_copy(deep=True)
    for pid in ("p1", "p2"):
        p = updated.players[pid]
        p.score = 0
        p.trophy_hall = []
        p.vp_tokens = 0
        p.inner_circle = []
        p.deck = []
        p.hand = []
        p.discard_pile = []

    totals = compute_final_scores(updated)

    assert totals["p1"] == 0
    assert totals["p2"] == 0


def test_compute_final_scores_trophy_vp() -> None:
    state = _fresh_state()
    updated = state.model_copy(deep=True)
    for pid in ("p1", "p2"):
        p = updated.players[pid]
        p.score = 0
        p.trophy_hall = []
        p.vp_tokens = 0
        p.inner_circle = []
        p.deck = []
        p.hand = []
        p.discard_pile = []

    updated.players["p1"].trophy_hall = ["e1", "e2", "e3"]
    totals = compute_final_scores(updated)
    assert totals["p1"] == 3


def test_compute_final_scores_token_vp() -> None:
    state = _fresh_state()
    updated = state.model_copy(deep=True)
    for pid in ("p1", "p2"):
        p = updated.players[pid]
        p.score = 0
        p.trophy_hall = []
        p.vp_tokens = 0
        p.inner_circle = []
        p.deck = []
        p.hand = []
        p.discard_pile = []

    updated.players["p1"].vp_tokens = 5
    totals = compute_final_scores(updated)
    assert totals["p1"] == 5


def test_compute_final_scores_deck_vp() -> None:
    state = _fresh_state()
    updated = state.model_copy(deep=True)
    for pid in ("p1", "p2"):
        p = updated.players[pid]
        p.score = 0
        p.trophy_hall = []
        p.vp_tokens = 0
        p.inner_circle = []
        p.deck = []
        p.hand = []
        p.discard_pile = []

    updated.players["p1"].deck = ["advance_scout"]
    totals = compute_final_scores(updated)
    assert totals["p1"] == 1


def test_compute_final_scores_inner_circle_vp() -> None:
    state = _fresh_state()
    updated = state.model_copy(deep=True)
    for pid in ("p1", "p2"):
        p = updated.players[pid]
        p.score = 0
        p.trophy_hall = []
        p.vp_tokens = 0
        p.inner_circle = []
        p.deck = []
        p.hand = []
        p.discard_pile = []

    updated.players["p1"].inner_circle = ["noble"]
    totals = compute_final_scores(updated)
    assert totals["p1"] == 1


def test_compute_final_scores_deck_vp_across_all_zones() -> None:
    state = _fresh_state()
    updated = state.model_copy(deep=True)
    for pid in ("p1", "p2"):
        p = updated.players[pid]
        p.score = 0
        p.trophy_hall = []
        p.vp_tokens = 0
        p.inner_circle = []
        p.deck = []
        p.hand = []
        p.discard_pile = []

    updated.players["p1"].deck = ["advance_scout"]
    updated.players["p1"].hand = ["advance_scout"]
    updated.players["p1"].discard_pile = ["advance_scout"]
    totals = compute_final_scores(updated)
    assert totals["p1"] == 3


# ---------------------------------------------------------------------------
# _cards_vp
# ---------------------------------------------------------------------------


def test_cards_vp_sums_field_correctly() -> None:
    from engine.state import card_index
    state = _fresh_state()
    index = card_index(state.definition.catalog)
    result = _cards_vp(["advance_scout", "advance_scout", "advance_scout"], index, "deck_vp")
    assert result == 3


def test_cards_vp_skips_unknown_card_ids() -> None:
    from engine.state import card_index
    state = _fresh_state()
    index = card_index(state.definition.catalog)
    result = _cards_vp(["nonexistent", "advance_scout"], index, "deck_vp")
    assert result == 1
