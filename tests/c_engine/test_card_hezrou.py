"""Hezrou card behavior tests: move enemy troop + promote top of deck."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from engine_c.bindings.ce_api import CEngine
from engine_c.bindings.engine_bindings import _lib
from engine_c.bindings.session import CSession
from engine_c.bindings.view import build_c_game_view
from tests.c_engine.card_test_helpers import make_card_test_session

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


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


def _player_deck(session: CSession, player_id: str) -> list[str]:
    s = session._state._ptr.contents
    for i in range(s.player_count):
        pid = _lib.intern_str(s.player_ids[i]).decode()
        if pid == player_id:
            ps = s.players[i]
            return [_lib.intern_str(ps.deck[j]).decode() for j in range(ps.deck_count)]
    return []


def _player_inner_circle(session: CSession, player_id: str) -> list[str]:
    s = session._state._ptr.contents
    for i in range(s.player_count):
        pid = _lib.intern_str(s.player_ids[i]).decode()
        if pid == player_id:
            ps = s.players[i]
            return [_lib.intern_str(ps.inner_circle[j]).decode() for j in range(ps.inner_circle_count)]
    return []


def test_hezrou_move_troop_produces_correct_labels():
    """Playing Hezrou should produce move_troop resolve_generic moves with
    source and destination in the label."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards" / "catalog.json"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["hezrou"]},
        troops={
            "default": {
                "site_gauntlgrym": ["p1", "p2", None],
                "route_1": [None],
                "route_2": [None],
            }
        },
        current_player="p1",
    )

    # Add a card to P1's deck for promote_top_of_deck
    s = session._state._ptr.contents
    p1s = s.players[0]
    p1s.deck_count = 1
    p1s.deck[0] = _lib.intern(b"soldier")

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "hezrou":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Hezrou not in hand")

    view = build_c_game_view(session)
    rg_moves = [m for m in view.legal_moves if m.move_type == "resolve_generic"]
    assert len(rg_moves) >= 1, f"Expected at least 1 resolve_generic move, got {len(rg_moves)}"

    # Each move should have a label containing "Move", "from", "to"
    for m in rg_moves:
        label = m.label or ""
        assert "Move" in label, f"Label should contain 'Move': {label}"
        assert "from" in label, f"Label should contain 'from': {label}"
        assert "to" in label, f"Label should contain 'to': {label}"
        # Check the underlying move data has target_id encoding
        tid = m.move.data.get("target_id", "")
        assert tid, "target_id should not be empty"
        parts = tid.split(":")
        assert len(parts) == 3, f"target_id should have 3 parts, got: {tid}"
        assert parts[0].isdigit(), f"First part of target_id should be digit: {tid}"

    session.destroy()


def test_hezrou_move_troop_executes():
    """Selecting a move_troop move should actually move the troop."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards" / "catalog.json"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["hezrou"]},
        troops={
            "default": {
                "site_gauntlgrym": ["p1", "p2", None],
                "route_1": [None],
                "route_2": [None],
            }
        },
        current_player="p1",
    )

    s = session._state._ptr.contents
    p1s = s.players[0]
    p1s.deck_count = 1
    p1s.deck[0] = _lib.intern(b"soldier")

    # Before: P2 occupies slot 1 of site_gauntlgrym, route_1/route_2 are free
    gaunt_before = _node_troop_slots(session, "site_gauntlgrym")
    assert "p2" in gaunt_before, f"P2 should be at site_gauntlgrym: {gaunt_before}"

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "hezrou":
            session.submit_move(m)
            break

    view = build_c_game_view(session)
    rg_moves = [m for m in view.legal_moves if m.move_type == "resolve_generic"]
    assert len(rg_moves) >= 1

    # Pick a move that targets route_1
    chosen = None
    for m in rg_moves:
        tid = m.move.data.get("target_id", "")
        if ":route_1:" in tid:
            chosen = m.move
            break
    assert chosen is not None, "No move targeting route_1 found"

    session.submit_move(chosen)

    # After move: P2 should be gone from site_gauntlgrym, route_1 should have P2
    gaunt_after = _node_troop_slots(session, "site_gauntlgrym")
    route1_after = _node_troop_slots(session, "route_1")
    assert "p2" not in gaunt_after, f"P2 should no longer be at site_gauntlgrym: {gaunt_after}"
    assert "p2" in route1_after, f"P2 should now be at route_1: {route1_after}"

    session.destroy()


def test_hezrou_promotes_top_of_deck():
    """Hezrou should promote the top card of draw deck to inner circle."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards" / "catalog.json"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["hezrou"]},
        troops={
            "default": {
                "site_gauntlgrym": ["p1", "p2", None],
                "route_1": [None],
            }
        },
        current_player="p1",
    )

    s = session._state._ptr.contents
    p1s = s.players[0]
    p1s.deck_count = 2
    p1s.deck[0] = _lib.intern(b"soldier")
    p1s.deck[1] = _lib.intern(b"noble")

    ic_before = _player_inner_circle(session, "p1")

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "hezrou":
            session.submit_move(m)
            break

    view = build_c_game_view(session)
    rg_moves = [m for m in view.legal_moves if m.move_type == "resolve_generic"]
    assert len(rg_moves) >= 1

    session.submit_move(rg_moves[0].move)

    # After resolving both actions, top deck card (noble at highest index) should be promoted
    deck_after = _player_deck(session, "p1")
    ic_after = _player_inner_circle(session, "p1")

    assert len(ic_after) == len(ic_before) + 1, f"Expected 1 more inner circle card, got {ic_after}"
    assert "noble" in ic_after, f"Expected 'noble' in inner circle: {ic_after}"
    assert "noble" not in deck_after, f"Expected 'noble' removed from deck: {deck_after}"
    assert "soldier" in deck_after, f"Expected 'soldier' still in deck: {deck_after}"

    session.destroy()


def test_hezrou_shuffles_discard_when_deck_empty():
    """When draw deck is empty, Hezrou should shuffle discard into deck first,
    then promote the top card."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards" / "catalog.json"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["hezrou"]},
        troops={
            "default": {
                "site_gauntlgrym": ["p1", "p2", None],
                "route_1": [None],
            }
        },
        current_player="p1",
    )

    s = session._state._ptr.contents
    p1s = s.players[0]
    p1s.deck_count = 0
    p1s.discard_pile_count = 2
    p1s.discard_pile[0] = _lib.intern(b"bounty_hunter")
    p1s.discard_pile[1] = _lib.intern(b"noble")

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "hezrou":
            session.submit_move(m)
            break

    view = build_c_game_view(session)
    rg_moves = [m for m in view.legal_moves if m.move_type == "resolve_generic"]
    assert len(rg_moves) >= 1
    session.submit_move(rg_moves[0].move)

    ic_after = _player_inner_circle(session, "p1")
    assert len(ic_after) == 1, f"Expected 1 card in inner circle, got {ic_after}"

    session.destroy()
