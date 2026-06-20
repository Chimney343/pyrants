"""Gibbering Mouther card behavior tests."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from engine_c.bindings.engine_bindings import _lib
from engine_c.bindings.session import CSession
from engine_c.bindings.view import build_c_game_view

SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data" / "scenarios" / "batch_card_generation" / "026_seed_4_gibbering_mouther.json"
)


def _discard_ids(session: CSession, player_id: str) -> list[str]:
    s = session._state._ptr.contents
    for i in range(s.player_count):
        pid = _lib.intern_str(s.player_ids[i]).decode()
        if pid == player_id:
            ps = s.players[i]
            return [_lib.intern_str(ps.discard_pile[j]).decode() for j in range(ps.discard_pile_count)]
    return []


def _count_empty_slots(session: CSession, site_id: str) -> int:
    s = session._state._ptr.contents
    site_sym = _lib.intern(site_id.encode())
    for i in range(s.node_count):
        if s.nodes[i].node_id == site_sym:
            return sum(1 for j in range(s.nodes[i].troop_slot_count) if s.nodes[i].troop_slots[j] == 0)
    return 0


def _add_player_to_site(session: CSession, site_id: str, player_id: str) -> None:
    s = session._state._ptr.contents
    site_sym = _lib.intern(site_id.encode())
    player_sym = _lib.intern(player_id.encode())
    for i in range(s.node_count):
        if s.nodes[i].node_id == site_sym:
            for j in range(s.nodes[i].troop_slot_count - 1, -1, -1):
                if s.nodes[i].troop_slots[j] == 0:
                    s.nodes[i].troop_slots[j] = player_sym
                    return
            break


def _play_card(session: CSession) -> None:
    for m in session.legal_moves():
        if getattr(m, "move_type", "") == "play_card" and m.data.get("card_id") == "gibbering_mouther":
            session.submit_move(m)
            return
    pytest.fail("Gibbering Mouther not in hand")


def _deploy_site(move) -> str | None:
    return move.data.get("action_id")


def test_gibbering_mouther_selects_player_and_gives_insane_outcast() -> None:
    """After deploying 2 troops, player selects an opponent with presence,
    and that opponent receives an Insane Outcast."""
    session = CSession.load(str(SCENARIO_PATH))

    _play_card(session)

    view = build_c_game_view(session)
    deploy_moves = [v for v in view.legal_moves if v.move_type == "resolve_generic"]
    assert deploy_moves, "No deploy moves"
    session.submit_move(deploy_moves[0].move)

    view = build_c_game_view(session)
    deploy_moves2 = [v for v in view.legal_moves if v.move_type == "resolve_generic"]
    assert deploy_moves2, "No second deploy move"

    chosen = None
    chosen_site = None
    for v in deploy_moves2:
        site = _deploy_site(v.move)
        if site and _count_empty_slots(session, site) >= 2:
            chosen = v.move
            chosen_site = site
            break
    assert chosen is not None, "No deploy move to a site with >=2 empty slots"

    _add_player_to_site(session, chosen_site, "p1")
    session.submit_move(chosen)

    view = build_c_game_view(session)
    player_select = [v for v in view.legal_moves if v.move_type == "resolve_generic"]
    assert player_select, f"Expected player selection, got: {[v.label for v in view.legal_moves]}"

    p1_move = [v for v in player_select if _deploy_site(v.move) == "p1"]
    if p1_move:
        session.submit_move(p1_move[0].move)
    else:
        pytest.fail(f"No p1 selection in: {[v.label for v in player_select]}")

    p1_after = _discard_ids(session, "p1")
    assert "insane_outcast" in p1_after, f"Expected Insane Outcast in p1 discard: {p1_after}"

    s = session._state._ptr.contents
    assert not s.pending_generic, "Card should be fully resolved"

    session.destroy()


def test_gibbering_mouther_no_target_skips_effect() -> None:
    """When no opponent has presence on the deploy sites, the Insane Outcast
    effect is skipped and the card resolves cleanly."""
    session = CSession.load(str(SCENARIO_PATH))

    p1_before = _discard_ids(session, "p1")
    p3_before = _discard_ids(session, "p3")
    p4_before = _discard_ids(session, "p4")

    _play_card(session)

    view = build_c_game_view(session)
    deploy = [v for v in view.legal_moves if v.move_type == "resolve_generic"]
    assert deploy, "No deploy moves"
    session.submit_move(deploy[0].move)

    view = build_c_game_view(session)
    deploy2 = [v for v in view.legal_moves if v.move_type == "resolve_generic"]
    assert deploy2, "No second deploy move"
    session.submit_move(deploy2[0].move)

    p1_after = _discard_ids(session, "p1")
    p3_after = _discard_ids(session, "p3")
    p4_after = _discard_ids(session, "p4")

    assert p1_after == p1_before, "p1 should not have received an Insane Outcast"
    assert p3_after == p3_before, "p3 should not have received an Insane Outcast"
    assert p4_after == p4_before, "p4 should not have received an Insane Outcast"

    s = session._state._ptr.contents
    assert not s.pending_generic, "Card should be fully resolved"

    session.destroy()
