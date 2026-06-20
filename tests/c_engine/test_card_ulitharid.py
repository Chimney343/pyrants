"""Ulitharid card behavior tests.

Verifies: play_card with max_cost filter, nested card execution,
automatic parent pending restoration, and devour with
requires_last_selected_market_slot.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from engine_c.bindings.ce_api import CEngine
from engine_c.bindings.engine_bindings import _lib, MAX_ZONE_SIZE, MOVE_RESOLVE_GENERIC
from engine_c.bindings.session import CSession
from tests.c_engine.card_test_helpers import make_card_test_session

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def test_ulitharid_play_costs_four_or_less_market_only() -> None:
    """play_card target selection should filter to cards costing 4 or less."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards" / "catalog.json"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["ulitharid"]},
        current_player="p1",
    )

    market_cards = ["noble", "aboleth", "soldier", "death_tyrant", "priestess_of_lolth"]
    ms = session._state._ptr.contents.market
    ms.row_count = min(len(market_cards), MAX_ZONE_SIZE)
    for j, cid in enumerate(market_cards[:MAX_ZONE_SIZE]):
        ms.row[j] = _lib.intern(cid.encode())

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "ulitharid":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Ulitharid not in hand")

    target_ids = {
        m.data["action_id"]
        for m in session.legal_moves()
        if m._move_type == "resolve_generic" and m.data.get("action_id")
    }

    assert "noble" in target_ids, "Noble (cost 0) should be selectable"
    assert "soldier" in target_ids, "Soldier (cost 0) should be selectable"
    assert "priestess_of_lolth" in target_ids, "Priestess (cost 3) should be selectable"
    assert "aboleth" not in target_ids, "Aboleth (cost 7) should NOT be selectable"
    assert "death_tyrant" not in target_ids, "Death Tyrant (cost 7) should NOT be selectable"

    session.destroy()


def test_ulitharid_play_and_devour_noble() -> None:
    """Play Noble from market via Ulitharid, then devour it."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards" / "catalog.json"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["ulitharid"]},
        current_player="p1",
    )

    market_cards = ["noble", "soldier"]
    ms = session._state._ptr.contents.market
    ms.row_count = min(len(market_cards), MAX_ZONE_SIZE)
    for j, cid in enumerate(market_cards[:MAX_ZONE_SIZE]):
        ms.row[j] = _lib.intern(cid.encode())

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "ulitharid":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Ulitharid not in hand")

    s = session._state._ptr.contents
    inf_before = s.resource_pool.influence

    for m in session.legal_moves():
        if m._move_type == "resolve_generic" and m.data.get("action_id") == "noble":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Noble not selectable for play_card")

    s = session._state._ptr.contents
    assert s.resource_pool.influence == inf_before + 1, (
        f"Noble should have granted 1 influence: {inf_before} -> {s.resource_pool.influence}"
    )

    devour_moves = [
        m for m in session.legal_moves()
        if m._move_type == "resolve_generic" and m.data.get("action_id") == "noble"
    ]
    assert len(devour_moves) == 1, f"Expected 1 devour target, got {len(devour_moves)}"

    dv = session._state._ptr.contents.devour_pile_count
    session.submit_move(devour_moves[0])

    s = session._state._ptr.contents
    assert s.devour_pile_count == dv + 1, f"Devour pile should have grown: {dv} -> {s.devour_pile_count}"
    devoured_ids = {
        _lib.intern_str(s.devour_pile[i]).decode()
        for i in range(s.devour_pile_count)
    }
    assert "noble" in devoured_ids, "Noble should be in devour pile"

    market_ids = {
        _lib.intern_str(s.market.row[i]).decode()
        for i in range(s.market.row_count)
    }
    assert "noble" not in market_ids, "Noble should be removed from market row"

    session.destroy()


def test_ulitharid_play_modal_card_and_devour() -> None:
    """Play a modal market card (intellect_devourer) via Ulitharid,
    resolve it, then devour it.  Exercises the parent chain cloning path
    in engine_clone that was previously broken (crash on
    legal_moves after nested modal resolution)."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards" / "catalog.json"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["ulitharid"]},
        current_player="p1",
    )

    market_cards = ["intellect_devourer", "soldier"]
    ms = session._state._ptr.contents.market
    ms.row_count = min(len(market_cards), MAX_ZONE_SIZE)
    for j, cid in enumerate(market_cards[:MAX_ZONE_SIZE]):
        ms.row[j] = _lib.intern(cid.encode())

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "ulitharid":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Ulitharid not in hand")

    s = session._state._ptr.contents
    inf_before = s.resource_pool.influence

    for m in session.legal_moves():
        if m._move_type == "resolve_generic" and m.data.get("action_id") == "intellect_devourer":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("intellect_devourer not selectable for play_card")

    for m in session.legal_moves():
        if m._move_type == "resolve_generic" and m.data.get("action_id") == "option_1":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("option_1 not available for intellect_devourer")

    s = session._state._ptr.contents
    assert s.resource_pool.influence == inf_before + 3, (
        f"option_1 should have granted 3 influence: {inf_before} -> {s.resource_pool.influence}"
    )

    devour_moves = [
        m for m in session.legal_moves()
        if m._move_type == "resolve_generic" and m.data.get("action_id") == "intellect_devourer"
    ]
    assert len(devour_moves) == 1, (
        f"Expected 1 devour target (intellect_devourer), got {len(devour_moves)}"
    )

    dv = session._state._ptr.contents.devour_pile_count
    session.submit_move(devour_moves[0])

    s = session._state._ptr.contents
    assert s.devour_pile_count == dv + 1, (
        f"Devour pile should have grown: {dv} -> {s.devour_pile_count}"
    )
    devoured_ids = {
        _lib.intern_str(s.devour_pile[i]).decode()
        for i in range(s.devour_pile_count)
    }
    assert "intellect_devourer" in devoured_ids, "intellect_devourer should be in devour pile"

    market_ids = {
        _lib.intern_str(s.market.row[i]).decode()
        for i in range(s.market.row_count)
    }
    assert "intellect_devourer" not in market_ids, (
        "intellect_devourer should be removed from market row"
    )

    session.destroy()
