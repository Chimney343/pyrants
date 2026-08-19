"""Ogre Zombie card behavior tests.

Ogre Zombie (4-cost, Conquest/Undead):
  Supplant a white troop anywhere.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from engine_c.bindings.engine_bindings import _lib
from engine_c.bindings.session import CSession
from game_setup.loaders import assemble_catalog_payload
from tests.c_engine.card_test_helpers import (
    _make_engine,
    _session_player_index,
    _sptr,
    make_card_test_session,
)

CARD_ID = "ogre_zombie"
_SITE_A = "site_gauntlgrym"
_SITE_B = "site_menzoberranzan"

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _play_card(session: CSession, card_id: str = CARD_ID) -> None:
    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == card_id:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"{card_id} not in hand")


def _has_pending_generic(session: CSession) -> bool:
    return bool(_sptr(session).contents.pending_generic)


def _trophy_hall(session: CSession, pid: str) -> list[str]:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return []
    ps = _sptr(session).contents.players[pi]
    return [_lib.intern_str(ps.trophy_hall[i]).decode() for i in range(ps.trophy_hall_count)]


def _troops_at_node(session: CSession, node_id: str) -> list[str | None]:
    s = _sptr(session).contents
    nid = _lib.intern(node_id.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            ns = s.nodes[ni]
            result = []
            for i in range(ns.troop_slot_count):
                occ = ns.troop_slots[i]
                result.append(_lib.intern_str(occ).decode() if occ else None)
            return result
    return []


def _resolve_generic_moves(session: CSession) -> list:
    return [m for m in session.legal_moves() if m._move_type == "resolve_generic"]


def _pick_supplant_target(session: CSession, node_id: str, slot_index: int) -> None:
    for m in _resolve_generic_moves(session):
        if m.data.get("action_id") == node_id:
            tid = m.data.get("target_id", "")
            if tid == str(slot_index):
                session.submit_move(m)
                return
    session.destroy()
    raise AssertionError(f"Supplant move for {node_id} slot {slot_index} not found")


def test_ogre_zombie_execution_model() -> None:
    catalog = assemble_catalog_payload(DATA_DIR / "cards")
    cards = catalog if isinstance(catalog, list) else catalog.get("cards", catalog)
    card = next(c for c in cards if c.get("card_id") == "ogre_zombie")

    actions = card["execution_model"]["actions"]
    assert len(actions) == 1

    supplant = actions[0]
    assert supplant["op"] == "supplant_troop"
    assert supplant["target_scope"] == "board_site"
    assert supplant["filters"] == ["white_troop_only"]
    assert supplant["metadata"]["ignore_presence_requirement"] is True
    assert supplant["metadata"]["targeting"] == "anywhere"
    assert supplant["optional"] is False
    assert supplant["quantity"] == {"kind": "unspecified", "value": None}

    assert "Supplant a white troop" in card["rules_text"]
    assert card["cost"] == 4
    assert card["aspect"] == "conquest"
    assert "undead" in card["secondary_aspects"]
    assert card["deck_vp"] == 2
    assert card["inner_circle_vp"] == 4


def test_ogre_zombie_supplants_white_troop_with_presence():
    """Supplant a white troop at a site where the player already has presence."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": [CARD_ID]},
        troops={"p1": {_SITE_A: ["p1", "white", None]}},
        current_player="p1",
    )

    _play_card(session)

    supplant_moves = _resolve_generic_moves(session)
    assert supplant_moves, "Expected supplant moves"
    session.submit_move(supplant_moves[0])

    assert not _has_pending_generic(session)

    troops = _troops_at_node(session, _SITE_A)
    assert "white" not in troops, f"White should be replaced, got {troops}"
    assert "p1" in troops, "p1 troop should have replaced white"
    assert "white" in _trophy_hall(session, "p1"), "White goes to p1's trophy hall"
    session.destroy()


def test_ogre_zombie_supplants_white_troop_without_presence():
    """Supplant a white troop at a site where the player has NO presence."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": [CARD_ID]},
        troops={"p2": {_SITE_B: ["p2", "white", None]}},
        current_player="p1",
    )

    _play_card(session)

    supplant_moves = _resolve_generic_moves(session)
    assert supplant_moves, "Expected supplant moves even without presence"
    site_b_move = [m for m in supplant_moves if m.data.get("action_id") == _SITE_B]
    assert site_b_move, f"Expected supplant move for {_SITE_B}"
    session.submit_move(site_b_move[0])

    assert not _has_pending_generic(session)

    troops = _troops_at_node(session, _SITE_B)
    assert "white" not in troops, f"White should be replaced at {_SITE_B}, got {troops}"
    assert "p1" in troops, f"p1 should have troop at {_SITE_B}, got {troops}"
    assert "white" in _trophy_hall(session, "p1"), "White goes to p1's trophy hall"
    session.destroy()


def test_ogre_zombie_only_supplants_white_troops():
    """Supplant moves target only white troops, skipping player-owned troops."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": [CARD_ID]},
        troops={"p1": {_SITE_A: ["p1", "p2", "white"]}},
        current_player="p1",
    )

    _play_card(session)

    supplant_moves = _resolve_generic_moves(session)
    site_a_moves = [m for m in supplant_moves if m.data.get("action_id") == _SITE_A]
    assert site_a_moves, "Expected supplant move for white at _SITE_A"
    slot_ids = [m.data.get("target_id") for m in site_a_moves]
    assert "0" not in slot_ids, "Slot 0 (p1 own troop) should not be supplantable"
    assert "1" not in slot_ids, "Slot 1 (p2 troop) should not be supplantable"
    assert "2" in slot_ids, "Slot 2 (white troop) should be supplantable"
    session.destroy()


def test_ogre_zombie_supplant_from_scenario_state():
    """Use the batch scenario state and verify supplant works."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2", "p3", "p4"],
        hand={"p3": [CARD_ID]},
        troops={
            "p3": {
                "site_gauntlgrym": ["white", "white", "p3"],
                "site_gracklstugh": ["white", "white", "p1", "p3"],
            },
        },
        current_player="p3",
    )

    _play_card(session)

    supplant_moves = _resolve_generic_moves(session)
    assert supplant_moves, "Expected supplant moves for white troops"
    session.submit_move(supplant_moves[0])

    assert not _has_pending_generic(session)
    assert "white" in _trophy_hall(session, "p3"), "Supplant takes white to trophy hall"
    session.destroy()
