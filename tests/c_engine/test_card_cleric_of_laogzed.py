"""Cleric of Laogzed: Move an enemy troop. At end of turn, promote a different played card."""

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
        catalog_path=str(DATA_DIR / "cards" / "catalog.json"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    return eng


def test_move_troop_only_targets_enemy_troops() -> None:
    """move_troop should only target enemy player troops, not white or own."""
    eng = _init_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["cleric_of_laogzed"]},
        troops={"p1": {"site_gauntlgrym": ["p1"]}},
        current_player="p1",
    )
    s = session._state._ptr.contents
    nid = _lib.intern(b"site_gauntlgrym")
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            s.nodes[ni].troop_slots[0] = _lib.intern(b"p1")
            s.nodes[ni].troop_slots[1] = _lib.intern(b"white")
            s.nodes[ni].troop_slots[2] = _lib.intern(b"p2")
            s.nodes[ni].troop_slot_count = 4
            break

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "cleric_of_laogzed":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Cleric of Laogzed not playable")

    target_source_slots = set()
    for m in session.legal_moves():
        if m._move_type == "resolve_generic" and m.data.get("target_id"):
            tid = str(m.data["target_id"])
            if ":" in tid:
                src_slot = tid.split(":")[0]
                target_source_slots.add(src_slot)

    assert "1" not in target_source_slots, "Slot 1 (white troop) should NOT be a legal move target"
    assert "2" in target_source_slots, "Slot 2 (p2/enemy troop) should be a legal move target"

    session.destroy()


def test_promote_cannot_target_self() -> None:
    """End-of-turn promote should NOT let Cleric of Laogzed promote itself."""
    eng = _init_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["cleric_of_laogzed", "noble"]},
        troops={"p1": {"site_gauntlgrym": ["p1", "p2"]}},
        current_player="p1",
    )

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "cleric_of_laogzed":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Cleric of Laogzed not playable")

    resolved_move = False
    for m in session.legal_moves():
        if m._move_type == "resolve_generic":
            session.submit_move(m)
            resolved_move = True
            break
    assert resolved_move, "Should have a move troop resolve move"

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "noble":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Noble should be playable after cleric")

    for m in session.legal_moves():
        if m._move_type == "end_main_phase":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Should have end_main_phase")

    self_as_target = False
    other_targets = []
    for m in session.legal_moves():
        if m._move_type == "promote_card":
            cid = m.data.get("card_id", "")
            if cid == "cleric_of_laogzed":
                self_as_target = True
            else:
                other_targets.append(cid)

    assert not self_as_target, (
        f"Cleric of Laogzed should NOT be a promote target. Other targets: {other_targets}"
    )
    assert len(other_targets) > 0, "Should have at least one other promote target"

    session.destroy()
