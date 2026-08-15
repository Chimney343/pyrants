"""Demogorgon card: devour, supplant anywhere (1) + supplant presence (2), each opponent gets 2 Insane Outcasts."""

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


def _set_white_at(session, slot_map: dict[str, int]) -> None:
    s = session._state._ptr.contents
    for name, slot in slot_map.items():
        nid = _lib.intern(name.encode())
        for ni in range(s.node_count):
            if s.nodes[ni].node_id == nid:
                if s.nodes[ni].troop_slot_count < slot + 1:
                    s.nodes[ni].troop_slot_count = slot + 1
                s.nodes[ni].troop_slots[slot] = _lib.intern(b"white")
                break


def _set_troops(session, node_id: str, player_id: str) -> None:
    s = session._state._ptr.contents
    nid = _lib.intern(node_id.encode())
    pid = _lib.intern(player_id.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            if s.nodes[ni].troop_slot_count < 1:
                s.nodes[ni].troop_slot_count = 1
            s.nodes[ni].troop_slots[0] = pid
            break


def _find_resolve_move(session, action_id: str):
    for m in session.legal_moves():
        if m._move_type == "resolve_generic" and m.data.get("action_id") == action_id:
            return m
    return None


def _play_card(session, card_id: str) -> None:
    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == card_id:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"{card_id} not playable")


def _resolve_action_ids(session) -> set[str]:
    ids = set()
    for m in session.legal_moves():
        if m._move_type == "resolve_generic" and m.data.get("action_id"):
            ids.add(m.data["action_id"])
    return ids


def _discard_count(session, player_id: str, card_id: str) -> int:
    s = session._state._ptr.contents
    sym = _lib.intern(card_id.encode())
    for i in range(s.player_count):
        pname = _lib.intern_str(s.player_ids[i])
        if pname and pname.decode() == player_id:
            ps = s.players[i]
            return sum(1 for j in range(ps.discard_pile_count) if ps.discard_pile[j] == sym)
    return 0


# ---------------------------------------------------------------------------
# Test 1 — Engine: supplant_troop now supports multi-selection
# ---------------------------------------------------------------------------

def test_supplant_multi_selection() -> None:
    eng = _init_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["demogorgon", "soldier", "noble", "house_guard", "priestess_of_lolth"]},
        troops={"p1": {"route_1": ["p1"], "route_4": ["p1"]}},
        current_player="p1",
    )
    _set_white_at(session, {"site_gauntlgrym": 0, "site_neverwinter": 0, "route_8": 0})

    _play_card(session, "demogorgon")

    devour = _find_resolve_move(session, "soldier")
    assert devour, "Devour should offer soldier"
    session.submit_move(devour)

    supplant_anywhere = [
        m for m in session.legal_moves()
        if m._move_type == "resolve_generic" and m.data.get("action_id") == "site_gauntlgrym"
    ]
    assert supplant_anywhere, "site_gauntlgrym should be a legal anywhere supplant target"
    session.submit_move(supplant_anywhere[0])

    s = session._state._ptr.contents
    barracks_after_first = s.players[0].barracks

    second_supplant_sites = _resolve_action_ids(session)
    assert second_supplant_sites, "Should offer second supplant targets (presence-bound)"
    target = next(iter(second_supplant_sites))
    move = _find_resolve_move(session, target)
    assert move, f"{target} should be selectable"
    session.submit_move(move)

    s = session._state._ptr.contents
    assert s.players[0].barracks == barracks_after_first - 1, (
        "Second supplant should cost 1 more barracks"
    )

    third_supplant_sites = _resolve_action_ids(session)
    assert third_supplant_sites, "Should offer third supplant target"
    target3 = next(iter(third_supplant_sites))
    move3 = _find_resolve_move(session, target3)
    session.submit_move(move3)

    s = session._state._ptr.contents
    assert s.players[0].barracks == barracks_after_first - 2, (
        "Three supplants total should cost 3 barracks"
    )

    session.destroy()


# ---------------------------------------------------------------------------
# Test 2 — Engine: give_insane_outcast_to_each_opponent respects quantity
# ---------------------------------------------------------------------------

def test_insane_outcast_multi_per_opponent() -> None:
    eng = _init_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2", "p3"],
        hand={"p1": ["demogorgon", "soldier", "noble", "house_guard", "priestess_of_lolth"]},
        troops={"p1": {"route_1": ["p1"], "route_4": ["p1"]}},
        current_player="p1",
    )
    _set_white_at(session, {"site_gauntlgrym": 0, "site_neverwinter": 0, "route_8": 0})

    _play_card(session, "demogorgon")

    devour = _find_resolve_move(session, "soldier")
    assert devour
    session.submit_move(devour)

    supplant_anywhere = [
        m for m in session.legal_moves()
        if m._move_type == "resolve_generic" and m.data.get("action_id") == "site_gauntlgrym"
    ]
    assert supplant_anywhere
    session.submit_move(supplant_anywhere[0])

    for _ in range(2):
        sites = _resolve_action_ids(session)
        assert sites
        target = next(iter(sites))
        move = _find_resolve_move(session, target)
        session.submit_move(move)

    assert session.legal_moves(), "Should have autoplay/end moves available"

    assert _discard_count(session, "p2", "insane_outcast") == 2, (
        "p2 should have 2 Insane Outcasts in discard"
    )
    assert _discard_count(session, "p3", "insane_outcast") == 2, (
        "p3 should have 2 Insane Outcasts in discard"
    )

    session.destroy()


# ---------------------------------------------------------------------------
# Test 3 — Card: Demogorgon end-to-end
# ---------------------------------------------------------------------------

def test_demogorgon_end_to_end() -> None:
    eng = _init_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2", "p3", "p4"],
        hand={"p1": ["demogorgon", "soldier", "noble", "house_guard", "priestess_of_lolth"]},
        troops={"p1": {"route_1": ["p1"], "route_4": ["p1"]}},
        current_player="p1",
    )
    _set_white_at(session, {
        "site_gauntlgrym": 0,
        "site_neverwinter": 0,
        "route_8": 0,
        "site_jhachalkhyn": 0,
    })

    s = session._state._ptr.contents
    barracks_before = s.players[0].barracks
    hand_before = s.players[0].hand_count

    _play_card(session, "demogorgon")

    devour = _find_resolve_move(session, "soldier")
    assert devour
    session.submit_move(devour)

    s = session._state._ptr.contents
    assert s.players[0].hand_count == hand_before - 2, "Demogorgon + devoured card gone"

    supplant_anywhere_sites = _resolve_action_ids(session)
    assert "site_jhachalkhyn" in supplant_anywhere_sites, (
        "site_jhachalkhyn (no presence) should be anywhere-target"
    )
    move = _find_resolve_move(session, "site_jhachalkhyn")
    session.submit_move(move)

    s = session._state._ptr.contents
    assert s.players[0].barracks == barracks_before - 1, "1st supplant cost 1 barracks"

    j_sym = _lib.intern(b"site_jhachalkhyn")
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == j_sym:
            assert s.nodes[ni].troop_slots[0] == _lib.intern(b"p1"), "White replaced by p1"
            break

    for _ in range(2):
        sites = _resolve_action_ids(session)
        assert sites, "Should offer presence-bound supplant targets"
        assert "site_jhachalkhyn" not in sites, (
            "site_jhachalkhyn should not be a presence target"
        )
        target = next(iter(sites))
        move = _find_resolve_move(session, target)
        session.submit_move(move)

    s = session._state._ptr.contents
    assert s.players[0].barracks == barracks_before - 3, "3 supplants = 3 barracks cost"

    for opp in ("p2", "p3", "p4"):
        assert _discard_count(session, opp, "insane_outcast") == 2, (
            f"{opp} should have 2 Insane Outcasts"
        )

    assert _discard_count(session, "p1", "insane_outcast") == 0, (
        "current player should NOT receive Insane Outcasts"
    )

    session.destroy()


# ---------------------------------------------------------------------------
# Test 4 — Engine: anywhere supplant includes a route (no presence required)
# ---------------------------------------------------------------------------

def test_anywhere_supplant_includes_route_without_presence() -> None:
    eng = _init_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["demogorgon", "soldier", "noble", "house_guard", "priestess_of_lolth"]},
        troops={"p1": {"route_1": ["p1"]}},
        current_player="p1",
    )
    _set_white_at(session, {"route_8": 0})

    _play_card(session, "demogorgon")

    devour = _find_resolve_move(session, "soldier")
    assert devour
    session.submit_move(devour)

    anywhere_ids = _resolve_action_ids(session)
    assert "route_8" in anywhere_ids, (
        "a white troop on a route must be a legal anywhere-supplant target"
    )

    session.destroy()
