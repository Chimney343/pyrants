"""Ettin card behavior tests.

Modal choice: choose exactly one mode.
- Option 1: deploy 3 troops at a board site.
- Option 2: assassinate 2 white troops at a board site.
"""

from __future__ import annotations

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))

from engine_c.bindings.engine_bindings import PHASE_MAIN, _lib
from tests.c_engine.card_test_helpers import (
    _make_engine,
    _session_player_index,
    _sptr,
    make_card_test_session,
)

_SITE = "site_gauntlgrym"
_SITE2 = "site_jhachalkhyn"
_P1 = "p1"
_P2 = "p2"
_WHITE = "white"
_CARD = "ettin"


def _barracks(session, pid):
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].barracks


def _troops_at_node(session, node_id):
    s = _sptr(session).contents
    nid = _lib.intern(node_id.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            return [
                _lib.intern_str(s.nodes[ni].troop_slots[i]).decode()
                if s.nodes[ni].troop_slots[i] != 0
                else None
                for i in range(s.nodes[ni].troop_slot_count)
            ]
    return []


def _trophy_hall(session, pid):
    pi = _session_player_index(session, pid)
    if pi < 0:
        return []
    s = _sptr(session).contents
    ps = s.players[pi]
    return [_lib.intern_str(ps.trophy_hall[j]).decode() for j in range(ps.trophy_hall_count)]


def _spies_at_node(session, node_id):
    s = _sptr(session).contents
    nid = _lib.intern(node_id.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            return [_lib.intern_str(s.nodes[ni].spies[i]).decode() for i in range(s.nodes[ni].spy_count)]
    return []


def _has_pending_generic(session):
    return bool(_sptr(session).contents.pending_generic)


def _build_session(**kwargs):
    defaults = {
        "player_ids": [_P1, _P2],
        "hand": {_P1: [_CARD]},
        "current_player": _P1,
    }
    defaults.update(kwargs)
    eng = _make_engine()
    session = make_card_test_session(eng, defaults.pop("player_ids"), **defaults)
    s = session._state._ptr.contents
    s.phase = PHASE_MAIN
    return session


def _play_card(session):
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == _CARD:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"{_CARD} not playable")


def _pick_option(session, option_id):
    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == option_id:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"{option_id} not found in resolve_generic moves")


def _resolve_deploy(session, node_id):
    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == node_id:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"Deploy move for {node_id} not found")


def _resolve_assassinate(session, node_id, slot_index):
    slot_str = str(slot_index)
    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == node_id and m.data.get("target_id") == slot_str:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"Assassinate move for {node_id} slot {slot_index} not found")


def _set_troop_slot(session, node_id, slot_index, occupant):
    s = _sptr(session).contents
    nid = _lib.intern(node_id.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            if occupant is None:
                s.nodes[ni].troop_slots[slot_index] = 0
            else:
                s.nodes[ni].troop_slots[slot_index] = _lib.intern(occupant.encode())
            if s.nodes[ni].troop_slot_count < slot_index + 1:
                s.nodes[ni].troop_slot_count = slot_index + 1
            return


# ---------------------------------------------------------------------------
# Tests — both options available
# ---------------------------------------------------------------------------


def test_both_options_available():
    """After playing Ettin with presence at a site, both option_1 and option_2 should be selectable."""
    session = _build_session(
        spies={_SITE: [_P1]},
        troops={_P1: {_SITE: [None, None, None]}},
    )
    _set_troop_slot(session, _SITE, 0, _WHITE)
    _set_troop_slot(session, _SITE, 1, _WHITE)

    _play_card(session)
    assert _has_pending_generic(session), "Modal choice should be pending after play"

    generic_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    option_1_moves = [m for m in generic_moves if m.data.get("action_id") == "option_1"]
    option_2_moves = [m for m in generic_moves if m.data.get("action_id") == "option_2"]

    assert option_1_moves, "option_1 (deploy 3 troops) should be available"
    assert option_2_moves, "option_2 (assassinate 2 white troops) should be available"

    assert option_1_moves[0].data.get("target_id") != "unavailable", "option_1 should not be marked unavailable"
    assert option_2_moves[0].data.get("target_id") != "unavailable", "option_2 should not be marked unavailable"

    session.destroy()


# ---------------------------------------------------------------------------
# Option 1 — deploy 3 troops
# ---------------------------------------------------------------------------


def test_option_1_deploys_three_troops():
    """Option 1 deploys exactly 3 troops to the chosen site; barracks decreases by 3."""
    session = _build_session(
        spies={_SITE: [_P1]},
        troops={_P1: {_SITE: [None, None, None]}},
    )

    barracks_before = _barracks(session, _P1)

    _play_card(session)
    _pick_option(session, "option_1")

    deploys = 0
    while _has_pending_generic(session):
        _resolve_deploy(session, _SITE)
        deploys += 1
        if deploys > 5:
            break

    assert deploys == 3, f"Should require exactly 3 deploy selections, got {deploys}"
    assert not _has_pending_generic(session), "Option 1 should resolve after 3 deploys"
    assert _barracks(session, _P1) == barracks_before - 3, f"Barracks should decrease by 3, was {barracks_before}, now {_barracks(session, _P1)}"

    troops = _troops_at_node(session, _SITE)
    assert troops.count(_P1) == 3, f"Expected 3 p1 troops at {_SITE}, got {troops}"

    session.destroy()


def test_option_1_deploy_no_presence_has_deploy_targets():
    """Picking option_1 without presence still presents deploy site options (all board sites)."""
    session = _build_session()

    _play_card(session)
    assert _has_pending_generic(session)

    _pick_option(session, "option_1")

    deploy_moves = [
        m for m in session.legal_moves()
        if m.move_type == "resolve_generic"
        and m.data.get("action_id") is not None
        and m.data.get("target_id") is None
    ]
    assert len(deploy_moves) > 0, "Option 1 should present deploy site choices"

    session.destroy()


def test_option_1_deploys_at_chosen_site():
    """Option 1 can deploy 3 troops; a site with presence is among the deploy options."""
    session = _build_session(
        spies={_SITE: [_P1]},
        troops={
            _P1: {
                _SITE: [None, None, None],
            }
        },
    )

    _play_card(session)
    _pick_option(session, "option_1")

    site_options = set()
    deploys = 0
    while _has_pending_generic(session):
        deploy_moves = [
            m for m in session.legal_moves()
            if m.move_type == "resolve_generic"
            and m.data.get("action_id") is not None
            and m.data.get("target_id") is None
        ]
        assert deploy_moves, f"Should have deploy choices; got {[m.data for m in session.legal_moves() if m.move_type == 'resolve_generic']}"

        for dm in deploy_moves[:3]:
            site_options.add(dm.data.get("action_id"))
        deploy_to = deploy_moves[0]
        session.submit_move(deploy_to)
        deploys += 1
        if deploys > 5:
            break

    assert deploys == 3, f"Should require exactly 3 deploy selections, got {deploys}"
    assert _SITE in site_options, f"Site {_SITE} with presence should be a deploy option; options: {site_options}"

    session.destroy()


# ---------------------------------------------------------------------------
# Option 2 — assassinate 2 white troops
# ---------------------------------------------------------------------------


def test_option_2_assassinates_two_white_troops():
    """Option 2 assassinates 2 white troops at a site with presence; they go to trophy hall."""
    session = _build_session(
        spies={_SITE: [_P1]},
        troops={_P1: {_SITE: [None, None, None]}},
    )
    _set_troop_slot(session, _SITE, 0, _WHITE)
    _set_troop_slot(session, _SITE, 1, _WHITE)

    _play_card(session)
    _pick_option(session, "option_2")

    assert _has_pending_generic(session), "Assassinate target selection should be pending"

    assassinations = 0
    while _has_pending_generic(session):
        slots = _troops_at_node(session, _SITE)
        target_slot = None
        for i, occ in enumerate(slots):
            if occ == _WHITE:
                target_slot = i
                break
        assert target_slot is not None, f"No white troop to assassinate at {_SITE}, slots: {slots}"
        _resolve_assassinate(session, _SITE, target_slot)
        assassinations += 1
        if assassinations > 5:
            break

    assert assassinations == 2, f"Should assassinate exactly 2 white troops, got {assassinations}"
    assert not _has_pending_generic(session), "Option 2 should resolve after 2 assassinations"

    troops = _troops_at_node(session, _SITE)
    assert _WHITE not in troops, f"No white troops should remain at {_SITE}, got {troops}"

    trophy = _trophy_hall(session, _P1)
    assert trophy.count(_WHITE) == 2, f"Trophy hall should contain 2 white entries, got {trophy}"

    session.destroy()


def test_option_2_only_targets_white_troops():
    """Option 2 should not allow assassinating player troops."""
    session = _build_session(
        spies={_SITE: [_P1]},
        troops={_P1: {_SITE: [None, None, None]}},
    )
    _set_troop_slot(session, _SITE, 0, _P2)
    _set_troop_slot(session, _SITE, 1, _WHITE)

    _play_card(session)
    _pick_option(session, "option_2")

    assert _has_pending_generic(session), "Assassinate target selection should be pending"

    assassinate_moves = [
        m for m in session.legal_moves()
        if m.move_type == "resolve_generic" and m.data.get("action_id") == _SITE
    ]
    target_slots = {m.data.get("target_id") for m in assassinate_moves}
    assert "0" not in target_slots, f"p2 troop at slot 0 should not be a target; targets: {target_slots}"
    assert "1" in target_slots, f"White troop at slot 1 should be a target; targets: {target_slots}"

    session.destroy()


def test_option_2_requires_presence():
    """Without presence at a site, option_2 should be marked unavailable."""
    session = _build_session(
        troops={_P1: {_SITE: [None, None, None]}},
    )
    _set_troop_slot(session, _SITE, 0, _WHITE)
    _set_troop_slot(session, _SITE, 1, _WHITE)

    _play_card(session)
    assert _has_pending_generic(session)

    generic_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    option_2_moves = [m for m in generic_moves if m.data.get("action_id") == "option_2"]

    assert option_2_moves, "option_2 should still be listed"
    assert option_2_moves[0].data.get("target_id") == "unavailable", (
        f"option_2 should be unavailable without presence, got {option_2_moves[0].data}"
    )

    session.destroy()


def test_option_2_no_targets_available():
    """Without white troops on the board, option_2 should have no targets."""
    session = _build_session(
        spies={_SITE: [_P1]},
        troops={_P1: {_SITE: [None, None, None]}},
    )

    _play_card(session)
    _pick_option(session, "option_2")

    assassinate_moves = [
        m for m in session.legal_moves()
        if m.move_type == "resolve_generic" and m.data.get("action_id") == _SITE
    ]
    assert len(assassinate_moves) == 0, (
        f"With no white troops, no assassinate targets should exist; got {[m.data for m in assassinate_moves]}"
    )

    session.destroy()
