"""Orcus card behavior tests — steal from trophy hall and deploy (two-step)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from engine_c.bindings.engine_bindings import _lib
from engine_c.bindings.session import CSession

SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data" / "scenarios" / "batch_card_generation" / "037_seed_4_orcus.json"
)


def _trophy_hall(session: CSession, player_id: str) -> list[str]:
    s = session._state._ptr.contents
    for i in range(s.player_count):
        pid = _lib.intern_str(s.player_ids[i]).decode()
        if pid == player_id:
            ps = s.players[i]
            return [
                _lib.intern_str(ps.trophy_hall[j]).decode()
                for j in range(ps.trophy_hall_count)
            ]
    return []


def _resource(session: CSession, resource: str) -> int:
    s = session._state._ptr.contents
    rp = s.resource_pool
    if resource == "power":
        return rp.power
    if resource == "influence":
        return rp.influence
    return 0


def _played_cards(session: CSession, player_id: str) -> list[str]:
    s = session._state._ptr.contents
    for i in range(s.player_count):
        pid = _lib.intern_str(s.player_ids[i]).decode()
        if pid == player_id:
            ps = s.players[i]
            return [
                _lib.intern_str(ps.played_cards[j]).decode()
                for j in range(ps.played_cards_count)
            ]
    return []


def _board_troops(session: CSession, node_id: str) -> list[str | None]:
    s = session._state._ptr.contents
    for i in range(s.node_count):
        nid = _lib.intern_str(s.nodes[i].node_id).decode()
        if nid == node_id:
            ns = s.nodes[i]
            return [
                _lib.intern_str(ns.troop_slots[j]).decode() if ns.troop_slots[j] else None
                for j in range(ns.troop_slot_count)
            ]
    return []


def test_orcus_full_sequence() -> None:
    """Orcus: devour hand card for 5 power, assassinate 2, then optionally
    steal up to 2 troops from any trophy hall via two-step selection."""
    session = CSession.load(str(SCENARIO_PATH))

    power_before = _resource(session, "power")

    # 1. Play Orcus
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data["card_id"] == "orcus":
            session.submit_move(m)
            break
    else:
        session.destroy()
        pytest.fail("Orcus not playable")

    # 2. Devour a hand card
    devour_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    devour_soldier = [m for m in devour_moves if m.data["action_id"] == "soldier"]
    assert devour_soldier, f"No soldier target for devour, got: {[m.data.get('action_id') for m in devour_moves]}"
    session.submit_move(devour_soldier[0])

    # 3+4. Power gain auto-resolves; first assassination
    moves = session.legal_moves()
    assert moves and moves[0].move_type == "resolve_generic", f"Expected resolve_generic, got {moves[0].move_type}"
    session.submit_move(moves[0])

    # 5. Second assassination
    moves2 = session.legal_moves()
    assert moves2, "Should have second assassination moves"
    session.submit_move(moves2[0])

    # 6. Select trophy hall (first steal, step 1: pick player + trophy)
    steal_select = session.legal_moves()
    assert steal_select, "Should have trophy hall select moves"
    assert steal_select[0].move_type == "resolve_generic"
    assert steal_select[0].data["action_id"] is None, "First move should be skip"

    non_skip = [m for m in steal_select if m.move_type == "resolve_generic" and m.data["action_id"] is not None]
    assert len(non_skip) > 0, "Should have at least one trophy to steal"

    choice = non_skip[0]
    source_player = choice.data["action_id"]
    trophy_index = int(choice.data["target_id"])
    trophies_before = _trophy_hall(session, source_player)
    assert trophy_index < len(trophies_before), f"Invalid trophy index {trophy_index}"

    session.submit_move(choice)

    # 7. Place on board (first steal, step 2: pick destination)
    dst_moves = session.legal_moves()
    assert dst_moves, "Should have destination placement moves"
    assert all(m.move_type == "resolve_generic" for m in dst_moves), "All should be resolve_generic"

    first_dst = dst_moves[0]
    dst_node = first_dst.data["action_id"]
    dst_tid = first_dst.data["target_id"]

    # Verify target_id composite: source_player:trophy_index:node_id:slot
    assert dst_tid is not None
    parts = dst_tid.split(":")
    assert len(parts) == 4, f"Target should be source:index:node:slot, got {dst_tid}"

    session.submit_move(first_dst)

    # Verify trophy was removed from source hall
    trophies_after = _trophy_hall(session, source_player)
    assert len(trophies_after) == len(trophies_before) - 1, (
        f"Trophy hall for {source_player} should decrease: "
        f"{len(trophies_before)} -> {len(trophies_after)}"
    )

    # Verify trophy was placed on board
    troops = _board_troops(session, dst_node)
    stolen_owner = trophies_before[trophy_index]
    assert stolen_owner in troops, (
        f"Stolen trophy {stolen_owner} should be on board at {dst_node}"
    )

    # 8. Second steal: skip it
    steal_select2 = session.legal_moves()
    skip2 = [m for m in steal_select2 if m.move_type == "resolve_generic" and m.data["action_id"] is None]
    assert skip2, "Should have skip option for second steal"
    session.submit_move(skip2[0])

    # Card should be resolved
    played = _played_cards(session, "p2")
    assert "orcus" in played, "Orcus should be in played cards"

    power_after = _resource(session, "power")
    assert power_after >= power_before + 5, (
        f"Power should increase by at least 5: {power_before} -> {power_after}"
    )

    session.destroy()


def test_orcus_steal_deploys_anywhere_including_routes() -> None:
    """The stolen trophy may be placed anywhere on the board, routes included."""
    session = CSession.load(str(SCENARIO_PATH))

    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data["card_id"] == "orcus":
            session.submit_move(m)
            break
    else:
        session.destroy()
        pytest.fail("Orcus not playable")

    devour_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    session.submit_move(devour_moves[0])
    session.submit_move(session.legal_moves()[0])  # assassinate 1
    session.submit_move(session.legal_moves()[0])  # assassinate 2

    steal_select = session.legal_moves()
    non_skip = [m for m in steal_select if m.move_type == "resolve_generic" and m.data["action_id"] is not None]
    assert non_skip, "Should have a trophy to steal"
    session.submit_move(non_skip[0])

    dst_moves = session.legal_moves()
    assert dst_moves, "Should have destination placement moves"
    route_dsts = [
        m for m in dst_moves
        if m.move_type == "resolve_generic"
        and m.data["action_id"] is not None
        and str(m.data["action_id"]).startswith("route_")
    ]
    assert route_dsts, (
        f"Should be able to deploy to a route (anywhere on board), "
        f"got dst action_ids: {[m.data['action_id'] for m in dst_moves]}"
    )
    session.destroy()


def test_orcus_skip_both_steals() -> None:
    """Orcus: skip both steal opportunities when there are available targets.
    The card should still resolve successfully."""
    session = CSession.load(str(SCENARIO_PATH))

    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data["card_id"] == "orcus":
            session.submit_move(m)
            break
    else:
        session.destroy()
        pytest.fail("Orcus not playable")

    # Devour
    moves = session.legal_moves()
    session.submit_move(moves[0])

    # Assassinate 1
    moves = session.legal_moves()
    session.submit_move(moves[0])

    # Assassinate 2
    moves = session.legal_moves()
    session.submit_move(moves[0])

    # Skip first steal
    steal1 = session.legal_moves()
    skip1 = [m for m in steal1 if m.move_type == "resolve_generic" and m.data["action_id"] is None]
    assert skip1, "Should have skip for first steal"
    session.submit_move(skip1[0])

    # Skip second steal
    steal2 = session.legal_moves()
    skip2 = [m for m in steal2 if m.move_type == "resolve_generic" and m.data["action_id"] is None]
    assert skip2, "Should have skip for second steal"
    session.submit_move(skip2[0])

    # Card should be resolved
    played = _played_cards(session, "p2")
    assert "orcus" in played, "Orcus should be in played cards"

    session.destroy()
