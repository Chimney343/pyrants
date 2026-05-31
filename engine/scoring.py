"""Scoring helpers for end-of-turn and final-score calculations."""

from __future__ import annotations

from engine.state import CardDefinition, GameState, NodeKind, card_index, board_index


def _count_troops(node_troop_slots: list[str | None], player_id: str) -> int:
    return sum(1 for occupant in node_troop_slots if occupant == player_id)


def _site_control_owner(state: GameState, node_id: str) -> str | None:
    node_state = state.board.nodes[node_id]
    counts: dict[str, int] = {}

    for occupant in node_state.troop_slots:
        if occupant is None:
            continue
        counts[occupant] = counts.get(occupant, 0) + 1

    if not counts:
        return None

    max_count = max(counts.values())
    leaders = [player_id for player_id, count in counts.items() if count == max_count]
    if len(leaders) != 1:
        return None

    return leaders[0]


def _is_total_control(state: GameState, node_id: str, player_id: str) -> bool:
    node_state = state.board.nodes[node_id]
    has_enemy_spies = any(spy_owner != player_id for spy_owner in node_state.spies)
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


def sync_site_control_markers(state: GameState) -> GameState:
    """Apply unique troop-majority control to site markers without clearing ties."""

    updated = state.model_copy(deep=True)
    board_definition_index = board_index(updated.definition.board)

    for node_id, node_definition in board_definition_index.items():
        if node_definition.kind != NodeKind.SITE:
            continue

        control_owner = _site_control_owner(updated, node_id)
        if control_owner is not None:
            updated.board.nodes[node_id].control_marker = control_owner

    return updated


def award_end_of_turn_site_vp(state: GameState, player_id: str) -> GameState:
    """Add VP from currently controlled sites to a player's running score."""

    updated = sync_site_control_markers(state)
    board_definition_index = board_index(updated.definition.board)

    site_vp = 0
    for node_id, node_definition in board_definition_index.items():
        if node_definition.kind != NodeKind.SITE:
            continue

        if updated.board.nodes[node_id].control_marker == player_id:
            site_vp += node_definition.vp_value

    updated.players[player_id].score += site_vp
    return updated


def compute_final_scores(state: GameState) -> dict[str, int]:
    """Compute final VP tally from map, deck, inner-circle, trophies, and tokens."""

    synced = sync_site_control_markers(state)
    definition_by_node = board_index(synced.definition.board)
    card_by_id = card_index(synced.definition.catalog)
    totals: dict[str, int] = {}

    for player_id, player_state in synced.players.items():
        map_vp = 0
        total_control_bonus = 0

        for node_id, node_definition in definition_by_node.items():
            if node_definition.kind != NodeKind.SITE:
                continue

            control_owner = synced.board.nodes[node_id].control_marker
            if control_owner == player_id:
                map_vp += node_definition.vp_value

            if _is_total_control(synced, node_id, player_id):
                total_control_bonus += 2

        trophy_vp = len(player_state.trophy_hall)
        token_vp = player_state.vp_tokens
        deck_zone_cards = player_state.deck + player_state.hand + player_state.discard_pile
        deck_vp = _cards_vp(deck_zone_cards, card_by_id, "deck_vp")
        inner_circle_vp = _cards_vp(player_state.inner_circle, card_by_id, "inner_circle_vp")

        totals[player_id] = (
            player_state.score
            + map_vp
            + total_control_bonus
            + trophy_vp
            + token_vp
            + deck_vp
            + inner_circle_vp
        )

    return totals
