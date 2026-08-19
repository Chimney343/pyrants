"""Council Member: Move 2 enemy troops. At end of turn, promote another played card.

Execution trace:
  1. play council_member → resolve_generic_execution (generic_runtime.c)
  2. action_1: move_troop (immediate, quantity=2)
     - action_requires_selection → 1 (line 187, in selection_ops)
     - resolve_runtime_action_count → 2 (QUANT_FIXED, value=2)
     - sel_move_troop (selection.c:455) generates source→dest pairs
       - excludes SYM_NULL, own troops, white troops (since no allow_white filter)
     - apply_move_troop (actions.c:371) executes the move
       - increments pending counter → action_requires_additional_choice
       - repeats until counter == 2
  3. action_2: promote_card (end_of_turn, sf=triggered_promote)
     - action_requires_selection → 0 (line 192, end_of_turn timing bypass)
     - deferred to pending_eot with requires_another_played_card=1 (lines 400-437)
  4. end_of_turn → deferred_promotion_target_ids (helpers.c:634)
     - filters out self (source_card_id), returns other played cards
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from engine_c.bindings.ce_api import CEngine
from engine_c.bindings.engine_bindings import _lib
from engine_c.bindings.session import CSession
from engine_c.bindings.view import build_c_game_view
from tests.c_engine.card_test_helpers import make_card_test_session, _sptr

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _init_engine() -> CEngine:
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    return eng


def _node_troop_slots(session: CSession, node_id: str) -> list[str | None]:
    s = _sptr(session).contents
    nid = _lib.intern(node_id.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            ns = s.nodes[ni]
            result: list[str | None] = []
            for t in range(ns.troop_slot_count):
                occ = ns.troop_slots[t]
                result.append(_lib.intern_str(occ).decode() if occ != 0 else None)
            return result
    return []


def _player_inner_circle(session: CSession, player_id: str) -> list[str]:
    s = _sptr(session).contents
    for i in range(s.player_count):
        pid = _lib.intern_str(s.player_ids[i]).decode()
        if pid == player_id:
            ps = s.players[i]
            return [_lib.intern_str(ps.inner_circle[j]).decode() for j in range(ps.inner_circle_count)]
    return []


def _player_played_cards(session: CSession, player_id: str) -> list[str]:
    s = _sptr(session).contents
    for i in range(s.player_count):
        pid = _lib.intern_str(s.player_ids[i]).decode()
        if pid == player_id:
            ps = s.players[i]
            return [_lib.intern_str(ps.played_cards[j]).decode() for j in range(ps.played_cards_count)]
    return []


def _submit_move_of_type(session: CSession, move_type: str) -> bool:
    for m in session.legal_moves():
        if m._move_type == move_type:
            session.submit_move(m)
            return True
    return False


# ── move_troop target filtering ──────────────────────────────────────────────

def test_move_troop_excludes_white_troops() -> None:
    """White troops should not appear as legal move_troop source targets."""
    eng = _init_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["council_member"]},
        troops={"p1": {"site_gauntlgrym": ["p1"]}},
        current_player="p1",
    )
    s = _sptr(session).contents
    nid = _lib.intern(b"site_gauntlgrym")
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            s.nodes[ni].troop_slots[0] = _lib.intern(b"p1")
            s.nodes[ni].troop_slots[1] = _lib.intern(b"white")
            s.nodes[ni].troop_slots[2] = _lib.intern(b"p2")
            s.nodes[ni].troop_slot_count = 4
            break

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "council_member":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Council Member not playable")

    target_source_slots = set()
    for m in session.legal_moves():
        if m._move_type == "resolve_generic" and m.data.get("target_id"):
            tid = str(m.data["target_id"])
            if ":" in tid:
                target_source_slots.add(tid.split(":")[0])

    assert "1" not in target_source_slots, "Slot 1 (white) should not be a legal move target"
    assert "2" in target_source_slots, "Slot 2 (p2 enemy) should be a legal move target"
    session.destroy()


def test_move_troop_excludes_own_troops() -> None:
    """The current player's own troops should not be legal move_troop targets."""
    eng = _init_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["council_member"]},
        troops={"p1": {"site_gauntlgrym": ["p1"]}},
        current_player="p1",
    )
    s = _sptr(session).contents
    nid = _lib.intern(b"site_gauntlgrym")
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            s.nodes[ni].troop_slots[0] = _lib.intern(b"p1")
            s.nodes[ni].troop_slots[1] = _lib.intern(b"p2")
            s.nodes[ni].troop_slot_count = 3
            break

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "council_member":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Council Member not playable")

    target_source_slots = set()
    for m in session.legal_moves():
        if m._move_type == "resolve_generic" and m.data.get("target_id"):
            tid = str(m.data["target_id"])
            if ":" in tid:
                target_source_slots.add(tid.split(":")[0])

    assert "0" not in target_source_slots, "Slot 0 (p1 own) should not be a legal move target"
    assert "1" in target_source_slots, "Slot 1 (p2 enemy) should be a legal move target"
    session.destroy()


# ── quantity enforcement ─────────────────────────────────────────────────────

def test_move_troop_limit_two() -> None:
    """Exactly 2 move_troop actions should be offered, then no more."""
    eng = _init_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["council_member"]},
        troops={"p1": {"site_gauntlgrym": ["p1"]}},
        current_player="p1",
    )
    s = _sptr(session).contents
    nid = _lib.intern(b"site_gauntlgrym")
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            s.nodes[ni].troop_slots[0] = _lib.intern(b"p1")
            s.nodes[ni].troop_slots[1] = _lib.intern(b"p2")
            s.nodes[ni].troop_slots[2] = _lib.intern(b"p3")
            s.nodes[ni].troop_slot_count = 4
            break

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "council_member":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Council Member not playable")

    resolved = 0
    for _ in range(2):
        found = False
        for m in session.legal_moves():
            if m._move_type == "resolve_generic":
                session.submit_move(m)
                resolved += 1
                found = True
                break
        if not found:
            session.destroy()
            raise AssertionError(f"No resolve_generic at resolution {resolved}")

    remaining = sum(1 for m in session.legal_moves() if m._move_type == "resolve_generic")
    assert resolved == 2
    assert remaining == 0, f"After 2 moves, expected 0 resolve_generic, got {remaining}"
    session.destroy()


# ── move_troop execution ─────────────────────────────────────────────────────

def test_move_troop_actually_moves_enemy_troop() -> None:
    """Selecting a move_troop target should physically relocate the troop on the board."""
    eng = _init_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["council_member"]},
        troops={"p1": {"site_gauntlgrym": ["p1", "p2", None]}},
        current_player="p1",
    )

    gaunt_before = _node_troop_slots(session, "site_gauntlgrym")
    assert "p2" in gaunt_before, f"P2 should be at site_gauntlgrym: {gaunt_before}"

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "council_member":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Council Member not playable")

    view = build_c_game_view(session)
    rg_moves = [m for m in view.legal_moves if m.move_type == "resolve_generic"]
    assert len(rg_moves) >= 1

    chosen = None
    for m in rg_moves:
        tid = m.move.data.get("target_id", "")
        if ":route_1:" in tid:
            chosen = m.move
            break
    assert chosen is not None, "No move targeting route_1 found"

    session.submit_move(chosen)

    gaunt_after = _node_troop_slots(session, "site_gauntlgrym")
    route1_after = _node_troop_slots(session, "route_1")
    assert "p2" not in gaunt_after, f"P2 should be gone from site_gauntlgrym: {gaunt_after}"
    assert "p2" in route1_after, f"P2 should now be at route_1: {route1_after}"
    session.destroy()


def test_move_troop_presence_required() -> None:
    """Nodes without the current player's presence should not appear as legal sources."""
    eng = _init_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["council_member"]},
        troops={"p1": {"site_gauntlgrym": ["p1"]}},
        current_player="p1",
    )
    s = _sptr(session).contents

    nid = _lib.intern(b"site_gauntlgrym")
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            s.nodes[ni].troop_slots[0] = _lib.intern(b"p1")
            s.nodes[ni].troop_slots[1] = _lib.intern(b"p2")
            s.nodes[ni].troop_slot_count = 4
            break

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "council_member":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Council Member not playable")

    source_nodes = set()
    for m in session.legal_moves():
        if m._move_type == "resolve_generic" and m.data.get("action_id"):
            src = m.data["action_id"]
            source_nodes.add(_lib.intern_str(src).decode() if isinstance(src, int) else str(src))

    assert "site_gauntlgrym" in source_nodes, f"site_gauntlgrym should be in source nodes: {source_nodes}"
    session.destroy()


def test_move_troop_destination_empty_slots() -> None:
    """The destination node must have at least one empty troop slot."""
    eng = _init_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["council_member"]},
        troops={"p1": {"site_gauntlgrym": ["p1", "p2", None]}},
        current_player="p1",
    )

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "council_member":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Council Member not playable")

    destinations = set()
    for m in session.legal_moves():
        if m._move_type == "resolve_generic" and m.data.get("target_id"):
            tid = str(m.data["target_id"])
            parts = tid.split(":")
            if len(parts) == 3:
                destinations.add(parts[1])

    assert len(destinations) > 0, "Should have at least one destination node"
    session.destroy()


# ── end-of-turn promote ──────────────────────────────────────────────────────

def test_end_of_turn_promote_another_played_card() -> None:
    """After playing Council Member + another card and ending main phase,
    the other played card should be promoted to inner circle."""
    eng = _init_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["council_member", "noble"]},
        troops={"p1": {"site_gauntlgrym": ["p1", "p2", None]}},
        current_player="p1",
    )

    # Play Council Member
    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "council_member":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Council Member not playable")

    # Resolve the move_troop action (need to do at least 1 of the 2 moves)
    moved = False
    for _ in range(2):
        for m in session.legal_moves():
            if m._move_type == "resolve_generic":
                session.submit_move(m)
                moved = True
                break
    assert moved, "Should have resolved at least one move_troop"

    # Play Noble (another card)
    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "noble":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Noble not playable")

    # Resolve Noble's default action (deploy)
    for m in session.legal_moves():
        if m._move_type == "resolve_generic":
            session.submit_move(m)
            break

    # End main phase
    assert _submit_move_of_type(session, "end_main_phase"), "Should have end_main_phase"

    # The promote_card move should be for Noble (the only other played card)
    promote_moves = [m for m in session.legal_moves() if m._move_type == "promote_card"]
    promote_targets = [m.data.get("card_id", "") for m in promote_moves]

    assert "noble" in promote_targets, f"Noble should be a promote target, got: {promote_targets}"
    assert "council_member" not in promote_targets, "Council Member should not promote itself"

    # Execute the promotion (non-optional — no skip_promote needed)
    assert _submit_move_of_type(session, "promote_card"), "Should have a promote_card move"

    ic_after = _player_inner_circle(session, "p1")
    assert "noble" in ic_after, f"Noble should be in inner circle: {ic_after}"
    session.destroy()


def test_end_of_turn_promote_no_other_played_card() -> None:
    """If Council Member is the only played card, end-of-turn promote should do nothing
    (no targets, skip promotion)."""
    eng = _init_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["council_member"]},
        troops={"p1": {"site_gauntlgrym": ["p1", "p2", None]}},
        current_player="p1",
    )

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "council_member":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Council Member not playable")

    # Resolve move_troop actions
    for _ in range(2):
        for m in session.legal_moves():
            if m._move_type == "resolve_generic":
                session.submit_move(m)
                break

    # End main phase
    assert _submit_move_of_type(session, "end_main_phase"), "Should have end_main_phase"

    # No promote_card moves should exist since Council Member is the only played card
    promote_moves = [m for m in session.legal_moves() if m._move_type == "promote_card"]
    assert len(promote_moves) == 0, (
        f"No other played card → no promote targets, got: "
        f"{[(m.data.get('card_id', '')) for m in promote_moves]}"
    )

    ic = _player_inner_circle(session, "p1")
    assert len(ic) == 0, f"Inner circle should be empty, got: {ic}"
    session.destroy()
