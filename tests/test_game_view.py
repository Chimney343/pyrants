"""Tests for structured game view projections."""

from __future__ import annotations

from pathlib import Path

from engine.moves import AssassinateMove, DeployMove, PlayCardMove, ResolveGenericChoiceMove
from engine.rules import apply, legal_moves
from engine.state import PendingPromotionState
from game_session import GameSession
from game_view import LegalMoveView, build_game_view, describe_move, filter_legal_moves

BASE_DIR = Path(__file__).resolve().parents[1]
BOARD_PATH = BASE_DIR / "data" / "boards" / "tyrants_of_the_underdark.json"
CARD_PATH = BASE_DIR / "data" / "cards" / "catalog.json"
SETUP_PATH = BASE_DIR / "data" / "decks" / "base_setup.json"


def _session(seed: int = 7) -> GameSession:
    return GameSession.from_files(
        board_path=BOARD_PATH,
        card_path=CARD_PATH,
        setup_path=SETUP_PATH,
        player_ids=["p1", "p2"],
        seed=seed,
    )


def test_build_game_view_contains_core_state_shapes() -> None:
    session = _session()

    view = build_game_view(session)

    assert view.current_player_id == "p1"
    assert view.phase == "main"
    assert view.hand
    assert isinstance(view.current_player_played, tuple)
    assert view.market_row
    assert view.player_summaries
    assert view.board_nodes
    assert view.prompts
    assert any(move.move_type == "play_card" for move in view.legal_moves)


def test_build_game_view_updates_after_move_submission() -> None:
    session = _session(seed=13)
    before = build_game_view(session)
    play_move = next(move.move for move in before.legal_moves if isinstance(move.move, PlayCardMove))

    session.submit_move(play_move)
    after = build_game_view(session)

    assert after.current_player_id == before.current_player_id
    assert len(after.hand) == len(before.hand) - 1
    assert len(after.current_player_played) >= len(before.current_player_played)
    assert after.resource_power >= before.resource_power
    assert after.resource_influence >= before.resource_influence


def test_filter_legal_moves_by_hand_card_id() -> None:
    session = _session(seed=13)
    view = build_game_view(session)
    card_id = view.hand[0].card_id

    filtered = filter_legal_moves(view.legal_moves, hand_card_id=card_id)

    assert filtered
    assert all(isinstance(move.move, PlayCardMove) for move in filtered)
    assert all(move.move.card_id == card_id for move in filtered)


def test_filter_legal_moves_by_node_id() -> None:
    deploy_site_gauntlgrym = DeployMove(player_id="p1", target_node_id="site_gauntlgrym", troop_count=1)
    deploy_site_b = DeployMove(player_id="p1", target_node_id="site_b", troop_count=1)
    legal_moves = (
        LegalMoveView(
            move=deploy_site_gauntlgrym,
            move_type="deploy",
            label="Deploy to site_gauntlgrym",
            payload=deploy_site_gauntlgrym.model_dump(mode="json"),
        ),
        LegalMoveView(
            move=deploy_site_b,
            move_type="deploy",
            label="Deploy to site_b",
            payload=deploy_site_b.model_dump(mode="json"),
        ),
    )

    node_filtered = filter_legal_moves(legal_moves, node_id="site_gauntlgrym")

    assert len(node_filtered) == 1
    assert node_filtered[0].move.target_node_id == "site_gauntlgrym"


def test_filter_legal_moves_by_option_id() -> None:
    move_one = ResolveGenericChoiceMove(player_id="p1", source_card_id="aboleth", option_id="option_1")
    move_two = ResolveGenericChoiceMove(player_id="p1", source_card_id="aboleth", option_id="option_2")
    legal_moves = (
        LegalMoveView(move=move_one, move_type="resolve_generic_choice", label="Choose option 1", payload=move_one.model_dump(mode="json")),
        LegalMoveView(move=move_two, move_type="resolve_generic_choice", label="Choose option 2", payload=move_two.model_dump(mode="json")),
    )

    filtered = filter_legal_moves(legal_moves, option_id="option_2")

    assert len(filtered) == 1
    assert filtered[0].move.option_id == "option_2"


def test_filter_legal_moves_by_played_card_id() -> None:
    move_one = ResolveGenericChoiceMove(
        player_id="p1",
        source_card_id="ambassador",
        selection={"target_card_id": "noble"},
    )
    move_two = ResolveGenericChoiceMove(
        player_id="p1",
        source_card_id="ambassador",
        selection={"target_card_id": "soldier"},
    )
    legal_moves = (
        LegalMoveView(move=move_one, move_type="resolve_generic_choice", label="choice one", payload=move_one.model_dump(mode="json")),
        LegalMoveView(move=move_two, move_type="resolve_generic_choice", label="choice two", payload=move_two.model_dump(mode="json")),
    )

    filtered = filter_legal_moves(legal_moves, played_card_id="soldier")

    assert len(filtered) == 1
    assert filtered[0].move.selection["target_card_id"] == "soldier"


def test_describe_move_for_generic_target_includes_target_card() -> None:
    session = _session(seed=17)
    move = ResolveGenericChoiceMove(
        player_id="p1",
        source_card_id="ambassador",
        selection={"target_card_id": "noble"},
    )

    label = describe_move(session.state, move)

    assert "Noble" in label

def test_prompt_shows_end_of_turn_promotion_source_card() -> None:
    session = _session(seed=19)
    state = session.state.model_copy(deep=True)
    state.phase = state.phase.END_OF_TURN
    state.pending_end_of_turn_promotions = [
        PendingPromotionState(
            card_id="ambassador",
            timing="end_of_turn",
            optional=False,
            deferred_choice=True,
            source_card_id="ambassador",
            requires_another_played_card=True,
        )
    ]
    session._state = state

    view = build_game_view(session)

    assert any("from Ambassador" in prompt for prompt in view.prompts)


def test_describe_move_for_modal_option_includes_option_effect_summary() -> None:
    session = _session(seed=21)
    state = session.state.model_copy(deep=True)
    state.players["p1"].hand = ["aboleth"]
    state.players["p1"].deck = []

    played = apply(state, PlayCardMove(player_id="p1", card_id="aboleth", hand_index=0))
    option_move = next(
        move
        for move in legal_moves(played)
        if isinstance(move, ResolveGenericChoiceMove) and move.option_id == "option_1"
    )

    label = describe_move(played, option_move)

    assert "place spy" in label
    assert "option_1" not in label


def test_build_game_view_includes_current_player_trophy_hall() -> None:
    session = _session(seed=31)
    state = session.state.model_copy(deep=True)
    state.resource_pool.power = 3
    state.board.nodes["site_gauntlgrym"].troop_slots = ["p1", "p2", None]

    updated = apply(
        state,
        AssassinateMove(
            player_id="p1",
            target_node_id="site_gauntlgrym",
            target_slot_index=1,
        ),
    )
    session._state = updated

    view = build_game_view(session)

    assert view.current_player_trophy_hall == ("p2",)
    assert view.player_summaries[0].trophy_hall_count == 1
