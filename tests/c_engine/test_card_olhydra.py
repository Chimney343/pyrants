"""Olhydra card behavior tests.

Olhydra (6-cost, Conquest/Elemental Prince):
  Supplant a white troop anywhere on the board.
  If the Conquest focus condition is met, deploy 2 troops.
"""

from __future__ import annotations

import json
from pathlib import Path

from engine_c.bindings.engine_bindings import _lib
from engine_c.bindings.session import CSession
from tests.c_engine.card_test_helpers import (
    _make_engine,
    _session_player_index,
    _sptr,
    make_card_test_session,
)

_P1 = "p1"
_P2 = "p2"
_SITE_A = "site_gauntlgrym"
_SITE_B = "site_jhachalkhyn"
_SITE_C = "site_gracklstugh"
_CARD_ID = "olhydra"

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _has_pending_generic(session: CSession) -> bool:
    return bool(_sptr(session).contents.pending_generic)


def _barracks(session: CSession, pid: str) -> int:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].barracks


def _trophy_count(session: CSession, pid: str) -> int:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].trophy_hall_count


def _node_troop_owners(session: CSession, node_id: str) -> list[str | None]:
    s = _sptr(session).contents
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


def _site_player_troops(session: CSession, node_id: str, player_id: str) -> int:
    s = _sptr(session).contents
    node_sym = _lib.intern(node_id.encode())
    player_sym = _lib.intern(player_id.encode())
    for i in range(s.node_count):
        if s.nodes[i].node_id == node_sym:
            return sum(1 for j in range(s.nodes[i].troop_slot_count)
                       if s.nodes[i].troop_slots[j] == player_sym)
    return 0


def _play_card(session: CSession, card_id: str) -> None:
    playable = [m for m in session.legal_moves()
                if getattr(m, "move_type", "") == "play_card"
                and m.data.get("card_id") == card_id]
    assert playable, f"{card_id} not playable"
    session.submit_move(playable[0])


# ---------------------------------------------------------------------------
# Execution model validation
# ---------------------------------------------------------------------------

def test_olhydra_execution_model_supplant_then_conditional_deploy() -> None:
    catalog = json.loads((DATA_DIR / "cards" / "catalog.json").read_text(encoding="utf-8"))
    cards = catalog if isinstance(catalog, list) else catalog.get("cards", catalog)
    card = next(c for c in cards if c.get("card_id") == "olhydra")

    actions = card["execution_model"]["actions"]
    assert len(actions) == 2

    supplant = actions[0]
    assert supplant["op"] == "supplant_troop"
    assert supplant["target_scope"] == "board_site"
    assert supplant["filters"] == ["white_troop_only"]
    assert supplant["metadata"]["ignore_presence_requirement"] is True
    assert supplant["metadata"]["targeting"] == "anywhere"
    assert supplant["optional"] is False

    deploy = actions[1]
    assert deploy["op"] == "deploy_troops"
    assert deploy["quantity"] == {"kind": "fixed", "value": 2}
    assert deploy["metadata"]["requires_focus"] is True
    assert deploy["metadata"]["focus_aspect"] == "conquest"
    assert deploy["optional"] is False

    assert "Supplant a white troop" in card["rules_text"]
    assert "deploy 2 troops" in card["rules_text"]

    assert card["cost"] == 6
    assert card["aspect"] == "conquest"
    assert "elemental prince" in card["secondary_aspects"]
    assert card["deck_vp"] == 3
    assert card["inner_circle_vp"] == 6


# ---------------------------------------------------------------------------
# Supplant tests
# ---------------------------------------------------------------------------

def test_olhydra_supplants_white_troop_anywhere_without_presence() -> None:
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [_CARD_ID]},
        troops={
            _P1: {_SITE_A: [_P1, None]},
            _P2: {_SITE_B: ["white", None, None]},
        },
        current_player=_P1,
    )

    before_barracks = _barracks(session, _P1)
    before_trophies = _trophy_count(session, _P1)

    _play_card(session, _CARD_ID)
    assert _has_pending_generic(session), "Should await supplant target selection"

    supplant_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    white_target = next(
        (m for m in supplant_moves if m.data.get("action_id") == _SITE_B and m.data.get("target_id") == "0"),
        None,
    )
    assert white_target is not None, (
        f"No supplant move for white troop at {_SITE_B} slot 0; "
        f"moves: {[(m.data.get('action_id'), m.data.get('target_id')) for m in supplant_moves]}"
    )
    session.submit_move(white_target)

    slots_after = _node_troop_owners(session, _SITE_B)
    assert "white" not in slots_after, f"White troop should be gone from {_SITE_B}: {slots_after}"

    assert _barracks(session, _P1) == before_barracks - 1, (
        f"Supplant should cost 1 troop from barracks: was {before_barracks}, now {_barracks(session, _P1)}"
    )
    assert _trophy_count(session, _P1) == before_trophies + 1, (
        "Supplant should add displaced white troop to trophy hall"
    )
    assert _site_player_troops(session, _SITE_B, _P1) == 1, (
        "P1 should have 1 troop at site_B after supplant"
    )

    session.destroy()


def test_olhydra_supplant_only_targets_white_troops_not_player_troops() -> None:
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [_CARD_ID]},
        troops={
            _P1: {_SITE_A: [_P1, None]},
            _P2: {_SITE_B: [_P2, "white"]},
        },
        current_player=_P1,
    )

    _play_card(session, _CARD_ID)

    supplant_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    site_b_targets = [m.data.get("target_id") for m in supplant_moves if m.data.get("action_id") == _SITE_B]
    assert "1" in site_b_targets, f"White troop at {_SITE_B} slot 1 should be supplantable; targets: {site_b_targets}"
    assert "0" not in site_b_targets, f"P2 troop at {_SITE_B} slot 0 must NOT be supplantable; targets: {site_b_targets}"

    session.destroy()


def test_olhydra_supplant_available_at_multiple_white_troop_sites() -> None:
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [_CARD_ID]},
        troops={
            _P1: {_SITE_A: [_P1, None]},
            _P2: {
                _SITE_B: ["white", None],
                _SITE_C: ["white", None],
            },
        },
        current_player=_P1,
    )

    _play_card(session, _CARD_ID)

    supplant_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    target_sites = {m.data.get("action_id") for m in supplant_moves}
    assert _SITE_B in target_sites, f"{_SITE_B} should be targetable"
    assert _SITE_C in target_sites, f"{_SITE_C} should be targetable"

    session.destroy()


# ---------------------------------------------------------------------------
# Conquest focus: deploy 2 troops
# ---------------------------------------------------------------------------

def test_olhydra_deploys_two_troops_with_conquest_focus() -> None:
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [_CARD_ID, "advance_scout"]},
        troops={
            _P2: {_SITE_A: ["white", None, None]},
        },
        current_player=_P1,
    )

    before_barracks = _barracks(session, _P1)

    _play_card(session, _CARD_ID)

    supplant_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    white_target = next(
        (m for m in supplant_moves if m.data.get("action_id") == _SITE_A and m.data.get("target_id") == "0"),
        None,
    )
    assert white_target is not None, f"No supplant move for white at {_SITE_A} slot 0"
    session.submit_move(white_target)

    assert _has_pending_generic(session), "Should await deploy target selection"

    deploy_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert len(deploy_moves) >= 1, f"Expected deploy moves, got {len(deploy_moves)}"

    for _ in range(2):
        assert _has_pending_generic(session), "Should still await deploy selection"
        site_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
        deploy = next(
            (m for m in site_moves if m.data.get("action_id") == _SITE_A),
            None,
        )
        assert deploy is not None, f"No deploy move for {_SITE_A}"
        session.submit_move(deploy)

    assert not _has_pending_generic(session), "Card should be fully resolved"
    assert _barracks(session, _P1) == before_barracks - 3, (
        f"Barracks should decrease by 3 (1 supplant + 2 deploy): was {before_barracks}, now {_barracks(session, _P1)}"
    )
    assert _site_player_troops(session, _SITE_A, _P1) == 3, (
        "P1 should have 3 troops at site_A (1 from supplant + 2 from deploy)"
    )

    session.destroy()


def test_olhydra_no_deploy_without_conquest_focus() -> None:
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [_CARD_ID, "noble"]},
        troops={
            _P2: {_SITE_A: ["white", None, None]},
        },
        current_player=_P1,
    )

    before_barracks = _barracks(session, _P1)

    _play_card(session, _CARD_ID)

    supplant_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    white_target = next(
        (m for m in supplant_moves if m.data.get("action_id") == _SITE_A and m.data.get("target_id") == "0"),
        None,
    )
    assert white_target is not None, f"No supplant move for white at {_SITE_A} slot 0"
    session.submit_move(white_target)

    assert not _has_pending_generic(session), (
        "Without conquest focus, card should be fully resolved after supplant"
    )
    assert _barracks(session, _P1) == before_barracks - 1, (
        f"Only supplant should cost barracks: was {before_barracks}, now {_barracks(session, _P1)}"
    )

    session.destroy()


def test_olhydra_focus_from_played_conquest_card() -> None:
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [_CARD_ID]},
        troops={
            _P2: {_SITE_A: ["white", None, None]},
        },
        current_player=_P1,
    )
    s = _sptr(session).contents
    p1_idx = _session_player_index(session, _P1)
    ps = s.players[p1_idx]
    ps.played_cards[0] = _lib.intern(b"advance_scout")
    ps.played_cards_count = 1

    before_barracks = _barracks(session, _P1)

    _play_card(session, _CARD_ID)

    supplant_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    white_target = next(
        (m for m in supplant_moves if m.data.get("action_id") == _SITE_A and m.data.get("target_id") == "0"),
        None,
    )
    assert white_target is not None
    session.submit_move(white_target)

    assert _has_pending_generic(session), "Should have deploy moves from played-zone conquest focus"
    deploy_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert len(deploy_moves) >= 1, f"Expected deploy moves, got {len(deploy_moves)}"

    for _ in range(2):
        site_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
        deploy = next((m for m in site_moves if m.data.get("action_id") == _SITE_A), None)
        assert deploy is not None
        session.submit_move(deploy)

    assert not _has_pending_generic(session)
    assert _barracks(session, _P1) == before_barracks - 3

    session.destroy()


def test_olhydra_resolves_completely_with_focus() -> None:
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [_CARD_ID, "advance_scout"]},
        troops={
            _P2: {_SITE_A: ["white", None, None]},
        },
        current_player=_P1,
    )

    _play_card(session, _CARD_ID)

    supplant_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    session.submit_move(supplant_moves[0])

    for _ in range(2):
        site_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
        session.submit_move(site_moves[0])

    remaining = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert not remaining, f"Expected card fully resolved, got {len(remaining)} generic moves"
    assert not _has_pending_generic(session)

    session.destroy()
