"""Advance Scout card behavior tests.

Advance Scout (3-cost, Conquest/Drow):
  Supplant a white troop.
  Requires presence at the target site (no ignore_presence_requirement).
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

CARD_ID = "advance_scout"
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


def _spies_at_node(session: CSession, node_id: str) -> list[str]:
    s = _sptr(session).contents
    nid = _lib.intern(node_id.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            ns = s.nodes[ni]
            return [_lib.intern_str(ns.spies[i]).decode() for i in range(ns.spy_count)]
    return []


def test_advance_scout_execution_model() -> None:
    catalog = assemble_catalog_payload(DATA_DIR / "cards")
    cards = catalog if isinstance(catalog, list) else catalog.get("cards", catalog)
    card = next(c for c in cards if c.get("card_id") == "advance_scout")

    actions = card["execution_model"]["actions"]
    assert len(actions) == 1

    supplant = actions[0]
    assert supplant["op"] == "supplant_troop"
    assert supplant["target_scope"] == "board_site"
    assert supplant["filters"] == ["white_troop_only"]
    assert supplant["optional"] is False
    assert supplant["quantity"] == {"kind": "unspecified", "value": None}
    assert supplant["metadata"] == {}

    assert "Supplant a white troop" in card["rules_text"]
    assert card["cost"] == 3
    assert card["aspect"] == "conquest"
    assert "drow" in card["secondary_aspects"]
    assert card["deck_vp"] == 1
    assert card["inner_circle_vp"] == 3


def test_supplants_white_troop_with_presence():
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


def test_cannot_supplant_without_presence():
    """Without presence at the site with a white troop, no supplant moves
    are offered (Advance Scout does NOT have ignore_presence_requirement)."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": [CARD_ID]},
        troops={"p2": {_SITE_B: ["p2", "white", None]}},
        current_player="p1",
    )

    _play_card(session)

    supplant_moves = _resolve_generic_moves(session)
    assert not supplant_moves, (
        f"Advance Scout requires presence; should have no supplant moves "
        f"when p1 has no troops/spies at {_SITE_B}"
    )
    session.destroy()


def test_only_supplants_white_troops():
    """Supplant moves target only white troops, not player-owned troops."""
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


def test_white_goes_to_active_player_trophy_hall():
    """The supplanted white troop enters the active player's trophy hall."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": [CARD_ID]},
        troops={"p1": {_SITE_A: ["p1", "white", None]}},
        current_player="p1",
    )

    assert "white" not in _trophy_hall(session, "p1"), "Trophy hall starts empty"

    _play_card(session)
    supplant_moves = _resolve_generic_moves(session)
    session.submit_move(supplant_moves[0])

    assert "white" in _trophy_hall(session, "p1"), "White should be in p1's trophy hall"
    assert "white" not in _trophy_hall(session, "p2"), "White should NOT be in p2's trophy hall"
    session.destroy()


def test_presence_via_spy():
    """A spy at the site counts as presence for supplant targeting."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": [CARD_ID]},
        troops={"p2": {_SITE_B: ["p2", "white", None]}},
        spies={_SITE_B: ["p1"]},
        current_player="p1",
    )

    assert "p1" in _spies_at_node(session, _SITE_B), "p1 should have a spy at _SITE_B"

    _play_card(session)

    supplant_moves = _resolve_generic_moves(session)
    assert supplant_moves, "Expected supplant moves (spy provides presence)"
    site_b_move = [m for m in supplant_moves if m.data.get("action_id") == _SITE_B]
    assert site_b_move, f"Expected supplant move for {_SITE_B}"
    session.submit_move(site_b_move[0])
    assert not _has_pending_generic(session)

    troops = _troops_at_node(session, _SITE_B)
    assert "white" not in troops
    assert "p1" in troops, "p1 troop should replace white at _SITE_B"
    assert "white" in _trophy_hall(session, "p1"), "White goes to p1's trophy hall"
    session.destroy()


def test_no_white_troops_on_board_no_moves():
    """If no white troops exist anywhere on the board, the card resolves
    with no supplant moves offered."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": [CARD_ID]},
        troops={"p1": {_SITE_A: ["p1", None, None]}},
        current_player="p1",
    )

    _play_card(session)

    supplant_moves = _resolve_generic_moves(session)
    assert not supplant_moves, "No white troops on board, should have no supplant moves"
    assert not _has_pending_generic(session), (
        "Card should resolve immediately when no white troops are on the board"
    )
    session.destroy()
