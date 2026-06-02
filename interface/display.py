"""Text rendering for CLI state and move information."""

from __future__ import annotations

from engine.rules import legal_moves
from engine.state import GameState, card_index


def _derive_control(troop_slots: list[str | None]) -> str | None:
    counts: dict[str, int] = {}
    for occupant in troop_slots:
        if occupant is not None:
            counts[occupant] = counts.get(occupant, 0) + 1
    if not counts:
        return None
    max_count = max(counts.values())
    leaders = [owner for owner, count in counts.items() if count == max_count]
    return leaders[0] if len(leaders) == 1 and leaders[0] != "white" else None


def render_state(state: GameState) -> str:
    """Render a concise text snapshot of the current game state."""

    current_player = state.players[state.current_player_id]
    cards_by_id = card_index(state.definition.catalog)

    lines: list[str] = [
        f"Round: {state.round_number}",
        f"Phase: {state.phase.value}",
        f"Current player: {state.current_player_id}",
        f"Resources: power={state.resource_pool.power}, influence={state.resource_pool.influence}",
        "",
        "Current player hand:",
    ]

    if current_player.hand:
        for index, card_id in enumerate(current_player.hand):
            card = cards_by_id.get(card_id)
            label = card.name if card is not None else card_id
            lines.append(f"  {index}: {label} ({card_id})")
    else:
        lines.append("  (empty)")

    lines.append("")
    lines.append("Market row:")
    if state.market.row:
        for index, card_id in enumerate(state.market.row):
            card = cards_by_id.get(card_id)
            label = card.name if card is not None else card_id
            lines.append(f"  {index}: {label} ({card_id})")
    else:
        lines.append("  (empty)")

    lines.append("")
    lines.append("Board occupancy:")
    for node_definition in state.definition.board.nodes:
        node_state = state.board.nodes[node_definition.node_id]
        troop_slots = ", ".join(slot if slot is not None else "_" for slot in node_state.troop_slots)
        spies = ", ".join(sorted(node_state.spies)) or "none"
        control = _derive_control(node_state.troop_slots) or "none"
        lines.append(
            f"  {node_definition.node_id} [{node_definition.kind.value}]: "
            f"troops=[{troop_slots}] spies={spies} control={control} vp_tokens={node_state.vp_tokens}"
        )

    return "\n".join(lines)


def render_legal_moves(state: GameState) -> str:
    """Render legal move payloads for the active player."""

    moves = legal_moves(state)
    if not moves:
        return "No legal moves."

    lines = ["Legal moves:"]
    for move in moves:
        lines.append(f"  - {move.model_dump()}")
    return "\n".join(lines)
