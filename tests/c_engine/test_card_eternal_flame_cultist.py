"""Eternal Flame Cultist card behavior tests.

Assassinate a troop. If the focus condition is met for Malice, gain 2 power.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from engine_c.bindings.ce_api import CEngine
from engine_c.bindings.engine_bindings import _lib
from engine_c.bindings.session import CSession
from tests.c_engine.card_test_helpers import make_card_test_session

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


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


def _node_troop_slots(session: CSession, node_id: str) -> list[str | None]:
    s = session._state._ptr.contents
    nid = _lib.intern(node_id.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            ns = s.nodes[ni]
            result = []
            for t in range(ns.troop_slot_count):
                occ = ns.troop_slots[t]
                result.append(_lib.intern_str(occ).decode() if occ != 0 else None)
            return result
    return []


def _resource_power(session: CSession) -> int:
    return session._state._ptr.contents.resource_pool.power


def _resolve_generic_moves(session: CSession) -> list:
    return [m for m in session.legal_moves() if getattr(m, "move_type", "") == "resolve_generic"]


def test_eternal_flame_cultist_assassinates_troop_without_focus_bonus():
    """Without a malice focus card, only assassinate happens. No power gain."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards" / "catalog.json"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["eternal_flame_cultist"]},
        troops={"p2": {"site_gauntlgrym": ["p2", None, None]}},
        spies={"site_gauntlgrym": ["p1"]},
        current_player="p1",
    )

    trophy_before = len(_trophy_hall(session, "p1"))
    power_before = _resource_power(session)
    gaunt_before = _node_troop_slots(session, "site_gauntlgrym")
    assert "p2" in gaunt_before, f"p2 troop should be at site_gauntlgrym: {gaunt_before}"

    for m in session.legal_moves():
        if getattr(m, "move_type", "") == "play_card" and m.data.get("card_id") == "eternal_flame_cultist":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("eternal_flame_cultist not in hand")

    rg_moves = _resolve_generic_moves(session)
    assert len(rg_moves) >= 1, f"Expected at least 1 resolve_generic for assassinate, got {len(rg_moves)}"
    assert rg_moves[0].data.get("target_id") == "0", (
        f"Assassinate should target slot 0 (p2 troop), got {rg_moves[0].data}"
    )

    session.submit_move(rg_moves[0])

    gaunt_after = _node_troop_slots(session, "site_gauntlgrym")
    assert "p2" not in gaunt_after, f"p2 troop should be assassinated: {gaunt_after}"

    trophy_after = len(_trophy_hall(session, "p1"))
    assert trophy_after == trophy_before + 1, (
        f"Trophy hall should have +1 assassinated troop, got {trophy_after} (was {trophy_before})"
    )

    assert _resource_power(session) == power_before, (
        f"Power should not change without malice focus. Before: {power_before}, After: {_resource_power(session)}"
    )

    final_gen = _resolve_generic_moves(session)
    assert len(final_gen) == 0, (
        f"Expected 0 resolve_generic after assassinate (no focus), got {len(final_gen)}"
    )

    session.destroy()


def test_eternal_flame_cultist_focus_bonus_gains_power():
    """With a malice focus card in hand, assassinate + gain 2 power."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards" / "catalog.json"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["eternal_flame_cultist", "blackguard"]},
        troops={"p2": {"site_gauntlgrym": ["p2", None, None]}},
        spies={"site_gauntlgrym": ["p1"]},
        current_player="p1",
    )

    trophy_before = len(_trophy_hall(session, "p1"))
    power_before = _resource_power(session)
    gaunt_before = _node_troop_slots(session, "site_gauntlgrym")
    assert "p2" in gaunt_before, f"p2 troop should be at site_gauntlgrym: {gaunt_before}"

    for m in session.legal_moves():
        if getattr(m, "move_type", "") == "play_card" and m.data.get("card_id") == "eternal_flame_cultist":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("eternal_flame_cultist not in hand")

    rg_moves = _resolve_generic_moves(session)
    assert len(rg_moves) >= 1, f"Expected at least 1 resolve_generic for assassinate, got {len(rg_moves)}"
    assert rg_moves[0].data.get("target_id") == "0", "Assassinate should target the p2 troop slot"

    session.submit_move(rg_moves[0])

    gaunt_mid = _node_troop_slots(session, "site_gauntlgrym")
    assert "p2" not in gaunt_mid, f"p2 troop should be assassinated: {gaunt_mid}"

    assert _resource_power(session) == power_before + 2, (
        f"Should gain 2 power from malice focus. Before: {power_before}, After: {_resource_power(session)}"
    )

    trophy_after = len(_trophy_hall(session, "p1"))
    assert trophy_after == trophy_before + 1, (
        f"Trophy hall should have +1 assassinated troop, got {trophy_after} (was {trophy_before})"
    )

    final_gen = _resolve_generic_moves(session)
    assert len(final_gen) == 0, (
        f"Expected 0 resolve_generic after all actions, got {len(final_gen)}"
    )

    session.destroy()


def test_eternal_flame_cultist_no_valid_target_auto_resolves():
    """When no troop exists on board, card resolves with no effect and no pending state."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards" / "catalog.json"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["eternal_flame_cultist", "noble"]},
        current_player="p1",
    )

    trophies_before = len(_trophy_hall(session, "p1"))
    power_before = _resource_power(session)

    for m in session.legal_moves():
        if getattr(m, "move_type", "") == "play_card" and m.data.get("card_id") == "eternal_flame_cultist":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("eternal_flame_cultist not in hand")

    gen_moves = _resolve_generic_moves(session)
    assert len(gen_moves) == 0, (
        f"Expected 0 resolve_generic with no troops, got {len(gen_moves)}"
    )

    s = session._state._ptr.contents
    assert not s.pending_generic, "pending_generic should be cleared when no targets"

    assert len(_trophy_hall(session, "p1")) == trophies_before, "Trophy hall unchanged"
    assert _resource_power(session) == power_before, "Power unchanged"

    move_types = {getattr(m, "move_type", "") for m in session.legal_moves()}
    assert "play_card" in move_types, "Should still be able to play other cards"
    assert "end_main_phase" in move_types, "Should be able to end main phase"

    session.destroy()


def test_eternal_flame_cultist_catalog_structure():
    """Verify execution_model: sequence with assassinate_troop + conditional_bonus for malice focus."""
    catalog_path = DATA_DIR / "cards" / "catalog.json"
    with open(catalog_path, encoding="utf-8") as f:
        catalog = json.load(f)

    card = None
    for c in catalog["cards"]:
        if c["card_id"] == "eternal_flame_cultist":
            card = c
            break
    assert card is not None, "Eternal Flame Cultist not found in catalog"

    assert card["cost"] == 4
    assert card["aspect"] == "malice"

    em = card["execution_model"]
    assert em["kind"] == "sequence", f"Expected sequence, got {em['kind']}"
    actions = em["actions"]
    assert len(actions) == 2, f"Expected 2 actions, got {len(actions)}"

    a1 = actions[0]
    assert a1["op"] == "assassinate_troop", f"action_1 should be assassinate_troop, got {a1['op']}"
    assert a1["optional"] is False, "action_1 must be mandatory"

    a2 = actions[1]
    assert a2["op"] == "conditional_bonus", f"action_2 should be conditional_bonus, got {a2['op']}"
    assert a2["metadata"]["condition"] == "focus_aspect_present"
    assert a2["metadata"]["focus_aspect"] == "malice"
    assert a2["metadata"]["resource"] == "power"
    assert a2["metadata"]["amount"] == 2

    top_actions = card.get("actions", [])
    assert len(top_actions) == 2
    assert top_actions[0]["optional"] is False
    assert top_actions[1]["optional"] is False
