"""Kobold card behavior tests.

Execution model: modal_choice (exactly_one)
  - Option 1 (option_1): deploy 1 troop to a board site
  - Option 2 (option_2): assassinate a white troop at a board site

Verifies:
  - Modal choice pending after play with source_card_id set
  - Exactly two options, no skip move
  - Option 1 deploys 1 troop, barracks decreases by 1
  - Option 2 assassinates a white troop, adds to trophy hall
  - Card fully resolves after choice (no pending generic)
  - Card stays in played_cards
  - Option 2 only targets white troops, not player troops
  - Option 2 unavailable without presence at site with white troop
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

_CARD = "kobold"
_P1 = "p1"
_P2 = "p2"
_WHITE = "white"
_SITE = "site_gauntlgrym"


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


def _has_pending_generic(session):
    return bool(_sptr(session).contents.pending_generic)


def _pending_source_card_id(session):
    pg = _sptr(session).contents.pending_generic
    if not pg:
        return ""
    sym = _lib.intern_str(pg.contents.source_card_id)
    return sym.decode() if sym else ""


def _played_cards_ids(session, pid):
    pi = _session_player_index(session, pid)
    if pi < 0:
        return []
    s = _sptr(session).contents
    ps = s.players[pi]
    return [_lib.intern_str(ps.played_cards[j]).decode() for j in range(ps.played_cards_count)]


def _set_troop_slot(session, node_id, slot_index, occupant):
    s = _sptr(session).contents
    nid = _lib.intern(node_id.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            s.nodes[ni].troop_slots[slot_index] = _lib.intern(occupant.encode()) if occupant else 0
            return


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
        if (
            m.move_type == "resolve_generic"
            and m.data.get("action_id") == node_id
            and m.data.get("target_id") == slot_str
        ):
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"Assassinate move for {node_id} slot {slot_index} not found")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_kobold_modal_choice_pending_after_play():
    """After playing Kobold, a pending generic choice exists with correct source_card_id."""
    session = _build_session()
    _play_card(session)

    assert _has_pending_generic(session), "Kobold must enter pending generic choice for modal"
    assert _pending_source_card_id(session) == _CARD, (
        f"Expected source_card_id {_CARD}, got {_pending_source_card_id(session)}"
    )
    session.destroy()


def test_kobold_modal_has_exactly_two_options_no_skip():
    """Modal offers exactly two options (option_1, option_2) with no skip move."""
    session = _build_session()
    _play_card(session)

    gen_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    target_moves = [m for m in gen_moves if m.data.get("action_id") is not None]
    skip_moves = [m for m in gen_moves if m.data.get("action_id") is None]

    assert len(target_moves) == 2, (
        f"Expected 2 modal options, got {len(target_moves)}: {[m.data for m in target_moves]}"
    )
    assert len(skip_moves) == 0, "No skip move for exactly_one modal"

    option_ids = {m.data["action_id"] for m in target_moves}
    assert option_ids == {"option_1", "option_2"}, f"Expected option_1 and option_2, got {option_ids}"
    session.destroy()


def test_kobold_option_1_deploys_one_troop():
    """Option 1 deploys 1 troop at a board site; barracks decreases by 1."""
    session = _build_session(
        spies={_SITE: [_P1]},
    )
    barracks_before = _barracks(session, _P1)
    troops_before = [t for t in _troops_at_node(session, _SITE) if t is not None]

    _play_card(session)
    _pick_option(session, "option_1")

    assert _has_pending_generic(session), "Deploy target selection should be pending"
    _resolve_deploy(session, _SITE)

    troops_after = [t for t in _troops_at_node(session, _SITE) if t is not None]
    assert len(troops_after) == len(troops_before) + 1, (
        f"Expected 1 more troop at {_SITE}, got {troops_after}"
    )
    assert _barracks(session, _P1) == barracks_before - 1, (
        f"Barracks should decrease by 1, was {barracks_before}, got {_barracks(session, _P1)}"
    )
    assert not _has_pending_generic(session), "Kobold should fully resolve after deploy"
    session.destroy()


def test_kobold_option_2_assassinates_white_troop():
    """Option 2 assassinates a white troop; adds to trophy hall."""
    session = _build_session(
        spies={_SITE: [_P1]},
        troops={_WHITE: {_SITE: [_WHITE, None, None]}},
    )

    trophy_before = _trophy_hall(session, _P1).count(_WHITE)
    troops_before = _troops_at_node(session, _SITE)
    assert _WHITE in troops_before, f"White troop should be at {_SITE}: {troops_before}"

    _play_card(session)
    _pick_option(session, "option_2")

    assert _has_pending_generic(session), "Assassinate target selection should be pending"

    troops = _troops_at_node(session, _SITE)
    white_slot = next((i for i, t in enumerate(troops) if t == _WHITE), None)
    assert white_slot is not None, f"No white troop to assassinate at {_SITE}, slots: {troops}"
    _resolve_assassinate(session, _SITE, white_slot)

    troops_after = _troops_at_node(session, _SITE)
    assert _WHITE not in troops_after, f"White troop should be assassinated: {troops_after}"

    trophy = _trophy_hall(session, _P1)
    assert trophy.count(_WHITE) == trophy_before + 1, (
        f"Trophy hall should contain {trophy_before + 1} white entries, got {trophy.count(_WHITE)}"
    )
    assert not _has_pending_generic(session), "Kobold should fully resolve after assassinate"
    session.destroy()


def test_kobold_option_2_only_targets_white_troops():
    """Option 2 should only allow assassinating white troops, not player troops."""
    session = _build_session(
        spies={_SITE: [_P1]},
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
    assert "0" not in target_slots, (
        f"p2 troop at slot 0 should not be a target; targets: {target_slots}"
    )
    assert "1" in target_slots, (
        f"White troop at slot 1 should be a target; targets: {target_slots}"
    )
    session.destroy()


def test_kobold_option_2_requires_presence():
    """Without presence at a site, option_2 should be marked unavailable."""
    session = _build_session()
    _set_troop_slot(session, _SITE, 0, _WHITE)

    _play_card(session)
    assert _has_pending_generic(session)

    generic_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    option_2_moves = [m for m in generic_moves if m.data.get("action_id") == "option_2"]

    assert option_2_moves, "option_2 should still be listed"
    assert option_2_moves[0].data.get("target_id") == "unavailable", (
        f"option_2 should be unavailable without presence, got {option_2_moves[0].data}"
    )
    session.destroy()


def test_kobold_option_2_no_white_targets_available():
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


def test_kobold_card_stays_in_played_cards_after_modal():
    """After fully resolving a modal option, the card remains in played_cards."""
    session = _build_session(
        spies={_SITE: [_P1]},
        troops={_WHITE: {_SITE: [_WHITE, None, None]}},
    )

    _play_card(session)
    _pick_option(session, "option_2")

    troops = _troops_at_node(session, _SITE)
    white_slot = next((i for i, t in enumerate(troops) if t == _WHITE), None)
    _resolve_assassinate(session, _SITE, white_slot)

    played = _played_cards_ids(session, _P1)
    assert _CARD in played, f"Kobold should be in played_cards, got {played}"
    assert not _has_pending_generic(session), "Kobold should fully resolve"
    session.destroy()


def test_kobold_resolves_after_modal_choice_option_1():
    """After deploying via option_1, no pending generic remains and main phase can end."""
    session = _build_session(
        spies={_SITE: [_P1]},
    )

    _play_card(session)
    _pick_option(session, "option_1")
    _resolve_deploy(session, _SITE)

    assert not _has_pending_generic(session), "Kobold should fully resolve after deploy"

    move_types = {m.move_type for m in session.legal_moves()}
    assert "end_main_phase" in move_types, "Should be able to end main phase after resolution"
    session.destroy()


def test_kobold_resolves_after_modal_choice_option_2():
    """After assassinating via option_2, no pending generic remains and main phase can end."""
    session = _build_session(
        spies={_SITE: [_P1]},
        troops={_WHITE: {_SITE: [_WHITE, None, None]}},
    )

    _play_card(session)
    _pick_option(session, "option_2")

    troops = _troops_at_node(session, _SITE)
    white_slot = next((i for i, t in enumerate(troops) if t == _WHITE), None)
    _resolve_assassinate(session, _SITE, white_slot)

    assert not _has_pending_generic(session), "Kobold should fully resolve after assassinate"

    move_types = {m.move_type for m in session.legal_moves()}
    assert "end_main_phase" in move_types, "Should be able to end main phase after resolution"
    session.destroy()
