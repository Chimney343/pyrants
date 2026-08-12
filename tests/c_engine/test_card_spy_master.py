"""Spy Master card behavior tests via the C engine bindings.

Spy Master is the simplest spy card: ``rules_text`` is just "Place a spy.".
Its execution model is a single ``place_spy`` action targeting ``board_site``,
so playing the card opens one spy-placement selection and then resolves.
"""

from __future__ import annotations

import json
from pathlib import Path

from engine_c.bindings.engine_bindings import _lib
from tests.c_engine.card_test_helpers import (
    _make_engine,
    _session_player_index,
    _sptr,
    make_card_test_session,
)

_P1 = "p1"
_P2 = "p2"
_CARD = "spy_master"
_SITE_A = "site_gauntlgrym"
_SITE_B = "site_blingdenfire"

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _spies_at_node(session, node_id):
    s = _sptr(session).contents
    nid = _lib.intern(node_id.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            return [_lib.intern_str(s.nodes[ni].spies[i]).decode() for i in range(s.nodes[ni].spy_count)]
    return []


def _spies_available(session, pid):
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].spies_available


def _played_cards(session, pid):
    s = _sptr(session).contents
    pi = _session_player_index(session, pid)
    if pi < 0:
        return []
    ps = s.players[pi]
    return [_lib.intern_str(ps.played_cards[i]).decode() for i in range(ps.played_cards_count)]


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
    return session


def _play_card(session, card_id=_CARD):
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == card_id:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"{card_id} not playable")


def _resolve_spy_placement(session, node_id):
    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == node_id:
            session.submit_move(m)
            return
    available = [m.data for m in session.legal_moves() if m.move_type == "resolve_generic"]
    session.destroy()
    raise AssertionError(f"Place-spy move for {node_id} not found, available: {available}")


# ---------------------------------------------------------------------------
# Catalog structure
# ---------------------------------------------------------------------------


def test_spy_master_catalog_structure():
    """The catalog encodes rules_text as a single place_spy action on a board site."""
    with open(DATA_DIR / "cards" / "catalog.json", encoding="utf-8-sig") as f:
        catalog = json.load(f)

    card = next(c for c in catalog["cards"] if c["card_id"] == _CARD)
    assert card["name"] == "Spy Master"
    assert card["cost"] == 2
    assert card["aspect"] == "guile"
    assert card["rules_text"] == "Place a spy."

    em = card["execution_model"]
    assert em["kind"] == "sequence", f"Expected sequence, got {em['kind']}"
    actions = em["actions"]
    assert len(actions) == 1, f"Expected 1 action, got {len(actions)}"

    a = actions[0]
    assert a["op"] == "place_spy", f"Expected place_spy, got {a['op']}"
    assert a["target_scope"] == "board_site"
    assert a["timing"] == "immediate"
    assert a["optional"] is False


# ---------------------------------------------------------------------------
# C engine behavior
# ---------------------------------------------------------------------------


def test_spy_master_places_spy_on_selected_site():
    """Playing Spy Master opens a spy placement; selecting a site places the spy there."""
    session = _build_session()
    spies_before = _spies_available(session, _P1)

    _play_card(session)
    assert _has_pending_generic(session), "Spy placement should be pending after play"

    _resolve_spy_placement(session, _SITE_A)

    assert not _has_pending_generic(session), "No pending choice after placing the spy"
    assert _P1 in _spies_at_node(session, _SITE_A), f"Spy should be placed at {_SITE_A}"
    assert _spies_available(session, _P1) == spies_before - 1, (
        f"spies_available should decrease by 1: {spies_before} -> {_spies_available(session, _P1)}"
    )

    session.destroy()


def test_spy_master_offers_only_site_nodes():
    """The spy placement selection must offer site nodes only, never route nodes."""
    session = _build_session()

    _play_card(session)

    offered = [m.data.get("action_id") for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert offered, "Expected at least one spy placement target"

    for node_id in offered:
        assert node_id.startswith("site_"), f"Expected only site nodes, got {node_id}"
    assert not any(node_id.startswith("route_") for node_id in offered), (
        f"Route nodes must not be offered; got {offered}"
    )

    session.destroy()


def test_spy_master_cannot_place_two_spies_on_same_site():
    """A site already holding the player's spy is excluded from placement targets."""
    session = _build_session(spies={_SITE_A: [_P1]})

    _play_card(session)

    offered = [m.data.get("action_id") for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert _SITE_A not in offered, f"{_SITE_A} already has p1's spy and must be excluded; got {offered}"
    assert _SITE_B in offered, f"{_SITE_B} should still be a legal target; got {offered}"

    _resolve_spy_placement(session, _SITE_B)
    assert _P1 in _spies_at_node(session, _SITE_B)
    assert not _has_pending_generic(session)

    session.destroy()


def test_spy_master_moves_to_played_cards():
    """Playing Spy Master removes it from hand and puts it in played_cards."""
    session = _build_session()

    _play_card(session)
    _resolve_spy_placement(session, _SITE_A)

    played = _played_cards(session, _P1)
    assert _CARD in played, f"Expected {_CARD} in played_cards, got {played}"

    session.destroy()
