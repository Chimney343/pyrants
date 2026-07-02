"""Mummy Lord card behavior tests.

Choose two times: (a) assassinate a white troop, (b) take a white trophy
from another player and deploy anywhere.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from engine_c.bindings.engine_bindings import MAX_ZONE_SIZE, _lib
from engine_c.bindings.session import CSession
from tests.c_engine.card_test_helpers import (
    _make_engine,
    _session_player_index,
    _sptr,
    make_card_test_session,
)

CARD_ID = "mummy_lord"
_SITE_A = "site_gauntlgrym"
_SITE_B = "site_menzoberranzan"
_SITE_C = "site_gracklstugh"


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


def _resolve_generics_by_action(session: CSession, action_id: str | None) -> list:
    return [m for m in session.legal_moves()
            if m._move_type == "resolve_generic" and m.data.get("action_id") == action_id]


def _resolve_generic_moves(session: CSession) -> list:
    return [m for m in session.legal_moves()
            if m._move_type == "resolve_generic"]


def _option_moves(session: CSession) -> list:
    return [m for m in session.legal_moves()
            if m._move_type == "resolve_generic"
            and m.data.get("target_id") != "unavailable"]


def _pick_option(session: CSession, option_id: str) -> None:
    for m in _option_moves(session):
        if m.data.get("action_id") == option_id:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"Option {option_id} not found in legal moves")


def _pick_trophy_from_player(session: CSession, player_id: str) -> None:
    for m in _resolve_generic_moves(session):
        if m.data.get("action_id") == player_id:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"Trophy move for {player_id} not found")


def _pick_deploy(session: CSession, node_id: str, slot_index: int) -> None:
    for m in _resolve_generic_moves(session):
        if m.data.get("action_id") == node_id:
            tid = m.data.get("target_id", "")
            if tid and isinstance(tid, str) and tid.endswith(f":{slot_index}"):
                session.submit_move(m)
                return
    session.destroy()
    raise AssertionError(f"Deploy move for {node_id} slot {slot_index} not found")


# ── viability tests ────────────────────────────────────────────────────────


def test_mummy_lord_option_2_unavailable_when_no_enemy_white_trophies():
    """option_2 grayed out when no enemy has a white trophy in their hall."""
    eng = _make_engine()
    session = make_card_test_session(eng, ["p1", "p2"], hand={"p1": [CARD_ID]}, current_player="p1")
    _play_card(session)
    rg = _resolve_generic_moves(session)
    available = [m for m in rg if m.data.get("target_id") != "unavailable"]
    assert any(m.data.get("action_id") == "option_1" for m in available)
    assert not any(m.data.get("action_id") == "option_2" for m in available)
    unavailable = [m for m in rg if m.data.get("target_id") == "unavailable"]
    assert any(m.data.get("action_id") == "option_2" for m in unavailable)
    session.destroy()


def test_mummy_lord_option_2_available_with_enemy_white_trophy():
    """option_2 is selectable when an enemy has a white trophy."""
    eng = _make_engine()
    session = make_card_test_session(eng, ["p1", "p2"], hand={"p1": [CARD_ID]}, current_player="p1")
    _set_trophy_hall(session, "p2", ["white"])
    _play_card(session)
    assert any(m.data.get("action_id") == "option_2" for m in _option_moves(session))
    session.destroy()


def test_mummy_lord_option_2_ignores_own_white_trophies():
    """option_2 unavailable when only the current player has white trophies."""
    eng = _make_engine()
    session = make_card_test_session(eng, ["p1", "p2"], hand={"p1": [CARD_ID]}, current_player="p1")
    _set_trophy_hall(session, "p1", ["white", "white"])
    _play_card(session)
    available = [m for m in _resolve_generic_moves(session) if m.data.get("target_id") != "unavailable"]
    assert not any(m.data.get("action_id") == "option_2" for m in available)
    session.destroy()


# ── single-choice tests ────────────────────────────────────────────────────


def test_mummy_lord_option_1_assassinates_white_troop():
    """Option 1: assassinate a white troop → goes to acting player's trophy hall."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": [CARD_ID]},
        troops={"p1": {_SITE_A: ["p1", "white", None]}},
        current_player="p1",
    )
    _play_card(session)
    _pick_option(session, "option_1")
    assassinate = _resolve_generic_moves(session)
    assert any(m.data.get("action_id") == _SITE_A for m in assassinate)
    session.submit_move(assassinate[0])
    troops = _troops_at_node(session, _SITE_A)
    assert "white" not in troops, f"White should be gone, got {troops}"
    assert "white" in _trophy_hall(session, "p1"), "White goes to p1's trophy hall"
    session.destroy()


def test_mummy_lord_option_2_steals_white_trophy_and_deploys():
    """Option 2: steal an enemy white trophy → deploy on the board."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": [CARD_ID]},
        troops={"p2": {_SITE_B: ["p2", None, None]}},
        current_player="p1",
    )
    _set_trophy_hall(session, "p2", ["white", "p1"])
    _play_card(session)
    _pick_option(session, "option_2")
    _pick_trophy_from_player(session, "p2")
    _pick_deploy(session, _SITE_B, 1)
    assert _trophy_hall(session, "p2") == ["p1"]
    assert "white" in _troops_at_node(session, _SITE_B)
    session.destroy()


def test_mummy_lord_option_2_deploys_anywhere_without_presence():
    """Option 2 deploy target: not restricted to presence sites."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": [CARD_ID]},
        troops={"p2": {_SITE_B: ["p2", None, None]}},
        current_player="p1",
    )
    _set_trophy_hall(session, "p2", ["white"])
    _play_card(session)
    _pick_option(session, "option_2")
    _pick_trophy_from_player(session, "p2")
    deploy = _resolve_generic_moves(session)
    assert deploy, "Deploy moves should exist even without presence at any site"
    session.submit_move(deploy[0])
    assert _trophy_hall(session, "p2") == []
    session.destroy()


# ── two-choice tests ───────────────────────────────────────────────────────


def test_mummy_lord_option_2_then_option_2():
    """Pick option_2 twice: steal from two different enemies."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2", "p3"],
        hand={"p1": [CARD_ID]},
        troops={"p1": {_SITE_A: ["p1", None, None]}},
        current_player="p1",
    )
    _set_trophy_hall(session, "p2", ["white", "white", "p1"])
    _set_trophy_hall(session, "p3", ["white"])

    _play_card(session)

    _pick_option(session, "option_2")
    _pick_trophy_from_player(session, "p2")
    _pick_deploy(session, _SITE_A, 1)

    assert _has_pending_generic(session)

    _pick_option(session, "option_2")
    _pick_trophy_from_player(session, "p3")
    _pick_deploy(session, _SITE_A, 2)

    assert not _has_pending_generic(session)

    assert len(_trophy_hall(session, "p2")) == 2
    assert _trophy_hall(session, "p3") == []
    session.destroy()


def test_mummy_lord_option_1_then_option_1():
    """Pick option_1 twice: assassinate two white troops at two sites."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": [CARD_ID]},
        troops={
            "p1": {
                _SITE_A: ["p1", "white", None],
                _SITE_B: ["p1", "white", None],
            },
        },
        current_player="p1",
    )
    _play_card(session)

    _pick_option(session, "option_1")
    assassinate1 = _resolve_generic_moves(session)
    session.submit_move(assassinate1[0])

    assert _has_pending_generic(session)

    _pick_option(session, "option_1")
    assassinate2 = _resolve_generic_moves(session)
    session.submit_move(assassinate2[0])

    assert not _has_pending_generic(session)

    assert sum(1 for t in _trophy_hall(session, "p1") if t == "white") == 2
    session.destroy()


def test_mummy_lord_option_2_then_option_1():
    """Pick option_2 (steal) then option_1 (assassinate)."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": [CARD_ID]},
        troops={
            "p1": {
                _SITE_A: ["p1", "white", None, None],
                _SITE_B: ["p1", None, None, None],
            },
        },
        current_player="p1",
    )
    _set_trophy_hall(session, "p2", ["white"])

    _play_card(session)

    _pick_option(session, "option_2")
    _pick_trophy_from_player(session, "p2")
    _pick_deploy(session, _SITE_B, 1)

    assert _has_pending_generic(session)

    _pick_option(session, "option_1")
    assassinate = _resolve_generic_moves(session)
    white_at_a = [m for m in assassinate if m.data.get("action_id") == _SITE_A]
    assert white_at_a
    session.submit_move(white_at_a[0])

    assert not _has_pending_generic(session)
    assert "white" not in _troops_at_node(session, _SITE_A)
    session.destroy()


def test_mummy_lord_option_1_then_option_2():
    """Pick option_1 (assassinate) then option_2 (steal+deploy)."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": [CARD_ID]},
        troops={"p1": {_SITE_A: ["p1", "white", None]}},
        current_player="p1",
    )
    _set_trophy_hall(session, "p2", ["white"])

    _play_card(session)

    _pick_option(session, "option_1")
    assassinate = _resolve_generic_moves(session)
    session.submit_move(assassinate[0])

    assert _has_pending_generic(session)

    _pick_option(session, "option_2")
    _pick_trophy_from_player(session, "p2")
    _pick_deploy(session, _SITE_A, 2)

    assert not _has_pending_generic(session)
    assert _trophy_hall(session, "p2") == []
    session.destroy()
