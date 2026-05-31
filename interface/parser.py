"""Parse CLI commands into typed engine moves."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from engine.moves import (
    ActivateCardAbilityMove,
    AssassinateMove,
    DeclineCardAbilityMove,
    DeployMove,
    EndMainPhaseMove,
    Move,
    PlayCardMove,
    PromoteCardMove,
    RecruitMove,
    ResolveCleanupMove,
    ResolveEndOfTurnMove,
    ReturnSpyMove,
    SkipPromoteMove,
)
from engine.state import GameState, TurnPhase


class CommandKind(str, Enum):
    """Kinds of parsed user commands."""

    MOVE = "move"
    HELP = "help"
    LEGAL = "legal"
    QUIT = "quit"


@dataclass(frozen=True)
class ParsedCommand:
    """A parsed command, with move payload only for MOVE commands."""

    kind: CommandKind
    move: Move | None = None


def help_text(phase: TurnPhase) -> str:
    """Return human-readable command help for the current phase."""

    shared = "help | legal | quit"
    if phase == TurnPhase.MAIN:
        return (
            "Main phase commands: play <hand_index> | deploy <node_id> | "
            "assassinate <node_id> <slot_index> | recruit <market_slot> | "
            "return-spy <node_id> <spy_owner_id> | "
            "activate <card_id> <ability_key> [discard_hand_index ...] | "
            "decline <card_id> <ability_key> | promote <card_id> | skip-promote <card_id> | end | "
            + shared
        )
    if phase == TurnPhase.END_OF_TURN:
        return "End-of-turn commands: promote <card_id> | skip-promote <card_id> | resolve | " + shared
    if phase == TurnPhase.CLEANUP:
        return "Cleanup commands: cleanup | " + shared
    return "Commands: " + shared


def parse_command(raw_command: str, state: GameState) -> ParsedCommand:
    """Parse one raw command string into a typed command object."""

    stripped = raw_command.strip()
    if not stripped:
        raise ValueError("Command cannot be empty")

    tokens = stripped.split()
    action = tokens[0].lower()

    if action in {"help", "h", "?"}:
        return ParsedCommand(kind=CommandKind.HELP)
    if action in {"legal", "l"}:
        return ParsedCommand(kind=CommandKind.LEGAL)
    if action in {"quit", "q", "exit"}:
        return ParsedCommand(kind=CommandKind.QUIT)

    current_player_id = state.current_player_id

    if state.phase == TurnPhase.MAIN:
        if action in {"end", "pass", "done"}:
            return ParsedCommand(
                kind=CommandKind.MOVE,
                move=EndMainPhaseMove(player_id=current_player_id),
            )

        if action in {"activate", "ability"}:
            if len(tokens) < 3:
                raise ValueError("Usage: activate <card_id> <ability_key> [discard_hand_index ...]")

            discard_hand_indices: list[int] = []
            for raw_index in tokens[3:]:
                try:
                    discard_hand_indices.append(int(raw_index))
                except ValueError as error:
                    raise ValueError("discard_hand_index must be an integer") from error

            return ParsedCommand(
                kind=CommandKind.MOVE,
                move=ActivateCardAbilityMove(
                    player_id=current_player_id,
                    card_id=tokens[1],
                    ability_key=tokens[2],
                    discard_hand_indices=discard_hand_indices,
                ),
            )

        if action in {"decline", "decline-ability"}:
            if len(tokens) != 3:
                raise ValueError("Usage: decline <card_id> <ability_key>")

            return ParsedCommand(
                kind=CommandKind.MOVE,
                move=DeclineCardAbilityMove(
                    player_id=current_player_id,
                    card_id=tokens[1],
                    ability_key=tokens[2],
                ),
            )

        if action in {"promote", "promo"}:
            if len(tokens) != 2:
                raise ValueError("Usage: promote <card_id>")

            return ParsedCommand(
                kind=CommandKind.MOVE,
                move=PromoteCardMove(
                    player_id=current_player_id,
                    card_id=tokens[1],
                ),
            )

        if action in {"skip-promote", "skippromote", "skip-promo"}:
            if len(tokens) != 2:
                raise ValueError("Usage: skip-promote <card_id>")

            return ParsedCommand(
                kind=CommandKind.MOVE,
                move=SkipPromoteMove(
                    player_id=current_player_id,
                    card_id=tokens[1],
                ),
            )

        if action in {"deploy", "d"}:
            if len(tokens) != 2:
                raise ValueError("Usage: deploy <node_id>")

            node_id = tokens[1]
            if node_id not in state.board.nodes:
                raise ValueError("Unknown node id")

            return ParsedCommand(
                kind=CommandKind.MOVE,
                move=DeployMove(
                    player_id=current_player_id,
                    target_node_id=node_id,
                    troop_count=1,
                ),
            )

        if action in {"play", "p"}:
            if len(tokens) != 2:
                raise ValueError("Usage: play <hand_index>")

            try:
                hand_index = int(tokens[1])
            except ValueError as error:
                raise ValueError("hand_index must be an integer") from error

            hand = state.players[current_player_id].hand
            if hand_index < 0 or hand_index >= len(hand):
                raise ValueError("hand_index is out of range")

            return ParsedCommand(
                kind=CommandKind.MOVE,
                move=PlayCardMove(
                    player_id=current_player_id,
                    card_id=hand[hand_index],
                    hand_index=hand_index,
                ),
            )

        if action in {"assassinate", "a"}:
            if len(tokens) != 3:
                raise ValueError("Usage: assassinate <node_id> <slot_index>")

            node_id = tokens[1]
            if node_id not in state.board.nodes:
                raise ValueError("Unknown node id")

            try:
                slot_index = int(tokens[2])
            except ValueError as error:
                raise ValueError("slot_index must be an integer") from error

            if slot_index < 0 or slot_index >= len(state.board.nodes[node_id].troop_slots):
                raise ValueError("slot_index is out of range")

            return ParsedCommand(
                kind=CommandKind.MOVE,
                move=AssassinateMove(
                    player_id=current_player_id,
                    target_node_id=node_id,
                    target_slot_index=slot_index,
                ),
            )

        if action in {"recruit", "r", "buy"}:
            if len(tokens) != 2:
                raise ValueError("Usage: recruit <market_slot>")

            try:
                market_slot = int(tokens[1])
            except ValueError as error:
                raise ValueError("market_slot must be an integer") from error

            if market_slot < 0 or market_slot >= len(state.market.row):
                raise ValueError("market_slot is out of range")

            return ParsedCommand(
                kind=CommandKind.MOVE,
                move=RecruitMove(
                    player_id=current_player_id,
                    market_slot=market_slot,
                ),
            )

        if action in {"return-spy", "returnspy", "rs"}:
            if len(tokens) != 3:
                raise ValueError("Usage: return-spy <node_id> <spy_owner_id>")

            node_id = tokens[1]
            if node_id not in state.board.nodes:
                raise ValueError("Unknown node id")

            return ParsedCommand(
                kind=CommandKind.MOVE,
                move=ReturnSpyMove(
                    player_id=current_player_id,
                    node_id=node_id,
                    spy_owner_id=tokens[2],
                ),
            )

        raise ValueError("Unknown main-phase command")

    if state.phase == TurnPhase.END_OF_TURN:
        if action in {"promote", "promo"}:
            if len(tokens) != 2:
                raise ValueError("Usage: promote <card_id>")

            return ParsedCommand(
                kind=CommandKind.MOVE,
                move=PromoteCardMove(
                    player_id=current_player_id,
                    card_id=tokens[1],
                ),
            )

        if action in {"skip-promote", "skippromote", "skip-promo"}:
            if len(tokens) != 2:
                raise ValueError("Usage: skip-promote <card_id>")

            return ParsedCommand(
                kind=CommandKind.MOVE,
                move=SkipPromoteMove(
                    player_id=current_player_id,
                    card_id=tokens[1],
                ),
            )

        if action in {"resolve", "endturn", "eot"}:
            return ParsedCommand(
                kind=CommandKind.MOVE,
                move=ResolveEndOfTurnMove(player_id=current_player_id),
            )
        raise ValueError("Unknown end-of-turn command")

    if state.phase == TurnPhase.CLEANUP:
        if action in {"cleanup", "next"}:
            return ParsedCommand(
                kind=CommandKind.MOVE,
                move=ResolveCleanupMove(player_id=current_player_id),
            )
        raise ValueError("Unknown cleanup command")

    raise ValueError("Commands are not available in the current phase")
