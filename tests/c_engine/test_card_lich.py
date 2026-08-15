"""Lich card behavior tests.

Place a spy. If another player has a troop there, take 2 troops from that
same player's trophy hall and deploy them anywhere on the board (regardless
of presence).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from engine_c.bindings.engine_bindings import MAX_ZONE_SIZE, _lib
from engine_c.bindings.session import CSession
from engine_c.bindings.view import build_c_game_view
from tests.c_engine.card_test_helpers import (
    _make_engine,
    _session_player_index,
    _sptr,
    make_card_test_session,
)

CARD_ID = "lich"
_SITE_A = "site_gauntlgrym"
_SITE_B = "site_menzoberranzan"


def _play_card(session: CSession, card_id: str) -> None:
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


def _set_trophy_hall(session: CSession, pid: str, trophies: list[str]) -> None:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return
    ps = _sptr(session).contents.players[pi]
    ps.trophy_hall_count = min(len(trophies), MAX_ZONE_SIZE)
    for i, t in enumerate(trophies[:MAX_ZONE_SIZE]):
        ps.trophy_hall[i] = _lib.intern(t.encode())


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


def _spies_at_node(session: CSession, node_id: str) -> list[str]:
    s = _sptr(session).contents
    nid = _lib.intern(node_id.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            ns = s.nodes[ni]
            return [_lib.intern_str(ns.spies[j]).decode() for j in range(ns.spy_count)]
    return []


def _resolve_generics_by_action(session: CSession, action_id: str | None) -> list:
    return [m for m in session.legal_moves()
            if m._move_type == "resolve_generic" and m.data.get("action_id") == action_id]


def _place_spy_at(session: CSession, site_id: str) -> None:
    moves = _resolve_generics_by_action(session, site_id)
    assert moves, f"Expected spy placement moves for {site_id}"
    session.submit_move(moves[0])


def _deploy_to(session: CSession, site_id: str) -> None:
    moves = _resolve_generics_by_action(session, site_id)
    assert moves, f"Expected deploy moves to {site_id}"
    session.submit_move(moves[0])


def test_lich_no_enemy_troop_at_spy_site_skips_trophy_phase():
    """Place spy at a site with no other troop -> trophy phase skipped."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": [CARD_ID]},
        current_player="p1",
    )

    _play_card(session, CARD_ID)

    _place_spy_at(session, _SITE_B)

    assert not _has_pending_generic(session), "Card should fully resolve after spy placement"
    assert _trophy_hall(session, "p2") == [], "No trophies should be taken"
    session.destroy()


def test_lich_single_enemy_deploys_two_trophies_anywhere():
    """Spy site has one enemy troop; take 2 trophies and deploy them to a site
    where the acting player has no presence (regardless of presence)."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": [CARD_ID]},
        troops={
            "p2": {_SITE_A: ["p2", "p2", "p2", "p2"]},
            "empty": {_SITE_B: [None, None, None, None]},
        },
        current_player="p1",
    )
    _set_trophy_hall(session, "p2", ["white", "p3"])

    _play_card(session, CARD_ID)

    _place_spy_at(session, _SITE_A)

    target_moves = _resolve_generics_by_action(session, "p2")
    assert target_moves, "Expected lich_select_target_player moves for p2"
    session.submit_move(target_moves[0])

    # p1 has no spy and no troop at _SITE_B -> no presence there.
    assert "p1" not in _spies_at_node(session, _SITE_B)
    assert "p1" not in _troops_at_node(session, _SITE_B)

    _deploy_to(session, _SITE_B)
    _deploy_to(session, _SITE_B)

    assert not _has_pending_generic(session), "Card should fully resolve"

    p2_trophies = _trophy_hall(session, "p2")
    assert len(p2_trophies) == 0, f"p2 should have 0 trophies, got {p2_trophies}"

    deployed = [t for t in _troops_at_node(session, _SITE_B) if t is not None]
    assert sorted(deployed) == ["p3", "white"], f"trophies should be deployed to _SITE_B, got {deployed}"

    session.destroy()


def test_lich_multiple_enemies_pick_target_then_trophies():
    """Spy site has troops from two enemies; trophies only from chosen one,
    deployed anywhere (no presence requirement)."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2", "p3"],
        hand={"p1": [CARD_ID]},
        troops={
            "p2": {_SITE_A: ["p2", "p3", None, None]},
            "empty": {_SITE_B: [None, None, None, None]},
        },
        current_player="p1",
    )
    _set_trophy_hall(session, "p2", ["white", "p3"])
    _set_trophy_hall(session, "p3", ["white", "p3", "white"])

    _play_card(session, CARD_ID)

    _place_spy_at(session, _SITE_A)

    p2_moves = _resolve_generics_by_action(session, "p2")
    p3_moves = _resolve_generics_by_action(session, "p3")
    assert p2_moves and p3_moves, "Expected target moves for both p2 and p3"
    session.submit_move(p2_moves[0])

    _deploy_to(session, _SITE_B)
    _deploy_to(session, _SITE_B)

    assert not _has_pending_generic(session), "Card should fully resolve"

    p2_trophies = _trophy_hall(session, "p2")
    p3_trophies = _trophy_hall(session, "p3")
    assert len(p2_trophies) == 0, f"p2 should have 0 trophies, got {p2_trophies}"
    assert len(p3_trophies) == 3, f"p3 trophies should be untouched, got {p3_trophies}"

    deployed = [t for t in _troops_at_node(session, _SITE_B) if t is not None]
    assert len(deployed) == 2, f"two trophies should be deployed, got {deployed}"

    session.destroy()


def test_lich_deploy_move_labels_render():
    """Deploy moves must render labels (no describe crash) naming the source
    player and the trophy owner."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": [CARD_ID]},
        troops={
            "p2": {_SITE_A: ["p2", "p2", "p2", "p2"]},
            "empty": {_SITE_B: [None, None, None, None]},
        },
        current_player="p1",
    )
    _set_trophy_hall(session, "p2", ["white", "p3"])

    _play_card(session, CARD_ID)
    _place_spy_at(session, _SITE_A)

    target_moves = _resolve_generics_by_action(session, "p2")
    assert target_moves, "Expected lich_select_target_player moves for p2"
    session.submit_move(target_moves[0])

    view = build_c_game_view(session)
    deploy_labels = [m.label for m in view.legal_moves]
    assert deploy_labels, "Expected deploy move labels"
    assert any("Deploy" in label for label in deploy_labels), f"got {deploy_labels[:3]}"
    assert any("Player 2" in label for label in deploy_labels), f"source player missing, got {deploy_labels[:3]}"
    session.destroy()


def test_lich_white_troop_at_spy_site_does_not_trigger():
    """A white (neutral) troop at the spy site is not 'another player', so the
    trophy phase must be skipped."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": [CARD_ID]},
        troops={
            "p2": {_SITE_A: ["white", "white", None, None]},
        },
        current_player="p1",
    )
    _set_trophy_hall(session, "p2", ["white", "p3"])

    _play_card(session, CARD_ID)
    _place_spy_at(session, _SITE_A)

    assert not _has_pending_generic(session), (
        "Card should resolve; a white troop does not trigger the trophy phase"
    )
    assert _trophy_hall(session, "p2") == ["white", "p3"], (
        "p2 trophies should be untouched when only a white troop is present"
    )
    session.destroy()


def test_lich_target_with_empty_trophy_hall_resolves():
    """Enemy troop at spy site but an empty trophy hall -> card resolves with
    nothing deployed."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": [CARD_ID]},
        troops={
            "p2": {_SITE_A: ["p2", None, None, None]},
        },
        current_player="p1",
    )

    _play_card(session, CARD_ID)
    _place_spy_at(session, _SITE_A)

    target_moves = _resolve_generics_by_action(session, "p2")
    assert target_moves, "Expected lich_select_target_player moves for p2"
    session.submit_move(target_moves[0])

    assert not _has_pending_generic(session), "Card should resolve with no trophies to deploy"
    assert _trophy_hall(session, "p2") == [], "p2 trophy hall stays empty"
    session.destroy()


def test_lich_enemy_with_one_trophy_takes_only_one():
    """If the enemy has fewer than 2 trophies, only the available one is taken."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": [CARD_ID]},
        troops={
            "p2": {_SITE_A: ["p2", None, None, None]},
            "empty": {_SITE_B: [None, None, None, None]},
        },
        current_player="p1",
    )
    _set_trophy_hall(session, "p2", ["white"])

    _play_card(session, CARD_ID)

    _place_spy_at(session, _SITE_A)

    target_moves = _resolve_generics_by_action(session, "p2")
    assert target_moves, "Expected lich_select_target_player moves for p2"
    session.submit_move(target_moves[0])

    _deploy_to(session, _SITE_B)

    assert not _has_pending_generic(session), "Card should fully resolve after the single trophy"

    p2_trophies = _trophy_hall(session, "p2")
    assert len(p2_trophies) == 0, f"p2 should have 0 trophies, got {p2_trophies}"

    deployed = [t for t in _troops_at_node(session, _SITE_B) if t is not None]
    assert deployed == ["white"], f"single trophy should be deployed, got {deployed}"

    session.destroy()
