"""Scoring helpers for end-of-turn and final-score calculations."""

from __future__ import annotations

from engine.state import CardDefinition, GameState, NodeKind, _cow_player, board_index, card_index


def _count_troops(node_troop_slots: list[str | None], player_id: str) -> int:
    return sum(1 for occupant in node_troop_slots if occupant == player_id)


def _site_control_owner(state: GameState, node_id: str) -> str | None:
    node_state = state.board.nodes[node_id]
    counts: dict[str, int] = {}

    for occupant in node_state.troop_slots:
        if occupant is not None:
            counts[occupant] = counts.get(occupant, 0) + 1

    if not counts:
        return None

    max_count = max(counts.values())
    leaders = [owner for owner, count in counts.items() if count == max_count]
    return leaders[0] if len(leaders) == 1 and leaders[0] != "white" else None


def _is_total_control(state: GameState, node_id: str, player_id: str) -> bool:
    node_state = state.board.nodes[node_id]
    has_enemy_spies = bool(node_state.spies - {player_id})
    all_troops_owned = all(slot_owner == player_id for slot_owner in node_state.troop_slots)
    return all_troops_owned and not has_enemy_spies


def _cards_vp(cards: list[str], index: dict[str, CardDefinition], field_name: str) -> int:
    total = 0
    for card_id in cards:
        card = index.get(card_id)
        if card is None:
            continue
        total += getattr(card, field_name)
    return total


def award_end_of_turn_site_vp(state: GameState, player_id: str) -> GameState:
    """Add end-of-turn VP from sites where the player has total control."""

    updated = state._cow_clone()
    board_definition_index = board_index(updated.definition.board)

    site_vp = 0
    for node_id, node_definition in board_definition_index.items():
        if node_definition.kind != NodeKind.SITE:
            continue

        if _is_total_control(updated, node_id, player_id):
            site_vp += node_definition.total_control_vp_per_turn

    _cow_player(updated, player_id).score += site_vp
    return updated


def compute_final_scores(state: GameState) -> dict[str, int]:
    """Compute final VP tally from map, deck, inner-circle, trophies, and tokens."""

    definition_by_node = board_index(state.definition.board)
    card_by_id = card_index(state.definition.catalog)
    totals: dict[str, int] = {}

    for player_id, player_state in state.players.items():
        total_vp = player_state.score

        for node_id, node_definition in definition_by_node.items():
            if node_definition.kind != NodeKind.SITE:
                continue

            if _site_control_owner(state, node_id) == player_id:
                total_vp += node_definition.control_vp

        trophy_vp = len(player_state.trophy_hall)
        token_vp = player_state.vp_tokens
        deck_zone_cards = player_state.deck + player_state.hand + player_state.discard_pile
        deck_vp = _cards_vp(deck_zone_cards, card_by_id, "deck_vp")
        inner_circle_vp = _cards_vp(player_state.inner_circle, card_by_id, "inner_circle_vp")

        totals[player_id] = (
            total_vp
            + trophy_vp
            + token_vp
            + deck_vp
            + inner_circle_vp
        )

    return totals
