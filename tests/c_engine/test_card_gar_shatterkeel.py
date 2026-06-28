"""Gar Shatterkeel card behavior: deploy 3 troops, recruit Conquest card costing ≤4."""

from __future__ import annotations

from pathlib import Path

from engine_c.bindings.ce_api import CEngine
from engine_c.bindings.engine_bindings import MAX_ZONE_SIZE, _lib
from engine_c.bindings.session import CSession
from tests.c_engine.card_test_helpers import make_card_test_session

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _site_troops(session: CSession, node_id: str, player_id: str) -> int:
    s = session._state._ptr.contents
    node_sym = _lib.intern(node_id.encode())
    player_sym = _lib.intern(player_id.encode())
    for i in range(s.node_count):
        if s.nodes[i].node_id == node_sym:
            return sum(1 for j in range(s.nodes[i].troop_slot_count) if s.nodes[i].troop_slots[j] == player_sym)
    return 0


def _barracks(session: CSession, player_id: str) -> int:
    s = session._state._ptr.contents
    for i in range(s.player_count):
        pname = _lib.intern_str(s.player_ids[i])
        if pname and pname.decode() == player_id:
            return s.players[i].barracks
    return -1


def _play_card(session: CSession, card_id: str) -> None:
    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == card_id:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"{card_id} not in hand")


def test_gar_shatterkeel_deploys_three_troops():
    """Playing Gar Shatterkeel produces 3 deploy moves; resolving them deploys 3 troops."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards" / "catalog.json"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["gar_shatterkeel"]},
        troops={"p1": {"site_gauntlgrym": [None, None, None]}},
        current_player="p1",
    )

    barracks_before = _barracks(session, "p1")
    troops_before = _site_troops(session, "site_gauntlgrym", "p1")
    assert troops_before == 0

    _play_card(session, "gar_shatterkeel")

    for _ in range(3):
        deploy_moves = [m for m in session.legal_moves() if m._move_type == "resolve_generic"]
        assert deploy_moves, "Expected deploy move"
        session.submit_move(deploy_moves[0])

    troops_after = _site_troops(session, "site_gauntlgrym", "p1")
    assert troops_after == 3, f"Expected 3 troops deployed, got {troops_after}"
    assert _barracks(session, "p1") == barracks_before - 3

    session.destroy()


def test_gar_shatterkeel_recruit_filters_by_aspect_and_cost():
    """After deploying 3 troops, recruit moves only show Conquest cards costing ≤4."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards" / "catalog.json"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["gar_shatterkeel"]},
        troops={"p1": {"site_gauntlgrym": [None, None, None]}},
        current_player="p1",
    )

    market_cards = ["advance_scout", "balor", "noble"]
    ms = session._state._ptr.contents.market
    ms.row_count = min(len(market_cards), MAX_ZONE_SIZE)
    for j, cid in enumerate(market_cards[:MAX_ZONE_SIZE]):
        ms.row[j] = _lib.intern(cid.encode())

    session._state._ptr.contents.resource_pool.influence = 10

    _play_card(session, "gar_shatterkeel")

    for _ in range(3):
        deploy_moves = [m for m in session.legal_moves() if m._move_type == "resolve_generic"]
        assert deploy_moves
        session.submit_move(deploy_moves[0])

    recruit_moves = [m for m in session.legal_moves() if m._move_type == "resolve_generic"]
    assert recruit_moves, "Expected recruit move after deploy"

    target_ids = {m.data.get("action_id") for m in recruit_moves}
    assert "advance_scout" in target_ids, "advance_scout (conquest, cost 3) should be selectable"
    assert "balor" not in target_ids, "balor (conquest, cost 6) should NOT be selectable (>4)"
    assert "noble" not in target_ids, "noble (not conquest) should NOT be selectable"

    session.destroy()


def test_gar_shatterkeel_resolves_completely():
    """After deploying 3 troops and recruiting a card, there are no remaining choices."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards" / "catalog.json"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["gar_shatterkeel"]},
        troops={"p1": {"site_gauntlgrym": [None, None, None]}},
        current_player="p1",
    )

    market_cards = ["advance_scout"]
    ms = session._state._ptr.contents.market
    ms.row_count = min(len(market_cards), MAX_ZONE_SIZE)
    for j, cid in enumerate(market_cards[:MAX_ZONE_SIZE]):
        ms.row[j] = _lib.intern(cid.encode())

    session._state._ptr.contents.resource_pool.influence = 10

    _play_card(session, "gar_shatterkeel")

    for _ in range(3):
        deploy_moves = [m for m in session.legal_moves() if m._move_type == "resolve_generic"]
        assert deploy_moves
        session.submit_move(deploy_moves[0])

    recruit_moves = [m for m in session.legal_moves() if m._move_type == "resolve_generic"]
    assert recruit_moves
    session.submit_move(recruit_moves[0])

    remaining = [m for m in session.legal_moves() if m._move_type == "resolve_generic"]
    assert not remaining, f"Expected card fully resolved, got {len(remaining)} generic moves"

    session.destroy()
