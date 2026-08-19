"""Vrock card behavior tests.

Modal card: either place a spy, or return one of own spies + gain 5 power.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from engine_c.bindings.ce_api import CEngine
from engine_c.bindings.engine_bindings import _lib
from engine_c.bindings.session import CSession
from tests.c_engine.card_test_helpers import make_card_test_session

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _spy_count_at_node(session: CSession, node_id: str, player_id: str) -> int:
    s = session._state._ptr.contents
    nid = _lib.intern(node_id.encode())
    pid = _lib.intern(player_id.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            ns = s.nodes[ni]
            return sum(1 for si in range(ns.spy_count) if ns.spies[si] == pid)
    return 0


def _total_spies_on_board(session: CSession, player_id: str) -> int:
    s = session._state._ptr.contents
    pid = _lib.intern(player_id.encode())
    total = 0
    for ni in range(s.node_count):
        ns = s.nodes[ni]
        total += sum(1 for si in range(ns.spy_count) if ns.spies[si] == pid)
    return total


def test_vrock_option_1_places_spy() -> None:
    """Option 1: place a spy on a board site."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["vrock"]},
        current_player="p1",
    )

    s = session._state._ptr.contents
    spies_before = s.players[0].spies_available
    gaunt_spies_before = _spy_count_at_node(session, "site_gauntlgrym", "p1")

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "vrock":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Vrock not in hand")

    for m in session.legal_moves():
        if m._move_type == "resolve_generic" and m.data.get("action_id") == "option_1":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("option_1 not available after playing Vrock")

    for m in session.legal_moves():
        if m._move_type == "resolve_generic" and m.data.get("action_id") == "site_gauntlgrym":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("No place_spy target (site_gauntlgrym) available")

    s = session._state._ptr.contents
    gaunt_spies_after = _spy_count_at_node(session, "site_gauntlgrym", "p1")
    assert gaunt_spies_after == gaunt_spies_before + 1, (
        f"Spy should be placed at site_gauntlgrym: {gaunt_spies_before} -> {gaunt_spies_after}"
    )
    assert s.players[0].spies_available == spies_before - 1, (
        f"spies_available should decrease: {spies_before} -> {s.players[0].spies_available}"
    )

    session.destroy()


def test_vrock_option_2_returns_spy_and_grants_5_power() -> None:
    """Option 2: return own spy from board to barracks and gain 5 power."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["vrock"]},
        spies={"site_gauntlgrym": ["p1"]},
        current_player="p1",
    )

    s = session._state._ptr.contents
    spies_avail_before = s.players[0].spies_available
    power_before = s.resource_pool.power
    board_spies_before = _total_spies_on_board(session, "p1")
    assert board_spies_before >= 1, "P1 must have a spy on board for option_2"

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "vrock":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Vrock not in hand")

    for m in session.legal_moves():
        if m._move_type == "resolve_generic" and m.data.get("action_id") == "option_2":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("option_2 not available after playing Vrock")

    for m in session.legal_moves():
        if m._move_type == "resolve_generic" and m.data.get("action_id") == "site_gauntlgrym":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("No return_spy target (site_gauntlgrym) available")

    s = session._state._ptr.contents
    board_spies_after = _total_spies_on_board(session, "p1")
    assert board_spies_after == board_spies_before - 1, (
        f"One spy should be removed from board: {board_spies_before} -> {board_spies_after}"
    )
    assert s.players[0].spies_available == spies_avail_before + 1, (
        f"spies_available should increase by 1: {spies_avail_before} -> {s.players[0].spies_available}"
    )
    assert s.resource_pool.power == power_before + 5, (
        f"Power should increase by 5: {power_before} -> {s.resource_pool.power}"
    )

    session.destroy()


def test_vrock_option_2_not_available_without_own_spy_on_board() -> None:
    """Option 2 should not be selectable when player has no spies on board."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["vrock"]},
        current_player="p1",
    )

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "vrock":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Vrock not in hand")

    option_2_moves = [
        m for m in session.legal_moves()
        if m._move_type == "resolve_generic" and m.data.get("action_id") == "option_2"
    ]
    assert len(option_2_moves) == 1, (
        f"option_2 should be listed but unavailable, got {len(option_2_moves)}"
    )
    assert option_2_moves[0].data.get("target_id") == "unavailable", (
        f"option_2 should be marked unavailable without own spy, got target_id={option_2_moves[0].data.get('target_id')}"
    )

    session.destroy()
