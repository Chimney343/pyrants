"""Intellect Devourer card behavior tests.

Verifies that return_unit targets only the player's own troops and spies,
and that returning them correctly increments barracks / spies_available.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from engine_c.bindings.ce_api import CEngine
from engine_c.bindings.engine_bindings import _lib, PHASE_MAIN
from engine_c.bindings.session import CSession
from tests.c_engine.card_test_helpers import make_card_test_session

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _resolve_move_for_target(legal_moves, action_id, target_id):
    """Find a resolve_generic move with matching action_id and target_id."""
    for m in legal_moves:
        d = m.data
        if m._move_type == "resolve_generic":
            if d.get("action_id") == action_id and d.get("target_id") == target_id:
                return m
    return None


def test_intellect_devourer_return_unit_only_targets_own_units() -> None:
    """return_unit should only show the current player's own troops/spies as targets."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )

    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["intellect_devourer"]},
        troops={
            "p1": {
                "site_gauntlgrym": ["p1", "p2"],
                "route_1": ["p1", None],
            }
        },
        spies={
            "site_gauntlgrym": ["p1", "p2"],
            "route_1": ["p1"],
        },
        current_player="p1",
    )
    session._state._ptr.contents.phase = PHASE_MAIN

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "intellect_devourer":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Intellect Devourer not in hand")

    for m in session.legal_moves():
        if m.data.get("action_id") == "option_2":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Option 2 not available")

    targets = [
        (m.data["action_id"], m.data["target_id"])
        for m in session.legal_moves()
        if m._move_type == "resolve_generic" and m.data["target_id"] is not None
    ]

    # p1 has troops at gauntlgrym (slot 0) and route_1 (slot 0)
    assert ("site_gauntlgrym", "troop:0") in targets, "p1 troop at gauntlgrym should be targetable"
    assert ("route_1", "troop:0") in targets, "p1 troop at route_1 should be targetable"

    # p1 has spies at gauntlgrym and route_1
    assert ("site_gauntlgrym", "spy:p1") in targets, "p1 spy at gauntlgrym should be targetable"
    assert ("route_1", "spy:p1") in targets, "p1 spy at route_1 should be targetable"

    # p2's units should NOT be targetable
    for (action_id, target_id) in targets:
        if "p2" in (target_id or ""):
            raise AssertionError(f"p2 unit should not be targetable: {action_id}, {target_id}")

    # Verify total count: 2 troops + 2 spies = 4 targets (+ 1 skip)
    assert len(targets) == 4, f"Expected 4 targets, got {len(targets)}: {targets}"

    session.destroy()


def test_intellect_devourer_return_troop_increments_barracks() -> None:
    """Returning a troop should increment barracks by 1 and clear the slot."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )

    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["intellect_devourer"]},
        troops={
            "p1": {"site_gauntlgrym": ["p1", "p2"]},
        },
        spies={},
        current_player="p1",
    )
    session._state._ptr.contents.phase = PHASE_MAIN

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "intellect_devourer":
            session.submit_move(m)
            break

    for m in session.legal_moves():
        if m.data.get("action_id") == "option_2":
            session.submit_move(m)
            break

    s = session._state._ptr.contents
    barracks_before = s.players[0].barracks

    move = _resolve_move_for_target(session.legal_moves(), "site_gauntlgrym", "troop:0")
    assert move is not None, "troop:0 at gauntlgrym should be selectable"

    session.submit_move(move)
    s = session._state._ptr.contents

    assert s.players[0].barracks == barracks_before + 1, (
        f"Barracks should increase: {barracks_before} -> {s.players[0].barracks}"
    )

    session.destroy()


def test_intellect_devourer_return_spy_increments_spies_available() -> None:
    """Returning a spy should increment spies_available by 1."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )

    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["intellect_devourer"]},
        troops={},
        spies={
            "site_gauntlgrym": ["p1", "p2"],
        },
        current_player="p1",
    )
    session._state._ptr.contents.phase = PHASE_MAIN

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "intellect_devourer":
            session.submit_move(m)
            break

    for m in session.legal_moves():
        if m.data.get("action_id") == "option_2":
            session.submit_move(m)
            break

    s = session._state._ptr.contents
    spies_before = s.players[0].spies_available

    move = _resolve_move_for_target(session.legal_moves(), "site_gauntlgrym", "spy:p1")
    assert move is not None, "spy:p1 at gauntlgrym should be selectable"

    session.submit_move(move)
    s = session._state._ptr.contents

    assert s.players[0].spies_available == spies_before + 1, (
        f"spies_available should increase: {spies_before} -> {s.players[0].spies_available}"
    )

    session.destroy()
