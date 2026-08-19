"""Stop conditions tests for card scenario search (C engine)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine_c.bindings.scenario_search import (
    StopConditions,
    ensure_card_scenario_c,
)
from engine_c.bindings.view import _catalog_cache

ROSTERS_PATH = Path(__file__).resolve().parents[1] / "data" / "decks"
CARD_PATH = Path(__file__).resolve().parents[1] / "data" / "cards"
BOARD_PATH = Path(__file__).resolve().parents[1] / "data" / "boards" / "tyrants_of_the_underdark.json"
SETUP_PATH = Path(__file__).resolve().parents[1] / "data" / "decks" / "base_setup.json"


def _current_player_has_spy(state) -> bool:
    current_sym = state._s.current_player_id
    for i in range(state._s.node_count):
        node = state._s.nodes[i]
        for j in range(node.spy_count):
            if node.spies[j] == current_sym:
                return True
    return False


def _count_aspect_in_hand(state, aspect: str) -> int:
    cat = _catalog_cache()
    current_idx = state.player_ids.index(state.current_player_id)
    hand = state.player_hand(current_idx)
    return sum(1 for cid in hand if cat.get(cid, {}).get("aspect") == aspect)


def test_ensure_card_scenario_c_no_conditions_unchanged() -> None:
    state, note, _market_deck_ids, _special_stacks_present = ensure_card_scenario_c(
        "noble",
        board_path=BOARD_PATH,
        card_path=CARD_PATH,
        setup_path=SETUP_PATH,
        rosters_path=ROSTERS_PATH,
        player_ids=["p1", "p2", "p3", "p4"],
        base_seed=0,
        max_attempts=1,
        max_steps_per_attempt=10,
    )
    assert note is None
    assert state.phase == "main"
    current_idx = state.player_ids.index(state.current_player_id)
    assert "noble" in state.player_hand(current_idx)
    state.destroy()


def test_ensure_card_scenario_c_require_spy_on_board() -> None:
    state, note, _market_deck_ids, _special_stacks_present = ensure_card_scenario_c(
        "noble",
        board_path=BOARD_PATH,
        card_path=CARD_PATH,
        setup_path=SETUP_PATH,
        rosters_path=ROSTERS_PATH,
        player_ids=["p1", "p2", "p3", "p4"],
        base_seed=42,
        max_attempts=5,
        max_steps_per_attempt=500,
        conditions=StopConditions(require_spy_on_board=True),
    )
    assert state.phase == "main"
    current_idx = state.player_ids.index(state.current_player_id)
    assert "noble" in state.player_hand(current_idx)
    if note is None:
        assert _current_player_has_spy(state), (
            f"Expected current player {state.current_player_id} to have a spy on the board"
        )
    state.destroy()


def test_ensure_card_scenario_c_require_aspect() -> None:
    state, note, _market_deck_ids, _special_stacks_present = ensure_card_scenario_c(
        "noble",
        board_path=BOARD_PATH,
        card_path=CARD_PATH,
        setup_path=SETUP_PATH,
        rosters_path=ROSTERS_PATH,
        player_ids=["p1", "p2", "p3", "p4"],
        base_seed=42,
        max_attempts=5,
        max_steps_per_attempt=500,
        conditions=StopConditions(require_aspect="obedience", require_aspect_count=3),
    )
    assert state.phase == "main"
    current_idx = state.player_ids.index(state.current_player_id)
    assert "noble" in state.player_hand(current_idx)
    if note is None:
        count = _count_aspect_in_hand(state, "obedience")
        assert count >= 3, (
            f"Expected >= 3 obedience cards in hand, got {count}"
        )
    state.destroy()


def test_ensure_card_scenario_c_combined_conditions() -> None:
    state, note, _market_deck_ids, _special_stacks_present = ensure_card_scenario_c(
        "noble",
        board_path=BOARD_PATH,
        card_path=CARD_PATH,
        setup_path=SETUP_PATH,
        rosters_path=ROSTERS_PATH,
        player_ids=["p1", "p2", "p3", "p4"],
        base_seed=42,
        max_attempts=10,
        max_steps_per_attempt=500,
        conditions=StopConditions(
            require_spy_on_board=True,
            require_aspect="obedience",
            require_aspect_count=3,
        ),
    )
    assert state.phase == "main"
    current_idx = state.player_ids.index(state.current_player_id)
    assert "noble" in state.player_hand(current_idx)
    if note is None:
        assert _current_player_has_spy(state)
        count = _count_aspect_in_hand(state, "obedience")
        assert count >= 3, f"Expected >= 3 obedience cards in hand, got {count}"
    state.destroy()
