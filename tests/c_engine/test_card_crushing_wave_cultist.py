"""Crushing Wave Cultist card behavior tests.

Assassinate a white troop. If the focus condition is met for Conquest, deploy 2 troops.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from engine_c.bindings.ce_api import CEngine
from engine_c.bindings.engine_bindings import _lib
from engine_c.bindings.session import CSession
from game_setup.loaders import assemble_catalog_payload
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


def _player_barracks(session: CSession, player_id: str) -> int:
    s = session._state._ptr.contents
    for i in range(s.player_count):
        pid = _lib.intern_str(s.player_ids[i]).decode()
        if pid == player_id:
            return s.players[i].barracks
    return 0


def _resolve_generic_moves(session: CSession) -> list:
    return [m for m in session.legal_moves() if getattr(m, "move_type", "") == "resolve_generic"]


def test_crushing_wave_cultist_assassinates_white_troop_without_focus_bonus() -> None:
    """Without a conquest focus card in hand, only assassinate happens. No deploy."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["crushing_wave_cultist"]},
        troops={"white": {"site_gauntlgrym": ["white", None, None]}},
        spies={"site_gauntlgrym": ["p1"]},
        current_player="p1",
    )

    trophy_before = len(_trophy_hall(session, "p1"))
    gaunt_before = _node_troop_slots(session, "site_gauntlgrym")
    assert "white" in gaunt_before, f"White troop should be at site_gauntlgrym: {gaunt_before}"
    barracks_before = _player_barracks(session, "p1")

    for m in session.legal_moves():
        if getattr(m, "move_type", "") == "play_card" and m.data.get("card_id") == "crushing_wave_cultist":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("crushing_wave_cultist not in hand")

    rg_moves = _resolve_generic_moves(session)
    assert len(rg_moves) >= 1, f"Expected at least 1 resolve_generic for assassinate, got {len(rg_moves)}"
    assert rg_moves[0].data.get("target_id") == "0", (
        f"Assassinate should target slot 0 (white troop), got {rg_moves[0].data}"
    )

    session.submit_move(rg_moves[0])

    gaunt_after = _node_troop_slots(session, "site_gauntlgrym")
    assert "white" not in gaunt_after, f"White troop should be assassinated: {gaunt_after}"
    assert _player_barracks(session, "p1") == barracks_before, "Barracks should not change (no deploy)"

    trophy_after = len(_trophy_hall(session, "p1"))
    assert trophy_after == trophy_before + 1, (
        f"Trophy hall should have +1 assassinated troop, got {trophy_after} (was {trophy_before})"
    )

    final_gen = _resolve_generic_moves(session)
    assert len(final_gen) == 0, (
        f"Expected 0 resolve_generic after assassinate (no focus), got {len(final_gen)}"
    )

    session.destroy()


def test_crushing_wave_cultist_focus_bonus_deploys_two_troops() -> None:
    """With a conquest focus card in hand, assassinate + 2 deploys happen."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["crushing_wave_cultist", "black_wyrmling"]},
        troops={"white": {"site_gauntlgrym": ["white", None, None]}},
        spies={"site_gauntlgrym": ["p1"]},
        current_player="p1",
    )

    gaunt_before = _node_troop_slots(session, "site_gauntlgrym")
    assert "white" in gaunt_before, f"White troop should be at site_gauntlgrym: {gaunt_before}"
    barracks_before = _player_barracks(session, "p1")
    trophies_before = len(_trophy_hall(session, "p1"))

    for m in session.legal_moves():
        if getattr(m, "move_type", "") == "play_card" and m.data.get("card_id") == "crushing_wave_cultist":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("crushing_wave_cultist not in hand")

    rg_moves = _resolve_generic_moves(session)
    assert len(rg_moves) == 1, f"Expected 1 resolve_generic (assassinate), got {len(rg_moves)}"
    assert rg_moves[0].data.get("target_id") == "0", "Assassinate should target the white troop slot"

    session.submit_move(rg_moves[0])

    gaunt_mid = _node_troop_slots(session, "site_gauntlgrym")
    assert "white" not in gaunt_mid, f"White troop should be assassinated: {gaunt_mid}"

    rg_moves2 = _resolve_generic_moves(session)
    deploy_count = len(rg_moves2)
    assert deploy_count >= 2, (
        f"Expected at least 2 deploy moves after assassinate with focus, got {deploy_count}"
    )

    session.submit_move(rg_moves2[0])

    rg_moves3 = _resolve_generic_moves(session)
    assert len(rg_moves3) >= 1, f"Expected at least 1 deploy move remaining, got {len(rg_moves3)}"
    session.submit_move(rg_moves3[0])

    s = session._state._ptr.contents
    p1_id = _lib.intern(b"p1")
    total_p1_troops = 0
    for ni in range(s.node_count):
        ns = s.nodes[ni]
        for t in range(ns.troop_slot_count):
            if ns.troop_slots[t] == p1_id:
                total_p1_troops += 1

    assert total_p1_troops == 2, (
        f"Expected 2 total p1 troops on board, got {total_p1_troops}"
    )
    assert _player_barracks(session, "p1") == barracks_before - 2, (
        f"Barracks should decrease by 2: {barracks_before} -> {_player_barracks(session, 'p1')}"
    )

    trophy_after = len(_trophy_hall(session, "p1"))
    assert trophy_after == trophies_before + 1, (
        f"Trophy hall should have +1 (assassinate), got {trophy_after} (was {trophies_before})"
    )

    final_gen = _resolve_generic_moves(session)
    assert len(final_gen) == 0, f"Expected 0 resolve_generic after all actions, got {len(final_gen)}"

    session.destroy()


def test_crushing_wave_cultist_no_valid_target_auto_resolves() -> None:
    """When no white troop exists on board, card resolves with no effect and no pending state."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["crushing_wave_cultist", "noble"]},
        current_player="p1",
    )

    trophies_before = len(_trophy_hall(session, "p1"))
    barracks_before = _player_barracks(session, "p1")

    for m in session.legal_moves():
        if getattr(m, "move_type", "") == "play_card" and m.data.get("card_id") == "crushing_wave_cultist":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("crushing_wave_cultist not in hand")

    gen_moves = _resolve_generic_moves(session)
    assert len(gen_moves) == 0, (
        f"Expected 0 resolve_generic with no white troops, got {len(gen_moves)}"
    )

    s = session._state._ptr.contents
    assert not s.pending_generic, "pending_generic should be cleared when no targets"

    assert len(_trophy_hall(session, "p1")) == trophies_before, "Trophy hall unchanged"
    assert _player_barracks(session, "p1") == barracks_before, "Barracks unchanged"

    move_types = {getattr(m, "move_type", "") for m in session.legal_moves()}
    assert "play_card" in move_types, "Should still be able to play other cards"
    assert "end_main_phase" in move_types, "Should be able to end main phase"

    session.destroy()


def test_crushing_wave_cultist_catalog_structure() -> None:
    """Verify execution_model: sequence with assassinate_troop + focused deploy_troops."""
    catalog = assemble_catalog_payload(DATA_DIR / "cards")

    card = None
    for c in catalog["cards"]:
        if c["card_id"] == "crushing_wave_cultist":
            card = c
            break
    assert card is not None, "Crushing Wave Cultist not found in catalog"

    assert card["cost"] == 3
    assert card["aspect"] == "conquest"

    em = card["execution_model"]
    assert em["kind"] == "sequence", f"Expected sequence, got {em['kind']}"
    actions = em["actions"]
    assert len(actions) == 2, f"Expected 2 actions, got {len(actions)}"

    a1 = actions[0]
    assert a1["op"] == "assassinate_troop", f"action_1 should be assassinate_troop, got {a1['op']}"
    assert a1["optional"] is False, "action_1 must be mandatory"
    assert a1["quantity"] == {"kind": "fixed", "value": 1}
    assert "white_troop_only" in a1["filters"]

    a2 = actions[1]
    assert a2["op"] == "deploy_troops", f"action_2 should be deploy_troops, got {a2['op']}"
    assert a2["optional"] is False, "action_2 must be mandatory"
    assert a2["quantity"] == {"kind": "fixed", "value": 2}
    assert a2["metadata"]["requires_focus"] is True
    assert a2["metadata"]["focus_aspect"] == "conquest"

    top_actions = card.get("actions", [])
    assert len(top_actions) == 2
    assert top_actions[0]["optional"] is False
    assert top_actions[1]["optional"] is False
