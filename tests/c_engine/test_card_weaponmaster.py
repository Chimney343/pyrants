"""Weaponmaster card behavior tests.

Verifies the modal_choice execution model:

- Option 1: deploy exactly 1 troop to a site.
- Option 2: assassinate a neutral white troop (normal legality — presence
  required), limited to white troops only.

``rules_text``: "Choose exactly one mode. Either deploy 1 troop, or
assassinate a white troop."
"""

from __future__ import annotations

from pathlib import Path

from engine_c.bindings.engine_bindings import PHASE_MAIN, _lib
from tests.c_engine.card_test_helpers import (
    _make_engine,
    _session_player_index,
    _sptr,
    make_card_test_session,
)

_P1 = "p1"
_P2 = "p2"
_WHITE = "white"
_SITE = "site_gauntlgrym"


def _build_weaponmaster_session(*, spies: dict | None = None,
                                troops: dict | None = None,
                                current_player: str = _P2):
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={current_player: ["weaponmaster", "noble"]},
        spies=spies,
        troops=troops,
        current_player=current_player,
    )
    s = session._state._ptr.contents
    s.phase = PHASE_MAIN
    return session


def _play_weaponmaster(session) -> None:
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == "weaponmaster":
            session.submit_move(m)
            return
    raise AssertionError("Weaponmaster not playable")


def _resolve_moves(session) -> list:
    return [m for m in session.legal_moves() if m.move_type == "resolve_generic"]


def _trophy_hall(session, pid: str) -> list[str]:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return []
    s = _sptr(session).contents
    ps = s.players[pi]
    return [_lib.intern_str(ps.trophy_hall[j]).decode() for j in range(ps.trophy_hall_count)]


def _barracks(session, pid: str) -> int:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return -1
    return _sptr(session).contents.players[pi].barracks


def _troops_at_node(session, node_id: str) -> list[str | None]:
    s = _sptr(session).contents
    nid = _lib.intern(node_id.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            ns = s.nodes[ni]
            return [
                _lib.intern_str(ns.troop_slots[i]).decode()
                if ns.troop_slots[i] != 0
                else None
                for i in range(ns.troop_slot_count)
            ]
    return []


def _has_pending_generic(session) -> bool:
    return bool(_sptr(session).contents.pending_generic)


def _option_move(session, option_id: str):
    matches = [m for m in _resolve_moves(session) if m.data.get("action_id") == option_id]
    assert matches, f"{option_id} not offered; moves={[m.data for m in _resolve_moves(session)]}"
    return matches[0]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_weaponmaster_deploy_one_troop():
    """Option 1 deploys exactly one troop, reducing barracks by 1."""
    session = _build_weaponmaster_session()

    barracks_before = _barracks(session, _P2)
    assert barracks_before > 0

    _play_weaponmaster(session)
    assert _has_pending_generic(session)

    option_1 = _option_move(session, "option_1")
    assert option_1.data.get("target_id") is None, (
        f"option_1 (deploy) should be viable, got target_id={option_1.data.get('target_id')}"
    )
    session.submit_move(option_1)

    # Deploy selection: node ids in action_id.
    deploy_moves = _resolve_moves(session)
    site_move = [m for m in deploy_moves if m.data.get("action_id") == _SITE]
    assert site_move, f"No deploy target for {_SITE}; moves={[m.data for m in deploy_moves]}"
    session.submit_move(site_move[0])

    assert not _has_pending_generic(session)
    assert _barracks(session, _P2) == barracks_before - 1, (
        f"Expected barracks {barracks_before - 1}, got {_barracks(session, _P2)}"
    )
    assert _P2 in _troops_at_node(session, _SITE), (
        f"Expected a {_P2} troop at {_SITE}, got {_troops_at_node(session, _SITE)}"
    )

    session.destroy()


def test_weaponmaster_assassinate_white_troop():
    """Option 2 assassinates a neutral white troop into the trophy hall."""
    session = _build_weaponmaster_session(spies={_SITE: [_P2]})

    troops_before = _troops_at_node(session, _SITE)
    white_count_before = troops_before.count(_WHITE)
    assert white_count_before > 0, f"Expected white troops at {_SITE}, got {troops_before}"

    _play_weaponmaster(session)
    assert _has_pending_generic(session)

    option_2 = _option_move(session, "option_2")
    assert option_2.data.get("target_id") != "unavailable", (
        "option_2 should be viable with a white troop at a presence site"
    )
    session.submit_move(option_2)

    # Assassinate selection: node id in action_id, slot index in target_id.
    assassinate_moves = _resolve_moves(session)
    white_move = None
    for am in assassinate_moves:
        if am.data.get("action_id") == _SITE:
            white_move = am
            break
    assert white_move is not None, (
        f"White troop at {_SITE} should be targetable; moves={[m.data for m in assassinate_moves]}"
    )
    slot = int(white_move.data.get("target_id"))
    assert _troops_at_node(session, _SITE)[slot] == _WHITE

    session.submit_move(white_move)
    assert not _has_pending_generic(session)

    trophy = _trophy_hall(session, _P2)
    assert trophy.count(_WHITE) == 1, f"Expected one white trophy, got {trophy}"

    troops_after = _troops_at_node(session, _SITE)
    assert troops_after.count(_WHITE) == white_count_before - 1, (
        f"Expected one fewer white troop at {_SITE}, was {troops_before}, now {troops_after}"
    )

    session.destroy()


def test_weaponmaster_assassinate_requires_presence():
    """Without presence at any white-troop site, option_2 is unavailable."""
    session = _build_weaponmaster_session()

    _play_weaponmaster(session)

    option_2 = _option_move(session, "option_2")
    assert option_2.data.get("target_id") == "unavailable", (
        "Without presence, option_2 should be unavailable"
    )

    session.destroy()


def test_weaponmaster_assassinate_white_only():
    """A non-white (player) troop at a presence site is not a legal target."""
    session = _build_weaponmaster_session(
        spies={_SITE: [_P2]},
        troops={_P1: {_SITE: [_P1, None, None]}},
    )

    _play_weaponmaster(session)

    option_2 = _option_move(session, "option_2")
    assert option_2.data.get("target_id") == "unavailable", (
        "With only a player troop (not white) at the presence site, "
        "option_2 should be unavailable"
    )

    session.destroy()


def test_weaponmaster_catalog_actions():
    """The execution model encodes exactly-one modal deploy | white assassinate."""
    import json

    catalog_path = Path(__file__).resolve().parents[2] / "data" / "cards" / "catalog.json"
    with open(catalog_path, encoding="utf-8") as f:
        catalog = json.load(f)

    card = None
    for c in catalog["cards"]:
        if c["card_id"] == "weaponmaster":
            card = c
            break
    assert card is not None, "Weaponmaster not found in catalog"

    em = card["execution_model"]
    assert em["kind"] == "modal_choice"
    assert em["selection"] == "exactly_one"
    assert len(em["options"]) == 2

    deploy_opts = [o for o in em["options"] if o["option_id"] == "option_1"]
    assassinate_opts = [o for o in em["options"] if o["option_id"] == "option_2"]
    assert len(deploy_opts) == 1 and len(assassinate_opts) == 1

    deploy_action = deploy_opts[0]["actions"][0]
    assert deploy_action["op"] == "deploy_troops"
    assert deploy_action["quantity"] == {"kind": "fixed", "value": 1}

    assassinate_action = assassinate_opts[0]["actions"][0]
    assert assassinate_action["op"] == "assassinate_troop"
    assert "white_troop_only" in assassinate_action["filters"]
