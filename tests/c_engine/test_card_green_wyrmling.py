"""Green Wyrmling card behavior tests: place spy + conditional 2 influence."""

from __future__ import annotations

from pathlib import Path

from engine_c.bindings.ce_api import CEngine
from engine_c.bindings.session import CSession
from tests.c_engine.card_test_helpers import make_card_test_session

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _play_card(session: CSession, card_id: str) -> None:
    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == card_id:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"{card_id} not in hand")


def _influence(session: CSession) -> int:
    return session._state._ptr.contents.resource_pool.influence


def _has_pending_generic(session: CSession) -> bool:
    return any(m._move_type == "resolve_generic" for m in session.legal_moves())


def _submit_spy_placement(session: CSession, node_id: str) -> None:
    rg = [m for m in session.legal_moves() if m._move_type == "resolve_generic"]
    site_moves = [m for m in rg if m.data.get("action_id") == node_id]
    assert site_moves, f"No resolve_generic move for {node_id}, moves: {[m.data for m in rg]}"
    session.submit_move(site_moves[0])


def test_green_wyrmling_gains_2_influence_when_other_player_troop_present():
    """Place spy on site with another player's troop → gain 2 influence."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["green_wyrmling"]},
        troops={"p1": {"site_gauntlgrym": ["p2", None, None]}},
        current_player="p1",
    )

    before = _influence(session)

    _play_card(session, "green_wyrmling")
    _submit_spy_placement(session, "site_gauntlgrym")

    assert not _has_pending_generic(session), "Card should be fully resolved"
    assert _influence(session) == before + 2, "Should gain 2 influence"
    session.destroy()


def test_green_wyrmling_no_influence_when_no_other_player_troop():
    """Place spy on site with only own troops → no influence gained."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["green_wyrmling"]},
        troops={"p1": {"site_gauntlgrym": ["p1", None, None]}},
        current_player="p1",
    )

    before = _influence(session)

    _play_card(session, "green_wyrmling")
    _submit_spy_placement(session, "site_gauntlgrym")

    assert not _has_pending_generic(session), "Card should be fully resolved"
    assert _influence(session) == before, "Should NOT gain influence"
    session.destroy()
