"""Balor card: devour a card from hand, supplant a white troop anywhere, deploy 1 troop."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from engine_c.bindings.ce_api import CEngine
from engine_c.bindings.engine_bindings import _lib
from tests.c_engine.card_test_helpers import make_card_test_session

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _init_engine() -> CEngine:
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    return eng


def _set_white_at(session, node_names: list[str]) -> None:
    s = session._state._ptr.contents
    for name in node_names:
        nid = _lib.intern(name.encode())
        for ni in range(s.node_count):
            if s.nodes[ni].node_id == nid:
                s.nodes[ni].troop_slots[0] = _lib.intern(b"white")
                if s.nodes[ni].troop_slot_count < 1:
                    s.nodes[ni].troop_slot_count = 1
                break


def _set_enemy_at(session, node_name: str, enemy: str) -> None:
    s = session._state._ptr.contents
    nid = _lib.intern(node_name.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            s.nodes[ni].troop_slots[0] = _lib.intern(enemy.encode())
            if s.nodes[ni].troop_slot_count < 1:
                s.nodes[ni].troop_slot_count = 1
            break


def _find_resolve_move(session, action_id: str):
    for m in session.legal_moves():
        if m._move_type == "resolve_generic" and m.data.get("action_id") == action_id:
            return m
    return None


def test_balor_supplant_includes_sites_without_presence() -> None:
    """White troops at sites where the player has NO presence must be legal supplant targets."""
    eng = _init_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["balor", "noble"]},
        troops={"p1": {"route_1": ["p1"]}},
        current_player="p1",
    )
    _set_white_at(session, ["site_gauntlgrym", "site_jhachalkhyn"])

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "balor":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Balor not playable")

    m = _find_resolve_move(session, "noble")
    assert m, "Devour cost should offer Noble as a target"
    session.submit_move(m)

    supplant_targets = {
        m.data["action_id"]
        for m in session.legal_moves()
        if m._move_type == "resolve_generic" and m.data.get("action_id")
    }

    assert "site_gauntlgrym" in supplant_targets, (
        "site_gauntlgrym (with presence) should be a supplant target"
    )
    assert "site_jhachalkhyn" in supplant_targets, (
        "site_jhachalkhyn (without presence) should be a supplant target"
    )

    session.destroy()


def test_beholder_assassinate_requires_presence() -> None:
    """Without ignore_presence_requirement, sites without presence are NOT legal targets."""
    eng = _init_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["beholder"]},
        troops={"p1": {"route_1": ["p1"]}},
        current_player="p1",
    )
    _set_enemy_at(session, "site_gauntlgrym", "p2")
    _set_enemy_at(session, "site_jhachalkhyn", "p2")

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "beholder":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Beholder not playable")

    assassinate_targets = {
        m.data["action_id"]
        for m in session.legal_moves()
        if m._move_type == "resolve_generic" and m.data.get("action_id")
    }

    assert "site_gauntlgrym" in assassinate_targets, (
        "site_gauntlgrym (with presence) should be an assassinate target"
    )
    assert "site_jhachalkhyn" not in assassinate_targets, (
        "site_jhachalkhyn (without presence) should NOT be an assassinate target"
    )

    session.destroy()


def test_balor_end_to_end_supplant_anywhere() -> None:
    """Full Balor: devour noble, supplant white at site without presence, deploy 1 troop."""
    eng = _init_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["balor", "noble"]},
        troops={"p1": {"route_1": ["p1"]}},
        current_player="p1",
    )
    _set_white_at(session, ["site_jhachalkhyn"])
    s = session._state._ptr.contents
    pi = 0
    barracks_before = s.players[pi].barracks
    hand_count_before = s.players[pi].hand_count

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "balor":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Balor not playable")

    devour = _find_resolve_move(session, "noble")
    assert devour, "Devour should offer noble"
    session.submit_move(devour)

    supplant_moves = [
        m for m in session.legal_moves()
        if m._move_type == "resolve_generic"
        and m.data.get("action_id") == "site_jhachalkhyn"
    ]
    assert supplant_moves, "site_jhachalkhyn should be a legal supplant target"
    session.submit_move(supplant_moves[0])

    s = session._state._ptr.contents
    assert s.players[pi].hand_count == hand_count_before - 2, (
        "Balor and Noble should be gone from hand"
    )
    assert s.players[pi].barracks == barracks_before - 1, (
        "Supplant costs 1 barracks"
    )
    j_sym = _lib.intern(b"site_jhachalkhyn")
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == j_sym:
            assert s.nodes[ni].troop_slots[0] == _lib.intern(b"p1"), (
                "White troop at site_jhachalkhyn should be replaced by p1"
            )
            break

    deploy_moves = [
        m for m in session.legal_moves()
        if m._move_type == "resolve_generic" and m.data.get("action_id")
    ]
    assert deploy_moves, "Deploy should offer targets"
    session.submit_move(deploy_moves[0])

    s = session._state._ptr.contents
    assert s.players[pi].barracks == barracks_before - 2, (
        "Supplant + deploy cost 2 barracks total"
    )

    session.destroy()


def test_balor_ignore_presence_still_filters_white_only() -> None:
    """With ignore_presence, enemy troops at sites without presence are NOT legal targets."""
    eng = _init_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["balor", "noble"]},
        troops={"p1": {"route_1": ["p1"]}},
        current_player="p1",
    )
    _set_white_at(session, ["site_gauntlgrym"])
    _set_enemy_at(session, "site_jhachalkhyn", "p2")

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "balor":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Balor not playable")

    devour = _find_resolve_move(session, "noble")
    assert devour, "Devour should offer noble"
    session.submit_move(devour)

    supplant_targets = {
        m.data["action_id"]
        for m in session.legal_moves()
        if m._move_type == "resolve_generic" and m.data.get("action_id")
    }

    assert "site_gauntlgrym" in supplant_targets, (
        "site_gauntlgrym (white troop) should be a target"
    )
    assert "site_jhachalkhyn" not in supplant_targets, (
        "site_jhachalkhyn (p2 troop) should NOT be a target with white_troop_only filter"
    )

    session.destroy()
