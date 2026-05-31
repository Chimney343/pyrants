"""CLI parser and loop smoke tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.moves import (
    ActivateCardAbilityMove,
    AssassinateMove,
    DeclineCardAbilityMove,
    DeployMove,
    PlayCardMove,
    PromoteCardMove,
    RecruitMove,
    ReturnSpyMove,
    SkipPromoteMove,
)
from engine.state import PendingAbilityState, PendingPromotionState, TurnPhase
from game_setup.loaders import create_game_state_from_files
from interface.cli import run_cli
from interface.display import render_state
from interface.parser import CommandKind, parse_command

BASE_DIR = Path(__file__).resolve().parents[1]
BOARD_PATH = BASE_DIR / "data" / "boards" / "base_game.json"
CARD_PATH = BASE_DIR / "data" / "cards" / "catalog.json"
SETUP_PATH = BASE_DIR / "data" / "decks" / "base_setup.json"


def _base_state(seed: int = 41):
    return create_game_state_from_files(BOARD_PATH, CARD_PATH, SETUP_PATH, ["p1", "p2"], seed=seed)


def test_parse_play_command_returns_play_card_move() -> None:
    state = _base_state()
    parsed = parse_command("play 0", state)

    assert parsed.kind == CommandKind.MOVE
    assert isinstance(parsed.move, PlayCardMove)
    assert parsed.move.card_id == state.players[state.current_player_id].hand[0]


def test_parse_deploy_command_returns_deploy_move() -> None:
    state = _base_state()
    parsed = parse_command("deploy site_a", state)

    assert parsed.kind == CommandKind.MOVE
    assert isinstance(parsed.move, DeployMove)
    assert parsed.move.target_node_id == "site_a"


def test_parse_assassinate_command_returns_assassinate_move() -> None:
    state = _base_state()
    parsed = parse_command("assassinate site_a 1", state)

    assert parsed.kind == CommandKind.MOVE
    assert isinstance(parsed.move, AssassinateMove)
    assert parsed.move.target_slot_index == 1


def test_parse_recruit_command_returns_recruit_move() -> None:
    state = _base_state()
    parsed = parse_command("recruit 0", state)

    assert parsed.kind == CommandKind.MOVE
    assert isinstance(parsed.move, RecruitMove)
    assert parsed.move.market_slot == 0


def test_parse_return_spy_command_returns_return_spy_move() -> None:
    state = _base_state()
    parsed = parse_command("return-spy site_a p2", state)

    assert parsed.kind == CommandKind.MOVE
    assert isinstance(parsed.move, ReturnSpyMove)
    assert parsed.move.node_id == "site_a"
    assert parsed.move.spy_owner_id == "p2"


def test_parse_activate_command_returns_activate_ability_move() -> None:
    state = _base_state()
    state.pending_ability = PendingAbilityState(card_id="ambassador", ability_key="gain_power")

    parsed = parse_command("activate ambassador gain_power 0 1", state)

    assert parsed.kind == CommandKind.MOVE
    assert isinstance(parsed.move, ActivateCardAbilityMove)
    assert parsed.move.card_id == "ambassador"
    assert parsed.move.discard_hand_indices == [0, 1]


def test_parse_decline_command_returns_decline_ability_move() -> None:
    state = _base_state()
    state.pending_ability = PendingAbilityState(card_id="ambassador", ability_key="gain_power")

    parsed = parse_command("decline ambassador gain_power", state)

    assert parsed.kind == CommandKind.MOVE
    assert isinstance(parsed.move, DeclineCardAbilityMove)
    assert parsed.move.ability_key == "gain_power"


def test_parse_promote_command_returns_promote_move() -> None:
    state = _base_state()
    state.pending_immediate_promotions = [
        PendingPromotionState(card_id="ambassador", timing="immediate", optional=True)
    ]

    parsed = parse_command("promote ambassador", state)

    assert parsed.kind == CommandKind.MOVE
    assert isinstance(parsed.move, PromoteCardMove)
    assert parsed.move.card_id == "ambassador"


def test_parse_skip_promote_command_returns_skip_move_in_end_of_turn() -> None:
    state = _base_state()
    state.phase = TurnPhase.END_OF_TURN
    state.pending_end_of_turn_promotions = [
        PendingPromotionState(card_id="ambassador", timing="end_of_turn", optional=True)
    ]

    parsed = parse_command("skip-promote ambassador", state)

    assert parsed.kind == CommandKind.MOVE
    assert isinstance(parsed.move, SkipPromoteMove)
    assert parsed.move.card_id == "ambassador"


def test_parse_command_rejects_out_of_range_hand_index() -> None:
    state = _base_state()

    with pytest.raises(ValueError, match="out of range"):
        parse_command("play 999", state)


def test_render_state_contains_turn_context() -> None:
    state = _base_state()
    rendered = render_state(state)

    assert "Current player" in rendered
    assert "Phase" in rendered
    assert "Market row" in rendered


def test_run_cli_accepts_legal_and_quit_commands() -> None:
    user_inputs = iter(["legal", "quit"])
    outputs: list[str] = []

    def _input(_: str) -> str:
        return next(user_inputs)

    def _output(message: str) -> None:
        outputs.append(message)

    run_cli(
        player_ids=["p1", "p2"],
        seed=5,
        input_fn=_input,
        output_fn=_output,
        max_steps=4,
    )

    assert any("Legal moves" in message for message in outputs)
    assert any("Exiting game." in message for message in outputs)
