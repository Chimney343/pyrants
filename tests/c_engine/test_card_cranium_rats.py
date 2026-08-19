"""Cranium Rats card behavior tests via the C engine bindings.

Verifies:
- Execution model: sequence with deploy_troops (2) + force_discard
- Deploy 2 troops sequentially on board nodes with presence
- Force an opponent with 3+ cards in hand to discard 1
- Discard auto-skips when no opponent has 3+ cards
- Card resolves cleanly after all actions complete
"""

from __future__ import annotations

from pathlib import Path

from engine_c.bindings.engine_bindings import PHASE_MAIN, _lib
from engine_c.bindings.session import CSession
from game_setup.loaders import assemble_catalog_payload
from tests.c_engine.card_test_helpers import (
    _make_engine,
    _session_player_index,
    _sptr,
    make_card_test_session,
)

CARD_ID = "cranium_rats"
_P1 = "p1"
_P2 = "p2"

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _has_pending_generic(session: CSession) -> bool:
    return bool(_sptr(session).contents.pending_generic)


def _hand_count(session: CSession, pid: str) -> int:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].hand_count


def _barracks(session: CSession, pid: str) -> int:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].barracks


def _resolve_generic_moves(session: CSession) -> list:
    return [m for m in session.legal_moves() if m.move_type == "resolve_generic"]


def _submit_first_resolve_generic(session: CSession) -> str:
    """Submit the first resolve_generic move. Returns its action_id."""
    for m in session.legal_moves():
        if m.move_type == "resolve_generic":
            action_id = m.data.get("action_id", "")
            session.submit_move(m)
            return action_id
    session.destroy()
    raise AssertionError("No resolve_generic move available")


def _submit_resolve_for_action_id(session: CSession, action_id: str) -> None:
    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == action_id:
            session.submit_move(m)
            return
    available = [m.data for m in session.legal_moves() if m.move_type == "resolve_generic"]
    session.destroy()
    raise AssertionError(
        f"resolve_generic move for {action_id} not found, available: {available}"
    )


def _play_card(session: CSession, card_id: str = CARD_ID) -> None:
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == card_id:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"{card_id} not playable")


def _build_session(**kwargs) -> CSession:
    defaults = {
        "player_ids": [_P1, _P2],
        "hand": {_P1: [CARD_ID]},
        "current_player": _P1,
    }
    defaults.update(kwargs)
    eng = _make_engine()
    session = make_card_test_session(eng, defaults.pop("player_ids"), **defaults)
    s = _sptr(session).contents
    s.phase = PHASE_MAIN
    return session


def _set_opponent_hand(session: CSession, pid: str, card: str, count: int) -> None:
    s = _sptr(session).contents
    pi = _session_player_index(session, pid)
    if pi < 0:
        return
    s.players[pi].hand_count = min(count, 40)
    for j in range(min(count, 40)):
        s.players[pi].hand[j] = _lib.intern(card.encode())


# ---------------------------------------------------------------------------
# Execution model validation
# ---------------------------------------------------------------------------


def test_cranium_rats_execution_model() -> None:
    """Validate the execution model structure from data/cards/."""
    catalog = assemble_catalog_payload(DATA_DIR / "cards")
    cards = catalog if isinstance(catalog, list) else catalog.get("cards", catalog)
    card = next(c for c in cards if c.get("card_id") == CARD_ID)

    assert card["cost"] == 2
    assert card["aspect"] == "conquest"
    assert "beast" in card["secondary_aspects"]
    assert card["deck_vp"] == 1
    assert card["inner_circle_vp"] == 3

    em = card["execution_model"]
    assert em["kind"] == "sequence"
    actions = em["actions"]
    assert len(actions) == 2

    deploy = actions[0]
    assert deploy["op"] == "deploy_troops"
    assert deploy["target_scope"] == "board_site"
    assert deploy["optional"] is False
    assert deploy["quantity"] == {"kind": "fixed", "value": 2}

    discard = actions[1]
    assert discard["op"] == "force_discard"
    assert discard["target_scope"] == "opponent"
    assert discard["optional"] is False


# ---------------------------------------------------------------------------
# Deploy + targeted discard (opponent has 3+ cards)
# ---------------------------------------------------------------------------


def test_cranium_rats_deploys_two_troops_and_forces_discard() -> None:
    """Play Cranium Rats: deploy 2 troops, then force p2 (4 cards) to discard 1."""
    session = _build_session()
    _set_opponent_hand(session, _P2, "noble", 4)
    barracks_before = _barracks(session, _P1)

    _play_card(session)
    assert _has_pending_generic(session), "Deploy should be pending"

    _submit_first_resolve_generic(session)
    assert _has_pending_generic(session), "Second deploy should be pending"

    _submit_first_resolve_generic(session)
    assert _has_pending_generic(session), "Discard should be pending"

    _submit_resolve_for_action_id(session, _P2)

    assert not _has_pending_generic(session)
    assert _barracks(session, _P1) == barracks_before - 2
    assert _hand_count(session, _P2) == 3

    session.destroy()


def test_cranium_rats_cannot_deploy_same_site_twice() -> None:
    """After deploying at a node, that node is excluded from the second deploy."""
    session = _build_session()
    _set_opponent_hand(session, _P2, "noble", 4)

    _play_card(session)
    node1 = _submit_first_resolve_generic(session)

    assert _has_pending_generic(session), "Second deploy should be pending"

    legal_nodes = [m.data.get("action_id") for m in _resolve_generic_moves(session)]
    assert node1 not in legal_nodes, (
        f"Node {node1} should be excluded (already deployed there); got {legal_nodes}"
    )
    assert len(legal_nodes) >= 1, f"Expected at least 1 deploy target; got {legal_nodes}"

    _submit_resolve_for_action_id(session, legal_nodes[0])
    assert _has_pending_generic(session), "Discard should be pending after deploys"

    _submit_resolve_for_action_id(session, _P2)
    assert not _has_pending_generic(session)

    session.destroy()


# ---------------------------------------------------------------------------
# Discard auto-skips when no opponent has 3+ cards
# ---------------------------------------------------------------------------


def test_cranium_rats_skips_discard_when_no_opponent_has_three_cards() -> None:
    """When all opponents have <3 cards, discard auto-skips after deploys."""
    session = _build_session()
    _set_opponent_hand(session, _P2, "noble", 2)

    _play_card(session)
    _submit_first_resolve_generic(session)

    rg = _resolve_generic_moves(session)
    assert rg, "Second deploy should be available"
    session.submit_move(rg[0])

    assert not _has_pending_generic(session), (
        "Discard should auto-skip when no opponent has 3+ cards"
    )
    assert _hand_count(session, _P2) == 2

    session.destroy()


def test_cranium_rats_only_targets_opponent_with_three_or_more_cards() -> None:
    """Opponent with <3 cards should not appear in discard target moves."""
    session = _build_session()
    _set_opponent_hand(session, _P2, "noble", 2)

    _play_card(session)
    _submit_first_resolve_generic(session)

    rg = _resolve_generic_moves(session)
    assert rg, "Second deploy should be available"
    session.submit_move(rg[0])

    discard_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    target_pids = [m.data.get("action_id") for m in discard_moves]
    assert _P2 not in target_pids, (
        f"P2 with 2 cards should not be targetable; got {target_pids}"
    )

    session.destroy()


# ---------------------------------------------------------------------------
# Card resolves cleanly
# ---------------------------------------------------------------------------


def test_cranium_rats_resolves_cleanly() -> None:
    """After both deploys and discard (or skip), no pending generic remains."""
    session = _build_session()
    _set_opponent_hand(session, _P2, "noble", 5)

    _play_card(session)
    _submit_first_resolve_generic(session)

    rg = _resolve_generic_moves(session)
    assert rg, "Second deploy should be available"
    session.submit_move(rg[0])

    _submit_resolve_for_action_id(session, _P2)

    assert not _has_pending_generic(session)

    session.destroy()
