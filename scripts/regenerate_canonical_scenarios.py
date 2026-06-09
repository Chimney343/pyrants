"""Regenerate the four canonical scenarios under data/scenarios/.

These scenarios are used by test_scenarios.py for regression testing.
Unlike card scenarios, they are hand-crafted from specific game states
rather than batch-generated from card roster searches.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.moves import PlayCardMove
from engine.rules import apply, legal_moves
from game_session import GameSession
from game_setup.scenarios import save_game_state


def main() -> None:
    scenarios_dir = ROOT / "data" / "scenarios"
    board_path = ROOT / "data" / "boards" / "tyrants_of_the_underdark.json"
    card_path = ROOT / "data" / "cards" / "catalog.json"
    setup_path = ROOT / "data" / "decks" / "base_setup.json"

    session = GameSession.from_files(
        board_path=board_path,
        card_path=card_path,
        setup_path=setup_path,
        player_ids=["p1", "p2"],
        seed=13,
    )
    save_game_state(
        session.state,
        scenarios_dir / "initial_two_player.json",
        scenario_id="initial_two_player",
        description="Two-player initial game state for scenario loading tests.",
        tags=["canonical", "initial", "regression"],
    )
    print("  initial_two_player.json")

    move = next(m for m in legal_moves(session.state) if isinstance(m, PlayCardMove))
    session.submit_move(move)
    save_game_state(
        session.state,
        scenarios_dir / "mid_turn_two_player.json",
        scenario_id="mid_turn_two_player",
        description="Two-player state after playing one card.",
        tags=["canonical", "mid-turn", "regression"],
        move_count=1,
    )
    print("  mid_turn_two_player.json")

    session2 = GameSession.from_files(
        board_path=board_path,
        card_path=card_path,
        setup_path=setup_path,
        player_ids=["p1", "p2"],
        seed=31,
    )
    state = session2.state.model_copy(deep=True)
    state.players["p1"].hand = ["enchanter_of_thay"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.board.nodes["site_gauntlgrym"].spies.add("p1")
    played = apply(state, PlayCardMove(player_id="p1", card_id="enchanter_of_thay", hand_index=0))
    save_game_state(
        played,
        scenarios_dir / "pending_modal_choice.json",
        scenario_id="pending_modal_choice",
        description="Two-player pending choice scenario after playing enchanter_of_thay.",
        tags=["canonical", "pending-choice", "regression"],
    )
    print("  pending_modal_choice.json")

    session3 = GameSession.from_files(
        board_path=board_path,
        card_path=card_path,
        setup_path=setup_path,
        player_ids=["p1", "p2"],
        seed=13,
    )
    scoring_state = session3.state.model_copy(deep=True)
    scoring_state.players["p1"].inner_circle = ["card_a", "card_b", "card_c"]
    scoring_state.players["p1"].trophy_hall = ["t1", "t2", "t3"]
    scoring_state.players["p2"].inner_circle = ["card_d", "card_e"]
    scoring_state.board.nodes["site_gauntlgrym"].troop_slots = ["p1", "p1", "p1"]
    save_game_state(
        scoring_state,
        scenarios_dir / "scoring_test.json",
        scenario_id="scoring_test",
        description="Two-player scenario with inner-circle, trophy-hall, and troop control data for scoring tests.",
        tags=["canonical", "scoring", "regression"],
    )
    print("  scoring_test.json")

    print("Canonical scenarios regenerated.")


if __name__ == "__main__":
    main()
