"""Shared session controller tests."""

from __future__ import annotations

from pathlib import Path

from engine.moves import InitialPlacementMove, PlayCardMove
from engine.state import TurnPhase
from game_session import GameSession

BASE_DIR = Path(__file__).resolve().parents[2]
BOARD_PATH = BASE_DIR / "data" / "boards" / "tyrants_of_the_underdark.json"
CARD_PATH = BASE_DIR / "data" / "cards" / "catalog.json"
SETUP_PATH = BASE_DIR / "data" / "decks" / "base_setup.json"


def _session(seed: int = 41) -> GameSession:
    session = GameSession.from_files(
        board_path=BOARD_PATH,
        card_path=CARD_PATH,
        setup_path=SETUP_PATH,
        player_ids=["p1", "p2"],
        seed=seed,
    )
    _resolve_setup(session)
    return session


def _resolve_setup(session: GameSession) -> None:
    from engine.helpers import _legal_initial_placement_node_ids

    while session.state.phase == TurnPhase.SETUP:
        node_ids = _legal_initial_placement_node_ids(session.state)
        move = InitialPlacementMove(
            player_id=session.state.current_player_id,
            target_node_id=node_ids[0],
        )
        session.submit_move(move)


def test_game_session_snapshot_exposes_current_state() -> None:
    session = _session()

    snapshot = session.snapshot()

    assert snapshot.state == session.state
    assert snapshot.move_count == 2
    assert snapshot.is_terminal is False
    assert snapshot.final_scores is None
    assert any(isinstance(move, PlayCardMove) for move in snapshot.legal_moves)


def test_game_session_submit_move_updates_state_and_move_log() -> None:
    session = _session(seed=13)
    player_id = session.state.current_player_id
    hand_size_before = len(session.state.players[player_id].hand)

    move = next(move for move in session.legal_moves() if isinstance(move, PlayCardMove))
    updated_state = session.submit_move(move)

    assert updated_state == session.state
    assert session.move_count == 3
    assert session.move_log[-1] == move
    assert len(session.state.players[player_id].hand) == hand_size_before - 1
    assert session.state.players[player_id].played_cards.count(move.card_id) == 1
